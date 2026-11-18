@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src;%CD%"
set "OMP_NUM_THREADS=1"
set "OPENBLAS_NUM_THREADS=1"
set "MKL_NUM_THREADS=1"
set "NUMEXPR_NUM_THREADS=1"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
%PY% -m compileall -q src\biointel\neuro_cns pages\263_Neuro_CNS_Intelligence_Studio.py
if errorlevel 1 goto :fail
%PY% -m pytest -q tests\test_neuro_cns_studio.py tests\test_neuro_cns_page.py tests\test_neuro_cns_step198_hardening.py
if errorlevel 1 goto :fail
echo.
echo Step198 Neuro/CNS verification PASSED.
exit /b 0
:fail
echo.
echo Step198 Neuro/CNS verification FAILED. Review the error output above.
exit /b 1
