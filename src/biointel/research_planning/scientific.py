from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import ceil
from typing import Any, Callable

import numpy as np
import pandas as pd

from biointel.study_design import calculate_design
from .catalog import PlanningModule, get_module

MAX_ANALYSIS_ROWS = 250_000


@dataclass
class PlanningResult:
    module_key: str
    primary: pd.DataFrame
    secondary: pd.DataFrame
    tables: dict[str, pd.DataFrame]
    summary: dict[str, Any]
    main_finding: str
    confidence: str
    limitations: tuple[str, ...]
    next_step: str

    def all_tables(self) -> dict[str, pd.DataFrame]:
        return {"primary": self.primary, "secondary": self.secondary, **self.tables}


def _rng(seed: int = 141) -> np.random.Generator:
    return np.random.default_rng(seed)


def _bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y", "eligible", "locked", "required"})


def _num(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(default)


def _clip(series: pd.Series, low: float, high: float) -> pd.Series:
    return _num(series).clip(low, high)


def _safe_text(series: pd.Series, default: str = "Unspecified") -> pd.Series:
    values = series.astype("string").fillna(default).str.strip()
    return values.mask(values.eq(""), default).astype(str)


def dataframe_sha256(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False).encode("utf-8")
    return sha256(payload).hexdigest()


def normalise_input(frame: pd.DataFrame, module: PlanningModule) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Input must be a pandas DataFrame.")
    if len(frame) > MAX_ANALYSIS_ROWS:
        frame = frame.head(MAX_ANALYSIS_ROWS).copy()
    else:
        frame = frame.copy()
    if frame.columns.duplicated().any():
        duplicates = sorted(set(frame.columns[frame.columns.duplicated()].astype(str)))
        raise ValueError(f"Duplicate columns are not allowed: {', '.join(duplicates)}")
    frame.columns = [str(column).strip() for column in frame.columns]
    missing = [column for column in module.required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    return frame.loc[:, list(dict.fromkeys([*module.required_columns, *frame.columns]))]


def demo_frame(module_key: str, rows: int = 48) -> pd.DataFrame:
    rows = max(12, min(int(rows), 500))
    rng = _rng(abs(hash(module_key)) % 10_000 + 141)
    if module_key == "study_protocol_designer":
        sections = ["Background", "Objectives", "Population", "Endpoints", "Visits", "Statistics", "Safety", "Data Management", "Ethics", "Dissemination"]
        return pd.DataFrame({
            "section": sections,
            "owner": ["Scientific Lead", "PI", "Clinical Lead", "Statistician", "Operations", "Statistician", "Safety Lead", "Data Manager", "PI", "Medical Writer"],
            "status": ["Reviewed", "Reviewed", "In review", "Draft", "In review", "Draft", "Reviewed", "In review", "Draft", "Draft"],
            "completeness": [94, 100, 82, 76, 84, 70, 92, 78, 66, 55],
            "risk": [2, 1, 4, 5, 3, 5, 2, 4, 5, 3],
            "due_day": [5, 8, 12, 16, 20, 24, 25, 28, 30, 35],
        })
    if module_key == "sample_size_power_studio":
        scenarios = ["Base", "Conservative", "Optimistic", "High dropout", "Unequal allocation"]
        return pd.DataFrame({
            "scenario": scenarios,
            "design": ["two_group_continuous"] * 5,
            "effect_size": [0.50, 0.35, 0.65, 0.50, 0.50],
            "alpha": [0.05] * 5,
            "power": [0.80, 0.90, 0.80, 0.80, 0.80],
            "dropout": [0.10, 0.15, 0.05, 0.30, 0.10],
            "allocation_ratio": [1.0, 1.0, 1.0, 1.0, 2.0],
        })
    if module_key == "clinical_trial_design_studio":
        cohorts = ["Sentinel", "Dose 1", "Dose 2", "Expansion A", "Expansion B"]
        return pd.DataFrame({
            "cohort": cohorts,
            "arm": ["Experimental", "Experimental", "Experimental", "Experimental", "Control"],
            "participants": [6, 12, 18, 48, 48],
            "start_day": [0, 28, 70, 120, 120],
            "end_day": [28, 70, 120, 300, 300],
            "response_rate": [0.25, 0.35, 0.45, 0.50, 0.30],
            "dropout_rate": [0.05, 0.08, 0.10, 0.12, 0.12],
        })
    if module_key == "experimental_design_doe":
        n = max(16, min(rows, 64))
        a = np.tile([-1.0, 1.0], n // 2 + 1)[:n]
        b = np.tile([-1.0, -1.0, 1.0, 1.0], n // 4 + 1)[:n]
        c = rng.choice([-1.0, 1.0], size=n)
        response = 50 + 8 * a - 5 * b + 4 * a * b + 2 * c + rng.normal(0, 2, n)
        return pd.DataFrame({"run": np.arange(1, n + 1), "factor_a": a, "factor_b": b, "factor_c": c, "response": response.round(3)})
    if module_key == "randomization_blinding_allocation":
        n = max(24, rows)
        return pd.DataFrame({
            "participant_id": [f"P{i+1:04d}" for i in range(n)],
            "stratum": np.where(np.arange(n) % 2 == 0, "Biomarker+", "Biomarker-"),
            "site": [f"Site {(i % 4) + 1}" for i in range(n)],
            "arm": np.where(np.arange(n) % 2 == 0, "Treatment", "Control"),
            "sequence": np.arange(1, n + 1),
        })
    if module_key == "cohort_eligibility_builder":
        n = max(60, rows)
        age = rng.integers(18, 86, n)
        biomarker = rng.normal(4.8, 1.6, n).clip(0, 10)
        diagnosis = rng.choice(["Target disease", "Related condition", "No confirmed diagnosis"], n, p=[0.65, 0.2, 0.15])
        eligible = (age <= 75) & (biomarker >= 3.0) & (diagnosis == "Target disease")
        reason = np.where(age > 75, "Age above limit", np.where(biomarker < 3, "Biomarker below threshold", np.where(diagnosis != "Target disease", "Diagnosis mismatch", "Eligible")))
        return pd.DataFrame({
            "participant_id": [f"C{i+1:05d}" for i in range(n)], "age": age,
            "sex": rng.choice(["Female", "Male"], n), "biomarker": biomarker.round(2),
            "diagnosis": diagnosis, "eligible": eligible, "exclusion_reason": reason,
        })
    if module_key == "endpoint_outcome_strategy":
        endpoints = ["Overall response", "Progression-free survival", "Quality of life", "Biomarker change", "Safety events", "Treatment adherence"]
        return pd.DataFrame({
            "endpoint": endpoints,
            "type": ["Primary", "Secondary", "Secondary", "Exploratory", "Safety", "Exploratory"],
            "priority": [5, 4, 3, 3, 5, 2],
            "measurement_burden": [2, 3, 4, 2, 3, 4],
            "sensitivity": [0.86, 0.82, 0.72, 0.78, 0.92, 0.65],
            "specificity": [0.80, 0.84, 0.70, 0.74, 0.88, 0.68],
            "missingness_risk": [0.08, 0.12, 0.22, 0.18, 0.05, 0.28],
        })
    if module_key == "biomarker_study_planning":
        biomarkers = [f"Marker {letter}" for letter in "ABCDEFGH"]
        return pd.DataFrame({
            "biomarker": biomarkers,
            "stage": ["Discovery", "Discovery", "Verification", "Verification", "Validation", "Validation", "Qualification", "Discovery"],
            "evidence": [45, 62, 68, 54, 78, 84, 91, 38],
            "assay_readiness": [35, 48, 62, 58, 74, 86, 92, 30],
            "validation_status": ["Pending", "Pending", "Internal", "Internal", "External planned", "External", "Qualified", "Pending"],
            "effect_size": [0.42, 0.56, 0.61, 0.48, 0.68, 0.72, 0.75, 0.35],
        })
    if module_key == "sampling_biospecimen_planning":
        return pd.DataFrame({
            "sample_type": ["Blood", "Plasma", "Serum", "PBMC", "Tumour biopsy", "Urine", "Saliva", "Stool"],
            "visit": ["Baseline", "Week 4", "Week 8", "Baseline", "Baseline", "Week 4", "Week 8", "Baseline"],
            "participants": [120, 110, 105, 120, 60, 110, 105, 100],
            "volume_ml": [10, 4, 4, 18, 0.5, 30, 2, 5],
            "aliquots": [4, 3, 3, 5, 2, 3, 2, 4],
            "storage_temp": ["-80°C", "-80°C", "-80°C", "LN2", "-80°C", "-80°C", "-20°C", "-80°C"],
            "failure_rate": [0.03, 0.05, 0.05, 0.08, 0.12, 0.06, 0.04, 0.10],
        })
    if module_key == "data_collection_crf_designer":
        variables = [
            ("Subject_ID", "Identifiers", "string", True, "Screening", "Unique and non-empty", 100),
            ("Age", "Demographics", "integer", True, "Screening", "18–100", 100),
            ("Sex", "Demographics", "category", True, "Screening", "Controlled list", 100),
            ("Diagnosis_Date", "Medical History", "date", True, "Baseline", "Not future", 90),
            ("Treatment_Arm", "Treatment", "category", True, "Baseline", "Randomization code", 85),
            ("Response", "Outcomes", "category", True, "Week 12", "RECIST values", 80),
            ("QoL_Score", "Outcomes", "number", False, "Week 12", "0–100", 75),
            ("Adverse_Event", "Safety", "string", False, "Every visit", "Conditional details", 70),
        ]
        return pd.DataFrame(variables, columns=["variable", "domain", "data_type", "required", "visit", "validation_rule", "completeness"])
    if module_key == "statistical_analysis_plan":
        return pd.DataFrame({
            "analysis": ["Primary efficacy", "Key secondary", "Safety", "Biomarker subgroup", "Sensitivity MI", "Per-protocol sensitivity"],
            "endpoint": ["Overall response", "PFS", "Adverse events", "Response", "Overall response", "Overall response"],
            "population": ["ITT", "ITT", "Safety", "ITT", "ITT", "PP"],
            "model": ["Logistic regression", "Cox model", "Descriptive", "Interaction model", "Multiple imputation + logistic", "Logistic regression"],
            "covariates": ["Baseline status, site", "Site, disease stage", "None", "Biomarker, treatment, interaction", "Baseline status, site", "Baseline status"],
            "multiplicity": ["Gatekeeping", "Gatekeeping", "None", "Exploratory", "Sensitivity", "Sensitivity"],
            "status": ["Reviewed", "Reviewed", "Draft", "Draft", "Planned", "Planned"],
        })
    if module_key == "research_feasibility_recruitment":
        n = 8
        return pd.DataFrame({
            "site": [f"Site {i+1}" for i in range(n)],
            "eligible_pool": rng.integers(60, 240, n),
            "screen_rate": rng.uniform(0.45, 0.78, n).round(3),
            "monthly_recruitment": rng.uniform(2.0, 9.0, n).round(2),
            "startup_months": rng.uniform(1.0, 5.0, n).round(2),
            "dropout_rate": rng.uniform(0.05, 0.22, n).round(3),
            "cost_per_subject": rng.integers(2500, 9500, n),
        })
    if module_key == "research_timeline_dependencies":
        return pd.DataFrame({
            "task": ["Protocol", "Ethics submission", "Database build", "Site selection", "Site activation", "Recruitment", "Sample analysis", "Database lock", "Statistical analysis", "Final report"],
            "phase": ["Planning", "Approvals", "Setup", "Setup", "Setup", "Execution", "Execution", "Closeout", "Analysis", "Reporting"],
            "duration_days": [30, 45, 35, 28, 35, 180, 120, 21, 30, 25],
            "predecessor": ["", "Protocol", "Protocol", "Protocol", "Ethics submission;Site selection", "Site activation", "Recruitment", "Sample analysis", "Database lock", "Statistical analysis"],
            "owner": ["PI", "Regulatory", "Data Manager", "Operations", "Operations", "Sites", "Laboratory", "Data Manager", "Statistician", "Medical Writer"],
            "progress": [100, 60, 70, 80, 30, 0, 0, 0, 0, 0],
            "risk": [2, 4, 3, 2, 4, 5, 4, 3, 3, 2],
        })
    if module_key == "research_risk_mitigation":
        return pd.DataFrame({
            "risk": ["Slow recruitment", "Assay failure", "High dropout", "Batch effect", "Endpoint missingness", "Reference update", "Site delay", "Underpowered subgroup"],
            "category": ["Recruitment", "Assay", "Clinical", "Data", "Statistics", "Scientific", "Operations", "Statistics"],
            "probability": [4, 3, 3, 4, 3, 2, 4, 4],
            "impact": [5, 5, 4, 4, 4, 3, 4, 3],
            "mitigation_status": ["In progress", "Planned", "Planned", "In progress", "Planned", "Monitored", "In progress", "Open"],
            "owner": ["Clinical Ops", "Lab Lead", "PI", "Data Lead", "Statistician", "Bioinformatics", "Clinical Ops", "Statistician"],
        })
    if module_key == "evidence_gap_literature_planning":
        questions = ["Earlier diagnosis", "Response prediction", "Long-term safety", "Paediatric population", "Rare subgroup", "Real-world effectiveness", "Mechanism", "Dose optimisation"]
        return pd.DataFrame({
            "question": questions,
            "population": ["Adults", "Biomarker+", "All", "Paediatric", "Rare genotype", "Routine care", "Translational", "All"],
            "intervention": ["Diagnostic test", "Therapy", "Therapy", "Therapy", "Therapy", "Therapy", "Mechanistic assay", "Dose strategy"],
            "comparator": ["Standard care", "Control", "External cohort", "Standard care", "Control", "Historical", "Reference", "Standard dose"],
            "outcome": ["Sensitivity", "Response", "Safety", "Response", "Response", "Effectiveness", "Pathway activity", "Benefit-risk"],
            "evidence_count": [18, 12, 8, 3, 2, 5, 10, 4],
            "quality": ["Moderate", "Moderate", "Low", "Very low", "Very low", "Low", "Moderate", "Low"],
            "contradiction": [0.20, 0.35, 0.45, 0.10, 0.25, 0.55, 0.40, 0.30],
        })
    if module_key == "preregistration_reproducibility":
        items = ["Primary hypothesis", "Primary endpoint", "Sample size", "Exclusion rules", "Primary model", "Covariates", "Multiplicity", "Random seed", "Sensitivity analyses", "Stopping rule"]
        planned = ["Treatment improves response", "Overall response", "140", "Predefined QC", "Logistic regression", "Site, baseline", "Gatekeeping", "84721", "MI and PP", "No early efficacy stop"]
        executed = planned.copy()
        executed[7] = "84721"
        executed[8] = "MI, PP and tipping point"
        return pd.DataFrame({
            "item": items,
            "section": ["Hypothesis", "Outcomes", "Design", "Population", "Analysis", "Analysis", "Analysis", "Reproducibility", "Analysis", "Interim"],
            "locked": [True] * 8 + [False, True],
            "status": ["Locked"] * 8 + ["Amended", "Locked"],
            "planned_value": planned,
            "executed_value": executed,
            "deviation_reason": [""] * 8 + ["Added after blinded missingness review", ""],
        })
    raise KeyError(f"No demo generator for {module_key}")


def _quality_table(dimensions: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({"dimension": list(dimensions), "score": [round(float(value), 1) for value in dimensions.values()]})


def _timeline_from_primary(frame: pd.DataFrame, label: str, start: str, end: str, owner: str | None = None) -> pd.DataFrame:
    columns = {"label": _safe_text(frame[label]), "start_day": _num(frame[start]).astype(float), "end_day": _num(frame[end]).astype(float)}
    if owner and owner in frame:
        columns[owner] = _safe_text(frame[owner])
    return pd.DataFrame(columns)


def _analyse_protocol(frame: pd.DataFrame) -> PlanningResult:
    data = frame.copy()
    data["section"] = _safe_text(data["section"])
    data["owner"] = _safe_text(data["owner"])
    data["status"] = _safe_text(data["status"])
    data["completeness"] = _clip(data["completeness"], 0, 100)
    data["risk"] = _clip(data["risk"], 1, 5)
    data["due_day"] = _num(data["due_day"]).clip(lower=0)
    data["readiness"] = (data["completeness"] - 8 * (data["risk"] - 1)).clip(0, 100)
    requirements = ["Objectives", "Population", "Endpoints", "Procedures", "Statistics", "Safety", "Data", "Ethics"]
    matrix = pd.MultiIndex.from_product([data["section"], requirements], names=["section", "requirement"]).to_frame(index=False)
    base = data.set_index("section")["completeness"]
    matrix["score"] = [max(0, min(100, float(base.get(section, 50)) + ((hash(section + req) % 17) - 8))) for section, req in zip(matrix["section"], matrix["requirement"])]
    timeline = pd.DataFrame({"label": data["section"], "start_day": (data["due_day"] - 7).clip(lower=0), "end_day": data["due_day"], "owner": data["owner"]})
    status_counts = data.groupby("status", as_index=False).size().rename(columns={"size": "records"})
    funnel = pd.DataFrame({"stage": ["Sections", "≥70% complete", "Reviewed", "Low risk"], "records": [len(data), int((data["completeness"] >= 70).sum()), int(data["status"].str.lower().eq("reviewed").sum()), int((data["risk"] <= 2).sum())]})
    quality = _quality_table({"Completeness": data["completeness"].mean(), "Ownership": 100 * data["owner"].ne("Unspecified").mean(), "Review": 100 * data["status"].str.lower().isin(["reviewed", "approved"]).mean(), "Risk control": 100 - 20 * (data["risk"].mean() - 1), "Schedule": 100 * data["due_day"].gt(0).mean()})
    summary = {"sections": len(data), "mean_completeness": round(data["completeness"].mean(), 1), "high_risk_sections": int((data["risk"] >= 4).sum()), "reviewed_sections": int(data["status"].str.lower().eq("reviewed").sum()), "input_sha256": dataframe_sha256(frame)}
    weakest = data.sort_values(["readiness", "risk"], ascending=[True, False]).iloc[0]
    return PlanningResult("study_protocol_designer", data.sort_values("readiness"), status_counts, {"matrix": matrix, "timeline": timeline, "funnel": funnel, "quality": quality}, summary, f"{weakest['section']} is the current protocol bottleneck at {weakest['completeness']:.0f}% completeness.", "Moderate", ("Completeness scores are planning metadata, not ethical or regulatory approval.", "Section quality still requires expert review."), "Resolve high-risk incomplete sections, then lock a reviewed protocol version.")


def _design_result(row: pd.Series) -> dict[str, Any]:
    design = str(row.get("design", "two_group_continuous")).strip().lower()
    kwargs: dict[str, Any] = {
        "alpha": float(row.get("alpha", 0.05)), "power": float(row.get("power", 0.8)),
        "dropout_fraction": float(row.get("dropout", 0.1)), "allocation_ratio": float(row.get("allocation_ratio", 1.0)),
    }
    if design in {"two_group_continuous", "paired_continuous", "one_way_anova", "repeated_measures", "cluster_randomized"}:
        kwargs["effect_size"] = max(0.01, float(row.get("effect_size", 0.5)))
    if design == "two_proportions":
        kwargs["proportion_1"], kwargs["proportion_2"] = 0.5, min(0.99, 0.5 + max(0.02, float(row.get("effect_size", 0.2))))
    result = calculate_design(design, **kwargs)
    return {"total_sample_size": result.total_sample_size, "complete_case_total": result.complete_case_total, "method": result.method, "adjusted_alpha": result.assumptions.get("adjusted_alpha", kwargs["alpha"])}


def _analyse_sample_size(frame: pd.DataFrame) -> PlanningResult:
    data = frame.copy()
    data["scenario"] = _safe_text(data["scenario"])
    data["design"] = _safe_text(data["design"], "two_group_continuous")
    for col, low, high, default in [("effect_size", 0.01, 5, 0.5), ("alpha", 0.0001, 0.25, 0.05), ("power", 0.5, 0.999, 0.8), ("dropout", 0, 0.79, 0.1), ("allocation_ratio", 0.1, 10, 1.0)]:
        data[col] = _num(data[col], default).clip(low, high)
    calculations = []
    warnings: list[str] = []
    for _, row in data.iterrows():
        try:
            calculations.append(_design_result(row))
        except Exception as exc:
            calculations.append({"total_sample_size": np.nan, "complete_case_total": np.nan, "method": "failed", "adjusted_alpha": row["alpha"]})
            warnings.append(f"{row['scenario']}: {exc}")
    calc = pd.DataFrame(calculations)
    data = pd.concat([data.reset_index(drop=True), calc], axis=1)
    sens_rows = []
    for _, row in data.dropna(subset=["total_sample_size"]).iterrows():
        base_n = int(row["complete_case_total"])
        for n in np.unique(np.maximum(4, np.round(np.linspace(base_n * 0.5, base_n * 1.6, 24))).astype(int)):
            # Smooth monotonic planning approximation around the target design point.
            achieved = 0.5 + (float(row["power"]) - 0.5) * min(1.8, n / max(base_n, 1)) ** 0.5
            sens_rows.append({"scenario": row["scenario"], "total_sample_size": int(n), "achieved_power": min(0.999, achieved)})
    sensitivity = pd.DataFrame(sens_rows)
    grid = pd.MultiIndex.from_product([np.round(np.linspace(0.2, 0.9, 8), 2), np.round(np.linspace(0.7, 0.95, 6), 2)], names=["effect_size", "target_power"]).to_frame(index=False)
    grid["required_n"] = np.ceil(16 * (1 / grid["effect_size"] ** 2) * (grid["target_power"] / 0.8)).astype(int)
    dropout_rows, allocation_rows, precision_rows = [], [], []
    for _, row in data.dropna(subset=["complete_case_total"]).iterrows():
        complete = int(row["complete_case_total"])
        for value in np.linspace(0, 0.4, 9):
            dropout_rows.append({"scenario": row["scenario"], "dropout": value, "total_sample_size": ceil(complete / (1 - value))})
        for ratio in [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]:
            allocation_rows.append({"scenario": row["scenario"], "allocation_ratio": ratio, "total_sample_size": ceil(complete * (1 + 0.08 * abs(np.log(ratio))))})
        for n in np.linspace(max(10, complete * 0.5), complete * 2, 12).astype(int):
            precision_rows.append({"scenario": row["scenario"], "sample_size": int(n), "ci_half_width": round(1.96 / np.sqrt(n), 4)})
    quality = _quality_table({"Assumption completeness": 100 * data[["effect_size", "alpha", "power", "dropout", "allocation_ratio"]].notna().all(axis=1).mean(), "Scenario diversity": min(100, 20 * len(data)), "Sensitivity coverage": 100 if not sensitivity.empty else 0, "Dropout planning": 100 * data["dropout"].notna().mean(), "Calculation success": 100 * data["total_sample_size"].notna().mean()})
    valid = data.dropna(subset=["total_sample_size"])
    summary = {"scenarios": len(data), "successful": len(valid), "median_recruitment": int(valid["total_sample_size"].median()) if not valid.empty else 0, "maximum_recruitment": int(valid["total_sample_size"].max()) if not valid.empty else 0, "warnings": warnings, "input_sha256": dataframe_sha256(frame)}
    return PlanningResult("sample_size_power_studio", data, sensitivity, {"grid": grid, "dropout": pd.DataFrame(dropout_rows), "allocation": pd.DataFrame(allocation_rows), "precision": pd.DataFrame(precision_rows), "quality": quality}, summary, f"Across valid scenarios, median planned recruitment is {summary['median_recruitment']:,} participants.", "Moderate", ("Power estimates are only as credible as their effect-size and variance assumptions.", "Specialist methods may be required for complex outcomes or adaptive designs."), "Review the conservative scenario and lock justified assumptions in the protocol and SAP.")


def _analyse_trial(frame: pd.DataFrame) -> PlanningResult:
    data = frame.copy()
    for col in ["cohort", "arm"]: data[col] = _safe_text(data[col])
    data["participants"] = _num(data["participants"]).clip(lower=0).round().astype(int)
    data["start_day"] = _num(data["start_day"]).clip(lower=0)
    data["end_day"] = np.maximum(_num(data["end_day"]), data["start_day"] + 1)
    data["response_rate"] = _clip(data["response_rate"], 0, 1)
    data["dropout_rate"] = _clip(data["dropout_rate"], 0, 0.79)
    data["expected_completers"] = np.floor(data["participants"] * (1 - data["dropout_rate"])).astype(int)
    data["expected_responders"] = np.round(data["expected_completers"] * data["response_rate"], 1)
    months = np.arange(0, max(2, int(np.ceil(data["end_day"].max() / 30)) + 1))
    recruitment = []
    for _, row in data.iterrows():
        duration = max(1, (row["end_day"] - row["start_day"]) / 30)
        for month in months:
            active = np.clip((month - row["start_day"] / 30) / duration, 0, 1)
            recruitment.append({"month": int(month), "arm": row["arm"], "cohort": row["cohort"], "cumulative_enrolled": int(round(row["participants"] * active))})
    recruitment_df = pd.DataFrame(recruitment).groupby(["month", "arm"], as_index=False)["cumulative_enrolled"].sum()
    funnel = pd.DataFrame({"stage": ["Planned", "Expected enrolled", "Expected completers", "Expected responders"], "participants": [int(data["participants"].sum()), int(data["participants"].sum()), int(data["expected_completers"].sum()), int(round(data["expected_responders"].sum()))]})
    interim = pd.DataFrame({"information_fraction": [0.25, 0.5, 0.75, 1.0], "boundary": [3.47, 2.45, 2.00, 1.96], "decision": ["Continue", "Continue/Review", "Review", "Final"]})
    timeline = pd.DataFrame({"label": data["cohort"], "start_day": data["start_day"], "end_day": data["end_day"], "arm": data["arm"]})
    quality = _quality_table({"Cohort definition": 100 * data["cohort"].ne("Unspecified").mean(), "Arm balance": max(0, 100 - 100 * data.groupby("arm")["participants"].sum().std(ddof=0) / max(1, data["participants"].sum())), "Dropout planning": 100 * data["dropout_rate"].notna().mean(), "Timeline": 100 * (data["end_day"] > data["start_day"]).mean(), "Interim strategy": 80})
    summary = {"cohorts": len(data), "arms": data["arm"].nunique(), "planned_participants": int(data["participants"].sum()), "expected_completers": int(data["expected_completers"].sum()), "expected_responders": float(data["expected_responders"].sum()), "input_sha256": dataframe_sha256(frame)}
    return PlanningResult("clinical_trial_design_studio", data, recruitment_df, {"recruitment": recruitment_df, "funnel": funnel, "interim": interim, "timeline": timeline, "quality": quality}, summary, f"The plan includes {summary['planned_participants']:,} participants across {summary['arms']} arms, with {summary['expected_completers']:,} expected completers.", "Moderate", ("Response and dropout assumptions are scenario values.", "Operational feasibility and regulatory requirements are not established by this simulation."), "Stress-test recruitment and dropout assumptions in the Synthetic Cohort & Trial Simulation Lab.")


def _analyse_doe(frame: pd.DataFrame) -> PlanningResult:
    data = frame.copy()
    data["run"] = _safe_text(data["run"])
    for col in ["factor_a", "factor_b", "factor_c", "response"]: data[col] = _num(data[col])
    x = np.column_stack([np.ones(len(data)), data["factor_a"], data["factor_b"], data["factor_c"], data["factor_a"] * data["factor_b"], data["factor_a"] * data["factor_c"], data["factor_b"] * data["factor_c"]])
    terms = ["Intercept", "A", "B", "C", "A×B", "A×C", "B×C"]
    coef, *_ = np.linalg.lstsq(x, data["response"].to_numpy(float), rcond=None)
    predicted = x @ coef
    pred = data[["run"]].copy(); pred["observed"] = data["response"]; pred["predicted"] = predicted; pred["residual"] = pred["observed"] - pred["predicted"]
    effects = pd.DataFrame({"term": terms[1:], "effect": coef[1:] * 2}); effects["abs_effect"] = effects["effect"].abs(); effects["sign"] = np.where(effects["effect"] >= 0, "Positive", "Negative")
    interaction = pd.DataFrame({"factor_1": ["A", "A", "B"], "factor_2": ["B", "C", "C"], "effect": [coef[4] * 2, coef[5] * 2, coef[6] * 2]})
    factors = pd.DataFrame({"run": np.repeat(data["run"].values, 3), "factor": np.tile(["A", "B", "C"], len(data)), "level": np.column_stack([data["factor_a"], data["factor_b"], data["factor_c"]]).reshape(-1)})
    grid_a, grid_b = np.meshgrid(np.linspace(data["factor_a"].min(), data["factor_a"].max(), 20), np.linspace(data["factor_b"].min(), data["factor_b"].max(), 20))
    grid_c = float(data["factor_c"].median())
    z = coef[0] + coef[1] * grid_a + coef[2] * grid_b + coef[3] * grid_c + coef[4] * grid_a * grid_b + coef[5] * grid_a * grid_c + coef[6] * grid_b * grid_c
    surface = pd.DataFrame({"factor_a": grid_a.ravel(), "factor_b": grid_b.ravel(), "response": z.ravel()})
    ss_res = float(np.sum((data["response"] - predicted) ** 2)); ss_tot = float(np.sum((data["response"] - data["response"].mean()) ** 2)); r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    quality = _quality_table({"Run completeness": 100 * data.notna().all(axis=1).mean(), "Factor balance": 100 - min(100, 20 * sum(abs(data[col].mean()) for col in ["factor_a", "factor_b", "factor_c"])), "Model fit": 100 * max(0, min(1, r2)), "Replication": min(100, 20 * len(data) / max(1, data[["factor_a", "factor_b", "factor_c"]].drop_duplicates().shape[0])), "Randomisation": 80})
    summary = {"runs": len(data), "r_squared": round(r2, 4), "largest_effect": effects.sort_values("abs_effect", ascending=False).iloc[0]["term"], "residual_rmse": round(float(np.sqrt(np.mean(pred["residual"] ** 2))), 4), "input_sha256": dataframe_sha256(frame)}
    return PlanningResult("experimental_design_doe", data, effects, {"effects": effects, "interaction": interaction, "matrix": factors, "surface": surface, "predictions": pred, "quality": quality}, summary, f"{summary['largest_effect']} is the largest estimated effect; the screening model explains {100*r2:.1f}% of observed variation.", "Moderate" if len(data) >= 16 else "Low", ("The linear screening model may miss curvature and higher-order effects.", "Confirm optima with independent runs and measurement-system checks."), "Review residuals and interactions, then schedule confirmatory runs around the candidate optimum.")


def _analyse_randomization(frame: pd.DataFrame) -> PlanningResult:
    data = frame.copy()
    for col in ["participant_id", "stratum", "site", "arm"]: data[col] = _safe_text(data[col])
    data["sequence"] = _num(data["sequence"]).round().astype(int)
    if data["participant_id"].duplicated().any(): raise ValueError("Participant identifiers must be unique.")
    counts = data.groupby(["site", "stratum", "arm"], as_index=False).size().rename(columns={"size": "participants"})
    matrix = data.groupby(["stratum", "arm"]).size().unstack(fill_value=0).stack().reset_index(name="participants")
    site_matrix = data.groupby(["site", "arm"]).size().unstack(fill_value=0).stack().reset_index(name="participants")
    ordered = data.sort_values("sequence").reset_index(drop=True)
    arms = sorted(data["arm"].unique())
    if len(arms) >= 2:
        ordered["imbalance"] = np.cumsum(np.where(ordered["arm"].eq(arms[0]), 1, -1))
    else: ordered["imbalance"] = np.arange(1, len(ordered)+1)
    blocks = pd.DataFrame({"block_size": [4, 6, 8], "blocks": [max(1, len(data)//12), max(1, len(data)//18), max(1, len(data)//24)], "site": ["Mixed"]*3})
    quality = _quality_table({"Unique IDs": 100, "Arm balance": max(0, 100 - 100 * data["arm"].value_counts().std(ddof=0) / max(1, len(data))), "Stratum balance": max(0, 100 - 20 * matrix.groupby("stratum")["participants"].std(ddof=0).fillna(0).mean()), "Site balance": max(0, 100 - 20 * site_matrix.groupby("site")["participants"].std(ddof=0).fillna(0).mean()), "Concealment plan": 80})
    summary = {"participants": len(data), "arms": data["arm"].nunique(), "strata": data["stratum"].nunique(), "sites": data["site"].nunique(), "maximum_sequence_imbalance": int(ordered["imbalance"].abs().max()), "input_sha256": dataframe_sha256(frame)}
    return PlanningResult("randomization_blinding_allocation", counts, ordered, {"matrix": matrix, "site_matrix": site_matrix, "sequence": ordered, "blocks": blocks, "imbalance": ordered[["sequence", "stratum", "imbalance"]], "quality": quality}, summary, f"The schedule allocates {summary['participants']} participants across {summary['arms']} arms with maximum running imbalance {summary['maximum_sequence_imbalance']}.", "High" if summary["maximum_sequence_imbalance"] <= 4 else "Moderate", ("This audit cannot verify whether allocation codes were kept concealed.", "Operational re-randomisation must be controlled independently."), "Separate the blinded operational schedule from the unblinding key and lock both manifests.")


def _analyse_cohort(frame: pd.DataFrame) -> PlanningResult:
    data = frame.copy()
    data["participant_id"] = _safe_text(data["participant_id"])
    data["age"] = _num(data["age"])
    data["sex"] = _safe_text(data["sex"])
    data["biomarker"] = _num(data["biomarker"])
    data["diagnosis"] = _safe_text(data["diagnosis"])
    data["eligible"] = _bool_series(data["eligible"])
    data["exclusion_reason"] = _safe_text(data["exclusion_reason"])
    eligible_n = int(data["eligible"].sum())
    exclusions = data.loc[~data["eligible"]].groupby("exclusion_reason", as_index=False).size().rename(columns={"size": "participants"}).sort_values("participants", ascending=False)
    funnel = pd.DataFrame({"stage": ["Candidate records", "Complete key fields", "Meets diagnosis", "Meets all rules"], "participants": [len(data), int(data[["age", "biomarker", "diagnosis"]].notna().all(axis=1).sum()), int(data["diagnosis"].eq("Target disease").sum()), eligible_n]})
    rules = pd.DataFrame({"rule": ["Diagnosis", "Age", "Biomarker", "Other/combined"], "removed": [int(data["diagnosis"].ne("Target disease").sum()), int((data["age"] > 75).sum()), int((data["biomarker"] < 3).sum()), max(0, len(data)-eligible_n-int(data["diagnosis"].ne("Target disease").sum()))]})
    fields = ["age", "sex", "biomarker", "diagnosis"]
    missing = pd.DataFrame([{"field": col, "group": "All", "missing_percent": 100 * data[col].isna().mean()} for col in fields])
    overlap = rules.assign(participants=rules["removed"])
    quality = _quality_table({"ID uniqueness": 100 * (1 - data["participant_id"].duplicated().mean()), "Key field completeness": 100 * data[fields].notna().mean().mean(), "Rule explainability": 100 * data["exclusion_reason"].ne("Unspecified").mean(), "Eligibility yield": 100 * eligible_n / max(1, len(data)), "Cohort size": min(100, eligible_n)})
    summary = {"candidates": len(data), "eligible": eligible_n, "eligibility_rate": round(eligible_n / max(1, len(data)), 4), "top_exclusion": exclusions.iloc[0]["exclusion_reason"] if not exclusions.empty else "None", "input_sha256": dataframe_sha256(frame)}
    return PlanningResult("cohort_eligibility_builder", data, exclusions, {"funnel": funnel, "exclusions": exclusions, "rules": rules, "missingness": missing, "overlap": overlap, "quality": quality}, summary, f"{eligible_n} of {len(data)} candidates ({100*summary['eligibility_rate']:.1f}%) meet the current rules; the leading exclusion is {summary['top_exclusion']}.", "Moderate", ("Eligibility depends on the imported variables and simplified rule representation.", "Clinical exceptions and temporal logic require adjudication."), "Review the highest-impact exclusion rules and validate the definition on an independent source cohort.")


def _analyse_endpoint(frame: pd.DataFrame) -> PlanningResult:
    data = frame.copy()
    for col in ["endpoint", "type"]: data[col] = _safe_text(data[col])
    data["priority"] = _clip(data["priority"], 1, 5); data["measurement_burden"] = _clip(data["measurement_burden"], 1, 5)
    data["sensitivity"] = _clip(data["sensitivity"], 0, 1); data["specificity"] = _clip(data["specificity"], 0, 1); data["missingness_risk"] = _clip(data["missingness_risk"], 0, 1)
    data["validity_score"] = 100 * (data["sensitivity"] + data["specificity"]) / 2
    data["priority_score"] = (20 * data["priority"] + data["validity_score"] - 12 * data["measurement_burden"] - 35 * data["missingness_risk"]).clip(0, 100)
    hierarchy = data[["type", "endpoint", "priority_score"]].rename(columns={"priority_score": "value"})
    matrix = pd.MultiIndex.from_product([data["endpoint"], data["endpoint"]], names=["endpoint_1", "endpoint_2"]).to_frame(index=False)
    matrix["planned_correlation"] = [1.0 if a == b else round(0.15 + (hash(a+b) % 55)/100, 2) for a,b in zip(matrix["endpoint_1"], matrix["endpoint_2"])]
    decision = pd.MultiIndex.from_product([data["endpoint"], ["Relevance", "Validity", "Burden", "Missingness", "Multiplicity"]], names=["endpoint", "criterion"]).to_frame(index=False)
    scores = data.set_index("endpoint")
    decision["score"] = [float(scores.loc[e, "priority_score"]) if c in {"Relevance","Validity"} else 100-float(scores.loc[e,"measurement_burden"])*15 if c=="Burden" else 100-float(scores.loc[e,"missingness_risk"])*100 if c=="Missingness" else 75 for e,c in zip(decision["endpoint"], decision["criterion"])]
    timeline = pd.DataFrame({"label": data["endpoint"], "start_day": np.arange(len(data))*5, "end_day": np.arange(len(data))*5+90, "endpoint": data["endpoint"]})
    quality = _quality_table({"Primary clarity": 100 if data["type"].str.lower().eq("primary").sum()==1 else 60, "Validity": data["validity_score"].mean(), "Low burden": 100-20*(data["measurement_burden"].mean()-1), "Missingness control": 100*(1-data["missingness_risk"].mean()), "Multiplicity plan": 75})
    summary = {"endpoints": len(data), "primary_endpoints": int(data["type"].str.lower().eq("primary").sum()), "top_endpoint": data.sort_values("priority_score", ascending=False).iloc[0]["endpoint"], "mean_validity": round(data["validity_score"].mean(),1), "input_sha256": dataframe_sha256(frame)}
    return PlanningResult("endpoint_outcome_strategy", data.sort_values("priority_score", ascending=False), hierarchy, {"hierarchy": hierarchy, "matrix": matrix, "decision": decision, "timeline": timeline, "quality": quality}, summary, f"{summary['top_endpoint']} has the strongest composite priority after accounting for validity, burden and missingness.", "Moderate", ("Input sensitivity and specificity values may be hypothetical.", "Endpoint hierarchy must align with estimands and multiplicity control."), "Confirm one primary endpoint and document the measurement and adjudication strategy.")


def _analyse_biomarker(frame: pd.DataFrame) -> PlanningResult:
    data = frame.copy()
    for col in ["biomarker", "stage", "validation_status"]: data[col] = _safe_text(data[col])
    data["evidence"] = _clip(data["evidence"],0,100); data["assay_readiness"] = _clip(data["assay_readiness"],0,100); data["effect_size"] = _num(data["effect_size"]).clip(lower=0)
    val_bonus = data["validation_status"].str.lower().map({"pending":0,"internal":10,"external planned":15,"external":25,"qualified":30}).fillna(5)
    data["maturity_score"] = (0.4*data["evidence"]+0.35*data["assay_readiness"]+20*np.tanh(data["effect_size"])+val_bonus).clip(0,100)
    funnel = data.groupby("stage", as_index=False).size().rename(columns={"size":"biomarkers"})
    cohort = pd.DataFrame({"cohort":["Discovery","Internal validation","External validation"],"participants":[120,80,160]})
    cutoff = pd.DataFrame([{"threshold":t,"metric":metric,"performance":max(0,min(1,0.72+0.18*np.exp(-((t-0.55)/0.22)**2)+(0.03 if metric=="Specificity" else 0)))} for t in np.linspace(0.1,0.9,17) for metric in ["Sensitivity","Specificity"]])
    matrix = pd.MultiIndex.from_product([data["biomarker"], ["Analytical","Internal","External","Utility"]], names=["biomarker","validation_stage"]).to_frame(index=False)
    maturity=data.set_index("biomarker")["maturity_score"]; matrix["score"]=[max(0,min(100,float(maturity[b])+((hash(b+s)%31)-15))) for b,s in zip(matrix["biomarker"],matrix["validation_stage"])]
    timeline=pd.DataFrame({"label":data["biomarker"],"start_day":np.arange(len(data))*15,"end_day":np.arange(len(data))*15+90,"stage":data["stage"]})
    quality=_quality_table({"Evidence":data["evidence"].mean(),"Assay readiness":data["assay_readiness"].mean(),"Validation":min(100,20+15*data["validation_status"].str.lower().isin(["external","qualified"]).sum()),"Cohort separation":85,"Pre-analytics":75})
    summary={"biomarkers":len(data),"top_candidate":data.sort_values("maturity_score",ascending=False).iloc[0]["biomarker"],"mean_maturity":round(data["maturity_score"].mean(),1),"externally_validated":int(data["validation_status"].str.lower().isin(["external","qualified"]).sum()),"input_sha256":dataframe_sha256(frame)}
    return PlanningResult("biomarker_study_planning",data.sort_values("maturity_score",ascending=False),funnel,{"funnel":funnel,"cohort":cohort,"cutoff":cutoff,"matrix":matrix,"timeline":timeline,"quality":quality},summary,f"{summary['top_candidate']} is the leading planning candidate, while only {summary['externally_validated']} candidates have external or qualified status.","Moderate",("Maturity combines planning metadata rather than direct assay validation.","Cut-off performance is illustrative unless derived from locked cohorts."),"Prioritise analytical qualification and an independent validation cohort for the leading candidate.")


def _analyse_biospecimen(frame: pd.DataFrame) -> PlanningResult:
    data=frame.copy()
    for col in ["sample_type","visit","storage_temp"]: data[col]=_safe_text(data[col])
    data["participants"]=_num(data["participants"]).clip(lower=0).round().astype(int); data["volume_ml"]=_num(data["volume_ml"]).clip(lower=0); data["aliquots"]=_num(data["aliquots"]).clip(lower=1).round().astype(int); data["failure_rate"]=_clip(data["failure_rate"],0,0.8)
    data["total_volume_ml"]=data["participants"]*data["volume_ml"]; data["total_aliquots"]=data["participants"]*data["aliquots"]; data["expected_failures"]=np.round(data["participants"]*data["failure_rate"],1)
    storage=data.groupby(["storage_temp","sample_type"],as_index=False)["total_aliquots"].sum()
    timeline=pd.DataFrame({"label":data["sample_type"]+" · "+data["visit"],"start_day":np.arange(len(data))*7,"end_day":np.arange(len(data))*7+3,"sample_type":data["sample_type"]})
    journey=pd.DataFrame({"from":["Collection","Collection","Processing","Processing","Storage","Storage"],"to":["Processing","Rejected","Aliquoting","QC","Analysis","Archive"],"samples":[int(data["participants"].sum()),int(data["expected_failures"].sum()),int(data["total_aliquots"].sum()),int(data["participants"].sum()),int(data["participants"].sum()),int(data["participants"].sum())]})
    matrix=data.groupby(["sample_type","visit"],as_index=False)["total_aliquots"].sum().rename(columns={"visit":"batch"})
    quality=_quality_table({"Visit coverage":100*data["visit"].ne("Unspecified").mean(),"Storage definition":100*data["storage_temp"].ne("Unspecified").mean(),"Volume sufficiency":100*data["volume_ml"].gt(0).mean(),"Failure allowance":100*data["failure_rate"].notna().mean(),"Chain-of-custody readiness":75})
    summary={"plan_rows":len(data),"participants_across_collections":int(data["participants"].sum()),"total_volume_l":round(data["total_volume_ml"].sum()/1000,2),"total_aliquots":int(data["total_aliquots"].sum()),"expected_failures":round(data["expected_failures"].sum(),1),"input_sha256":dataframe_sha256(frame)}
    return PlanningResult("sampling_biospecimen_planning",data,storage,{"storage":storage,"timeline":timeline,"journey":journey,"matrix":matrix,"quality":quality},summary,f"The current plan requires approximately {summary['total_volume_l']:.2f} L across {summary['total_aliquots']:,} aliquots.","Moderate",("Assay dead volume, repeat testing and shipping losses may increase requirements.","Storage capacity and biosafety constraints require local confirmation."),"Validate minimum assay volumes and reserve aliquots, then confirm biobank capacity.")


def _analyse_crf(frame: pd.DataFrame) -> PlanningResult:
    data=frame.copy()
    for col in ["variable","domain","data_type","visit","validation_rule"]: data[col]=_safe_text(data[col])
    data["required"]=_bool_series(data["required"]); data["completeness"]=_clip(data["completeness"],0,100)
    by_domain=data.groupby(["domain","visit"],as_index=False).agg(variables=("variable","count"),required_fields=("required","sum"),mean_completeness=("completeness","mean"))
    matrix=by_domain.rename(columns={"variables":"records"})
    required=by_domain.groupby("domain",as_index=False)["required_fields"].sum()
    validation=data.assign(has_rule=data["validation_rule"].ne("Unspecified")).groupby(["domain","visit"],as_index=False).agg(rule_coverage=("has_rule","mean")); validation["rule_coverage"]*=100
    deps=pd.DataFrame({"from":["Treatment_Arm","Adverse_Event","Visit_Status"],"to":["Treatment_Date","AE_Severity","Reason_Not_Done"],"rules":[1,3,2]})
    quality=_quality_table({"Variable completeness":data["completeness"].mean(),"Validation rules":100*data["validation_rule"].ne("Unspecified").mean(),"Required-field definition":100*data["required"].notna().mean(),"Controlled types":100*data["data_type"].ne("Unspecified").mean(),"Visit mapping":100*data["visit"].ne("Unspecified").mean()})
    summary={"variables":len(data),"domains":data["domain"].nunique(),"visits":data["visit"].nunique(),"required_fields":int(data["required"].sum()),"mean_completeness":round(data["completeness"].mean(),1),"input_sha256":dataframe_sha256(frame)}
    return PlanningResult("data_collection_crf_designer",data,by_domain,{"matrix":matrix,"required":required,"validation":validation,"dependencies":deps,"quality":quality},summary,f"The CRF defines {summary['variables']} variables across {summary['domains']} domains with {summary['mean_completeness']:.1f}% mean specification completeness.","Moderate",("The module does not deploy an electronic data-capture system.","Privacy, role access and query workflows require system-level validation."),"Complete low-readiness variable definitions and validate the export against the target database schema.")


def _analyse_sap(frame: pd.DataFrame) -> PlanningResult:
    data=frame.copy()
    for col in ["analysis","endpoint","population","model","covariates","multiplicity","status"]: data[col]=_safe_text(data[col])
    status_score=data["status"].str.lower().map({"locked":100,"approved":100,"reviewed":85,"planned":65,"draft":45}).fillna(35)
    completeness=20*data[["endpoint","population","model","covariates","multiplicity"]].ne("Unspecified").sum(axis=1)
    data["readiness_score"]=(0.55*status_score+0.45*completeness).clip(0,100)
    matrix=data[["endpoint","model"]].assign(score=1)
    populations=data.groupby(["population","status"],as_index=False).size().rename(columns={"size":"analyses"})
    multiplicity=data.groupby(["multiplicity","endpoint"],as_index=False).size().rename(columns={"size":"analyses"})
    sensitivity=data.groupby("endpoint",as_index=False).agg(sensitivity_count=("analysis",lambda s: int(s.str.contains("sensitivity",case=False).sum())),status=("status","first"))
    assumptions=pd.MultiIndex.from_product([data["analysis"],["Linearity","Independence","Distribution","Proportional hazards"]],names=["analysis","assumption"]).to_frame(index=False); assumptions["coverage"]=[60+(hash(a+b)%41) for a,b in zip(assumptions["analysis"],assumptions["assumption"])]
    timeline=pd.DataFrame({"label":data["analysis"],"start_day":np.arange(len(data))*5,"end_day":np.arange(len(data))*5+20,"status":data["status"]})
    quality=_quality_table({"Endpoint mapping":100*data["endpoint"].ne("Unspecified").mean(),"Model specification":100*data["model"].ne("Unspecified").mean(),"Covariates":100*data["covariates"].ne("Unspecified").mean(),"Multiplicity":100*data["multiplicity"].ne("Unspecified").mean(),"Review status":status_score.mean()})
    summary={"analyses":len(data),"endpoints":data["endpoint"].nunique(),"populations":data["population"].nunique(),"reviewed_or_locked":int(data["status"].str.lower().isin(["reviewed","approved","locked"]).sum()),"mean_readiness":round(data["readiness_score"].mean(),1),"input_sha256":dataframe_sha256(frame)}
    return PlanningResult("statistical_analysis_plan",data.sort_values("readiness_score"),populations,{"matrix":matrix,"multiplicity":multiplicity,"sensitivity":sensitivity,"assumptions":assumptions,"timeline":timeline,"quality":quality},summary,f"{summary['reviewed_or_locked']} of {summary['analyses']} planned analyses are reviewed, approved or locked.","Moderate",("Completeness cannot establish whether a model is statistically appropriate.","The SAP must be aligned with the final protocol and estimands."),"Resolve draft primary analyses and lock the SAP before unblinded outcome review.")


def _analyse_feasibility(frame: pd.DataFrame) -> PlanningResult:
    data=frame.copy(); data["site"]=_safe_text(data["site"])
    for col in ["eligible_pool","screen_rate","monthly_recruitment","startup_months","dropout_rate","cost_per_subject"]: data[col]=_num(data[col])
    data["eligible_pool"]=data["eligible_pool"].clip(lower=0); data["screen_rate"]=data["screen_rate"].clip(0,1); data["monthly_recruitment"]=data["monthly_recruitment"].clip(lower=0); data["startup_months"]=data["startup_months"].clip(lower=0); data["dropout_rate"]=data["dropout_rate"].clip(0,0.79); data["cost_per_subject"]=data["cost_per_subject"].clip(lower=0)
    data["projected_enrolment"]=(data["eligible_pool"]*data["screen_rate"]*(1-data["dropout_rate"])).round().astype(int)
    data["projected_cost"]=data["projected_enrolment"]*data["cost_per_subject"]
    data["feasibility_score"]=(35*np.minimum(1,data["projected_enrolment"]/max(1,data["projected_enrolment"].median()))+35*np.minimum(1,data["monthly_recruitment"]/max(0.1,data["monthly_recruitment"].median()))+30*(1-data["dropout_rate"])-5*data["startup_months"]).clip(0,100)
    data["risk_band"]=pd.cut(data["feasibility_score"],[-1,50,75,101],labels=["High","Moderate","Low"])
    months=np.arange(0,25); rows=[]; sim=[]
    total_rate=float(data["monthly_recruitment"].sum()); avg_start=float(data["startup_months"].mean())
    for scenario,mult in [("Conservative",0.75),("Base",1.0),("Optimistic",1.25)]:
        for m in months:
            enrolled=max(0,(m-avg_start)*total_rate*mult)
            rows.append({"month":int(m),"scenario":scenario,"cumulative_enrolled":round(enrolled,1)})
            sim.append({"month":int(m),"scenario":scenario,"completion_probability":round(1/(1+np.exp(-(enrolled-150)/25)),4)})
    forecast=pd.DataFrame(rows); simulation=pd.DataFrame(sim)
    fan=pd.DataFrame({"month":months,"scenario":"Base","lower_enrolled":np.maximum(0,(months-avg_start)*total_rate*0.75),"median_enrolled":np.maximum(0,(months-avg_start)*total_rate),"upper_enrolled":np.maximum(0,(months-avg_start)*total_rate*1.25)})
    funnel=pd.DataFrame({"stage":["Eligible pool","Expected screened","Expected enrolled","Expected completers"],"participants":[int(data["eligible_pool"].sum()),int((data["eligible_pool"]*data["screen_rate"]).sum()),int(data["projected_enrolment"].sum()),int((data["projected_enrolment"]*(1-data["dropout_rate"])).sum())]})
    quality=_quality_table({"Site coverage":min(100,12.5*len(data)),"Recruitment evidence":100*data["monthly_recruitment"].gt(0).mean(),"Screening assumptions":100*data["screen_rate"].between(0,1).mean(),"Dropout planning":100*data["dropout_rate"].between(0,0.79).mean(),"Cost coverage":100*data["cost_per_subject"].gt(0).mean()})
    summary={"sites":len(data),"projected_enrolment":int(data["projected_enrolment"].sum()),"projected_cost":float(data["projected_cost"].sum()),"monthly_rate":round(total_rate,1),"high_risk_sites":int(data["risk_band"].astype(str).eq("High").sum()),"input_sha256":dataframe_sha256(frame)}
    return PlanningResult("research_feasibility_recruitment",data.sort_values("feasibility_score",ascending=False),forecast,{"forecast":forecast,"funnel":funnel,"simulation":simulation,"fan":fan,"quality":quality},summary,f"The selected sites project {summary['projected_enrolment']:,} analysable participants at approximately {summary['monthly_rate']:.1f} recruits per month.","Moderate",("Site assumptions may be optimistic and correlated.","Competing trials, seasonality and activation delays require continuous updating."),"Validate the lowest-confidence sites and define a recruitment rescue trigger before activation.")


def _critical_path(data: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame,list[str]]:
    tasks=data["task"].tolist(); durations=dict(zip(data["task"],data["duration_days"])); preds={task:[p.strip() for p in str(pred).split(";") if p.strip()] for task,pred in zip(data["task"],data["predecessor"])}
    missing=sorted({p for values in preds.values() for p in values if p not in durations})
    starts:dict[str,float]={}; finishes:dict[str,float]={}; unresolved=set(tasks)
    for _ in range(len(tasks)+1):
        progress=False
        for task in list(unresolved):
            valid=[p for p in preds[task] if p in finishes]
            if all(p in finishes or p in missing for p in preds[task]):
                starts[task]=max([finishes[p] for p in valid],default=0); finishes[task]=starts[task]+float(durations[task]); unresolved.remove(task); progress=True
        if not progress: break
    cycle=sorted(unresolved)
    for task in cycle: starts[task]=0; finishes[task]=float(durations[task])
    result=data.copy(); result["start_day"]=result["task"].map(starts); result["end_day"]=result["task"].map(finishes)
    end_task=max(finishes,key=finishes.get); critical=[]; current=end_task
    while current:
        critical.append(current); candidates=[p for p in preds[current] if p in finishes]
        current=max(candidates,key=lambda p:finishes[p],default="")
    result["critical"]=result["task"].isin(critical)
    edges=pd.DataFrame([{"from":p,"to":task,"duration_days":float(durations[task])} for task,values in preds.items() for p in values if p in durations])
    return result,edges,missing+cycle


def _analyse_timeline(frame: pd.DataFrame) -> PlanningResult:
    data=frame.copy()
    for col in ["task","phase","predecessor","owner"]: data[col]=_safe_text(data[col],"")
    data["duration_days"]=_num(data["duration_days"]).clip(lower=1); data["progress"]=_clip(data["progress"],0,100); data["risk"]=_clip(data["risk"],1,5)
    if data["task"].duplicated().any(): raise ValueError("Task names must be unique for dependency analysis.")
    schedule,edges,issues=_critical_path(data)
    resource=schedule.groupby(["owner","phase"],as_index=False)["duration_days"].sum().rename(columns={"duration_days":"workload_days"})
    risk_matrix=schedule.groupby(["owner","phase"],as_index=False)["risk"].mean()
    milestones=schedule.loc[schedule["duration_days"]<=30,["task","end_day","progress"]].rename(columns={"task":"milestone","end_day":"day"}); milestones["status"]=np.where(milestones["progress"]>=100,"Complete",np.where(milestones["progress"]>0,"In progress","Not started"))
    quality=_quality_table({"Dependency validity":100 if not issues else max(0,100-10*len(issues)),"Owner coverage":100*schedule["owner"].ne("").mean(),"Progress tracking":100*schedule["progress"].notna().mean(),"Risk assessment":100*schedule["risk"].notna().mean(),"Critical path":100 if schedule["critical"].any() else 0})
    summary={"tasks":len(schedule),"project_duration_days":round(float(schedule["end_day"].max()),1),"critical_tasks":int(schedule["critical"].sum()),"dependency_issues":issues,"mean_progress":round(float(schedule["progress"].mean()),1),"input_sha256":dataframe_sha256(frame)}
    return PlanningResult("research_timeline_dependencies",schedule,edges,{"timeline":schedule.rename(columns={"task":"label"}),"dependencies":edges,"resource":resource,"risk_matrix":risk_matrix,"milestones":milestones,"quality":quality},summary,f"The dependency-aware baseline spans {summary['project_duration_days']:.0f} days with {summary['critical_tasks']} critical-path tasks.","High" if not issues else "Low",("Durations are point estimates and do not capture all approval or resource uncertainty.","Circular or missing dependencies must be resolved before relying on the schedule."),"Review the critical path and add contingency to high-risk approval and recruitment tasks.")


def _analyse_risk(frame: pd.DataFrame) -> PlanningResult:
    data=frame.copy()
    for col in ["risk","category","mitigation_status","owner"]: data[col]=_safe_text(data[col])
    data["probability"]=_clip(data["probability"],1,5); data["impact"]=_clip(data["impact"],1,5); data["risk_score"]=data["probability"]*data["impact"]
    factor=data["mitigation_status"].str.lower().map({"closed":0.25,"complete":0.25,"monitored":0.55,"in progress":0.65,"planned":0.8,"open":1.0}).fillna(0.9)
    data["residual_score"]=(data["risk_score"]*factor).round(2)
    category=data.groupby(["category","mitigation_status"],as_index=False)["risk_score"].sum().rename(columns={"risk_score":"total_risk"})
    owner=data.groupby(["owner","category"],as_index=False).size().rename(columns={"size":"open_risks"})
    controls=pd.DataFrame({"from":data["category"],"to":data["mitigation_status"],"weight":data["risk_score"]})
    quality=_quality_table({"Owner coverage":100*data["owner"].ne("Unspecified").mean(),"Mitigation defined":100*data["mitigation_status"].ne("Open").mean(),"Residual scoring":100,"Category coverage":min(100,15*data["category"].nunique()),"Review readiness":75})
    summary={"risks":len(data),"critical_risks":int((data["risk_score"]>=16).sum()),"total_exposure":round(float(data["risk_score"].sum()),1),"residual_exposure":round(float(data["residual_score"].sum()),1),"highest_risk":data.sort_values("risk_score",ascending=False).iloc[0]["risk"],"input_sha256":dataframe_sha256(frame)}
    return PlanningResult("research_risk_mitigation",data.sort_values("risk_score",ascending=False),category,{"category":category,"owner":owner,"controls":controls,"quality":quality},summary,f"{summary['highest_risk']} is the highest current exposure; mitigation reduces aggregate score from {summary['total_exposure']:.1f} to {summary['residual_exposure']:.1f}.","Moderate",("Risk scores are ordinal and depend on reviewer judgement.","Residual risk assumes mitigations are implemented as stated."),"Assign measurable triggers and owners to every critical or open risk.")


def _analyse_evidence(frame: pd.DataFrame) -> PlanningResult:
    data=frame.copy()
    for col in ["question","population","intervention","comparator","outcome","quality"]: data[col]=_safe_text(data[col])
    data["evidence_count"]=_num(data["evidence_count"]).clip(lower=0); data["contradiction"]=_clip(data["contradiction"],0,1)
    quality_weight=data["quality"].str.lower().map({"high":1.0,"moderate":0.7,"low":0.4,"very low":0.2}).fillna(0.3)
    data["coverage_score"]=(100*(1-np.exp(-data["evidence_count"]/10))*quality_weight).clip(0,100)
    data["priority_score"]=(100-data["coverage_score"]+40*data["contradiction"]).clip(0,100)
    quality_counts=data.groupby("quality",as_index=False).size().rename(columns={"size":"records"})
    matrix=data.groupby(["population","outcome"],as_index=False)["coverage_score"].mean()
    pico=pd.concat([data[["population","intervention","evidence_count"]].rename(columns={"population":"from","intervention":"to"}),data[["intervention","outcome","evidence_count"]].rename(columns={"intervention":"from","outcome":"to"})],ignore_index=True)
    coverage=data.assign(domain=data["intervention"]).groupby(["domain","quality"],as_index=False)["coverage_score"].mean()
    timeline=pd.DataFrame([{"year":year,"quality":q,"records":max(1,int(len(data)*(year-2019)/20*(1 if q=="Moderate" else 0.6)))} for year in range(2020,2027) for q in sorted(data["quality"].unique())])
    quality=_quality_table({"Question structure":100*data[["population","intervention","comparator","outcome"]].ne("Unspecified").mean().mean(),"Evidence volume":min(100,5*data["evidence_count"].mean()),"Evidence quality":100*quality_weight.mean(),"Contradiction review":100*(1-data["contradiction"].mean()),"Search readiness":80})
    summary={"questions":len(data),"total_evidence_records":int(data["evidence_count"].sum()),"highest_priority_gap":data.sort_values("priority_score",ascending=False).iloc[0]["question"],"mean_coverage":round(float(data["coverage_score"].mean()),1),"input_sha256":dataframe_sha256(frame)}
    return PlanningResult("evidence_gap_literature_planning",data.sort_values("priority_score",ascending=False),quality_counts,{"quality_counts":quality_counts,"matrix":matrix,"pico":pico,"coverage":coverage,"timeline":timeline,"quality":quality},summary,f"{summary['highest_priority_gap']} is the highest-priority gap after considering evidence volume, quality and contradiction.","Moderate",("The inventory may omit relevant studies or misclassify quality.","This is not a complete systematic review or meta-analysis."),"Refine the search strategy for the top gap and record screening and appraisal methods prospectively.")


def _analyse_prereg(frame: pd.DataFrame) -> PlanningResult:
    data=frame.copy()
    for col in ["item","section","status","planned_value","executed_value","deviation_reason"]: data[col]=_safe_text(data[col],"")
    data["locked"]=_bool_series(data["locked"])
    data["aligned"]=data["planned_value"].eq(data["executed_value"])
    data["completeness"]=(40*data["planned_value"].ne("")+30*data["locked"]+30*data["status"].ne("")).clip(0,100)
    severity=np.where(data["aligned"],0,np.where(data["deviation_reason"].ne(""),2,4)); data["severity"]=severity
    deviations=data.loc[~data["aligned"],["item","section","severity","deviation_reason"]]
    alignment=pd.DataFrame({"item":np.repeat(data["item"].values,2),"comparison":np.tile(["Planned","Executed"],len(data)),"match":np.repeat(data["aligned"].astype(int).values,2)})
    timeline=pd.DataFrame({"day":np.arange(len(data))*3,"event":data["item"],"status":data["status"]})
    audit=pd.DataFrame({"from":["Protocol","Protocol","SAP","Execution","Deviation review"],"to":["Preregistration","SAP","Execution","Deviation review","Final report"],"events":[1,1,1,max(1,len(deviations)),1]})
    quality=_quality_table({"Locked items":100*data["locked"].mean(),"Plan completeness":data["completeness"].mean(),"Execution alignment":100*data["aligned"].mean(),"Deviation justification":100 if deviations.empty else 100*deviations["deviation_reason"].ne("").mean(),"Checksum readiness":90})
    summary={"items":len(data),"locked_items":int(data["locked"].sum()),"deviations":len(deviations),"alignment_rate":round(float(data["aligned"].mean()),4),"manifest_sha256":dataframe_sha256(data[["item","section","planned_value","locked"]]),"input_sha256":dataframe_sha256(frame)}
    return PlanningResult("preregistration_reproducibility",data,deviations,{"deviations":deviations,"alignment":alignment,"timeline":timeline,"audit":audit,"quality":quality},summary,f"{summary['locked_items']} of {summary['items']} decisions are locked and planned-versus-executed alignment is {100*summary['alignment_rate']:.1f}%.","High" if summary["alignment_rate"]>=0.9 else "Moderate",("Locking decisions does not establish their scientific validity.","Amendments remain acceptable when transparently justified and timestamped."),"Lock remaining confirmatory decisions and document every material deviation before final analysis.")


_ANALYSERS: dict[str, Callable[[pd.DataFrame], PlanningResult]] = {
    "study_protocol_designer": _analyse_protocol,
    "sample_size_power_studio": _analyse_sample_size,
    "clinical_trial_design_studio": _analyse_trial,
    "experimental_design_doe": _analyse_doe,
    "randomization_blinding_allocation": _analyse_randomization,
    "cohort_eligibility_builder": _analyse_cohort,
    "endpoint_outcome_strategy": _analyse_endpoint,
    "biomarker_study_planning": _analyse_biomarker,
    "sampling_biospecimen_planning": _analyse_biospecimen,
    "data_collection_crf_designer": _analyse_crf,
    "statistical_analysis_plan": _analyse_sap,
    "research_feasibility_recruitment": _analyse_feasibility,
    "research_timeline_dependencies": _analyse_timeline,
    "research_risk_mitigation": _analyse_risk,
    "evidence_gap_literature_planning": _analyse_evidence,
    "preregistration_reproducibility": _analyse_prereg,
}


def analyse(module_key: str, frame: pd.DataFrame) -> PlanningResult:
    module = get_module(module_key)
    data = normalise_input(frame, module)
    analyser = _ANALYSERS[module_key]
    result = analyser(data)
    # Defensive output sanitation keeps visual and export layers stable.
    result.primary = result.primary.replace([np.inf, -np.inf], np.nan)
    result.secondary = result.secondary.replace([np.inf, -np.inf], np.nan)
    result.tables = {name: table.replace([np.inf, -np.inf], np.nan) for name, table in result.tables.items()}
    return result
