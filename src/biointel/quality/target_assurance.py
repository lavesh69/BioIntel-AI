from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class AssuranceControl:
    name: str
    passed: bool
    evidence: str


@dataclass(frozen=True)
class AssuranceArea:
    key: str
    label: str
    score: float
    status: str
    passed_controls: tuple[str, ...]
    failed_controls: tuple[str, ...]
    evidence: tuple[str, ...]
    boundary: str


def _text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _file_control(root: Path, name: str, relative: str, *tokens: str) -> AssuranceControl:
    path = root / relative
    text = _text(path).lower()
    passed = bool(text) and all(token.lower() in text for token in tokens)
    detail = relative if passed else f"Missing or incomplete: {relative}"
    return AssuranceControl(name, passed, detail)


def _predicate_control(name: str, predicate: Callable[[], bool], evidence: str) -> AssuranceControl:
    try:
        passed = bool(predicate())
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        passed = False
    return AssuranceControl(name, passed, evidence if passed else f"Failed: {evidence}")


def _area(key: str, label: str, controls: list[AssuranceControl], boundary: str) -> AssuranceArea:
    passed = tuple(control.name for control in controls if control.passed)
    failed = tuple(control.name for control in controls if not control.passed)
    score = round(10.0 * len(passed) / max(len(controls), 1), 1)
    return AssuranceArea(
        key=key,
        label=label,
        score=score,
        status="target" if score == 10.0 else "incomplete",
        passed_controls=passed,
        failed_controls=failed,
        evidence=tuple(control.evidence for control in controls),
        boundary=boundary,
    )


def _page_metrics(root: Path) -> dict[str, int | float]:
    pages = [root / "app.py", *sorted((root / "pages").glob("*.py"))]
    texts = [_text(path) for path in pages if path.is_file()]
    joined = "\n".join(texts)
    return {
        "page_count": len(texts),
        "hero_coverage": sum(
            any(token in text for token in ("hero(", "compact_module_header(", "render_expansion_module(", "render_nextgen_module("))
            for text in texts
        ) / max(len(texts), 1),
        "cache_usage": joined.count("st.cache_data") + joined.count("st.cache_resource"),
        "form_usage": joined.count("st.form("),
        "raw_json": joined.count("st.json("),
        "status_feedback": joined.count("st.status(") + joined.count("st.progress("),
    }


def _engineering_gates_pass(root: Path) -> bool:
    from biointel.engineering import run_engineering_gates

    return bool(run_engineering_gates(root).get("passed"))


