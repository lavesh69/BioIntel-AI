"""Evidence-bound P0/P1 priority remediation for Step 196.

This package helps teams stage and verify locally supplied evidence without
inventing external scientific, operational or regulatory proof.
"""

from .catalog import (
    EXECUTION_KEY_ALIASES,
    GATE_ORDER,
    P0_MODULE_KEYS,
    P1_MODULE_KEYS,
    PRIORITY_MODULES,
    canonical_execution_key,
)
from .functional import (
    execution_contract_bytes,
    execution_portfolio_rows,
    module_execution_contract,
    prepare_functional_workspaces,
    run_execution_preflight,
)
from .registry import PriorityEvidenceRegistry

__all__ = [
    "EXECUTION_KEY_ALIASES",
    "GATE_ORDER",
    "P0_MODULE_KEYS",
    "P1_MODULE_KEYS",
    "PRIORITY_MODULES",
    "PriorityEvidenceRegistry",
    "canonical_execution_key",
    "execution_contract_bytes",
    "execution_portfolio_rows",
    "module_execution_contract",
    "prepare_functional_workspaces",
    "run_execution_preflight",
]
