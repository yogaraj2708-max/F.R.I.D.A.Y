@echo off
title F.R.I.D.A.Y. 2.0 - Tactical Personal Assistant
cd /d "%~dp0"

if exist "dist\FRIDAY_2.0\FRIDAY_2.0.exe" (
    start "" "dist\FRIDAY_2.0\FRIDAY_2.0.exe"
    exit /b 0
)

:: Prefer windowless Python (pythonw) so no black CMD window is left open
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" run_friday_gui.py
    exit /b 0
)

where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw run_friday_gui.py
    exit /b 0
)

:: Fallback to standard runner
call run_friday_gui.bat
