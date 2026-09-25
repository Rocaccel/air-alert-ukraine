# main.py v2.0 — Telegram вычищен. Источник: легкие API (ubilling/tryvoha).
# Главный таск: опрос API + WiFi-монитор + сторож веб-потока.
# Вторичный поток (стек 6КБ): мигание LED + веб-панель + heartbeat.
# Без записей во flash в цикле.
import gc
import time
import machine

import config_store
import alerts
import web as webmod
import version
import logbuf
from hw import LED_PIN

try:
    import _thread
    HAVE_THREAD = True
except Exception:
    HAVE_THREAD = False

cfg = config_store.load()

# LED зашит в hw.py (NodeMCU-32S: GPIO2 встроенный + внешний параллельно)
try:
    led = machine.Pin(int(LED_PIN), machine.Pin.OUT)
except Exception:
    led = machine.Pin(2, machine.Pin.OUT)
try:
    led.off()
except Exception:
    try:
        led.value(0)
    except Exception:
        pass

state = {
    "alert": False,
    "last_check": "never",
    "last_err": "",
    "source": "-",
    "region": cfg.get("region", "odeska"),
    "ip": "",
    "worker_ts": 0,     # heartbeat веб-потока
    "worker_gen": 0,    # поколение веб-потока (для перезапуска)
}

try:
    import network
    sta = network.WLAN(network.STA_IF)
    if sta.isconnected():
        state["ip"] = sta.ifconfig()[0]
except Exception:
    sta = None

logbuf.log("boot", "esp-alert %s region=%s interval=%s thread=%s" % (
    version.FW_VERSION, cfg.get("region"), cfg.get("check_interval"), HAVE_THREAD))

