@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Python compilation
python -m compileall -q src pages tests || goto :fail

echo [2/4] Code quality
ruff check src pages tests || goto :fail

echo [3/4] Critical regression tests
pytest -q tests\test_step52_critical_fixes.py tests\test_step48_equal_depth_projects.py tests\test_step49_deep_professional_projects.py || goto :fail

echo [4/4] Live connection and runtime tests
pytest -q tests\test_step50_runtime_repair.py tests\test_step51_connected_platform.py tests\test_step52_live_integrations.py || goto :fail

echo.
echo STEP 53 VERIFICATION PASSED
exit /b 0

:fail
echo.
echo STEP 53 VERIFICATION FAILED
exit /b 1
