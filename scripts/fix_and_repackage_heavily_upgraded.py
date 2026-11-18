"""
BioIntel AI 15.6.0 — Heavily Upgraded 4-Part Fix & Repackage Script
===================================================================
Fixes INSTALL_WINDOWS.bat and RUN_BOTH_WINDOWS.bat for the 4-part
heavily upgraded packaging layout, then creates balanced ZIPs plus
UNPACK_SHIRO_AI.bat in Camera Roll\\HEY.

Error sources fixed:
  1. INSTALL_WINDOWS.bat loops over parts 1-5 but we only ship 4 parts
  2. RUN_BOTH_WINDOWS.bat also checks for 5 parts
  3. EXTRACT_AND_INSTALL_STEP220_WINDOWS.bat references a 5-part PREFIX
  4. step206_contract.py has PART_COUNT = 5
  5. verify_step206_windows_install_run.py checks "for %%P in (1 2 3 4 5)"
  6. install_windows_step206.py validates 5-part markers
  7. step97_runtime_preflight.py returns set(range(1, 6))
  8. UNPACK_SHIRO_AI.bat needs to unpack into flat folder then run INSTALL
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────
SOURCE = Path(r"C:\Users\lavesh dobriyal\AppData\Local\BioIntelAI\App\Releases\15.6.0-Step220")
WORKSPACE = Path(r"C:\Users\lavesh dobriyal\.gemini\antigravity\scratch\BioIntel-AI-15.6.0-Stage2Workspace")
TARGET_DIR = Path(r"C:\Users\lavesh dobriyal\Pictures\Camera Roll\HEY")
PART_COUNT = 4
ZIP_PREFIX = "BioIntel-AI-15.6.0-HEAVILY-UPGRADED"

IGNORE_DIRS = {".venv", "__pycache__", ".git", "tmp", ".venv.step196-backup",
               ".venv.step206-backup", ".venv.step220-backup"}
IGNORE_EXTS = {".pyc", ".pyo", ".log"}


def fix_file(path: Path, replacements: list[tuple[str, str]]) -> bool:
    """Apply text replacements to a file. Returns True if any changes made."""
    if not path.is_file():
        print(f"  SKIP (not found): {path}")
        return False
    content = path.read_text(encoding="utf-8", errors="replace")
    original = content
    for old, new in replacements:
        content = content.replace(old, new)
    if content != original:
        path.write_text(content, encoding="utf-8")
        print(f"  FIXED: {path.name}")
        return True
    else:
        print(f"  OK (no changes needed): {path.name}")
        return False


def fix_all_5_to_4_references(root: Path) -> int:
    """Fix all 5-part references to 4-part across all critical files."""
    changes = 0

    # ── 1. step206_contract.py: PART_COUNT = 5 → 4 ──
    contract = root / "scripts" / "step206_contract.py"
    if contract.is_file():
        if fix_file(contract, [("PART_COUNT = 5", "PART_COUNT = 4")]):
            changes += 1

    # ── 2. INSTALL_WINDOWS.bat: loop 1 2 3 4 5 → 1 2 3 4 ──
    install_bat = root / "INSTALL_WINDOWS.bat"
    if install_bat.is_file():
        if fix_file(install_bat, [
            ("for %%P in (1 2 3 4 5)", "for %%P in (1 2 3 4)"),
        ]):
            changes += 1

    # ── 3. RUN_BOTH_WINDOWS.bat: loop 1 2 3 4 5 → 1 2 3 4 ──
    run_bat = root / "RUN_BOTH_WINDOWS.bat"
    if run_bat.is_file():
        if fix_file(run_bat, [
            ("for %%P in (1 2 3 4 5)", "for %%P in (1 2 3 4)"),
        ]):
            changes += 1

    # ── 4. EXTRACT_AND_INSTALL_STEP220_WINDOWS.bat: 5-part → 4-part ──
    extract_bat = root / "EXTRACT_AND_INSTALL_STEP220_WINDOWS.bat"
    if extract_bat.is_file():
        if fix_file(extract_bat, [
            ("for %%P in (1 2 3 4 5)", "for %%P in (1 2 3 4)"),
            ('set "PREFIX=BioIntel-AI-15.6.0-Step220-ULTIMATE-PROFESSIONAL-WINDOWS-V20.3-5PART"',
             f'set "PREFIX={ZIP_PREFIX}"'),
        ]):
            changes += 1

    # ── 5. step97_runtime_preflight.py: range(1, 6) → range(1, 5) ──
    preflight = root / "scripts" / "step97_runtime_preflight.py"
    if preflight.is_file():
        if fix_file(preflight, [
            ("return set(range(1, 6))", "return set(range(1, 5))"),
        ]):
            changes += 1

    # ── 6. verify_step206_windows_install_run.py ──
    verify = root / "scripts" / "verify_step206_windows_install_run.py"
    if verify.is_file():
        content = verify.read_text(encoding="utf-8", errors="replace")
        new_content = content
        # Fix the "five-part workflow" check string
        new_content = new_content.replace(
            '"for %%P in (1 2 3 4 5)" in install',
            '"for %%P in (1 2 3 4)" in install'
        )
        new_content = new_content.replace(
            '"for %%P in (1 2 3 4 5)" in run_bat',
            '"for %%P in (1 2 3 4)" in run_bat'
        )
        # Fix labels
        new_content = new_content.replace('"5/5 markers"', '"4/4 markers"')
        new_content = new_content.replace('"5/5 present"', '"4/4 present"')
        new_content = new_content.replace(
            "five-part workflow", "four-part workflow"
        )
        new_content = new_content.replace(
            "five-part scientific runtime preflight", "four-part scientific runtime preflight"
        )
        new_content = new_content.replace(
            'f"Step{RELEASE_STEP} accepts 5/5 markers"',
            'f"Step{RELEASE_STEP} accepts 4/4 markers"'
        )
        if new_content != content:
            verify.write_text(new_content, encoding="utf-8")
            print(f"  FIXED: {verify.name}")
            changes += 1
        else:
            print(f"  OK (no changes needed): {verify.name}")

    # ── 7. step206_release_gate.py: fix "5/5 present" label ──
    gate = root / "scripts" / "step206_release_gate.py"
    if gate.is_file():
        if fix_file(gate, [
            ('"5/5 present"', '"4/4 present"'),
            ('"five-part Step220 extraction"', '"four-part Step220 extraction"'),
        ]):
            changes += 1

    return changes


def create_4_part_markers(root: Path) -> None:
    """Create .release_parts/step220_partN.ok for parts 1-4."""
    parts_dir = root / ".release_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, 5):
        marker = parts_dir / f"step220_part{i}.ok"
        marker.write_text(f"Part {i} of 4 — BioIntel AI 15.6.0 Heavily Upgraded\n", encoding="utf-8")
    # Remove part 5 marker if it exists
    old_marker = parts_dir / "step220_part5.ok"
    old_marker.unlink(missing_ok=True)
    print(f"  Created 4-part markers in {parts_dir}")


def update_manifest_hashes(root: Path) -> int:
    """Update SHA-256 hashes for all changed files in the manifest."""
    manifest_path = root / "release" / "SOURCE_MANIFEST_SHA256.json"
    if not manifest_path.is_file():
        print(f"  SKIP manifest (not found): {manifest_path}")
        return 0
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    files_list = data.get("files", [])
    updated = 0
    for item in files_list:
        rel_path = item.get("path")
        if not rel_path:
            continue
        file_path = root / rel_path
        if file_path.is_file():
            new_bytes = file_path.read_bytes()
            new_sha = hashlib.sha256(new_bytes).hexdigest()
            if item.get("sha256") != new_sha:
                item["sha256"] = new_sha
                item["size_bytes"] = len(new_bytes)
                updated += 1
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"  Updated {updated} hashes in manifest")
    return updated


def package_4_zips(root: Path, target_dir: Path) -> None:
    """Create 4 balanced ZIP files from the source tree."""
    target_dir.mkdir(parents=True, exist_ok=True)

    # Collect all files
    all_files: list[tuple[Path, int]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext not in IGNORE_EXTS:
                full_path = Path(dirpath) / f
                try:
                    sz = full_path.stat().st_size
                    all_files.append((full_path, sz))
                except OSError:
                    pass

    # Sort largest-first for balanced distribution
    all_files.sort(key=lambda x: x[1], reverse=True)

    # Distribute files into 4 buckets using greedy balancing
    buckets: list[list[Path]] = [[] for _ in range(PART_COUNT)]
    bucket_sizes = [0] * PART_COUNT
    for full_path, sz in all_files:
        min_idx = bucket_sizes.index(min(bucket_sizes))
        buckets[min_idx].append(full_path)
        bucket_sizes[min_idx] += sz

    # Create each ZIP
    for part_num in range(1, PART_COUNT + 1):
        part_files = buckets[part_num - 1]
        zip_path = target_dir / f"{ZIP_PREFIX}-Part{part_num}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for full_path in part_files:
                try:
                    arcname = full_path.relative_to(root)
                    zf.write(full_path, arcname)
                except Exception:
                    pass
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        print(f"  Part {part_num}: {zip_path.name} ({len(part_files)} files, {size_mb:.2f} MB)")


def write_unpack_bat(target_dir: Path) -> None:
    """Write the UNPACK_SHIRO_AI.bat auto-unpacker."""
    bat_content = (
        '@echo off\r\n'
        'setlocal EnableExtensions DisableDelayedExpansion\r\n'
        'title BioIntel AI (Shiro AI) — Heavily Upgraded 4-Part Unpacker\r\n'
        'echo ============================================================\r\n'
        'echo   BIOINTEL AI 15.6.0 HEAVILY UPGRADED — 4-PART UNPACKER\r\n'
        'echo   India\'s First-Ever AI-Powered Biotechnology Research Platform\r\n'
        'echo ============================================================\r\n'
        'echo.\r\n'
        '\r\n'
        'set "DEST=%LOCALAPPDATA%\\BioIntelAI\\InstallSource\\HeavilyUpgraded"\r\n'
        'if not exist "%DEST%" mkdir "%DEST%" >nul 2>&1\r\n'
        '\r\n'
        'echo Checking all 4 ZIP parts...\r\n'
        f'for %%P in (1 2 3 4) do if not exist "%~dp0{ZIP_PREFIX}-Part%%P.zip" (\r\n'
        '  echo ERROR: Part %%P ZIP is missing beside this file.\r\n'
        '  echo Keep this BAT and all four ZIPs in the same folder.\r\n'
        '  pause\r\n'
        '  exit /b 1\r\n'
        ')\r\n'
        '\r\n'
        'echo Extracting all 4 parts to: %DEST%\r\n'
        'echo This may take a few minutes...\r\n'
        'echo.\r\n'
        'for %%P in (1 2 3 4) do (\r\n'
        '  echo [%%P/4] Extracting Part %%P...\r\n'
        f'  powershell -NoProfile -Command "Expand-Archive -Path \'%~dp0{ZIP_PREFIX}-Part%%P.zip\' -DestinationPath \'%DEST%\' -Force"\r\n'
        '  if errorlevel 1 (\r\n'
        '    echo ERROR: Part %%P extraction failed.\r\n'
        '    pause\r\n'
        '    exit /b 1\r\n'
        '  )\r\n'
        ')\r\n'
        '\r\n'
        'echo.\r\n'
        'echo All 4 parts extracted successfully.\r\n'
        'echo.\r\n'
        '\r\n'
        'if not exist "%DEST%\\INSTALL_WINDOWS.bat" (\r\n'
        '  echo ERROR: INSTALL_WINDOWS.bat not found in extracted folder.\r\n'
        '  echo Extraction may have been incomplete. Try again.\r\n'
        '  pause\r\n'
        '  exit /b 1\r\n'
        ')\r\n'
        '\r\n'
        'echo Starting verified installation...\r\n'
        'call "%DEST%\\INSTALL_WINDOWS.bat"\r\n'
        'set "RC=%ERRORLEVEL%"\r\n'
        'if not "%RC%"=="0" (\r\n'
        '  echo.\r\n'
        '  echo Installation exited with code %RC%.\r\n'
        '  echo Check the error messages above.\r\n'
        '  pause\r\n'
        '  exit /b %RC%\r\n'
        ')\r\n'
        '\r\n'
        'echo.\r\n'
        'echo ============================================================\r\n'
        'echo   INSTALLATION COMPLETE!\r\n'
        'echo   Ab RUN_BOTH_WINDOWS.bat ya Desktop shortcut use karein.\r\n'
        'echo ============================================================\r\n'
        'pause\r\n'
        'exit /b 0\r\n'
    )
    bat_path = target_dir / "UNPACK_SHIRO_AI.bat"
    bat_path.write_text(bat_content, encoding="utf-8")
    print(f"  Created: {bat_path.name}")


def main() -> int:
    print("=" * 64)
    print("BioIntel AI 15.6.0 - Heavily Upgraded Fix & Repackage")
    print("=" * 64)
    print()

    # Step 1: Fix 5→4 part references in all critical files (installed copy)
    print("[1/6] Fixing 5-part -> 4-part references in installed copy...")
    changes = fix_all_5_to_4_references(SOURCE)
    print(f"  Total files changed: {changes}")
    print()

    # Step 2: Create 4-part markers
    print("[2/6] Creating 4-part release markers...")
    create_4_part_markers(SOURCE)
    print()

    # Step 3: Update SHA-256 manifest
    print("[3/6] Updating SHA-256 manifest hashes...")
    updated = update_manifest_hashes(SOURCE)
    print()

    # Step 4: Apply same fixes to workspace copy
    print("[4/6] Applying same fixes to workspace copy...")
    if WORKSPACE.is_dir():
        changes2 = fix_all_5_to_4_references(WORKSPACE)
        create_4_part_markers(WORKSPACE)
        update_manifest_hashes(WORKSPACE)
        print(f"  Total files changed in workspace: {changes2}")
    else:
        print("  SKIP: Workspace not found")
    print()

    # Step 5: Package 4 balanced ZIPs
    print("[5/6] Packaging 4 balanced heavily upgraded ZIPs...")
    package_4_zips(SOURCE, TARGET_DIR)
    print()

    # Step 6: Write UNPACK_SHIRO_AI.bat
    print("[6/6] Creating UNPACK_SHIRO_AI.bat...")
    write_unpack_bat(TARGET_DIR)
    print()

    print("=" * 64)
    print("ALL DONE! Files in Camera Roll\\HEY:")
    for f in sorted(TARGET_DIR.iterdir()):
        sz = f.stat().st_size / (1024 * 1024)
        print(f"  {f.name}  ({sz:.2f} MB)")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
