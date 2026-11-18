from __future__ import annotations

import json

from biointel.training.model_artifact import ModelArtifact
from biointel.ui.brand import BRAND, branded_model_identity


def _metric_lines(metrics: dict[str, float | None]) -> str:
    if not metrics:
        return "- No metrics stored."
    lines = []
    for name, value in metrics.items():
        rendered = "undefined" if value is None else f"{value:.6g}"
        lines.append(f"- **{name}:** {rendered}")
    return "\n".join(lines)


def build_model_card_markdown(artifact: ModelArtifact) -> str:
    """Create a complete model card from saved artifact metadata."""

    metadata = artifact.metadata
    identity = branded_model_identity("model.joblib", metadata, {})
    schema = artifact.feature_schema
    training_config = json.dumps(metadata.training_config, indent=2, sort_keys=True, default=str)
    data_quality = json.dumps(metadata.data_quality_summary, indent=2, sort_keys=True, default=str)
    confidence_intervals = json.dumps(
        metadata.confidence_intervals, indent=2, sort_keys=True, default=str
    )
    uncertainty_calibration = json.dumps(
        metadata.uncertainty_calibration, indent=2, sort_keys=True, default=str
    )

    return f"""# {BRAND.name} Model Card

_{BRAND.descriptor} · {BRAND.tagline}_

## Model identity

- **Experiment ID:** `{metadata.experiment_id}`
- **Artifact format:** `{metadata.artifact_version}`
- **Model version:** `{metadata.model_version}`
- **Branded model:** `{identity.display_name}`
- **Estimator:** `{metadata.model_name}`
- **Evidence tier:** `Tier {identity.tier_code} — {identity.tier_label}`
- **Task:** `{metadata.task_type}`
- **Trained at:** `{metadata.trained_at_utc}`
- **Synthetic demonstration:** `{"Yes" if metadata.synthetic_demo else "No"}`

## Intended use

Educational and research-oriented Drug–Target Interaction classification or
pActivity regression. This artifact is not intended for clinical diagnosis,
treatment selection, safety assessment, regulatory decisions or proof of
physical binding.

## Dataset provenance

- **Dataset:** `{metadata.dataset_name}`
- **Dataset version:** `{metadata.dataset_version}`
- **Dataset SHA-256:** `{metadata.dataset_sha256}`
- **Activity type:** `{metadata.activity_type or "Not specified"}`
- **Training rows:** `{metadata.train_rows}`
- **Validation rows:** `{metadata.validation_rows}`
- **Final test rows:** `{metadata.test_rows}`

The hash identifies the cleaned dataframe used by this run without embedding
the raw sequences or molecule records in this card.

## Evaluation design

- **Split strategy:** `{metadata.split_strategy}`
- **Threshold strategy:** `{metadata.threshold_strategy}`
- **Probability calibration:** `{metadata.calibration_method}`
- **Decision threshold:** `{metadata.decision_threshold}`
- **Bootstrap confidence intervals:**

```json
{confidence_intervals}
```

### Conformal uncertainty calibration

```json
{uncertainty_calibration}
```

### Validation metrics

{_metric_lines(metadata.validation_metrics)}

### Final held-out test metrics

{_metric_lines(metadata.metrics)}

## Feature schema

- **Feature count:** `{schema.feature_count}`
- **Feature hash:** `{schema.feature_hash}`
- **Morgan radius:** `{schema.fingerprint_radius}`
- **Morgan bits:** `{schema.fingerprint_bits}`
- **Use chirality:** `{schema.use_chirality}`
- **Dipeptide features:** `{schema.include_dipeptides}`

## Training configuration

```json
{training_config}
```

## Data-quality summary

```json
{data_quality}
```

## Known limitations

- Results depend on assay quality, label definition, negatives and dataset bias.
- Random-pair splits can overestimate performance when related molecules or
  targets occur across partitions.
- Applicability-domain checks are screening heuristics, not guarantees.
- High probability is model confidence, not experimental certainty.
- Synthetic demo artifacts have no biological or clinical validity.
- Binding, mechanism, toxicity, pharmacokinetics and efficacy require separate
  experimental validation.

## Ethical and safety notice

For educational and research use only. Do not use this model as the sole basis
for human or animal treatment, compound administration or laboratory safety
decisions.
"""
