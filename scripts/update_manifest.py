import json
import hashlib
from pathlib import Path

target_dirs = [
    Path(r'C:\Users\lavesh dobriyal\.gemini\antigravity\scratch\BioIntel-AI-15.6.0'),
    Path(r'C:\Users\lavesh dobriyal\AppData\Local\BioIntelAI\App\Releases\15.6.0-Step220'),
]

for root_dir in target_dirs:
    if not root_dir.exists():
        continue
    manifest_path = root_dir / 'release' / 'SOURCE_MANIFEST_SHA256.json'
    if not manifest_path.is_file():
        continue
    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    files = data.get('files', [])
    updated = 0
    for item in files:
        rel_path = item.get('path')
        if not rel_path:
            continue
        file_path = root_dir / rel_path
        if file_path.is_file():
            new_bytes = file_path.read_bytes()
            new_sha = hashlib.sha256(new_bytes).hexdigest()
            if item.get('sha256') != new_sha:
                item['sha256'] = new_sha
                item['size_bytes'] = len(new_bytes)
                updated += 1
    manifest_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(f'Updated {updated} hashes in {manifest_path}')
