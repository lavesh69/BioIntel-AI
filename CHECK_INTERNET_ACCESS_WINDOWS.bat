@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
set "BIOINTEL_INTERNET_ENABLED=1"

if not exist .venv\Scripts\python.exe (
  echo Virtual environment is missing. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)

echo Checking BioIntel internet configuration...
call .venv\Scripts\python.exe -m biointel internet-status
if errorlevel 1 goto :error

echo.
echo Checking RCSB PDB, PubChem, UniProt and ChEMBL connectivity...
call .venv\Scripts\python.exe -m biointel internet-check
if errorlevel 1 goto :error

echo.
echo Internet access checks completed.
pause
exit /b 0

:error
echo.
echo Internet access check failed. Confirm Windows network, DNS, proxy and firewall settings.
pause
exit /b 1
