"""Authoritative, non-duplicating product registry derived from BioIntel catalogs.

The navigation catalog remains the source of truth for every user-facing page.
This module enriches those records with existing scientific-depth and next-gen
contracts instead of maintaining a second hand-written module list.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.util
from pathlib import Path
import sys
from typing import Any

from biointel.nextgen.catalog import MODULE_BY_KEY
from biointel.ui.navigation import PAGE_CATALOG, catalogue_integrity

PRODUCT_VERSION = "15.6.0"


def _load_depth_profiles() -> dict[str, Any]:
    """Load the metadata-only profile file without importing optional engines.

    ``biointel.scientific_depth.__init__`` intentionally exposes runtime
    readiness helpers and therefore imports optional scientific packages. The
    release registry must remain readable even before those packages are
    installed, so its pure-dataclass profile source is loaded directly.
    """

    name = "biointel._product_registry_depth_profiles"
    existing = sys.modules.get(name)
    if existing is not None:
        return dict(existing.MODULE_PROFILES)
    path = Path(__file__).resolve().parent / "scientific_depth" / "profiles.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load scientific depth profiles: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return dict(module.MODULE_PROFILES)


MODULE_PROFILES = _load_depth_profiles()


@dataclass(frozen=True)
class ProductModuleRecord:
    id: str
    title: str
    category: str
    subcategory: str
    path: str
    route: str
    icon: str
    version: str
    development_status: str
    maturity_status: str
    validation_status: str
    capability_labels: tuple[str, ...]
    purpose: str
    description: str
    supported_inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    required_columns: tuple[str, ...]
    workflow: tuple[str, ...]
    engine_dependencies: tuple[str, ...]
    built_in_engines: tuple[str, ...]
    external_engines: tuple[str, ...]
    required_ai_models: tuple[str, ...]
    reference_dependencies: tuple[str, ...]
    optional_online_providers: tuple[str, ...]
    validation_checks: tuple[str, ...]
    optimization_strategy: tuple[str, ...]
    offline_core_available: bool
    full_analysis_requires_external_assets: bool
    resource_class: str
    estimated_resource_requirement: str
    documentation: tuple[str, ...]
    sample_data: tuple[str, ...]
    input_templates: tuple[str, ...]
    related_modules: tuple[str, ...]
    limitations: str
    fallback_behavior: str
    feature_flags: dict[str, bool]
    enabled: bool
    featured: bool
    keywords: tuple[str, ...]
    registry_sources: tuple[str, ...]


def _starter_assets(root: Path, key: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    folder = root / "data" / "module_starter_kits" / key
    if not folder.is_dir():
        return (), (), ()
    files = [path for path in sorted(folder.rglob("*")) if path.is_file()]
    relative = lambda path: path.relative_to(root).as_posix()
    documentation = tuple(relative(path) for path in files if path.name == "manifest.json")
    samples = tuple(
        relative(path)
        for path in files
        if any(token in path.name.casefold() for token in ("sample", "filled", "demo", "example"))
    )
    templates = tuple(
        relative(path)
        for path in files
        if any(token in path.name.casefold() for token in ("blank", "template", "starter_kit"))
    )
    return documentation, samples, templates


def _resource_class(category: str, external_engines: tuple[str, ...]) -> str:
    gpu_markers = {"gromacs", "openmm", "cellpose", "stardist", "proteinmpnn", "rfdiffusion", "dorado"}
    if gpu_markers.intersection(external_engines):
        return "Heavy; background job recommended; GPU optional when supported"
    if external_engines or category in {"Bioinformatics", "Discovery", "Lab Analytics", "AI Lab", "Neuro/CNS"}:
        return "Moderate-to-heavy; bounded preview and background execution supported"
    return "Light-to-moderate local workload"


PLATFORM_CATEGORIES = {
    "Start",
    "Operations",
    "Governance",
    "Data",
    "Data & Governance",
    "Reporting",
    "Evidence",
    "Intelligence",
}

MODEL_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "dti_predictor": ("User-selected registered DTI model artifact",),
    "model_evaluation": ("User-selected registered model artifact",),
    "external_model_qualification": ("Imported external model package",),
    "multiomics_biomarker": ("Optional registered biomarker model",),
    "authentic_models_independent_benchmarks": ("Task-matched registered model package",),
}

PROVIDER_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "external_databases": ("UniProt", "ChEMBL"),
    "connected_data_explorer": (
        "NCBI",
        "UniProt",
        "PubChem",
        "RCSB PDB",
        "ChEMBL",
        "ClinicalTrials.gov",
        "ClinVar",
        "GEO",
        "BindingDB",
    ),
    "provider_integration_center": ("Ollama", "SearXNG", "optional OpenAI", "official scientific providers"),
    "biointel_copilot": ("Ollama", "SearXNG", "optional OpenAI"),
    "scientific_evidence_excellence": ("Official scientific evidence providers",),
}


def build_module_registry(project_root: str | Path | None = None) -> tuple[ProductModuleRecord, ...]:
    root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
    category_members: dict[str, list[str]] = {}
    for page in PAGE_CATALOG:
        category_members.setdefault(page.category, []).append(page.key)

    records: list[ProductModuleRecord] = []
    for page in PAGE_CATALOG:
        nextgen = MODULE_BY_KEY.get(page.key)
        profile = MODULE_PROFILES.get(page.key)
        documentation, samples, templates = _starter_assets(root, page.key)

        supported_inputs = tuple(nextgen.accepted_inputs) if nextgen else ()
        outputs = tuple(nextgen.outputs) if nextgen else ()
        required_columns = tuple(nextgen.required_columns) if nextgen else ()
        workflow = tuple(nextgen.workflow) if nextgen else ()
        purpose = nextgen.purpose if nextgen else page.description
        if profile:
            supported_inputs = tuple(dict.fromkeys((*supported_inputs, *profile.native_formats)))
        all_engines = tuple(profile.engines) if profile else ()
        built_in = tuple(item for item in all_engines if item.startswith("biointel_native::"))
        external = tuple(item for item in all_engines if not item.startswith("biointel_native::"))
        models = MODEL_REQUIREMENTS.get(page.key, ())
        references = tuple(profile.references) if profile else ()
        providers = PROVIDER_REQUIREMENTS.get(page.key, ())
        validations = tuple(profile.validations) if profile else ()
        optimization = tuple(profile.optimization) if profile else ()
        limitation = (
            (nextgen.boundary if nextgen else "")
            or (profile.boundary if profile else "")
            or "Software operation is tested; scientific interpretation remains research-use and requires domain review."
        )
        labels = ["Functional"]
        if external or references:
            labels.append("External dependency required")
        if models:
            labels.append("Requires AI model")
        if providers:
            labels.append("Requires API credentials or online provider")
        if nextgen and nextgen.kind == "scientific":
            labels.append("Not validated")
        if "demo" in page.title.casefold() or "demo" in page.description.casefold():
            labels.append("Demo-only")
        auto_discovered = page.category == "Unclassified" or "automatically discovered" in page.description.casefold()
        if auto_discovered:
            labels = ["Experimental", "Not validated"]

        related = tuple(key for key in category_members.get(page.category, ()) if key != page.key)[:6]
        enabled = (root / page.path).is_file()
        resource_class = _resource_class(page.category, external)
        maturity = "Experimental" if auto_discovered else "Fully implemented software surface"
        subcategory = (
            "Platform and operations"
            if (nextgen and nextgen.kind == "platform") or page.category in PLATFORM_CATEGORIES
            else "Scientific analysis"
        )
        sources = ["biointel.ui.navigation.PAGE_CATALOG"]
        if nextgen:
            sources.append("biointel.nextgen.catalog.MODULE_BY_KEY")
        if profile:
            sources.append("biointel.scientific_depth.profiles.MODULE_PROFILES")
        records.append(
            ProductModuleRecord(
                id=page.key,
                title=page.title,
                category=page.category,
                subcategory=subcategory,
                path=page.path,
                route=page.path,
                icon=page.icon,
                version=PRODUCT_VERSION,
                development_status="Experimental" if auto_discovered else "Functional",
                maturity_status=maturity,
                validation_status=(
                    "Software-tested; scientific outputs require module-specific validation"
                    if enabled
                    else "Not implemented"
                ),
                capability_labels=tuple(dict.fromkeys(labels)),
                purpose=purpose,
                description=page.description,
                supported_inputs=supported_inputs,
                outputs=outputs,
                required_columns=required_columns,
                workflow=workflow,
                engine_dependencies=all_engines,
                built_in_engines=built_in,
                external_engines=external,
                required_ai_models=models,
                reference_dependencies=references,
                optional_online_providers=providers,
                validation_checks=validations,
                optimization_strategy=optimization,
                offline_core_available=True,
                full_analysis_requires_external_assets=bool(external or references or models),
                resource_class=resource_class,
                estimated_resource_requirement=resource_class,
                documentation=tuple(dict.fromkeys((*documentation, "docs/USER_GUIDE.md"))),
                sample_data=samples,
                input_templates=templates,
                related_modules=related,
                limitations=limitation,
                fallback_behavior=(
                    "Use the bounded built-in research workflow; external-engine actions remain disabled with an actionable requirement message."
                    if external
                    else "Module failure is isolated and reported with recovery guidance; unrelated modules remain available."
                ),
                feature_flags={
                    "searchable": True,
                    "favourites": True,
                    "recent_history": True,
                    "sample_data_available": bool(samples),
                    "input_template_available": bool(templates),
                    "background_execution_recommended": bool(external),
                    "external_engine_actions": bool(external),
                },
                enabled=enabled,
                featured=page.featured,
                keywords=page.keywords,
                registry_sources=tuple(sources),
            )
        )
    return tuple(records)


def registry_as_dicts(project_root: str | Path | None = None) -> list[dict[str, Any]]:
    return [asdict(record) for record in build_module_registry(project_root)]


def registry_integrity(project_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
    records = build_module_registry(root)
    ids = [record.id for record in records]
    paths = [record.path for record in records]
    navigation = catalogue_integrity(root)
    duplicate_ids = sorted({item for item in ids if ids.count(item) > 1})
    duplicate_paths = sorted({item for item in paths if paths.count(item) > 1})
    disabled = sorted(record.id for record in records if not record.enabled)
    healthy = bool(navigation.get("healthy")) and not duplicate_ids and not duplicate_paths and not disabled
    return {
        "schema": "biointel.product-registry-integrity.v1",
        "healthy": healthy,
        "module_count": len(records),
        "navigation_page_count": len(PAGE_CATALOG),
        "duplicate_ids": duplicate_ids,
        "duplicate_paths": duplicate_paths,
        "disabled_or_missing": disabled,
        "auto_discovered": navigation.get("auto_discovered", []),
        "navigation": navigation,
    }


MODULE_REGISTRY = build_module_registry()
MODULE_BY_ID = {record.id: record for record in MODULE_REGISTRY}

__all__ = [
    "MODULE_BY_ID",
    "MODULE_REGISTRY",
    "ProductModuleRecord",
    "build_module_registry",
    "registry_as_dicts",
    "registry_integrity",
]
