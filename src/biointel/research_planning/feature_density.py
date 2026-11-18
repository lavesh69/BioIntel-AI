from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PeakFeatureProfile:
    module_key: str
    feature_groups: Mapping[str, tuple[str, ...]]
    signature_visuals: tuple[str, ...]
    validation_checks: tuple[str, ...]

    @property
    def feature_count(self) -> int:
        return sum(len(items) for items in self.feature_groups.values())


_SHARED_FEATURES: dict[str, tuple[str, ...]] = {
    "Traceability": (
        "Objective-to-output scientific lineage",
        "Change-impact propagation",
        "Assumption-to-decision links",
        "Review and approval history",
    ),
    "Comparison": (
        "Scenario comparison",
        "Version comparison",
        "Before-versus-after amendment review",
        "Selected-record handoff preservation",
    ),
    "Quality": (
        "Module completeness score",
        "Cross-module consistency checks",
        "Unresolved blocker queue",
        "Evidence and limitation status",
    ),
    "Export": (
        "Machine-readable planning manifest",
        "Underlying visual-data export",
        "Calculation provenance",
        "Reproducible review package",
    ),
    "Execution": (
        "Bounded calculation runtime",
        "Deterministic seed control",
        "Failure-isolated specialist panels",
        "Stable recovery identifiers",
    ),
    "Collaboration": (
        "Named scientific owner",
        "Reviewer decision queue",
        "Comment and resolution history",
        "Deadline and escalation metadata",
    ),
}


def _profile(
    key: str,
    specialist: Sequence[str],
    visuals: Sequence[str],
    checks: Sequence[str],
) -> PeakFeatureProfile:
    groups = dict(_SHARED_FEATURES)
    groups["Specialist"] = tuple(specialist)
    return PeakFeatureProfile(key, groups, tuple(visuals), tuple(checks))


