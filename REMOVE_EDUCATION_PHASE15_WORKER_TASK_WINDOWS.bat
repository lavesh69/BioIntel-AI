@echo off
setlocal EnableExtensions
schtasks /Delete /F /TN "BioIntel Education Phase15 Worker"
if errorlevel 1 exit /b 1
echo BioIntel Education Phase15 Worker task removed.
pause
