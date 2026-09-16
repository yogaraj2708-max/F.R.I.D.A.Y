@echo off
title F.R.I.D.A.Y. 2.0 - Tactical Personal Assistant
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo =======================================================
    echo   F.R.I.D.A.Y. 2.0 - First-Time Auto-Setup Detected
    echo =======================================================
    echo Virtual environment (.venv) was not found.
    echo Creating virtual environment and installing all dependencies...
    echo (This is a one-time automated setup. Please wait 1-2 minutes.)
    echo.
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo [ERROR]: Python was not found in your system PATH.
        echo Please install Python 3.10, 3.11, or 3.12 from https://www.python.org/
        echo Make sure to check the box: [x] "Add Python to PATH".
        pause
        exit /b 1
    )
    echo [1/2] Upgrading pip package installer...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    echo.
    echo [2/2] Installing required dependencies (PySide6, Whisper, Kokoro, etc.)...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERROR]: Failed to install some dependencies.
        echo Please verify your internet connection and try running this again.
        pause
        exit /b 1
    )
    echo.
    echo =======================================================
    echo   Setup complete! Launching F.R.I.D.A.Y. 2.0 HUD...
    echo =======================================================
    echo.
)

".venv\Scripts\python.exe" run_friday_gui.py
if errorlevel 1 (
    echo.
    echo F.R.I.D.A.Y. exited with an error code.
    pause
)
