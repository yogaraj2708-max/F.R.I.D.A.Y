@echo off
title F.R.I.D.A.Y. 2.0 - Tactical Personal Assistant
cd /d "%~dp0"

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else if exist ".venv\bin\python.exe" (
    set "PYTHON_EXE=.venv\bin\python.exe"
)

"%PYTHON_EXE%" run_friday_gui.py
if errorlevel 1 (
    echo.
    echo [Notice]: F.R.I.D.A.Y. failed to start.
    echo If dependencies are missing, please run setup.bat first.
    pause
)
