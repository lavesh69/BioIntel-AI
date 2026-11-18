import hashlib
import json
import os
import sys

def compute_sha256(filepath: str) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def generate_manifest(root_dir: str, output_file: str):
    manifest = {}
    print(f"Generating SHA-256 manifest for {root_dir}...")
    for root, _, files in os.walk(root_dir):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, root_dir).replace("\\", "/")
            manifest[rel_path] = compute_sha256(full_path)
    
    with open(output_file, "w", encoding="utf-8") as out:
        json.dump(manifest, out, indent=2)
    print(f"Manifest written to {output_file} ({len(manifest)} files recorded).")

if __name__ == "__main__":
    target_root = sys.argv[1] if len(sys.argv) > 1 else "."
    target_out = sys.argv[2] if len(sys.argv) > 2 else "STEP220_PRE_DEV_MANIFEST_SHA256.json"
    generate_manifest(target_root, target_out)
