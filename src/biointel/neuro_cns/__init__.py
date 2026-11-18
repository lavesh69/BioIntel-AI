"""Unified 41-module Neuro/CNS studio with advanced validation and production systems.

The studio preserves the established scientific, completion and production
layers and adds Step208 maximum-potential research workflows. Software
functionality remains local-first and fail-closed. Predictive-looking outputs
remain screening or exploratory unless independent evidence, approved data
bindings and responsible scientific review are supplied.
"""

from biointel.neuro_cns.catalog import MODULES, MODULE_BY_KEY, WORKSPACES
from biointel.neuro_cns.completion import COMPLETION_FEATURES
from biointel.neuro_cns.max_potential import MAX_POTENTIAL_FEATURES
from biointel.neuro_cns.production import PRODUCTION_FEATURES

__version__ = "208.0"
__all__ = [
    "MODULES",
    "MODULE_BY_KEY",
    "WORKSPACES",
    "MAX_POTENTIAL_FEATURES",
    "COMPLETION_FEATURES",
    "PRODUCTION_FEATURES",
    "__version__",
]
