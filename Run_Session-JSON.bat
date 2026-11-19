@echo off
setlocal
cd /d "%~dp0"



python metadata_gui.py master.json

if errorlevel 1 (
    echo.
    echo Processing ended with an error.
    pause
) else (
    echo.
    echo Processing finished.
    pause
)

endlocal