@echo off
setlocal EnableExtensions DisableDelayedExpansion
title BioIntel AI 15.6.0 Step220 - Sanitized Support Bundle
if exist "%LOCALAPPDATA%\BioIntelAI\App\Releases\15.6.0-Step220\.venv\Scripts\python.exe" (
  "%LOCALAPPDATA%\BioIntelAI\App\Releases\15.6.0-Step220\.venv\Scripts\python.exe" "%LOCALAPPDATA%\BioIntelAI\App\Releases\15.6.0-Step220\scripts\step206_support_bundle.py" --root "%LOCALAPPDATA%\BioIntelAI\App\Releases\15.6.0-Step220"
) else (
  echo ERROR: Managed BioIntel installation missing hai. INSTALL_WINDOWS.bat run karein.
  pause
  exit /b 1
)
pause
exit /b %ERRORLEVEL%
