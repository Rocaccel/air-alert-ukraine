"""Источники тревоги БЕЗ Telegram (v2.0): два зашитых легких API по plain HTTP.
Добавить свои источники нельзя — только эти два с авто-failover.

1. Ubilling aerialalerts: http://ubilling.net.ua/aerialalerts/
   без ключей, ~2.5КБ: {"states": {"Одеська область": {"alertnow": bool}}}
2. Tryvoha: http://tryvoha.online/api/v1/alerts/{slug}
   без ключей, ~300Б: {"active": bool, "active_anywhere": bool, ...}
Только RAM, во flash ничего не пишем.
"""
CHUNK = 2048
FETCH_DEADLINE_MS = 60000
SOCK_TIMEOUT = 12
BODY_LIMIT = 16384
DNS_TTL_MS = 600000

UBILL_URL = "http://ubilling.net.ua/aerialalerts/"
TRYVOHA_URL = "http://tryvoha.online/api/v1/alerts/"

# (tryvoha-slug, имя на странице, имя в ubilling | None у районов/городов-громад)
# Области + м.Київ (есть в обоих API), затем города-state и все районы (только tryvoha).
REGIONS = [
    ("odeska", "Одеська область", "Одеська область"),
    ("vinnicka-oblast", "Вінницька область", "Вінницька область"),
    ("volinska-oblast", "Волинська область", "Волинська область"),
    ("dnipropetrovska", "Дніпропетровська область", "Дніпропетровська область"),
    ("donecka-oblast", "Донецька область", "Донецька область"),
    ("zitomirska-oblast", "Житомирська область", "Житомирська область"),
    ("zakarpatska-oblast", "Закарпатська область", "Закарпатська область"),
    ("zaporizka-oblast", "Запорізька область", "Запорізька область"),
    ("ivano-frankivska-oblast", "Івано-Франківська область", "Івано-Франківська область"),
    ("kyivska", "Київська область", "Київська область"),
    ("kyiv", "м. Київ", "м. Київ"),
    ("kirovogradska-oblast", "Кіровоградська область", "Кіровоградська область"),
    ("luganska-oblast", "Луганська область", "Луганська область"),
    ("lvivska", "Львівська область", "Львівська область"),
    ("mikolayivska-oblast", "Миколаївська область", "Миколаївська область"),
    ("poltavska-oblast", "Полтавська область", "Полтавська область"),
    ("rivnenska-oblast", "Рівненська область", "Рівненська область"),
    ("sumska-oblast", "Сумська область", "Сумська область"),
    ("ternopilska-oblast", "Тернопільська область", "Тернопільська область"),
    ("xarkivska-oblast", "Харківська область", "Харківська область"),
    ("xersonska-oblast", "Херсонська область", "Херсонська область"),
    ("xmelnycka-oblast", "Хмельницька область", "Хмельницька область"),
    ("cerkaska-oblast", "Черкаська область", "Черкаська область"),
    ("cernivecka-oblast", "Чернівецька область", "Чернівецька область"),
    ("cernigivska-oblast", "Чернігівська область", "Чернігівська область"),
    ("m-zaporizzia-ta-zaporizka-teritorialna-gromada", "м. Запоріжжя", None),
    ("m-xarkiv-ta-xarkivska-teritorialna-gromada", "м. Харків", None),
    ("baxmutskii-raion", "Бахмутський район", None),
    ("bastanskii-raion", "Баштанський район", None),
    ("berdicivskii-raion", "Бердичівський район", None),
    ("berdianskii-raion", "Бердянський район", None),
    ("beregivskii-raion", "Берегівський район", None),
    ("berezivskii-raion", "Березівський район", None),
    ("berislavskii-raion", "Бериславський район", None),
    ("bilgorod-dnistrovskii-raion", "Білгород-Дністровський район", None),
    ("bilocerkivskii-raion", "Білоцерківський район", None),
    ("bogoduxivskii-raion", "Богодухівський район", None),
    ("bolgradskii-raion", "Болградський район", None),
    ("borispilskii-raion", "Бориспільський район", None),
    ("brovarskii-raion", "Броварський район", None),
    ("bucanskii-raion", "Бучанський район", None),
    ("varaskii-raion", "Вараський район", None),
    ("vasilivskii-raion", "Василівський район", None),
    ("verxovinskii-raion", "Верховинський район", None),
    ("viznickii-raion", "Вижницький район", None),
    ("visgorodskii-raion", "Вишгородський район", None),
    ("vinnickii-raion", "Вінницький район", None),
    ("voznesenskii-raion", "Вознесенський район", None),
    ("volnovaskii-raion", "Волноваський район", None),
    ("volodimir-volinskii-raion", "Володимир-Волинський район", None),
    ("gaisinskii-raion", "Гайсинський район", None),
    ("geniceskii-raion", "Генічеський район", None),
    ("golovanivskii-raion", "Голованівський район", None),
    ("gorlivskii-raion", "Горлівський район", None),
    ("dniprovskii-raion", "Дніпровський район", None),
    ("dnistrovskii-raion", "Дністровський район", None),
    ("doneckii-raion", "Донецький район", None),
    ("drogobickii-raion", "Дрогобицький район", None),
    ("dubenskii-raion", "Дубенський район", None),
    ("zitomirskii-raion", "Житомирський район", None),
    ("zmerinskii-raion", "Жмеринський район", None),
    ("zviagelskii-raion", "Звягельський район", None),
    ("zaporizkii-raion", "Запорізький район", None),
    ("zvenigorodskii-raion", "Звенигородський район", None),
    ("zolotoniskii-raion", "Золотоніський район", None),
    ("zolocivskii-raion", "Золочівський район", None),
    ("ivano-frankivskii-raion", "Івано-Франківський район", None),
    ("izmayilskii-raion", "Ізмаїльський район", None),
    ("iziumskii-raion", "Ізюмський район", None),
    ("kaluskii-raion", "Калуський район", None),
    ("kalmiuskii-raion", "Кальміуський район", None),
    ("kamianec-podilskii-raion", "Кам'янець-Подільський район", None),
    ("kamianskii-raion", "Кам'янський район", None),
    ("kamin-kasirskii-raion", "Камінь-Каширський район", None),
    ("kaxovskii-raion", "Каховський район", None),
    ("kovelskii-raion", "Ковельський район", None),
    ("kolomiiskii-raion", "Коломийський район", None),
    ("konotopskii-raion", "Конотопський район", None),
    ("korostenskii-raion", "Коростенський район", None),
    ("koriukivskii-raion", "Корюківський район", None),
    ("kosivskii-raion", "Косівський район", None),
    ("kramatorskii-raion", "Краматорський район", None),
    ("krasnogradskii-raion", "Красноградський район", None),
    ("kremeneckii-raion", "Кременецький район", None),
    ("kremencuckii-raion", "Кременчуцький район", None),
    ("krivorizkii-raion", "Криворізький район", None),
    ("kropivnickii-raion", "Кропивницький район", None),
    ("kupianskii-raion", "Куп'янський район", None),
    ("lozivskii-raion", "Лозівський район", None),
    ("lubenskii-raion", "Лубенський район", None),
    ("luckii-raion", "Луцький район", None),
    ("lvivskii-raion", "Львівський район", None),
    ("mariupolskii-raion", "Маріупольський район", None),
    ("melitopolskii-raion", "Мелітопольський район", None),
    ("mikolayivskii-raion", "Миколаївський район", None),
    ("mirgorodskii-raion", "Миргородський район", None),
    ("mogiliv-podilskii-raion", "Могилів-Подільський район", None),
    ("mukacivskii-raion", "Мукачівський район", None),
    ("nadvirnianskii-raion", "Надвірнянський район", None),
    ("nizinskii-raion", "Ніжинський район", None),
    ("nikopolskii-raion", "Нікопольський район", None),
    ("novgorod-siverskii-raion", "Новгород-Сіверський район", None),
    ("novoukrayinskii-raion", "Новоукраїнський район", None),
    ("obuxivskii-raion", "Обухівський район", None),
    ("odeskii-raion", "Одеський район", None),
    ("oleksandriiskii-raion", "Олександрійський район", None),
    ("oxtirskii-raion", "Охтирський район", None),
    ("pavlogradskii-raion", "Павлоградський район", None),
    ("pervomaiskii-raion", "Первомайський район", None),
    ("podilskii-raion", "Подільський район", None),
    ("pokrovskii-raion", "Покровський район", None),
    ("pologivskii-raion", "Пологівський район", None),
    ("poltavskii-raion", "Полтавський район", None),
    ("priluckii-raion", "Прилуцький район", None),
    ("raxivskii-raion", "Рахівський район", None),
    ("rivnenskii-raion", "Рівненський район", None),
    ("rozdilnianskii-raion", "Роздільнянський район", None),
    ("romenskii-raion", "Роменський район", None),
    ("samarivskii-raion", "Самарівський район", None),
    ("sambirskii-raion", "Самбірський район", None),
    ("sarnenskii-raion", "Сарненський район", None),
    ("sinelnikivskii-raion", "Синельниківський район", None),
    ("skadovskii-raion", "Скадовський район", None),
    ("striiskii-raion", "Стрийський район", None),
    ("sumskii-raion", "Сумський район", None),
    ("ternopilskii-raion", "Тернопільський район", None),
    ("tulcinskii-raion", "Тульчинський район", None),
    ("tiacivskii-raion", "Тячівський район", None),
    ("uzgorodskii-raion", "Ужгородський район", None),
    ("umanskii-raion", "Уманський район", None),
    ("fastivskii-raion", "Фастівський район", None),
    ("xarkivskii-raion", "Харківський район", None),
    ("xersonskii-raion", "Херсонський район", None),
    ("xmelnickii-raion", "Хмельницький район", None),
    ("xmilnickii-raion", "Хмільницький район", None),
    ("xustskii-raion", "Хустський район", None),
    ("cerkaskii-raion", "Черкаський район", None),
    ("cerniveckii-raion", "Чернівецький район", None),
    ("cernigivskii-raion", "Чернігівський район", None),
    ("cortkivskii-raion", "Чортківський район", None),
    ("cuguyivskii-raion", "Чугуївський район", None),
    ("sepetivskii-raion", "Шепетівський район", None),
    ("septickii-raion", "Шептицький район", None),
    ("sostkinskii-raion", "Шосткинський район", None),
    ("iavorivskii-raion", "Яворівський район", None),
]
DEFAULT_REGION = "odeska"