PEAK_FEATURE_PROFILES: dict[str, PeakFeatureProfile] = {
    "research_planning_command_center": _profile(
        "research_planning_command_center",
        (
            "Multi-study portfolio readiness",
            "Weighted readiness policies",
            "Approval and review deadline tracker",
            "Unresolved assumption inbox",
            "Amendment impact inbox",
            "Cross-project comparison",
            "Orphan planning-object detection",
            "Portfolio-level dependency risk",
        ),
        (
            "Portfolio readiness matrix", "Digital-thread network", "Blocker flow", "Assumption aging",
            "Approval calendar", "Cross-study comparison", "Dependency risk network", "Readiness trend",
        ),
        ("Every study has an owner", "Weights sum to one", "Critical blockers are surfaced", "Orphan objects are reported"),
    ),
    "research_budget_participant_burden": _profile(
        "research_budget_participant_burden",
        (
            "Currency and exchange-rate normalization", "Annual inflation escalation", "Monthly cash-flow forecast",
            "Site-specific cost contracts", "Cost per enrolled participant", "Cost per evaluable participant",
            "Participant compensation planning", "Burden-equity analysis", "Contingency allocation",
            "Budget scenario comparison", "Cash runway warning", "Cost-driver sensitivity",
        ),
        (
            "Cost waterfall", "P10-P50-P90 forecast", "Monthly burn curve", "Site-cost map", "Burden equity heatmap",
            "Cost-per-participant comparison", "Contingency allocation", "Cash runway timeline",
        ),
        ("Currency is specified", "Inflation is non-negative", "Contingency is explicit", "Participant burden is subgroup-reviewed"),
    ),
    "study_protocol_designer": _profile(
        "study_protocol_designer",
        (
            "Collaborative protocol section editor", "Reusable protocol section library", "Protocol synopsis generator",
            "Schedule-of-activities editor", "Country and site appendices", "Protocol deviation dictionary",
            "Approval workflow", "Amendment redline", "Section dependency validation", "Participant journey builder",
            "Critical-to-quality ownership", "Review-progress tracking",
        ),
        (
            "Schedule-of-activities matrix", "Amendment redline", "Section dependency graph", "Participant journey",
            "Review progress", "Critical-to-quality map", "Protocol completeness", "Approval timeline",
        ),
        ("Primary objective is defined", "Primary endpoint is linked", "Schedule is internally consistent", "Amendments are impact-assessed"),
    ),
    "data_collection_crf_designer": _profile(
        "data_collection_crf_designer",
        (
            "Drag-and-drop form specification", "ePRO and eCOA metadata", "Multilingual labels", "Dynamic skip logic",
            "Cross-form edit checks", "Coding dictionaries", "Live form preview", "Automated rule test cases",
            "Dependency-cycle detection", "Respondent burden scoring", "Visit coverage analysis", "FHIR/CDASH mapping",
        ),
        (
            "Form logic graph", "Edit-check network", "Field dependency map", "Respondent burden", "Visit-form coverage",
            "Variable lineage", "Rule-test results", "Translation completeness",
        ),
        ("Variable names are unique", "Required fields have valid types", "Skip logic has no cycles", "Every endpoint has a collection variable"),
    ),
    "cohort_eligibility_builder": _profile(
        "cohort_eligibility_builder",
        (
            "Visual rule builder", "Nested Boolean groups", "Temporal eligibility logic", "Computable phenotype definitions",
            "OMOP and FHIR source mappings", "Duplicate participant detection", "Source-data feasibility",
            "Rule test cases", "Cohort version comparison", "Portable rule export", "Eligibility sensitivity",
            "Site-level eligible population estimation",
        ),
        (
            "Attrition funnel", "Temporal rule timeline", "Eligibility decision tree", "Rule-overlap UpSet",
            "Site feasibility map", "Rule sensitivity", "Cohort version diff", "Exclusion reason flow",
        ),
        ("Rules are syntactically valid", "Required source variables exist", "Temporal windows are explicit", "Duplicate participants are handled"),
    ),
    "endpoint_outcome_strategy": _profile(
        "endpoint_outcome_strategy",
        (
            "Endpoint library", "Estimand alignment", "Endpoint adjudication charter", "MCID planning",
            "Competing-risk strategy", "Win-ratio planning", "Composite endpoint contribution",
            "Measurement-error model", "Responder definition simulator", "Missing-outcome strategy",
            "Endpoint burden scoring", "Validation-evidence registry",
        ),
        (
            "Objective-estimand-endpoint graph", "Endpoint hierarchy", "Composite contribution", "Adjudication workflow",
            "Burden-versus-value", "MCID sensitivity", "Measurement schedule", "Missingness risk",
        ),
        ("Primary endpoint is unique", "MCID has a source", "Intercurrent events are addressed", "Collection and analysis are linked"),
    ),
    "randomization_blinding_allocation": _profile(
        "randomization_blinding_allocation",
        (
            "Minimization allocation", "Covariate-adaptive assignment", "Central allocation service contract",
            "Secure seed and digest", "Variable block generation", "Unequal allocation", "Re-randomization controls",
            "Emergency code-break workflow", "Sequential imbalance monitoring", "Assignment entropy",
            "Predictability testing", "Independent allocation export",
        ),
        (
            "Live imbalance trajectory", "Assignment entropy", "Site-arm heatmap", "Block-pattern audit",
            "Emergency unblinding timeline", "Covariate balance", "Predictability risk", "Allocation sequence audit",
        ),
        ("Participant identifiers are unique", "Strata are available", "Seed is recorded", "Maximum imbalance is within tolerance"),
    ),
    "statistical_analysis_plan": _profile(
        "statistical_analysis_plan",
        (
            "TFL shell builder", "ADaM specification editor", "Mock-data dry run", "Analysis-code skeleton generation",
            "Tipping-point analysis plan", "Interim-analysis rules", "Derived-variable catalogue",
            "Endpoint-to-estimand mapping", "Multiplicity graph", "Analysis population rules",
            "Dataset-variable lineage", "Output production roadmap",
        ),
        (
            "Endpoint-estimand-model flow", "Multiplicity graph", "Population overlap", "Mock TFL gallery",
            "Variable lineage", "Sensitivity grid", "Output roadmap", "Analysis readiness matrix",
        ),
        ("Every primary endpoint has a model", "Estimand IDs are present", "Multiplicity is specified", "TFL outputs have source datasets"),
    ),
    "biostatistics_design": _profile(
        "biostatistics_design",
        (
            "Generalized linear mixed models", "Bayesian model planning", "Causal-inference estimators",
            "Recurrent-event methods", "Competing-risk methods", "Robust estimation", "Multiple imputation",
            "Mediation analysis", "Subgroup interaction", "Equivalence and non-inferiority",
            "Model-assumption compatibility", "Independent calculation verification",
        ),
        (
            "Model navigator", "Assumption diagnostic matrix", "Effect-size forest", "Missing-data comparison",
            "Sensitivity tornado", "Method compatibility", "Prior sensitivity", "Model robustness",
        ),
        ("Outcome type is specified", "Design and model are compatible", "Missing-data strategy exists", "Effect measure is interpretable"),
    ),
    "synthetic_cohort_trial": _profile(
        "synthetic_cohort_trial",
        (
            "Correlated synthetic variables", "Longitudinal digital participants", "Time-to-event outcomes",
            "MNAR dropout", "Treatment adherence", "Protocol deviations", "Site heterogeneity",
            "Real-cohort calibration", "Privacy attack screening", "Distribution preservation",
            "Treatment-effect recovery", "Scenario-specific random seeds",
        ),
        (
            "Real-versus-synthetic comparison", "Privacy-utility frontier", "Trajectory fan", "Missingness mechanism",
            "Effect recovery", "Site heterogeneity", "Correlation preservation", "Disclosure-risk distribution",
        ),
        ("Synthetic labels are explicit", "No direct identifiers are exported", "Utility is measured", "Disclosure risk is reported"),
    ),
    "sample_size_power_studio": _profile(
        "sample_size_power_studio",
        (
            "Bayesian assurance simulation", "Conditional-power uncertainty", "OBrien-Fleming alpha spending",
            "Pocock alpha spending", "Group-sequential operating characteristics", "Type-I error simulation",
            "Expected sample size under early stopping", "Cluster-size imbalance adjustment",
            "Stepped-wedge covariance planning", "ICC sensitivity", "Independent calculation manifest",
            "Simulation convergence and deterministic seed",
        ),
        (
            "Assurance curve", "Conditional-power interval", "Interim efficacy boundary", "Type-I error and power",
            "Stopping-look probability", "ICC design-effect surface", "Stepped-wedge precision", "Simulation convergence",
        ),
        ("Alpha is valid", "Simulation count is bounded", "Type-I error is reported", "Complex-design assumptions are explicit"),
    ),
    "clinical_trial_design_studio": _profile(
        "clinical_trial_design_studio",
        (
            "Group-sequential operating-characteristic simulation", "Interim efficacy and futility planning",
            "Type-I error verification", "Expected sample size estimation", "3+3 dose-escalation review",
            "Dose-toxicity confidence intervals", "Maximum tolerated dose screening", "Arm lifecycle decision contract",
            "Deterministic simulation seed", "Safety stopping review", "Independent boundary export",
            "Decision manifest with checksums",
        ),
        (
            "Interim boundary", "Operating-characteristic bars", "Stopping-look distribution", "Dose-toxicity plot",
            "Dose decision ladder", "Expected sample size comparison", "Safety review matrix", "Arm lifecycle timeline",
        ),
        ("Type-I error is estimated", "Dose toxicities do not exceed participants", "Interim fractions are ordered", "Simulation seed is recorded"),
    ),
    "experimental_design_doe": _profile(
        "experimental_design_doe",
        (
            "Randomized factorial design generation", "Central composite design generation", "Rotatable axial-point planning",
            "Center-point allocation", "Response-surface regression", "Main-effect estimation",
            "Interaction-effect estimation", "Quadratic-effect estimation", "Rank-deficiency detection",
            "Alias and collinearity review", "AICc and model diagnostics", "D-efficiency calculation",
        ),
        (
            "Design matrix", "Coefficient Pareto", "Observed-versus-predicted", "Residual map",
            "Alias network", "Factor correlation heatmap", "Response surface", "Design-region coverage",
        ),
        ("Design is estimable", "Factor ranges are valid", "Aliasing is surfaced", "Starter responses are labelled synthetic"),
    ),
    "biomarker_study_planning": _profile(
        "biomarker_study_planning",
        (
            "Expected confusion-matrix planning", "Sensitivity and specificity confidence intervals",
            "PPV and NPV prevalence sensitivity", "Positive and negative likelihood ratios", "Youden index",
            "Analytical CV penalty", "External-validation readiness", "Cut-off lock status",
            "Validation-maturity scoring", "Leakage-prevention checklist", "Candidate ranking",
            "Intended-use prevalence sensitivity",
        ),
        (
            "Performance-maturity map", "PPV/NPV prevalence curves", "Sensitivity-specificity intervals",
            "Expected confusion matrix", "Analytical CV comparison", "Validation stage funnel",
            "Leakage readiness", "Candidate ranking",
        ),
        ("Candidate names are unique", "Probabilities are in range", "Cut-off lock is reported", "External validation is distinguished"),
    ),
    "sampling_biospecimen_planning": _profile(
        "sampling_biospecimen_planning",
        (
            "Deterministic specimen barcodes", "Parent-child aliquot lineage", "Volume-consumption planning",
            "Reserve-volume policy", "Sample exhaustion warning", "Storage-demand aggregation",
            "Chain-of-custody event contract", "Temperature logger ingestion", "Excursion detection",
            "Freeze-temperature severity", "Inventory checksum manifest", "Bounded inventory generation",
        ),
        (
            "Specimen lineage tree", "Storage-demand chart", "Volume sufficiency", "Custody timeline",
            "Temperature trace", "Excursion table", "Sample availability", "Aliquot status distribution",
        ),
        ("Collection volumes are positive", "Aliquot limits are bounded", "Assay plus reserve volume is checked", "Temperature thresholds are explicit"),
    ),
    "research_feasibility_recruitment": _profile(
        "research_feasibility_recruitment",
        (
            "Probabilistic site activation", "Gamma-Poisson recruitment-rate variation", "Screen-success adjustment",
            "Retention adjustment", "Site capacity limits", "Monte Carlo completion probability",
            "P10-P50-P90 recruitment forecast", "Site underperformance probability", "Rescue-trigger generation",
            "Bayesian recruitment-rate update", "Horizon sensitivity", "Deterministic simulation seed",
        ),
        (
            "Recruitment fan chart", "Completion probability", "Site contribution", "Site underperformance risk",
            "Bayesian rate update", "Rescue trigger board", "Capacity utilization", "Activation uncertainty",
        ),
        ("Site names are unique", "Rates and capacities are non-negative", "Retention is a probability", "Completion uncertainty is reported"),
    ),
    "research_timeline_dependencies": _profile(
        "research_timeline_dependencies",
        (
            "PERT three-point durations", "Dependency cycle detection", "Unknown predecessor rejection",
            "Critical path calculation", "Task slack calculation", "Beta-PERT duration sampling",
            "Monte Carlo project duration", "Task criticality index", "P50 and P90 finish dates",
            "Resource-load aggregation", "Schedule-risk warning", "Deterministic simulation seed",
        ),
        (
            "Probabilistic Gantt", "Project duration distribution", "Task criticality index", "Resource-load chart",
            "Slack comparison", "P50-P90 milestone view", "Dependency network", "Delay propagation",
        ),
        ("Dependencies are acyclic", "PERT durations are ordered", "Task names are unique", "Schedule uncertainty is quantified"),
    ),
    "research_risk_mitigation": _profile(
        "research_risk_mitigation",
        (
            "FMEA probability-impact-detectability scoring", "Gross RPN", "Control-effectiveness adjustment",
            "Residual RPN", "KRI traffic-light classification", "Risk owner validation",
            "Bow-tie threat-control-consequence links", "Monte Carlo occurrence simulation",
            "Financial exposure distribution", "Schedule-delay distribution", "Category aggregation",
            "Residual-risk escalation",
        ),
        (
            "Gross-versus-residual risk", "FMEA matrix", "Financial exposure distribution", "Schedule-delay distribution",
            "Category control effectiveness", "Bow-tie network", "KRI board", "Residual-risk waterfall",
        ),
        ("Scores are within 1-5", "Control effectiveness is a probability", "Every risk has an owner", "Residual high risks are surfaced"),
    ),
    "evidence_gap_literature_planning": _profile(
        "evidence_gap_literature_planning",
        (
            "DOI normalization", "Exact DOI duplicate detection", "Normalized-title duplicate detection",
            "Bounded near-title similarity review", "PRISMA-style screening flow", "Quality and design weighting",
            "Inverse-variance fixed-effect pooling", "Heterogeneity Q and I-squared", "Direction contradiction detection",
            "Evidence certainty downgrade", "Population-outcome evidence matrix", "Search and screening manifest",
        ),
        (
            "PRISMA flow", "Study effect forest", "Contradiction matrix", "Evidence certainty",
            "Duplicate review", "Quality distribution", "Population-outcome map", "Evidence timeline",
        ),
        ("Study identifiers are unique", "Duplicates are excluded from pooling", "Standard errors are positive", "Heterogeneity is reported"),
    ),
    "preregistration_reproducibility": _profile(
        "preregistration_reproducibility",
        (
            "Planned-executed-reported comparison", "Outcome-switching detection", "Undisclosed-deviation detection",
            "Deviation severity classification", "Item-level SHA-256 locks", "Whole-plan cryptographic lock",
            "Artifact SHA-256 format verification", "Runtime environment snapshot", "Analysis dependency manifest",
            "Alignment score", "Locked-item coverage", "Reproducibility export contract",
        ),
        (
            "Plan-execution-report alignment", "Outcome-switching matrix", "Deviation severity", "Artifact integrity",
            "Environment manifest", "Lock coverage", "Amendment timeline", "Reproduction readiness",
        ),
        ("Preregistration items are unique", "Locked values are hashed", "Material changes have reasons", "Artifact hashes are validated"),
    ),

}


