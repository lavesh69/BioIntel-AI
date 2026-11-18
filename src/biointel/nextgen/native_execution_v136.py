from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import contextlib
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from functools import lru_cache
from typing import Any, Callable, Iterable

import pandas as pd

from biointel.jobs.local_queue import JobRecord, LocalJobQueue
from biointel.native.engines import detect_engine, plan_catalog
from biointel.native.formats import (
    INTERACTIVE_NATIVE_BYTES,
    MAX_NATIVE_FILE_BYTES,
    NativeParseResult,
    detect_native_format,
    parse_native_path,
    parse_native_source,
    stage_native_source,
)
from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS
from biointel.nextgen.catalog import MODULE_BY_KEY
from biointel.nextgen.scientific import analyse, normalise, read_upload
from biointel.nextgen.services import state_root
from biointel.ui.operational_canvas import render_operational_canvas

MAX_BACKGROUND_PREVIEW_RECORDS = 500_000
MAX_INLINE_BYTES = 100 * 1024 * 1024
MAX_ENGINE_THREADS = 32


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _safe_name(value: str) -> str:
    name = Path(str(value or "scientific_input.dat")).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "scientific_input.dat"
    return stem[:180]


def _matches_extension(name: str, extensions: Iterable[str]) -> bool:
    lower = Path(name).name.lower()
    return any(lower.endswith("." + str(extension).lower().lstrip(".")) for extension in extensions)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class NativePipelineProfile:
    module_key: str
    title: str
    accepted_extensions: tuple[str, ...]
    preferred_viewer: str
    builtin_stages: tuple[str, ...]
    optional_engines: tuple[str, ...]
    engine_plan_keys: tuple[str, ...]
    reference_assets: tuple[str, ...]
    primary_outputs: tuple[str, ...]
    maximum_bytes: int = MAX_NATIVE_FILE_BYTES
    interactive_bytes: int = INTERACTIVE_NATIVE_BYTES
    boundary: str = "Built-in parsing and QC are available. Specialist external-engine results require the declared local tools and reference assets."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PROFILES: dict[str, NativePipelineProfile] = {
    "digital_pathology_foundation": NativePipelineProfile(
        "digital_pathology_foundation",
        "Whole-slide pathology ingestion and segmentation readiness",
        ("svs", "ndpi", "mrxs", "scn", "tif", "tiff", "ome.tif", "ome.tiff", "png", "jpg", "jpeg"),
        "pathology",
        ("checksum", "slide metadata", "bounded thumbnail/tile QC", "scanner/stain review", "segmentation readiness", "artifact validation"),
        ("openslide", "cellpose", "stardist"),
        ("cellpose_segment",),
        ("Stain-normalisation profile", "Approved pathology model weights", "Scanner/site metadata"),
        ("slide_manifest.json", "tile_qc.csv.gz", "segmentation outputs when engine-ready"),
    ),
    "long_read_epigenome": NativePipelineProfile(
        "long_read_epigenome",
        "Long-read methylation, phasing and DMR pipeline",
        ("bam", "cram", "bedmethyl", "bedmethyl.gz", "bed", "bed.gz", "vcf", "vcf.gz", "tsv", "txt"),
        "genome_browser",
        ("checksum", "alignment/mod-base validation", "coverage QC", "methylation preview", "haplotype readiness", "DMR input validation"),
        ("samtools", "whatshap", "deeptools", "bcftools", "tabix"),
        ("samtools_index", "samtools_depth", "whatshap_phase", "deeptools_bamcoverage"),
        ("Reference FASTA", "Genome build manifest", "Imprinting catalogue", "Optional phased VCF"),
        ("methylation_preview.csv.gz", "coverage_qc.json", "phasing readiness manifest"),
    ),
    "single_cell_long_read_isoforms": NativePipelineProfile(
        "single_cell_long_read_isoforms",
        "Single-cell long-read transcript and isoform pipeline",
        ("bam", "cram", "gtf", "gff", "gff3", "h5ad", "mtx", "mtx.gz", "csv", "tsv"),
        "single_cell",
        ("checksum", "cell metadata QC", "transcript annotation QC", "barcode/UMI readiness", "isoform evidence preview", "replicate design validation"),
        ("samtools", "minimap2", "scanpy", "rmats", "majiq", "suppa2"),
        (),
        ("Reference FASTA", "Transcript annotation GTF/GFF", "Barcode whitelist", "Sample/replicate manifest"),
        ("cell_metadata.csv.gz", "isoform_preview.csv.gz", "transcript_qc.json"),
    ),
    "biomedical_foundation_model_hub": NativePipelineProfile(
        "biomedical_foundation_model_hub",
        "Model checkpoint and embedding asset lifecycle",
        ("onnx", "safetensors", "pt", "pth", "bin", "gguf", "json", "yaml", "yml"),
        "static_reporting",
        ("checksum", "asset metadata", "size/memory profile", "licence gate", "runtime compatibility", "security boundary"),
        ("llama_cpp", "proteinmpnn", "rfdiffusion", "scanpy"),
        (),
        ("Model card", "Licence record", "Expected SHA-256", "Tokenizer/config assets", "Benchmark dataset"),
        ("model_asset_manifest.json", "hardware_fit.csv", "licence_readiness.json"),
        boundary="Binary model assets are never deserialised during inspection. Inference is enabled only through explicitly approved local engines and checksum-bound assets.",
    ),
    "amr_surveillance": NativePipelineProfile(
        "amr_surveillance",
        "AMR read-to-surveillance readiness pipeline",
        ("fastq", "fq", "fastq.gz", "fq.gz", "fasta", "fa", "fna", "faa", "gff", "gff3", "vcf", "vcf.gz"),
        "outbreak_map",
        ("checksum", "read/assembly QC", "species readiness", "AMR database readiness", "lineage/phylogeny readiness", "surveillance manifest"),
        ("kraken2", "bracken", "abricate", "blastn", "flye", "minimap2", "mafft", "iqtree"),
        ("flye_assemble", "mafft_align", "iqtree_build"),
        ("Kraken/Bracken database", "AMR gene database release", "Breakpoint standard/version", "MLST/cgMLST schema"),
        ("amr_input_qc.json", "classification readiness", "lineage readiness", "surveillance manifest"),
    ),
    "spatial_medicine_tme": NativePipelineProfile(
        "spatial_medicine_tme",
        "Spatial transcriptomics and histology ingestion pipeline",
        ("h5ad", "mtx", "mtx.gz", "h5", "hdf5", "tif", "tiff", "ome.tif", "ome.tiff", "png", "jpg", "jpeg", "csv", "tsv"),
        "single_cell",
        ("checksum", "coordinate QC", "image metadata", "cell/spot metadata", "registration readiness", "neighbourhood input validation"),
        ("openslide", "cellpose", "stardist", "scanpy"),
        ("cellpose_segment",),
        ("Platform manifest", "Histology image", "Spatial coordinates", "Feature annotation", "Optional segmentation model"),
        ("spatial_metadata.csv.gz", "coordinate_qc.json", "registration readiness manifest"),
    ),
    "gene_therapy_vector": NativePipelineProfile(
        "gene_therapy_vector",
        "Gene-therapy vector sequence and safety pipeline",
        ("gb", "gbk", "genbank", "fasta", "fa", "fna", "vcf", "csv", "tsv"),
        "sequence_track",
        ("checksum", "construct parsing", "capacity/GC QC", "feature integrity", "off-target readiness", "immunogenicity readiness"),
        ("blastn", "netmhcpan", "netmhciipan", "vep"),
        ("vep_annotate",),
        ("Vector/serotype reference", "Host genome build", "Population immunity evidence", "Approved epitope model/data"),
        ("construct_manifest.json", "sequence_qc.csv.gz", "safety readiness manifest"),
    ),
    "cell_therapy_cart": NativePipelineProfile(
        "cell_therapy_cart",
        "CAR-T construct annotation and immune-safety pipeline",
        ("fasta", "fa", "faa", "fna", "gb", "gbk", "genbank", "csv", "tsv"),
        "sequence_track",
        ("checksum", "construct parsing", "domain/CDR readiness", "germline readiness", "antigen evidence gate", "manufacturing manifest"),
        ("anarci", "igblast", "netmhcpan", "netmhciipan"),
        ("anarci_number", "igblast_germline"),
        ("IgBLAST germline database", "Antigen tissue-expression atlas", "MHC model data", "Construct design manifest"),
        ("car_construct_manifest.json", "domain_annotation.csv.gz", "immune_safety_readiness.json"),
    ),
    "federated_biomedical_ai": NativePipelineProfile(
        "federated_biomedical_ai",
        "Federated training manifest and privacy-accounting pipeline",
        ("csv", "tsv", "json", "jsonl", "parquet", "feather"),
        "multiomics",
        ("checksum", "site schema QC", "round manifest QC", "privacy parameter validation", "fairness readiness", "signed-update manifest"),
        (),
        (),
        ("Site data dictionaries", "Model architecture hash", "Privacy policy", "Signing keys/public certificates"),
        ("federation_manifest.json", "site_schema_qc.csv.gz", "privacy_accounting.json"),
    ),
    "clinical_biomarker_survival": NativePipelineProfile(
        "clinical_biomarker_survival",
        "Clinical biomarker and longitudinal survival ingestion pipeline",
        ("csv", "tsv", "txt", "xlsx", "xls", "json", "jsonl", "parquet", "feather"),
        "multiomics",
        ("checksum", "patient/time/event schema QC", "unit/date validation", "site/cohort validation", "missingness review", "analysis-design lock"),
        (),
        (),
        ("Data dictionary", "Endpoint definition", "Censoring rules", "Cohort/version manifest", "External validation protocol"),
        ("clinical_schema_qc.json", "patient_preview.csv.gz", "analysis_design_manifest.json"),
        boundary="This pipeline supports research analysis and validation planning. It does not provide diagnosis, treatment advice or regulatory-grade clinical qualification.",
    ),
    "protein_ligand_codesign": NativePipelineProfile(
        "protein_ligand_codesign",
        "Protein–ligand structure preparation and docking readiness",
        ("pdb", "cif", "mmcif", "sdf", "mol", "mol2", "pdbqt", "csv", "tsv"),
        "molecular_3d",
        ("checksum", "structure/ligand parse", "chain/residue QC", "ligand property preview", "docking-box readiness", "selectivity panel manifest"),
        ("obabel", "vina", "gromacs", "openmm", "proteinmpnn", "rfdiffusion"),
        ("vina_dock", "gromacs_mdrun"),
        ("Prepared receptor", "Prepared ligand", "Search-box definition", "Selectivity-panel structures", "Optional MD force field"),
        ("structure_qc.json", "ligand_preview.csv.gz", "docking_readiness.json"),
    ),
    "pangenome_population_medicine": NativePipelineProfile(
        "pangenome_population_medicine",
        "Pangenome graph and population-variant pipeline",
        ("gfa", "gfa1", "gfa2", "vg", "xg", "gbz", "vcf", "vcf.gz", "bcf", "fasta", "fa", "fna"),
        "pangenome_graph",
        ("checksum", "graph/path QC", "variant schema QC", "population metadata validation", "index readiness", "coordinate-system manifest"),
        ("minigraph", "vg", "odgi", "graphaligner", "bcftools", "tabix"),
        ("minigraph_graph", "bcftools_norm", "bcftools_stats"),
        ("Reference assembly", "Graph release/version", "Population metadata", "Coordinate/liftover manifest"),
        ("graph_qc.json", "path_preview.csv.gz", "population_variant_manifest.json"),
    ),
    "pharmacovigilance_intelligence": NativePipelineProfile(
        "pharmacovigilance_intelligence",
        "Adverse-event case harmonisation and signal pipeline",
        ("csv", "tsv", "txt", "xlsx", "xls", "json", "jsonl", "xml", "parquet", "feather"),
        "multiomics",
        ("checksum", "case schema QC", "duplicate fingerprinting", "drug/event normalisation readiness", "time-to-onset validation", "signal manifest"),
        (),
        (),
        ("MedDRA release", "WHO Drug dictionary/licence", "Case deduplication policy", "Exposure denominator when available"),
        ("case_schema_qc.json", "deduplication_review.csv.gz", "signal_readiness.json"),
    ),
    "synthetic_cohort_trial": NativePipelineProfile(
        "synthetic_cohort_trial",
        "Trial-simulation design and scenario ingestion pipeline",
        ("csv", "tsv", "xlsx", "xls", "json", "jsonl", "yaml", "yml", "parquet", "feather"),
        "multiomics",
        ("checksum", "arm/site schema QC", "outcome/time validation", "missingness/dropout design", "simulation seed lock", "scenario manifest"),
        (),
        (),
        ("Protocol estimand", "Endpoint distribution assumptions", "Recruitment/dropout assumptions", "Random seed policy"),
        ("trial_design_manifest.json", "scenario_input.csv.gz", "operating_characteristics_plan.json"),
    ),
    "autonomous_lab_planner": NativePipelineProfile(
        "autonomous_lab_planner",
        "Experimental design, plate and resource planning pipeline",
        ("csv", "tsv", "xlsx", "xls", "json", "jsonl", "yaml", "yml"),
        "plate_map",
        ("checksum", "factor/control schema QC", "replicate/power readiness", "plate constraints", "resource schedule validation", "approval manifest"),
        (),
        (),
        ("Instrument calendar", "Reagent/inventory snapshot", "SOP/protocol version", "Biosafety approval requirements"),
        ("design_manifest.json", "plate_layout.csv.gz", "resource_schedule.csv.gz"),
    ),
}


