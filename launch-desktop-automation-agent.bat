@echo off
setlocal

cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python main.py
) else (
    py -3 main.py
)

if errorlevel 1 (
    echo.
    echo The app exited with an error.
    pause
)
