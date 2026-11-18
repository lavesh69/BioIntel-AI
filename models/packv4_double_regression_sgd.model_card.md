# BioIntel AI Model Card

## Model identity

- **Experiment ID:** `exp-20260704T080622+0000-7ecd1bd3`
- **Artifact format:** `7.0.0`
- **Model version:** `4.0.0-double-data`
- **Estimator:** `sgd_regression`
- **Task:** `regression`
- **Trained at:** `2026-07-04T08:06:22+00:00`
- **Synthetic demonstration:** `Yes`

## Intended use

Educational and research-oriented Drug–Target Interaction classification or
pActivity regression. This artifact is not intended for clinical diagnosis,
treatment selection, safety assessment, regulatory decisions or proof of
physical binding.

## Dataset provenance

- **Dataset:** `biointel_synthetic_double_ultra_dti_v4`
- **Dataset version:** `4.0`
- **Dataset SHA-256:** `cbdc6fd2bea79184cb0e1577865125b8bf815b654da74f7834f4a95166d051cd`
- **Activity type:** `SYNTHETIC_AFFINITY_SCORE`
- **Training rows:** `20480`
- **Validation rows:** `5120`
- **Final test rows:** `6400`

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
    "bootstrap_samples": 30,
    "lower_95": 0.6309546606005353,
    "upper_95": 0.6492616693251938
  },
  "r2": {
    "bootstrap_samples": 30,
    "lower_95": -2.7196637478901398,
    "upper_95": -2.449987750715722
  },
  "rmse": {
    "bootstrap_samples": 30,
    "lower_95": 0.7520743868733096,
    "upper_95": 0.770311127256323
  }
}
```

### Conformal uncertainty calibration

```json
{
  "absolute_residual_quantile": 0.5890115513931251,
  "alpha": 0.1,
  "calibration_rows": 5120,
  "coverage_target": 0.9,
  "method": "split_conformal_regression"
}
```

### Validation metrics

- **mae:** 0.277476
- **mse:** 0.125499
- **rmse:** 0.354259
- **r2:** -0.501927
- **pearson:** 0.466969
- **spearman:** 0.47432

### Final held-out test metrics

- **mae:** 0.640914
- **mse:** 0.581487
- **rmse:** 0.762553
- **r2:** -2.60877
- **pearson:** -0.148163
- **spearman:** 0.00307008
- **conformal_coverage:** 0.496719
- **average_interval_width:** 1.17802

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
  "bootstrap_iterations": 30,
  "calibration_method": "none",
  "conformal_alpha": 0.1,
  "dataset_name": "biointel_synthetic_double_ultra_dti_v4",
  "dataset_version": "4.0",
  "decision_threshold": 0.5,
  "fingerprint_bits": 128,
  "fingerprint_radius": 2,
  "include_dipeptides": false,
  "model_name": "sgd_regression",
  "model_version": "4.0.0-double-data",
  "n_estimators": 1,
  "random_seed": 20260717,
  "source_description": "BioIntel deterministic synthetic Double Ultra 32,000-pair DTI benchmark",
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
    "drug_cache_hits": 31360,
    "protein_cache_hits": 31950,
    "rows_processed": 32000,
    "unique_drugs": 640,
    "unique_targets": 50
  },
  "invalid_rows": 0,
  "original_rows": 32000,
  "p_activity_max": 7.656,
  "p_activity_min": 4.8659,
  "split_summary": {
    "group_overlap": false,
    "strategy": "target_group",
    "test_groups": 10,
    "test_rows": 6400,
    "train_groups": 32,
    "train_rows": 20480,
    "validation_groups": 8,
    "validation_rows": 5120
  },
  "task": "regression",
  "valid_after_cleaning": 32000
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
