# release.py — снапшот релиза + публикация в GitHub Releases.
# Использование: release.py X.Y.Z  (или release.bat X.Y.Z).
#
# Шаги: сверка версии с src/version.py -> чистое рабочее дерево ->
# отсутствующий тег vX.Y.Z -> pack.py (свежий firmware.tar.gz) ->
# releases/X.Y.Z/{air-alert-X.Y.Z-src.zip, MANIFEST.txt} ->
# git tag + push -> gh release create (ассеты: zip, MANIFEST.txt,
# firmware.tar.gz).
#
# Каталог releases/ в git не коммитится (.gitignore): снапшот живёт
# локально, публикуется ассетами GitHub Release.
import hashlib
import os
import re
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
# В zip-снапшот идут все tracked-файлы, кроме этих двух
# (внутри zip ровно N записей без корневой папки).
EXCLUDE = {'.gitignore', 'AGENTS.md'}


def die(msg, hint=None):
    sys.exit('FAIL: %s%s' % (msg, ('\n' + hint) if hint else ''))


def git(*args, capture=True):
    r = subprocess.run(['git'] + list(args), cwd=ROOT, text=True,
                       capture_output=capture)
    if r.returncode != 0:
        die('git %s: %s' % (' '.join(args),
                            (r.stderr or '').strip() or 'exit %d' % r.returncode))
    return (r.stdout or '').strip()


def run(args):
    print('== %s' % ' '.join(map(str, args)))
    r = subprocess.run(list(args), cwd=ROOT)
    if r.returncode != 0:
        die('%s -> exit %d' % (' '.join(map(str, args)), r.returncode))


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r'\d+\.\d+\.\d+', sys.argv[1]):
        die('usage: release.py X.Y.Z')
    ver = sys.argv[1]
    tag = 'v' + ver

    # 1. версия: аргумент == FW_VERSION (защита от опечатки)
    with open(os.path.join(ROOT, 'src', 'version.py'), encoding='utf-8') as f:
        m = re.search(r'FW_VERSION\s*=\s*"([^"]+)"', f.read())
    fw = m.group(1) if m else None
    if fw != ver:
        die('FW_VERSION=%s, а запрошен %s — поправьте src/version.py' % (fw, ver))

    # 2. чистое дерево (тег ставим на HEAD, в релиз уходят только коммиты)
    st = git('status', '--porcelain')
    if st:
        die('рабочее дерево не чистое, сначала закоммитьте:\n' + st)

    # 3. тега ещё нет
    if subprocess.run(['git', 'rev-parse', '-q', '--verify',
                       'refs/tags/' + tag], cwd=ROOT).returncode == 0:
        die('тег %s уже существует' % tag,
            'нужен новый коммит/версию, либо удалите тег: git tag -d %s' % tag)

    # 4. свежий OTA-бандл (mpy-cross, gzip wbits=9)
    run([sys.executable, os.path.join(ROOT, 'pack.py')])
    firmware = os.path.join(ROOT, 'firmware.tar.gz')

    # pack.py пересобирает .mpy: если они изменились — zip разойдётся
    # с тегом, сначала закоммитьте пересборку
    st = git('status', '--porcelain')
    if st:
        die('pack.py изменил файлы — закоммитьте пересборку и повторите:\n' + st)

    # 5. снапшот: zip + MANIFEST.txt
    out_dir = os.path.join(ROOT, 'releases', ver)
    os.makedirs(out_dir, exist_ok=True)
    files = [f for f in git('ls-files').splitlines() if f not in EXCLUDE]
    zip_name = 'air-alert-%s-src.zip' % ver
    zip_path = os.path.join(out_dir, zip_name)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for fn in files:
            z.write(os.path.join(ROOT, fn), fn)

    sha_zip = sha256(zip_path)
    sha_fw = sha256(firmware)
    head = git('rev-parse', '--short', 'HEAD')
    manifest = os.path.join(out_dir, 'MANIFEST.txt')
    with open(manifest, 'w', encoding='utf-8', newline='\n') as f:
        f.write('air-alert-ukraine %s — снапшот, git %s\n' % (ver, head))
        f.write('%s  %d  %s\n' % (sha_zip, os.path.getsize(zip_path), zip_name))
        f.write('%s  %d  firmware.tar.gz\n' % (sha_fw, os.path.getsize(firmware)))
        f.write('содержимое %s (%d записей):\n' % (zip_name, len(files)))
        for fn in files:
            p = os.path.join(ROOT, fn)
            f.write('%s  %d  %s\n' % (sha256(p), os.path.getsize(p), fn))
    print('OK: %s (%d записей), MANIFEST.txt' % (zip_path, len(files)))

    # 6. ветка + тег + push (ветку тоже — на GitHub должна быть актуальной;
    # тег указывает на HEAD, релиз создаётся на нём)
    r = subprocess.run(['git', 'symbolic-ref', '--short', 'HEAD'], cwd=ROOT,
                       text=True, capture_output=True)
    if r.returncode == 0 and r.stdout.strip():
        run(['git', 'push', 'origin', r.stdout.strip()])
    run(['git', 'tag', '-a', tag, '-m', 'release %s' % ver])
    # явный refspec: "push origin v0.4.0" неоднозначен (ветка + тег с
    # одинаковым именем -> "matches more than one")
    run(['git', 'push', 'origin', 'refs/tags/' + tag])

    # 7. публикация
    run(['gh', 'release', 'create', tag, zip_path, manifest, firmware,
         '--verify-tag', '--generate-notes'])
    print('OK: релиз %s опубликован' % tag)


if __name__ == '__main__':
    main()