try:
    gc.collect()
    gc.threshold(gc.mem_free() // 4 + 15000)
except Exception:
    pass

# замок для state между потоками
try:
    _lock = _thread.allocate_lock() if HAVE_THREAD else None
except Exception:
    _lock = None
    HAVE_THREAD = False

def _take():
    if _lock:
        try:
            _lock.acquire()
        except Exception:
            pass

def _give():
    if _lock:
        try:
            _lock.release()
        except Exception:
            pass

def _interval():
    try:
        v = int(cfg.get("check_interval", 60))
    except Exception:
        v = 60
    if v < 10:
        v = 10
    if v > 3600:
        v = 3600
    return v

def _mem():
    try:
        return gc.mem_free()
    except Exception:
        return -1

def set_led(on):
    try:
        if on:
            led.on()
        else:
            led.off()
    except Exception:
        try:
            led.value(1 if on else 0)
        except Exception:
            pass

def _friendly_err(e):
    s = str(e)
    if "MALLOC" in s.upper() or "ENOMEM" in s or "ENOMEM" in repr(e):
        return "OOM (мало RAM, повтор)"
    if "-202" in s or "EAI_NONAME" in s or "getaddrinfo" in s or "dns" in s.lower():
        return "нет сети/DNS (STA offline?)"
    return s[:120]

def _online():
    try:
        return sta is not None and sta.isconnected()
    except Exception:
        return False

_last_skip_log = None

def do_check(first=False, retries=3):
    global _last_skip_log
    # v2.0.1: без WiFi проверять нечего (AP-режим = нет интернета).
    # Пропускаем тихо: лог не чаще раза в 5 мин, LED держит последнее.
    if not _online():
        try:
            now = time.ticks_ms()
        except Exception:
            now = 0
        try:
            quiet = (_last_skip_log is not None
                     and time.ticks_diff(now, _last_skip_log) < 300000)
        except Exception:
            quiet = False
        _take()
        try:
            state["last_check"] = "offline"
        finally:
            _give()
        if not quiet:
            _last_skip_log = now
            logbuf.log("check", "skip: offline (AP mode, no internet)")
        return
    gc.collect()
    free0 = _mem()
    slug = cfg.get("region", "odeska")
    for attempt in range(1, retries + 1):
        try:
            alert, source = alerts.check(slug)
            break
        except Exception as e:
            gc.collect()
            if attempt < retries:
                logbuf.log("check", "try %d/%d fail: %s | %r free0=%s" % (
                    attempt, retries, _friendly_err(e), e, free0))
                time.sleep_ms(2000)
            else:
                _take()
                try:
                    state["last_err"] = _friendly_err(e)
                finally:
                    _give()
                logbuf.log("check", "ERR: %s | %r free0=%s" % (
                    state["last_err"], e, free0))
                gc.collect()
                return
    try:
        free = _mem()
        _take()
        try:
            prev = state["alert"]
            state["alert"] = bool(alert)
            state["source"] = source
            state["region"] = slug
            state["last_check"] = "ok"
            state["last_err"] = ""
            snap_alert = state["alert"]
        finally:
            _give()
        if first:
            logbuf.log("boot", "init %s=%s src=%s free=%s" % (slug, snap_alert, source, free))
        elif snap_alert != prev:
            logbuf.log("TRIGGER", "-> %s src=%s free=%s" % (snap_alert, source, free))
        else:
            logbuf.log("check", "ok %s=%s src=%s free=%s" % (slug, snap_alert, source, free))
    except Exception as e:
        _take()
        try:
            state["last_err"] = str(e)[:120]
        finally:
            _give()
        logbuf.log("check", "ERR: %s | %r" % (state["last_err"], e))
    gc.collect()

def blink_on_ms():
    try:
        return int(cfg.get("blink_on_ms", 500))
    except Exception:
        return 500

def blink_off_ms():
    try:
        return int(cfg.get("blink_off_ms", 500))
    except Exception:
        return 500

def worker_task(gen):
    """Веб + мигание во вторичном потоке. Чужое поколение — выход."""
    led_state = False
    try:
        last_toggle = time.ticks_ms()
    except Exception:
        last_toggle = 0
    while True:
        try:
            if gen != state.get("worker_gen"):
                return
        except Exception:
            pass
        try:
            now = time.ticks_ms()
        except Exception:
            now = 0
        # 1) мигание
        try:
            cur_alert = state.get("alert", False)
        except Exception:
            cur_alert = False
        if cur_alert:
            try:
                iv = blink_on_ms() if led_state else blink_off_ms()
            except Exception:
                iv = 500
            try:
                diff = time.ticks_diff(now, last_toggle)
            except Exception:
                diff = iv
            if diff >= iv:
                led_state = not led_state
                set_led(led_state)
                last_toggle = now
        else:
            if led_state:
                led_state = False
                set_led(False)
                last_toggle = now
        # 2) веб (неблокирующий accept + короткие ответы)
        if srv:
            try:
                webmod.poll(srv, cfg, state, config_store, set_led)
            except Exception as e:
                logbuf.log("web", "poll err: " + str(e)[:100])
        # 3) heartbeat
        _take()
        try:
            try:
                state["worker_ts"] = time.ticks_ms()
            except Exception:
                state["worker_ts"] = 1
        finally:
            _give()
        try:
            time.sleep_ms(50)
        except Exception:
            pass

def start_worker():
    global HAVE_THREAD
    _take()
    try:
        state["worker_gen"] = state.get("worker_gen", 0) + 1
        try:
            state["worker_ts"] = time.ticks_ms()
        except Exception:
            state["worker_ts"] = 1
        gen = state["worker_gen"]
    finally:
        _give()
    if not HAVE_THREAD:
        return False
    try:
        try:
            # 6КБ: дежурный режим не затронут (OTA-распаковка — единственный риск)
            _thread.stack_size(6 * 1024)
        except Exception:
            pass
        _thread.start_new_thread(worker_task, (gen,))
        logbuf.log("worker", "thread started gen=%s stack=6k" % gen)
        return True
    except Exception as e:
        HAVE_THREAD = False
        logbuf.log("worker", "thread fail (%r), sync mode" % (e,))
        return False

def wifi_step():
    try:
        if sta is not None and sta.isconnected():
            ip = sta.ifconfig()[0]
            if ip != state.get("ip"):
                _take()
                try:
                    state["ip"] = ip
                finally:
                    _give()
                logbuf.log("wifi", "ip=" + ip)
        else:
            if state.get("ip"):
                logbuf.log("wifi", "lost (AP fallback активен если был)")
                _take()
                try:
                    state["ip"] = ""
                finally:
                    _give()
    except Exception as e:
        logbuf.log("wifi", "mon err: " + str(e)[:80])

# веб-сервер СТАРТУЕТ ДО первой проверки: портал доступен через ~3с
srv = None
try:
    srv = webmod.start_server(cfg, state, config_store)
    logbuf.log("web", "on :80 ip=" + str(state.get("ip", "")))
except Exception as e:
    logbuf.log("web", "fail: " + str(e))

worker_ok = start_worker()
last_watchdog = 0

if not worker_ok:
    # fallback без потоков: все синхронно в главном цикле
    logbuf.log("worker", "sync fallback mode")
    do_check(first=True)
    led_state = False
    try:
        last_toggle = time.ticks_ms()
    except Exception:
        last_toggle = 0
    last_poll = 0
    last_wifi = 0
    while True:
        try:
            now = time.ticks_ms()
        except Exception:
            now = 0
        try:
            cur_alert = state.get("alert", False)
        except Exception:
            cur_alert = False
        if cur_alert:
            try:
                iv = blink_on_ms() if led_state else blink_off_ms()
                diff = time.ticks_diff(now, last_toggle)
            except Exception:
                iv, diff = 500, 0
            if diff >= iv:
                led_state = not led_state
                set_led(led_state)
                last_toggle = now
        else:
            if led_state:
                led_state = False
                set_led(False)
                last_toggle = now
        try:
            interval_ms = _interval() * 1000
        except Exception:
            interval_ms = 60000
        try:
            elapsed = time.ticks_diff(now, last_poll)
        except Exception:
            elapsed = interval_ms
        if last_poll == 0 or elapsed >= interval_ms:
            last_poll = now
            do_check(first=False)
        if srv:
            try:
                webmod.poll(srv, cfg, state, config_store, set_led)
            except Exception as e:
                logbuf.log("web", "poll err: " + str(e)[:100])
        try:
            wdiff = time.ticks_diff(now, last_wifi)
        except Exception:
            wdiff = 0
        if wdiff >= 30000:
            last_wifi = now
            wifi_step()
        try:
            time.sleep_ms(50)
        except Exception:
            pass

# основной режим: проверка в главном таске, сторож веб-потока + WiFi
do_check(first=True)
while True:
    iv = _interval()
    slept = 0
    while slept < iv:
        time.sleep(1)
        slept += 1
        wifi_step()
        # сторож веб-потока (кулдаун 60с от дублей)
        if HAVE_THREAD:
            try:
                now = time.ticks_ms()
                ts = state.get("worker_ts", 0)
                if time.ticks_diff(now, ts) > 15000 and time.ticks_diff(now, last_watchdog) > 60000:
                    last_watchdog = now
                    logbuf.log("worker", "stale ts, restarting thread")
                    start_worker()
            except Exception as e:
                logbuf.log("worker", "watchdog err: " + str(e)[:80])
    do_check(first=False)
