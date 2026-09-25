@echo off
REM upload.bat - основной путь заливки: указанные файлы из src по USB + reset.
REM Использование: upload.bat main.py web.py
REM Порт по умолчанию COM3, переопределить: set ESPPORT=COM5
REM Перед запуском отпустить порт в Thonny - Stop или закрыть.
REM Запасной путь - OTA-бандл: pack.bat + POST /ota-bundle.
setlocal
cd /d "%~dp0"
if "%ESPPORT%"=="" set ESPPORT=COM3
set MPYEXE=D:\1-PORTABLE\Python_PORTABLE\python\python.exe
if "%~1"=="" (
  echo usage: upload.bat file1 file2 ... - файлы берутся из src
  exit /b 1
)
"%MPYEXE%" -m mpremote connect %ESPPORT% exec "import sys; print('link ok')"
if errorlevel 1 (
  echo НЕ МОГУ ОТКРЫТЬ %ESPPORT% - возможно порт держит Thonny
  exit /b 1
)
:loop
if "%~1"=="" goto done
if not exist "src\%~1" (
  echo НЕТ ФАЙЛА: src\%~1
  exit /b 1
)
echo --- %~1
"%MPYEXE%" -m mpremote connect %ESPPORT% cp "src\%~1" ":%~1"
if errorlevel 1 (
  echo ОШИБКА ЗАЛИВКИ: %~1
  exit /b 1
)
shift
goto loop
:done
echo --- reset
"%MPYEXE%" -m mpremote connect %ESPPORT% reset
if errorlevel 1 (
  echo ОШИБКА RESET
  exit /b 1
)
echo ГОТОВО: файлы залиты, ESP перезагружается. Проверка: /status fw
endlocal
