from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

import numpy as np
import pandas as pd

TARGET_WEIGHT_TEMPLATES: dict[str, dict[str, float]] = {
    "balanced": {
        "disease_relevance": 0.25,
        "genetic_evidence": 0.20,
        "pathway_evidence": 0.10,
        "tractability": 0.20,
        "safety_window": 0.10,
        "experimental_validation": 0.15,
    },
    "genetics_first": {
        "disease_relevance": 0.20,
        "genetic_evidence": 0.35,
        "pathway_evidence": 0.10,
        "tractability": 0.15,
        "safety_window": 0.10,
        "experimental_validation": 0.10,
    },
    "oncology": {
        "disease_relevance": 0.25,
        "genetic_evidence": 0.20,
        "pathway_evidence": 0.10,
        "tractability": 0.15,
        "safety_window": 0.10,
        "experimental_validation": 0.20,
    },
    "cns": {
        "disease_relevance": 0.20,
        "genetic_evidence": 0.15,
        "pathway_evidence": 0.10,
        "tractability": 0.20,
        "safety_window": 0.25,
        "experimental_validation": 0.10,
    },
    "infectious_disease": {
        "disease_relevance": 0.20,
        "genetic_evidence": 0.10,
        "pathway_evidence": 0.15,
        "tractability": 0.20,
        "safety_window": 0.20,
        "experimental_validation": 0.15,
    },
}


@dataclass(frozen=True)
class TargetPriorityScore:
    target_id: str
    disease_relevance: float
    genetic_evidence: float
    pathway_evidence: float
    tractability: float
    safety_window: float
    experimental_validation: float
    total_score: float
    confidence_adjusted_score: float
    evidence_confidence: float
    priority_tier: str
    limiting_factors: list[str]
    gate_failures: list[str]
    contributions: dict[str, float]
    methodology: dict[str, object]


def _bounded(value: float, name: str) -> float:
    numeric = float(value)
    if not 0 <= numeric <= 100:
        raise ValueError(f"{name} must be between 0 and 100.")
    return numeric


def _normalized_weights(weights: Mapping[str, float]) -> dict[str, float]:
    expected = set(TARGET_WEIGHT_TEMPLATES["balanced"])
    missing = expected - set(weights)
    extra = set(weights) - expected
    if missing or extra:
        raise ValueError(
            "Target weights must contain exactly: " + ", ".join(sorted(expected))
        )
    cleaned = {name: float(value) for name, value in weights.items()}
    if any(value < 0 for value in cleaned.values()):
        raise ValueError("Target weights cannot be negative.")
    total = sum(cleaned.values())
    if total <= 0:
        raise ValueError("At least one positive target weight is required.")
    return {name: value / total for name, value in cleaned.items()}


