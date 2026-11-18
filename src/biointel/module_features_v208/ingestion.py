from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterable

import numpy as np
import pandas as pd

MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
INTERACTIVE_PREVIEW_BYTES = 100 * 1024 * 1024
CHUNK_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class FormatCapability:
    format_key: str
    extensions: tuple[str, ...]
    category: str
    mode: str
    dependency: str | None
    description: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["available"] = self.dependency is None or importlib.util.find_spec(self.dependency) is not None
        return payload


FORMAT_CAPABILITIES: tuple[FormatCapability, ...] = (
    FormatCapability("csv_tsv", (".csv", ".tsv", ".txt"), "tabular", "native", None, "Chunked local tabular preview and analysis."),
    FormatCapability("json_jsonl", (".json", ".jsonl", ".ndjson"), "tabular", "native", None, "Local JSON/JSON-lines preview."),
    FormatCapability("numpy", (".npy", ".npz"), "array", "native", None, "Local NumPy arrays with pickle disabled."),
    FormatCapability("fasta_fastq", (".fa", ".fasta", ".fna", ".fq", ".fastq", ".gz"), "sequence", "native", None, "Streaming FASTA/FASTQ record inspection."),
    FormatCapability("vcf", (".vcf", ".vcf.gz"), "variant", "native", None, "Header-aware VCF preview and variant normalization."),
    FormatCapability("h5ad", (".h5ad",), "single-cell", "native_dependency", "anndata", "Backed AnnData inspection without loading the entire matrix."),
    FormatCapability("zarr", (".zarr",), "single-cell", "native_dependency", "anndata", "AnnData Zarr inspection when the local adapter is available."),
    FormatCapability("nifti", (".nii", ".nii.gz"), "neuroimaging", "optional_adapter", "nibabel", "NIfTI volume and affine reader."),
    FormatCapability("dicom", (".dcm", ".dicom"), "neuroimaging", "optional_adapter", "pydicom", "DICOM metadata and pixel-data reader."),
    FormatCapability("edf_bdf_fif", (".edf", ".bdf", ".fif"), "neurophysiology", "optional_adapter", "mne", "EEG/MEG reader using MNE when installed."),
    FormatCapability("bam_cram_bcf", (".bam", ".cram", ".bcf"), "genomics", "optional_adapter", "pysam", "Indexed alignment/variant reader using pysam."),
    FormatCapability("bigwig", (".bw", ".bigwig", ".bb", ".bigbed"), "genomics", "optional_adapter", "pyBigWig", "BigWig/BigBed region reader."),
    FormatCapability("plink", (".bed", ".bim", ".fam", ".pgen", ".pvar", ".psam"), "genomics", "external_tool", None, "PLINK2 executable-backed workflow; binary decoding is not silently approximated."),
    FormatCapability("gfa", (".gfa", ".gfa1", ".gfa2"), "graphs", "native", None, "Streaming GFA segment/link inspection."),
    FormatCapability("ome_tiff", (".ome.tif", ".ome.tiff", ".tif", ".tiff"), "microscopy", "native_dependency", "PIL", "Multi-page image inspection; OME metadata remains adapter-aware."),
    FormatCapability("mzml", (".mzml",), "mass-spectrometry", "optional_adapter", "pymzml", "mzML spectrum reader when installed."),
    FormatCapability("fast5", (".fast5",), "long-read", "optional_adapter", "ont_fast5_api", "Oxford Nanopore FAST5 reader when installed."),
    FormatCapability("pod5", (".pod5",), "long-read", "optional_adapter", "pod5", "Oxford Nanopore POD5 reader when installed."),
)

_EXTENSION_LOOKUP = {
    extension: capability
    for capability in FORMAT_CAPABILITIES
    for extension in capability.extensions
}


def _safe_filename(filename: str) -> str:
    name = Path(str(filename or "upload.bin")).name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return name or "upload.bin"


def detect_format(filename: str) -> FormatCapability | None:
    lowered = str(filename).lower()
    for extension in sorted(_EXTENSION_LOOKUP, key=len, reverse=True):
        if lowered.endswith(extension):
            return _EXTENSION_LOOKUP[extension]
    return None


def format_support_table() -> pd.DataFrame:
    rows = []
    for capability in FORMAT_CAPABILITIES:
        row = capability.to_dict()
        row["extensions"] = ", ".join(capability.extensions)
        rows.append(row)
    return pd.DataFrame(rows)


