@echo off
REM pack.bat - sobrat firmware.tar.gz cherez pack.py
REM format gzip wbits=9 dlya ESP. Obychny tar -czf daet wbits=15 i OOM 32768
setlocal
cd /d "%~dp0"
if exist "firmware.tar.gz" del "firmware.tar.gz"
"D:\1-PORTABLE\Python_PORTABLE\python\python.exe" pack.py
endlocal
