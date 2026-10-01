# boot.py — WiFi STA с fallback в AP. Выполняется до main.py.
# Откат по кнопке FLASH (GPIO0): зажать после RST в течение ~2с.
import network
import time

try:
    import logbuf
except Exception:
    logbuf = None

def _log(tag, msg):
    if logbuf:
        try:
            logbuf.log(tag, msg)
            return
        except Exception:
            pass
    try:
        print("[" + tag + "] " + msg)
    except Exception:
        pass

# --- восстановление без панели: кнопка FLASH (GPIO0, NodeMCU-32S) ---
_BTN_PIN = 0
_BTN_WIN_MS = 2000   # окно наблюдения после старта (идёт параллельно с WiFi)
_BTN_HOLD_MS = 400   # удержание низкого уровня для срабатывания
_btn_pin = None
_btn_low_ms = None
_btn_t0 = time.ticks_ms()
_btn_win = time.ticks_add(_btn_t0, _BTN_WIN_MS)
_btn_done = False

def _btn_setup():
    global _btn_pin
    try:
        import machine
        _btn_pin = machine.Pin(_BTN_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
    except Exception:
        _btn_pin = None

def _btn_tick():
    """Опрос GPIO0; True = кнопка зажата >= 400мс (один раз за загрузку)."""
    global _btn_low_ms, _btn_done
    if _btn_done or _btn_pin is None:
        return False
    try:
        v = _btn_pin.value()
    except Exception:
        return False
    if v == 0:
        if _btn_low_ms is None:
            _btn_low_ms = time.ticks_ms()
        elif time.ticks_diff(time.ticks_ms(), _btn_low_ms) >= _BTN_HOLD_MS:
            _btn_done = True
            return True
    else:
        _btn_low_ms = None
    return False

def _btn_rollback():
    """Откат из /bak по кнопке. Успех -> 5 вспышек + reset;
    любая ошибка -> 10 вспышек + обычная загрузка (панель/REPL остаются)."""
    _log("button", "FLASH held -> rollback from /bak")
    try:
        import ota
        res = ota.rollback()
        r = list(res[0]) if isinstance(res, tuple) and res[0] else []
        failed = list(res[1]) if isinstance(res, tuple) and len(res) > 1 and res[1] else []
        if not r and not failed:
            _log("button", "rollback: nothing in /bak")
        else:
            _log("button", "rollback: " + ",".join(r) + (" | fail: " + ",".join(failed) if failed else ""))
        if r and not failed:
            _flash(5, 120)
            try:
                import machine
                machine.reset()
            except Exception as e:
                _log("button", "reset fail: " + str(e))
            return
    except Exception as e:
        _log("button", "rollback ERROR: " + str(e)[:80])
    _flash(10, 120)

_btn_setup()

try:
    from config_store import load
    cfg = load()
except Exception:
    cfg = {"wifi_ssid": "", "wifi_pass": ""}

SSID = cfg.get("wifi_ssid", "") or ""
PASS = cfg.get("wifi_pass", "") or ""

sta = network.WLAN(network.STA_IF)
ap = network.WLAN(network.AP_IF)

sta.active(True)
ap.active(False)

def _connect():
    if not SSID:
        return False
    try:
        if sta.isconnected():
            return True
        sta.connect(SSID, PASS)
        t0 = time.ticks_ms()
        while not sta.isconnected():
            if time.ticks_diff(time.ticks_ms(), t0) > 15000:
                return False
            time.sleep_ms(300)
            if _btn_tick():
                _btn_rollback()
        return True
    except Exception:
        return False

def _flash(n, ms=300):
    """Самопроверка LED при старте: 1 вспышка = STA ok, 2 = AP-режим.
    Никогда не роняет загрузку."""
    try:
        import machine
        try:
            from hw import LED_PIN
        except Exception:
            LED_PIN = 2
        pin = machine.Pin(int(LED_PIN), machine.Pin.OUT)
        for _ in range(n):
            try:
                pin.on()
            except Exception:
                try:
                    pin.value(1)
                except Exception:
                    break
            time.sleep_ms(ms)
            try:
                pin.off()
            except Exception:
                try:
                    pin.value(0)
                except Exception:
                    break
            time.sleep_ms(ms)
    except Exception:
        pass

ok = _connect()
if ok:
    try:
        _log("wifi", "STA IP: " + sta.ifconfig()[0])
    except Exception:
        pass
    _flash(1)
else:
    # Fallback AP для первоначальной настройки
    try:
        ap.active(True)
        ap.config(essid="ESP32-ALERT", authmode=network.AUTH_OPEN)
        _log("wifi", "AP ESP32-ALERT 192.168.4.1")
    except Exception as e:
        _log("wifi", "AP fail: " + str(e))
    _flash(2)

# Остаток окна GPIO0: WiFi уже дал тикам ~1.5-2с, добираем до полного
# окна (100мс/замер). В норме окно уже исчерпано -> задержки нет.
while not _btn_done and _btn_pin is not None:
    if time.ticks_diff(_btn_win, time.ticks_ms()) <= 0:
        break
    time.sleep_ms(100)
    if _btn_tick():
        _btn_rollback()
        break
