@echo off
title F.R.I.D.A.Y. 2.0 - Tactical Personal Assistant
cd /d "%~dp0"
if exist "dist\FRIDAY_2.0\FRIDAY_2.0.exe" (
    start "" "dist\FRIDAY_2.0\FRIDAY_2.0.exe"
) else if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" run_friday_gui.py
) else (
    echo [Notice]: Compiled binary not found in dist. Launching Python runner...
    python run_friday_gui.py
)
