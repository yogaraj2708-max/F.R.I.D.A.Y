@echo off
title F.R.I.D.A.Y. 2.0 - Tactical Personal Assistant
cd /d "%~dp0"
if exist "dist\FRIDAY_2.0\FRIDAY_2.0.exe" (
    start "" "dist\FRIDAY_2.0\FRIDAY_2.0.exe"
) else (
    call run_friday_gui.bat
)