# Район/громада -> родительская область (tryvoha-slug). Нужно для fallback:
# с 2026-09 tryvoha отдает plain HTTP 301 на https (на ESP нет TLS), поэтому
# при недоступности tryvoha район показывает тревогу своей ОБЛАСТИ по ubilling
# (источник "ubilling~oblast" — аппроксимация, см. check()).
# Часть сверена с живым tryvoha /api/v1/alerts (поле oblast_slug), остальное —
# райцентр -> область по админ. делению 2020 (Первомайский район — только
# Николаевская обл.: Харьковский упразднен в 2020).
PARENT = {
    # vinnicka-oblast
    "gaisinskii-raion": "vinnicka-oblast",
    "mogiliv-podilskii-raion": "vinnicka-oblast",
    "tulcinskii-raion": "vinnicka-oblast",
    "vinnickii-raion": "vinnicka-oblast",
    "xmilnickii-raion": "vinnicka-oblast",
    "zmerinskii-raion": "vinnicka-oblast",
    # volinska-oblast
    "kamin-kasirskii-raion": "volinska-oblast",
    "kovelskii-raion": "volinska-oblast",
    "luckii-raion": "volinska-oblast",
    "volodimir-volinskii-raion": "volinska-oblast",
    # dnipropetrovska
    "dniprovskii-raion": "dnipropetrovska",
    "kamianskii-raion": "dnipropetrovska",
    "krivorizkii-raion": "dnipropetrovska",
    "nikopolskii-raion": "dnipropetrovska",
    "pavlogradskii-raion": "dnipropetrovska",
    "samarivskii-raion": "dnipropetrovska",
    "sinelnikivskii-raion": "dnipropetrovska",
    # donecka-oblast
    "baxmutskii-raion": "donecka-oblast",
    "doneckii-raion": "donecka-oblast",
    "gorlivskii-raion": "donecka-oblast",
    "kalmiuskii-raion": "donecka-oblast",
    "kramatorskii-raion": "donecka-oblast",
    "mariupolskii-raion": "donecka-oblast",
    "pokrovskii-raion": "donecka-oblast",
    "volnovaskii-raion": "donecka-oblast",
    # zitomirska-oblast
    "berdicivskii-raion": "zitomirska-oblast",
    "korostenskii-raion": "zitomirska-oblast",
    "zitomirskii-raion": "zitomirska-oblast",
    "zviagelskii-raion": "zitomirska-oblast",
    # zakarpatska-oblast
    "beregivskii-raion": "zakarpatska-oblast",
    "mukacivskii-raion": "zakarpatska-oblast",
    "raxivskii-raion": "zakarpatska-oblast",
    "tiacivskii-raion": "zakarpatska-oblast",
    "uzgorodskii-raion": "zakarpatska-oblast",
    "xustskii-raion": "zakarpatska-oblast",
    # zaporizka-oblast
    "berdianskii-raion": "zaporizka-oblast",
    "melitopolskii-raion": "zaporizka-oblast",
    "pologivskii-raion": "zaporizka-oblast",
    "vasilivskii-raion": "zaporizka-oblast",
    "zaporizkii-raion": "zaporizka-oblast",
    "m-zaporizzia-ta-zaporizka-teritorialna-gromada": "zaporizka-oblast",
    # ivano-frankivska-oblast
    "ivano-frankivskii-raion": "ivano-frankivska-oblast",
    "kaluskii-raion": "ivano-frankivska-oblast",
    "kolomiiskii-raion": "ivano-frankivska-oblast",
    "kosivskii-raion": "ivano-frankivska-oblast",
    "nadvirnianskii-raion": "ivano-frankivska-oblast",
    "verxovinskii-raion": "ivano-frankivska-oblast",
    # kyivska
    "bilocerkivskii-raion": "kyivska",
    "borispilskii-raion": "kyivska",
    "brovarskii-raion": "kyivska",
    "bucanskii-raion": "kyivska",
    "fastivskii-raion": "kyivska",
    "obuxivskii-raion": "kyivska",
    "visgorodskii-raion": "kyivska",
    # kirovogradska-oblast
    "golovanivskii-raion": "kirovogradska-oblast",
    "kropivnickii-raion": "kirovogradska-oblast",
    "novoukrayinskii-raion": "kirovogradska-oblast",
    "oleksandriiskii-raion": "kirovogradska-oblast",
    # lvivska
    "drogobickii-raion": "lvivska",
    "iavorivskii-raion": "lvivska",
    "lvivskii-raion": "lvivska",
    "sambirskii-raion": "lvivska",
    "septickii-raion": "lvivska",
    "striiskii-raion": "lvivska",
    "zolocivskii-raion": "lvivska",
    # mikolayivska-oblast
    "bastanskii-raion": "mikolayivska-oblast",
    "mikolayivskii-raion": "mikolayivska-oblast",
    "pervomaiskii-raion": "mikolayivska-oblast",
    "voznesenskii-raion": "mikolayivska-oblast",
    # odeska
    "berezivskii-raion": "odeska",
    "bilgorod-dnistrovskii-raion": "odeska",
    "bolgradskii-raion": "odeska",
    "izmayilskii-raion": "odeska",
    "odeskii-raion": "odeska",
    "podilskii-raion": "odeska",
    "rozdilnianskii-raion": "odeska",
    # poltavska-oblast
    "kremencuckii-raion": "poltavska-oblast",
    "lubenskii-raion": "poltavska-oblast",
    "mirgorodskii-raion": "poltavska-oblast",
    "poltavskii-raion": "poltavska-oblast",
    # rivnenska-oblast
    "dubenskii-raion": "rivnenska-oblast",
    "rivnenskii-raion": "rivnenska-oblast",
    "sarnenskii-raion": "rivnenska-oblast",
    "varaskii-raion": "rivnenska-oblast",
    # sumska-oblast
    "konotopskii-raion": "sumska-oblast",
    "oxtirskii-raion": "sumska-oblast",
    "romenskii-raion": "sumska-oblast",
    "sostkinskii-raion": "sumska-oblast",
    "sumskii-raion": "sumska-oblast",
    # ternopilska-oblast
    "cortkivskii-raion": "ternopilska-oblast",
    "kremeneckii-raion": "ternopilska-oblast",
    "ternopilskii-raion": "ternopilska-oblast",
    # xarkivska-oblast
    "bogoduxivskii-raion": "xarkivska-oblast",
    "cuguyivskii-raion": "xarkivska-oblast",
    "iziumskii-raion": "xarkivska-oblast",
    "krasnogradskii-raion": "xarkivska-oblast",
    "kupianskii-raion": "xarkivska-oblast",
    "lozivskii-raion": "xarkivska-oblast",
    "xarkivskii-raion": "xarkivska-oblast",
    "m-xarkiv-ta-xarkivska-teritorialna-gromada": "xarkivska-oblast",
    # xersonska-oblast
    "berislavskii-raion": "xersonska-oblast",
    "geniceskii-raion": "xersonska-oblast",
    "kaxovskii-raion": "xersonska-oblast",
    "skadovskii-raion": "xersonska-oblast",
    "xersonskii-raion": "xersonska-oblast",
    # xmelnycka-oblast
    "kamianec-podilskii-raion": "xmelnycka-oblast",
    "sepetivskii-raion": "xmelnycka-oblast",
    "xmelnickii-raion": "xmelnycka-oblast",
    # cerkaska-oblast
    "cerkaskii-raion": "cerkaska-oblast",
    "umanskii-raion": "cerkaska-oblast",
    "zolotoniskii-raion": "cerkaska-oblast",
    "zvenigorodskii-raion": "cerkaska-oblast",
    # cernivecka-oblast
    "cerniveckii-raion": "cernivecka-oblast",
    "dnistrovskii-raion": "cernivecka-oblast",
    "viznickii-raion": "cernivecka-oblast",
    # cernigivska-oblast
    "cernigivskii-raion": "cernigivska-oblast",
    "koriukivskii-raion": "cernigivska-oblast",
    "nizinskii-raion": "cernigivska-oblast",
    "novgorod-siverskii-raion": "cernigivska-oblast",
    "priluckii-raion": "cernigivska-oblast",
}