_DEFAULT_SPECIALIST = (
    "Specialist scenario editor", "Module-specific validation rules", "Versioned comparison workspace",
    "Linked scientific inspection", "Sensitivity and uncertainty analysis", "Reviewable decision records",
    "Cross-module impact propagation", "Publication-ready visual data", "Structured evidence notes",
    "Failure-safe calculation contract", "Module-specific quality score", "Reproducible export manifest",
)
_DEFAULT_VISUALS = (
    "Module readiness heatmap", "Scenario comparison", "Change impact", "Assumption sensitivity",
    "Decision trace", "Reviewer timeline", "Quality radar", "Cross-module handoff map",
)
_DEFAULT_CHECKS = ("Required inputs present", "Assumptions documented", "Results are reviewable", "Exports include provenance")


def get_peak_profile(module_key: str) -> PeakFeatureProfile:
    return PEAK_FEATURE_PROFILES.get(module_key, _profile(module_key, _DEFAULT_SPECIALIST, _DEFAULT_VISUALS, _DEFAULT_CHECKS))


def feature_inventory(module_key: str) -> pd.DataFrame:
    profile = get_peak_profile(module_key)
    rows: list[dict[str, Any]] = []
    for group, features in profile.feature_groups.items():
        for index, feature in enumerate(features, start=1):
            rows.append({
                "feature_id": f"{module_key}:{group.lower()}:{index}",
                "group": group,
                "feature": feature,
                "implementation_status": "Implemented",
                "review_status": "Needs review",
                "provenance_required": True,
            })
    return pd.DataFrame(rows)


