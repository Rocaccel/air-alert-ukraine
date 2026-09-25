"""Хранилище настроек в config.json (flash пишется только по Save).
v2.0: Telegram вычищен — нет channel/слов/зеркал. Только region slug.
"""
try:
    import ujson as json
except ImportError:
    import json

CONFIG_PATH = "config.json"

DEFAULTS = {
    "region": "odeska",
    "check_interval": 60,
    "wifi_ssid": "",
    "wifi_pass": "",
    "ota_enabled": True,
    "blink_on_ms": 500,
    "blink_off_ms": 500,
}

_VALID = None

def _valid_regions():
    global _VALID
    if _VALID is None:
        try:
            import alerts as _a
            _VALID = set(s for s, _n, _u in _a.REGIONS)
        except Exception:
            _VALID = set(["odeska"])
    return _VALID

def _sanitize(cfg):
    out = dict(DEFAULTS)
    try:
        for k in out:
            if k in cfg:
                out[k] = cfg[k]
    except Exception:
        pass
    try:
        out["check_interval"] = int(out["check_interval"])
    except Exception:
        out["check_interval"] = 60
    if out["check_interval"] < 10:
        out["check_interval"] = 10
    if out["check_interval"] > 3600:
        out["check_interval"] = 3600
    out["ota_enabled"] = bool(out["ota_enabled"])
    try:
        r = str(out.get("region", "odeska") or "").strip()
    except Exception:
        r = "odeska"
    out["region"] = r if r in _valid_regions() else "odeska"
    return out

def load():
    try:
        with open(CONFIG_PATH, "r") as f:
            return _sanitize(json.load(f))
    except Exception:
        return dict(DEFAULTS)

def save(cfg):
    cfg = _sanitize(cfg)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f)
    return cfg
