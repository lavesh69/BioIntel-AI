from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any, Iterable

import pandas as pd

from biointel.native.engines import ENGINE_REGISTRY, detect_engine
from biointel.scientific_depth.native_workflows import is_native_engine
from biointel.scientific_depth.profiles import MODULE_PROFILES


@dataclass(frozen=True)
class ProvisioningSpec:
    engine: str
    label: str
    category: str
    conda_packages: tuple[str, ...]
    pip_packages: tuple[str, ...]
    manual_distribution: bool
    licence_acceptance_required: bool
    model_weights_required: bool
    reference_data_required: bool
    supported_backends: tuple[str, ...]
    version_constraint: str
    smoke_test: tuple[str, ...]
    modules: tuple[str, ...]
    software_recipe_complete: bool


# Exact package identifiers are used when a maintained package is generally
# available. Empty entries deliberately mean that the provider/manual route is
# required; BioIntel never substitutes an unrelated package merely to make a
# readiness indicator green.
_PACKAGE_OVERRIDES: dict[str, dict[str, Any]] = {
    "bowtie": {"conda": ("bowtie2",)},
    "iqtree": {"conda": ("iqtree",)},
    "deeptools": {"conda": ("deeptools",)},
    "openmm": {"conda": ("openmm",), "pip": ("openmm",)},
    "stardist": {"conda": ("stardist",), "pip": ("stardist",)},
    "openslide": {"conda": ("openslide", "openslide-python"), "pip": ("openslide-python",)},
    "cellpose": {"conda": ("cellpose",), "pip": ("cellpose",)},
    "scanpy": {"conda": ("scanpy",), "pip": ("scanpy",)},
    "scvelo": {"conda": ("scvelo",), "pip": ("scvelo",)},
    "cellrank": {"conda": ("cellrank",), "pip": ("cellrank",)},
    "anarci": {"conda": ("anarci",), "pip": ("anarci",)},
    "whatshap": {"conda": ("whatshap",), "pip": ("whatshap",)},
    "openms": {"conda": ("openms",)},
    "openms_featurefinder": {"conda": ("openms",)},
    "llama_cpp": {"pip": ("llama-cpp-python",)},
    "netmhcpan": {"manual": True, "licence": True},
    "netmhciipan": {"manual": True, "licence": True},
    "dorado": {"manual": True, "weights": True},
    "proteinmpnn": {"manual": True, "weights": True},
    "rfdiffusion": {"manual": True, "weights": True},
    "colabfold": {"conda": ("colabfold",), "weights": True},
    "gromacs": {"conda": ("gromacs",)},
    "vep": {"conda": ("ensembl-vep",)},
    "bracken": {"conda": ("bracken",)},
    "humann": {"conda": ("humann",)},
    "expansionhunter": {"conda": ("expansionhunter",)},
    "graphaligner": {"conda": ("graphaligner",)},
    "igblast": {"conda": ("igblast",)},
    "plink2": {"conda": ("plink2",)},
    "saige": {"conda": ("r-saige",)},
    "regenie": {"conda": ("regenie",)},
    "busco": {"conda": ("busco",)},
    "merqury": {"conda": ("merqury",)},
    "vg": {"conda": ("vg",)},
    "odgi": {"conda": ("odgi",)},
}


def _engine_modules() -> dict[str, tuple[str, ...]]:
    mapping: dict[str, set[str]] = {}
    for module_key, profile in MODULE_PROFILES.items():
        for engine in profile.engines:
            key = str(engine).lower()
            if is_native_engine(engine) or key not in ENGINE_REGISTRY:
                continue
            mapping.setdefault(key, set()).add(module_key)
    return {key: tuple(sorted(values)) for key, values in mapping.items()}


def _default_conda_package(engine: str) -> tuple[str, ...]:
    # Most command-line bioinformatics packages use their executable name in
    # Bioconda. Overrides above handle known exceptions.
    return (engine.replace("_", "-"),)


