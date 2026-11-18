from __future__ import annotations

import hashlib
import io
import json
import tempfile
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from .core import (
    ALLOWED_USES,
    PROHIBITED_USES,
    SYNTHETIC_BANNER_TEXT,
    SYNTHETIC_WATERMARK,
    SyntheticGeneratedDataset,
    SyntheticGenerationCancelled,
)

CancelCheck = Callable[[], bool] | None


def _cancelled(check: CancelCheck) -> None:
    if check is not None and check():
        raise SyntheticGenerationCancelled("Synthetic package export was cancelled.")


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def synthetic_export_metadata() -> dict[str, Any]:
    return {
        "watermark": SYNTHETIC_WATERMARK,
        "is_synthetic": True,
        "data_origin": "synthetic",
        "allowed_use": list(ALLOWED_USES),
        "prohibited_use": list(PROHIBITED_USES),
    }


def synthetic_json_export(payload: Mapping[str, Any]) -> bytes:
    return _json_bytes({**synthetic_export_metadata(), "payload": dict(payload)})


def synthetic_csv_export(frame: pd.DataFrame) -> bytes:
    output = io.StringIO()
    output.write(f"# {SYNTHETIC_WATERMARK}\n")
    prepared = frame.copy()
    prepared["data_origin"] = "synthetic"
    prepared["is_synthetic"] = True
    prepared["synthetic_notice"] = SYNTHETIC_WATERMARK
    prepared.to_csv(output, index=False)
    return output.getvalue().encode("utf-8")


def write_synthetic_package_directory(dataset: SyntheticGeneratedDataset, destination: str | Path, *, cancel_check: CancelCheck = None) -> Path:
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    file_hashes: dict[str, str] = {}
    for name, frame in sorted(dataset.tables.items()):
        _cancelled(cancel_check)
        safe_name = Path(name).name
        target = root / safe_name
        prepared = pd.DataFrame(frame).copy()
        prepared["data_origin"] = "synthetic"
        prepared["is_synthetic"] = True
        prepared["synthetic_notice"] = SYNTHETIC_WATERMARK
        with target.open("w", encoding="utf-8", newline="") as handle:
            handle.write(f"# {SYNTHETIC_WATERMARK}\n")
            prepared.to_csv(handle, index=False, chunksize=5000)
        file_hashes[safe_name] = _sha256(target)
    required_payloads = {
        "generation_parameters.json": {**synthetic_export_metadata(), **dataset.config.to_dict()},
        "expected_ground_truth.json": {**synthetic_export_metadata(), "restricted_to_demo_developer_view": True, "records": [item.to_dict() for item in dataset.ground_truth]},
        "expected_qc_findings.json": {**synthetic_export_metadata(), "findings": dataset.expected_qc_findings},
        "expected_recommendations.json": {**synthetic_export_metadata(), "recommendations": dataset.expected_recommendations},
    }
    for name, payload in required_payloads.items():
        _cancelled(cancel_check)
        target = root / name
        target.write_bytes(_json_bytes(payload))
        file_hashes[name] = _sha256(target)
    readme = f"""# SYNTHETIC DEMO DATA

{SYNTHETIC_BANNER_TEXT}

- Module: {dataset.config.module_id}
- Scenario: {dataset.config.scenario}
- Random seed: {dataset.config.seed}
- Dataset size: {dataset.config.size_preset}
- Allowed use: {', '.join(ALLOWED_USES)}
- Prohibited use: {', '.join(PROHIBITED_USES)}

The files use neutral synthetic identifiers and contain no copied user rows, patient identifiers, real citations, clinical claims or proprietary records.
"""
    readme_path = root / "README_SYNTHETIC_DATA.md"
    readme_path.write_text(readme, encoding="utf-8")
    file_hashes[readme_path.name] = _sha256(readme_path)
    manifest = dataset.manifest.to_dict()
    manifest.update(synthetic_export_metadata())
    manifest["file_hashes"] = dict(sorted(file_hashes.items()))
    manifest["required_package_files"] = [
        "synthetic_manifest.json", "README_SYNTHETIC_DATA.md",
        "generation_parameters.json", "expected_ground_truth.json",
        "expected_qc_findings.json", "expected_recommendations.json",
    ]
    manifest_path = root / "synthetic_manifest.json"
    manifest_path.write_bytes(_json_bytes(manifest))
    return root


def build_synthetic_dataset_package(dataset: SyntheticGeneratedDataset, *, cancel_check: CancelCheck = None) -> bytes:
    with tempfile.TemporaryDirectory(prefix="biointel-synthetic-") as temporary:
        root = write_synthetic_package_directory(dataset, temporary, cancel_check=cancel_check)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for path in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
                _cancelled(cancel_check)
                if path.is_file():
                    archive.write(path, path.name)
        content = output.getvalue()
    with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("Synthetic package contains duplicate paths.")
        if archive.testzip() is not None:
            raise RuntimeError("Synthetic package failed CRC verification.")
        required = {
            "synthetic_manifest.json", "README_SYNTHETIC_DATA.md",
            "generation_parameters.json", "expected_ground_truth.json",
            "expected_qc_findings.json", "expected_recommendations.json",
        }
        if not required.issubset(names):
            raise RuntimeError("Synthetic package is missing required manifest files.")
    return content


__all__ = [
    "build_synthetic_dataset_package",
    "synthetic_csv_export",
    "synthetic_export_metadata",
    "synthetic_json_export",
    "write_synthetic_package_directory",
]
