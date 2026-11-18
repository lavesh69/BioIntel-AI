@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title BioIntel AI Step 115 - Verify Installation

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  for /f "usebackq delims=" %%P in (`py -3.11 -c "import sys;print(sys.executable)" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
)
if not exist "%PYTHON_EXE%" (
  echo ERROR: Python environment not found. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)

"%PYTHON_EXE%" "scripts\verify_step115_non_chart_visuals.py"
if errorlevel 1 (
  echo ERROR: Step 115 release verification failed.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $root=[IO.Path]::GetFullPath('%~dp0'); $manifest=Join-Path $root 'FILE_MANIFEST_SHA256.txt'; $bad=@(); $checked=0; foreach($line in Get-Content -LiteralPath $manifest){ if($line -match '^([0-9a-fA-F]{64})  (.+)$'){ $checked++; $path=Join-Path $root $Matches[2]; if(-not(Test-Path -LiteralPath $path)){ $bad+=('Missing: '+$Matches[2]); continue }; $actual=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant(); if($actual -ne $Matches[1].ToLowerInvariant()){ $bad+=('Changed: '+$Matches[2]) } } }; if($bad.Count){ throw (($bad | Select-Object -First 10) -join [Environment]::NewLine) }; Write-Host ('Internal SHA-256 verification passed: '+$checked+' files.')"
if errorlevel 1 (
  echo ERROR: Internal file verification failed.
  pause
  exit /b 1
)

echo.
echo BIOINTEL AI 11.6.0 VERIFICATION PASSED.
pause
exit /b 0
