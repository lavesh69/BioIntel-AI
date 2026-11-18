from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from biointel.native.formats import MAX_NATIVE_FILE_BYTES, NativeParseResult, parse_native_path

from .catalog import MODULE_BY_KEY
from .native_profiles import compound_suffix, profile_for


MAX_NATIVE_PREVIEW_RECORDS = 100_000
MAX_ANALYSIS_RECORDS = 250_000


@dataclass(frozen=True)
class NativeInputBundle:
    module_key: str
    staged_path: str
    manifest_path: str
    extension: str
    parse_result: NativeParseResult
    analysis_frame: pd.DataFrame
    analysis_ready: bool
    blocking_reason: str
    warnings: tuple[str, ...]

    def summary(self) -> dict[str, Any]:
        return {
            "schema": "biointel.bioinformatics.native_input.v139",
            "module_key": self.module_key,
            "extension": self.extension,
            "staged_path": self.staged_path,
            "manifest_path": self.manifest_path,
            "analysis_ready": self.analysis_ready,
            "blocking_reason": self.blocking_reason,
            "warnings": list(self.warnings),
            "native": self.parse_result.summary(),
            "analysis_rows": len(self.analysis_frame),
            "analysis_columns": list(map(str, self.analysis_frame.columns)),
        }


def _user_root(project_root: str | Path) -> Path:
    root = Path(project_root).resolve()
    return Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or root / "UserData").resolve()


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
    return cleaned[:180] or "scientific_input.bin"


def _source_bytes(source: Any) -> tuple[bytes, str]:
    name = str(getattr(source, "name", "scientific_input.bin"))
    if hasattr(source, "getvalue"):
        payload = bytes(source.getvalue())
    else:
        payload = bytes(source.read())
    if not payload:
        raise ValueError("The native scientific file is empty.")
    if len(payload) > MAX_NATIVE_FILE_BYTES:
        raise ValueError("The native scientific file exceeds the configured 1 GB limit.")
    return payload, name


def stage_native_upload(project_root: str | Path, source: Any, *, module_key: str) -> dict[str, Any]:
    if module_key not in MODULE_BY_KEY:
        raise KeyError(module_key)
    payload, original_name = _source_bytes(source)
    extension = compound_suffix(original_name)
    profile = profile_for(module_key)
    if extension not in profile.accepted_extensions:
        allowed = ", ".join(f".{item}" for item in profile.accepted_extensions)
        raise ValueError(f".{extension or 'unknown'} is not accepted by this module. Supported native inputs: {allowed}")

    user_root = _user_root(project_root)
    token = uuid4().hex
    workdir = (user_root / "native_engine_workspace" / module_key / token).resolve()
    allowed_root = (user_root / "native_engine_workspace").resolve()
    workdir.mkdir(parents=True, exist_ok=False)
    try:
        workdir.relative_to(allowed_root)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError("Unsafe native staging directory") from exc

    target = workdir / _safe_filename(original_name)
    partial = target.with_suffix(target.suffix + ".partial")
    digest = sha256(payload).hexdigest()
    with partial.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    written_digest = sha256(partial.read_bytes()).hexdigest()
    if written_digest != digest:
        partial.unlink(missing_ok=True)
        raise IOError("Native input checksum changed during staging.")
    partial.replace(target)

    manifest = {
        "schema": "biointel.bioinformatics.native_stage.v139",
        "module_key": module_key,
        "original_name": Path(original_name).name,
        "extension": extension,
        "path": str(target),
        "workdir": str(workdir),
        "size_bytes": len(payload),
        "sha256": digest,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "accepted_extensions": list(profile.accepted_extensions),
    }
    manifest_path = workdir / "stage_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {**manifest, "manifest_path": str(manifest_path)}


def _numeric_genotype(value: Any) -> float:
    text = str(value or "").replace("|", "/")
    alleles = [token for token in text.split("/") if token.isdigit()]
    return float(sum(int(token) for token in alleles)) if alleles else np.nan


def _safe_numeric(series: pd.Series, default: float | int | None = None) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.fillna(default) if default is not None else values


def _rename_aliases(frame: pd.DataFrame, aliases: dict[str, tuple[str, ...]]) -> pd.DataFrame:
    output = frame.copy()
    lower_map = {str(column).strip().lower(): str(column) for column in output.columns}
    for target, candidates in aliases.items():
        if target in output.columns:
            continue
        match = next((lower_map[candidate.lower()] for candidate in candidates if candidate.lower() in lower_map), None)
        if match is not None:
            output[target] = output[match]
    return output


def _normalize_gwas(frame: pd.DataFrame) -> pd.DataFrame:
    out = _rename_aliases(frame, {
        "variant": ("variant_id", "id", "snp", "rsid"),
        "position": ("pos", "bp"),
        "sample": ("iid", "sample_id"),
        "phenotype": ("pheno", "trait"),
    })
    if "genotype" in out:
        out["genotype"] = out["genotype"].map(_numeric_genotype)
    if "phenotype" not in out:
        out["phenotype"] = np.nan
    return out


