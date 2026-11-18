@echo off
setlocal
cd /d "%~dp0"
if "%~2"=="" (
  echo Usage: CONFIGURE_STEP122_PROTEIN_MODELS_WINDOWS.bat backend model_path [expected_sha256]
  echo Backends: proteinmpnn rfdiffusion colabfold_batch foldx rosetta_scripts
  exit /b 2
)
set "HASHARG="
if not "%~3"=="" set "HASHARG=--sha256 %~3"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\configure_step122_protein_asset.py "%~1" "%~2" --license-accepted %HASHARG%
) else (
  python scripts\configure_step122_protein_asset.py "%~1" "%~2" --license-accepted %HASHARG%
)
endlocal
