@echo off
setlocal

:: 1. Check for Administrator privileges
NET SESSION >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Requesting Administrator privileges...
    :: Re-launch self with Admin rights
    powershell -Command "Start-Process cmd -ArgumentList '/k \"%~dpnx0\"' -Verb RunAs"
    exit /b
)

:: 2. Set Working Directory to Script Location (Portable)
cd /d "%~dp0"
echo Current Directory: %CD%


:: 3. Run Application
echo.
echo Starting USB Security Framework...
python app.py

:: 4. Keep window open if app crashes (optional, good for debug)
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with error code %ERRORLEVEL%.
    pause
)
exit /b