def region_name(slug):
    for s, name, _u in REGIONS:
        if s == slug:
            return name
    return "Одеська область"

def ubilling_name(slug):
    for s, _n, u in REGIONS:
        if s == slug:
            return u
    return "Одеська область"

def valid_region(slug):
    for s, _n, _u in REGIONS:
        if s == slug:
            return True
    return False

def _now_ms():
    try:
        import time as _t
        return _t.ticks_ms()
    except Exception:
        pass
    try:
        import time as _t2
        return int(_t2.time() * 1000)
    except Exception:
        return 0

def _later_ms(delta):
    try:
        import time as _t
        try:
            return _t.ticks_add(_t.ticks_ms(), delta)
        except Exception:
            pass
    except Exception:
        pass
    return _now_ms() + delta

def _fresh(exp):
    try:
        import time as _t
        return _t.ticks_diff(exp, _t.ticks_ms()) > 0
    except Exception:
        pass
    return exp > _now_ms()

def _ticks():
    return _now_ms()

def _expired(t0):
    try:
        import time as _t
        return _t.ticks_diff(_t.ticks_ms(), t0) > FETCH_DEADLINE_MS
    except Exception:
        pass
    return _now_ms() - t0 > FETCH_DEADLINE_MS

_DNS_CACHE = {}

