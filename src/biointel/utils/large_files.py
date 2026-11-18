from __future__ import annotations

from biointel.runtime_paths import runtime_report_path

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

DEFAULT_ALLOWED_EXTENSIONS = {
    ".aln",
    ".bam",
    ".bcf",
    ".bed",
    ".cif",
    ".csv",
    ".fa",
    ".fasta",
    ".fastq",
    ".fq",
    ".gz",
    ".h5",
    ".h5ad",
    ".loom",
    ".mmcif",
    ".mzml",
    ".parquet",
    ".pdb",
    ".sam",
    ".tsv",
    ".txt",
    ".vcf",
    ".xlsx",
    ".zip",
}


@dataclass(frozen=True)
class LargeFileReference:
    source_path: str
    name: str
    extension: str
    size_bytes: int
    modified_at: str
    registered_at: str
    sha256: str | None
    label: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _sha256(path: Path, *, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def profile_local_file(
    source: str | os.PathLike[str],
    *,
    label: str = "",
    compute_hash: bool = False,
    allowed_extensions: Iterable[str] | None = None,
    max_size_bytes: int = 2 * 1024**4,
) -> LargeFileReference:
    path = Path(source).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("The selected path is not a regular file.")
    extension = path.suffix.lower()
    allowed = {
        value.lower() if str(value).startswith(".") else f".{str(value).lower()}"
        for value in (allowed_extensions or DEFAULT_ALLOWED_EXTENSIONS)
    }
    if extension not in allowed:
        raise ValueError(
            f"Unsupported file extension {extension or '(none)'}. "
            f"Accepted extensions: {', '.join(sorted(allowed))}"
        )
    stat = path.stat()
    if stat.st_size <= 0:
        raise ValueError("The selected file is empty.")
    if stat.st_size > int(max_size_bytes):
        raise ValueError(
            f"The selected file exceeds the configured local-reference limit "
            f"of {max_size_bytes / 1024**4:.1f} TiB."
        )
    return LargeFileReference(
        source_path=str(path),
        name=path.name,
        extension=extension,
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        registered_at=datetime.now(UTC).isoformat(),
        sha256=_sha256(path) if compute_hash else None,
        label=str(label).strip(),
    )


def registry_path(root: Path) -> Path:
    return runtime_report_path(root, "large_file_registry.json")


def load_registry(root: Path) -> list[dict[str, object]]:
    path = registry_path(root)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("files", []) if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def register_local_file(
    root: Path,
    source: str | os.PathLike[str],
    *,
    label: str = "",
    compute_hash: bool = False,
    allowed_extensions: Iterable[str] | None = None,
) -> LargeFileReference:
    reference = profile_local_file(
        source,
        label=label,
        compute_hash=compute_hash,
        allowed_extensions=allowed_extensions,
    )
    rows = load_registry(root)
    rows = [row for row in rows if row.get("source_path") != reference.source_path]
    rows.append(reference.to_dict())
    rows.sort(key=lambda row: str(row.get("registered_at", "")), reverse=True)
    target = registry_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "updated_at": datetime.now(UTC).isoformat(),
        "files": rows,
    }
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=target.parent, delete=False, suffix=".tmp"
    ) as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(target)
    return reference


def remove_registered_paths(root: Path, paths: Iterable[str]) -> int:
    remove = {str(Path(path)) for path in paths}
    rows = load_registry(root)
    kept = [row for row in rows if str(row.get("source_path", "")) not in remove]
    removed = len(rows) - len(kept)
    target = registry_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "updated_at": datetime.now(UTC).isoformat(),
        "files": kept,
    }
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return removed