def provisioning_spec(engine: str) -> ProvisioningSpec:
    key = str(engine).lower()
    spec = ENGINE_REGISTRY[key]
    override = _PACKAGE_OVERRIDES.get(key, {})
    manual = bool(override.get("manual", False))
    conda = tuple(override.get("conda", ()))
    pip = tuple(override.get("pip", ()))
    if not manual and not conda and not pip:
        conda = _default_conda_package(key)
    weights = bool(override.get("weights", False))
    licence = bool(override.get("licence", False))
    reference_required = bool(spec.required_databases)
    if manual:
        backends = ("registered-provider-installation", "protected-native-workspace")
    elif pip and not conda:
        backends = ("pinned-python-venv", "container")
    else:
        backends = ("micromamba-conda-lock", "container", "registered-native-installation")
    version_constraint = ">=current-supported-release,<next-breaking-major"
    smoke = tuple([*spec.executables[:1], *spec.version_args])
    complete = bool(backends and smoke and (manual or conda or pip))
    return ProvisioningSpec(
        engine=key,
        label=spec.label,
        category=spec.category,
        conda_packages=conda,
        pip_packages=pip,
        manual_distribution=manual,
        licence_acceptance_required=licence,
        model_weights_required=weights,
        reference_data_required=reference_required,
        supported_backends=backends,
        version_constraint=version_constraint,
        smoke_test=smoke,
        modules=_engine_modules().get(key, ()),
        software_recipe_complete=complete,
    )


def provisioning_catalog(engines: Iterable[str] | None = None) -> pd.DataFrame:
    selected = sorted(set(str(v).lower() for v in (engines or _engine_modules())))
    rows: list[dict[str, Any]] = []
    for engine in selected:
        item = asdict(provisioning_spec(engine))
        for key in ("conda_packages", "pip_packages", "supported_backends", "smoke_test", "modules"):
            item[key] = ", ".join(item[key])
        item["module_count"] = len(provisioning_spec(engine).modules)
        rows.append(item)
    return pd.DataFrame(rows)


def runtime_inventory(engines: Iterable[str] | None = None) -> pd.DataFrame:
    recipes = provisioning_catalog(engines)
    rows: list[dict[str, Any]] = []
    for row in recipes.to_dict(orient="records"):
        key = str(row["engine"])
        status = detect_engine(key)
        executable = Path(status.executable).resolve() if status.executable else None
        executable_sha256 = ""
        if executable and executable.is_file() and executable.name.lower() not in {"python", "python.exe"}:
            try:
                executable_sha256 = hashlib.sha256(executable.read_bytes()).hexdigest()
            except OSError:
                executable_sha256 = ""
        rows.append(
            {
                **row,
                "installed": bool(status.available),
                "detected_path": str(executable or ""),
                "detected_version": status.version,
                "executable_sha256": executable_sha256,
                "docker_available": bool(shutil.which("docker")),
                "micromamba_available": bool(shutil.which("micromamba")),
                "conda_available": bool(shutil.which("conda")),
                "wsl_available": bool(shutil.which("wsl") or shutil.which("wsl.exe")),
            }
        )
    return pd.DataFrame(rows)


def safe_slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return text or "asset"


def engine_manifest(engine: str) -> dict[str, Any]:
    item = provisioning_spec(engine)
    payload: dict[str, Any] = {
        "schema": "biointel.step164.engine-provisioning-manifest.v1",
        "engine": item.engine,
        "label": item.label,
        "category": item.category,
        "modules": list(item.modules),
        "installation": {
            "supported_backends": list(item.supported_backends),
            "conda_channels": ["conda-forge", "bioconda"],
            "conda_packages": list(item.conda_packages),
            "pip_packages": list(item.pip_packages),
            "manual_distribution": item.manual_distribution,
            "licence_acceptance_required": item.licence_acceptance_required,
            "version_constraint": item.version_constraint,
        },
        "qualification": {
            "smoke_test": list(item.smoke_test),
            "executable_sha256_required": True,
            "version_capture_required": True,
            "model_weights_required": item.model_weights_required,
            "reference_data_required": item.reference_data_required,
            "negative_control_required": True,
            "golden_fixture_required": True,
        },
        "claim_boundary": "A complete recipe is not an installed or scientifically qualified runtime. Installation, licence acceptance, weights, references and smoke-test evidence are verified independently.",
    }
    payload["manifest_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return payload


__all__ = [
    "ProvisioningSpec",
    "engine_manifest",
    "provisioning_catalog",
    "provisioning_spec",
    "runtime_inventory",
    "safe_slug",
]
