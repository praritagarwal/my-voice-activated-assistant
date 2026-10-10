@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
 .venv\Scripts\python.exe assistant.py --voice
) else (
 python assistant.py --voice
)
pause
