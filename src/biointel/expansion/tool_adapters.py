from __future__ import annotations

import shutil
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class ToolRequirement:
    executable: str
    purpose: str
    required: bool = False


MODULE_TOOLS: dict[str, tuple[ToolRequirement, ...]] = {
    "epigenomics_chromatin": (
        ToolRequirement("macs2", "ATAC-seq/ChIP-seq peak calling"),
        ToolRequirement("bedtools", "Genomic interval operations"),
        ToolRequirement("samtools", "BAM/CRAM validation and indexing"),
        ToolRequirement("bowtie2", "Read alignment"),
    ),
    "metabolomics_lipidomics": (
        ToolRequirement("msconvert", "Vendor-format conversion to mzML"),
    ),
    "immunoinformatics_vaccine": (
        ToolRequirement("netMHCpan", "External MHC-I binding prediction"),
        ToolRequirement("netMHCIIpan", "External MHC-II binding prediction"),
    ),
    "antibody_biologics": (
        ToolRequirement("anarci", "Antibody numbering and CDR annotation"),
        ToolRequirement("igblastn", "Immunoglobulin sequence alignment"),
    ),
    "docking_dynamics": (
        ToolRequirement("vina", "AutoDock Vina docking"),
        ToolRequirement("obabel", "Ligand/protein format conversion"),
        ToolRequirement("gmx", "GROMACS molecular dynamics"),
    ),
    "pharmacogenomics": (
        ToolRequirement("bcftools", "VCF normalization and filtering"),
        ToolRequirement("whatshap", "Read-backed variant phasing"),
    ),
    "spatial_omics_pathology": (
        ToolRequirement("cellpose", "Image segmentation"),
    ),
    "single_cell_trajectory": (
        ToolRequirement("velocyto", "RNA velocity quantification"),
    ),
    "bioimage_microscopy": (
        ToolRequirement("cellpose", "Deep-learning segmentation"),
        ToolRequirement("ilastik", "Interactive pixel classification"),
    ),
    "genome_editing_safety": (
        ToolRequirement("bowtie", "Genome-wide off-target alignment"),
        ToolRequirement("blastn", "Sequence similarity search"),
    ),
    "proteogenomics_neoantigen": (
        ToolRequirement("comet", "Peptide-spectrum matching"),
        ToolRequirement("msgfplus", "Proteomics database search"),
        ToolRequirement("bcftools", "Variant normalization"),
    ),
    "one_health_environmental": (
        ToolRequirement("kraken2", "Taxonomic classification"),
        ToolRequirement("minimap2", "Read/genome alignment"),
        ToolRequirement("abricate", "AMR gene screening"),
    ),
}


EXECUTABLE_ENGINE_KEYS: dict[str, str] = {
    "macs2": "macs2", "bedtools": "bedtools", "samtools": "samtools", "bowtie2": "bowtie",
    "msconvert": "msconvert", "netMHCpan": "netmhcpan", "netMHCIIpan": "netmhciipan",
    "anarci": "anarci", "igblastn": "igblast", "vina": "vina", "obabel": "obabel",
    "gmx": "gromacs", "bcftools": "bcftools", "whatshap": "whatshap", "cellpose": "cellpose",
    "velocyto": "velocyto", "bowtie": "bowtie", "blastn": "blastn", "comet": "comet",
    "msgfplus": "msgfplus", "kraken2": "kraken2", "minimap2": "minimap2", "abricate": "abricate",
}


def tool_status(module_key: str) -> pd.DataFrame:
    rows = []
    managed: dict[str, dict[str, object]] = {}
    try:
        from biointel.engine_platform_v196.state import EngineStateStore
        inventory = EngineStateStore().inventory()
        if not inventory.empty:
            managed = {str(row["engine"]): row for row in inventory.to_dict(orient="records")}
    except Exception:
        managed = {}
    for requirement in MODULE_TOOLS.get(module_key, ()):
        engine_key = EXECUTABLE_ENGINE_KEYS.get(requirement.executable, requirement.executable.lower())
        state = managed.get(engine_key, {})
        managed_path = str(state.get("executable", "") or "")
        path = shutil.which(requirement.executable) or (managed_path if managed_path and Path(managed_path).is_file() else None)
        qualified = bool(state.get("qualified", 0))
        rows.append({
            "tool": requirement.executable,
            "engine_key": engine_key,
            "purpose": requirement.purpose,
            "installed": path is not None,
            "qualified": qualified,
            "manager_state": str(state.get("state", "not-registered")),
            "detected_path": path or "Not detected",
            "source": "Engine Control Center" if managed_path and path == managed_path else ("System PATH" if path else "Not detected"),
            "required_for_table_analysis": requirement.required,
            "execution_policy": "Runs only when explicitly invoked by the user",
        })
    return pd.DataFrame(rows)


def installed_tool_count(module_key: str) -> tuple[int, int]:
    frame = tool_status(module_key)
    if frame.empty:
        return 0, 0
    return int(frame["installed"].sum()), int(len(frame))


def serialisable_requirements(module_key: str) -> list[dict[str, object]]:
    return [asdict(item) for item in MODULE_TOOLS.get(module_key, ())]