def optional_adapter_status() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for capability in FORMAT_CAPABILITIES:
        if capability.dependency is None and capability.mode != "external_tool":
            continue
        available = capability.dependency is not None and importlib.util.find_spec(capability.dependency) is not None
        rows.append(
            {
                "format": capability.format_key,
                "mode": capability.mode,
                "dependency": capability.dependency or "external executable",
                "available": bool(available),
                "state": "available" if available else "optional service unavailable",
            }
        )
    return pd.DataFrame(rows)


def stage_stream(
    stream: BinaryIO,
    *,
    filename: str,
    staging_dir: str | Path,
    max_bytes: int = MAX_UPLOAD_BYTES,
    chunk_bytes: int = CHUNK_BYTES,
) -> dict[str, Any]:
    if max_bytes <= 0 or chunk_bytes <= 0:
        raise ValueError("Upload limits must be positive.")
    directory = Path(staging_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(filename)
    final_path = directory / safe_name
    digest = hashlib.sha256()
    total = 0
    with tempfile.NamedTemporaryFile(prefix=f".{safe_name}.", suffix=".part", dir=directory, delete=False) as handle:
        temp_path = Path(handle.name)
        try:
            while True:
                chunk = stream.read(chunk_bytes)
                if not chunk:
                    break
                if not isinstance(chunk, (bytes, bytearray)):
                    raise TypeError("Upload stream must return bytes.")
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"Upload exceeds the {max_bytes / 1024**3:.1f} GB safety limit.")
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
    os.replace(temp_path, final_path)
    capability = detect_format(safe_name)
    return {
        "path": str(final_path),
        "filename": safe_name,
        "size_bytes": total,
        "sha256": digest.hexdigest(),
        "format": capability.format_key if capability else "unknown",
        "mode": capability.mode if capability else "unsupported",
        "adapter_available": capability is not None
        and (capability.dependency is None or importlib.util.find_spec(capability.dependency) is not None),
        "interactive_preview_allowed": total <= INTERACTIVE_PREVIEW_BYTES,
    }


def file_manifest(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    capability = detect_format(source.name)
    return {
        "path": str(source),
        "filename": source.name,
        "size_bytes": source.stat().st_size,
        "sha256": digest.hexdigest(),
        "format": capability.format_key if capability else "unknown",
        "mode": capability.mode if capability else "unsupported",
    }


def _preview_delimited(path: Path, *, separator: str, max_rows: int) -> pd.DataFrame:
    return pd.read_csv(path, sep=separator, nrows=max_rows, low_memory=False)


def _preview_json(path: Path, *, max_rows: int) -> pd.DataFrame:
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        rows = []
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle):
                if index >= max_rows:
                    break
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return pd.DataFrame(rows)
    payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    if isinstance(payload, list):
        return pd.DataFrame(payload[:max_rows])
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                return pd.DataFrame(value[:max_rows])
        return pd.DataFrame([payload])
    return pd.DataFrame({"value": [payload]})


def _preview_vcf(path: Path, *, max_rows: int) -> pd.DataFrame:
    columns: list[str] | None = None
    records: list[list[str]] = []
    opener = path.open
    if path.name.lower().endswith(".gz"):
        import gzip

        opener = lambda *args, **kwargs: gzip.open(path, *args, **kwargs)  # type: ignore[assignment]
    with opener("rt", encoding="utf-8", errors="replace") as handle:  # type: ignore[misc]
        for line in handle:
            if line.startswith("##"):
                continue
            if line.startswith("#CHROM"):
                columns = line.lstrip("#").rstrip("\n").split("\t")
                continue
            if not line.startswith("#"):
                records.append(line.rstrip("\n").split("\t"))
                if len(records) >= max_rows:
                    break
    if not columns:
        columns = ["CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"]
    width = max([len(columns), *[len(row) for row in records]], default=len(columns))
    padded_columns = columns + [f"EXTRA_{i}" for i in range(len(columns) + 1, width + 1)]
    return pd.DataFrame([row + [None] * (width - len(row)) for row in records], columns=padded_columns)


