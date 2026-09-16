@echo off
title F.R.I.D.A.Y. 2.0 - Tactical Personal Assistant
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_friday_gui.py
) else (
    python run_friday_gui.py
)
pause
