# pack.py — OTA-бандл firmware.tar.gz для ESP.
# Формат: tar + gzip с окном 512Б (wbits=9).
# Зачем: DeflateIO на ESP выделяет окно целиком при создании. Окно 32КБ
# (wbits=15, обычный tar/gzip) -> "memory allocation failed, allocating 32768"
# на фрагментированной куче. Окно 512Б распаковывается всегда.
# Распаковщик: ota.unpack_tar_gz (deflate, GZIP, wbits 9).
# Бандлы, собранные обычным tar -czf / python gzip (wbits=15), не примутся.
import binascii
import io
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import zlib

# web.py/alerts.py в бандл НЕ входят: на устройстве едут только их .mpy.
# У .py приоритет над .mpy — их наличие на плате включает on-device
# компиляцию после WiFi-инициализации: пик аллокаций рвёт кучу ->
# lwIP без mbuf -> плата не отвечает на ping (эмпирически 0.4.0).
# Исходники .py остаются в src/ и в zip релиза.
FILES = ['boot.py', 'main.py', 'config_store.py',
         'ota.py', 'version.py', 'hw.py', 'logbuf.py', 'template.html',
         'utarfile.py']
# Предкомпиляция: .mpy грузится без on-device компиляции (и грузится
# только если одноимённого .py на плате нет).
MPY_SRC = ['web.py', 'alerts.py']
OUT = sys.argv[1] if len(sys.argv) > 1 else 'firmware.tar.gz'

base = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')


def find_mpy_cross():
    exe = shutil.which('mpy-cross')
    if exe:
        return exe
    for cand in (os.path.join(os.path.dirname(sys.executable), 'Scripts',
                              'mpy-cross.exe'),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'mpy-cross.exe')):
        if os.path.exists(cand):
            return cand
    raise SystemExit('mpy-cross not found (pip install mpy-cross==1.28.0.post2 '
                     'or place mpy-cross.exe next to pack.py)')


mcpy = find_mpy_cross()
for fn in MPY_SRC:
    src_p = os.path.join(base, fn)
    out_p = os.path.join(base, fn[:-3] + '.mpy')
    subprocess.run([mcpy, src_p, '-o', out_p], check=True)
    FILES.append(fn[:-3] + '.mpy')

buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode='w') as t:
    for fn in FILES:
        p = os.path.join(base, fn)
        ti = t.gettarinfo(p, arcname=fn)
        with open(p, 'rb') as f:
            t.addfile(ti, f)
tar_data = buf.getvalue()

co = zlib.compressobj(9, zlib.DEFLATED, -9, 8, 0)  # минус = сырой deflate без обертки
raw = co.compress(tar_data) + co.flush()
gz = (b'\x1f\x8b\x08\x00' + struct.pack('<L', 0) + b'\x00\xff' + raw
      + struct.pack('<L', binascii.crc32(tar_data) & 0xffffffff)
      + struct.pack('<L', len(tar_data) & 0xffffffff))
with open(OUT, 'wb') as f:
    f.write(gz)
print('OK: %s tar=%d gz=%d files=%d' % (OUT, len(tar_data), len(gz), len(FILES)))
