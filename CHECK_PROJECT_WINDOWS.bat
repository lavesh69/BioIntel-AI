@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

if not exist .venv\Scripts\python.exe (
  echo The virtual environment is missing.
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)

echo [1/14] Core imports...
call .venv\Scripts\python.exe -c "import streamlit, fastapi, uvicorn, httpx, Bio, rdkit, sklearn, pandas, numpy; print('Core imports passed')"
if errorlevel 1 goto :error

echo [2/14] Python compilation...
call .venv\Scripts\python.exe -m compileall -q app.py pages src scripts tests
if errorlevel 1 goto :error

echo [3/14] Unit tests...
call .venv\Scripts\python.exe -m pytest -q
if errorlevel 1 goto :error

echo [4/14] No-login API smoke test...
call .venv\Scripts\python.exe -c "from fastapi.testclient import TestClient; from biointel.api.main import app; c=TestClient(app); h=c.get('/health'); assert h.status_code==200; assert h.json()['authentication_required'] is False; assert c.get('/model/status').status_code==200; assert c.get('/system/diagnostics').status_code==200; assert c.get('/catalog/models').status_code==200; assert c.get('/catalog/datasets').status_code==200; assert c.get('/workflow/status').status_code==200; assert c.get('/ui/catalog').status_code==200; assert c.get('/workflow/report-data').status_code==200; assert c.get('/portfolio/projects').status_code==200; assert c.get('/operations/alerts').status_code==200; assert c.get('/operations/timeline').status_code==200; assert c.get('/executive/summary').status_code==200; assert c.get('/governance/summary').status_code==200; assert c.get('/audit/integrity').status_code==200; assert c.get('/data/packs').status_code==200; assert c.get('/models/benchmark').status_code==200; assert c.get('/models/double-benchmark').status_code==200; assert c.get('/models/5x-benchmark').status_code==200; assert c.get('/system/cache-status').status_code==200; assert c.get('/data/coverage').status_code==200; assert c.get('/databases/status').status_code==200; assert c.get('/intelligence/search', params={'q':'model'}).status_code==200; assert c.get('/knowledge/search', params={'q':'dataset'}).status_code==200; assert c.get('/analytics/overview').status_code==200; assert c.get('/assets/search', params={'q':'model'}).status_code==200; print('API smoke test passed')"
if errorlevel 1 goto :error

echo [5/14] Professional database fabric...
call .venv\Scripts\python.exe -m biointel database-status
if errorlevel 1 goto :error

echo [6/14] System diagnostics...
call .venv\Scripts\python.exe scripts\diagnose.py
if errorlevel 1 goto :error

echo [7/14] Workspace backup smoke test...
call .venv\Scripts\python.exe -m biointel workspace-backup --output backups\check_backup.zip
if errorlevel 1 goto :error
del /q backups\check_backup.zip >nul 2>&1

echo [8/14] Workspace report smoke test...
call .venv\Scripts\python.exe -m biointel workspace-report --output reports\generated\check_report.html
if errorlevel 1 goto :error
del /q reports\generated\check_report.html >nul 2>&1
del /q reports\generated\check_report.json >nul 2>&1

echo [9/14] Executive summary smoke test...
call .venv\Scripts\python.exe -m biointel executive-summary --output reports\generated\check_executive.json
if errorlevel 1 goto :error
del /q reports\generated\check_executive.json >nul 2>&1

echo [10/14] Governance and evidence smoke test...
call .venv\Scripts\python.exe scripts\governance_smoke_test.py
if errorlevel 1 goto :error

echo [11/14] Data and model library smoke test...
call .venv\Scripts\python.exe scripts\data_pack_smoke_test.py
if errorlevel 1 goto :error

echo [12/14] Release verification...
call .venv\Scripts\python.exe scripts\verify_release.py
if errorlevel 1 goto :error

echo [13/14] Ruff...
call .venv\Scripts\python.exe -m ruff check .
if errorlevel 1 goto :error

echo [14/14] Black formatting check...
call .venv\Scripts\python.exe -m black --check --workers 1 .
if errorlevel 1 goto :error

echo.
echo BioIntel AI Step 21 Professional Intelligence passed all local checks.
pause
exit /b 0

:error
echo.
echo A project check failed. Read the error above.
pause
exit /b 1