def profile_for(module_key: str) -> NativePipelineProfile:
    if module_key not in PROFILES:
        raise KeyError(f"No Step 136 native pipeline profile for {module_key}")
    return PROFILES[module_key]


def profile_table(module_key: str) -> pd.DataFrame:
    profile = profile_for(module_key)
    rows: list[dict[str, Any]] = []
    for index, stage in enumerate(profile.builtin_stages, start=1):
        rows.append({"Stage": str(index), "Built-in stage": stage, "Execution": "Built in / bounded"})
    for engine in profile.optional_engines:
        rows.append({"Stage": "External", "Built-in stage": engine, "Execution": "Optional local engine"})
    return pd.DataFrame(rows)



def streamlit_upload_types(module_key: str) -> list[str]:
    """Return Streamlit-compatible suffix filters while retaining strict compound-suffix validation."""
    profile = profile_for(module_key)
    values: set[str] = set()
    for extension in profile.accepted_extensions:
        cleaned = str(extension).lower().lstrip(".")
        if not cleaned:
            continue
        values.add(cleaned)
        # Streamlit/browser file pickers may only match the final suffix for compound formats.
        if "." in cleaned:
            values.add(cleaned.rsplit(".", 1)[-1])
    return sorted(values)

def reference_table(module_key: str) -> pd.DataFrame:
    profile = profile_for(module_key)
    return pd.DataFrame(
        [{"Reference asset": item, "Required for": profile.title, "Bundled": False, "Status": "Provide and checksum before external execution"} for item in profile.reference_assets]
    )


