# web.py — RU-панель из template.html (двухпроходный чанковый рендер, токены {{...}}).
# Страница ~13КБ никогда не материализуется целиком: проход 1 считает длину тела,
# проход 2 шлет чанками по 512Б. {{REGION_OPTIONS}} (~155 опций) шлется поштучно.
# Причина: при 85КБ свободного heap нет непрерывных 13КБ (фрагментация) — было OOM.
# /upload одиночного .py УБРАН по решению v5 (только бандл + URL публичные).
import gc
import time
import machine

try:
    import usocket as socket
except ImportError:
    import socket
try:
    import uselect as select
except ImportError:
    import select
try:
    import ujson as json
except ImportError:
    import json
try:
    import uos as os
except ImportError:
    import os

import logbuf
import config_store

_ota_mod = None

def _ota():
    # ленивый импорт: ota.py (~6КБ байткода) не фрагментирует кучу к моменту
    # первого TLS-handshake; грузится только при реальном OTA-действии
    global _ota_mod
    if _ota_mod is None:
        import ota as _m
        _ota_mod = _m
    return _ota_mod

def _bak_note():
    # видимое предупреждение: если бэкап не удался, откат вернёт старые файлы
    # не всех файлов — молчать об этом нельзя (раньше падало тихо из-за OOM)
    fails = _ota().LAST_BAK_FAIL
    if not fails:
        return ""
    return " | бэкап не удался: " + ",".join(fails)

TPL_PATH = "template.html"

def _urldecode(s):
    # Правильно для UTF-8: собираем БАЙТЫ (%XX и литералы <128), затем один
    # decode('utf-8'). Старый вариант chr(int(..,16)) трактовал UTF-8-байты
    # как Latin-1 -> двойное кодирование кириллицы в config.json (кракозябры
    # на странице + несрабатывание триггера). Работает и на CPython, и на
    # MicroPython (bytes.decode('utf-8') есть в обоих).
    out = bytearray()
    i = 0
    L = len(s)
    while i < L:
        ch = s[i]
        if ch == "+":
            out.append(32)  # space
            i += 1
            continue
        if ch == "%" and i + 2 < L:
            try:
                out.append(int(s[i + 1:i + 3], 16))
                i += 3
                continue
            except Exception:
                pass
        try:
            o = ord(ch)
        except Exception:
            o = 63
        if o < 128:
            out.append(o)
        else:
            # не-ASCII литерал (не должно быть в form-urlencoded) — как UTF-8
            try:
                for b in ch.encode("utf-8"):
                    out.append(b)
            except Exception:
                pass
        i += 1
    try:
        return bytes(out).decode("utf-8")
    except Exception:
        try:
            return bytes(out).decode("utf-8", "ignore")
        except Exception:
            return "".join(chr(b) for b in out)

def _parse_qs(body):
    d = {}
    for part in body.split("&"):
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        d[_urldecode(k)] = _urldecode(v)
    return d

