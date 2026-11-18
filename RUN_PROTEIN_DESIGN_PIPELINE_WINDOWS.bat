@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: RUN_PROTEIN_DESIGN_PIPELINE_WINDOWS.bat request.json [--execute]
  echo Templates are in data\templates\step122\
  exit /b 2
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\run_step122_protein_design_pipeline.py %*
) else (
  python scripts\run_step122_protein_design_pipeline.py %*
)
endlocal