def _resolve(host, port):
    try:
        import socket
    except ImportError:
        raise RuntimeError("no socket")
    try:
        key = "%s:%s" % (host, port)
    except Exception:
        key = str(host)
    try:
        ent = _DNS_CACHE.get(key)
        if ent is not None and _fresh(ent[1]):
            return ent[0]
    except Exception:
        pass
    try:
        ai = socket.getaddrinfo(host, port)[0][-1]
    except Exception as e:
        raise RuntimeError("dns " + host + ": " + str(e)[:60])
    try:
        _DNS_CACHE[key] = (ai, _later_ms(DNS_TTL_MS))
    except Exception:
        pass
    return ai

def _dns_invalidate(host, port=None):
    try:
        if port is None:
            for k in [k for k in _DNS_CACHE.keys()]:
                try:
                    if k == host or k.startswith(str(host) + ":"):
                        _DNS_CACHE.pop(k, None)
                except Exception:
                    pass
        else:
            _DNS_CACHE.pop("%s:%s" % (host, port), None)
    except Exception:
        pass

def _split_http(url):
    """'http://host[:port]/path' -> (host, port, path). Только plain HTTP."""
    s = (url or "").strip()
    if "://" in s:
        scheme, s = s.split("://", 1)
        if scheme.lower() != "http":
            raise RuntimeError("only plain http (no TLS on ESP)")
    else:
        raise RuntimeError("bad url")
    if "/" in s:
        host, path = s.split("/", 1)
        path = "/" + path
    else:
        host, path = s, "/"
    port = 80
    if ":" in host:
        host, p = host.rsplit(":", 1)
        try:
            port = int(p)
        except Exception:
            raise RuntimeError("bad port")
    if not host:
        raise RuntimeError("bad host")
    return host, port, path

