@echo off
chcp 65001 >nul
cd /d "%~dp0"
python plate_agent.py setup
pause
