@echo off
setlocal
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
python scripts\step170_build_assets.py --root "%CD%" || exit /b 1
python scripts\step170_validate_runtime_reference.py --root "%CD%" || exit /b 1
python -m pytest -q tests\test_step170_runtime_reference_qualification.py || exit /b 1
echo STEP 170 VERIFICATION PASSED
exit /b 0
