"""OTA: запись файлов, распаковка .tar.gz, скачивание по URL, откат. Без boot-записей."""
import gc

ALLOWED = (
    "main.py", "web.py", "alerts.py", "ota.py",
    "config_store.py", "boot.py", "version.py",
    "hw.py", "logbuf.py", "template.html", "utarfile.py",
)
# config.json и last-файлы специально НЕ обновляются пакетом
MAX_BUNDLE = 300 * 1024
MAX_SINGLE = 100 * 1024
BAK_DIR = "bak"

def _mkdir(d):
    try:
        import os
        try:
            os.mkdir(d)
        except Exception:
            pass
    except Exception:
        pass

def safe_name(name):
    if not name:
        return ""
    name = name.replace("\\", "/").split("/")[-1].strip()
    if name in (".", "..", ""):
        return ""
    if ".." in name or "/" in name:
        return ""
    return name

def is_allowed(name):
    return safe_name(name) in ALLOWED

def backup(name):
    _mkdir(BAK_DIR)
    src = safe_name(name)
    if not src:
        return False
    try:
        with open(src, "rb") as f:
            data = f.read()
        with open(BAK_DIR + "/" + src, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False

def write_file(name, data):
    name = safe_name(name)
    with open(name, "wb") as f:
        f.write(data)

def free_bytes():
    try:
        import os
        s = os.statvfs("/")
        return s[0] * s[3]
    except Exception:
        return 10 * 1024 * 1024

def unpack_tar_gz(tmp_path):
    """Распаковывает firmware.tar.gz в корень. Возвращает список записанных файлов."""
    gc.collect()
    # utarfile.py вендорен в прошивке (micropython-lib, MIT) — отдельного
    # `mip install` на устройстве не требуется
    try:
        import utarfile as tarfile
    except ImportError:
        try:
            import tarfile
        except ImportError:
            raise RuntimeError("need utarfile.py in firmware (re-upload bundle)")
    try:
        import uzlib as zlibmod
        zmode = "uzlib"
    except ImportError:
        try:
            import zlib as zlibmod
            zmode = "zlib"
        except ImportError:
            try:
                # MicroPython >=1.21 (напр. ESP32_GENERIC 1.28): uzlib нет,
                # есть deflate.DeflateIO с read/readinto
                import deflate as zlibmod
                zmode = "deflate"
            except ImportError:
                raise RuntimeError("need uzlib/zlib/deflate")
    written = []
    f = open(tmp_path, "rb")
    try:
        if zmode == "uzlib":
            # 31 = gzip
            try:
                stream = zlibmod.DecompIO(f, 31)
            except TypeError:
                stream = zlibmod.DecompIO(f)
        elif zmode == "deflate":
            # окно 512Б (wbits=9): бандл собирается pack.py. Окно 32КБ
            # (wbits=15, обычный gzip) не выделяется на фрагментированной
            # куче (было OOM на 32768 байт), такие бандлы больше не шлем.
            try:
                stream = zlibmod.DeflateIO(f, zlibmod.GZIP, 9)
            except Exception:
                stream = zlibmod.DeflateIO(f, zlibmod.AUTO, 9)
        else:
            import io as _io
            data = f.read()
            try:
                raw = zlibmod.decompress(data, 31)
            except Exception:
                raw = zlibmod.decompress(data)
            stream = _io.BytesIO(raw)
        tf = tarfile.TarFile(fileobj=stream)
        for info in tf:
            name = safe_name(getattr(info, "name", ""))
            if not name or not is_allowed(name):
                # пропускаем config.json, папки, мусор
                try:
                    ex = tf.extractfile(info)
                    if ex:
                        try:
                            ex.close()
                        except Exception:
                            pass
                except Exception:
                    pass
                continue
            fh = tf.extractfile(info)
            if not fh:
                continue
            backup(name)
            with open(name, "wb") as out:
                while True:
                    ch = fh.read(1024)
                    if not ch:
                        break
                    out.write(ch)
                    gc.collect()
            try:
                fh.close()
            except Exception:
                pass
            written.append(name)
            gc.collect()
        try:
            tf.close()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass
    finally:
        try:
            f.close()
        except Exception:
            pass
    if "main.py" not in written:
        raise RuntimeError("bundle has no main.py: " + ",".join(written))
    return written

def download_url(url, target_path, limit):
    try:
        import urequests as requests
    except ImportError:
        import requests
    r = requests.get(url, timeout=20)
    try:
        # пробуем потоково
        total = 0
        with open(target_path, "wb") as f:
            try:
                raw = getattr(r, "raw", None)
            except Exception:
                raw = None
            if raw is not None:
                try:
                    while True:
                        ch = raw.read(1024)
                        if not ch:
                            break
                        total += len(ch)
                        if total > limit:
                            raise RuntimeError("file too big")
                        f.write(ch)
                except RuntimeError:
                    raise
                except Exception:
                    # fallback на content
                    data = getattr(r, "content", b"")
                    if len(data) > limit:
                        raise RuntimeError("file too big")
                    f.write(data)
                    total = len(data)
            else:
                data = getattr(r, "content", None)
                if data is None:
                    try:
                        data = r.text.encode()
                    except Exception:
                        data = b""
                if len(data) > limit:
                    raise RuntimeError("file too big")
                f.write(data)
                total = len(data)
        return total
    finally:
        try:
            r.close()
        except Exception:
            pass

def rollback():
    import os
    restored = []
    try:
        files = os.listdir(BAK_DIR)
    except Exception:
        return restored
    for name in files:
        if not is_allowed(name):
            continue
        try:
            with open(BAK_DIR + "/" + name, "rb") as f:
                data = f.read()
            with open(name, "wb") as f:
                f.write(data)
            restored.append(name)
        except Exception:
            pass
    return restored
