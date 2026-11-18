@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

if not exist .venv\Scripts\python.exe (
  echo Virtual environment is missing.
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)

echo.
echo [1/6] Generating bundled data packs...
call .venv\Scripts\python.exe scripts\generate_data_packs.py
if errorlevel 1 goto :error

echo.
echo [2/6] Training or reusing bundled models...
call .venv\Scripts\python.exe scripts\train_data_pack_models.py
if errorlevel 1 goto :error

echo.
echo [3/6] Training or reusing Step 16 ML suite...
call .venv\Scripts\python.exe scripts\train_step16_ml_suite.py
if errorlevel 1 goto :error

echo.
echo [4/6] Training or reusing Step 17 double-data ML suite...
call .venv\Scripts\python.exe scripts\train_step17_double_data_suite.py
if errorlevel 1 goto :error

echo.
echo [5/6] Training or reusing Step 19 5X full-data ML suite...
call .venv\Scripts\python.exe scripts\train_step19_5x_suite.py
if errorlevel 1 goto :error

echo.
echo [6/6] Verifying data and model library...
call .venv\Scripts\python.exe scripts\data_pack_smoke_test.py
if errorlevel 1 goto :error

echo.
echo Data and model library is ready.
echo Open BioIntel AI and choose Data ^& Model Library.
pause
exit /b 0

:error
echo.
echo Data/model build failed. Review the error above.
pause
exit /b 1
