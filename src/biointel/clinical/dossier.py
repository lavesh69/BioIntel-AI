from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .readiness import evaluate_clinical_pharma_readiness
from .registry import ClinicalValidationRegistry


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build_validation_dossier(
    registry: ClinicalValidationRegistry, program_id: str, output: str | Path
) -> Path:
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    report = evaluate_clinical_pharma_readiness(registry, program_id).to_dict()
    tables = registry.export_tables(program_id)
    snapshot = registry.snapshot(program_id)
    audit = registry.verify_audit_chain().__dict__
    files: dict[str, bytes] = {
        "readiness_report.json": json.dumps(report, indent=2, sort_keys=True).encode(),
        "audit_chain_verification.json": json.dumps(audit, indent=2, sort_keys=True).encode(),
        "BOUNDARY.txt": (
            "This dossier is an evidence package, not a clinical certification, GxP certificate, "
            "regulatory approval, laboratory accreditation or authorization for patient-care use.\n"
        ).encode(),
    }
    for name, rows in tables.items():
        files[f"tables/{name}.json"] = json.dumps(rows, indent=2, sort_keys=True).encode()
    external_artifact_integrity: list[dict[str, Any]] = []
    for item in snapshot.get("external_artifacts", []):
        integrity = registry.verify_external_artifact_integrity(item["artifact_id"])
        external_artifact_integrity.append(integrity)
        if not integrity["valid"]:
            continue
        source = registry.path.parent / item["artifact_path"]
        suffix = Path(item["original_filename"]).suffix.lower() or ".bin"
        files[f"external_artifacts/{item['artifact_id']}{suffix}"] = source.read_bytes()
    files["external_artifact_integrity.json"] = json.dumps(
        external_artifact_integrity, indent=2, sort_keys=True
    ).encode()
    manifest = {
        "schema": "biointel.clinical-validation-dossier.v1",
        "program_id": program_id,
        "generated_utc": datetime.now(UTC).isoformat(),
        "release_eligible": report["release_eligible"],
        "external_artifacts": len(snapshot.get("external_artifacts", [])),
        "files": [
            {"path": name, "sha256": _sha(payload), "size": len(payload)}
            for name, payload in sorted(files.items())
        ],
    }
    files["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, payload in sorted(files.items()):
            archive.writestr(name, payload)
    return target


def verify_validation_dossier(path: str | Path) -> dict[str, Any]:
    target = Path(path).resolve()
    failures: list[str] = []
    checked = 0
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        duplicate = sorted({name for name in names if names.count(name) > 1})
        unsafe = [
            name
            for name in names
            if name.startswith(("/", "\\")) or ".." in PurePosixPath(name).parts
        ]
        bad_member = archive.testzip()
        if "manifest.json" not in names:
            failures.append("missing manifest.json")
            manifest: dict[str, Any] = {"files": []}
        else:
            manifest = json.loads(archive.read("manifest.json"))
        for item in manifest.get("files", []):
            name = str(item["path"])
            if name not in names:
                failures.append(f"missing:{name}")
                continue
            payload = archive.read(name)
            if len(payload) != int(item["size"]):
                failures.append(f"size:{name}")
                continue
            if _sha(payload) != str(item["sha256"]):
                failures.append(f"digest:{name}")
                continue
            checked += 1
    return {
        "valid": not duplicate and not unsafe and bad_member is None and not failures,
        "checked_files": checked,
        "duplicate_members": duplicate,
        "unsafe_members": unsafe,
        "bad_member": bad_member,
        "failures": failures,
        "sha256": _sha(target.read_bytes()),
        "size_bytes": target.stat().st_size,
    }
