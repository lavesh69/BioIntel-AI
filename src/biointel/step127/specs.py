from __future__ import annotations

from .bioinformatics_specs import BIOINFORMATICS_SPECS
from .discovery_specs import DISCOVERY_SPECS
from .lab_specs import LAB_SPECS
from .models import ModuleSpec

ALL_MODULE_SPECS: tuple[ModuleSpec, ...] = (*BIOINFORMATICS_SPECS, *DISCOVERY_SPECS, *LAB_SPECS)
MODULE_SPECS: dict[str, ModuleSpec] = {spec.key: spec for spec in ALL_MODULE_SPECS}
PAGE_TO_MODULE: dict[str, str] = {spec.page_path: spec.key for spec in ALL_MODULE_SPECS}
TITLE_TO_MODULE: dict[str, str] = {spec.title.lower(): spec.key for spec in ALL_MODULE_SPECS}


def get_spec(module_key: str) -> ModuleSpec:
    try:
        return MODULE_SPECS[module_key]
    except KeyError as exc:
        raise KeyError(f"Unknown Step 127 module key: {module_key}") from exc


def specs_for_domain(domain: str) -> tuple[ModuleSpec, ...]:
    wanted = domain.strip().lower()
    return tuple(spec for spec in ALL_MODULE_SPECS if spec.domain.lower() == wanted)
