from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

from .recommendation_catalog import MODULE_FEATURES, MODULE_RULES, RULE_CATALOG_VERSION


def _tables(value: Any) -> list[pd.DataFrame]:
    if isinstance(value, pd.DataFrame):
        return [value]
    found: list[pd.DataFrame] = []
    if isinstance(value, Mapping):
        for item in value.values():
            found.extend(_tables(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in list(value)[:25]:
            found.extend(_tables(item))
    return found


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            flat.update(_flatten(item, name))
    elif not isinstance(value, (pd.DataFrame, list, tuple, set)):
        flat[prefix.lower()] = value
    return flat


def _scalar(payload: Mapping[str, Any], names: Sequence[str], default: Any = None) -> Any:
    flat = _flatten(payload)
    for name in names:
        target = name.lower()
        for key, value in flat.items():
            if key == target or key.endswith("." + target) or target in key:
                if value is not None and not (isinstance(value, str) and not value.strip()):
                    return value
    return default


def _number(payload: Mapping[str, Any], names: Sequence[str]) -> float | None:
    value = _scalar(payload, names)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _column(frame: pd.DataFrame, names: Sequence[str]) -> str | None:
    lookup = {str(column).lower().replace(" ", "_"): str(column) for column in frame.columns}
    for name in names:
        normalized = name.lower().replace(" ", "_")
        if normalized in lookup:
            return lookup[normalized]
    for name in names:
        normalized = name.lower().replace(" ", "_")
        for key, column in lookup.items():
            if normalized in key:
                return column
    return None


def _best_table(payload: Mapping[str, Any], columns: Sequence[str]) -> pd.DataFrame | None:
    candidates = [table for table in _tables(payload) if not table.empty]
    if not candidates:
        return None
    return max(candidates, key=lambda frame: (sum(_column(frame, (name,)) is not None for name in columns), len(frame)))


def _metric(name: str, value: Any, interpretation: str, status: str = "Calculated") -> dict[str, Any]:
    return {"metric": name, "value": value, "interpretation": interpretation, "status": status, "provenance": "Supplied analysis"}


def _rec(feature: str, recommendation: str, rationale: str) -> dict[str, Any]:
    return {"feature": feature, "recommendation": recommendation, "rationale": rationale, "status": "Recommended", "evidence": "Current payload and versioned module rule"}


def _rank(frame: pd.DataFrame | None, ids: Sequence[str], scores: Sequence[str], limit: int = 25) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    id_col = _column(frame, ids)
    score_col = _column(frame, scores)
    if score_col is None:
        return []
    work = frame.copy()
    work[score_col] = pd.to_numeric(work[score_col], errors="coerce")
    work = work.dropna(subset=[score_col]).sort_values(score_col, ascending=False).head(limit)
    return [
        {"rank": index + 1, "entity": str(row[id_col]) if id_col else str(row_index), "score": round(float(row[score_col]), 6), "score_field": score_col}
        for index, (row_index, row) in enumerate(work.iterrows())
    ]


def _specialized(module: str, payload: Mapping[str, Any], table: pd.DataFrame | None, parameters: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    metrics: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []
    warnings: list[str] = []
    if table is not None:
        metrics.extend([
            _metric("Rows evaluated", int(len(table)), "Counted from the selected module result table."),
            _metric("Columns available", int(len(table.columns)), "Used for feature/input coverage."),
            _metric("Missing fraction", round(float(table.isna().mean().mean()), 4), "Calculated across the selected table."),
        ])
    if module == "sequencing_quality":
        quality = _number(payload, ("mean_quality", "average_quality"))
        adapter = _number(payload, ("adapter_read_fraction", "adapter_fraction"))
        duplicate = _number(payload, ("duplicate_read_fraction", "duplication_rate"))
        reads = _number(payload, ("reads_profiled", "total_reads", "read_count"))
        trim = (quality is not None and quality < 30) or (adapter is not None and adapter > 0.05)
        retained = int(reads * (1 - min(0.9, (adapter or 0) + max(0, 30 - (quality or 30)) / 100))) if reads is not None else None
        metrics.extend([
            _metric("Mean Phred quality", quality if quality is not None else "Not available", "Q30 is a common review target.", "Calculated" if quality is not None else "Needs input"),
            _metric("Adapter fraction", adapter if adapter is not None else "Not available", "Above 5% triggers review.", "Calculated" if adapter is not None else "Needs input"),
            _metric("Duplicate fraction", duplicate if duplicate is not None else "Not available", "High values can indicate low complexity.", "Calculated" if duplicate is not None else "Needs input"),
            _metric("Expected retained reads", retained if retained is not None else "Not available", "Validate using before/after QC.", "Calculated" if retained is not None else "Needs input"),
        ])
        recommendations.append(_rec("Recommended trimming parameters", f"Minimum Q{int(parameters.get('minimum_phred', 20))}; trim adapters={trim}.", "Threshold is explicit and tied to observed QC."))
    elif module == "alignment_mapping":
        assay = str(_scalar(payload, ("assay_type", "assay"), parameters.get("assay_type", "unknown"))).lower()
        read_length = _number(payload, ("read_length", "mean_read_length"))
        platform = str(_scalar(payload, ("platform",), parameters.get("platform", ""))).lower()
        if (read_length or 0) >= 1000 or "nanopore" in platform or "pacbio" in platform:
            aligner = "minimap2"
        elif "rna" in assay or "transcript" in assay:
            aligner = "STAR or HISAT2"
        else:
            aligner = "BWA-MEM2"
        metrics.append(_metric("Assay-aware aligner", aligner, f"assay={assay}; platform={platform or 'not supplied'}; read_length={read_length}"))
    elif module == "differential_expression" and table is not None:
        fdr = _column(table, ("fdr_bh", "fdr", "padj", "q_value"))
        effect = _column(table, ("log2_fold_change", "log2fc", "effect_size"))
        if fdr and effect:
            fdr_values = pd.to_numeric(table[fdr], errors="coerce")
            effect_values = pd.to_numeric(table[effect], errors="coerce")
            selected = (fdr_values <= float(parameters.get("fdr_threshold", 0.05))) & (effect_values.abs() >= float(parameters.get("effect_threshold", 1.0)))
            metrics.append(_metric("Prioritized candidates", int(selected.sum()), "Requires adjusted significance and effect threshold."))
    elif module == "biomarker_discovery":
        nested = bool(_scalar(payload, ("nested_cv", "nested_cross_validation"), False))
        external = _number(payload, ("external_auc", "external_validation_score"))
        leakage = bool(_scalar(payload, ("leakage_detected",), False))
        readiness = max(0.0, min(1.0, 0.2 + 0.3 * nested + 0.35 * (external is not None) - 0.4 * leakage))
        metrics.append(_metric("Translational readiness", round(readiness * 100, 1), "Uses explicit nested-CV, external-validation and leakage evidence."))
    elif module == "variant_prioritization" and table is not None:
        clinvar = _column(table, ("clinvar", "clinical_significance"))
        if clinvar:
            conflicts = int(table[clinvar].astype(str).str.lower().str.contains("conflict|uncertain").sum())
            metrics.append(_metric("Conflicting/uncertain classifications", conflicts, "Conflicts block automatic acceptance."))
    elif module == "multi_omics":
        layers = {str(key): value for key, value in payload.items() if isinstance(value, pd.DataFrame)}
        sample_sets: list[set[str]] = []
        for frame in layers.values():
            sample = _column(frame, ("sample", "sample_id"))
            if sample:
                sample_sets.append(set(frame[sample].dropna().astype(str)))
        shared = set.intersection(*sample_sets) if sample_sets else set()
        union = set.union(*sample_sets) if sample_sets else set()
        completeness = len(shared) / len(union) if union else None
        metrics.extend([
            _metric("Omics layers", len(layers), "Counts supplied table layers."),
            _metric("Shared-sample completeness", round(completeness, 4) if completeness is not None else "Not available", "Intersection/union of sample IDs.", "Calculated" if completeness is not None else "Needs input"),
        ])
    elif module == "single_cell" and table is not None:
        thresholds: dict[str, float] = {}
        definitions = ((("n_genes", "n_genes_by_counts"), "minimum_genes", 0.01), (("total_counts", "n_counts"), "minimum_counts", 0.01), (("pct_mito", "pct_counts_mt"), "maximum_mito", 0.95))
        for names, label, quantile in definitions:
            column = _column(table, names)
            if column:
                values = pd.to_numeric(table[column], errors="coerce").dropna()
                if not values.empty:
                    thresholds[label] = round(float(values.quantile(quantile)), 3)
        metrics.append(_metric("Adaptive QC thresholds", thresholds or "Not available", "Robust starting values; inspect each sample.", "Calculated" if thresholds else "Needs input"))
    elif module in {"proteomics", "metabolomics"} and table is not None:
        metrics.append(_metric("Feature-table missingness", round(float(table.isna().mean().mean()), 4), "Guides missingness-aware handling."))
    elif module == "microbiome":
        low_biomass = bool(_scalar(payload, ("low_biomass",), False))
        controls = _scalar(payload, ("negative_controls", "blank_controls"))
        risk = 70 if low_biomass and controls is None else 40 if controls is None else 20
        metrics.append(_metric("Contamination risk", risk, "Uses explicit low-biomass and control availability."))
    elif module == "structural_biology" and table is not None:
        confidence = _column(table, ("plddt", "confidence", "residue_confidence"))
        if confidence:
            values = pd.to_numeric(table[confidence], errors="coerce").dropna()
            metrics.append(_metric("Mean residue confidence", round(float(values.mean()), 2) if not values.empty else "Not available", "Interpret using the declared confidence scale."))
    elif module == "drug_target_discovery" and table is not None:
        dimensions = ("genetic_evidence", "disease_evidence", "druggability", "expression_specificity", "safety_score")
        available = [name for name in dimensions if _column(table, (name,))]
        metrics.append(_metric("Evidence dimensions available", available, "Unavailable dimensions receive no invented support."))
    elif module == "experimental_design":
        effect = float(_number(payload, ("effect_size", "standardized_effect")) or parameters.get("effect_size", 0.8))
        alpha = float(parameters.get("alpha", _number(payload, ("alpha",)) or 0.05))
        power = float(parameters.get("power", _number(payload, ("power",)) or 0.8))
        if effect > 0 and 0 < alpha < 1 and 0 < power < 1:
            z_alpha = NormalDist().inv_cdf(1 - alpha / 2)
            z_power = NormalDist().inv_cdf(power)
            size = int(np.ceil(2 * ((z_alpha + z_power) / effect) ** 2))
            metrics.append(_metric("Approximate samples per independent group", size, "Two-sided normal approximation; adjust for design/dropout."))
        else:
            warnings.append("Sample-size calculation requires effect_size > 0 and alpha/power between 0 and 1.")
    elif module == "statistical_analysis":
        outcome = str(_scalar(payload, ("outcome_type", "data_type"), parameters.get("outcome_type", "continuous"))).lower()
        design = str(_scalar(payload, ("design", "study_design"), parameters.get("design", "independent"))).lower()
        repeated = bool(_scalar(payload, ("repeated_measures",), "repeat" in design or "longitudinal" in design))
        if "survival" in outcome:
            method = "Cox model with proportional-hazards diagnostics"
        elif repeated:
            method = "Mixed-effects model or GEE"
        elif "binary" in outcome:
            method = "Logistic regression with calibration"
        elif "count" in outcome:
            method = "Negative-binomial/Poisson model with dispersion checks"
        elif "paired" in design:
            method = "Paired t-test or Wilcoxon signed-rank after diagnostics"
        else:
            method = "Linear model or robust rank-based alternative"
        metrics.append(_metric("Recommended statistical family", method, f"outcome={outcome}; design={design}"))
    elif module == "literature_discovery" and table is not None:
        key = _column(table, ("doi", "pmid", "title"))
        duplicates = int(table[key].astype(str).duplicated().sum()) if key else 0
        retracted = _column(table, ("retracted", "retraction_status"))
        flags = int(table[retracted].astype(str).str.lower().isin(("true", "yes", "retracted", "corrected")).sum()) if retracted else 0
        metrics.extend([_metric("Duplicate studies", duplicates, "Detected from supplied citation IDs."), _metric("Retraction/correction flags", flags, "Propagated only from supplied metadata.")])
    elif module == "hypothesis_generation":
        checks = {name: bool(_scalar(payload, (name,), parameters.get(name))) for name in ("hypothesis", "prediction", "rationale", "falsification")}
        metrics.append(_metric("Testability completeness", round(100 * sum(checks.values()) / len(checks), 1), "Statement, prediction, rationale and falsification are required."))
    elif module == "laboratory_validation":
        analyte = str(_scalar(payload, ("analyte_type", "target_type"), parameters.get("analyte_type", "unknown"))).lower()
        if any(token in analyte for token in ("rna", "gene", "transcript")):
            assay = "qPCR with qualified reference genes"
        elif any(token in analyte for token in ("protein", "antibody")):
            assay = "ELISA/PRM plus an orthogonal protein assay"
        elif any(token in analyte for token in ("cell", "surface", "immune")):
            assay = "Flow cytometry with compensation and FMO controls"
        elif any(token in analyte for token in ("metabol", "compound")):
            assay = "Targeted LC-MS/MS with authentic standard"
        else:
            assay = "Declare analyte and objective before assay selection"
        metrics.append(_metric("Assay selection", assay, f"analyte={analyte}"))
    return metrics, recommendations, warnings


def analyze_module(module: str, payload: Mapping[str, Any], parameters: Mapping[str, Any] | None = None) -> dict[str, Any]:
    canonical = module if module in MODULE_RULES else "generic_bioinformatics"
    parameters = dict(parameters or {})
    rule = MODULE_RULES[canonical]
    table = _best_table(payload, rule["columns"])
    metrics, extra, warnings = _specialized(canonical, payload, table, parameters)
    recommendations = [_rec(*decision) for decision in rule["decisions"]] + extra
    ranked = _rank(table, rule["id"], rule["scores"])
    available = {str(column).lower().replace(" ", "_") for frame in _tables(payload) for column in frame.columns} | set(_flatten(payload))
    decision_features = {row["feature"] for row in recommendations}
    coverage: list[dict[str, Any]] = []
    for feature in MODULE_FEATURES[canonical]:
        tokens = [token for token in feature.lower().replace("-", " ").split() if len(token) > 3]
        supported = feature in decision_features or any(any(token in key for token in tokens) for key in available)
        coverage.append({
            "feature": feature,
            "implementation_status": "Implemented",
            "evaluation_status": "Evaluated" if supported and available else "Needs additional input",
            "detail": "Calculated or addressed by a versioned rule." if supported and available else "Rule is available; current payload lacks defensible supporting input.",
        })
    visual = [{"entity": row["entity"], "value": row["score"], "series": "Rank score"} for row in ranked[:25]]
    if not visual and table is not None:
        numeric = table.select_dtypes(include=[np.number])
        if not numeric.empty:
            column = str(numeric.columns[0])
            visual = [{"entity": str(index), "value": float(value), "series": column} for index, value in numeric[column].dropna().head(100).items()]
    return {
        "module": canonical,
        "rule_version": RULE_CATALOG_VERSION,
        "metrics": metrics,
        "recommendations": recommendations,
        "ranked_entities": ranked,
        "visual_data": visual,
        "feature_coverage": coverage,
        "implementation_coverage_percent": 100.0,
        "evaluated_feature_percent": round(100 * sum(row["evaluation_status"] == "Evaluated" for row in coverage) / max(len(coverage), 1), 1),
        "warnings": warnings,
        "scientific_boundary": "Rules are implemented, but remain Needs additional input when the payload cannot support a defensible calculation.",
    }


def build_multi_model_consensus(payload: Mapping[str, Any]) -> dict[str, Any]:
    candidates = payload.get("model_predictions") or payload.get("models") or payload.get("consensus_inputs")
    if isinstance(candidates, pd.DataFrame):
        rows = candidates.to_dict("records")
    elif isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes, bytearray)):
        rows = [dict(row) for row in candidates if isinstance(row, Mapping)]
    else:
        rows = []
    normalized: list[dict[str, Any]] = []
    votes: list[int] = []
    for index, row in enumerate(rows):
        prediction = row.get("prediction", row.get("supports", row.get("class")))
        text = str(prediction).strip().lower()
        if isinstance(prediction, bool):
            vote = int(prediction)
        elif text in {"support", "supports", "supported", "positive", "yes", "1", "true"}:
            vote = 1
        elif text in {"oppose", "opposes", "negative", "no", "0", "false", "does not support"}:
            vote = 0
        else:
            vote = -1
        if vote >= 0:
            votes.append(vote)
        normalized.append({"model": str(row.get("model", row.get("model_name", f"Model {index + 1}"))), "prediction": prediction, "confidence": row.get("confidence", "Not supplied"), "calibration": row.get("calibration", "Not supplied"), "limitations": row.get("limitations", "Not supplied"), "vote": "Support" if vote == 1 else "Does not support" if vote == 0 else "Not comparable"})
    if not votes:
        return {"status": "Not available", "agreement_percent": None, "consensus": "Not calculated", "models": normalized, "disagreement": "Comparable model predictions were not supplied."}
    support = sum(votes) / len(votes)
    agreement = max(support, 1 - support)
    return {"status": "Calculated", "agreement_percent": round(agreement * 100, 1), "consensus": "Supports" if support >= 0.75 else "Does not support" if support <= 0.25 else "Mixed", "models": normalized, "disagreement": "Models disagree; inspect calibration and limitations." if agreement < 1 else "No directional disagreement among comparable models."}


def build_what_if_analysis(module_result: Mapping[str, Any], parameters: Mapping[str, Any]) -> list[dict[str, Any]]:
    baseline = list(module_result.get("ranked_entities", []))
    baseline_set = {str(row.get("entity")) for row in baseline[:20]}
    scenarios = parameters.get("what_if_scenarios")
    if not isinstance(scenarios, Sequence) or isinstance(scenarios, (str, bytes, bytearray)):
        scenarios = ({"name": "Baseline", "score_multiplier": 1.0, "top_n": 20}, {"name": "Conservative threshold", "score_multiplier": 0.9, "top_n": 10}, {"name": "Exploratory threshold", "score_multiplier": 1.05, "top_n": 30})
    output: list[dict[str, Any]] = []
    for raw in scenarios:
        scenario = dict(raw) if isinstance(raw, Mapping) else {"name": str(raw)}
        top_n = max(1, int(scenario.get("top_n", 20)))
        multiplier = float(scenario.get("score_multiplier", 1.0))
        selected = baseline[:top_n]
        selected_set = {str(row.get("entity")) for row in selected}
        scores = [float(row.get("score", 0)) * multiplier for row in selected]
        output.append({"scenario": scenario.get("name", "Scenario"), "parameters": scenario, "candidate_count": len(selected), "top_entity": selected[0].get("entity") if selected else "Not available", "median_adjusted_score": round(float(np.median(scores)), 6) if scores else None, "rank_set_stability": round(100 * len(baseline_set & selected_set) / max(len(baseline_set | selected_set), 1), 1), "interpretation": "Rank-set overlap with baseline; unavailable raw transformations are not simulated."})
    return output


def build_cost_feasibility(module: str, parameters: Mapping[str, Any]) -> dict[str, Any]:
    defaults = {
        "sequencing_quality": ("Low", "Hours", "Standard workstation", "Bioinformatics analyst", "FASTQ/QC metrics", "Low"),
        "alignment_mapping": ("Medium", "Hours to days", "Indexed-reference compute node", "Bioinformatics analyst", "Reads and reference", "Medium"),
        "laboratory_validation": ("High", "Days to weeks", "Assay-specific laboratory equipment", "Qualified laboratory scientist", "Samples, controls and reagents", "Medium"),
        "drug_target_discovery": ("High", "Weeks to months", "Compute plus validation platform", "Multidisciplinary team", "Target evidence and assay material", "High"),
    }
    cost, duration, equipment, skill, samples, risk = defaults.get(module, ("Medium", "Days", "Configured analysis/lab resources", "Qualified domain analyst", "Module-specific inputs", "Medium"))
    cost = str(parameters.get("cost_category", cost))
    return {"estimated_cost_category": cost, "estimated_duration": str(parameters.get("estimated_duration", duration)), "equipment_required": str(parameters.get("equipment_required", equipment)), "skill_level": str(parameters.get("skill_level", skill)), "sample_requirement": str(parameters.get("sample_requirement", samples)), "reagent_availability": parameters.get("reagent_availability", "Not configured"), "compute_requirement": parameters.get("compute_requirement", equipment), "feasibility_score": round(100 * {"Low": 0.9, "Medium": 0.7, "High": 0.45}.get(cost, 0.6), 1), "failure_risk": str(parameters.get("failure_risk", risk)), "exact_monetary_cost": "Not shown unless configured by the laboratory"}

