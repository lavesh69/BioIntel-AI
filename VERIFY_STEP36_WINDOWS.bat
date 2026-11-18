@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=%CD%\src
set OMP_NUM_THREADS=1
set OPENBLAS_NUM_THREADS=1
set MKL_NUM_THREADS=1
set NUMEXPR_NUM_THREADS=1

echo [1/5] Compiling Python sources...
python -m compileall -q src pages app.py || exit /b 1

echo [2/5] Checking Step 36 validation frameworks...
python -m pytest tests\test_step36_target_quality.py -q || exit /b 1

echo [3/5] Checking compliance, FAIR, SaaS and research maturity...
python -m pytest tests\test_step36_maturity_frameworks.py -q || exit /b 1

echo [4/5] Checking semantic visual baselines...
python -m pytest tests\visual\test_semantic_visual_regression.py -q || exit /b 1

echo [5/5] Reading maturity matrix...
python -c "from biointel.maturity import build_maturity_readiness; r=build_maturity_readiness('.'); print('Implementation:',r['implementation_average'],'/10'); assert r['all_implementation_targets_complete']"
if errorlevel 1 exit /b 1

echo Step 36 verification passed.
endlocal
