import os
import pathlib
import zipfile

root_dir = pathlib.Path(r"C:\Users\lavesh dobriyal\.gemini\antigravity\scratch\BioIntel-Step220")
downloads_dir = pathlib.Path(r"C:\Users\lavesh dobriyal\Downloads")

prefix = "BioIntel-AI-15.6.0-RC1-Part"

EXCLUDE_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", "dist_release", ".idea", ".vscode", "scratch"}
EXCLUDE_EXTS = {".pyc", ".pyo", ".pyd"}

all_files = []
for p in root_dir.rglob("*"):
    if p.is_file():
        rel = p.relative_to(root_dir)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if p.suffix.lower() in EXCLUDE_EXTS:
            continue
        all_files.append((p, rel))

all_files.sort(key=lambda x: str(x[1]))
total_files = len(all_files)
print(f"Packaging BioIntel AI 15.6.0 RC1 ({total_files} files)...")

chunk_size = (total_files + 3) // 4
parts = [all_files[i:i + chunk_size] for i in range(0, total_files, chunk_size)]

for idx, file_chunk in enumerate(parts, 1):
    zip_path = downloads_dir / f"{prefix}{idx}.zip"
    print(f"Creating RC1 Part {idx}: {zip_path.name} ({len(file_chunk)} files)...")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for full_p, rel_p in file_chunk:
            archive_path = pathlib.Path("BioIntel-Step220") / rel_p
            zf.write(full_p, arcname=archive_path)
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  RC1 Part {idx} created: {size_mb:.2f} MB")

print("All 4 final RC1 ZIP parts successfully created in Downloads folder!")
