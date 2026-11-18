# BioIntel AI Model Card

## Model identity

- **Experiment ID:** `exp-20260704T040150+0000-ed702f95`
- **Artifact format:** `7.0.0`
- **Model version:** `1.0.0-demo`
- **Estimator:** `random_forest`
- **Task:** `regression`
- **Trained at:** `2026-07-04T04:01:50+00:00`
- **Synthetic demonstration:** `Yes`

## Intended use

Educational and research-oriented Drug–Target Interaction classification or
pActivity regression. This artifact is not intended for clinical diagnosis,
treatment selection, safety assessment, regulatory decisions or proof of
physical binding.

## Dataset provenance

- **Dataset:** `synthetic_dti_demo`
- **Dataset version:** `1.0`
- **Dataset SHA-256:** `a3112f390dc5bacb62092db9a0f66a5cd2084543638b93e6d4df2234fbcb4d64`
- **Activity type:** `SYNTHETIC_SCORE`
- **Training rows:** `57`
- **Validation rows:** `15`
- **Final test rows:** `24`

The hash identifies the cleaned dataframe used by this run without embedding
the raw sequences or molecule records in this card.

## Evaluation design

- **Split strategy:** `random_pair`
- **Threshold strategy:** `fixed`
- **Probability calibration:** `none`
- **Decision threshold:** `None`
- **Bootstrap confidence intervals:**

```json
{
  "mae": {
    "bootstrap_samples": 200,
    "lower_95": 0.4758896728726997,
    "upper_95": 0.8618074785099875
  },
  "r2": {
    "bootstrap_samples": 200,
    "lower_95": -0.47288066826536396,
    "upper_95": 0.02351233018020782
  },
  "rmse": {
    "bootstrap_samples": 200,
    "lower_95": 0.631111234190758,
    "upper_95": 1.0274022476237066
  }
}
```

### Conformal uncertainty calibration

```json
{
  "absolute_residual_quantile": 1.6843961309523792,
  "alpha": 0.1,
  "calibration_rows": 15,
  "coverage_target": 0.9,
  "method": "split_conformal_regression"
}
```

### Validation metrics

- **mae:** 0.785393
- **mse:** 0.855061
- **rmse:** 0.924695
- **r2:** -0.14497
- **pearson:** -0.0307708
- **spearman:** -0.0822899

### Final held-out test metrics

- **mae:** 0.683567
- **mse:** 0.74978
- **rmse:** 0.865898
- **r2:** -0.132033
- **pearson:** -0.0474013
- **spearman:** -0.0311209
- **conformal_coverage:** 0.958333
- **average_interval_width:** 3.36879

## Feature schema

- **Feature count:** `295`
- **Feature hash:** `b989f240b3066eaf54f14201f2e41204d6a83686e606057facc2d97488c377f6`
- **Morgan radius:** `2`
- **Morgan bits:** `256`
- **Use chirality:** `True`
- **Dipeptide features:** `False`

## Training configuration

```json
{
  "activity_type": "SYNTHETIC_SCORE",
  "bootstrap_iterations": 200,
  "calibration_method": "none",
  "conformal_alpha": 0.1,
  "dataset_name": "synthetic_dti_demo",
  "dataset_version": "1.0",
  "decision_threshold": 0.5,
  "fingerprint_bits": 256,
  "fingerprint_radius": 2,
  "include_dipeptides": false,
  "model_name": "random_forest",
  "model_version": "1.0.0-demo",
  "n_estimators": 80,
  "random_seed": 42,
  "source_description": "User-provided or local dataset",
  "split_strategy": "random_pair",
  "synthetic_demo": true,
  "task_type": "regression",
  "test_fraction": 0.25,
  "threshold_strategy": "fixed",
  "use_chirality": true,
  "validation_fraction": 0.15
}
```

## Data-quality summary

```json
{
  "class_distribution": null,
  "conflicting_pair_groups": 0,
  "exact_duplicate_rows": 0,
  "invalid_rows": 0,
  "original_rows": 96,
  "p_activity_max": 7.56,
  "p_activity_min": 4.7,
  "split_summary": {
    "strategy": "random_pair",
    "test_rows": 24,
    "train_rows": 57,
    "validation_rows": 15
  },
  "task": "regression",
  "valid_after_cleaning": 96
}
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
