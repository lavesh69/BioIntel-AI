from __future__ import annotations

from typing import Any

try:
    import pandas as pd
except ImportError:
    pd = None


def _nested(result: Any, *keys: str) -> Any:
    current = result
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def evaluate_results(results: dict[str, Any]) -> pd.DataFrame:
    findings: list[dict[str, Any]] = []

    def add(severity: str, rule: str, message: str, modules: str) -> None:
        findings.append({"severity": severity, "rule": rule, "modules": modules, "message": message})

    bbb = results.get("bbb_permeability")
    pk = results.get("brain_exposure_pk")
    occupancy = results.get("receptor_occupancy")
    side = results.get("cns_side_effects")
    off_target = results.get("off_target_neurotoxicity")
    expression = results.get("brain_expression_atlas")
    precision = results.get("precision_neurology")
    advanced_safety = results.get("advanced_safety_margin")
    advanced_dose = results.get("advanced_dose_effect")
    advanced_compounds = results.get("advanced_compound_optimization")
    advanced_signature = results.get("advanced_multiomics_signature")
    advanced_review = results.get("advanced_neurophysiology_review")
    advanced_twin = results.get("advanced_brain_digital_twin")

    bbb_class = _nested(bbb, "classification")
    kp_uu = _nested(pk, "kp_uu_brain")
    if bbb_class in {"unlikely_or_uncertain", "outside_applicability_domain"} and isinstance(kp_uu, (int, float)) and kp_uu > 1.0:
        add("high", "BBB_PK_CONFLICT", "BBB screen is unfavourable/uncertain while the supplied PK simulation implies Kp,uu,brain > 1. Review passive/efflux parameters and units.", "BBB Permeability; Brain Exposure PK")

    if isinstance(occupancy, pd.DataFrame) and not occupancy.empty:
        high = pd.to_numeric(occupancy.get("occupancy_percent"), errors="coerce") >= 80
        if high.any() and not pk:
            add("medium", "OCCUPANCY_WITHOUT_PK", "High receptor occupancy is reported without a linked brain-exposure result. Confirm that free-brain concentration and affinity units match.", "Receptor Occupancy")
        errors = occupancy.get("error")
        if errors is not None and errors.notna().any():
            add("medium", "AFFINITY_ROWS_INVALID", f"{int(errors.notna().sum())} affinity row(s) were excluded because units or values were invalid.", "Receptor Occupancy")

    if isinstance(side, dict):
        coverage = _nested(side, "coverage", "coverage_fraction")
        if isinstance(coverage, (int, float)) and coverage < 0.5:
            add("high", "LOW_SIDE_EFFECT_COVERAGE", f"Only {coverage:.0%} of supplied targets have side-effect associations. Do not interpret absent estimates as low risk.", "CNS Side-Effect Predictor")

    if isinstance(off_target, dict) and int(off_target.get("flag_count", 0)) > 0 and not side:
        add("medium", "OFF_TARGET_WITHOUT_EFFECT_CONTEXT", "CNS off-targets were detected but side-effect mapping has not been run.", "Off-Target Neurotoxicity; CNS Side Effects")

    if isinstance(expression, dict) and expression.get("found") is False:
        add("low", "EXPRESSION_UNAVAILABLE", "Target expression was not found in the bundled snapshot. This is a data-coverage gap, not evidence of absent brain expression.", "Brain Expression Atlas")

    if isinstance(precision, dict):
        metrics = precision.get("quality_metrics", {})
        silhouette = metrics.get("silhouette_score")
        if isinstance(silhouette, (int, float)) and silhouette < 0.25:
            add("high", "UNSTABLE_STRATIFICATION", f"Silhouette score is low ({silhouette:.3f}); cohort clusters may not be reproducible.", "Precision Neurology")
        stability = metrics.get("bootstrap_stability")
        if isinstance(stability, (int, float)) and stability < 0.60:
            add("high", "LOW_CLUSTER_STABILITY", f"Bootstrap cluster stability is low ({stability:.2f}). Avoid biological interpretation until replicated.", "Precision Neurology")

    if isinstance(advanced_safety, dict):
        high_count = int(advanced_safety.get("high_off_target_count", 0) or 0)
        if high_count:
            add("high", "HIGH_OFF_TARGET_OCCUPANCY", f"{high_count} supplied off-target(s) exceed the high-occupancy review threshold.", "CNS Safety Margin Matrix")

    if isinstance(advanced_dose, dict):
        window = float(advanced_dose.get("time_inside_effect_window_hours", 0.0) or 0.0)
        if window <= 0:
            add("medium", "NO_SIMULATED_EFFECT_WINDOW", "No time interval simultaneously met the configured primary-target and off-target occupancy thresholds.", "Dose-to-Brain-to-Effect Simulator")

    if isinstance(advanced_compounds, dict):
        comparison = advanced_compounds.get("comparison")
        if isinstance(comparison, pd.DataFrame) and not comparison.empty and "inside_applicability_domain" in comparison:
            outside = int((comparison["inside_applicability_domain"] == False).sum())  # noqa: E712
            if outside:
                add("medium", "ANALOGUES_OUTSIDE_DOMAIN", f"{outside} analogue(s) are outside local descriptor applicability checks.", "CNS Compound Optimization Board")

    if isinstance(advanced_signature, dict):
        auc = advanced_signature.get("cross_validated_auc")
        if isinstance(auc, (int, float)) and auc < 0.65:
            add("medium", "WEAK_INTERNAL_SIGNATURE", f"Cross-validated signature AUC is only {auc:.3f}; do not advance without stronger and external performance.", "Neuro Multi-Omics Signature Builder")

    if isinstance(advanced_review, dict) and advanced_review.get("signal_quality_grade") == "poor":
        add("high", "POOR_SIGNAL_QUALITY", "Neurophysiology input quality is poor; event and connectivity outputs require correction/re-acquisition review.", "Digital Neurophysiology Review Board")

    if isinstance(advanced_twin, dict) and int(advanced_twin.get("surface_point_count", 0) or 0) == 0:
        add("medium", "EMPTY_DIGITAL_TWIN_SURFACE", "No voxels/points passed the selected digital-twin threshold.", "3D Brain Digital Twin Viewer")

    benchmark = results.get("max_benchmark_validation")
    if isinstance(benchmark, dict):
        metrics = benchmark.get("metrics")
        if isinstance(metrics, pd.DataFrame) and not metrics.empty:
            auc_row = metrics.loc[metrics["metric"] == "roc_auc", "value"]
            if not auc_row.empty and float(auc_row.iloc[0]) < 0.70:
                add("high", "BENCHMARK_PERFORMANCE_WEAK", f"Benchmark ROC AUC is {float(auc_row.iloc[0]):.3f}; do not advance the model without improvement and external validation.", "Benchmark Validation Center")
            brier_row = metrics.loc[metrics["metric"] == "brier", "value"]
            if not brier_row.empty and float(brier_row.iloc[0]) > 0.25:
                add("medium", "BENCHMARK_CALIBRATION_WEAK", f"Brier score is {float(brier_row.iloc[0]):.3f}; probability calibration requires review.", "Benchmark Validation Center")

    domain = results.get("max_applicability_domain")
    if isinstance(domain, dict):
        inside = domain.get("inside_fraction")
        if isinstance(inside, (int, float)) and inside < 0.80:
            add("high", "LOW_APPLICABILITY_COVERAGE", f"Only {inside:.0%} of query records are inside the configured reference domain.", "Applicability Domain Inspector")

    uncertainty = results.get("max_uncertainty")
    if isinstance(uncertainty, dict):
        summary = uncertainty.get("output_summary", {})
        low, high, median = summary.get("ci95_low"), summary.get("ci95_high"), summary.get("median")
        if all(isinstance(value, (int, float)) for value in (low, high, median)) and float(high) - float(low) > max(abs(float(median)) * 0.50, 10.0):
            add("medium", "HIGH_PARAMETER_UNCERTAINTY", "The propagated 95% interval is broad relative to the median output. Improve parameter measurements before interpretation.", "Uncertainty & Sensitivity Lab")

    release_dashboard = results.get("max_release_dashboard")
    if isinstance(release_dashboard, dict) and not release_dashboard.get("controlled_release_eligible", False):
        blockers = release_dashboard.get("blockers") or []
        add("info", "CONTROLLED_RELEASE_BLOCKED", "; ".join(map(str, blockers[:3])) or "Controlled release gates remain open.", "Maximum-Potential Release Dashboard")

    if not findings:
        add("info", "NO_CROSS_MODULE_CONFLICT", "No configured cross-module consistency conflicts were detected in the current result set.", "All completed modules")
    severity_order = pd.CategoricalDtype(["high", "medium", "low", "info"], ordered=True)
    frame = pd.DataFrame(findings)
    frame["severity"] = frame["severity"].astype(severity_order)
    return frame.sort_values(["severity", "rule"], ignore_index=True)


def result_quality_summary(results: dict[str, Any]) -> dict[str, Any]:
    findings = evaluate_results(results)
    counts = findings["severity"].astype(str).value_counts().to_dict()
    return {
        "module_results": len(results),
        "high_findings": int(counts.get("high", 0)),
        "medium_findings": int(counts.get("medium", 0)),
        "low_findings": int(counts.get("low", 0)),
        "release_eligible": False,
        "status": "review_required" if counts.get("high", 0) or counts.get("medium", 0) else "screening_consistent",
    }
