@echo off
chcp 65001 >nul
cd /d "%~dp0"
title OilBook - камера табло
:loop
python plate_agent.py
echo Программа остановилась. Перезапуск через 10 секунд (закройте окно, чтобы выйти)...
timeout /t 10 >nul
goto loop
