from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_PACKAGE_FILES = 20_000
MAX_PACKAGE_UNCOMPRESSED_BYTES = 50 * 1024**3


@dataclass(frozen=True)
class QualificationResult:
    qualified: bool
    implementation_score: float
    evidence_score: float
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    files_verified: int
    package_root: str
    model_card: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON file: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _safe_extract(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        if len(members) > MAX_PACKAGE_FILES:
            raise ValueError("Model package contains too many archive members.")
        total = 0
        for member in members:
            normalized = member.filename.replace("\\", "/")
            target = (destination / normalized).resolve()
            try:
                target.relative_to(destination.resolve())
            except ValueError as exc:
                raise ValueError(f"Unsafe package member: {member.filename}") from exc
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"Symbolic links are not accepted: {member.filename}")
            if not member.is_dir():
                total += int(member.file_size)
                if total > MAX_PACKAGE_UNCOMPRESSED_BYTES:
                    raise ValueError("Model package exceeds the configured uncompressed-size limit.")
        archive.extractall(destination)


def qualify_model_package(package: str | Path, *, require_external_validation: bool = True) -> QualificationResult:
    source = Path(package).expanduser().resolve()
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if source.is_file() and zipfile.is_zipfile(source):
        temporary = tempfile.TemporaryDirectory(prefix="biointel-model-")
        root = Path(temporary.name)
        _safe_extract(source, root)
        children = [path for path in root.iterdir() if path.is_dir()]
        if len(children) == 1 and not (root / "model_card.json").exists():
            root = children[0]
    elif source.is_dir():
        root = source
    else:
        raise ValueError("Model package must be a directory or ZIP archive.")
    try:
        required = {
            "model_card.json": root / "model_card.json",
            "dataset_manifest.json": root / "dataset_manifest.json",
            "metrics.json": root / "metrics.json",
            "FILE_MANIFEST_SHA256.json": root / "FILE_MANIFEST_SHA256.json",
        }
        blockers: list[str] = []
        warnings: list[str] = []
        for name, path in required.items():
            if not path.is_file():
                blockers.append(f"Missing required file: {name}")
        if blockers:
            return QualificationResult(False, 0.0, 0.0, tuple(blockers), (), 0, str(root), {})
        card = _read_json(required["model_card.json"])
        dataset = _read_json(required["dataset_manifest.json"])
        metrics = _read_json(required["metrics.json"])
        manifest = _read_json(required["FILE_MANIFEST_SHA256.json"])
        manifest_rows = manifest.get("files", [])
        if not isinstance(manifest_rows, list) or not manifest_rows:
            blockers.append("File manifest contains no verifiable file rows.")
            manifest_rows = []
        verified = 0
        seen: set[str] = set()
        for row in manifest_rows:
            if not isinstance(row, dict):
                blockers.append("File manifest contains a non-object row.")
                continue
            relative = str(row.get("path", "")).replace("\\", "/")
            expected = str(row.get("sha256", "")).lower()
            if not relative or relative in seen:
                blockers.append(f"Duplicate or empty manifest path: {relative or '<empty>'}")
                continue
            seen.add(relative)
            path = (root / relative).resolve()
            try:
                path.relative_to(root.resolve())
            except ValueError:
                blockers.append(f"Unsafe manifest path: {relative}")
                continue
            if not path.is_file():
                blockers.append(f"Manifest file missing: {relative}")
                continue
            if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
                blockers.append(f"Invalid SHA-256 value: {relative}")
                continue
            if _sha256(path).lower() != expected:
                blockers.append(f"Manifest hash mismatch: {relative}")
                continue
            verified += 1
        control_names = set(required) - {"FILE_MANIFEST_SHA256.json"}
        unprotected_controls = sorted(control_names - seen)
        if unprotected_controls:
            blockers.append("Control files not covered by manifest: " + ", ".join(unprotected_controls))
        for field in ("model_name", "model_version", "intended_use", "algorithm", "created_at_utc"):
            if not card.get(field):
                blockers.append(f"Model card field missing: {field}")
        artifact = str(card.get("artifact_path", "")).strip().replace("\\", "/")
        if artifact:
            if artifact not in seen:
                blockers.append("Declared model artifact is not protected by the file manifest.")
        else:
            warnings.append("Model card does not declare artifact_path.")
        if card.get("synthetic_training_data") is True:
            blockers.append("Model is explicitly trained on synthetic data.")
        dataset_hash = str(dataset.get("dataset_sha256", "")).strip().lower()
        if len(dataset_hash) != 64 or any(char not in "0123456789abcdef" for char in dataset_hash):
            blockers.append("Dataset manifest lacks a valid 64-character dataset_sha256.")
        if not dataset.get("license"):
            warnings.append("Dataset licence is not declared.")
        validation = card.get("validation", {}) if isinstance(card.get("validation"), dict) else {}
        if require_external_validation and not validation.get("independent_external"):
            blockers.append("Independent external validation is not documented.")
        if not validation.get("temporal_or_scaffold_split"):
            warnings.append("Temporal/scaffold/protein-cluster generalisation is not documented.")
        if not validation.get("calibration_assessed"):
            warnings.append("Calibration assessment is not documented.")
        if not metrics:
            blockers.append("Metrics file is empty.")
        if not card.get("limitations"):
            warnings.append("Model limitations are not documented.")
        if not card.get("applicability_domain"):
            warnings.append("Applicability domain is not documented.")
        implementation_penalty = 1.2 * len([item for item in blockers if "external validation" not in item.lower()]) + 0.25 * len(warnings)
        implementation_score = max(0.0, min(10.0, 10.0 - implementation_penalty))
        evidence_score = max(0.0, min(10.0, 10.0 - 1.5 * len(blockers) - 0.5 * len(warnings)))
        return QualificationResult(not blockers, round(implementation_score, 2), round(evidence_score, 2), tuple(blockers), tuple(warnings), verified, str(root), card)
    finally:
        if temporary is not None:
            temporary.cleanup()