def engine_plan_table(module_key: str) -> pd.DataFrame:
    profile = profile_for(module_key)
    if not profile.engine_plan_keys:
        return pd.DataFrame(columns=["Plan", "Engine", "Purpose"])
    catalogue = plan_catalog()
    return catalogue[catalogue["Plan"].isin(profile.engine_plan_keys)].reset_index(drop=True)


def reference_binding_table(project_root: str | Path, module_key: str) -> pd.DataFrame:
    profile = profile_for(module_key)
    project = Path(project_root).resolve()
    config_path = project / "config" / "step136_reference_bindings.json"
    data: dict[str, Any] = {}
    if config_path.is_file():
        with contextlib.suppress(Exception):
            data = json.loads(config_path.read_text(encoding="utf-8"))
    module_bindings = dict((data.get("modules") or {}).get(module_key) or {})
    asset_root = Path(os.environ.get("BIOINTEL_REFERENCE_ASSETS_DIR") or project / "data" / "reference_assets").resolve()
    rows: list[dict[str, Any]] = []
    for requirement in profile.reference_assets:
        binding = dict(module_bindings.get(requirement) or {})
        relative = str(binding.get("path", "")).strip()
        expected = str(binding.get("sha256", "")).strip().lower()
        status = "Not bound"
        actual = ""
        size = 0
        resolved = None
        if relative:
            candidate = (asset_root / relative).resolve()
            try:
                candidate.relative_to(asset_root)
                resolved = candidate
            except ValueError:
                status = "Unsafe path blocked"
            if resolved is not None:
                if resolved.is_file():
                    size = resolved.stat().st_size
                    actual = _sha256_path(resolved)
                    status = "Verified" if expected and actual == expected else "Checksum mismatch" if expected else "Present; checksum not pinned"
                else:
                    status = "Missing file"
        rows.append({
            "Reference asset": requirement,
            "Binding": relative or "—",
            "Expected SHA-256": expected or "—",
            "Actual SHA-256": actual or "—",
            "Size bytes": size,
            "Status": status,
        })
    return pd.DataFrame(rows)


