from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sqlite3
from typing import Iterable

import pandas as pd

from biointel.database.core import managed_connect
from .profiles import MODULE_PROFILES
from .native_workflows import is_native_engine


@dataclass(frozen=True)
class ToolchainStatus:
    engine: str
    available: bool
    detected: str
    kind: str
    install_hint: str
    modules: tuple[str, ...]


ALIASES: dict[str, tuple[str, ...]] = {
    "bwa": ("bwa", "bwa-mem2"), "samtools": ("samtools",), "macs2": ("macs2", "macs3"),
    "deeptools": ("bamCoverage", "deepTools"), "openms": ("OpenMSInfo", "FileInfo", "FeatureFinderMetabo"),
    "netmhcpan": ("netMHCpan",), "netmhciipan": ("netMHCIIpan",), "anarci": ("ANARCI", "anarci"),
    "igblast": ("igblastn", "igblastp"), "vina": ("vina",), "gromacs": ("gmx", "gmx_mpi"),
    "bcftools": ("bcftools",), "whatshap": ("whatshap",), "vep": ("vep",),
    "openslide": ("openslide-show-properties",), "cellpose": ("cellpose",), "scanpy": ("scanpy",),
    "scvelo": ("scvelo",), "cellrank": ("cellrank",), "stardist": ("stardist",),
    "bowtie": ("bowtie", "bowtie2"), "bowtie2": ("bowtie2",), "blastn": ("blastn",),
    "comet": ("comet",), "msgfplus": ("MSGFPlus", "msgfplus"), "kraken2": ("kraken2",),
    "bracken": ("bracken",), "humann": ("humann", "humann3"), "minimap2": ("minimap2",),
    "plink2": ("plink2",), "regenie": ("regenie",), "saige": ("SAIGE",), "sniffles": ("sniffles",),
    "expansionhunter": ("ExpansionHunter", "expansionhunter"), "rmats": ("rmats.py", "rmats"),
    "majiq": ("majiq",), "suppa2": ("suppa.py", "suppa2"), "flye": ("flye",),
    "hifiasm": ("hifiasm",), "busco": ("busco",), "merqury": ("merqury.sh",),
    "dorado": ("dorado",), "modkit": ("modkit",), "minigraph": ("minigraph",), "vg": ("vg",),
    "odgi": ("odgi",), "graphaligner": ("GraphAligner",), "proteinmpnn": ("protein_mpnn_run.py",),
    "rfdiffusion": ("run_inference.py",), "colabfold": ("colabfold_batch",), "llama_cpp": ("llama-cli", "llama-server"),
    "amrfinderplus": ("amrfinder",), "resfinder": ("run_resfinder.py", "resfinder"),
    "fastqc": ("fastqc", "fastqc.exe"), "multiqc": ("multiqc", "multiqc.exe"),
    "fastp": ("fastp", "fastp.exe"), "cutadapt": ("cutadapt", "cutadapt.exe"),
    "snpeff": ("snpEff", "snpEff.exe", "snpeff"),
    "interproscan": ("interproscan.sh", "interproscan", "interproscan.bat"),
    "hmmer": ("hmmsearch", "hmmsearch.exe"), "blastp": ("blastp", "blastp.exe"),
    "mosdepth": ("mosdepth", "mosdepth.exe"), "picard": ("picard", "picard.exe"),
    "salmon": ("salmon", "salmon.exe"), "kallisto": ("kallisto", "kallisto.exe"),
}

PYTHON_PACKAGES: dict[str, str] = {
    "openmm": "openmm", "scanpy": "scanpy", "scvelo": "scvelo", "cellrank": "cellrank",
    "stardist": "stardist", "openslide": "openslide", "cellpose": "cellpose", "anarci": "anarci",
    "whatshap": "whatshap", "deeptools": "deeptools", "llama_cpp": "llama_cpp",
}

