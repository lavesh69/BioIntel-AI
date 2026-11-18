@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
title BioIntel MCP Server
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
if not defined BIOINTEL_USER_DATA_DIR set "BIOINTEL_USER_DATA_DIR=%LOCALAPPDATA%\BioIntelAI\UserData"
if not defined BIOINTEL_MCP_PRINCIPAL (
  echo ERROR: BIOINTEL_MCP_PRINCIPAL is not configured.
  popd
  exit /b 2
)
if not defined BIOINTEL_MCP_INSTITUTION (
  echo ERROR: BIOINTEL_MCP_INSTITUTION is not configured.
  popd
  exit /b 2
)
if not defined BIOINTEL_MCP_API_KEY (
  echo ERROR: BIOINTEL_MCP_API_KEY is not configured.
  popd
  exit /b 2
)
set "PY=%CD%\.venv\Scripts\python.exe"
set "PYARGS="
if not exist "%PY%" (
  set "PY=py"
  set "PYARGS=-3.11"
)
set "PYTHONPATH=%CD%\src"
if /I "%~1"=="/diagnose" (
  "%PY%" %PYARGS% -m biointel.education.phase23_30.mcp_server --diagnose
) else (
  "%PY%" %PYARGS% -m biointel.education.phase23_30.mcp_server
)
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