@lru_cache(maxsize=128)
def _detect_engine_cached(key: str, timeout_seconds: float) -> Any:
    return detect_engine(key, timeout_seconds=timeout_seconds)


def engine_readiness(module_key: str, *, timeout_seconds: float = 2.0) -> pd.DataFrame:
    profile = profile_for(module_key)
    if not profile.optional_engines:
        return pd.DataFrame(columns=["Engine", "Key", "Available", "Executable", "Version", "Category", "Capabilities", "Reference data", "GPU optional", "Installation note"])
    rows = []
    for key in profile.optional_engines:
        try:
            status = _detect_engine_cached(key, float(timeout_seconds))
            rows.append({
                "Engine": status.label,
                "Key": status.key,
                "Available": bool(status.available),
                "Executable": status.executable or "Not found",
                "Version": status.version,
                "Category": status.category,
                "Capabilities": ", ".join(status.capabilities),
                "Reference data": ", ".join(status.required_databases) or "None declared",
                "GPU optional": bool(status.gpu_optional),
                "Installation note": status.note,
            })
        except Exception as exc:
            rows.append({"Engine": key, "Key": key, "Available": False, "Executable": "Probe failed", "Version": "Unknown", "Category": "", "Capabilities": "", "Reference data": "", "GPU optional": False, "Installation note": f"{type(exc).__name__}: {exc}"})
    return pd.DataFrame(rows)