INSTALL_HINTS: dict[str, str] = {
    "openmm": "Install the pinned OpenMM Python environment from the scientific-extras installer.",
    "scanpy": "Install the pinned Scanpy/AnnData environment from the scientific-extras installer.",
    "cellpose": "Install Cellpose plus approved model weights; record model checksum and GPU/CPU runtime.",
    "gromacs": "Install a validated GROMACS build or configure WSL; verify force fields and executable checksum.",
    "kraken2": "Install Kraken2/Bracken and register a versioned taxonomy database outside the core ZIP.",
    "vep": "Install Ensembl VEP with a genome-build-matched offline cache and plugins.",
    "fastqc": "Install FastQC and preserve per-file HTML/ZIP reports with checksums.",
    "multiqc": "Install MultiQC and pin its version/configuration for run-level aggregation.",
    "fastp": "Install fastp and preserve JSON/HTML reports plus trimmed-read hashes.",
    "snpeff": "Install SnpEff with a genome-build-matched, checksum-pinned database.",
    "interproscan": "Install InterProScan with licensed/pinned member databases.",
    "hmmer": "Install HMMER and register the exact HMM database release and checksum.",
    "salmon": "Install Salmon and register the transcriptome index build and checksum.",
    "kallisto": "Install Kallisto and register the transcriptome index build and checksum.",
}


def _engine_modules() -> dict[str, tuple[str, ...]]:
    mapping: dict[str, list[str]] = {}
    for key, profile in MODULE_PROFILES.items():
        for engine in profile.engines:
            if is_native_engine(engine):
                continue
            mapping.setdefault(engine.lower(), []).append(key)
    return {engine: tuple(sorted(set(modules))) for engine, modules in mapping.items()}


def detect_specialist_toolchains(engines: Iterable[str] | None = None) -> pd.DataFrame:
    mapping = _engine_modules()
    requested = sorted(set(str(e).lower() for e in (engines or mapping)))
    rows: list[dict[str, object]] = []
    for engine in requested:
        path = ""
        for candidate in ALIASES.get(engine, (engine,)):
            found = shutil.which(candidate)
            if found:
                path = found
                break
        package = PYTHON_PACKAGES.get(engine)
        package_ok = bool(package and importlib.util.find_spec(package))
        available = bool(path or package_ok)
        status = ToolchainStatus(
            engine=engine,
            available=available,
            detected=path or (f"Python package: {package}" if package_ok else "Not detected"),
            kind="executable" if path else ("python-package" if package_ok else "missing"),
            install_hint=INSTALL_HINTS.get(engine, f"Install and pin {engine}; verify version, checksum, licence and reference compatibility."),
            modules=mapping.get(engine, ()),
        )
        row = asdict(status)
        row["module_count"] = len(status.modules)
        row["modules"] = ", ".join(status.modules)
        rows.append(row)
    return pd.DataFrame(rows)


def _normalise(value: object) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).lower()))


def _tokens(value: object) -> set[str]:
    stop = {"database", "reference", "release", "data", "annotation", "model", "assets", "asset"}
    return {token for token in _normalise(value).split() if len(token) >= 3 and token not in stop}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _registered_assets(root: Path) -> list[dict[str, object]]:
    db = root / "data" / "reference_assets" / "reference_assets.sqlite3"
    if not db.is_file():
        return []
    connection = managed_connect(db)
    connection.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in connection.execute("SELECT * FROM assets")]
    finally:
        connection.close()
    results: list[dict[str, object]] = []
    for row in rows:
        metadata = {}
        try:
            metadata = json.loads(str(row.get("metadata_json") or "{}"))
        except json.JSONDecodeError:
            metadata = {}
        local_value = str(row.get("local_path") or "").strip()
        local = Path(local_value)
        if local_value and not local.is_absolute():
            local = (root / local).resolve()
        exists = bool(local_value and local.is_file())
        observed = str(row.get("observed_sha256") or "").lower()
        expected = str(row.get("expected_sha256") or "").lower()
        actual = _sha256(local) if exists else ""
        checksum_verified = bool(exists and actual and ((observed and actual == observed) or (expected and actual == expected)))
        results.append({**row, "metadata": metadata, "local_resolved": str(local) if local_value else "", "exists": exists, "actual_sha256": actual, "checksum_verified": checksum_verified})
    return results


