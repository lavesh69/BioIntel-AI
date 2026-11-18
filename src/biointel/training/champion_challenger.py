from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from biointel.training.model_artifact import ModelArtifact
from biointel.training.model_catalog import update_model_catalog


@dataclass(frozen=True)
class ModelComparison:
    champion_score: float
    challenger_score: float
    challenger_wins: bool
    metric_name: str
    improvement: float
    reasons: tuple[str, ...]


def _metric(artifact: ModelArtifact) -> tuple[str, float, bool]:
    metrics = artifact.metadata.metrics
    if artifact.metadata.task_type == "classification":
        for name in ("roc_auc", "balanced_accuracy", "f1"):
            value = metrics.get(name)
            if value is not None:
                return name, float(value), True
    else:
        for name in ("rmse", "mae"):
            value = metrics.get(name)
            if value is not None:
                return name, float(value), False
    raise ValueError("Artifact does not contain a comparable primary metric.")


def compare_champion_challenger(
    champion: ModelArtifact,
    challenger: ModelArtifact,
    *,
    minimum_relative_improvement: float = 0.01,
    require_non_synthetic_challenger: bool = False,
) -> ModelComparison:
    if champion.metadata.task_type != challenger.metadata.task_type:
        raise ValueError("Champion and challenger task types differ.")
    champion.validate_feature_schema(challenger.feature_schema, challenger.feature_names)
    metric_name, champion_value, higher_is_better = _metric(champion)
    challenger_metric, challenger_value, _ = _metric(challenger)
    if challenger_metric != metric_name:
        raise ValueError("Artifacts do not expose the same primary metric.")
    reasons: list[str] = []
    if higher_is_better:
        improvement = (challenger_value - champion_value) / max(abs(champion_value), 1e-12)
    else:
        improvement = (champion_value - challenger_value) / max(abs(champion_value), 1e-12)
    challenger_wins = improvement >= minimum_relative_improvement
    if improvement < minimum_relative_improvement:
        reasons.append(
            f"Relative {metric_name} improvement {improvement:.2%} is below "
            f"the required {minimum_relative_improvement:.2%}."
        )
    if require_non_synthetic_challenger and challenger.metadata.synthetic_demo:
        challenger_wins = False
        reasons.append("Challenger is marked as synthetic/demo.")
    return ModelComparison(
        champion_score=champion_value,
        challenger_score=challenger_value,
        challenger_wins=challenger_wins,
        metric_name=metric_name,
        improvement=improvement,
        reasons=tuple(reasons),
    )


def promote_challenger(
    models_directory: str | Path,
    challenger_filename: str,
    comparison: ModelComparison,
) -> None:
    if not comparison.challenger_wins:
        raise ValueError("Challenger did not satisfy promotion criteria.")
    update_model_catalog(
        models_directory,
        challenger_filename,
        state="active",
        is_default=True,
        notes=(
            f"Promoted by champion-challenger policy: {comparison.metric_name} "
            f"improvement {comparison.improvement:.2%}."
        ),
    )
