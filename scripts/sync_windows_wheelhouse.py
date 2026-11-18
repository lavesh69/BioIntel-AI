from __future__ import annotations

import hashlib
import json
import zipfile
from email.parser import Parser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEELHOUSE = ROOT / "wheelhouse" / "windows-cp311-x64"
METADATA = WHEELHOUSE / "WHEELHOUSE_METADATA.json"
MANIFEST = WHEELHOUSE / "MANIFEST_SHA256.txt"
LOCK = ROOT / "requirements-windows-cp311-offline.lock"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_record(wheel: Path) -> dict[str, object]:
    with zipfile.ZipFile(wheel) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = Parser().parsestr(
            archive.read(metadata_name).decode("utf-8", errors="strict")
        )
    name = str(metadata["Name"])
    return {
        "name": name,
        "canonical_name": name.lower().replace("_", "-").replace(".", "-"),
        "version": str(metadata["Version"]),
        "filename": wheel.name,
        "size_bytes": wheel.stat().st_size,
        "sha256": sha256(wheel),
    }


def main() -> int:
    payload = json.loads(METADATA.read_text(encoding="utf-8"))
    wheels = sorted(WHEELHOUSE.glob("*.whl"), key=lambda path: path.name.casefold())
    packages = [package_record(wheel) for wheel in wheels]
    payload["packages"] = packages
    payload["wheel_count"] = len(wheels)
    payload["total_size_bytes"] = sum(path.stat().st_size for path in wheels)
    payload["education_selective_mega_r9"] = {
        "development_tools": [
            "black==25.12.0",
            "pytest==8.4.2",
            "ruff==0.16.1",
        ],
        "purpose": "Complete the offline requirements.txt installation contract.",
    }
    payload["education_full_local_upgrade_r15"] = {
        "speech_to_text": "faster-whisper==1.2.1",
        "inference_runtime": "ctranslate2==4.8.1",
        "model": "Systran/faster-whisper-tiny",
        "model_revision": "d90ca5fe260221311c53c58e660288d3deb8d356",
        "model_manifest_sha256": "2507446bda93db691ec9afda4afbdd90c193ec9e55a4c6358894117b147b9b5c",
        "runtime_contract": "CPU INT8, local files only, no credentials or runtime network",
        "purpose": "Real multilingual Education lecture transcription with educator review.",
    }
    METADATA.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    MANIFEST.write_text(
        "".join(f"{item['sha256']}  {item['filename']}\n" for item in packages),
        encoding="utf-8",
    )
    LOCK.write_text(
        "# Complete offline Windows CPython 3.11 x64 wheelhouse lock.\n"
        "# Generated from wheel metadata; every row is hash-pinned.\n"
        + "".join(
            f"{item['name']}=={item['version']} --hash=sha256:{item['sha256']}\n"
            for item in packages
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "wheel_count": len(wheels),
                "total_size_bytes": payload["total_size_bytes"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
