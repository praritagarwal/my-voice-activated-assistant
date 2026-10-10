@echo off
setlocal
cd /d "%~dp0"
python -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
python build_windows.py
if errorlevel 1 goto failed
echo Build finished. See dist\Sitara and dist\Sitara-Windows.zip.
pause
exit /b 0
:failed
echo Build failed. Use your working activated Python 3.11 Conda environment and check the error above.
pause
exit /b 1
