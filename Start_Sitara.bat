@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0Sitara.exe" goto packaged
if not exist "%~dp0launcher_python.txt" goto unregistered
set /p SITARA_PYTHON=<"%~dp0launcher_python.txt"
if not exist "%SITARA_PYTHON%" goto unregistered
for %%I in ("%SITARA_PYTHON%") do set "SITARA_ENV=%%~dpI"
set "PATH=%SITARA_ENV%;%SITARA_ENV%Library\bin;%SITARA_ENV%Scripts;%PATH%"
"%SITARA_PYTHON%" "%~dp0launch_assistant.py" %*
goto finished
:packaged
"%~dp0Sitara.exe" %*
goto finished
:unregistered
echo Run python register_launcher.py once from your activated treadmill-assistant Conda environment.
pause
exit /b 1
:finished
if errorlevel 1 pause
