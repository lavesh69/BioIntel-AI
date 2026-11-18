@echo off
setlocal EnableExtensions
pushd "%~dp0" >nul 2>&1 || exit /b 1
where ollama.exe >nul 2>&1
if errorlevel 1 (
  echo SHIRO_LOCAL_RUNTIME=SETUP_REQUIRED
  popd
  exit /b 2
)
ollama --version
powershell -NoProfile -Command "try { $r=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5; $r.models|ForEach-Object{$_.name}; exit 0 } catch { Write-Error $_.Exception.Message; exit 3 }"
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
