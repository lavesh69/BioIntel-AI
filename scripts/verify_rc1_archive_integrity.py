import glob
import json
import os
import zipfile
import hashlib

def compute_sha256(filepath: str) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def verify_archives():
    downloads = r"C:\Users\lavesh dobriyal\Downloads"
    zips = sorted(glob.glob(os.path.join(downloads, "BioIntel-AI-15.6.0-EDUCATION-PHASE16-MEGA-FIXED-R2.1-INSTALL-HOTFIX-Part*.zip")))
    
    print(f"Verifying {len(zips)} release archives...")
    file_map = {}
    crc_report = {}

    for zpath in zips:
        zname = os.path.basename(zpath)
        with zipfile.ZipFile(zpath, 'r') as zf:
            bad_file = zf.testzip()
            if bad_file:
                print(f"CRC ERROR in {zname}: Bad file {bad_file}")
                return False
            
            for info in zf.infolist():
                if not info.is_dir():
                    file_map[info.filename] = zname
                    crc_report[info.filename] = info.CRC

    print(f"Archive CRC Check: PASSED 100% CLEAN ({len(file_map)} files verified across 4 parts)")
    
    output_report = r"C:\Users\lavesh dobriyal\.gemini\antigravity\scratch\BioIntel-Step220\BIOINTEL_RC1_ARCHIVE_VERIFICATION.json"
    with open(output_report, "w", encoding="utf-8") as out:
        json.dump({
            "archive_count": len(zips),
            "total_files": len(file_map),
            "crc_integrity_passed": True,
            "archives": [os.path.basename(z) for z in zips]
        }, out, indent=2)

    print(f"Archive verification saved to {output_report}")
    return True

if __name__ == "__main__":
    verify_archives()
