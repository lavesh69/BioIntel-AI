@echo off
setlocal
cd /d "%~dp0"
echo [BioIntel AI] Optimizing SQLite registries and analytics stores...
python -c "from pathlib import Path; from biointel.database.migrations import optimize_existing_registries; import json; print(json.dumps(optimize_existing_registries(Path.cwd()), indent=2))"
if errorlevel 1 (
  echo Optimization failed. Run INSTALL_WINDOWS.bat and try again.
  exit /b 1
)
echo Optimization complete.
endlocal
