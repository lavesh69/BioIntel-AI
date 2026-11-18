from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import pandas as pd

from .models import PlatformConflictError, PlatformValidationError, new_id, utc_now
from .storage import DiscoveryPlatformStore

ProgressCallback = Callable[[int, int], None]
CancellationCallback = Callable[[], bool]

FORMAT_SUFFIXES = {
    ".fastq.gz": "FASTQ", ".fq.gz": "FASTQ", ".fasta.gz": "FASTA", ".fa.gz": "FASTA",
    ".vcf.gz": "VCF", ".nii.gz": "NIfTI", ".fastq": "FASTQ", ".fq": "FASTQ",
    ".fasta": "FASTA", ".fa": "FASTA", ".fna": "FASTA", ".faa": "FASTA",
    ".bam": "BAM", ".cram": "CRAM", ".sam": "SAM", ".vcf": "VCF", ".bcf": "BCF",
    ".bed": "BED", ".gtf": "GTF", ".gff": "GFF", ".gff3": "GFF",
    ".h5ad": "h5ad", ".loom": "Loom", ".mtx": "10x MTX", ".h5": "HDF5",
    ".mzml": "mzML", ".mzxml": "mzXML", ".mzid": "mzIdentML", ".mzidentml": "mzIdentML",
    ".dcm": "DICOM", ".dicom": "DICOM", ".nii": "NIfTI", ".ome.tiff": "OME-TIFF",
    ".ome.tif": "OME-TIFF", ".tiff": "TIFF", ".tif": "TIFF", ".svs": "SVS",
    ".csv": "CSV", ".tsv": "TSV", ".xlsx": "XLSX", ".xls": "XLSX",
    ".json": "JSON", ".jsonl": "JSONL", ".parquet": "Parquet", ".hdf5": "HDF5",
    ".zip": "ZIP",
}

TEXT_FORMATS = {
    "FASTQ", "FASTA", "SAM", "VCF", "BED", "GTF", "GFF", "10x MTX",
    "mzML", "mzXML", "mzIdentML", "CSV", "TSV", "JSON", "JSONL",
}


class IngestionCancelled(RuntimeError):
    pass


def detect_format(path: str | Path) -> str:
    source = Path(path)
    lower = source.name.lower()
    for suffix in sorted(FORMAT_SUFFIXES, key=len, reverse=True):
        if lower.endswith(suffix):
            return FORMAT_SUFFIXES[suffix]
    with source.open("rb") as handle:
        header = handle.read(512)
    if header.startswith(b"BAM\x01"):
        return "BAM"
    if header.startswith(b"CRAM"):
        return "CRAM"
    if header.startswith(b"PK\x03\x04"):
        return "ZIP"
    if header.startswith(b"\x89HDF\r\n\x1a\n"):
        return "HDF5"
    if header[:2] in {b"II", b"MM"}:
        return "TIFF"
    if len(header) > 132 and header[128:132] == b"DICM":
        return "DICOM"
    text = header.decode("utf-8", errors="ignore").lstrip()
    if text.startswith(">"):
        return "FASTA"
    if text.startswith("##fileformat=VCF"):
        return "VCF"
    if text.startswith("{") or text.startswith("["):
        return "JSON"
    if text.startswith("<?xml") and "<mzML" in text:
        return "mzML"
    raise PlatformValidationError(f"Unsupported or unrecognized scientific file format: {source.name}")


def _check_cancel(cancelled: CancellationCallback | None) -> None:
    if cancelled and cancelled():
        raise IngestionCancelled("File ingestion was cancelled")


def stream_sha256(
    path: str | Path,
    *,
    chunk_size: int = 1024 * 1024,
    cancelled: CancellationCallback | None = None,
    progress: ProgressCallback | None = None,
) -> str:
    source = Path(path)
    total = source.stat().st_size
    processed = 0
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        while chunk := handle.read(max(64 * 1024, int(chunk_size))):
            _check_cancel(cancelled)
            digest.update(chunk)
            processed += len(chunk)
            if progress:
                progress(processed, total)
    return digest.hexdigest()


def _optional_import_error(package: str, purpose: str, exc: ImportError) -> dict[str, Any]:
    return {
        "status": "Dependency missing",
        "dependency": package,
        "purpose": purpose,
        "detail": str(exc),
        "usable_partial_result": True,
    }


