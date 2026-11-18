from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path



def _normalize_root(value: str | Path) -> Path:
    raw = str(value).strip().strip('\"').strip("'")
    if not raw or raw == ".":
        return Path.cwd().resolve()
    return Path(raw).expanduser().resolve()

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(root: Path) -> dict[str, object]:
    wheelhouse = root / "wheelhouse" / "windows-cp311-x64"
    manifest_path = wheelhouse / "MANIFEST_SHA256.txt"
    metadata_path = wheelhouse / "WHEELHOUSE_METADATA.json"
    lock_path = root / "requirements-windows-cp311-offline.lock"
    missing_required = [
        str(path.relative_to(root))
        for path in (wheelhouse, manifest_path, metadata_path, lock_path)
        if not path.exists()
    ]
    if missing_required:
        return {"valid": False, "missing_required": missing_required, "wheel_count": 0}

    expected: dict[str, str] = {}
    malformed_manifest: list[str] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            digest, filename = line.split(None, 1)
        except ValueError:
            malformed_manifest.append(line)
            continue
        expected[filename.strip()] = digest.strip().lower()

    actual_wheels = {path.name: path for path in wheelhouse.glob("*.whl")}
    missing_wheels = sorted(set(expected) - set(actual_wheels))
    unexpected_wheels = sorted(set(actual_wheels) - set(expected))
    hash_mismatches = sorted(
        name
        for name, expected_hash in expected.items()
        if name in actual_wheels and sha256(actual_wheels[name]) != expected_hash
    )
    corrupt_wheels: list[str] = []
    for name, path in actual_wheels.items():
        try:
            with zipfile.ZipFile(path) as archive:
                if archive.testzip() is not None:
                    corrupt_wheels.append(name)
        except zipfile.BadZipFile:
            corrupt_wheels.append(name)

    compatibility_errors: list[str] = []
    setuptools_name = "setuptools-80.9.0-py3-none-any.whl"
    setuptools_path = actual_wheels.get(setuptools_name)
    if setuptools_path is None:
        compatibility_errors.append(f"missing {setuptools_name}")
    else:
        try:
            with zipfile.ZipFile(setuptools_path) as archive:
                if "pkg_resources/__init__.py" not in archive.namelist():
                    compatibility_errors.append(f"{setuptools_name} does not provide pkg_resources")
        except zipfile.BadZipFile:
            compatibility_errors.append(f"{setuptools_name} is not a readable wheel")
    if any(name.startswith("setuptools-83.") for name in actual_wheels):
        compatibility_errors.append("setuptools 83.x removes pkg_resources and is incompatible with ont-fast5-api 4.1.3")
    ont_name = "ont_fast5_api-4.1.3-py3-none-any.whl"
    ont_path = actual_wheels.get(ont_name)
    if ont_path is None:
        compatibility_errors.append(f"missing {ont_name}")
    else:
        try:
            with zipfile.ZipFile(ont_path) as archive:
                source = archive.read("ont_fast5_api/compression_settings.py").decode("utf-8", errors="replace")
            if "import pkg_resources" not in source:
                compatibility_errors.append(f"unexpected {ont_name} runtime contract")
        except (KeyError, zipfile.BadZipFile):
            compatibility_errors.append(f"{ont_name} compression settings are unreadable")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata_count = int(metadata.get("wheel_count", -1))
    lock_rows = [
        row.strip()
        for row in lock_path.read_text(encoding="utf-8").splitlines()
        if row.strip() and not row.lstrip().startswith("#")
    ]
    unhashed_lock_rows = [row for row in lock_rows if " --hash=sha256:" not in row]
    valid = not any(
        (
            missing_required,
            malformed_manifest,
            missing_wheels,
            unexpected_wheels,
            hash_mismatches,
            corrupt_wheels,
            unhashed_lock_rows,
            compatibility_errors,
        )
    ) and metadata_count == len(actual_wheels) == len(lock_rows)
    return {
        "valid": valid,
        "wheel_count": len(actual_wheels),
        "metadata_wheel_count": metadata_count,
        "lock_rows": len(lock_rows),
        "total_size_bytes": sum(path.stat().st_size for path in actual_wheels.values()),
        "missing_required": missing_required,
        "malformed_manifest": malformed_manifest,
        "missing_wheels": missing_wheels,
        "unexpected_wheels": unexpected_wheels,
        "hash_mismatches": hash_mismatches,
        "corrupt_wheels": corrupt_wheels,
        "unhashed_lock_rows": unhashed_lock_rows,
        "runtime_compatibility": {
            "setuptools": setuptools_name,
            "legacy_consumer": ont_name,
            "pkg_resources_required": True,
            "errors": compatibility_errors,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the bundled Windows CPython 3.11 wheelhouse."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = verify(_normalize_root(args.root))
    payload = json.dumps(result, indent=2)
    print(payload)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
