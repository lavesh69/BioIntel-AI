import os, sys, zipfile
from pathlib import Path

source = Path(r'C:\Users\lavesh dobriyal\AppData\Local\BioIntelAI\App\Releases\15.6.0-Step220')
target_dir = Path(r'C:\Users\lavesh dobriyal\Pictures\Camera Roll\HEY')

target_dir.mkdir(parents=True, exist_ok=True)

ignore_dirs = {'.venv', '__pycache__', '.git', 'tmp'}
ignore_exts = {'.pyc', '.pyo', '.log'}

print('Packaging STAGE 4 MASTER 4-PART BioIntel-AI-15.6.0-HEAVILY-UPGRADED Zip files in Camera Roll\\\\HEY...')
all_files = []
for root, dirs, files in os.walk(source):
    dirs[:] = [d for d in dirs if d not in ignore_dirs]
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext not in ignore_exts:
            full_path = Path(root) / f
            try:
                sz = full_path.stat().st_size
                all_files.append((full_path, sz))
            except Exception:
                pass

all_files.sort(key=lambda x: x[1], reverse=True)

buckets = [[], [], [], []]
bucket_sizes = [0, 0, 0, 0]

for full_path, sz in all_files:
    min_idx = bucket_sizes.index(min(bucket_sizes))
    buckets[min_idx].append(full_path)
    bucket_sizes[min_idx] += sz

for part_num in range(1, 5):
    part_files = buckets[part_num - 1]
    zip_path = target_dir / f'BioIntel-AI-15.6.0-HEAVILY-UPGRADED-Part{part_num}.zip'
    
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for full_path in part_files:
            try:
                arcname = full_path.relative_to(source)
                zf.write(full_path, arcname)
            except Exception:
                pass
            
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f'Created Heavily Upgraded Zip Part {part_num}: {zip_path.name} ({len(part_files)} files, {size_mb:.2f} MB)')

bat_code = '@echo off\n' + 'title BioIntel AI Heavily Upgraded - 1-Click 4-Part Unpacker\n' + 'echo ========================================================\n' + 'echo   BIOINTEL AI HEAVILY UPGRADED 4-PART AUTOMATIC UNPACKER\n' + 'echo ========================================================\n' + 'echo Extracting Part 1, Part 2, Part 3, Part 4 into BioIntel-Step220...\n' + 'powershell -Command "Expand-Archive -Path \'.\\BioIntel-AI-15.6.0-HEAVILY-UPGRADED-Part1.zip\' -DestinationPath \'.\\BioIntel-Step220\' -Force"\n' + 'powershell -Command "Expand-Archive -Path \'.\\BioIntel-AI-15.6.0-HEAVILY-UPGRADED-Part2.zip\' -DestinationPath \'.\\BioIntel-Step220\' -Force"\n' + 'powershell -Command "Expand-Archive -Path \'.\\BioIntel-AI-15.6.0-HEAVILY-UPGRADED-Part3.zip\' -DestinationPath \'.\\BioIntel-Step220\' -Force"\n' + 'powershell -Command "Expand-Archive -Path \'.\\BioIntel-AI-15.6.0-HEAVILY-UPGRADED-Part4.zip\' -DestinationPath \'.\\BioIntel-Step220\' -Force"\n' + 'cd BioIntel-Step220\n' + 'call INSTALL_WINDOWS.bat\n' + 'pause\n'

(target_dir / 'UNPACK_SHIRO_AI.bat').write_text(bat_code, encoding='utf-8')
print('SUCCESS! Created all 4 BioIntel-AI-15.6.0-HEAVILY-UPGRADED Zips and UNPACK_SHIRO_AI.bat in Camera Roll\\\\HEY')