def pipeline_readiness(module_key: str, *, source_name: str = "", source_head: bytes = b"") -> dict[str, Any]:
    profile = profile_for(module_key)
    detected = detect_native_format(source_name, source_head, preferred_viewer=profile.preferred_viewer) if source_name else "not_selected"
    engines = engine_readiness(module_key)
    available = int(engines["Available"].sum()) if not engines.empty else 0
    return {
        "module_key": module_key,
        "profile": profile.title,
        "detected_format": detected,
        "built_in_stages": len(profile.builtin_stages),
        "optional_engines": len(profile.optional_engines),
        "available_engines": available,
        "engine_ready": bool(profile.optional_engines and available == len(profile.optional_engines)),
        "references_required": len(profile.reference_assets),
        "external_execution_state": "ready" if profile.optional_engines and available == len(profile.optional_engines) else "blocked_or_partial",
        "boundary": profile.boundary,
    }


def stage_for_background(project_root: str | Path, source: Any, module_key: str) -> dict[str, Any]:
    profile = profile_for(module_key)
    root = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or Path(project_root) / "UserData").resolve()
    target_dir = root / "staged_uploads" / "step136" / module_key
    target_dir.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix="biointel-step136-stage-"))
    try:
        staged, owned = stage_native_source(source, directory=temporary_dir, maximum_bytes=profile.maximum_bytes)
        if not _matches_extension(staged.name, profile.accepted_extensions):
            raise ValueError(
                f"Unsupported native input for {module_key}: {staged.name}. "
                f"Allowed extensions: {', '.join(profile.accepted_extensions)}"
            )
        digest = _sha256_path(staged)
        target = target_dir / f"{digest[:16]}-{_safe_name(staged.name)}"
        if not target.exists():
            temporary_target = target.with_suffix(target.suffix + ".partial")
            shutil.copyfile(staged, temporary_target)
            if _sha256_path(temporary_target) != digest:
                temporary_target.unlink(missing_ok=True)
                raise IOError("Staged scientific file failed checksum verification")
            temporary_target.replace(target)
        return {
            "path": str(target),
            "sha256": digest,
            "size_bytes": target.stat().st_size,
            "module_key": module_key,
            "source_name": target.name,
        }
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


def submit_native_pipeline_job(
    project_root: str | Path,
    module_key: str,
    staged: dict[str, Any],
    *,
    max_records: int = 100_000,
    priority: int = 80,
) -> JobRecord:
    profile = profile_for(module_key)
    queue = LocalJobQueue(runtime_database_path(Path(project_root), "jobs.sqlite3"))
    payload = {
        "module_key": module_key,
        "path": str(staged["path"]),
        "source_sha256": str(staged["sha256"]),
        "max_records": max(1_000, min(int(max_records), MAX_BACKGROUND_PREVIEW_RECORDS)),
        "preferred_viewer": profile.preferred_viewer,
        "profile_schema": "biointel.step136.native_pipeline.v1",
    }
    return queue.submit(
        "nextgen_native_pipeline",
        payload,
        priority=priority,
        max_attempts=3,
        stages=list(profile.builtin_stages),
        resources={"threads": min(4, MAX_ENGINE_THREADS), "memory_gb": 4, "maximum_bytes": profile.maximum_bytes},
        estimated_seconds=max(5.0, float(staged.get("size_bytes", 0)) / (25 * 1024 * 1024)),
    )


class _UploadProxy:
    def __init__(self, path: Path) -> None:
        self.name = path.name
        self._path = path

    def getvalue(self) -> bytes:
        return self._path.read_bytes()


