@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo BioIntel virtual environment not found. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
if "%~1"=="" (
  echo Usage: WATCH_DOCUMENT_FOLDER_WINDOWS.bat "C:\Research\Incoming"
  pause
  exit /b 1
)
.venv\Scripts\python.exe scripts\watch_document_folder.py "%~1" --recursive --ocr auto
echo.
pause