def _sidecar_assets(root: Path) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for folder in (root / "data" / "reference_assets", root / "data" / "reference_packs", root / "data" / "public_reference"):
        if not folder.exists():
            continue
        for sidecar in folder.rglob("*.reference.json"):
            try:
                payload = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            local_value = str(payload.get("local_path") or payload.get("path") or "").strip()
            local = (sidecar.parent / local_value).resolve() if local_value else Path()
            exists = bool(local_value and local.is_file())
            expected = str(payload.get("sha256") or "").lower()
            actual = _sha256(local) if exists else ""
            results.append({
                "asset_id": str(payload.get("asset_id") or sidecar.stem),
                "provider": str(payload.get("provider") or ""),
                "version": str(payload.get("version") or ""),
                "status": str(payload.get("status") or "staged"),
                "local_resolved": str(local) if local_value else "",
                "exists": exists,
                "checksum_verified": bool(expected and actual == expected),
                "license_accepted": int(bool(payload.get("license_accepted") or payload.get("licence_accepted"))),
                "metadata": payload,
            })
    return results


def _asset_match_score(reference: str, asset: dict[str, object]) -> float:
    reference_tokens = _tokens(reference)
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    identity = " ".join(
        str(value)
        for value in (
            asset.get("asset_id", ""),
            asset.get("provider", ""),
            metadata.get("reference_name", ""),
            metadata.get("purpose", ""),
            metadata.get("name", ""),
            metadata.get("aliases", ""),
        )
    )
    asset_tokens = _tokens(identity)
    if not reference_tokens or not asset_tokens:
        return 0.0
    intersection = len(reference_tokens & asset_tokens)
    coverage = intersection / len(reference_tokens)
    precision = intersection / len(asset_tokens)
    return 0.7 * coverage + 0.3 * precision


def reference_readiness(root: Path | str, module_keys: Iterable[str] | None = None) -> pd.DataFrame:
    """Report only registry/sidecar-backed reference candidates.

    Filename substring matching is intentionally prohibited because generic words
    such as "genome", "annotation" or "model" created false positives in Step 153.
    """
    root = Path(root).resolve()
    keys = sorted(set(module_keys or MODULE_PROFILES))
    assets = _registered_assets(root) + _sidecar_assets(root)
    rows: list[dict[str, object]] = []
    for key in keys:
        for reference in MODULE_PROFILES[key].references:
            ranked = sorted((( _asset_match_score(reference, asset), asset) for asset in assets), key=lambda item: item[0], reverse=True)
            score, candidate = ranked[0] if ranked else (0.0, {})
            matched = bool(score >= 0.72 and candidate.get("exists"))
            checksum = bool(matched and candidate.get("checksum_verified"))
            licence = bool(matched and int(candidate.get("license_accepted") or 0) == 1)
            version = str(candidate.get("version") or "") if matched else ""
            status = str(candidate.get("status") or "") if matched else "missing"
            qualified = bool(matched and checksum and licence and version and status.lower() in {"active", "verified", "installed", "approved"})
            rows.append({
                "module_key": key,
                "reference": reference,
                "local_candidate_detected": matched,
                "candidate_asset_id": str(candidate.get("asset_id") or "") if matched else "",
                "candidate_paths": str(candidate.get("local_resolved") or "") if matched else "",
                "match_score": float(score) if matched else 0.0,
                "checksum_verified": checksum,
                "licence_accepted": licence,
                "version_declared": bool(version),
                "candidate_version": version,
                "candidate_status": status,
                "qualified_for_use": qualified,
                "qualification_required": not qualified,
                "detection_policy": "exact registry/sidecar identity with >=0.72 token score; filename-only matches prohibited",
            })
    return pd.DataFrame(rows)


def toolchain_summary(frame: pd.DataFrame | None = None) -> dict[str, object]:
    data = detect_specialist_toolchains() if frame is None else frame
    available = int(data["available"].astype(bool).sum()) if not data.empty else 0
    return {
        "schema": "biointel.step154.specialist-toolchain-readiness.v2",
        "engines": int(len(data)),
        "available": available,
        "missing": int(len(data) - available),
        "all_specialist_toolchains_available": bool(len(data) > 0 and available == len(data)),
        "native_fallbacks_are_not_counted_as_specialist_tools": True,
        "reference_filename_false_positives_prohibited": True,
    }
