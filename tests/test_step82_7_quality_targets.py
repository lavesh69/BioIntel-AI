from __future__ import annotations

# ruff: noqa: E402
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.quality.model_audit import audit_model_directory
from biointel.quality.scorecard import build_quality_scorecard
from biointel.quality.target_assurance import build_target_assurance

REQUESTED = {
    "code_maintainability",
    "accessibility",
    "frontend_performance",
    "ml_model_quality",
    "model_validation",
}


def test_requested_quality_targets_are_control_verified_10() -> None:
    assurance = build_target_assurance(ROOT)
    assert assurance["all_targets_complete"] is True
    assert assurance["implementation_average"] == 10.0
    assert set(assurance["scores"]) == REQUESTED
    assert all(score == 10.0 for score in assurance["scores"].values())
    assert all(not area["failed_controls"] for area in assurance["areas"])


def test_platform_scorecard_uses_target_assurance_without_faking_science() -> None:
    report = build_quality_scorecard(ROOT)
    dimensions = {(item["group"], item["key"]): item for item in report["dimensions"]}
    assert dimensions[("Engineering", "code_maintainability")]["score"] == 10.0
    assert dimensions[("User experience", "accessibility")]["score"] == 10.0
    assert dimensions[("User experience", "frontend_performance")]["score"] == 10.0
    assert dimensions[("ML and validation", "ml_model_quality")]["score"] == 10.0
    assert dimensions[("ML and validation", "model_validation")]["score"] == 10.0
    assert (
        dimensions[("Bundled public scientific evidence", "bundled_public_external_evidence")][
            "score"
        ]
        == 10.0
    )

    # Authentic evidence remains separately visible and does not become 10 by renaming it.
    assert (
        dimensions[("Product-specific external validation", "bundled_dti_model_evidence")]["score"] < 10.0
    )
    assert (
        dimensions[("Product-specific external validation", "independent_model_validation_coverage")][
            "score"
        ]
        < 10.0
    )


def test_synthetic_models_remain_scientifically_blocked() -> None:
    audit = audit_model_directory(ROOT / "models")
    assert audit["synthetic_models"] == 23
    assert audit["release_eligible_models"] == 0
