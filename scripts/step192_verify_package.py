from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("parts", nargs=4, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = []
    all_valid = True
    for index, path in enumerate(args.parts, 1):
        item = {"path": str(path), "exists": path.is_file(), "part": index}
        if not path.is_file():
            item.update({"valid": False, "error": "missing"})
            all_valid = False
            results.append(item)
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                corrupt = archive.testzip()
                names = archive.namelist()
                marker = f"BioIntel-AI/.release_parts/step192_part{index}.ok"
                unsafe = [name for name in names if not safe(name)]
                valid = corrupt is None and marker in names and not unsafe
                item.update({"valid": valid, "sha256": sha256(path), "size_bytes": path.stat().st_size, "entries": len(names), "corrupt_entry": corrupt, "marker_present": marker in names, "unsafe_paths": unsafe})
                all_valid = all_valid and valid
        except zipfile.BadZipFile as exc:
            item.update({"valid": False, "error": str(exc)})
            all_valid = False
        results.append(item)
    payload = {"schema": "biointel.step192.external-package-verification.v1", "passed": all_valid, "parts": results}
    text = json.dumps(payload, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if all_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