def score_target_priority(
    target_id: str,
    *,
    disease_relevance: float,
    genetic_evidence: float,
    pathway_evidence: float,
    tractability: float,
    safety_window: float,
    experimental_validation: float,
    template: str = "balanced",
    weights: Mapping[str, float] | None = None,
    evidence_confidence: float = 100.0,
    hard_gates: Mapping[str, float] | None = None,
) -> TargetPriorityScore:
    values = {
        "disease_relevance": _bounded(disease_relevance, "disease_relevance"),
        "genetic_evidence": _bounded(genetic_evidence, "genetic_evidence"),
        "pathway_evidence": _bounded(pathway_evidence, "pathway_evidence"),
        "tractability": _bounded(tractability, "tractability"),
        "safety_window": _bounded(safety_window, "safety_window"),
        "experimental_validation": _bounded(
            experimental_validation, "experimental_validation"
        ),
    }
    confidence = _bounded(evidence_confidence, "evidence_confidence")
    if weights is None:
        if template not in TARGET_WEIGHT_TEMPLATES:
            raise ValueError(
                "Unknown target-priority template. Choose: "
                + ", ".join(sorted(TARGET_WEIGHT_TEMPLATES))
            )
        selected_weights = _normalized_weights(TARGET_WEIGHT_TEMPLATES[template])
    else:
        selected_weights = _normalized_weights(weights)
        template = "custom"

    contributions = {
        name: round(values[name] * selected_weights[name], 4) for name in values
    }
    total = round(sum(contributions.values()), 2)
    adjusted = round(total * (0.5 + 0.5 * confidence / 100.0), 2)
    gates = {name: float(value) for name, value in (hard_gates or {}).items()}
    gate_failures = [
        f"{name.replace('_', ' ').title()} below gate ({values[name]:.1f} < {threshold:.1f})"
        for name, threshold in gates.items()
        if name in values and values[name] < threshold
    ]
    decision_score = adjusted
    if gate_failures:
        tier = "D — blocked by hard gate"
    elif decision_score >= 80:
        tier = "A — high priority"
    elif decision_score >= 65:
        tier = "B — promising"
    elif decision_score >= 50:
        tier = "C — evidence gaps"
    else:
        tier = "D — low priority / insufficient evidence"
    limiting = [name.replace("_", " ").title() for name, value in values.items() if value < 50]
    return TargetPriorityScore(
        target_id=str(target_id).strip() or "unnamed_target",
        total_score=total,
        confidence_adjusted_score=adjusted,
        evidence_confidence=confidence,
        priority_tier=tier,
        limiting_factors=limiting,
        gate_failures=gate_failures,
        contributions=contributions,
        methodology={
            "type": "user-evidence weighted prioritisation",
            "template": template,
            "weights": selected_weights,
            "confidence_adjustment": "score × (0.5 + 0.5 × evidence confidence)",
            "hard_gates": gates,
            "warning": (
                "Scores reflect supplied or imported evidence ratings and are not "
                "independent biological evidence."
            ),
        },
        **values,
    )


def target_score_dict(result: TargetPriorityScore) -> dict[str, object]:
    return asdict(result)


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def _normalize_objective(
    series: pd.Series,
    *,
    higher_is_better: bool,
    method: str,
    winsor_fraction: float,
) -> tuple[pd.Series, pd.Series]:
    numeric = _numeric(series)
    missing = numeric.isna()
    observed = numeric.dropna()
    if observed.empty:
        return pd.Series(0.0, index=series.index), missing

    clipped = numeric.copy()
    if method in {"robust_percentile", "winsorized_minmax"} and len(observed) >= 4:
        fraction = min(max(float(winsor_fraction), 0.0), 0.2)
        lower, upper = observed.quantile([fraction, 1 - fraction])
        clipped = clipped.clip(lower=lower, upper=upper)

    if method == "robust_percentile":
        normalized = clipped.rank(method="average", pct=True)
        if not higher_is_better:
            normalized = 1.0 - normalized + (1.0 / max(len(observed), 1))
    elif method == "zscore":
        median = float(observed.median())
        mad = float((observed - median).abs().median())
        scale = 1.4826 * mad
        if scale <= 1e-12:
            normalized = pd.Series(0.5, index=series.index)
        else:
            z = (clipped - median) / scale
            z = z.clip(-6, 6)
            normalized = 1.0 / (1.0 + np.exp(-z))
            if not higher_is_better:
                normalized = 1.0 - normalized
    else:
        low, high = float(clipped.min()), float(clipped.max())
        if high == low:
            normalized = pd.Series(0.5, index=series.index)
        else:
            normalized = (clipped - low) / (high - low)
            if not higher_is_better:
                normalized = 1.0 - normalized

    normalized = pd.Series(normalized, index=series.index, dtype=float).clip(0, 1)
    normalized.loc[missing] = 0.0
    return normalized, missing


def _pareto_front(values: np.ndarray) -> np.ndarray:
    count = len(values)
    front = np.ones(count, dtype=bool)
    for i in range(count):
        if not front[i]:
            continue
        dominated = np.all(values >= values[i], axis=1) & np.any(values > values[i], axis=1)
        if np.any(dominated):
            front[i] = False
    return front