def validate_file(
    path: str | Path,
    *,
    detected_format: str | None = None,
    cancelled: CancellationCallback | None = None,
) -> dict[str, Any]:
    source = Path(path).resolve()
    if not source.is_file():
        raise PlatformValidationError(f"Input file was not found: {source}")
    if source.stat().st_size == 0:
        raise PlatformValidationError("Input file is empty")
    fmt = detected_format or detect_format(source)
    warnings: list[str] = []
    metadata: dict[str, Any] = {}
    status = "Valid"
    try:
        if fmt == "ZIP" or (fmt == "XLSX" and source.suffix.lower() == ".xlsx"):
            with zipfile.ZipFile(source) as archive:
                bad = archive.testzip()
                if bad:
                    raise PlatformValidationError(f"Archive member failed CRC: {bad}")
                unsafe = [
                    item.filename
                    for item in archive.infolist()
                    if Path(item.filename).is_absolute() or ".." in Path(item.filename).parts
                ]
                if unsafe:
                    raise PlatformValidationError(
                        "Archive contains unsafe paths: " + ", ".join(unsafe[:5])
                    )
                metadata["archive_members"] = len(archive.infolist())
        elif source.name.lower().endswith(".gz"):
            with gzip.open(source, "rb") as handle:
                while handle.read(1024 * 1024):
                    _check_cancel(cancelled)
        elif fmt in {"HDF5", "h5ad", "Loom"}:
            try:
                import h5py
            except ImportError as exc:
                return {
                    "format": fmt,
                    **_optional_import_error("h5py", f"{fmt} structural validation", exc),
                }
            with h5py.File(source, "r") as handle:
                metadata["root_keys"] = list(handle.keys())[:100]
        elif fmt in {"TIFF", "OME-TIFF", "SVS"}:
            try:
                from PIL import Image
            except ImportError as exc:
                return {
                    "format": fmt,
                    **_optional_import_error("Pillow", f"{fmt} image validation", exc),
                }
            with Image.open(source) as image:
                image.verify()
                metadata["image_format"] = image.format
        elif fmt == "DICOM":
            try:
                import pydicom
            except ImportError as exc:
                return {
                    "format": fmt,
                    **_optional_import_error("pydicom", "DICOM metadata validation", exc),
                }
            dataset = pydicom.dcmread(source, stop_before_pixels=True, force=False)
            metadata["sop_class_uid"] = str(getattr(dataset, "SOPClassUID", ""))
            metadata["modality"] = str(getattr(dataset, "Modality", ""))
        elif fmt == "NIfTI":
            try:
                import nibabel as nib
            except ImportError as exc:
                return {
                    "format": fmt,
                    **_optional_import_error("nibabel", "NIfTI header validation", exc),
                }
            image = nib.load(str(source))
            metadata["shape"] = tuple(int(value) for value in image.shape)
        elif fmt in {"BAM", "CRAM", "BCF"}:
            try:
                import pysam
            except ImportError as exc:
                status = "Dependency missing"
                warnings.append(f"pysam is required for deep {fmt} validation: {exc}")
            else:
                mode = "rb" if fmt == "BAM" else ("rc" if fmt == "CRAM" else "rb")
                opener = pysam.AlignmentFile if fmt in {"BAM", "CRAM"} else pysam.VariantFile
                with opener(str(source), mode) as handle:
                    metadata["references"] = list(getattr(handle, "references", ()))[:100]
        elif fmt == "Parquet":
            try:
                frame = pd.read_parquet(source, columns=[])
                metadata["columns_loaded"] = len(frame.columns)
            except ImportError as exc:
                status = "Dependency missing"
                warnings.append(f"pyarrow or fastparquet is required: {exc}")
        elif fmt in TEXT_FORMATS:
            opener = gzip.open if source.name.lower().endswith(".gz") else open
            with opener(source, "rt", encoding="utf-8", errors="strict") as handle:
                first = handle.readline()
                if not first:
                    raise PlatformValidationError("Text file has no readable records")
                if fmt == "FASTQ" and not first.startswith("@"):
                    raise PlatformValidationError("FASTQ first record must start with @")
                if fmt == "FASTA" and not first.startswith(">"):
                    raise PlatformValidationError("FASTA first record must start with >")
                if fmt == "VCF" and not first.startswith("#"):
                    raise PlatformValidationError("VCF header is missing")
                metadata["first_line_length"] = len(first.rstrip("\r\n"))
    except (OSError, UnicodeError, zipfile.BadZipFile, gzip.BadGzipFile) as exc:
        raise PlatformValidationError(f"{fmt} corruption check failed: {exc}") from exc
    return {
        "format": fmt,
        "status": status,
        "warnings": warnings,
        "metadata": metadata,
        "size_bytes": source.stat().st_size,
    }


def _text_preview(path: Path, maximum_lines: int = 20) -> list[str]:
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    output: list[str] = []
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        for _ in range(maximum_lines):
            line = handle.readline()
            if not line:
                break
            output.append(line.rstrip("\r\n")[:4000])
    return output