def profile_digest(module_key: str) -> str:
    profile = get_peak_profile(module_key)
    payload = {
        "module_key": profile.module_key,
        "feature_groups": {key: list(value) for key, value in profile.feature_groups.items()},
        "signature_visuals": list(profile.signature_visuals),
        "validation_checks": list(profile.validation_checks),
    }
    return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def build_study_map(plan: Mapping[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    objective = str(plan.get("primary_objective") or "Primary objective")
    endpoint = str(plan.get("primary_endpoint") or "Primary endpoint")
    estimand = str(plan.get("estimand_id") or plan.get("estimand_ids", ["EST-001"])[0])
    variable = str(plan.get("estimand_variable") or endpoint)
    model = str(plan.get("estimator") or "Primary model")
    output = str(plan.get("primary_output") or "Primary TFL")
    records = [
        ("objective", objective, "study_protocol_designer"),
        ("endpoint", endpoint, "endpoint_outcome_strategy"),
        ("estimand", estimand, "statistical_analysis_plan"),
        ("variable", variable, "data_collection_crf_designer"),
        ("model", model, "biostatistics_design"),
        ("output", output, "statistical_analysis_plan"),
    ]
    nodes = pd.DataFrame([
        {"node_id": f"N{index:02d}", "node_type": kind, "label": label, "module_key": module}
        for index, (kind, label, module) in enumerate(records, start=1)
    ])
    edges = pd.DataFrame([
        {"source": nodes.iloc[index]["node_id"], "target": nodes.iloc[index + 1]["node_id"], "relationship": relationship, "weight": 1.0}
        for index, relationship in enumerate(("defines", "interpreted_by", "measured_as", "analysed_by", "reported_as"))
    ])
    return nodes, edges


_CHANGE_IMPACT = {
    "primary_endpoint": ("endpoint_outcome_strategy", "sample_size_power_studio", "data_collection_crf_designer", "statistical_analysis_plan", "preregistration_reproducibility"),
    "sample_size": ("sample_size_power_studio", "research_feasibility_recruitment", "research_budget_participant_burden", "research_timeline_dependencies"),
    "protocol_sample_size": ("sample_size_power_studio", "research_feasibility_recruitment", "research_budget_participant_burden"),
    "visits": ("sampling_biospecimen_planning", "data_collection_crf_designer", "research_timeline_dependencies", "research_budget_participant_burden"),
    "inclusion_criteria": ("cohort_eligibility_builder", "research_feasibility_recruitment", "sample_size_power_studio"),
    "randomization_strata": ("randomization_blinding_allocation", "data_collection_crf_designer", "statistical_analysis_plan"),
    "estimator": ("statistical_analysis_plan", "biostatistics_design", "sample_size_power_studio"),
    "budget_total": ("research_budget_participant_burden", "research_feasibility_recruitment", "research_timeline_dependencies"),
}


def change_impact(previous: Mapping[str, Any], current: Mapping[str, Any]) -> pd.DataFrame:
    keys = sorted(set(previous) | set(current))
    rows: list[dict[str, Any]] = []
    for key in keys:
        old = previous.get(key)
        new = current.get(key)
        if old == new:
            continue
        impacted = _CHANGE_IMPACT.get(key, ("research_planning_command_center",))
        severity = "Critical" if key in {"primary_endpoint", "sample_size", "protocol_sample_size", "estimator"} else "Major"
        for module_key in impacted:
            rows.append({
                "changed_field": key,
                "old_value": json.dumps(old, default=str) if isinstance(old, (dict, list, tuple)) else old,
                "new_value": json.dumps(new, default=str) if isinstance(new, (dict, list, tuple)) else new,
                "impacted_module": module_key,
                "severity": severity,
                "required_action": "Recalculate and review" if severity == "Critical" else "Review linkage",
            })
    return pd.DataFrame(rows)


def assumption_sensitivity(
    effect_size: float = 0.35,
    sample_size: int = 200,
    budget: float = 1_000_000.0,
    duration_months: float = 18.0,
) -> pd.DataFrame:
    if effect_size <= 0 or sample_size <= 0 or budget < 0 or duration_months <= 0:
        raise ValueError("Effect size, sample size and duration must be positive; budget cannot be negative.")
    scenarios = (("Stress", 0.70), ("Conservative", 0.85), ("Base", 1.0), ("Optimistic", 1.15))
    rows = []
    for name, factor in scenarios:
        adjusted_effect = effect_size * factor
        required_n = max(2, math.ceil(sample_size * (effect_size / adjusted_effect) ** 2))
        adjusted_budget = budget * (required_n / sample_size) * (1.10 if name == "Stress" else 1.0)
        adjusted_duration = duration_months * (required_n / sample_size) ** 0.65
        rows.append({
            "scenario": name,
            "effect_size": adjusted_effect,
            "required_sample_size": required_n,
            "budget": adjusted_budget,
            "duration_months": adjusted_duration,
            "relative_to_base": required_n / sample_size,
        })
    return pd.DataFrame(rows)


def plan_quality_matrix(plan: Mapping[str, Any], module_keys: Sequence[str] | None = None) -> pd.DataFrame:
    keys = list(module_keys or (
        "study_protocol_designer", "endpoint_outcome_strategy", "sample_size_power_studio",
        "data_collection_crf_designer", "statistical_analysis_plan", "research_feasibility_recruitment",
        "research_risk_mitigation", "preregistration_reproducibility",
    ))
    required_by_dimension = {
        "Complete": ("primary_objective", "primary_endpoint"),
        "Consistent": ("protocol_sample_size", "power_sample_size"),
        "Reviewed": ("reviewer", "review_status"),
        "Locked": ("protocol_sha256",),
        "Evidence-backed": ("source_provenance",),
        "Export-ready": ("protocol_id", "protocol_version"),
    }
    rows = []
    for module in keys:
        for dimension, required in required_by_dimension.items():
            if dimension == "Consistent":
                score = 100.0 if plan.get("protocol_sample_size") == plan.get("power_sample_size") and plan.get("protocol_sample_size") else 40.0
            else:
                present = sum(bool(plan.get(field)) for field in required)
                score = 100.0 * present / len(required)
            rows.append({"module_key": module, "dimension": dimension, "score": score, "status": "Ready" if score >= 80 else "Needs attention"})
    return pd.DataFrame(rows)


def portfolio_readiness(studies: pd.DataFrame, weights: Mapping[str, float] | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {"study_id", "protocol", "statistics", "operations", "data", "risk", "budget", "reproducibility"}
    missing = required - set(studies.columns)
    if missing:
        raise ValueError("Portfolio table is missing: " + ", ".join(sorted(missing)))
    if studies["study_id"].astype(str).duplicated().any():
        raise ValueError("Study identifiers must be unique.")
    dimensions = ["protocol", "statistics", "operations", "data", "risk", "budget", "reproducibility"]
    default_weight = 1.0 / len(dimensions)
    selected = {dimension: float((weights or {}).get(dimension, default_weight)) for dimension in dimensions}
    total = sum(selected.values())
    if total <= 0:
        raise ValueError("Readiness weights must have a positive total.")
    selected = {key: value / total for key, value in selected.items()}
    result = studies.copy()
    for column in dimensions:
        result[column] = pd.to_numeric(result[column], errors="coerce").clip(0, 100)
    result["weighted_readiness"] = sum(result[column].fillna(0) * selected[column] for column in dimensions)
    result["critical_blockers"] = (result[dimensions] < 50).sum(axis=1)
    result["status"] = np.select(
        [result["critical_blockers"] > 0, result["weighted_readiness"] < 80],
        ["Blocked", "Needs review"],
        default="Ready",
    )
    summary = {
        "studies": int(len(result)),
        "ready": int((result["status"] == "Ready").sum()),
        "blocked": int((result["status"] == "Blocked").sum()),
        "portfolio_readiness": float(result["weighted_readiness"].mean()) if len(result) else 0.0,
        "weights": selected,
    }
    return result, summary


def budget_cashflow(
    items: pd.DataFrame,
    months: int,
    annual_inflation: float = 0.03,
    exchange_rate: float = 1.0,
    contingency_fraction: float = 0.10,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    required = {"category", "quantity", "unit_cost", "start_month", "end_month"}
    missing = required - set(items.columns)
    if missing:
        raise ValueError("Budget items are missing: " + ", ".join(sorted(missing)))
    if months < 1 or months > 600:
        raise ValueError("Months must be between 1 and 600.")
    if annual_inflation < -0.5 or annual_inflation > 2:
        raise ValueError("Annual inflation is outside the supported planning range.")
    if exchange_rate <= 0 or not 0 <= contingency_fraction <= 1:
        raise ValueError("Exchange rate must be positive and contingency must be between zero and one.")
    table = items.copy()
    for column in ("quantity", "unit_cost", "start_month", "end_month"):
        table[column] = pd.to_numeric(table[column], errors="raise")
    if (table["quantity"] < 0).any() or (table["unit_cost"] < 0).any():
        raise ValueError("Budget quantities and costs cannot be negative.")
    if (table["start_month"] < 1).any() or (table["end_month"] < table["start_month"]).any() or (table["end_month"] > months).any():
        raise ValueError("Budget month ranges are invalid.")
    table["base_cost"] = table["quantity"] * table["unit_cost"] * exchange_rate
    table["duration_months"] = table["end_month"] - table["start_month"] + 1
    rows: list[dict[str, Any]] = []
    for month in range(1, months + 1):
        monthly_total = 0.0
        inflation_factor = (1 + annual_inflation) ** ((month - 1) / 12.0)
        for _, row in table.iterrows():
            if row["start_month"] <= month <= row["end_month"]:
                monthly_total += row["base_cost"] / row["duration_months"] * inflation_factor
        rows.append({"month": month, "planned_cost": monthly_total, "cumulative_cost": 0.0})
    cashflow = pd.DataFrame(rows)
    cashflow["cumulative_cost"] = cashflow["planned_cost"].cumsum()
    inflated_total = float(cashflow["planned_cost"].sum())
    summary = {
        "base_total": float(table["base_cost"].sum()),
        "inflated_total": inflated_total,
        "contingency": inflated_total * contingency_fraction,
        "total_with_contingency": inflated_total * (1 + contingency_fraction),
        "peak_monthly_burn": float(cashflow["planned_cost"].max()),
        "peak_burn_month": int(cashflow.loc[cashflow["planned_cost"].idxmax(), "month"]) if len(cashflow) else None,
    }
    return table, cashflow, summary


def participant_equity_burden(rows: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {"subgroup", "visits", "visit_minutes", "travel_minutes", "questionnaire_minutes", "digital_access_score", "discomfort_score"}
    missing = required - set(rows.columns)
    if missing:
        raise ValueError("Burden table is missing: " + ", ".join(sorted(missing)))
    table = rows.copy()
    for column in required - {"subgroup"}:
        table[column] = pd.to_numeric(table[column], errors="raise")
    if (table[list(required - {"subgroup"})] < 0).any().any():
        raise ValueError("Burden values cannot be negative.")
    table["time_hours"] = table["visits"] * (table["visit_minutes"] + table["travel_minutes"] + table["questionnaire_minutes"]) / 60.0
    table["burden_score"] = table["time_hours"] + 2 * table["digital_access_score"] + table["discomfort_score"]
    mean = float(table["burden_score"].mean()) if len(table) else 0.0
    maximum = float(table["burden_score"].max()) if len(table) else 0.0
    minimum = float(table["burden_score"].min()) if len(table) else 0.0
    summary = {
        "subgroups": int(table["subgroup"].nunique()),
        "mean_burden": mean,
        "max_burden": maximum,
        "equity_gap": maximum - minimum,
        "equity_ratio": maximum / mean if mean else 0.0,
    }
    return table, summary


def protocol_schedule_matrix(schedule: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"activity", "visit", "day", "required"}
    missing = required - set(schedule.columns)
    if missing:
        raise ValueError("Schedule is missing: " + ", ".join(sorted(missing)))
    table = schedule.copy()
    table["day"] = pd.to_numeric(table["day"], errors="raise")
    table["required"] = table["required"].map(lambda value: str(value).strip().lower() in {"1", "true", "yes", "y", "required"})
    if table[["activity", "visit"]].astype(str).duplicated().any():
        duplicates = table.loc[table[["activity", "visit"]].astype(str).duplicated(keep=False), ["activity", "visit"]]
        raise ValueError("Duplicate activity/visit combinations: " + duplicates.astype(str).agg(" @ ".join, axis=1).drop_duplicates().str.cat(sep=", "))
    matrix = table.pivot(index="activity", columns="visit", values="required").eq(True)
    visit_days = table.groupby("visit", as_index=False)["day"].median().sort_values("day")
    return matrix, visit_days


def protocol_redline(previous: Mapping[str, Any], current: Mapping[str, Any]) -> pd.DataFrame:
    rows = []
    for key in sorted(set(previous) | set(current)):
        old, new = previous.get(key), current.get(key)
        if old == new:
            continue
        rows.append({
            "section": key,
            "previous": json.dumps(old, default=str) if isinstance(old, (dict, list, tuple)) else old,
            "current": json.dumps(new, default=str) if isinstance(new, (dict, list, tuple)) else new,
            "change_type": "Added" if old in (None, "", [], {}) else "Removed" if new in (None, "", [], {}) else "Modified",
            "impact_required": key in _CHANGE_IMPACT,
        })
    return pd.DataFrame(rows)


def validate_crf_logic(fields: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"variable", "data_type", "required", "show_when_variable", "show_when_value"}
    missing = required - set(fields.columns)
    if missing:
        raise ValueError("CRF specification is missing: " + ", ".join(sorted(missing)))
    table = fields.copy().fillna("")
    table["variable"] = table["variable"].astype(str).str.strip()
    issues: list[dict[str, Any]] = []
    duplicates = table[table["variable"].duplicated(keep=False)]
    for variable in sorted(duplicates["variable"].unique()):
        issues.append({"variable": variable, "severity": "Critical", "issue": "Duplicate variable name"})
    variables = set(table["variable"])
    graph: dict[str, str] = {}
    for _, row in table.iterrows():
        source = str(row["show_when_variable"]).strip()
        target = str(row["variable"]).strip()
        if source:
            if source not in variables:
                issues.append({"variable": target, "severity": "Critical", "issue": f"Dependency source {source} does not exist"})
            elif source == target:
                issues.append({"variable": target, "severity": "Critical", "issue": "Field depends on itself"})
            graph[target] = source
        if str(row["data_type"]).lower() not in {"string", "integer", "float", "date", "datetime", "boolean", "choice"}:
            issues.append({"variable": target, "severity": "Major", "issue": "Unsupported data type"})
    for start in graph:
        seen: set[str] = set()
        node = start
        while node in graph:
            if node in seen:
                issues.append({"variable": start, "severity": "Critical", "issue": "Skip-logic dependency cycle"})
                break
            seen.add(node)
            node = graph[node]
    issue_table = pd.DataFrame(issues).drop_duplicates() if issues else pd.DataFrame(columns=["variable", "severity", "issue"])
    table["logic_status"] = table["variable"].map(lambda value: "Needs attention" if value in set(issue_table.get("variable", [])) else "Ready")
    return table, issue_table


def generate_crf_test_cases(fields: pd.DataFrame) -> pd.DataFrame:
    validated, issues = validate_crf_logic(fields)
    rows: list[dict[str, Any]] = []
    for _, row in validated.iterrows():
        variable = str(row["variable"])
        dtype = str(row["data_type"]).lower()
        rows.extend([
            {"variable": variable, "test_case": "Valid value", "expected": "Accepted", "test_value": {"integer": 1, "float": 1.5, "date": "2026-01-01", "datetime": "2026-01-01T12:00:00", "boolean": True}.get(dtype, "Valid")},
            {"variable": variable, "test_case": "Missing value", "expected": "Rejected" if str(row["required"]).lower() in {"1", "true", "yes", "required"} else "Accepted", "test_value": None},
        ])
        if str(row["show_when_variable"]).strip():
            rows.append({"variable": variable, "test_case": "Skip logic false", "expected": "Hidden", "test_value": "Dependency not met"})
    output = pd.DataFrame(rows)
    output["specification_has_critical_issue"] = output["variable"].isin(set(issues.loc[issues["severity"] == "Critical", "variable"])) if not issues.empty else False
    return output


_ALLOWED_OPERATORS = {"==", "!=", ">", ">=", "<", "<=", "in", "not_in", "contains"}


def evaluate_cohort_rules(participants: pd.DataFrame, rules: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"rule_id", "field", "operator", "value", "logic"}
    missing = required - set(rules.columns)
    if missing:
        raise ValueError("Rule table is missing: " + ", ".join(sorted(missing)))
    if participants.empty:
        raise ValueError("Participant table is empty.")
    table = participants.copy()
    mask: pd.Series | None = None
    audit: list[dict[str, Any]] = []
    for _, rule in rules.iterrows():
        field = str(rule["field"])
        operator = str(rule["operator"])
        logic = str(rule["logic"]).upper() or "AND"
        if field not in table.columns:
            raise ValueError(f"Rule field does not exist: {field}")
        if operator not in _ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported rule operator: {operator}")
        series = table[field]
        raw_value = rule["value"]
        if operator in {">", ">=", "<", "<="}:
            left = pd.to_numeric(series, errors="coerce")
            value = float(raw_value)
            current = {">": left > value, ">=": left >= value, "<": left < value, "<=": left <= value}[operator]
        elif operator == "==":
            current = series.astype(str) == str(raw_value)
        elif operator == "!=":
            current = series.astype(str) != str(raw_value)
        elif operator in {"in", "not_in"}:
            values = {item.strip() for item in str(raw_value).split("|") if item.strip()}
            current = series.astype(str).isin(values)
            if operator == "not_in":
                current = ~current
        else:
            current = series.astype(str).str.contains(re.escape(str(raw_value)), case=False, na=False)
        current = current.fillna(False)
        before = int(mask.sum()) if mask is not None else len(table)
        if mask is None:
            mask = current
        elif logic == "OR":
            mask = mask | current
        else:
            mask = mask & current
        after = int(mask.sum())
        audit.append({"rule_id": rule["rule_id"], "field": field, "operator": operator, "logic": logic, "eligible_after_rule": after, "excluded_at_step": max(0, before - after)})
    result = table.copy()
    result["eligible"] = mask if mask is not None else True
    return result, pd.DataFrame(audit)


def score_endpoints(endpoints: pd.DataFrame) -> pd.DataFrame:
    required = {"endpoint", "clinical_relevance", "validity", "reliability", "burden", "missingness_risk"}
    missing = required - set(endpoints.columns)
    if missing:
        raise ValueError("Endpoint table is missing: " + ", ".join(sorted(missing)))
    table = endpoints.copy()
    metrics = ["clinical_relevance", "validity", "reliability", "burden", "missingness_risk"]
    for column in metrics:
        table[column] = pd.to_numeric(table[column], errors="raise").clip(0, 100)
    table["value_score"] = 0.40 * table["clinical_relevance"] + 0.30 * table["validity"] + 0.20 * table["reliability"] + 0.10 * (100 - table["missingness_risk"])
    table["net_priority"] = table["value_score"] - 0.25 * table["burden"]
    table["rank"] = table["net_priority"].rank(method="dense", ascending=False).astype(int)
    table["recommended_role"] = np.select([table["rank"] == 1, table["rank"] <= 3], ["Primary candidate", "Secondary candidate"], default="Exploratory")
    return table.sort_values(["rank", "endpoint"]).reset_index(drop=True)


def composite_endpoint_contribution(events: pd.DataFrame) -> pd.DataFrame:
    required = {"component", "events", "total_participants", "clinical_weight"}
    missing = required - set(events.columns)
    if missing:
        raise ValueError("Composite endpoint table is missing: " + ", ".join(sorted(missing)))
    table = events.copy()
    for column in ("events", "total_participants", "clinical_weight"):
        table[column] = pd.to_numeric(table[column], errors="raise")
    if (table["total_participants"] <= 0).any() or (table[["events", "clinical_weight"]] < 0).any().any():
        raise ValueError("Composite endpoint counts and weights are invalid.")
    table["event_rate"] = table["events"] / table["total_participants"]
    table["weighted_events"] = table["events"] * table["clinical_weight"]
    total = table["weighted_events"].sum()
    table["contribution_fraction"] = table["weighted_events"] / total if total else 0.0
    table["dominance_flag"] = table["contribution_fraction"] > 0.70
    return table.sort_values("contribution_fraction", ascending=False).reset_index(drop=True)


def minimization_randomization(
    participants: pd.DataFrame,
    strata_columns: Sequence[str],
    arms: Sequence[str] = ("Control", "Treatment"),
    seed: int = 143,
    bias_probability: float = 0.80,
) -> pd.DataFrame:
    if not 0.5 <= bias_probability <= 1.0:
        raise ValueError("Bias probability must be between 0.5 and 1.0.")
    if len(arms) < 2 or len(set(arms)) != len(arms):
        raise ValueError("At least two unique arms are required.")
    if participants.empty:
        raise ValueError("No participants are available for randomization.")
    if "participant_id" not in participants.columns:
        raise ValueError("participant_id is required.")
    if participants["participant_id"].astype(str).duplicated().any():
        raise ValueError("Participant identifiers must be unique.")
    missing = [column for column in strata_columns if column not in participants.columns]
    if missing:
        raise ValueError("Missing stratification columns: " + ", ".join(missing))
    rng = np.random.default_rng(seed)
    arm_list = list(map(str, arms))
    assignments: list[dict[str, Any]] = []
    counts: dict[tuple[str, str, str], int] = {}
    total_counts = {arm: 0 for arm in arm_list}
    order = rng.permutation(len(participants))
    for sequence, idx in enumerate(order, start=1):
        row = participants.iloc[int(idx)]
        scores: dict[str, float] = {}
        for arm in arm_list:
            score = total_counts[arm]
            for column in strata_columns:
                level = str(row[column])
                score += counts.get((column, level, arm), 0)
            scores[arm] = float(score)
        minimum = min(scores.values())
        best = [arm for arm, score in scores.items() if score == minimum]
        if len(best) == 1 and rng.random() <= bias_probability:
            selected = best[0]
        else:
            selected = str(rng.choice(arm_list))
        total_counts[selected] += 1
        for column in strata_columns:
            level = str(row[column])
            counts[(column, level, selected)] = counts.get((column, level, selected), 0) + 1
        record = row.to_dict()
        record.update({"sequence": sequence, "assigned_arm": selected, "imbalance_score": scores[selected], "seed": seed})
        assignments.append(record)
    return pd.DataFrame(assignments).sort_values("sequence").reset_index(drop=True)


def allocation_audit(assignments: pd.DataFrame, strata_columns: Sequence[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {"participant_id", "assigned_arm"}
    missing = required - set(assignments.columns)
    if missing:
        raise ValueError("Assignment table is missing: " + ", ".join(sorted(missing)))
    rows: list[dict[str, Any]] = []
    for column in strata_columns:
        if column not in assignments.columns:
            raise ValueError(f"Missing stratification column: {column}")
        grouped = assignments.groupby([column, "assigned_arm"], dropna=False).size().unstack(fill_value=0)
        for level, counts in grouped.iterrows():
            rows.append({"stratum": column, "level": str(level), "minimum_arm_count": int(counts.min()), "maximum_arm_count": int(counts.max()), "absolute_imbalance": int(counts.max() - counts.min())})
    audit = pd.DataFrame(rows)
    proportions = assignments["assigned_arm"].value_counts(normalize=True)
    entropy = float(-(proportions * np.log2(proportions)).sum()) if len(proportions) else 0.0
    maximum_entropy = math.log2(max(1, assignments["assigned_arm"].nunique()))
    summary = {
        "participants": int(len(assignments)),
        "arms": int(assignments["assigned_arm"].nunique()),
        "maximum_stratum_imbalance": int(audit["absolute_imbalance"].max()) if len(audit) else 0,
        "assignment_entropy": entropy,
        "normalized_entropy": entropy / maximum_entropy if maximum_entropy else 0.0,
        "allocation_digest": sha256(assignments.to_csv(index=False).encode()).hexdigest(),
    }
    return audit, summary


def build_tfl_shells(analyses: pd.DataFrame) -> pd.DataFrame:
    required = {"analysis_id", "endpoint", "population", "model", "output_type", "source_dataset"}
    missing = required - set(analyses.columns)
    if missing:
        raise ValueError("SAP inventory is missing: " + ", ".join(sorted(missing)))
    table = analyses.copy()
    if table["analysis_id"].astype(str).duplicated().any():
        raise ValueError("Analysis identifiers must be unique.")
    allowed = {"Table", "Figure", "Listing"}
    invalid = ~table["output_type"].astype(str).isin(allowed)
    table["shell_status"] = np.where(invalid, "Needs review", "Ready")
    table["shell_title"] = table["output_type"].astype(str).str[0] + "-" + (table.index + 1).astype(str).str.zfill(3) + " · " + table["endpoint"].astype(str)
    table["lineage_key"] = table["source_dataset"].astype(str) + " → " + table["model"].astype(str) + " → " + table["shell_title"]
    return table


def method_compatibility_matrix() -> pd.DataFrame:
    methods = {
        "Continuous": {"Parallel": "ANCOVA / linear model", "Repeated": "Mixed-effects model", "Cluster": "Cluster-adjusted mixed model", "Crossover": "Period/sequence mixed model"},
        "Binary": {"Parallel": "Logistic / risk model", "Repeated": "GEE / GLMM", "Cluster": "Cluster-adjusted GLMM", "Crossover": "Conditional logistic model"},
        "Count": {"Parallel": "Poisson / negative binomial", "Repeated": "Count GLMM", "Cluster": "Cluster count model", "Crossover": "Period-adjusted count model"},
        "Time-to-event": {"Parallel": "Cox / RMST", "Repeated": "Recurrent-event model", "Cluster": "Frailty model", "Crossover": "Generally unsuitable"},
    }
    rows = []
    for outcome, designs in methods.items():
        for design, method in designs.items():
            rows.append({"outcome_type": outcome, "design": design, "recommended_method": method, "compatible": "unsuitable" not in method.lower()})
    return pd.DataFrame(rows)


def generate_synthetic_cohort(
    n: int = 500,
    seed: int = 143,
    missingness: float = 0.05,
    site_effect: float = 0.25,
) -> pd.DataFrame:
    if n < 10 or n > 1_000_000:
        raise ValueError("Synthetic cohort size must be between 10 and 1,000,000.")
    if not 0 <= missingness <= 0.8 or site_effect < 0:
        raise ValueError("Missingness or site effect is outside the supported range.")
    rng = np.random.default_rng(seed)
    sites = rng.choice(["Site A", "Site B", "Site C", "Site D"], n, p=[0.30, 0.25, 0.25, 0.20])
    site_offset = {"Site A": -site_effect, "Site B": 0.0, "Site C": site_effect, "Site D": 0.5 * site_effect}
    age = np.clip(rng.normal(52, 14, n), 18, 90)
    baseline = rng.normal(0, 1, n) + np.array([site_offset[site] for site in sites])
    treatment = rng.integers(0, 2, n)
    adherence = np.clip(rng.beta(8, 2, n), 0, 1)
    dropout_logit = -2.2 + 0.8 * (1 - adherence) + 0.25 * (baseline > 1)
    dropout_prob = 1 / (1 + np.exp(-dropout_logit))
    dropout = rng.random(n) < dropout_prob
    outcome = baseline + 0.45 * treatment * adherence - 0.015 * (age - 52) + rng.normal(0, 0.8, n)
    frame = pd.DataFrame({
        "synthetic_id": [f"SYN-{index + 1:07d}" for index in range(n)],
        "site": sites,
        "age": age,
        "baseline": baseline,
        "treatment": treatment,
        "adherence": adherence,
        "dropout_probability": dropout_prob,
        "dropout": dropout,
        "outcome": outcome,
        "synthetic_record": True,
    })
    for column in ("baseline", "outcome"):
        mask = rng.random(n) < missingness * (1 + 0.5 * dropout.astype(float))
        frame.loc[mask, column] = np.nan
    return frame


def synthetic_privacy_utility(real: pd.DataFrame, synthetic: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    numeric = sorted(set(real.select_dtypes(include="number").columns) & set(synthetic.select_dtypes(include="number").columns))
    if not numeric:
        raise ValueError("Real and synthetic tables need at least one shared numeric column.")
    rows = []
    for column in numeric:
        real_series = pd.to_numeric(real[column], errors="coerce").dropna()
        syn_series = pd.to_numeric(synthetic[column], errors="coerce").dropna()
        if real_series.empty or syn_series.empty:
            continue
        denominator = max(float(real_series.std(ddof=0)), 1e-9)
        mean_distance = abs(float(real_series.mean()) - float(syn_series.mean())) / denominator
        std_ratio = float(syn_series.std(ddof=0)) / denominator
        nearest = np.min(np.abs(real_series.to_numpy()[:, None] - syn_series.sample(min(250, len(syn_series)), random_state=143).to_numpy()[None, :]), axis=0)
        rows.append({
            "variable": column,
            "standardized_mean_distance": mean_distance,
            "std_ratio": std_ratio,
            "utility_score": max(0.0, 100 * (1 - min(1.0, 0.5 * mean_distance + 0.5 * abs(1 - std_ratio)))),
            "nearest_real_distance_median": float(np.median(nearest)),
        })
    comparison = pd.DataFrame(rows)
    summary = {
        "variables": int(len(comparison)),
        "mean_utility_score": float(comparison["utility_score"].mean()) if len(comparison) else 0.0,
        "minimum_nearest_distance": float(comparison["nearest_real_distance_median"].min()) if len(comparison) else 0.0,
        "disclosure_warning": bool(len(comparison) and (comparison["nearest_real_distance_median"] <= 1e-9).any()),
    }
    return comparison, summary


def reviewer_timeline(events: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "actor", "action", "module_key", "status"}
    missing = required - set(events.columns)
    if missing:
        raise ValueError("Review events are missing: " + ", ".join(sorted(missing)))
    table = events.copy()
    table["timestamp"] = pd.to_datetime(table["timestamp"], errors="raise", utc=True)
    table = table.sort_values("timestamp").reset_index(drop=True)
    table["event_number"] = np.arange(1, len(table) + 1)
    return table