def rank_discovery_hits(
    frame: pd.DataFrame,
    *,
    id_column: str,
    benefit_columns: dict[str, float] | None = None,
    cost_columns: dict[str, float] | None = None,
    method: str = "robust_percentile",
    missing_penalty: float = 0.20,
    winsor_fraction: float = 0.05,
    minimum_completeness: float = 0.0,
) -> pd.DataFrame:
    """Rank compounds with explicit missingness, completeness and Pareto diagnostics.

    Methods: ``robust_percentile`` (default), ``winsorized_minmax``, ``minmax``
    and ``zscore``. Missing values always receive the worst normalized value and a
    separate weighted penalty; they can never be treated as best-in-class.
    """
    if frame.empty:
        return frame.copy()
    if id_column not in frame.columns:
        raise ValueError(f"Missing identifier column: {id_column}")
    benefits = (
        benefit_columns
        if benefit_columns is not None
        else {"developability_score": 0.45, "qed": 0.20}
    )
    costs = cost_columns if cost_columns is not None else {
        "risk_score": 0.25,
        "synthetic_accessibility_heuristic": 0.10,
    }
    requested = list(benefits) + list(costs)
    missing_columns = [column for column in requested if column not in frame.columns]
    if missing_columns:
        raise ValueError("Missing ranking column(s): " + ", ".join(missing_columns))
    if set(benefits) & set(costs):
        raise ValueError("An objective cannot be both benefit and cost.")
    allowed_methods = {"robust_percentile", "winsorized_minmax", "minmax", "zscore"}
    if method not in allowed_methods:
        raise ValueError("Unsupported ranking method: " + method)
    total_weight = sum(float(value) for value in benefits.values()) + sum(
        float(value) for value in costs.values()
    )
    if total_weight <= 0:
        raise ValueError("At least one positive ranking weight is required.")
    if not 0 <= missing_penalty <= 1:
        raise ValueError("missing_penalty must be between 0 and 1.")
    if not 0 <= minimum_completeness <= 1:
        raise ValueError("minimum_completeness must be between 0 and 1.")

    result = frame.copy()
    score = pd.Series(0.0, index=result.index, dtype=float)
    missing_weight = pd.Series(0.0, index=result.index, dtype=float)
    normalized_columns: list[str] = []

    for column, raw_weight in benefits.items():
        weight = float(raw_weight) / total_weight
        normalized, missing = _normalize_objective(
            result[column],
            higher_is_better=True,
            method=method,
            winsor_fraction=winsor_fraction,
        )
        result[f"normalized_{column}"] = normalized.round(6)
        result[f"contribution_{column}"] = (normalized * weight * 100).round(3)
        normalized_columns.append(f"normalized_{column}")
        score += normalized * weight * 100
        missing_weight += missing.astype(float) * weight

    for column, raw_weight in costs.items():
        weight = float(raw_weight) / total_weight
        normalized, missing = _normalize_objective(
            result[column],
            higher_is_better=False,
            method=method,
            winsor_fraction=winsor_fraction,
        )
        result[f"normalized_{column}"] = normalized.round(6)
        result[f"contribution_{column}"] = (normalized * weight * 100).round(3)
        normalized_columns.append(f"normalized_{column}")
        score += normalized * weight * 100
        missing_weight += missing.astype(float) * weight

    result["objective_completeness"] = (1.0 - missing_weight).clip(0, 1).round(4)
    result["missing_objective_count"] = result[requested].isna().sum(axis=1).astype(int)
    result["missing_evidence_penalty"] = (missing_weight * missing_penalty * 100).round(3)
    result["multi_objective_score"] = (
        score - result["missing_evidence_penalty"]
    ).clip(lower=0).round(3)
    result["ranking_eligible"] = result["objective_completeness"] >= minimum_completeness
    result["ranking_warning"] = np.where(
        result["missing_objective_count"] > 0,
        "Ranked with missing evidence; worst-value and explicit penalty applied",
        "Complete selected objective set",
    )
    matrix = result[normalized_columns].fillna(0.0).to_numpy(dtype=float)
    result["pareto_front"] = _pareto_front(matrix)
    result["ranking_method"] = method

    result = result.sort_values(
        ["ranking_eligible", "multi_objective_score", "objective_completeness", id_column],
        ascending=[False, False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    result.insert(0, "hit_rank", np.arange(1, len(result) + 1))
    return result
