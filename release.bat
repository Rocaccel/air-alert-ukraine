@echo off
REM release.bat - snarshot + GitHub Release cherez release.py
REM Ispolzovanie: release.bat X.Y.Z
setlocal
cd /d "%~dp0"
"D:\1-PORTABLE\Python_PORTABLE\python\python.exe" release.py %*
endlocal