def _esc(s):
    s = str(s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def _fw():
    try:
        import version as ver
        return ver.FW_VERSION
    except Exception:
        return "?"

def _net_mode(cfg, state):
    # честный режим: офлайн с сохранённым SSID — не AP (AP только при пустом SSID)
    if state.get("ip"):
        return "Онлайн — домашняя сеть"
    if cfg.get("wifi_ssid", ""):
        return "Офлайн — сеть недоступна"
    return "Точка доступа ESP32-ALERT"

def _ago(ts):
    # "35 с назад" / "5 мин назад" для последней проверки
    if not ts:
        return "—"
    try:
        d = time.ticks_diff(time.ticks_ms(), ts) // 1000
    except Exception:
        return "—"
    if d < 0:
        d = 0
    if d < 90:
        return "%d с назад" % d
    if d < 5400:
        return "%d мин назад" % (d // 60)
    if d < 129600:
        return "%d ч назад" % (d // 3600)
    return "%d дн назад" % (d // 86400)

def _uptime():
    try:
        s = time.ticks_ms() // 1000
    except Exception:
        return "?"
    if s < 90:
        return "%d с" % s
    if s < 5400:
        return "%d мин" % (s // 60)
    if s < 129600:
        return "%d ч %d мин" % (s // 3600, (s % 3600) // 60)
    return "%d дн" % (s // 86400)

def _info_tokens(cfg, state):
    # токены страницы /info: человекочитаемые индикаторы работы и ошибок
    err = str(state.get("last_err", "") or "")
    lc = state.get("last_check", "never")
    if err:
        check, ccls = "Ошибка опроса", "err"
    elif lc == "ok":
        check, ccls = "Проверено", "ok"
    elif lc == "offline":
        check, ccls = "Нет сети", "warn"
    else:
        check, ccls = "Ещё не проверялось", "warn"
    if state.get("ip"):
        ncls = "ok"
    elif cfg.get("wifi_ssid", ""):
        ncls = "err"
    else:
        ncls = "warn"
    # здоровье веб-потока: heartbeat обновляется каждые ~50мс
    ts = state.get("worker_ts", 0)
    try:
        age = time.ticks_diff(time.ticks_ms(), ts) // 1000 if ts else -1
    except Exception:
        age = -1
    if 0 <= age < 5:
        worker, wcls = "жив", "ok"
    elif age >= 5:
        worker, wcls = "завис (%d с)" % age, "err"
    else:
        worker, wcls = "—", "warn"
    ssid = cfg.get("wifi_ssid", "") or ""
    lines = logbuf.tail()
    return {
        "{{CHECK}}": _esc(check),
        "{{CHECK_CLS}}": ccls,
        "{{CHECK_AGO}}": _esc(_ago(state.get("last_check_ts", 0))),
        "{{NET_CLS}}": ncls,
        "{{WIFI_SHOW}}": _esc(ssid if ssid else "—"),
        "{{UPTIME}}": _esc(_uptime()),
        "{{HEAP}}": "%d КБ" % (gc.mem_free() // 1024),
        "{{WORKER}}": _esc(worker),
        "{{WORKER_CLS}}": wcls,
        "{{LOG}}": _esc("\n".join(lines)) if lines else "— пусто",
    }

_CHUNK = 512  # чанки чтения template.html: ни одного объекта ~13КБ в RAM
_OPTS_TOKEN = b"{{REGION_OPTIONS}}"

def _iter_regions():
    """Список (slug, name, ubilling) — итерируем как есть, строк не собираем."""
    try:
        import alerts as _a
        return _a.REGIONS
    except Exception:
        return [("odeska", "Одеська область", "Одеська область")]

def _opt_bytes(slug, name):
    # один <option> (~110Б): шлем поштучно, общей строки опций нет
    return (b'<option value="' + str(slug).encode("utf-8") + b'" label="'
            + _esc(name).encode("utf-8") + b'"></option>')

def render_tokens(cfg, state, msg=""):
    alert = bool(state.get("alert"))
    err = str(state.get("last_err", "") or "")
    try:
        import alerts as _a
        region_label = _a.region_name(cfg.get("region", "odeska"))
    except Exception:
        region_label = cfg.get("region", "odeska")
    t = {
        "{{ALERT_CLS}}": "on" if alert else "off",
        "{{ALERT_BADGE}}": "ALERT ON — ТРЕВОГА" if alert else "ALERT OFF — спокойно",
        "{{ALERT_SUB}}": "Мигание включено • LED работает" if alert else "Дежурный режим • LED погашен",
        "{{REGION}}": _esc(region_label),
        "{{REGION_SLUG}}": _esc(cfg.get("region", "odeska")),
        "{{SOURCE}}": _esc(state.get("source", "-")),
        "{{LAST}}": _esc(state.get("last_check", "never")),
        "{{ERR}}": _esc(err if err else "нет"),
        "{{ERR_CLS}}": "err" if err else "ok",
        "{{IP}}": _esc(state.get("ip", "")),
        "{{IPURL}}": _esc(state.get("ip", "") or "192.168.4.1"),
        "{{NETMODE}}": _net_mode(cfg, state),
        "{{FW}}": _esc(_fw()),
        "{{INTERVAL}}": _esc(cfg.get("check_interval", 60)),
        "{{BLINK_ON}}": _esc(cfg.get("blink_on_ms", 500)),
        "{{BLINK_OFF}}": _esc(cfg.get("blink_off_ms", 500)),
        "{{WIFI_SSID}}": _esc(cfg.get("wifi_ssid", "")),
        "{{WIFI_PASS}}": _esc(cfg.get("wifi_pass", "")),
        "{{MSG}}": ('<div class="msg">' + _esc(msg) + "</div>") if msg else "",
    }
    return t

def _send(conn, code, ctype, body):
    if isinstance(body, str):
        body = body.encode("utf-8")
    head = "HTTP/1.0 %d OK\r\nContent-Type: %s\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % (code, ctype, len(body))
    conn.send(head.encode())
    conn.send(body)

def _emit_safe(safe, btoks):
    """safe — кусок шаблона без partial-токена на конце.
    yield (0, bytes) готовые куски и (1, None) маркеры опций."""
    parts = safe.split(_OPTS_TOKEN)
    for i, p in enumerate(parts):
        if i:
            yield (1, None)
        if p:
            for k, v in btoks.items():
                if k in p:
                    p = p.replace(k, v)
            yield (0, p)

def _scan_template(btoks, max_tok, tpl=TPL_PATH):
    """Детерминированный проход по файлу (для замера длины и для отправки).
    Читаем чанками по _CHUNK байт; токен на границе чанков не теряется
    (overlap max_tok + откат partial-токена в carry)."""
    tkeys = tuple(btoks.keys()) + (_OPTS_TOKEN,)
    with open(tpl, "rb") as f:
        carry = b""
        while True:
            piece = f.read(_CHUNK)
            buf = carry + piece if piece else carry
            if not piece:
                if buf:
                    for item in _emit_safe(buf, btoks):
                        yield item
                return
            if len(buf) > max_tok:
                safe, carry = buf[:-max_tok], buf[-max_tok:]
                # partial-токен на стыке — целиком обратно в carry
                cut = 0
                for k in tkeys:
                    m = len(k) - 1
                    if m > len(safe):
                        m = len(safe)
                    while m > cut:
                        if safe.endswith(k[:m]):
                            cut = m
                            break
                        m -= 1
                if cut:
                    safe, carry = safe[:-cut], safe[-cut:] + carry
            else:
                safe, carry = b"", buf
            for item in _emit_safe(safe, btoks):
                yield item

def _send_template(conn, cfg, state, msg="", tpl=TPL_PATH, extra_toks=None):
    toks = render_tokens(cfg, state, msg)
    if extra_toks:
        toks.update(extra_toks)
    btoks = {}
    for k, v in toks.items():
        try:
            btoks[k.encode("utf-8")] = str(v).encode("utf-8")
        except Exception:
            pass
    max_tok = len(_OPTS_TOKEN)
    for k in btoks:
        if len(k) > max_tok:
            max_tok = len(k)
    gc.collect()
    # проход 1: точная длина тела без материализации страницы
    total = 0
    for kind, data in _scan_template(btoks, max_tok, tpl):
        if kind == 0:
            total += len(data)
        else:
            for _s, _n, _u in _iter_regions():
                total += len(_opt_bytes(_s, _n))
    head = ("HTTP/1.0 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
            "Content-Length: %d\r\nConnection: close\r\n\r\n" % total)
    conn.send(head.encode())
    # проход 2: отправка чанками; опции — по одному региону
    for kind, data in _scan_template(btoks, max_tok, tpl):
        if kind == 0:
            if data:
                conn.send(data)
        else:
            for _s, _n, _u in _iter_regions():
                conn.send(_opt_bytes(_s, _n))
    gc.collect()

def start_server(cfg, state):
    s = socket.socket()
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    s.bind(("0.0.0.0", 80))
    s.listen(1)
    s.setblocking(False)
    try:
        poller = select.poll()
        poller.register(s, select.POLLIN)
    except Exception:
        poller = None
    return {"sock": s, "poller": poller}

def _recv_line(conn, buf):
    # MicroPython: bytearray НЕ поддерживает del срезов — работаем bytes+срезы.
    # buf: bytes -> (line, rest)
    while b"\r\n" not in buf:
        try:
            ch = conn.recv(512)
        except Exception:
            break
        if not ch:
            break
        buf = buf + ch
        if len(buf) > 8192:
            break
    if b"\r\n" in buf:
        i = buf.find(b"\r\n")
        line = buf[:i].decode("utf-8", "ignore")
        return line, buf[i + 2:]
    return "", buf

def _recv_exact(conn, buf, n, limit=400 * 1024):
    # buf: bytes -> (data, rest)
    while len(buf) < n:
        if len(buf) > limit:
            raise RuntimeError("too big")
        try:
            ch = conn.recv(1024)
        except Exception:
            break
        if not ch:
            break
        buf = buf + ch
    return buf[:n], buf[n:]

def poll(srv, cfg, state, set_led=None):
    s = srv["sock"]
    poller = srv.get("poller")
    try:
        if poller:
            if not poller.poll(0):
                return
        else:
            s.settimeout(0)
    except Exception:
        return
    try:
        conn, _ = s.accept()
    except Exception:
        return
    try:
        try:
            conn.settimeout(5)
        except Exception:
            pass
        buf = b""
        req, buf = _recv_line(conn, buf)
        if not req:
            conn.close()
            return
        parts = req.split(" ")
        method = parts[0] if len(parts) > 0 else "GET"
        path = parts[1] if len(parts) > 1 else "/"
        headers = {}
        while True:
            line, buf = _recv_line(conn, buf)
            if line is None or line == "":
                break
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        clen = int(headers.get("content-length", "0") or "0")
        ctype = headers.get("content-type", "")
        if path == "/" and method == "GET":
            gc.collect()
            _send_template(conn, cfg, state)
        elif path == "/status" and method == "GET":
            st = dict(state)
            st["fw"] = _fw()
            st["region"] = cfg.get("region")
            st["interval"] = cfg.get("check_interval")
            st["blink_on_ms"] = cfg.get("blink_on_ms")
            st["blink_off_ms"] = cfg.get("blink_off_ms")
            st["log_tail"] = logbuf.tail()
            _send(conn, 200, "application/json", json.dumps(st))
        elif path == "/info" and method == "GET":
            # человекочитаемая страница состояния (индикаторы + журнал)
            gc.collect()
            _send_template(conn, cfg, state, "", "info.html",
                           _info_tokens(cfg, state))
        elif path == "/save" and method == "POST":
            raw, buf = _recv_exact(conn, buf, clen, 8192)
            form = _parse_qs(raw.decode("utf-8", "ignore"))
            old_ssid = cfg.get("wifi_ssid", "")
            old_pass = cfg.get("wifi_pass", "")
            region_warn = False
            if "region" in form:
                new_slug = form.get("region", "")
                try:
                    import alerts as _a
                    ok = _a.valid_region(new_slug)
                except Exception:
                    ok = False
                if ok:
                    cfg["region"] = new_slug
                else:
                    # мусор/опечатка: молча в дефолт не падаем, оставляем старый
                    region_warn = True
            try:
                cfg["check_interval"] = max(10, min(3600, int(form.get("check_interval", cfg.get("check_interval", 60)))))
            except Exception:
                pass
            # поля мигания: зажим 50..5000, мусор не затирает старую настройку
            cfg["blink_on_ms"] = config_store.blink_ms(
                form.get("blink_on_ms"), cfg.get("blink_on_ms", 500))
            cfg["blink_off_ms"] = config_store.blink_ms(
                form.get("blink_off_ms"), cfg.get("blink_off_ms", 500))
            # клиент отправил число, а применено другое -> зажим 50..5000
            blink_clamped = False
            for _k in ("blink_on_ms", "blink_off_ms"):
                try:
                    if int(str(form.get(_k, "")).strip()) != cfg[_k]:
                        blink_clamped = True
                except Exception:
                    pass
            cfg["wifi_ssid"] = form.get("wifi_ssid", cfg.get("wifi_ssid", ""))
            cfg["wifi_pass"] = form.get("wifi_pass", cfg.get("wifi_pass", ""))
            wifi_changed = (cfg.get("wifi_ssid", "") != old_ssid
                            or cfg.get("wifi_pass", "") != old_pass)
            try:
                if not config_store.save(cfg):
                    raise RuntimeError("запись config.json не удалась")
                if wifi_changed:
                    msg = "Сохранено, перезагрузка для нового WiFi..."
                else:
                    msg = "Сохранено"
                if region_warn:
                    msg += " (регион не распознан — оставлен прежний)"
                if blink_clamped:
                    msg += " (мигание приведено к 50–5000)"
                logbuf.log("web", "save region=%s interval=%s blink=%s/%s wifi_changed=%s" % (
                    cfg.get("region"), cfg.get("check_interval"),
                    cfg.get("blink_on_ms"), cfg.get("blink_off_ms"), wifi_changed))
            except Exception as e:
                msg = "Ошибка сохранения: " + str(e)
                wifi_changed = False
                logbuf.log("web", "save ERR: " + str(e)[:100])
            _send_template(conn, cfg, state, msg)
            if wifi_changed:
                # ответ уже отправлен целиком — пауза и ребут (STA коннектится в boot.py)
                logbuf.log("web", "reboot (wifi changed)")
                try:
                    conn.close()
                except Exception:
                    pass
                try:
                    import time as _t
                    _t.sleep_ms(500)
                except Exception:
                    pass
                machine.reset()
                return
        elif path == "/reboot" and method == "POST":
            if clen:
                try:
                    _d, buf = _recv_exact(conn, buf, min(clen, 2048), 8192)
                except Exception:
                    pass
            _send(conn, 200, "text/plain", "reboot...")
            try:
                conn.close()
            except Exception:
                pass
            logbuf.log("web", "reboot by user")
            import time
            time.sleep_ms(300)
            machine.reset()
            return
        elif path == "/upload" and method == "POST":
            # v5: одиночная заливка убрана — только бандл
            try:
                _d, buf = _recv_exact(conn, buf, min(clen, 8192), 400 * 1024)
            except Exception:
                pass
            _send_template(conn, cfg, state, "Одиночная загрузка отключена — используйте .tar.gz бандл")
        elif path == "/ota-bundle" and method == "POST":
            msg = _handle_multipart(conn, buf, clen, ctype, cfg)
            logbuf.log("ota", "bundle: " + msg[:100])
            _send_template(conn, cfg, state, msg)
        elif path == "/ota-url" and method == "POST":
            raw, buf = _recv_exact(conn, buf, clen, 8192)
            form = _parse_qs(raw.decode("utf-8", "ignore"))
            msg = _handle_url(form, cfg)
            logbuf.log("ota", "url: " + msg[:100])
            _send_template(conn, cfg, state, msg)
        else:
            _send(conn, 404, "text/plain", "not found")
    except Exception as e:
        try:
            _send(conn, 500, "text/plain", "err: " + str(e)[:200])
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
        gc.collect()

def _handle_url(form, cfg):
    # v5: только публичные URL, без токенов
    url = (form.get("url", "") or "").strip()
    if not url.startswith("http"):
        return "Некорректный URL (нужен http/https)"
    is_bundle = ("bundle" in form) or url.endswith(".tar.gz") or url.endswith(".tgz")
    if is_bundle:
        if _ota().free_bytes() < 600 * 1024:
            return "Мало места во flash"
        tmp = "tmp_bundle.tar.gz"
        try:
            _ota().download_url(url, tmp, _ota().MAX_BUNDLE)
            written = _ota().unpack_tar_gz(tmp)
            try:
                os.remove(tmp)
            except Exception:
                pass
            return "Пакет OK: " + ",".join(written) + " — перезагрузите вручную" + _bak_note()
        except Exception as e:
            return "Ошибка пакета: " + str(e)[:200]
    else:
        target = _ota().safe_name(form.get("target", "main.py"))
        if not _ota().is_allowed(target):
            return "Target запрещен (разрешены: пакет или файл: main.py, web.py, alerts.py, ota.py, config_store.py, boot.py, version.py, hw.py, logbuf.py, template.html, info.html, web.mpy, alerts.mpy)"
        try:
            _ota().download_url(url, "tmp_ota.py", _ota().MAX_SINGLE)
            _ota().LAST_BAK_FAIL[:] = []  # иначе в сообщении останется список из прошлого бандла
            _ota().backup(target)
            with open("tmp_ota.py", "rb") as f:
                data = f.read()
            _ota().write_file(target, data)
            try:
                os.remove("tmp_ota.py")
            except Exception:
                pass
            msg = "Файл OK: " + target + " — перезагрузите вручную"
            if target.endswith(".py") and target in ("web.py", "alerts.py"):
                # у .py приоритет над .mpy: после ребута устройство скомпилирует
                # файл само (66КБ подряд после WiFi) — пик рвёт кучу и сеть.
                msg += ("; ВНИМАНИЕ: " + target + " получит приоритет над "
                        + target[:-3] + ".mpy — при ребуте будет on-device "
                        "компиляция (риск: плата перестанет отвечать). "
                        "Предпочтительнее залить " + target[:-3] + ".mpy")
            return msg + _bak_note()
        except Exception as e:
            return "Ошибка файла: " + str(e)[:200]

def _handle_multipart(conn, buf, clen, ctype, cfg):
    if "boundary=" not in ctype:
        return "Нужен multipart"
    b = ctype.split("boundary=")[-1].strip().strip('"')
    bound = ("--" + b).encode()
    end_bound = ("--" + b + "--").encode()
    limit = _ota().MAX_BUNDLE
    if clen > limit + 4096:
        return "Файл слишком большой"
    if _ota().free_bytes() < 600 * 1024:
        return "Мало места во flash"
    # стрим тела сразу в файл: в RAM только чанк ~1КБ + holdback ~100Б.
    # holdback держит хвост (концевые \r\n + граница), чтобы отрезать ее
    # без материализации тела (было OOM на 23КБ бандле при 62КБ free).
    hold = len(end_bound) + 4
    try:
        f = open("tmp_bundle.tar.gz", "wb")
    except Exception as e:
        return "Ошибка файла: " + str(e)[:100]

    def _drop_tmp():
        try:
            f.close()
        except Exception:
            pass
        try:
            os.remove("tmp_bundle.tar.gz")
        except Exception:
            pass

    pend = b""  # неподтвержденный хвост: заголовки part / хвост под границу
    data_started = False
    head = buf  # байты, уже принятые poll (заголовки запроса + начало тела)
    received = 0  # байт данных записано в файл (без границ)
    try:
        rest = clen
        while rest > 0 or head:
            if head:
                ch = head[:1024]
                head = head[1024:]
                if len(ch) > rest:
                    ch = ch[:rest]
            else:
                if rest <= 0:
                    break
                try:
                    ch = conn.recv(1024 if rest > 1024 else rest)
                except Exception as e:
                    raise RuntimeError("recv: " + str(e)[:60])
                if not ch:
                    break
            rest -= len(ch)
            pend = pend + ch
            if not data_started:
                if len(pend) > 2048 + hold:
                    _drop_tmp()
                    return "Битый multipart"
                dp = pend.find(b"\r\n\r\n")
                if dp < 0:
                    continue
                pend = pend[dp + 4:]
                data_started = True
            # сливаем все кроме хвоста hold
            if len(pend) > hold:
                f.write(pend[:-hold])
                received += len(pend) - hold
                if received > limit + hold + 8192:
                    _drop_tmp()
                    return "Файл слишком большой"
                pend = pend[-hold:]
        if not data_started:
            _drop_tmp()
            return "Битый multipart"
        # в pend: хвост данных + \r\n + граница (+финальный \r\n)
        de = pend.rfind(end_bound)
        if de < 0:
            de = pend.rfind(bound)
        if de < 0:
            _drop_tmp()
            return "Битый multipart"
        data_tail = pend[:de - 2] if de >= 2 and pend[de - 2:de] == b"\r\n" else pend[:de]
        f.write(data_tail)
        received += len(data_tail)
        f.close()
    except Exception as e:
        _drop_tmp()
        return "Ошибка приема: " + str(e)[:100]
    if received > limit:
        _drop_tmp()
        return "Файл слишком большой"
    del pend
    gc.collect()
    try:
        written = _ota().unpack_tar_gz("tmp_bundle.tar.gz")
        try:
            os.remove("tmp_bundle.tar.gz")
        except Exception:
            pass
        return "Пакет OK: " + ",".join(written) + " — перезагрузите вручную" + _bak_note()
    except Exception as e:
        return "Ошибка пакета: " + str(e)[:200]
