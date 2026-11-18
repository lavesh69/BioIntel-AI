from __future__ import annotations

import re
from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy import stats

from .analysis_common import bh_fdr, numeric, require_columns, standardized_effect
from .models import PlatformValidationError

PMID_RE = re.compile(r"^[1-9][0-9]{0,8}$")
DOI_RE = re.compile(r"^10\.[0-9]{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)


def drug_target_discovery(
    frame: pd.DataFrame, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    require_columns(frame, ("target_id",))
    data = frame.copy()
    components = {
        "genetic_evidence": 0.20,
        "disease_evidence": 0.20,
        "druggability": 0.20,
        "expression_relevance": 0.10,
        "tractability": 0.10,
        "safety": 0.15,
        "competitive_novelty": 0.05,
    }
    weights = {
        key: float(parameters.get(f"{key}_weight", default))
        for key, default in components.items()
    }
    total = sum(max(0, value) for value in weights.values())
    if total <= 0:
        raise PlatformValidationError("At least one positive target-ranking weight is required")
    weights = {key: max(0, value) / total for key, value in weights.items()}
    score_parts = pd.DataFrame(index=data.index)
    missing = []
    for key in weights:
        if key == "competitive_novelty":
            competitors = numeric(
                data.get("competitor_count", pd.Series(np.nan, index=data.index))
            )
            part = 1 - np.clip(competitors.fillna(10) / 10, 0, 1)
            absent = competitors.isna()
        else:
            values = numeric(data.get(key, pd.Series(np.nan, index=data.index)))
            part = np.clip(values.fillna(0), 0, 1)
            absent = values.isna()
        score_parts[key] = part
        missing.append(absent.rename(key))
    data["priority_score"] = sum(score_parts[key] * weights[key] for key in weights)
    missing_frame = pd.concat(missing, axis=1)
    data["evidence_completeness"] = 1 - missing_frame.mean(axis=1)
    off_target = numeric(
        data.get("off_target_risk", pd.Series(0.0, index=data.index))
    ).fillna(0)
    data["priority_score"] = np.clip(data["priority_score"] - 0.15 * off_target, 0, 1)
    data["review_flags"] = [
        [
            label
            for label, condition in (
                ("Safety evidence missing", pd.isna(row.get("safety"))),
                ("Off-target risk high", float(row.get("off_target_risk") or 0) > 0.6),
                ("Low evidence completeness", float(row["evidence_completeness"]) < 0.6),
            )
            if condition
        ]
        for _, row in data.iterrows()
    ]
    data = data.sort_values("priority_score", ascending=False)
    return {
        "ranked_targets": data.to_dict(orient="records"),
        "weights": weights,
        "scientific_boundary": (
            "Target scores aggregate supplied evidence only. Open Targets, ChEMBL, UniProt, "
            "GTEx, HPA, and DepMap records require versioned verified imports."
        ),
    }


def experimental_design(
    frame: pd.DataFrame, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    effect_size = float(parameters.get("effect_size", 0))
    alpha = float(parameters.get("alpha", 0.05))
    power = float(parameters.get("power", 0.8))
    groups = int(parameters.get("groups", 2))
    dropout = float(parameters.get("dropout_fraction", 0.0))
    if effect_size <= 0:
        raise PlatformValidationError("A positive standardized effect size is required")
    if not 0 < alpha < 1 or not 0 < power < 1:
        raise PlatformValidationError("Alpha and power must be between 0 and 1")
    if groups < 2:
        raise PlatformValidationError("At least two groups are required")
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_power = stats.norm.ppf(power)
    per_group = int(np.ceil(2 * ((z_alpha + z_power) / effect_size) ** 2))
    adjusted = int(np.ceil(per_group / max(1e-9, 1 - dropout)))
    blocks = max(1, int(parameters.get("blocks", 1)))
    labels = [f"Group {index + 1}" for index in range(groups)]
    assignments = [
        {
            "sequence": index + 1,
            "block": index % blocks + 1,
            "group": labels[index % groups],
        }
        for index in range(adjusted * groups)
    ]
    imbalance_fields = []
    for field in ("batch", "plate", "sex", "timepoint"):
        if field in frame.columns:
            counts = frame.groupby([field]).size()
            imbalance_fields.append(
                {
                    "field": field, "minimum": int(counts.min()),
                    "maximum": int(counts.max()),
                    "ratio": float(counts.max() / max(1, counts.min())),
                }
            )
    return {
        "sample_size": {
            "per_group_before_dropout": per_group,
            "per_group_after_dropout": adjusted,
            "total": adjusted * groups,
            "method": "Two-sided normal approximation for a standardized two-group effect",
        },
        "randomization_plan": assignments,
        "balance_review": imbalance_fields,
        "required_controls": list(parameters.get("controls", [])),
        "blinding": str(parameters.get("blinding", "Specify operator and analyst blinding")),
        "scientific_boundary": "Confirm assumptions with the final statistical model and domain-specific variance estimates.",
    }


def _kaplan_meier(time: np.ndarray, event: np.ndarray) -> list[dict[str, float]]:
    order = np.argsort(time)
    time = time[order]
    event = event[order]
    survival = 1.0
    rows = [{"time": 0.0, "survival": 1.0, "at_risk": float(len(time))}]
    for point in np.unique(time[event == 1]):
        at_risk = int((time >= point).sum())
        events = int(((time == point) & (event == 1)).sum())
        survival *= 1 - events / max(1, at_risk)
        rows.append({"time": float(point), "survival": float(survival), "at_risk": float(at_risk)})
    return rows


def statistical_analysis(
    frame: pd.DataFrame, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    analysis_type = str(parameters.get("analysis_type", "two_group"))
    if analysis_type == "survival":
        require_columns(frame, ("time", "event", "group"))
        data = frame.copy()
        data["time"] = numeric(data["time"])
        data["event"] = numeric(data["event"]).astype("Int64")
        data = data.dropna(subset=["time", "event", "group"])
        groups = list(dict.fromkeys(data["group"].astype(str)))
        curves = {
            group: _kaplan_meier(
                data.loc[data["group"].astype(str).eq(group), "time"].to_numpy(float),
                data.loc[data["group"].astype(str).eq(group), "event"].to_numpy(int),
            )
            for group in groups
        }
        return {
            "analysis_type": "survival",
            "kaplan_meier": curves,
            "events": {
                group: int(
                    data.loc[data["group"].astype(str).eq(group), "event"].sum()
                )
                for group in groups
            },
            "scientific_boundary": "Kaplan-Meier estimates are calculated; adjusted Cox models require a configured validated statistics adapter.",
        }
    require_columns(frame, ("group", "value"))
    data = frame.copy()
    data["value"] = numeric(data["value"])
    data = data.dropna(subset=["group", "value"])
    groups = list(dict.fromkeys(data["group"].astype(str)))
    if len(groups) != 2:
        raise PlatformValidationError("Two-group analysis requires exactly two groups")
    first = data.loc[data["group"].astype(str).eq(groups[0]), "value"].to_numpy(float)
    second = data.loc[data["group"].astype(str).eq(groups[1]), "value"].to_numpy(float)
    if len(first) < 2 or len(second) < 2:
        raise PlatformValidationError("Each group requires at least two finite observations")
    paired = bool(parameters.get("paired", False))
    if paired:
        require_columns(data, ("subject_id",))
        pivot = data.pivot_table(index="subject_id", columns="group", values="value", aggfunc="mean")
        pivot = pivot.dropna(subset=groups)
        if len(pivot) < 2:
            raise PlatformValidationError("Paired analysis requires at least two complete pairs")
        first = pivot[groups[0]].to_numpy(float)
        second = pivot[groups[1]].to_numpy(float)
        parametric = stats.ttest_rel(second, first)
        nonparametric = stats.wilcoxon(second, first)
    else:
        parametric = stats.ttest_ind(second, first, equal_var=False)
        nonparametric = stats.mannwhitneyu(second, first, alternative="two-sided")
    levene = stats.levene(first, second)
    shapiro = {
        groups[0]: stats.shapiro(first).pvalue if 3 <= len(first) <= 5000 else None,
        groups[1]: stats.shapiro(second).pvalue if 3 <= len(second) <= 5000 else None,
    }
    seed = int(parameters.get("seed", 42))
    rng = np.random.default_rng(seed)
    bootstrap = []
    for _ in range(min(5000, int(parameters.get("bootstrap_iterations", 1000)))):
        bootstrap.append(
            float(
                np.mean(rng.choice(second, len(second), replace=True))
                - np.mean(rng.choice(first, len(first), replace=True))
            )
        )
    return {
        "analysis_type": "paired" if paired else "independent",
        "groups": groups,
        "descriptive": {
            groups[0]: {"n": len(first), "mean": float(np.mean(first)), "median": float(np.median(first)), "sd": float(np.std(first, ddof=1))},
            groups[1]: {"n": len(second), "mean": float(np.mean(second)), "median": float(np.median(second)), "sd": float(np.std(second, ddof=1))},
        },
        "parametric": {"statistic": float(parametric.statistic), "p_value": float(parametric.pvalue)},
        "nonparametric": {"statistic": float(nonparametric.statistic), "p_value": float(nonparametric.pvalue)},
        "standardized_effect": standardized_effect(first, second),
        "mean_difference": float(np.mean(second) - np.mean(first)),
        "bootstrap_mean_difference_ci95": [
            float(np.quantile(bootstrap, 0.025)), float(np.quantile(bootstrap, 0.975))
        ],
        "diagnostics": {
            "shapiro_p_values": shapiro,
            "levene_p_value": float(levene.pvalue),
            "missing_rows_excluded": int(len(frame) - len(data)),
        },
    }


def literature_discovery(
    frame: pd.DataFrame, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    require_columns(frame, ("title",))
    data = frame.copy()
    for column in ("pmid", "doi", "identifier", "claim_id", "direction"):
        if column not in data:
            data[column] = ""
        data[column] = data[column].fillna("").astype(str).str.strip()
    data["pmid_valid_format"] = data["pmid"].map(
        lambda value: not value or bool(PMID_RE.fullmatch(value))
    )
    data["doi_valid_format"] = data["doi"].map(
        lambda value: not value or bool(DOI_RE.fullmatch(value))
    )
    data["identifier_key"] = np.where(
        data["pmid"].ne(""), "PMID:" + data["pmid"],
        np.where(
            data["doi"].ne(""), "DOI:" + data["doi"].str.lower(),
            data["title"].astype(str).str.lower().str.replace(r"\s+", " ", regex=True),
        ),
    )
    data["duplicate"] = data.duplicated("identifier_key", keep="first")
    deduplicated = data.loc[~data["duplicate"]].copy()
    contradictions = []
    for claim_id, subset in deduplicated.loc[deduplicated["claim_id"].ne("")].groupby("claim_id"):
        directions = set(subset["direction"].str.lower()) - {""}
        if any(value in directions for value in {"support", "positive"}) and any(
            value in directions for value in {"oppose", "negative", "contradictory"}
        ):
            contradictions.append(
                {
                    "claim_id": claim_id,
                    "identifiers": subset["identifier_key"].tolist(),
                    "directions": sorted(directions),
                }
            )
    retracted = (
        deduplicated.get("retraction_state", pd.Series("", index=deduplicated.index))
        .astype(str).str.lower().isin({"retracted", "yes", "true"})
    )
    return {
        "records": deduplicated.to_dict(orient="records"),
        "summary": {
            "input_records": len(data),
            "deduplicated_records": len(deduplicated),
            "duplicates": int(data["duplicate"].sum()),
            "invalid_pmid_formats": int((~data["pmid_valid_format"]).sum()),
            "invalid_doi_formats": int((~data["doi_valid_format"]).sum()),
            "retracted_records": int(retracted.sum()),
        },
        "contradictions": contradictions,
        "search_strategy": parameters.get("search_strategy", {}),
        "scientific_boundary": (
            "Format validation is not database verification. PubMed, Europe PMC, Crossref, "
            "ClinicalTrials.gov, correction, and retraction checks require live official adapters."
        ),
    }


def hypothesis_generation(
    frame: pd.DataFrame, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    require_columns(frame, ("observation", "direction"))
    data = frame.dropna(subset=["observation", "direction"]).copy()
    if len(data) < int(parameters.get("minimum_observations", 2)):
        raise PlatformValidationError("Insufficient observations for hypothesis generation")
    exposure = str(parameters.get("exposure", "")).strip()
    outcome = str(parameters.get("outcome", "")).strip()
    mechanism = str(parameters.get("mechanism", "")).strip()
    if not exposure or not outcome:
        raise PlatformValidationError("Exposure and outcome are required")
    support = data.loc[
        data["direction"].astype(str).str.lower().isin({"support", "positive", "increased"})
    ]
    oppose = data.loc[
        data["direction"].astype(str).str.lower().isin({"oppose", "negative", "contradictory"})
    ]
    return {
        "hypothesis": (
            f"{exposure} is associated with {outcome}"
            + (f" through {mechanism}" if mechanism else "")
            + " under the stated study conditions."
        ),
        "null_hypothesis": f"{exposure} has no reproducible association with {outcome}.",
        "competing_hypotheses": [
            f"The observed association is explained by {value}."
            for value in parameters.get(
                "competing_explanations", ["batch effects", "unmeasured confounding"]
            )
        ],
        "supporting_observations": support["observation"].astype(str).tolist(),
        "contradictory_observations": oppose["observation"].astype(str).tolist(),
        "falsification_criteria": list(
            parameters.get(
                "falsification_criteria",
                [
                    "The association is absent in a preregistered independent dataset.",
                    "The effect disappears after prespecified confounder adjustment.",
                ],
            )
        ),
        "predictions": list(parameters.get("predictions", [])),
        "evidence_gaps": list(parameters.get("evidence_gaps", [])),
        "confidence": None,
        "origin": "rule_based_guidance",
        "scientific_boundary": "Generated text is a testable research hypothesis, not biological truth.",
    }


def laboratory_validation(
    frame: pd.DataFrame, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    assay = str(parameters.get("assay", "generic")).lower()
    if assay == "qpcr":
        require_columns(frame, ("target", "sample_id", "group", "ct", "reference_ct"))
        data = frame.copy()
        data["ct"] = numeric(data["ct"])
        data["reference_ct"] = numeric(data["reference_ct"])
        data["delta_ct"] = data["ct"] - data["reference_ct"]
        control_group = str(parameters.get("control_group", "")).strip()
        if not control_group:
            control_group = str(data["group"].iloc[0])
        control_mean = (
            data.loc[data["group"].astype(str).eq(control_group)]
            .groupby("target")["delta_ct"]
            .mean()
        )
        data["control_delta_ct"] = data["target"].map(control_mean)
        if data["control_delta_ct"].isna().any():
            raise PlatformValidationError("Every target requires a control-group reference")
        data["delta_delta_ct"] = data["delta_ct"] - data["control_delta_ct"]
        data["relative_expression"] = np.power(2.0, -data["delta_delta_ct"])
        replicate_cv = (
            data.groupby(["target", "group"])["delta_ct"]
            .agg(["mean", "std", "count"])
            .reset_index()
        )
        replicate_cv["delta_ct_cv"] = (
            replicate_cv["std"].abs() / replicate_cv["mean"].abs().replace(0, np.nan)
        )
        maximum_cv = float(parameters.get("maximum_replicate_cv", 0.2))
        replicate_cv["qc_pass"] = (
            (replicate_cv["count"] >= int(parameters.get("minimum_replicates", 3)))
            & (replicate_cv["delta_ct_cv"].fillna(np.inf) <= maximum_cv)
        )
        return {
            "assay": "qPCR",
            "results": data.to_dict(orient="records"),
            "replicate_qc": replicate_cv.to_dict(orient="records"),
            "acceptance_met": bool(replicate_cv["qc_pass"].all()),
            "method": "Delta-delta Ct relative quantification with prespecified control group.",
        }
    require_columns(frame, ("result_id", "observed_value"))
    data = frame.copy()
    data["observed_value"] = numeric(data["observed_value"])
    minimum = float(parameters.get("acceptance_minimum", -np.inf))
    maximum = float(parameters.get("acceptance_maximum", np.inf))
    data["acceptance_met"] = data["observed_value"].between(minimum, maximum)
    return {
        "assay": str(parameters.get("assay", "Generic validation")),
        "results": data.to_dict(orient="records"),
        "acceptance_met": bool(data["acceptance_met"].all()),
        "acceptance_range": {"minimum": minimum, "maximum": maximum},
        "scientific_boundary": "Observed values are user/import supplied; BioIntel does not fabricate assay results.",
    }
