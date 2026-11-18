from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

REQUIRED_DTI_SPLITS = (
    "cold_drug",
    "cold_target",
    "cold_drug_and_target",
    "scaffold",
    "protein_sequence_cluster",
    "temporal",
    "independent_external",
    "prospective",
)


@dataclass(frozen=True)
class SplitValidationEvidence:
    split: str
    dataset_sha256: str
    train_rows: int
    test_rows: int
    drug_overlap: int
    target_overlap: int
    scaffold_overlap: int | None
    temporal_order_valid: bool | None
    metrics: dict[str, float]
    confidence_intervals: dict[str, Any]
    calibration: dict[str, float]
    reviewer: str
    signed_manifest: bool
    passed: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class DTIValidationMatrix:
    model_sha256: str
    generated_at_utc: str
    required_splits: tuple[str, ...]
    evidence: tuple[SplitValidationEvidence, ...]
    coverage_fraction: float
    release_eligible: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _split_blockers(split: str, payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if len(str(payload.get("dataset_sha256", ""))) != 64:
        blockers.append("Immutable validation dataset SHA-256 is missing.")
    if int(payload.get("test_rows", 0)) < 100:
        blockers.append("Validation split has fewer than 100 test observations.")
    if split in {"cold_drug", "cold_drug_and_target", "scaffold"} and int(payload.get("drug_overlap", 0)) != 0:
        blockers.append("Drug leakage detected between training and test partitions.")
    if split in {"cold_target", "cold_drug_and_target", "protein_sequence_cluster"} and int(payload.get("target_overlap", 0)) != 0:
        blockers.append("Target leakage detected between training and test partitions.")
    if split == "scaffold" and int(payload.get("scaffold_overlap", -1)) != 0:
        blockers.append("Molecular scaffold leakage detected.")
    if split == "temporal" and payload.get("temporal_order_valid") is not True:
        blockers.append("Temporal ordering is absent or invalid.")
    metrics = payload.get("metrics") or {}
    task = str(payload.get("task", "classification")).lower()
    if task == "classification":
        if float(metrics.get("roc_auc", 0.0)) < 0.70:
            blockers.append("ROC-AUC is below 0.70.")
        if float(metrics.get("balanced_accuracy", 0.0)) < 0.65:
            blockers.append("Balanced accuracy is below 0.65.")
    else:
        if float(metrics.get("r2", -1.0)) <= 0.0:
            blockers.append("R² does not beat the mean baseline.")
        if float(metrics.get("pearson", 0.0)) < 0.30:
            blockers.append("Pearson correlation is below 0.30.")
    if not payload.get("confidence_intervals"):
        blockers.append("Confidence intervals are missing.")
    if split in {"independent_external", "prospective"}:
        if not str(payload.get("reviewer", "")).strip():
            blockers.append("Independent reviewer identity is missing.")
        if payload.get("signed_manifest") is not True:
            blockers.append("Signed evidence manifest is missing.")
    return blockers


def build_validation_matrix(
    model_path: str | Path,
    evidence: Iterable[dict[str, Any]],
) -> DTIValidationMatrix:
    model_sha = _sha256(model_path)
    records: list[SplitValidationEvidence] = []
    supplied: set[str] = set()
    global_blockers: list[str] = []
    for payload in evidence:
        split = str(payload.get("split", "")).strip().lower()
        if split not in REQUIRED_DTI_SPLITS:
            global_blockers.append(f"Unsupported DTI split evidence: {split or '<empty>'}.")
            continue
        supplied.add(split)
        blockers = _split_blockers(split, payload)
        records.append(
            SplitValidationEvidence(
                split=split,
                dataset_sha256=str(payload.get("dataset_sha256", "")),
                train_rows=int(payload.get("train_rows", 0)),
                test_rows=int(payload.get("test_rows", 0)),
                drug_overlap=int(payload.get("drug_overlap", 0)),
                target_overlap=int(payload.get("target_overlap", 0)),
                scaffold_overlap=(None if payload.get("scaffold_overlap") is None else int(payload["scaffold_overlap"])),
                temporal_order_valid=(None if payload.get("temporal_order_valid") is None else bool(payload["temporal_order_valid"])),
                metrics={str(k): float(v) for k, v in (payload.get("metrics") or {}).items()},
                confidence_intervals=dict(payload.get("confidence_intervals") or {}),
                calibration={str(k): float(v) for k, v in (payload.get("calibration") or {}).items()},
                reviewer=str(payload.get("reviewer", "")),
                signed_manifest=bool(payload.get("signed_manifest", False)),
                passed=not blockers,
                blockers=tuple(blockers),
            )
        )
    missing = [split for split in REQUIRED_DTI_SPLITS if split not in supplied]
    global_blockers.extend(f"Required validation evidence missing: {split}." for split in missing)
    failed = [record.split for record in records if not record.passed]
    global_blockers.extend(f"Validation split failed release policy: {split}." for split in failed)
    coverage = len(supplied.intersection(REQUIRED_DTI_SPLITS)) / len(REQUIRED_DTI_SPLITS)
    return DTIValidationMatrix(
        model_sha256=model_sha,
        generated_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        required_splits=REQUIRED_DTI_SPLITS,
        evidence=tuple(records),
        coverage_fraction=round(coverage, 4),
        release_eligible=not global_blockers,
        blockers=tuple(global_blockers),
    )


def save_validation_matrix(matrix: DTIValidationMatrix, path: str | Path) -> Path:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(matrix.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return destination
