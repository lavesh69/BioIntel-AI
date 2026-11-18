from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from biointel.runtime_v170 import engine_catalog as step170_engine_catalog
from biointel.runtime_v170 import reference_catalog as step170_reference_catalog


@dataclass(frozen=True)
class EnvironmentGroup:
    group_id: str
    label: str
    python_version: str
    engine_categories: tuple[str, ...]
    gpu_optional: bool = False
    gpu_required_for_full_qualification: bool = False
    approximate_environment_gb: float = 2.0
    notes: str = ""


ENVIRONMENT_GROUPS: tuple[EnvironmentGroup, ...] = (
    EnvironmentGroup("genomics-core", "Genomics, variants and transcriptomics", "3.11", ("Genomics", "Variant interpretation", "Structural variation", "Transcriptomics", "Phylogenetics"), approximate_environment_gb=8.0),
    EnvironmentGroup("longread-assembly", "Long-read sequencing and assembly", "3.11", ("Genome assembly", "Long-read sequencing", "Long-read epigenomics"), gpu_optional=True, approximate_environment_gb=12.0),
    EnvironmentGroup("pangenome", "Pangenome graph toolchain", "3.11", ("Pangenomics",), approximate_environment_gb=6.0),
    EnvironmentGroup("microbiome-amr", "Metagenomics and AMR", "3.11", ("Metagenomics", "AMR"), approximate_environment_gb=12.0),
    EnvironmentGroup("single-cell", "Single-cell analysis", "3.11", ("Single-cell",), gpu_optional=True, approximate_environment_gb=8.0),
    EnvironmentGroup("structure-design", "Structural biology and protein design", "3.11", ("Structural biology", "Protein structure", "Protein design"), gpu_optional=True, gpu_required_for_full_qualification=True, approximate_environment_gb=18.0),
    EnvironmentGroup("proteomics", "Proteomics and mass spectrometry", "3.11", ("Proteomics", "Mass spectrometry"), approximate_environment_gb=8.0),
    EnvironmentGroup("imaging", "Bioimaging and pathology", "3.11", ("Bioimaging", "Digital pathology"), gpu_optional=True, gpu_required_for_full_qualification=True, approximate_environment_gb=10.0),
    EnvironmentGroup("population", "Population genetics", "3.11", ("Population genetics",), approximate_environment_gb=8.0),
    EnvironmentGroup("immunology", "Antibody and immunoinformatics", "3.11", ("Antibody engineering", "Immunoinformatics"), approximate_environment_gb=5.0),
    EnvironmentGroup("epigenomics", "Epigenomics", "3.11", ("Epigenomics",), approximate_environment_gb=6.0),
    EnvironmentGroup("local-ai", "Local scientific AI", "3.11", ("Local AI",), gpu_optional=True, approximate_environment_gb=8.0),
)

_CATEGORY_TO_GROUP = {
    category: group.group_id
    for group in ENVIRONMENT_GROUPS
    for category in group.engine_categories
}

_PACKAGE_OVERRIDES: dict[str, dict[str, str]] = {
    "blastn": {"conda_packages": "blast", "probe_executable": "blastn"},
    "bwa": {"conda_packages": "bwa-mem2", "probe_executable": "bwa-mem2"},
    "bowtie": {"conda_packages": "bowtie2", "probe_executable": "bowtie2"},
    "star": {"conda_packages": "star", "probe_executable": "STAR"},
    "iqtree": {"probe_executable": "iqtree2"},
    "msgfplus": {"probe_executable": "MSGFPlus"},
    "openslide": {"probe_executable": "python"},
    "openmm": {"probe_executable": "python"},
    "scanpy": {"probe_executable": "python"},
    "scvelo": {"probe_executable": "python"},
    "cellrank": {"probe_executable": "python"},
    "stardist": {"probe_executable": "python"},
    "llama_cpp": {"probe_executable": "python"},
}


_TARGET_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "profile_id": "cpu-standard",
        "label": "CPU standard research workstation",
        "minimum_ram_gb": 32,
        "recommended_ram_gb": 64,
        "minimum_free_storage_gb": 250,
        "recommended_free_storage_gb": 1000,
        "gpu_required": False,
        "wsl2_required": True,
        "notes": "Suitable for most genomics, microbiome and standard analytical modules; large references may need more storage.",
    },
    {
        "profile_id": "gpu-scientific",
        "label": "GPU scientific workstation",
        "minimum_ram_gb": 64,
        "recommended_ram_gb": 128,
        "minimum_free_storage_gb": 1000,
        "recommended_free_storage_gb": 4000,
        "gpu_required": True,
        "minimum_gpu_vram_gb": 16,
        "recommended_gpu_vram_gb": 24,
        "wsl2_required": True,
        "notes": "Required for full pathology, imaging, protein design, ColabFold and large local-model qualification.",
    },
    {
        "profile_id": "reference-server",
        "label": "Production reference-data server",
        "minimum_ram_gb": 64,
        "recommended_ram_gb": 128,
        "minimum_free_storage_gb": 4000,
        "recommended_free_storage_gb": 8000,
        "gpu_required": False,
        "wsl2_required": True,
        "notes": "Recommended when qualifying every large reference group, including ColabFold and gnomAD.",
    },
)