def _normalize_epigenomics(frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
    out = _rename_aliases(frame, {"region": ("name", "id"), "signal": ("score", "coverage", "methylation_fraction")})
    if "sample" not in out:
        out["sample"] = Path(source_name).stem
    if "condition" not in out:
        out["condition"] = "Unspecified"
    if "region" not in out and {"chrom", "start", "end"}.issubset(out.columns):
        out["region"] = out["chrom"].astype(str) + ":" + out["start"].astype(str) + "-" + out["end"].astype(str)
    if "signal" not in out:
        out["signal"] = 1.0
    return out


def _normalize_pgx(frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
    out = _rename_aliases(frame, {
        "variant": ("variant_id", "id", "rsid"),
        "allele": ("alt", "genotype"),
        "gene": ("symbol", "name"),
        "sample": ("sample_id", "iid"),
    })
    if "sample" not in out:
        out["sample"] = Path(source_name).stem
    if "gene" not in out:
        out["gene"] = "Unmapped pharmacogene"
    if "drug" not in out:
        out["drug"] = "Medication mapping required"
    if "evidence_level" not in out:
        out["evidence_level"] = "Unreviewed"
    return out


def _normalize_sv(frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
    out = frame.copy()
    if {"chrom1", "start1", "end1", "chrom2", "start2", "end2"}.issubset(out.columns):
        out["chrom"] = out["chrom1"]
        out["start"] = out["start1"]
        out["end"] = out["end2"]
        out["event_type"] = np.where(out["chrom1"].astype(str).eq(out["chrom2"].astype(str)), "INTRACHROMOSOMAL", "TRANSLOCATION")
        out["partner_chrom"] = out["chrom2"]
        out["partner_start"] = out["start2"]
        out["partner_end"] = out["end2"]
    out = _rename_aliases(out, {
        "event_id": ("variant_id", "name", "id"),
        "event_type": ("variant_type", "svtype", "type"),
        "support": ("read_support", "depth", "score", "quality"),
        "start": ("position", "pos"),
        "sample": ("sample_id",),
    })
    if "sample" not in out:
        out["sample"] = Path(source_name).stem
    if "end" not in out and "start" in out:
        out["end"] = _safe_numeric(out["start"], 0) + 1
    if "event_type" not in out:
        out["event_type"] = "Unclassified"
    if "support" not in out:
        out["support"] = 1.0
    return out


def _normalize_splicing(frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
    out = _rename_aliases(frame, {
        "transcript": ("parent", "transcript_id", "id"),
        "gene": ("name", "gene_name", "gene_id"),
        "event": ("feature_type", "event_type", "id"),
        "junction_support": ("score", "coverage", "count"),
    })
    if "sample" not in out:
        out["sample"] = Path(source_name).stem
    if "group" not in out:
        out["group"] = "Unspecified"
    if "psi" not in out:
        out["psi"] = np.nan
    if "junction_support" not in out:
        out["junction_support"] = 1.0
    return out


def _normalize_annotation(frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
    out = _rename_aliases(frame, {
        "feature_id": ("id", "name", "record_id"),
        "evidence": ("source",),
    })
    if "genome" not in out:
        out["genome"] = Path(source_name).stem
    if "feature_type" not in out:
        out["feature_type"] = "sequence_record"
    if "chrom" not in out:
        out["chrom"] = out.get("record_id", pd.Series([Path(source_name).stem] * len(out), index=out.index))
    if "start" not in out:
        out["start"] = 0
    if "end" not in out:
        out["end"] = _safe_numeric(out.get("length", pd.Series([1] * len(out), index=out.index)), 1)
    if "strand" not in out:
        out["strand"] = "."
    if "evidence" not in out:
        out["evidence"] = "native import"
    return out


def _normalize_viral(frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
    out = _rename_aliases(frame, {
        "sample": ("sample_id",), "subject": ("patient", "host"), "frequency": ("allele_frequency", "af"),
    })
    if "sample" not in out:
        out["sample"] = Path(source_name).stem
    if "subject" not in out:
        out["subject"] = out["sample"]
    if "time" not in out:
        out["time"] = 0
    if "lineage" not in out:
        out["lineage"] = "Unassigned"
    return out


def _normalize_single_cell(frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
    out = _rename_aliases(frame, {"cell": ("cell_id", "barcode"), "sample": ("sample_id",), "cluster": ("cell_type", "leiden", "louvain"), "batch": ("batch_id",)})
    if "cell" not in out:
        out["cell"] = [f"cell_{index + 1}" for index in range(len(out))]
    if "sample" not in out:
        out["sample"] = Path(source_name).stem
    if "cluster" not in out:
        out["cluster"] = "Unassigned"
    if "batch" not in out:
        out["batch"] = "Unspecified"
    embedding = next((column for column in out.columns if str(column).lower().startswith(("x_umap_", "x_pca_", "x_tsne_", "spatial_"))), None)
    if embedding is not None:
        out["modality"] = "embedding"
        out["feature"] = embedding
        out["value"] = _safe_numeric(out[embedding])
    return out


def _normalize_comparative(frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
    out = _rename_aliases(frame, {"region": ("name", "id"), "conservation": ("score",), "activity": ("signal", "score")})
    if "species" not in out:
        out["species"] = "Unspecified"
    if "ortholog_group" not in out:
        out["ortholog_group"] = out.get("region", pd.Series([Path(source_name).stem] * len(out), index=out.index))
    if "motif" not in out:
        out["motif"] = "Unspecified"
    if "activity" not in out:
        out["activity"] = out.get("conservation", 1.0)
    return out


def normalize_native_frame(module_key: str, result: NativeParseResult) -> tuple[pd.DataFrame, list[str]]:
    frame = result.primary.copy()
    warnings = list(result.warnings)
    if frame.empty:
        return frame, warnings
    frame = frame.loc[:, ~frame.columns.astype(str).duplicated()].head(MAX_ANALYSIS_RECORDS)
    frame.replace([np.inf, -np.inf], np.nan, inplace=True)
    source_name = result.source_name

    if module_key == "population_gwas_peak":
        frame = _normalize_gwas(frame)
    elif module_key == "epigenomics_peak":
        frame = _normalize_epigenomics(frame, source_name)
    elif module_key == "pharmacogenomics_peak":
        frame = _normalize_pgx(frame, source_name)
    elif module_key in {"structural_variant_peak", "circular_dna_instability"}:
        frame = _normalize_sv(frame, source_name)
        if module_key == "circular_dna_instability" and "copy_number" not in frame:
            frame["copy_number"] = np.nan
    elif module_key == "rna_splicing_peak":
        frame = _normalize_splicing(frame, source_name)
    elif module_key == "single_cell_multiome":
        frame = _normalize_single_cell(frame, source_name)
    elif module_key == "viral_within_host":
        frame = _normalize_viral(frame, source_name)
    elif module_key == "genome_annotation":
        frame = _normalize_annotation(frame, source_name)
    elif module_key == "comparative_regulatory_genomics":
        frame = _normalize_comparative(frame, source_name)

    required = MODULE_BY_KEY[module_key].required_columns
    missing = [column for column in required if column not in frame.columns]
    if missing:
        warnings.append("Native preview is available, but analysis requires mapped fields: " + ", ".join(missing))
    return frame, warnings


def prepare_native_input(
    project_root: str | Path,
    source: Any,
    *,
    module_key: str,
    max_records: int = MAX_NATIVE_PREVIEW_RECORDS,
) -> NativeInputBundle:
    staged = stage_native_upload(project_root, source, module_key=module_key)
    path = Path(staged["path"])
    profile = profile_for(module_key)
    result = parse_native_path(path, preferred_viewer=profile.preferred_viewer, max_records=max_records)
    if result.format_key not in profile.format_keys and result.format_key not in {"tabular", "bed", "gff", "vcf", "fasta", "fastq"}:
        result.warnings.append(
            f"Detected native format '{result.format_key}' is retained for metadata/QC but is not a primary analysis format for this module."
        )
    frame, warnings = normalize_native_frame(module_key, result)
    required = MODULE_BY_KEY[module_key].required_columns
    missing = [column for column in required if column not in frame.columns]
    nonempty_required = [column for column in required if column in frame.columns and frame[column].notna().any()]
    analysis_ready = bool(not frame.empty and not missing)
    blocking_reason = ""
    if result.engine_required and not analysis_ready:
        blocking_reason = f"{result.engine_required} is required to decode this native format into analysis-ready records."
    elif missing:
        blocking_reason = "Map or generate the required scientific fields before analysis: " + ", ".join(missing)
    elif frame.empty:
        blocking_reason = "The file was checksum-verified, but no analysis-ready records were decoded."

    enriched_manifest = {
        **staged,
        "native_summary": result.summary(),
        "analysis_ready": analysis_ready,
        "blocking_reason": blocking_reason,
        "analysis_rows": len(frame),
        "analysis_columns": list(map(str, frame.columns)),
        "warnings": warnings,
    }
    Path(staged["manifest_path"]).write_text(json.dumps(enriched_manifest, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return NativeInputBundle(
        module_key=module_key,
        staged_path=str(path),
        manifest_path=str(staged["manifest_path"]),
        extension=str(staged["extension"]),
        parse_result=result,
        analysis_frame=frame,
        analysis_ready=analysis_ready,
        blocking_reason=blocking_reason,
        warnings=tuple(warnings),
    )


def remove_staged_native_input(bundle: NativeInputBundle) -> None:
    path = Path(bundle.staged_path)
    workdir = path.parent
    with contextlib.suppress(Exception):
        for child in workdir.iterdir():
            if child.is_file():
                child.unlink(missing_ok=True)
        workdir.rmdir()


__all__ = [
    "MAX_ANALYSIS_RECORDS",
    "MAX_NATIVE_PREVIEW_RECORDS",
    "NativeInputBundle",
    "normalize_native_frame",
    "prepare_native_input",
    "remove_staged_native_input",
    "stage_native_upload",
]
