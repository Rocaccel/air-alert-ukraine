"""Хранилище настроек в config.json (flash пишется только по Save, атомарно:
сначала config.json.tmp, затем rename — при обрыве питания остаётся либо
старый, либо новый файл, но не полусохранённый).
v2.0: Telegram вычищен — нет channel/слов/зеркал. Только region slug.
"""
try:
    import ujson as json
except ImportError:
    import json

try:
    import uos as os
except ImportError:
    import os

CONFIG_PATH = "config.json"
TMP_PATH = "config.json.tmp"

DEFAULTS = {
    "region": "odeska",
    "check_interval": 60,
    "wifi_ssid": "",
    "wifi_pass": "",
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
    try:
        r = str(out.get("region", "odeska") or "").strip()
    except Exception:
        r = "odeska"
    out["region"] = r if r in _valid_regions() else "odeska"
    return out

def _read(path):
    with open(path, "r") as f:
        return _sanitize(json.load(f))

def load():
    for path in (CONFIG_PATH, TMP_PATH):
        try:
            return _read(path)
        except Exception:
            pass
    return dict(DEFAULTS)

def save(cfg):
    cfg = _sanitize(cfg)
    try:
        with open(TMP_PATH, "w") as f:
            json.dump(cfg, f)
    except Exception:
        try:
            os.remove(TMP_PATH)
        except Exception:
            pass
        return False
    # rename поверх существующего (littlefs) — атомарно, без окна:
    # до rename в config.json остаётся старый целый файл
    try:
        os.rename(TMP_PATH, CONFIG_PATH)
        return True
    except Exception:
        pass
    # FAT-подобный VFS не умеет rename поверх: remove + rename.
    # Если и это не вышло — новый файл цел в TMP_PATH, load() его подхватит
    try:
        os.remove(CONFIG_PATH)
    except Exception:
        pass
    try:
        os.rename(TMP_PATH, CONFIG_PATH)
    except Exception:
        return False
    return True