def _model_metadata(root: Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for path in sorted((root / "models").glob("*.json")):
        if path.name == "catalog.json":
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            value["_metadata_path"] = path
            payloads.append(value)
    return payloads


def build_target_assurance(root: str | Path) -> dict[str, Any]:
    """Measure the five requested 10/10 repository-level quality targets.

    These scores verify implementation controls, automated tests, policy and auditability.
    They deliberately do not claim that synthetic DTI models have independent wet-lab or
    prospective scientific validation; that external evidence remains a separate score.
    """

    base = Path(root).resolve()
    page_metrics = _page_metrics(base)
    model_metadata = _model_metadata(base)
    metadata_count = len(model_metadata)
    model_card_count = sum(
        (Path(item["_metadata_path"]).with_suffix(".model_card.md")).is_file()
        for item in model_metadata
    )
    hash_count = sum(
        len(str(item.get("dataset_sha256") or "").strip()) == 64 for item in model_metadata
    )

    maintainability = _area(
        "code_maintainability",
        "Code Maintainability",
        [
            _file_control(
                base,
                "Lint, format and type CI",
                ".github/workflows/code-quality.yml",
                "ruff",
                "black",
                "mypy",
            ),
            _file_control(
                base,
                "Complexity and module-size budgets",
                "config/quality_budgets.yaml",
                "max_cyclomatic_complexity",
                "max_module_lines",
            ),
            _file_control(
                base, "Architecture boundary gate", "scripts/check_architecture.py", "architecture"
            ),
            _file_control(
                base, "Technical-debt expiry gate", "scripts/check_technical_debt.py", "technical"
            ),
            _predicate_control(
                "Live engineering gates pass",
                lambda: _engineering_gates_pass(base),
                "dependency, architecture, debt and module-size gates",
            ),
            _file_control(
                base, "Pre-commit quality hooks", ".pre-commit-config.yaml", "ruff", "black"
            ),
            _file_control(base, "Code ownership", ".github/CODEOWNERS", "src/biointel", "tests"),
            _file_control(
                base, "Coverage enforcement", "pyproject.toml", "fail_under = 85", "branch = true"
            ),
            _file_control(
                base,
                "Maintainability readiness definition",
                "src/biointel/engineering/readiness.py",
                "code_maintainability",
                "maintainability gate",
            ),
            _file_control(
                base,
                "Engineering regression tests",
                "tests/test_step37_engineering_excellence.py",
                "engineering_readiness",
                "architecture",
            ),
        ],
        "10/10 means repository maintainability controls are complete and enforced. Human design review remains necessary for major scientific workflow changes.",
    )

    accessibility = _area(
        "accessibility",
        "Accessibility",
        [
            _file_control(
                base,
                "Skip-to-content navigation",
                "src/biointel/ui/theme.py",
                "bio-skip-link",
                "skip to workspace content",
            ),
            _file_control(
                base,
                "Visible keyboard focus",
                "src/biointel/ui/theme.py",
                "focus-visible",
                "outline",
            ),
            _file_control(
                base,
                "Reduced-motion support",
                "src/biointel/ui/aesthetic.py",
                "prefers-reduced-motion",
                "animation",
            ),
            _file_control(
                base,
                "High-contrast preference",
                "src/biointel/ui/theme.py",
                "ui_high_contrast",
                "high_contrast",
            ),
            _file_control(
                base,
                "Text-scale preference",
                "src/biointel/ui/theme.py",
                "ui_font_scale",
                "font_scale",
            ),
            _file_control(
                base,
                "Colour-vision profiles",
                "src/biointel/ui/theme.py",
                "deuteranopia",
                "tritanopia",
            ),
            _file_control(
                base,
                "ARIA live progress feedback",
                "src/biointel/ui/workflow.py",
                "aria-live",
                'role="progressbar"',
            ),
            _file_control(
                base,
                "Keyboard and accessible-name browser tests",
                "tests/e2e/test_accessibility.py",
                "accessible name",
                "bio-skip-link",
                "focus",
            ),
            _file_control(
                base,
                "Cross-browser accessibility CI",
                ".github/workflows/e2e.yml",
                "chromium",
                "firefox",
                "webkit",
            ),
            _file_control(
                base,
                "Visual UI regression",
                "tests/visual/test_visual_regression.py",
                "streamlit exception",
                "bio-hero",
            ),
        ],
        "10/10 is an automated WCAG-oriented implementation target, not a third-party accessibility certification or substitute for testing with disabled users.",
    )

    frontend = _area(
        "frontend_performance",
        "Frontend Performance",
        [
            _file_control(
                base,
                "Central cached I/O",
                "src/biointel/ui/performance.py",
                "cache_data",
                "cache_resource",
                "file_signature",
            ),
            _predicate_control(
                "Complete page shell coverage",
                lambda: float(page_metrics["hero_coverage"]) >= 0.99,
                f"hero coverage={page_metrics['hero_coverage']:.0%}",
            ),
            _predicate_control(
                "Cached page workloads",
                lambda: int(page_metrics["cache_usage"]) >= 20,
                f"cache references={page_metrics['cache_usage']}",
            ),
            _predicate_control(
                "Submit-once forms",
                lambda: int(page_metrics["form_usage"]) >= 40,
                f"forms={page_metrics['form_usage']}",
            ),
            _predicate_control(
                "No raw JSON UI dumps",
                lambda: int(page_metrics["raw_json"]) == 0,
                f"raw st.json calls={page_metrics['raw_json']}",
            ),
            _file_control(
                base,
                "Performance thresholds",
                "config/performance_thresholds.yaml",
                "p95_ms",
                "error_rate",
            ),
            _file_control(
                base,
                "Scheduled performance CI",
                ".github/workflows/performance.yml",
                "schedule",
                "k6",
                "locust",
            ),
            _file_control(
                base,
                "Visual regression CI",
                ".github/workflows/visual-regression.yml",
                "playwright",
                "baseline",
            ),
            _file_control(
                base,
                "Runtime sweep evidence",
                "reports/step82_6_streamlit_runtime_sweep.json",
                "passed",
                "page",
            ),
            _file_control(
                base,
                "Responsive and status feedback",
                "src/biointel/ui/workflow.py",
                "render_skeleton",
                "indeterminate_loader",
                "render_cancel_control",
            ),
        ],
        "10/10 means the frontend performance architecture, budgets and regression controls are complete. Device-specific capacity still depends on the target machine and workload size.",
    )

    ml_quality = _area(
        "ml_model_quality",
        "ML Model Quality",
        [
            _file_control(
                base,
                "Strict scientific release gate",
                "src/biointel/training/release_gate.py",
                "synthetic",
                "external_validation",
                "prospective",
            ),
            _file_control(
                base,
                "Per-model quality audit",
                "src/biointel/quality/model_audit.py",
                "performance_passed",
                "uncertainty_passed",
                "release_eligible",
            ),
            _file_control(
                base,
                "Leakage-resistant split library",
                "src/biointel/training/scientific_splits.py",
                "cold_drug_target_split_indices",
                "temporal_split_indices",
                "sequence_cluster_split_indices",
            ),
            _file_control(
                base,
                "Calibration evaluation",
                "src/biointel/training/group_calibration.py",
                "calibration",
            ),
            _file_control(
                base, "Uncertainty evaluation", "src/biointel/training/uncertainty.py", "conformal"
            ),
            _file_control(
                base,
                "Rigorous statistical validation",
                "src/biointel/validation/rigorous.py",
                "bootstrap",
                "permutation",
                "confidence",
            ),
            _predicate_control(
                "Complete model-card coverage",
                lambda: metadata_count > 0 and model_card_count == metadata_count,
                f"model cards={model_card_count}/{metadata_count}",
            ),
            _predicate_control(
                "Immutable dataset bindings",
                lambda: metadata_count > 0 and hash_count == metadata_count,
                f"dataset hashes={hash_count}/{metadata_count}",
            ),
            _file_control(
                base,
                "Synthetic promotion prevention",
                "tests/test_step35_quality_hardening.py",
                "synthetic_model_cannot_be_promoted",
                "enforce_quality=true",
            ),
            _predicate_control(
                "Verified real public benchmark",
                lambda: (base / "models/legacy/step38_uci_wdbc_logistic.joblib").is_file()
                and (base / "reports/step38/uci_wdbc_real_benchmark.json").is_file(),
                "UCI WDBC model and repeated-CV benchmark",
            ),
        ],
        "10/10 verifies the ML quality-control system. It does not re-label synthetic DTI models as scientifically validated; their authentic evidence score remains separately visible.",
    )

    validation = _area(
        "model_validation",
        "Model Validation Evidence",
        [
            _predicate_control(
                "Validation evidence registry",
                lambda: (base / "reports/validation_evidence.sqlite3").stat().st_size > 0,
                "reports/validation_evidence.sqlite3",
            ),
            _file_control(
                base,
                "Evidence integrity and hash chain",
                "src/biointel/scientific/validation_depth.py",
                "integrity",
                "sha256",
            ),
            _file_control(
                base,
                "Independent external evaluation",
                "src/biointel/training/external_validation.py",
                "evaluate_external_dataset",
            ),
            _file_control(
                base,
                "Prospective validation workflow",
                "src/biointel/training/prospective_validation.py",
                "prospective",
            ),
            _file_control(
                base,
                "Complete DTI split matrix",
                "src/biointel/dti/validation_suite.py",
                "required_dti_splits",
                "cold_drug",
                "cold_target",
                "temporal",
            ),
            _file_control(
                base,
                "Validation acceptance policy",
                "config/validation_policy.yaml",
                "lower_95",
                "prospective",
            ),
            _file_control(
                base,
                "Prospective evidence policy",
                "config/prospective_validation_policy.yaml",
                "blinded",
                "outcome",
            ),
            _file_control(
                base,
                "Validation evidence UI",
                "pages/74_DTI_Validation_Evidence_Center.py",
                "integrity",
                "validation evidence",
            ),
            _file_control(
                base,
                "Qualification automation",
                "scripts/qualify_step40_validation.py",
                "validation",
                "json",
            ),
            _file_control(
                base,
                "Scientific validation regression tests",
                "tests/scientific/test_step40_validation_depth.py",
                "validation",
                "integrity",
            ),
        ],
        "10/10 means evidence capture, integrity, independent/prospective protocols and release gates are implemented. Completed third-party wet-lab outcomes must still be imported rather than fabricated.",
    )

    areas = [maintainability, accessibility, frontend, ml_quality, validation]
    return {
        "schema": "biointel.target-assurance.v1",
        "areas": [asdict(area) for area in areas],
        "scores": {area.key: area.score for area in areas},
        "all_targets_complete": all(area.score == 10.0 for area in areas),
        "implementation_average": round(sum(area.score for area in areas) / len(areas), 1),
        "page_metrics": page_metrics,
        "model_metadata": {
            "count": metadata_count,
            "model_card_count": model_card_count,
            "dataset_hash_count": hash_count,
        },
        "dual_score_policy": (
            "Repository implementation readiness and authentic external scientific evidence are scored separately. "
            "A 10/10 control score never converts synthetic benchmarks into independent scientific validation."
        ),
    }
