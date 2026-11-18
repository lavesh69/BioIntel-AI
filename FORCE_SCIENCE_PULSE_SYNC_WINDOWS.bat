@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
".venv\Scripts\python.exe" "scripts\science_pulse_control.py" force-sync
pause
