@echo off
setlocal
cd /d "%~dp0"
python scripts\run_peak_phase2_browser_regression.py
set CODE=%ERRORLEVEL%
if "%CODE%"=="2" (
  echo Browser regression dependencies are unavailable. Install Streamlit and Playwright, then run playwright install chromium.
)
exit /b %CODE%