def _bounded_module_analysis(module_key: str, source: Path) -> dict[str, Any]:
    if source.stat().st_size > MAX_INLINE_BYTES:
        return {"state": "skipped_large_file", "reason": "Module analysis conversion is limited to 100 MB; native parsing remains available."}
    try:
        raw = read_upload(_UploadProxy(source), module_key)
        if raw.empty:
            return {"state": "no_module_rows", "reason": "The native parser produced metadata/QC only; join required scientific evidence before module analysis."}
        module = MODULE_BY_KEY[module_key]
        frame = normalise(raw, module)
        result, summary, secondary, extras = analyse(frame, module, 0.7)
        return {
            "state": "completed",
            "input_rows": int(len(frame)),
            "result_rows": int(len(result)),
            "summary": summary,
            "frame": frame,
            "result": result,
            "secondary": secondary,
            "extras": extras,
        }
    except Exception as exc:
        return {"state": "safe_conversion_block", "reason": f"{type(exc).__name__}: {exc}"}


def _write_frame(frame: pd.DataFrame | None, path: Path) -> str | None:
    if frame is None or frame.empty:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression="gzip")
    return str(path)


def execute_native_pipeline_job(
    project_root: str | Path,
    payload: dict[str, Any],
    *,
    job_id: str,
    progress: Callable[[float, str, str], None] | None = None,
    control: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    module_key = str(payload.get("module_key", ""))
    profile = profile_for(module_key)
    root = Path(project_root).resolve()
    user_root = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or root / "UserData").resolve()
    allowed = (user_root / "staged_uploads").resolve()
    source = Path(str(payload.get("path", ""))).expanduser().resolve()
    try:
        source.relative_to(allowed)
    except ValueError as exc:
        raise ValueError("Native module pipeline path is outside the protected staging directory") from exc
    if not source.is_file():
        raise FileNotFoundError(source)
    if not _matches_extension(source.name, profile.accepted_extensions):
        raise ValueError(f"Staged file extension is not permitted for {module_key}: {source.name}")
    if source.stat().st_size > profile.maximum_bytes:
        raise ValueError("Scientific file exceeds the module's configured 1 GB limit")
    expected = str(payload.get("source_sha256", ""))
    actual = _sha256_path(source)
    if expected and actual != expected:
        raise ValueError("Staged source checksum no longer matches the submitted job")

    def emit(percent: float, stage: str, message: str) -> None:
        if progress is not None:
            progress(percent, stage, message)
        if control is not None:
            control({"stage": stage, "progress_percent": percent, "source_sha256": actual})

    output_dir = user_root / "native_results" / module_key / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    emit(8, "checksum", "Source path, size and SHA-256 verified")
    result = parse_native_path(
        source,
        preferred_viewer=profile.preferred_viewer,
        max_records=max(1_000, min(int(payload.get("max_records", 100_000)), MAX_BACKGROUND_PREVIEW_RECORDS)),
    )
    emit(42, "native_parse", f"Decoded {result.record_count:,} bounded native records")

    native_primary = _write_frame(result.primary, output_dir / "native_primary.csv.gz")
    secondary_files: dict[str, str] = {}
    for key, frame in result.secondary.items():
        written = _write_frame(frame, output_dir / f"native_{_safe_name(key)}.csv.gz")
        if written:
            secondary_files[key] = written

    analysis = _bounded_module_analysis(module_key, source)
    analysis_files: dict[str, Any] = {}
    if analysis.get("state") == "completed":
        emit(68, "module_analysis", "Converted native input into the module schema and ran bounded scientific screening")
        analysis_files["normalised_input"] = _write_frame(analysis.pop("frame", None), output_dir / "module_input.csv.gz")
        analysis_files["result"] = _write_frame(analysis.pop("result", None), output_dir / "module_result.csv.gz")
        analysis_files["secondary"] = _write_frame(analysis.pop("secondary", None), output_dir / "module_secondary.csv.gz")
        extras = analysis.pop("extras", {}) or {}
        analysis_files["extras"] = {}
        for key, frame in extras.items():
            written = _write_frame(frame, output_dir / f"module_extra_{_safe_name(key)}.csv.gz")
            if written:
                analysis_files["extras"][key] = written
    else:
        emit(68, "module_analysis", "Native QC completed; module conversion remains blocked until required fields/evidence are available")

    readiness = pipeline_readiness(module_key, source_name=source.name, source_head=source.read_bytes()[:65536])
    engines = engine_readiness(module_key)
    readiness["engine_rows"] = engines.to_dict(orient="records")
    readiness["reference_assets"] = list(profile.reference_assets)
    readiness["engine_plan_keys"] = list(profile.engine_plan_keys)
    emit(84, "readiness", "External-engine and reference-asset readiness evaluated")

    native_summary = result.summary()
    native_summary.pop("preview_array", None)
    manifest = {
        "schema": "biointel.step136.native_pipeline_result.v1",
        "job_id": job_id,
        "module_key": module_key,
        "module_title": MODULE_BY_KEY[module_key].title,
        "source": {
            "path": str(source),
            "name": source.name,
            "size_bytes": source.stat().st_size,
            "sha256": actual,
            "detected_format": result.format_key,
        },
        "native_parse": native_summary,
        "module_analysis": analysis,
        "readiness": readiness,
        "artifacts": {
            "native_primary": native_primary,
            "native_secondary": secondary_files,
            "module": analysis_files,
        },
        "scientific_boundary": profile.boundary,
        "created_at_utc": _utc_now(),
    }
    manifest_path = output_dir / "pipeline_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8")
    emit(96, "finalize", "Pipeline manifest and checksum-bound artifacts written")
    return {**manifest, "manifest_path": str(manifest_path)}


