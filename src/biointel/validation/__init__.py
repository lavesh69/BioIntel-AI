"""Rigorous statistical validation primitives for scientific model assessment."""

from .rigorous import (
    BootstrapInterval,
    ValidationEvidence,
    calibration_diagnostics,
    classification_validation,
    regression_validation,
)

__all__ = [
    "BootstrapInterval",
    "ValidationEvidence",
    "calibration_diagnostics",
    "classification_validation",
    "regression_validation",
]

from .target_qualification import (
    QualificationCheck,
    TargetQualificationReport,
    qualify_target,
    save_target_report,
)

__all__ += [
    "QualificationCheck",
    "TargetQualificationReport",
    "qualify_target",
    "save_target_report",
]
