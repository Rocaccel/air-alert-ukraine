# pack.py — OTA-бандл firmware.tar.gz для ESP.
# Формат: tar + gzip с окном 512Б (wbits=9).
# Зачем: DeflateIO на ESP выделяет окно целиком при создании. Окно 32КБ
# (wbits=15, обычный tar/gzip) -> "memory allocation failed, allocating 32768"
# на фрагментированной куче. Окно 512Б распаковывается всегда.
# Распаковщик: ota.unpack_tar_gz (deflate, GZIP, wbits 9), прошивка 2.1.7+.
# Банды, собранные обычным tar -czf / python w:gz (wbits=15), 2.1.7+ НЕ примет.
import binascii
import io
import os
import struct
import sys
import tarfile
import zlib

FILES = ['boot.py', 'main.py', 'config_store.py', 'alerts.py', 'web.py',
         'ota.py', 'version.py', 'hw.py', 'logbuf.py', 'template.html',
         'utarfile.py']
OUT = sys.argv[1] if len(sys.argv) > 1 else 'firmware.tar.gz'

base = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
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
