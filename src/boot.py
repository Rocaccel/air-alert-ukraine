# boot.py — WiFi STA с fallback в AP. Выполняется до main.py.
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
