@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo BioIntel virtual environment not found. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
if "%~1"=="" (
  echo Drag a supported document onto this file or run:
  echo EXTRACT_DOCUMENT_WINDOWS.bat "C:\path\document.pdf"
  pause
  exit /b 1
)
.venv\Scripts\python.exe scripts\extract_document.py "%~1" --ocr auto
echo.
pause
