from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.util
from pathlib import Path
import shutil
from typing import Any, Iterable

import pandas as pd

from biointel.native.engines import ENGINE_REGISTRY, _PLAN_REQUIREMENTS, detect_engine
from biointel.scientific_depth.native_workflows import is_native_engine
from biointel.scientific_depth.profiles import MODULE_PROFILES


@dataclass(frozen=True)
class RuntimeRecipe:
    engine: str
    label: str
    category: str
    modules: tuple[str, ...]
    execution_backends: tuple[str, ...]
    install_strategy: str
    package_hint: str
    licence_class: str
    manual_action_required: bool
    model_or_database_required: bool
    checksum_required: bool
    version_probe_required: bool
    protected_plan_available: bool
    recipe_complete: bool


# These overrides describe provisioning policy only. They do not claim that a
# tool, model, licence or database is bundled in the core application package.
_MANUAL_LICENCE = {"netmhcpan", "netmhciipan"}
_MODEL_WEIGHT_TOOLS = {"dorado", "cellpose", "stardist", "proteinmpnn", "rfdiffusion", "colabfold", "llama_cpp"}
_PYTHON_FIRST = {"openmm", "scanpy", "scvelo", "cellrank", "stardist", "openslide", "cellpose", "anarci", "whatshap", "deeptools", "llama_cpp"}
_CONTAINER_FIRST = {
    "vep", "openms", "gromacs", "kraken2", "bracken", "humann", "busco",
    "saige", "regenie", "proteinmpnn", "rfdiffusion", "colabfold",
}


def _engine_modules() -> dict[str, tuple[str, ...]]:
    mapping: dict[str, list[str]] = {}
    for module_key, profile in MODULE_PROFILES.items():
        for engine in profile.engines:
            key = engine.lower()
            if is_native_engine(engine) or key not in ENGINE_REGISTRY:
                continue
            mapping.setdefault(key, []).append(module_key)
    return {key: tuple(sorted(set(values))) for key, values in mapping.items()}


def _protected_plan_engines() -> set[str]:
    return {
        str(requirements[0]).lower()
        for requirements in _PLAN_REQUIREMENTS.values()
        if requirements
    }


def runtime_recipe(engine: str) -> RuntimeRecipe:
    key = str(engine).lower()
    spec = ENGINE_REGISTRY[key]
    modules = _engine_modules().get(key, ())
    protected = key in _protected_plan_engines()
    if key in _MANUAL_LICENCE:
        strategy = "manual-licence-registration"
        backends = ("native-executable", "managed-workspace")
        package_hint = f"Register a licensed {spec.label} installation and its data directory."
        licence = "registration-required"
        manual = True
    elif key in _PYTHON_FIRST:
        strategy = "pinned-python-environment"
        backends = ("python-environment", "conda-lock", "container")
        package_hint = f"Install {key} in the Step 161 pinned scientific environment."
        licence = "open-source-or-provider-terms"
        manual = key in _MODEL_WEIGHT_TOOLS
    elif key in _CONTAINER_FIRST:
        strategy = "digest-pinned-container-or-conda"
        backends = ("container", "conda-lock", "native-executable")
        package_hint = f"Provision {spec.label} through a digest-pinned container or locked environment."
        licence = "open-source-or-provider-terms"
        manual = key in _MODEL_WEIGHT_TOOLS
    else:
        strategy = "native-or-conda-lock"
        backends = ("native-executable", "conda-lock", "container", "wsl2")
        package_hint = f"Provision a version-pinned {spec.label} executable and record its checksum."
        licence = "open-source-or-provider-terms"
        manual = False
    database_required = bool(spec.required_databases) or key in _MODEL_WEIGHT_TOOLS
    return RuntimeRecipe(
        engine=key,
        label=spec.label,
        category=spec.category,
        modules=modules,
        execution_backends=backends,
        install_strategy=strategy,
        package_hint=package_hint,
        licence_class=licence,
        manual_action_required=manual,
        model_or_database_required=database_required,
        checksum_required=True,
        version_probe_required=True,
        protected_plan_available=protected,
        recipe_complete=bool(backends and strategy and package_hint and protected),
    )