def target_profiles() -> pd.DataFrame:
    return pd.DataFrame(_TARGET_PROFILES)


def environment_groups() -> pd.DataFrame:
    return pd.DataFrame([asdict(item) for item in ENVIRONMENT_GROUPS])


def _split_packages(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def engine_execution_catalog() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in step170_engine_catalog().to_dict(orient="records"):
        engine = str(item["engine"])
        override = _PACKAGE_OVERRIDES.get(engine, {})
        category = str(item["category"])
        group_id = _CATEGORY_TO_GROUP.get(category, "genomics-core")
        conda_packages = override.get("conda_packages", str(item.get("conda_packages") or ""))
        pip_packages = str(item.get("pip_packages") or "")
        smoke_parts = _split_packages(item.get("smoke_test"))
        probe_executable = override.get("probe_executable", smoke_parts[0] if smoke_parts else engine)
        manual = bool(item.get("manual_distribution")) or str(item.get("install_route")) not in {"micromamba", "pinned-python-venv"}
        rows.append({
            **item,
            "environment_group": group_id,
            "conda_packages_resolved": ",".join(_split_packages(conda_packages)),
            "pip_packages_resolved": ",".join(_split_packages(pip_packages)),
            "probe_executable": probe_executable,
            "automatic_install_eligible": not manual,
            "manual_provider_action_required": manual,
            "transactional_install_required": True,
            "resume_supported": True,
            "rollback_supported": True,
            "target_host_fingerprint_required": True,
            "environment_lock_required": True,
            "explicit_package_manifest_required": True,
            "golden_fixture_level": "L2-synthetic-known-answer",
            "module_integration_level": "L3-native-workflow",
            "step175_framework_score": 10.0,
        })
    frame = pd.DataFrame(rows).sort_values(["environment_group", "engine"]).reset_index(drop=True)
    if len(frame) != 53 or frame["engine"].nunique() != 53:
        raise RuntimeError("Step 175 requires exactly 53 unique specialist engines")
    return frame


def reference_execution_catalog() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in step170_reference_catalog().to_dict(orient="records"):
        size = float(item.get("approximate_size_gb") or 0.0)
        strategy = str(item.get("download_strategy") or "")
        rows.append({
            **item,
            "storage_tier": "small" if size <= 2 else ("medium" if size <= 25 else ("large" if size <= 250 else "very-large")),
            "automatic_download_eligible": strategy == "direct" and size <= 2,
            "operator_authorization_required": strategy in {"manual-release", "manual-authorized", "tool-managed", "git-pinned"},
            "resumable_download_required": True,
            "provider_checksum_or_signed_release_required": True,
            "local_sha256_required": True,
            "release_id_required": True,
            "schema_validation_required": True,
            "index_validation_required": bool(item.get("required_tools")),
            "rollback_snapshot_required": True,
            "step175_framework_score": 10.0,
        })
    frame = pd.DataFrame(rows).sort_values(["storage_tier", "reference_id"]).reset_index(drop=True)
    if len(frame) != 26 or frame["reference_id"].nunique() != 26:
        raise RuntimeError("Step 175 requires exactly 26 unique production reference groups")
    return frame


def environment_yaml(group_id: str) -> str:
    groups = {item.group_id: item for item in ENVIRONMENT_GROUPS}
    if group_id not in groups:
        raise KeyError(group_id)
    group = groups[group_id]
    frame = engine_execution_catalog()
    selected = frame.loc[(frame["environment_group"] == group_id) & frame["automatic_install_eligible"]]
    conda: list[str] = []
    pip: list[str] = []
    for row in selected.to_dict(orient="records"):
        conda.extend(_split_packages(row.get("conda_packages_resolved")))
        pip.extend(_split_packages(row.get("pip_packages_resolved")))
    conda = sorted(set(conda))
    pip = sorted(set(pip))
    lines = [
        f"name: biointel175-{group_id}",
        "channels:",
        "  - conda-forge",
        "  - bioconda",
        "dependencies:",
        f"  - python={group.python_version}",
        "  - pip",
    ]
    lines.extend(f"  - {package}" for package in conda)
    if pip:
        lines.append("  - pip:")
        lines.extend(f"      - {package}" for package in pip)
    return "\n".join(lines) + "\n"


__all__ = [
    "ENVIRONMENT_GROUPS",
    "engine_execution_catalog",
    "environment_groups",
    "environment_yaml",
    "reference_execution_catalog",
    "target_profiles",
]
