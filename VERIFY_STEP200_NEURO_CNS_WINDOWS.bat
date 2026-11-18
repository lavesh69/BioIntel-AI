@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

for %%P in (1 2 3 4 5) do if not exist ".release_parts\step200_part%%P.ok" (
  echo ERROR: Missing Step200 Part %%P. Extract all five matching ZIPs again.
  exit /b 200
)

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" "scripts\verify_step200_neuro.py" --root "." --pytest --output "reports\step200-neuro-verification.json"
if errorlevel 1 (
  echo Step200 Neuro/CNS verification failed.
  exit /b 1
)

echo Step200 Neuro/CNS verification passed: 23 modules, 18 advanced systems.
exit /b 0
