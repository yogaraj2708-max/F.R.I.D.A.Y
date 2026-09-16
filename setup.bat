@echo off
title F.R.I.D.A.Y. 2.0 - Environment Setup
cd /d "%~dp0"

echo =======================================================
echo    F.R.I.D.A.Y. 2.0 - Environment and Dependency Setup
echo =======================================================
echo.

echo [1/3] Detecting compatible Python installation (3.10, 3.11, or 3.12)...

set "BASE_PYTHON="

:: 1. Check Python Launcher for 3.11
py -3.11 -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>&1
if %errorlevel% equ 0 (
    set "BASE_PYTHON=py -3.11"
    goto :python_found
)

:: 2. Check Python Launcher for 3.12
py -3.12 -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
if %errorlevel% equ 0 (
    set "BASE_PYTHON=py -3.12"
    goto :python_found
)

:: 3. Check Python Launcher for 3.10
py -3.10 -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 10) else 1)" >nul 2>&1
if %errorlevel% equ 0 (
    set "BASE_PYTHON=py -3.10"
    goto :python_found
)

:: 4. Check system 'python' command
python -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)" >nul 2>&1
if %errorlevel% equ 0 (
    set "BASE_PYTHON=python"
    goto :python_found
)

:: 5. If we reach here, either Python is not installed or an incompatible version was detected
python --version >nul 2>&1
if %errorlevel% neq 0 goto :no_python

:: Python is installed, but it's an incompatible version (like 3.13 or 3.14)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set "DETECTED_PY_VER=%%v"
goto :incompatible_python

:python_found
for /f "tokens=*" %%v in ('%BASE_PYTHON% --version 2^>^&1') do set "ACTIVE_PY_VER=%%v"
echo Compatible Python detected: %ACTIVE_PY_VER% (%BASE_PYTHON%)

echo.
echo [2/3] Setting up Python environment (.venv)...

:: Check existing .venv compatibility
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)" >nul 2>&1
    if %errorlevel% equ 0 (
        set "PYTHON_EXE=.venv\Scripts\python.exe"
        echo Using verified virtual environment: .venv\Scripts\python.exe
        goto :install_deps
    ) else (
        echo [Notice]: Existing .venv was created with an incompatible Python version.
        echo Removing incompatible .venv...
        rmdir /s /q .venv >nul 2>&1
    )
)

if exist ".venv\bin\python.exe" (
    echo [Notice]: Removing incompatible Unix-style .venv...
    rmdir /s /q .venv >nul 2>&1
)

echo Creating fresh virtual environment (.venv) using %ACTIVE_PY_VER%...
%BASE_PYTHON% -m venv .venv >nul 2>&1

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    echo Virtual environment created successfully.
    goto :install_deps
)

echo [Notice]: Virtual environment creation restricted. Using %BASE_PYTHON% directly.
set "PYTHON_EXE=%BASE_PYTHON%"

:install_deps
echo.
echo [3/3] Installing all required dependencies...
echo Using Python interpreter: %PYTHON_EXE%
echo.
"%PYTHON_EXE%" -m pip install --upgrade pip
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 goto :install_error

echo.
echo Creating Desktop Shortcut and registering application icon...
"%PYTHON_EXE%" scripts\create_desktop_shortcut.py >nul 2>&1

echo.
echo =======================================================
echo   Setup Complete! All dependencies successfully installed.
echo   Desktop shortcut created: F.R.I.D.A.Y. 2.0
echo   You can launch F.R.I.D.A.Y. from your Desktop or run_friday_gui.bat
echo =======================================================
echo.
pause
exit /b 0

:no_python
echo.
echo ========================================================================
echo [ERROR]: Python is not installed or not in your system PATH.
echo.
echo Please download and install Python 3.11 (Recommended: 3.11.9):
echo https://www.python.org/downloads/release/python-3119/
echo.
echo CRITICAL: During installation, make sure you check the box:
echo [x] "Add Python to PATH"
echo ========================================================================
echo.
pause
exit /b 1

:incompatible_python
echo.
echo ========================================================================
echo [ERROR]: Incompatible Python Version Detected!
echo.
echo Your system is currently using: %DETECTED_PY_VER%
echo.
echo WHY THIS HAPPENED:
echo PySide6 (Qt GUI), Faster-Whisper, and AI libraries do NOT yet support
echo Python 3.13 or Python 3.14 (pre-release). They require Python 3.10, 3.11, or 3.12.
echo.
echo HOW TO FIX IN 2 MINUTES:
echo 1. Download and run the official Python 3.11.9 64-bit installer:
echo    https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
echo.
echo 2. IMPORTANT: On the first screen of the installer, check the box:
echo    [x] "Add Python to PATH"
echo.
echo 3. Click "Install Now".
echo 4. Delete the ".venv" folder in your F.R.I.D.A.Y. directory (if it exists).
echo 5. Re-run setup.bat!
echo ========================================================================
echo.
pause
exit /b 1

:install_error
echo.
echo ========================================================================
echo [ERROR]: Dependency installation failed. Please review the errors above.
echo ========================================================================
echo.
pause
exit /b 1
