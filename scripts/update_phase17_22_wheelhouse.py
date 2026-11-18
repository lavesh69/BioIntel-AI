from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEELHOUSE = ROOT / "wheelhouse" / "windows-cp311-x64"
METADATA = WHEELHOUSE / "WHEELHOUSE_METADATA.json"
MANIFEST = WHEELHOUSE / "MANIFEST_SHA256.txt"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    payload = json.loads(METADATA.read_text(encoding="utf-8"))
    existing = {
        item["filename"]: item
        for item in payload.get("packages", [])
        if isinstance(item, dict) and item.get("filename")
    }
    wheel = WHEELHOUSE / "imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl"
    existing[wheel.name] = {
        "name": "imageio-ffmpeg",
        "canonical_name": "imageio-ffmpeg",
        "version": "0.6.0",
        "filename": wheel.name,
        "size_bytes": wheel.stat().st_size,
        "sha256": sha256(wheel),
    }
    wheels = sorted(WHEELHOUSE.glob("*.whl"), key=lambda path: path.name.casefold())
    payload["packages"] = sorted(
        existing.values(),
        key=lambda item: str(item["filename"]).casefold(),
    )
    payload["wheel_count"] = len(wheels)
    payload["total_size_bytes"] = sum(path.stat().st_size for path in wheels)
    payload["education_phase17_22"] = {
        "bundled_media_runtime": "imageio-ffmpeg==0.6.0",
        "purpose": "Local Windows lecture probing and media processing without a PATH dependency.",
    }
    METADATA.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    MANIFEST.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in wheels),
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
