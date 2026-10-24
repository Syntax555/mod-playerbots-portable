@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Zygor.ps1" %*
if errorlevel 1 (
    echo.
    echo Zygor Guides Viewer was not installed. Read the error above before trying again.
    pause
    exit /b 1
)
pause
