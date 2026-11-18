"""Safe, deterministic synthetic-data workspaces."""

from .core import (
    CONTROL_PRESETS,
    CLEAN_SCENARIOS,
    FAILURE_SCENARIOS,
    MODULE_SPECS,
    SIZE_PRESETS,
    SYNTHETIC_BANNER_TEXT,
    SYNTHETIC_BANNER_TITLE,
    SYNTHETIC_WATERMARK,
    SyntheticDatasetManifest,
    SyntheticGeneratedDataset,
    SyntheticGenerationConfig,
    SyntheticSafetyError,
    SyntheticScenario,
    SyntheticTruthRecord,
    SyntheticValidationResult,
    enforce_evidence_assignment,
    enforce_origin_transition,
    enforce_project_merge,
    enforce_validation_assignment,
    payload_contains_synthetic,
)
from .exports import build_synthetic_dataset_package, write_synthetic_package_directory
from .generators import SyntheticDatasetGenerator, generate_synthetic_dataset
from .registry import SyntheticDataRegistry

__all__ = [
    "CLEAN_SCENARIOS", "CONTROL_PRESETS", "FAILURE_SCENARIOS", "MODULE_SPECS", "SIZE_PRESETS",
    "SYNTHETIC_BANNER_TEXT", "SYNTHETIC_BANNER_TITLE", "SYNTHETIC_WATERMARK",
    "SyntheticDataRegistry", "SyntheticDatasetGenerator", "SyntheticDatasetManifest",
    "SyntheticGeneratedDataset", "SyntheticGenerationConfig", "SyntheticSafetyError",
    "SyntheticScenario", "SyntheticTruthRecord", "SyntheticValidationResult",
    "build_synthetic_dataset_package", "enforce_evidence_assignment",
    "enforce_origin_transition", "enforce_project_merge", "enforce_validation_assignment",
    "generate_synthetic_dataset", "payload_contains_synthetic", "write_synthetic_package_directory",
]
