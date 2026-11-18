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

def verify_mobile(root_dir: str, backup_dir: str) -> bool:
    mobile_rel = "platform/mobile"
    curr_mobile = os.path.join(root_dir, mobile_rel)
    back_mobile = os.path.join(backup_dir, mobile_rel)

    if not os.path.exists(curr_mobile) or not os.path.exists(back_mobile):
        print("Mobile directory missing in source or backup.")
        return False

    diffs = []
    for r, _, files in os.walk(back_mobile):
        for f in files:
            b_path = os.path.join(r, f)
            rel = os.path.relpath(b_path, backup_dir).replace("\\", "/")
            c_path = os.path.join(root_dir, rel)

            if not os.path.exists(c_path):
                diffs.append((rel, "MISSING_IN_CURRENT"))
                continue
            
            if compute_sha256(b_path) != compute_sha256(c_path):
                diffs.append((rel, "HASH_MISMATCH"))

    if diffs:
        print(f"FAILED: {len(diffs)} mobile files modified or missing!")
        for rel, reason in diffs[:10]:
            print(f"  {reason}: {rel}")
        return False
    else:
        print("SUCCESS: All mobile source files are 100% byte-for-byte identical to original backup.")
        return True

if __name__ == "__main__":
    r_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    b_dir = sys.argv[2] if len(sys.argv) > 2 else "../BioIntel-Step220-BACKUP"
    success = verify_mobile(r_dir, b_dir)
    sys.exit(0 if success else 1)