def job_table(records: Iterable[JobRecord]) -> pd.DataFrame:
    rows = []
    for record in records:
        payload = record.payload or {}
        rows.append({
            "Job ID": record.job_id,
            "Module": payload.get("module_key", ""),
            "Status": record.status,
            "Progress": float(record.progress_percent),
            "Stage": record.current_stage,
            "Attempts": f"{record.attempts}/{record.max_attempts}",
            "Source": Path(str(payload.get("path", ""))).name,
            "Created": record.created_at_utc,
            "Error": record.error,
        })
    return pd.DataFrame(rows)


def validate_profiles() -> dict[str, Any]:
    missing = sorted(set(NEW_BIOMEDICAL_KEYS) - set(PROFILES))
    extra = sorted(set(PROFILES) - set(NEW_BIOMEDICAL_KEYS))
    duplicate_extensions = {
        key: sorted({ext for ext in profile.accepted_extensions if profile.accepted_extensions.count(ext) > 1})
        for key, profile in PROFILES.items()
    }
    duplicate_extensions = {key: values for key, values in duplicate_extensions.items() if values}
    return {
        "module_count": len(PROFILES),
        "missing_profiles": missing,
        "extra_profiles": extra,
        "duplicate_extensions": duplicate_extensions,
        "valid": not missing and not extra and not duplicate_extensions and len(PROFILES) == 15,
    }


