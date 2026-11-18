import math
import os
import pathlib
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "dist_release"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MASTER_ZIP_PATH = OUTPUT_DIR / "BioIntel_AI_v15.6.0_Full.zip"

print("--- Step 1: Creating Master ZIP Archive ---")

# Files/folders to exclude
EXCLUDE_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", "dist_release", ".idea", ".vscode"}
EXCLUDE_EXTS = {".pyc", ".pyo", ".pyd"}

with zipfile.ZipFile(MASTER_ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in ROOT.rglob("*"):
        if path.is_file():
            # Check exclusions
            rel = path.relative_to(ROOT)
            parts = rel.parts
            if any(part in EXCLUDE_DIRS for part in parts):
                continue
            if path.suffix.lower() in EXCLUDE_EXTS:
                continue
            zf.write(path, arcname=rel)

total_bytes = MASTER_ZIP_PATH.stat().st_size
print(f"Master ZIP created successfully! Total size: {total_bytes} bytes ({total_bytes / (1024*1024):.2f} MB)")

print("--- Step 2: Splitting Master ZIP into 4 Equal Parts ---")

part_size = math.ceil(total_bytes / 4)
print(f"Calculated part size for each of the 4 parts: {part_size} bytes ({part_size / (1024*1024):.2f} MB)")

part_files = []
with MASTER_ZIP_PATH.open("rb") as master_f:
    for i in range(1, 5):
        part_name = f"BioIntel_AI_v15.6.0_Part{i}.zip"
        part_path = OUTPUT_DIR / part_name
        chunk = master_f.read(part_size)
        part_path.write_bytes(chunk)
        actual_size = part_path.stat().st_size
        part_files.append((part_name, actual_size))
        print(f"  Created Part {i}: {part_name} -> {actual_size} bytes ({actual_size / (1024*1024):.2f} MB)")

# Remove the temp master zip
MASTER_ZIP_PATH.unlink(missing_ok=True)

print("--- Step 3: Creating One-Click Extractor Script ---")
extractor_script = """@echo off
setlocal EnableExtensions DisableDelayedExpansion
title BioIntel AI 15.6.0 - Part Joiner & One-Click Extractor
echo ============================================================
echo BioIntel AI 15.6.0 - 4-Part Automatic Extractor & Installer
echo ============================================================
echo.

if not exist "BioIntel_AI_v15.6.0_Part1.zip" (
  echo ERROR: BioIntel_AI_v15.6.0_Part1.zip missing hai.
  echo Saare 4 Part ZIPs ko same folder me rkhein.
  pause
  exit /b 1
)

echo Joining 4 ZIP parts...
copy /b "BioIntel_AI_v15.6.0_Part1.zip"+"BioIntel_AI_v15.6.0_Part2.zip"+"BioIntel_AI_v15.6.0_Part3.zip"+"BioIntel_AI_v15.6.0_Part4.zip" "BioIntel_AI_v15.6.0_Joined.zip" >nul

echo Extracting BioIntel_AI_v15.6.0_Joined.zip...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path 'BioIntel_AI_v15.6.0_Joined.zip' -DestinationPath '.' -Force"

if exist "BioIntel_AI_v15.6.0_Joined.zip" del /f /q "BioIntel_AI_v15.6.0_Joined.zip"

echo.
echo Extraction complete! Starting Windows Installation...
call "INSTALL_WINDOWS.bat"
"""

(OUTPUT_DIR / "EXTRACT_AND_INSTALL_STEP220_WINDOWS.bat").write_text(extractor_script, encoding="utf-8")
print("One-click extractor script created: EXTRACT_AND_INSTALL_STEP220_WINDOWS.bat")

print("\n--- 4-PART ZIP CREATION SUCCESSFUL ---")
