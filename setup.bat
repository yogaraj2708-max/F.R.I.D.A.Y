@echo off
title F.R.I.D.A.Y. 2.0 - Environment Setup
cd /d "%~dp0"

echo =======================================================
echo    F.R.I.D.A.Y. 2.0 - Environment and Dependency Setup
echo =======================================================
echo.

echo [1/3] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 goto :no_python

echo [2/3] Setting up Python environment...
set "PYTHON_EXE=python"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    echo Using existing virtual environment: .venv\Scripts\python.exe
    goto :install_deps
)

echo Creating virtual environment (.venv)...
python -m venv .venv >nul 2>&1

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    echo Virtual environment created successfully.
    goto :install_deps
)

if exist ".venv\bin\python.exe" (
    set "PYTHON_EXE=.venv\bin\python.exe"
    echo Virtual environment created in bin.
    goto :install_deps
)

echo [Notice]: Virtual environment could not be created or was restricted.
echo Using system Python directly.
set "PYTHON_EXE=python"

:install_deps
echo.
echo [3/3] Installing all required dependencies...
echo Using Python interpreter: %PYTHON_EXE%
echo.
"%PYTHON_EXE%" -m pip install --upgrade pip
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 goto :install_error

echo.
echo =======================================================
echo   Setup Complete! All dependencies successfully installed.
echo   You can now launch F.R.I.D.A.Y. via run_friday_gui.bat
echo =======================================================
echo.
pause
exit /b 0

:no_python
echo.
echo [ERROR]: Python is not installed or not in your system PATH.
echo Please install Python 3.10, 3.11, or 3.12 from https://www.python.org/
echo Ensure you check the box: [x] "Add Python to PATH".
echo.
pause
exit /b 1

:install_error
echo.
echo [ERROR]: Dependency installation failed. Please review the messages above.
echo.
pause
exit /b 1
