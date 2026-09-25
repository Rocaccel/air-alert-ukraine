@echo off
REM build-mpy.bat — предкомпиляция src\*.py в .mpy через mpy-cross.
REM Зачем: .mpy грузятся без компиляции на ESP -> меньше фрагментации кучи
REM перед TLS-handshake + меньше резидентного байткода.
REM
REM 1. Скачайте mpy-cross под вашу версию MicroPython с https://micropython.org/download/
REM    (для прошивки 1.28.x нужен mpy-cross 1.28.x; _mpy нашей сборки = 11014,
REM    проверяется строкой version.build в REPL).
REM 2. Положите mpy-cross.exe рядом с этим bat или в PATH.
REM 3. Запустите: получите папку mpy\*.mpy — залейте ЕЕ содержимое в ESP
REM    вместо .py (config.json/template.html — как есть).
setlocal
cd /d "%~dp0"
if not exist mpy mkdir mpy
where mpy-cross >nul 2>nul
if %errorlevel% neq 0 (
  echo mpy-cross not found. Download matching your firmware from https://micropython.org/download/
  echo Need mpy-cross for MicroPython 1.28.x (_mpy=11014).
  exit /b 1
)
for %%f in (src\*.py) do (
  echo compiling %%f
  mpy-cross -o "mpy\%%~nf.mpy" "%%f"
  if errorlevel 1 echo FAILED %%f && exit /b 1
)
echo OK: mpy\ ready. Upload *.mpy + template.html to ESP instead of *.py
dir mpy
endlocal
