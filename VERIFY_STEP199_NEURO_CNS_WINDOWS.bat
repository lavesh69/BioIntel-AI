@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)

%PYTHON_EXE% -m pytest -q tests\test_neuro_cns_studio.py tests\test_neuro_cns_page.py tests\test_neuro_cns_step198_hardening.py tests\test_neuro_cns_step199_advanced.py
if errorlevel 1 (
  echo Step199 Neuro/CNS verification failed.
  exit /b 1
)

echo Step199 Neuro/CNS verification passed.
exit /b 0