def http_get(url, on_post=None):
    """GET по plain HTTP, тело целиком (лимит BODY_LIMIT). Возвращает bytes."""
    try:
        import gc
        gc.collect()
    except Exception:
        pass
    try:
        import socket
    except ImportError:
        raise RuntimeError("no socket")
    host, port, path = _split_http(url)
    try:
        hp = host if int(port) == 80 else "%s:%s" % (host, port)
    except Exception:
        hp = host
    ai = _resolve(host, port)
    s = socket.socket()
    try:
        try:
            s.settimeout(SOCK_TIMEOUT)
        except Exception:
            pass
        try:
            s.connect(ai)
        except Exception as e:
            _dns_invalidate(host, port)  # IP мог протухнуть — резолвим заново
            raise RuntimeError("api " + hp + " connect: " + str(e)[:60])
        s.send(("GET " + path + " HTTP/1.0\r\n"
                "Host: " + host + "\r\n"
                "User-Agent: ESP-Alert/2.0\r\n"
                "Connection: close\r\n\r\n").encode())
        raw = b""
        t0 = _ticks()
        while b"\r\n\r\n" not in raw:
            if _expired(t0):
                raise RuntimeError("api " + hp + " deadline(headers)")
            ch = s.recv(CHUNK)
            if not ch:
                break
            raw += ch
            if len(raw) > 8192:
                break
        hb = raw.find(b"\r\n\r\n")
        if hb < 0:
            raise RuntimeError("api " + hp + " bad head")
        try:
            status = raw[:hb].split(b"\r\n", 1)[0].decode("latin1", "ignore")
        except Exception:
            status = ""
        if " 200" not in status:
            raise RuntimeError("api " + hp + " http " + status[:60])
        body = raw[hb + 4:]
        while True:
            if _expired(t0):
                raise RuntimeError("api " + hp + " deadline(body)")
            try:
                ch = s.recv(CHUNK)
            except Exception as e:
                raise RuntimeError("api " + hp + " recv: " + str(e)[:60])
            if not ch:
                break
            body += ch
            if len(body) > BODY_LIMIT:
                raise RuntimeError("api " + hp + " body too big")
        return body
    finally:
        try:
            s.close()
        except Exception:
            pass
        try:
            import gc
            gc.collect()
        except Exception:
            pass

