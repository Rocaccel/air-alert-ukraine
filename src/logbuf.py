# logbuf.py — кольцевой лог в RAM (без flash) + дублирование в REPL.
# Последние N строк доступны через /status как log_tail.
MAX_LINES = 25

_buf = []

def _ts():
    try:
        import time
        return "%ds" % (time.ticks_ms() // 1000)
    except Exception:
        return "?"

def log(tag, msg):
    line = "[%s][%s] %s" % (_ts(), tag, msg)
    try:
        print(line)
    except Exception:
        pass
    try:
        _buf.append(line)
        while len(_buf) > MAX_LINES:
            del _buf[0]
    except Exception:
        pass
    return line

def tail():
    try:
        return list(_buf)
    except Exception:
        return []
