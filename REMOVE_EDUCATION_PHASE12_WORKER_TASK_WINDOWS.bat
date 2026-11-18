@echo off
setlocal EnableExtensions
schtasks /Delete /F /TN "BioIntel Education Phase12 Worker"
if errorlevel 1 exit /b 1
echo BioIntel Education Phase12 Worker task removed.
pause
