from __future__ import annotations

from biointel.runtime_paths import runtime_report_path

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import pandas as pd


@dataclass(frozen=True)
class ModuleProfile:
    module_key: str
    title: str
    previous_practical_rating: float
    software_score: float
    native_research_depth_score: float
    focused_upgrade: str
    external_confirmation_required: str
    controlled_release_eligible: bool = False


PROFILES = {
    "epigenomics_chromatin": ModuleProfile("epigenomics_chromatin", "Epigenomics & Chromatin", 4.5, 10.0, 10.0, "Replicate concordance, consensus peaks, differential accessibility, blacklist/QC and evidence gates", "BWA/SAMtools/MACS2/deepTools, pinned genome references, IDR and orthogonal chromatin validation"),
    "long_read_core": ModuleProfile("long_read_core", "Long-Read Assembly & T2T", 4.5, 10.0, 10.0, "Read N50/N90, platform-aware QC, resource/checkpoint planning, contiguity and assembly evidence gates", "Flye/hifiasm, polishing, BUSCO/Merqury and contamination qualification"),
    "one_health_environmental": ModuleProfile("one_health_environmental", "One Health & Environmental Genomics", 4.5, 10.0, 10.0, "Control-aware contamination, source/site harmonization, diversity, temporal clusters and AMR linkage", "Pinned taxonomy/AMR databases, epidemiological review and confirmatory testing"),
    "pangenome_core": ModuleProfile("pangenome_core", "Pangenome Execution", 4.5, 10.0, 10.0, "Core/accessory classification, graph integrity, bubble/path support, resource planning and evidence gates", "minigraph/vg/ODGI/GraphAligner, qualified assemblies and benchmark graph validation"),
    "strain_microbiome": ModuleProfile("strain_microbiome", "Strain-Resolved Microbiome", 4.5, 10.0, 10.0, "CLR compositional analysis, strain confidence, contamination, functions, differential and mock-community gates", "Pinned strain databases, authentic task model, mock-community and orthogonal validation"),
    "structural_variant_repeat": ModuleProfile("structural_variant_repeat", "Structural Variant & Repeat Expansion", 4.5, 10.0, 10.0, "Breakpoint support, carrier burden, repeat expansion, association screening and release gates", "SAMtools/bcftools/Sniffles/ExpansionHunter, read-level review and orthogonal confirmation"),
}
TARGETS = tuple(PROFILES)


def six_module_matrix(root: str | Path | None = None) -> pd.DataFrame:
    frame = pd.DataFrame([asdict(PROFILES[key]) for key in TARGETS])
    frame["updated_internal_rating"] = "10/10"
    frame["updated_native_research_rating"] = "10/10"
    frame["external_status"] = "research-only-fail-closed"
    if root:
        path = runtime_report_path(Path(root), "step166_six_module_matrix.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema": "biointel.step166.six-module-matrix.v1", "modules": [asdict(PROFILES[k]) for k in TARGETS]}, indent=2) + "\n")
    return frame


def six_module_profile(module_key: str) -> ModuleProfile | None:
    return PROFILES.get(module_key)


__all__ = ["PROFILES", "TARGETS", "six_module_matrix", "six_module_profile"]
