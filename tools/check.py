# check.py — повторяемые проверки для air-alert-ukraine (без тест-фреймворка).
# Запуск: python tools/check.py  (из корня репо, нужен любой Python 3.8+)
#
# Что проверяет:
#   1. py_compile всех src/*.py
#   2. Рендер-контракт: шаблон рендерится без остаточных {{...}},
#      значения blink попадают в input#blink_on_ms / #blink_off_ms,
#      каждый name="blink_*" имеет пару form.get("blink_*") в web.py
#   3. Таблица blink_ms: границы, мусор, float, отрицательные
#   4. _sanitize: зажим и дефолты
#   5. Версия: FW_VERSION встречается в README.md минимум 2 раза
#
# На железе не гоняется (устройство может быть недоступно) — только PC.
import os
import re
import sys
import types
import py_compile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

failures = []


def check(name, cond, detail=""):
    status = "OK " if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


# --- 1. py_compile всех src/*.py ---
py_files = [f for f in os.listdir(SRC) if f.endswith(".py")]
for f in sorted(py_files):
    try:
        py_compile.compile(os.path.join(SRC, f), doraise=True)
        check(f"py_compile {f}", True)
    except py_compile.PyCompileError as e:
        check(f"py_compile {f}", False, str(e))

# --- стаб machine для импорта web.py на ПК ---
if "machine" not in sys.modules:
    m = types.ModuleType("machine")
    m.reset = lambda: None
    m.reset_cause = lambda: 0
    m.Pin = lambda *a, **k: None
    sys.modules["machine"] = m

import config_store  # noqa: E402
import web  # noqa: E402

# --- 2. Рендер-контракт ---
cfg = dict(config_store.DEFAULTS)
cfg["region"] = "m-odesa-ta-odeska-teritorialna-gromada"
cfg["blink_on_ms"] = 100
cfg["blink_off_ms"] = 200
cfg["wifi_ssid"] = "test"
state = {
    "ip": "192.168.1.38", "alert": False, "source": "aiu",
    "last_check": "ok", "ap": None, "worker_gen": 1, "last_err": "",
}

tokens = web.render_tokens(cfg, state)
with open(os.path.join(SRC, "template.html"), encoding="utf-8") as f:
    tpl = f.read()

# нет остаточных токенов после подстановки
rendered = tpl
for k, v in tokens.items():
    rendered = rendered.replace(k, str(v))
rendered = rendered.replace("{{REGION_OPTIONS}}", "")
leftover = re.findall(r"\{\{[A-Z_]+\}\}", rendered)
check("рендер: нет остаточных {{...}}", len(leftover) == 0, str(leftover))

# значения blink в input#blink_*
m_on = re.search(r'<input[^>]*id="blink_on_ms"[^>]*value="([^"]*)"', tpl.replace("{{BLINK_ON}}", str(tokens["{{BLINK_ON}}"])))
m_off = re.search(r'<input[^>]*id="blink_off_ms"[^>]*value="([^"]*)"', tpl.replace("{{BLINK_OFF}}", str(tokens["{{BLINK_OFF}}"])))
check("рендер: value=100 в input#blink_on_ms", m_on is not None and m_on.group(1) == "100")
check("рендер: value=200 в input#blink_off_ms", m_off is not None and m_off.group(1) == "200")

# каждый name="blink_*" имеет пару form.get("blink_*") в web.py
with open(os.path.join(SRC, "web.py"), encoding="utf-8") as f:
    web_src = f.read()
for m in re.finditer(r'name="(blink_[a-z_]+)"', tpl):
    field = m.group(1)
    check(f'name="{field}" ↔ form.get в web.py', f'form.get("{field}"' in web_src or f"form.get('{field}'" in web_src)

# --- 3. Таблица blink_ms ---
# BLINK_MIN_MS теперь 150
MINV = config_store.BLINK_MIN_MS
MAXV = config_store.BLINK_MAX_MS
cases = [
    ("10", MINV), ("50", MINV), ("-5", MINV),          # ниже минимума → минимум
    ("99999", MAXV), ("5001", MAXV),                     # выше максимума → максимум
    ("abc", 500), (None, 500), ("", 500), ("100.5", 500),  # мусор → old
    ("300", 300), ("150", 150),                          # валидные
    (1000.0, 1000),                                      # float → int
    ("  250  ", 250),                                    # пробелы
]
for raw, expected in cases:
    got = config_store.blink_ms(raw, 500)
    check(f"blink_ms({raw!r}, 500) == {expected}", got == expected, f"got {got}")

# --- 4. _sanitize ---
s1 = config_store._sanitize({"blink_on_ms": 99999, "blink_off_ms": -10})
check("_sanitize: 99999 → 5000", s1["blink_on_ms"] == MAXV)
check("_sanitize: -10 → min", s1["blink_off_ms"] == MINV)
s2 = config_store._sanitize({})
check("_sanitize({}): blink_on_ms → 500", s2["blink_on_ms"] == 500)
check("_sanitize({}): blink_off_ms → 500", s2["blink_off_ms"] == 500)

# --- 5. Версия в README ≥2 раз ---
with open(os.path.join(ROOT, "src", "version.py"), encoding="utf-8") as f:
    ver = re.search(r'FW_VERSION\s*=\s*"([^"]+)"', f.read()).group(1)
with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
    readme = f.read()
count = readme.count(ver)
check(f"FW_VERSION {ver} в README ≥2 раз", count >= 2, f"найдено {count}")

# --- итог ---
print()
if failures:
    print(f"FAILED: {len(failures)} проверок не прошло:")
    for f_ in failures:
        print(f"  - {f_}")
    sys.exit(1)
print(f"OK: все проверки прошли (версия {ver})")
