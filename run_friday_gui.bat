@echo off
title F.R.I.D.A.Y. 2.0 - Tactical Personal Assistant
cd /d "%~dp0"

:: Prefer windowless Python (pythonw.exe) so no black CMD window is left open
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" run_friday_gui.py
    exit /b 0
)

if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" run_friday_gui.py
    exit /b 0
)

where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw run_friday_gui.py
    exit /b 0
)

python run_friday_gui.py
