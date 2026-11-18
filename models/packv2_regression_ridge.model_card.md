# BioIntel AI Model Card

## Model identity

- **Experiment ID:** `exp-20260704T054608+0000-3fe97e2a`
- **Artifact format:** `7.0.0`
- **Model version:** `2.0.0-data-pack`
- **Estimator:** `ridge`
- **Task:** `regression`
- **Trained at:** `2026-07-04T05:46:08+00:00`
- **Synthetic demonstration:** `Yes`

## Intended use

Educational and research-oriented Drug–Target Interaction classification or
pActivity regression. This artifact is not intended for clinical diagnosis,
treatment selection, safety assessment, regulatory decisions or proof of
physical binding.

## Dataset provenance

- **Dataset:** `biointel_synthetic_extended_dti_v2`
- **Dataset version:** `2.0`
- **Dataset SHA-256:** `2a2b6d781714a62c33bf9695eae38973b2f4111257a52e9a65c946ae10ff3d08`
- **Activity type:** `SYNTHETIC_AFFINITY_SCORE`
- **Training rows:** `3600`
- **Validation rows:** `960`
- **Final test rows:** `1200`

The hash identifies the cleaned dataframe used by this run without embedding
the raw sequences or molecule records in this card.

## Evaluation design

- **Split strategy:** `target_group`
- **Threshold strategy:** `fixed`
- **Probability calibration:** `none`
- **Decision threshold:** `None`
- **Bootstrap confidence intervals:**

```json
{
  "mae": {
    "bootstrap_samples": 50,
    "lower_95": 0.33362784823325076,
    "upper_95": 0.35642896325829904
  },
  "r2": {
    "bootstrap_samples": 50,
    "lower_95": -0.5888493870284927,
    "upper_95": -0.40040933644080406
  },
  "rmse": {
    "bootstrap_samples": 50,
    "lower_95": 0.40508848061491254,
    "upper_95": 0.43132262020260737
  }
}
```

### Conformal uncertainty calibration

```json
{
  "absolute_residual_quantile": 0.620032792279205,
  "alpha": 0.1,
  "calibration_rows": 960,
  "coverage_target": 0.9,
  "method": "split_conformal_regression"
}
```

### Validation metrics

- **mae:** 0.370474
- **mse:** 0.17324
- **rmse:** 0.416221
- **r2:** 0.0731612
- **pearson:** 0.413817
- **spearman:** 0.452554

### Final held-out test metrics

- **mae:** 0.343037
- **mse:** 0.173088
- **rmse:** 0.416039
- **r2:** -0.487907
- **pearson:** 0.31912
- **spearman:** 0.336066
- **conformal_coverage:** 0.858333
- **average_interval_width:** 1.24007

## Feature schema

- **Feature count:** `167`
- **Feature hash:** `ad1a1adefaf32ad217e60b3df843aa2ef3acde7a28c4854c8a78397f6580bf14`
- **Morgan radius:** `2`
- **Morgan bits:** `128`
- **Use chirality:** `True`
- **Dipeptide features:** `False`

## Training configuration

```json
{
  "activity_type": "SYNTHETIC_AFFINITY_SCORE",
  "bootstrap_iterations": 50,
  "calibration_method": "none",
  "conformal_alpha": 0.1,
  "dataset_name": "biointel_synthetic_extended_dti_v2",
  "dataset_version": "2.0",
  "decision_threshold": 0.5,
  "fingerprint_bits": 128,
  "fingerprint_radius": 2,
  "include_dipeptides": false,
  "model_name": "ridge",
  "model_version": "2.0.0-data-pack",
  "n_estimators": 1,
  "random_seed": 20260704,
  "source_description": "BioIntel deterministic synthetic extended DTI benchmark",
  "split_strategy": "target_group",
  "synthetic_demo": true,
  "task_type": "regression",
  "test_fraction": 0.2,
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
  "feature_cache": {
    "drug_cache_hits": 5520,
    "protein_cache_hits": 5736,
    "rows_processed": 5760,
    "unique_drugs": 240,
    "unique_targets": 24
  },
  "invalid_rows": 0,
  "original_rows": 5760,
  "p_activity_max": 7.8404,
  "p_activity_min": 5.3421,
  "split_summary": {
    "group_overlap": false,
    "strategy": "target_group",
    "test_groups": 5,
    "test_rows": 1200,
    "train_groups": 15,
    "train_rows": 3600,
    "validation_groups": 4,
    "validation_rows": 960
  },
  "task": "regression",
  "valid_after_cleaning": 5760
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
