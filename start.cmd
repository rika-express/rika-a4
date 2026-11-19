@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)" >nul 2>&1
if errorlevel 1 (
  echo Нужен установленный Python 3.13 или новее. Проверьте python --version в новом PowerShell.
  goto failed
)
if not exist node_modules\vue\dist\vue.global.prod.js (
  echo Устанавливаем Vue внутри проекта...
  call npm.cmd ci --omit=dev --no-audit --no-fund
  if errorlevel 1 goto failed
)
if not defined RIKA_PORT set "RIKA_PORT=8000"
echo Адрес приложения: http://127.0.0.1:%RIKA_PORT%
echo Окно оставьте открытым. Остановка: Ctrl+C.
python backend\server.py
if errorlevel 1 goto failed
exit /b
:failed
echo Запуск не выполнен. Причина указана выше; инструкция в README.md.
pause
