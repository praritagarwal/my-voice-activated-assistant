@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
 .venv\Scripts\python.exe test_voice.py
) else (
 python test_voice.py
)
pause