def preview_file(
    path: str | Path,
    *,
    detected_format: str | None = None,
    maximum_rows: int = 20,
) -> dict[str, Any]:
    source = Path(path).resolve()
    fmt = detected_format or detect_format(source)
    maximum_rows = max(1, min(int(maximum_rows), 100))
    result: dict[str, Any] = {"format": fmt, "name": source.name, "rows": []}
    if fmt in {"CSV", "TSV"}:
        separator = "," if fmt == "CSV" else "\t"
        frame = pd.read_csv(source, sep=separator, nrows=maximum_rows)
        result.update(
            {
                "columns": [str(value) for value in frame.columns],
                "rows": frame.where(frame.notna(), None).to_dict(orient="records"),
            }
        )
    elif fmt == "XLSX":
        frame = pd.read_excel(source, nrows=maximum_rows)
        result.update(
            {
                "columns": [str(value) for value in frame.columns],
                "rows": frame.where(frame.notna(), None).to_dict(orient="records"),
            }
        )
    elif fmt == "JSONL":
        rows = []
        for line in _text_preview(source, maximum_rows):
            rows.append(json.loads(line))
        result["rows"] = rows
    elif fmt == "JSON":
        if source.stat().st_size > 5 * 1024 * 1024:
            result["notice"] = "JSON preview skipped above 5 MiB; streaming ingestion remains available."
        else:
            payload = json.loads(source.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                result["rows"] = payload[:maximum_rows]
            else:
                result["rows"] = [payload]
    elif fmt == "ZIP":
        with zipfile.ZipFile(source) as archive:
            result["rows"] = [
                {
                    "name": item.filename, "size_bytes": item.file_size,
                    "compressed_bytes": item.compress_size, "crc": f"{item.CRC:08x}",
                }
                for item in archive.infolist()[:maximum_rows]
            ]
    elif fmt in {"HDF5", "h5ad", "Loom"}:
        try:
            import h5py
        except ImportError as exc:
            result["dependency"] = _optional_import_error("h5py", f"{fmt} preview", exc)
        else:
            with h5py.File(source, "r") as handle:
                result["rows"] = [
                    {"key": key, "type": type(handle[key]).__name__}
                    for key in list(handle.keys())[:maximum_rows]
                ]
    elif fmt in TEXT_FORMATS:
        result["rows"] = [{"line": line} for line in _text_preview(source, maximum_rows)]
    else:
        result["notice"] = (
            f"{fmt} metadata is validated without loading raw payloads into memory."
        )
    return result



def validate_tabular_schema(
    path: str | Path,
    *,
    required_columns: Sequence[str] = (),
    delimiter: str | None = None,
) -> dict[str, Any]:
    source = Path(path)
    fmt = detect_format(source)
    if fmt not in {"CSV", "TSV", "XLSX"}:
        return {
            "valid": not required_columns,
            "format": fmt,
            "missing_columns": list(required_columns),
            "notice": "Column schema validation applies to CSV, TSV, and XLSX inputs.",
        }
    if fmt == "XLSX":
        frame = pd.read_excel(source, nrows=100)
    else:
        frame = pd.read_csv(
            source,
            sep=delimiter or ("," if fmt == "CSV" else "\t"),
            nrows=100,
        )
    columns = [str(column) for column in frame.columns]
    duplicate_columns = [
        column for column in dict.fromkeys(columns) if columns.count(column) > 1
    ]
    missing = [column for column in required_columns if column not in columns]
    return {
        "valid": not missing and not duplicate_columns,
        "format": fmt,
        "columns": columns,
        "missing_columns": missing,
        "duplicate_columns": duplicate_columns,
        "preview_rows_checked": len(frame),
    }


def _copy_stream(
    source: Path,
    destination: Path,
    *,
    cancelled: CancellationCallback | None = None,
    progress: ProgressCallback | None = None,
    chunk_size: int = 1024 * 1024,
) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = source.stat().st_size
    processed = 0
    digest = hashlib.sha256()
    temporary = destination.with_suffix(destination.suffix + ".partial")
    try:
        with source.open("rb") as reader, temporary.open("wb") as writer:
            while chunk := reader.read(max(64 * 1024, int(chunk_size))):
                _check_cancel(cancelled)
                writer.write(chunk)
                digest.update(chunk)
                processed += len(chunk)
                if progress:
                    progress(processed, total)
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return digest.hexdigest()


class ScientificFileIngestor:
    def __init__(self, store: DiscoveryPlatformStore):
        self.store = store

    def ingest(
        self,
        dataset_id: str,
        source_path: str | Path,
        *,
        required_columns: Sequence[str] = (),
        allow_cross_dataset_duplicate: bool = False,
        cancelled: CancellationCallback | None = None,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        dataset = self.store.row("datasets", "dataset_id", dataset_id)
        if dataset is None:
            raise KeyError(dataset_id)
        source = Path(source_path).resolve()
        fmt = detect_format(source)
        validation = validate_file(source, detected_format=fmt, cancelled=cancelled)
        schema = validate_tabular_schema(source, required_columns=required_columns)
        if required_columns and not schema["valid"]:
            raise PlatformValidationError(
                "Input schema validation failed; missing columns: "
                + ", ".join(schema.get("missing_columns", []))
            )
        digest = stream_sha256(source, cancelled=cancelled)
        with self.store.connect(read_only=True) as connection:
            duplicates = [
                dict(row)
                for row in connection.execute(
                    "SELECT file_id,dataset_id,stored_path FROM dataset_files WHERE sha256=?",
                    (digest,),
                )
            ]
        same_dataset = next(
            (item for item in duplicates if item["dataset_id"] == dataset_id), None
        )
        if same_dataset:
            return {
                "status": "Duplicate",
                "file_id": same_dataset["file_id"],
                "dataset_id": dataset_id,
                "sha256": digest,
                "duplicate_of": same_dataset,
                "copied": False,
            }
        if duplicates and not allow_cross_dataset_duplicate:
            raise PlatformConflictError(
                "Identical file is already registered in dataset "
                + str(duplicates[0]["dataset_id"])
            )
        file_id = new_id("FILE")
        destination_root = (
            self.store.artifact_root / "datasets" / Path(dataset_id).name / Path(file_id).name
        ).resolve()
        if not destination_root.is_relative_to(self.store.artifact_root):
            raise PlatformValidationError("Dataset storage path escaped the artifact root")
        destination = (destination_root / source.name).resolve()
        if not destination.is_relative_to(destination_root):
            raise PlatformValidationError("Unsafe input filename")
        copied_hash = _copy_stream(
            source, destination, cancelled=cancelled, progress=progress
        )
        if copied_hash != digest:
            destination.unlink(missing_ok=True)
            raise PlatformConflictError("File hash changed during ingestion")
        metadata = {
            "validation": validation,
            "schema": schema,
            "source_path": str(source),
            "duplicate_of": duplicates,
        }
        self.store.insert(
            "dataset_files",
            {
                "file_id": file_id, "dataset_id": dataset_id,
                "original_name": source.name, "stored_path": str(destination),
                "format": fmt, "size_bytes": source.stat().st_size,
                "sha256": digest, "validation_status": validation["status"],
                "metadata_json": metadata, "created_at_utc": utc_now(),
            },
        )
        formats = list(dataset.get("file_formats") or [])
        if fmt not in formats:
            formats.append(fmt)
        self.store.update(
            "datasets", "dataset_id", dataset_id,
            {
                "file_formats_json": formats,
                "processing_status": "Ingested",
                "imported_at_utc": utc_now(),
            },
        )
        self.store.audit(
            "file_ingested", "dataset_file", file_id,
            project_id=dataset["project_id"],
            detail={
                "dataset_id": dataset_id, "format": fmt, "sha256": digest,
                "size_bytes": source.stat().st_size,
                "validation_status": validation["status"],
            },
        )
        return self.store.row("dataset_files", "file_id", file_id) or {}

    def ingest_many(
        self,
        dataset_id: str,
        paths: Iterable[str | Path],
        *,
        required_columns_by_format: Mapping[str, Sequence[str]] | None = None,
        allow_cross_dataset_duplicate: bool = False,
        cancelled: CancellationCallback | None = None,
    ) -> dict[str, Any]:
        completed: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        for raw_path in paths:
            _check_cancel(cancelled)
            try:
                source = Path(raw_path)
                fmt = detect_format(source)
                completed.append(
                    self.ingest(
                        dataset_id,
                        source,
                        required_columns=(required_columns_by_format or {}).get(fmt, ()),
                        allow_cross_dataset_duplicate=allow_cross_dataset_duplicate,
                        cancelled=cancelled,
                    )
                )
            except (OSError, ValueError, KeyError, IngestionCancelled) as exc:
                failures.append({"path": str(raw_path), "error": str(exc)})
                if isinstance(exc, IngestionCancelled):
                    break
        return {
            "dataset_id": dataset_id,
            "completed": completed,
            "failures": failures,
            "partial_success": bool(completed and failures),
            "cancelled": bool(failures and failures[-1]["error"].endswith("cancelled")),
        }

    def files(self, dataset_id: str, *, limit: int = 1000) -> list[dict[str, Any]]:
        return self.store.rows(
            "dataset_files", filters={"dataset_id": dataset_id},
            order_by="created_at_utc", limit=limit,
        )


__all__ = [
    "FORMAT_SUFFIXES",
    "IngestionCancelled",
    "ScientificFileIngestor",
    "detect_format",
    "preview_file",
    "stream_sha256",
    "validate_file",
    "validate_tabular_schema",
]