def runtime_recipe_catalog(engines: Iterable[str] | None = None) -> pd.DataFrame:
    mapping = _engine_modules()
    selected = sorted(set(str(value).lower() for value in (engines or mapping)))
    rows: list[dict[str, Any]] = []
    for engine in selected:
        recipe = runtime_recipe(engine)
        row = asdict(recipe)
        row["modules"] = ", ".join(recipe.modules)
        row["module_count"] = len(recipe.modules)
        row["execution_backends"] = ", ".join(recipe.execution_backends)
        rows.append(row)
    return pd.DataFrame(rows)


def runtime_detection_matrix(engines: Iterable[str] | None = None) -> pd.DataFrame:
    recipes = runtime_recipe_catalog(engines)
    rows: list[dict[str, Any]] = []
    for row in recipes.to_dict(orient="records"):
        engine = str(row["engine"])
        status = detect_engine(engine)
        python_package = engine if engine in _PYTHON_FIRST else ""
        python_detected = bool(python_package and importlib.util.find_spec(python_package))
        rows.append(
            {
                **row,
                "installed": bool(status.available or python_detected),
                "detected_path": status.executable or (f"Python package: {python_package}" if python_detected else ""),
                "detected_version": status.version,
                "docker_available": bool(shutil.which("docker")),
                "conda_available": bool(shutil.which("conda") or shutil.which("micromamba")),
                "wsl_available": bool(shutil.which("wsl") or shutil.which("wsl.exe")),
                "operational_path_ready": bool(row["recipe_complete"]),
            }
        )
    return pd.DataFrame(rows)


def module_runtime_path_matrix(module_key: str, *, detect_runtime: bool = True) -> pd.DataFrame:
    profile = MODULE_PROFILES[module_key]
    engines = [
        engine.lower()
        for engine in profile.engines
        if not is_native_engine(engine) and engine.lower() in ENGINE_REGISTRY
    ]
    if not engines:
        return pd.DataFrame(
            [
                {
                    "module_key": module_key,
                    "engine": "biointel_native",
                    "label": "BioIntel deterministic native engine",
                    "recipe_complete": True,
                    "installed": True,
                    "execution_backends": "in-process Python",
                    "manual_action_required": False,
                    "licence_class": "included",
                    "protected_plan_available": True,
                    "operational_path_ready": True,
                }
            ]
        )
    if detect_runtime:
        frame = runtime_detection_matrix(engines)
    else:
        frame = runtime_recipe_catalog(engines).copy()
        frame["installed"] = False
        frame["detected_path"] = ""
        frame["detected_version"] = "Not probed during module execution"
        frame["docker_available"] = False
        frame["conda_available"] = False
        frame["wsl_available"] = False
        frame["operational_path_ready"] = frame["recipe_complete"].astype(bool)
    frame.insert(0, "module_key", module_key)
    return frame


def runtime_catalog_summary(frame: pd.DataFrame | None = None) -> dict[str, Any]:
    data = runtime_recipe_catalog() if frame is None else frame
    return {
        "schema": "biointel.step161.runtime-recipe-summary.v1",
        "external_engines": int(len(data)),
        "complete_recipes": int(data["recipe_complete"].astype(bool).sum()) if not data.empty else 0,
        "protected_execution_plans": int(data["protected_plan_available"].astype(bool).sum()) if not data.empty else 0,
        "all_engines_have_managed_paths": bool(not data.empty and data["recipe_complete"].astype(bool).all()),
        "installed_tools_are_detected_separately": True,
        "licences_models_and_databases_are_not_inferred": True,
    }


__all__ = [
    "RuntimeRecipe",
    "module_runtime_path_matrix",
    "runtime_catalog_summary",
    "runtime_detection_matrix",
    "runtime_recipe",
    "runtime_recipe_catalog",
]
