@echo off
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements-voice.txt
if errorlevel 1 goto failed
echo Setup complete. Run test_voice.bat while stationary.
pause
exit /b 0
:failed
echo Setup failed. Check the errors above. Run from an activated Python 3.11 environment, or use the Conda commands in README.md.
pause
exit /b 1
