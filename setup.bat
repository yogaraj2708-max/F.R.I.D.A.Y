@echo off
title F.R.I.D.A.Y. 2.0 - Environment & Dependency Setup
cd /d "%~dp0"

echo =======================================================
echo    F.R.I.D.A.Y. 2.0 - Environment & Dependency Setup
echo =======================================================
echo.

echo [1/3] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR]: Python is not installed or not in your system PATH.
    echo Please install Python 3.10, 3.11, or 3.12 from https://www.python.org/
    echo Ensure you check the box: [x] "Add Python to PATH".
    pause
    exit /b 1
)

echo [2/3] Creating virtual environment (.venv)...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR]: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created successfully.
) else (
    echo Existing virtual environment detected.
)

echo [3/3] Upgrading pip and installing requirements...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR]: Failed to install dependencies. Please check your internet connection.
    pause
    exit /b 1
)

echo.
echo =======================================================
echo   Setup Complete! All dependencies successfully installed.
echo   You can now launch F.R.I.D.A.Y. via run_friday_gui.bat
echo =======================================================
echo.
pause