def _sequence_preview(path: Path, *, max_rows: int) -> pd.DataFrame:
    import gzip

    opener = gzip.open if path.name.lower().endswith(".gz") else open
    rows: list[dict[str, Any]] = []
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        first = handle.readline()
        handle.seek(0)
        if first.startswith(">"):
            identifier = None
            sequence: list[str] = []
            for line in handle:
                line = line.strip()
                if line.startswith(">"):
                    if identifier is not None:
                        text = "".join(sequence)
                        rows.append({"id": identifier, "length": len(text), "sequence_preview": text[:80]})
                        if len(rows) >= max_rows:
                            break
                    identifier = line[1:].split()[0] or "unnamed"
                    sequence = []
                else:
                    sequence.append(line)
            if identifier is not None and len(rows) < max_rows:
                text = "".join(sequence)
                rows.append({"id": identifier, "length": len(text), "sequence_preview": text[:80]})
        elif first.startswith("@"):
            while len(rows) < max_rows:
                header = handle.readline().strip()
                if not header:
                    break
                sequence = handle.readline().strip()
                plus = handle.readline().strip()
                quality = handle.readline().strip()
                if not plus.startswith("+"):
                    raise ValueError("FASTQ structure is invalid near record %d." % (len(rows) + 1))
                rows.append(
                    {
                        "id": header.lstrip("@").split()[0],
                        "length": len(sequence),
                        "mean_quality_ascii": float(np.mean([ord(char) - 33 for char in quality])) if quality else np.nan,
                        "sequence_preview": sequence[:80],
                    }
                )
        else:
            raise ValueError("Sequence file is neither FASTA nor FASTQ.")
    return pd.DataFrame(rows)


def load_preview(path: str | Path, *, max_rows: int = 10_000) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    manifest = file_manifest(source)
    capability = detect_format(source.name)
    if capability is None:
        raise ValueError(f"Unsupported file extension: {source.suffix or '[none]' }.")
    if manifest["size_bytes"] > MAX_UPLOAD_BYTES:
        raise ValueError("File exceeds the 1 GB ingestion safety limit.")
    key = capability.format_key
    if key == "csv_tsv":
        separator = "\t" if source.suffix.lower() in {".tsv", ".txt"} else ","
        frame = _preview_delimited(source, separator=separator, max_rows=max_rows)
        return {"manifest": manifest, "preview": frame, "shape_preview": tuple(frame.shape)}
    if key == "json_jsonl":
        frame = _preview_json(source, max_rows=max_rows)
        return {"manifest": manifest, "preview": frame, "shape_preview": tuple(frame.shape)}
    if key == "vcf":
        frame = _preview_vcf(source, max_rows=max_rows)
        return {"manifest": manifest, "preview": frame, "shape_preview": tuple(frame.shape)}
    if key == "fasta_fastq":
        frame = _sequence_preview(source, max_rows=min(max_rows, 50_000))
        return {"manifest": manifest, "preview": frame, "shape_preview": tuple(frame.shape)}
    if key == "numpy":
        if source.suffix.lower() == ".npy":
            array = np.load(source, mmap_mode="r", allow_pickle=False)
            preview = np.asarray(array[tuple(slice(0, min(20, size)) for size in array.shape)])
            return {"manifest": manifest, "preview": preview, "shape": tuple(array.shape), "dtype": str(array.dtype)}
        archive = np.load(source, mmap_mode="r", allow_pickle=False)
        arrays = pd.DataFrame(
            [{"key": name, "shape": tuple(archive[name].shape), "dtype": str(archive[name].dtype)} for name in archive.files]
        )
        return {"manifest": manifest, "preview": arrays, "keys": archive.files}
    if key == "h5ad":
        import anndata as ad

        obj = ad.read_h5ad(source, backed="r")
        try:
            obs = obj.obs.head(min(max_rows, 5000)).reset_index()
            var = obj.var.head(min(max_rows, 5000)).reset_index()
            return {
                "manifest": manifest,
                "shape": tuple(obj.shape),
                "obs_preview": obs,
                "var_preview": var,
                "backed": True,
            }
        finally:
            if getattr(obj, "file", None) is not None:
                obj.file.close()
    if key == "gfa":
        rows = []
        with source.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line or line.startswith("H"):
                    continue
                parts = line.rstrip("\n").split("\t")
                rows.append({"record_type": parts[0], "field_1": parts[1] if len(parts) > 1 else None, "field_count": len(parts)})
                if len(rows) >= max_rows:
                    break
        return {"manifest": manifest, "preview": pd.DataFrame(rows)}
    if capability.dependency and importlib.util.find_spec(capability.dependency) is None:
        return {
            "manifest": manifest,
            "preview": pd.DataFrame(),
            "optional_service_unavailable": True,
            "message": f"Optional {capability.dependency} adapter is unavailable. The app remains usable offline.",
        }
    return {
        "manifest": manifest,
        "preview": pd.DataFrame(),
        "adapter_available": True,
        "message": "The format adapter is available; use the specialist module for full decoding.",
    }


def cleanup_staged_file(path: str | Path, *, allowed_root: str | Path) -> bool:
    target = Path(path).expanduser().resolve()
    root = Path(allowed_root).expanduser().resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Refusing to remove a file outside the staging root.") from exc
    if target.is_file():
        target.unlink()
        return True
    return False