def _json(body):
    try:
        import ujson as json
    except ImportError:
        import json
    try:
        if isinstance(body, bytes):
            body = body.decode("utf-8", "ignore")
    except Exception:
        body = str(body)
    return json.loads(body)

def fetch_ubilling():
    """Весь dict {имя_области: bool} одним запросом."""
    data = _json(http_get(UBILL_URL))
    try:
        states = data["states"]
    except Exception:
        raise RuntimeError("ubilling bad format")
    out = {}
    try:
        for name, st in states.items():
            try:
                out[name] = bool(st.get("alertnow", False))
            except Exception:
                pass
    except Exception:
        raise RuntimeError("ubilling bad states")
    return out

def fetch_tryvoha(slug):
    """bool для slug области/города."""
    data = _json(http_get(TRYVOHA_URL + slug))
    try:
        if bool(data.get("active")):
            return True
        if bool(data.get("active_anywhere")):
            return True
        da = data.get("districts_active")
        if da:
            return True
        return False
    except Exception:
        raise RuntimeError("tryvoha bad format")

def check(slug):
    """(alert_bool, source). Области: ubilling -> tryvoha.
    Районы/громады: tryvoha -> fallback на тревогу области ("ubilling~oblast").
    Не пишет во flash."""
    if not valid_region(slug):
        slug = DEFAULT_REGION
    last_e = RuntimeError("no source")
    name = ubilling_name(slug)
    if name is not None:
        try:
            states = fetch_ubilling()
            if name in states:
                return bool(states[name]), "ubilling"
            last_e = RuntimeError("ubilling no region " + slug)
        except Exception as e:
            last_e = e
    try:
        return bool(fetch_tryvoha(slug)), "tryvoha"
    except Exception as e:
        last_e = e
    if name is None:
        # своей строки в ubilling нет: аппроксимация областью
        try:
            ps = PARENT.get(slug)
            pname = ubilling_name(ps) if ps else None
            if pname is not None:
                states = fetch_ubilling()
                if pname in states:
                    return bool(states[pname]), "ubilling~oblast"
                last_e = RuntimeError("ubilling no parent " + slug)
            else:
                last_e = RuntimeError("no parent " + slug)
        except Exception as e:
            last_e = e
    try:
        import gc as _ggc
        _ggc.collect()
    except Exception:
        pass
    raise last_e
