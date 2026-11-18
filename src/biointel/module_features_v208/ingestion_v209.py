from __future__ import annotations

import io
import json
import zipfile
from pathlib import PurePosixPath
from typing import Any

import pandas as pd


def safe_zip_basename(name: str) -> str:
    path = PurePosixPath(str(name).replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("The uploaded ZIP contains an unsafe path.")
    if not path.name:
        raise ValueError("The uploaded ZIP contains an invalid filename.")
    return path.name.lower()


def read_zip_tables_bytes(raw: bytes, *, max_uncompressed_bytes: int = 100 * 1024 * 1024) -> dict[str, Any]:
    if not raw:
        raise ValueError("The uploaded ZIP is empty.")
    output: dict[str, Any] = {}
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = safe_zip_basename(info.filename)
                if name in output:
                    raise ValueError(f"Duplicate ZIP basename is not allowed: {name}")
                total += int(info.file_size)
                if total > max_uncompressed_bytes:
                    raise ValueError("The ZIP expands beyond the 100 MB interactive safety boundary.")
                if info.compress_size and info.file_size / max(1, info.compress_size) > 200:
                    raise ValueError(f"Suspicious compression ratio in {name}.")
                content = archive.read(info)
                if name.endswith((".csv", ".tsv", ".txt")):
                    separator = "\t" if name.endswith((".tsv", ".txt")) else ","
                    output[name] = pd.read_csv(io.BytesIO(content), sep=separator, low_memory=False)
                elif name.endswith(".json"):
                    output[name] = json.loads(content.decode("utf-8"))
                elif name.endswith((".fasta", ".fa", ".fna", ".faa")):
                    output[name] = content.decode("utf-8")
    except zipfile.BadZipFile as exc:
        raise ValueError("The uploaded file is not a valid ZIP archive.") from exc
    if not output:
        raise ValueError("The ZIP does not contain a supported CSV/TSV/JSON/FASTA input.")
    return output


def _pick(mapping: dict[str, Any], *tokens: str, required_type: type | tuple[type, ...] | None = None) -> Any | None:
    for name, value in mapping.items():
        if any(token in name for token in tokens) and (required_type is None or isinstance(value, required_type)):
            return value
    return None


def structured_payload_from_zip(feature_key: str, files: dict[str, Any]) -> Any:
    if feature_key == "microbiome_controls":
        abundance = _pick(files, "abundance", "count", required_type=pd.DataFrame)
        metadata = _pick(files, "metadata", "sample", required_type=pd.DataFrame)
        if abundance is None or metadata is None:
            raise ValueError("Microbiome ZIP needs abundance/count and metadata CSV files.")
        return {"abundance": abundance, "metadata": metadata}
    if feature_key == "admet_calibration":
        reference = _pick(files, "reference", "train", required_type=pd.DataFrame)
        query = _pick(files, "query", "candidate", "test", required_type=pd.DataFrame)
        if reference is None or query is None:
            raise ValueError("ADMET ZIP needs reference/train and query/candidate CSV files.")
        return {"reference": reference, "query": query}
    if feature_key == "protein_design":
        candidates = _pick(files, "candidate", "design", required_type=pd.DataFrame)
        parameters = _pick(files, "parameter", "manifest", required_type=dict) or {}
        reference = parameters.get("reference_sequence") if isinstance(parameters, dict) else None
        if not reference:
            fasta = _pick(files, "reference", required_type=str)
            if fasta:
                reference = "".join(line.strip() for line in fasta.splitlines() if line and not line.startswith(">"))
        if candidates is None or not reference:
            raise ValueError("Protein-design ZIP needs candidates CSV and a reference FASTA or parameters JSON.")
        return {"reference": reference, "candidates": candidates, "conserved_positions": parameters.get("conserved_positions", ()) if isinstance(parameters, dict) else ()}
    if feature_key == "primer_crispr":
        primers = _pick(files, "primer", "guide", required_type=pd.DataFrame)
        parameters = _pick(files, "parameter", "manifest", required_type=dict) or {}
        if primers is None or not isinstance(parameters, dict) or not parameters.get("target_sequence"):
            raise ValueError("Primer/CRISPR ZIP needs primers/guides CSV and parameters JSON with target_sequence.")
        return {"primers": primers, **parameters}
    frames = [value for value in files.values() if isinstance(value, pd.DataFrame)]
    if len(frames) == 1:
        return frames[0]
    raise ValueError("This workflow needs a single supported table or its documented multi-file ZIP layout.")


__all__ = ["safe_zip_basename", "read_zip_tables_bytes", "structured_payload_from_zip"]
