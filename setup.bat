@echo off
title F.R.I.D.A.Y. 2.0 - Environment Setup
cd /d "%~dp0"

echo =======================================================
echo    F.R.I.D.A.Y. 2.0 - Environment and Dependency Setup
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

echo [2/3] Setting up Python environment...
set "PYTHON_EXE=python"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    echo Using existing virtual environment: .venv\Scripts\python.exe
) else (
    echo Creating virtual environment (.venv)...
    python -m venv .venv >nul 2>&1
    if exist ".venv\Scripts\python.exe" (
        set "PYTHON_EXE=.venv\Scripts\python.exe"
        echo Virtual environment created successfully.
    ) else if exist ".venv\bin\python.exe" (
        set "PYTHON_EXE=.venv\bin\python.exe"
        echo Virtual environment created in bin.
    ) else (
        echo [Notice]: Virtual environment creation skipped or restricted by Windows.
        echo Using system Python directly.
        set "PYTHON_EXE=python"
    )
)

echo.
echo [3/3] Installing all required dependencies...
echo Using Python interpreter: %PYTHON_EXE%
"%PYTHON_EXE%" -m pip install --upgrade pip
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR]: Dependency installation failed. Please check pip output above.
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
