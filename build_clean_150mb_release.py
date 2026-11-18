import math
import os
import pathlib
import shutil
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "dist_release_v2"

# Clean old artifacts in dist_release
if OUTPUT_DIR.exists():
    for item in OUTPUT_DIR.glob("*"):
        if item.is_file():
            item.unlink(missing_ok=True)
else:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MASTER_ZIP = OUTPUT_DIR / "BioIntel_AI_v15.6.0_CleanMaster.zip"

print("--- Step 1: Building Clean Master ZIP Archive (Zero Code Loss) ---")

EXCLUDE_DIRS = {
    ".venv",
    ".git",
    "__pycache__",
    ".pytest_cache",
    "dist_release",
    "BioIntel-Step220",
    ".idea",
    ".vscode",
}
EXCLUDE_EXTS = {".pyc", ".pyo", ".pyd"}

with zipfile.ZipFile(MASTER_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for path in ROOT.rglob("*"):
        if path.is_file():
            rel = path.relative_to(ROOT)
            if any(part in EXCLUDE_DIRS for part in rel.parts):
                continue
            if path.suffix.lower() in EXCLUDE_EXTS:
                continue
            if path.name.startswith("test_") and path.name.endswith(".zip"):
                continue
            zf.write(path, arcname=rel)

total_bytes = MASTER_ZIP.stat().st_size
total_mb = total_bytes / (1024 * 1024)
print(f"Master ZIP created successfully! Total size: {total_bytes} bytes ({total_mb:.2f} MB)")

print("--- Step 2: Splitting into 4 Equal Parts ---")

part_size = math.ceil(total_bytes / 4)
part_mb = part_size / (1024 * 1024)
print(f"Each part size: {part_size} bytes ({part_mb:.2f} MB)")

for i in range(1, 5):
    part_name = f"BioIntel_AI_v15.6.0_Part{i}.zip"
    part_path = OUTPUT_DIR / part_name
    with MASTER_ZIP.open("rb") as mf:
        mf.seek((i - 1) * part_size)
        chunk = mf.read(part_size)
        part_path.write_bytes(chunk)
    print(f"  Created Part {i}: {part_name} -> {part_path.stat().st_size / (1024*1024):.2f} MB")

MASTER_ZIP.unlink(missing_ok=True)

print("--- Step 3: Creating Extractor Script ---")
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

# Copy to artifacts directory
ARTIFACT_DIR = pathlib.Path("C:/Users/lavesh dobriyal/.gemini/antigravity/brain/bf3bcec5-9acf-4bae-8a81-cc38f753f063")
if ARTIFACT_DIR.exists():
    for f in OUTPUT_DIR.glob("*"):
        shutil.copy(f, ARTIFACT_DIR / f.name)

print("\n--- 4-PART COMPACT RELEASE SUCCESSFUL ---")