def render_native_execution_v136_panel(module_key: str, *, key_prefix: str) -> None:
    import streamlit as st

    profile = profile_for(module_key)

    @st.cache_data(ttl=120, show_spinner=False)
    def _cached_engines(key: str) -> pd.DataFrame:
        return engine_readiness(key)

    st.markdown("### Native raw-data & execution pipeline")
    st.caption("Checksum-bound native parsing, resumable background execution and explicit external-engine/reference readiness.")
    overview = pipeline_readiness(module_key)
    cols = st.columns(4)
    cols[0].metric("Native formats", len(profile.accepted_extensions))
    cols[1].metric("Built-in stages", len(profile.builtin_stages))
    cols[2].metric("Optional engines", len(profile.optional_engines))
    cols[3].metric("Reference assets", len(profile.reference_assets))

    with st.expander("Pipeline contract", expanded=False):
        st.dataframe(profile_table(module_key), width="stretch", hide_index=True)
        plans = engine_plan_table(module_key)
        if not plans.empty:
            st.markdown("**Protected external-engine plans**")
            st.dataframe(plans, width="stretch", hide_index=True)
        st.markdown("**Reference requirements**")
        st.dataframe(reference_binding_table(PROJECT_ROOT_FALLBACK(), module_key), width="stretch", hide_index=True)
        st.warning(profile.boundary)

    engines = _cached_engines(module_key)
    if not engines.empty:
        st.markdown("#### Local engine readiness")
        st.dataframe(engines, width="stretch", hide_index=True)
    else:
        st.info("This module's Step 136 pipeline is fully built-in; no external executable is required for schema/QC and planning.")

    upload = st.file_uploader(
        "Native scientific input",
        type=streamlit_upload_types(module_key),
        key=f"{key_prefix}_native_upload",
        help="Files are checksum-verified and limited to 1 GB. Large files are staged and parsed through the persistent local job queue.",
    )
    max_records = st.number_input(
        "Maximum bounded preview records",
        min_value=1_000,
        max_value=MAX_BACKGROUND_PREVIEW_RECORDS,
        value=100_000,
        step=10_000,
        key=f"{key_prefix}_native_records",
    )
    if upload is not None:
        size = int(getattr(upload, "size", 0) or len(upload.getvalue()))
        st.caption(f"Selected: `{upload.name}` · {size / (1024 * 1024):.2f} MB")
        inspect_col, queue_col = st.columns(2)
        if inspect_col.button("Inspect native input", key=f"{key_prefix}_inspect_native", width="stretch"):
            try:
                with st.spinner("Parsing a bounded native preview…"):
                    parsed = parse_native_source(
                        upload,
                        preferred_viewer=profile.preferred_viewer,
                        max_records=min(int(max_records), 100_000),
                )
                st.success(f"Detected {parsed.format_key}; loaded {parsed.record_count:,} preview records.")
                render_operational_canvas(
                    "Native input inspection",
                    parsed.summary(),
                    workflow=("Format detection", "Bounded parse", "Quality review", "Scientific handoff"),
                )
                if not parsed.primary.empty:
                    st.dataframe(parsed.primary.head(1_000), width="stretch", hide_index=True)
                for secondary_key, frame in parsed.secondary.items():
                    if not frame.empty:
                        with st.expander(f"{secondary_key} ({len(frame):,} records)"):
                            st.dataframe(frame.head(1_000), width="stretch", hide_index=True)
            except Exception as exc:
                st.error(f"Native inspection failed safely: {type(exc).__name__}: {exc}")
        if queue_col.button("Stage & queue resumable pipeline", key=f"{key_prefix}_queue_native", width="stretch"):
            try:
                staged = stage_for_background(PROJECT_ROOT_FALLBACK(), upload, module_key)
                job = submit_native_pipeline_job(PROJECT_ROOT_FALLBACK(), module_key, staged, max_records=int(max_records))
                st.session_state[f"{key_prefix}_last_native_job"] = job.job_id
                st.success(f"Queued `{job.job_id}` with checksum `{staged['sha256'][:16]}…`.")
            except Exception as exc:
                st.error(f"Queue submission failed safely: {type(exc).__name__}: {exc}")

    project_root = PROJECT_ROOT_FALLBACK()
    queue = LocalJobQueue(runtime_database_path(project_root, "jobs.sqlite3"))
    jobs = [record for record in queue.list(limit=100) if record.job_type == "nextgen_native_pipeline" and record.payload.get("module_key") == module_key]
    if jobs:
        st.markdown("#### Native pipeline jobs")
        st.dataframe(job_table(jobs), width="stretch", hide_index=True)
        selected_id = st.selectbox("Job controls", [record.job_id for record in jobs], key=f"{key_prefix}_job_select")
        selected = queue.get(selected_id)
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("Run one worker cycle", key=f"{key_prefix}_worker", width="stretch"):
            try:
                from biointel.jobs.worker import LocalWorker

                result = LocalWorker(project_root, worker_id="step136-ui-worker").run_once()
                st.success(result.message) if result.status == "completed" else st.info(result.message)
                st.rerun()
            except Exception as exc:
                st.error(f"Worker failed safely: {type(exc).__name__}: {exc}")
        if c2.button("Pause", key=f"{key_prefix}_pause", disabled=selected.status not in {"queued", "running"}, width="stretch"):
            queue.request_pause(selected_id)
            st.rerun()
        if c3.button("Resume", key=f"{key_prefix}_resume", disabled=selected.status != "paused", width="stretch"):
            queue.resume(selected_id)
            st.rerun()
        if c4.button("Cancel", key=f"{key_prefix}_cancel", disabled=selected.status in {"completed", "cancelled"}, width="stretch"):
            queue.request_cancel(selected_id)
            st.rerun()
        timeline = queue.timeline(selected_id)
        with st.expander("Job timeline and artifacts", expanded=selected.status in {"failed", "completed"}):
            render_operational_canvas(
                "Job timeline and artifacts",
                {"job_id": selected_id, "events": timeline},
                workflow=("Queued", "Running", "Verification", "Completed"),
            )


def PROJECT_ROOT_FALLBACK() -> Path:
    return Path(__file__).resolve().parents[3]


__all__ = [
    "MAX_BACKGROUND_PREVIEW_RECORDS",
    "MAX_INLINE_BYTES",
    "NativePipelineProfile",
    "PROFILES",
    "engine_plan_table",
    "engine_readiness",
    "execute_native_pipeline_job",
    "job_table",
    "pipeline_readiness",
    "profile_for",
    "profile_table",
    "reference_binding_table",
    "reference_table",
    "render_native_execution_v136_panel",
    "stage_for_background",
    "streamlit_upload_types",
    "submit_native_pipeline_job",
    "validate_profiles",
]
