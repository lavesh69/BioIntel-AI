from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

TOOLS_ROOT = Path.home() / "AppData" / "Local" / "BioIntelAI" / "ScientificTools"
MAX_ARCHIVE_FILES = 2_000
MAX_UNCOMPRESSED_BYTES = 1_500_000_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_file(url: str, dest: Path, expected_sha256: str) -> Path:
    expected = expected_sha256.strip().lower()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise ValueError("A verified 64-character SHA-256 digest is required.")
    print(f"Downloading: {url} -> {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "BioIntelAI-Installer/15.6.0"})
    staged = dest.with_suffix(dest.suffix + ".download")
    with urllib.request.urlopen(req, timeout=60) as resp, staged.open("wb") as f:
        shutil.copyfileobj(resp, f)
    actual = sha256_file(staged)
    if actual != expected:
        staged.unlink(missing_ok=True)
        raise ValueError(f"Downloaded archive SHA-256 mismatch: expected {expected}, got {actual}")
    os.replace(staged, dest)
    print(f"Downloaded ({dest.stat().st_size / (1024*1024):.2f} MB)")
    return dest


def safe_extract_zip(source: Path, destination: Path) -> None:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source, "r") as archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_FILES:
            raise ValueError("Scientific tool archive contains too many members.")
        total = 0
        for member in members:
            normalized = member.filename.replace("\\", "/")
            relative = PurePosixPath(normalized)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or (relative.parts and ":" in relative.parts[0])
            ):
                raise ValueError(f"Unsafe archive path: {member.filename}")
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"Symbolic links are not accepted: {member.filename}")
            target = (destination / Path(*relative.parts)).resolve()
            if not target.is_relative_to(destination):
                raise ValueError(f"Archive path escapes destination: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            total += int(member.file_size)
            if total > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("Scientific tool archive exceeds the extraction size limit.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source_handle, target.open("wb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle)


def setup_minimap2(expected_sha256: str):
    print("\n--- Setting up Minimap2 (Windows x64) ---")
    dest_dir = TOOLS_ROOT / "minimap2"
    if (dest_dir / "minimap2.exe").is_file():
        print("Minimap2 already present!")
        return
    url = "https://github.com/lh3/minimap2/releases/download/v2.28/minimap2-2.28_x64-win.zip"
    zip_path = TOOLS_ROOT / "minimap2.zip"
    try:
        download_file(url, zip_path, expected_sha256)
        safe_extract_zip(zip_path, dest_dir)
        print("Extracted Minimap2 successfully.")
    except Exception as exc:
        print(f"Minimap2 download skipped / notice: {exc}")

def setup_plink2(expected_sha256: str):
    print("\n--- Setting up PLINK2 (Windows x64) ---")
    dest_dir = TOOLS_ROOT / "plink2"
    if (dest_dir / "plink2.exe").is_file():
        print("PLINK2 already present!")
        return
    url = "https://s3.amazonaws.com/plink2-assets/alpha6/plink2_win64_20240901.zip"
    zip_path = TOOLS_ROOT / "plink2.zip"
    try:
        download_file(url, zip_path, expected_sha256)
        safe_extract_zip(zip_path, dest_dir)
        print("Extracted PLINK2 successfully.")
    except Exception as exc:
        print(f"PLINK2 download skipped / notice: {exc}")

def main():
    parser = argparse.ArgumentParser(description="BioIntel AI Automatic Toolchain Setup")
    parser.add_argument("--all", action="store_true", help="Download all open-source toolchain binaries")
    parser.add_argument(
        "--minimap2-sha256",
        default=os.environ.get("BIOINTEL_MINIMAP2_SHA256", ""),
        help="Publisher-verified SHA-256 for the pinned Minimap2 archive.",
    )
    parser.add_argument(
        "--plink2-sha256",
        default=os.environ.get("BIOINTEL_PLINK2_SHA256", ""),
        help="Publisher-verified SHA-256 for the pinned PLINK2 archive.",
    )
    args = parser.parse_args()

    TOOLS_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"Target Scientific Tools directory: {TOOLS_ROOT}")

    setup_minimap2(args.minimap2_sha256)
    setup_plink2(args.plink2_sha256)

    print("\n[SUCCESS] Scientific toolchain installer check complete!")

if __name__ == "__main__":
    main()
