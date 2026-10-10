@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python не найден. Установите Python 3.12 с python.org
  echo и при установке отметьте галочку "Add python.exe to PATH".
  pause
  exit /b 1
)
echo Устанавливаю нужные компоненты, это займёт пару минут...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Не удалось установить компоненты. Проверьте интернет и запустите ещё раз.
  pause
  exit /b 1
)
echo.
echo Готово. Теперь запустите setup.bat
pause
