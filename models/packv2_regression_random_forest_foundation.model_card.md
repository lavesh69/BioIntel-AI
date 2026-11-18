# BioIntel AI Model Card

## Model identity

- **Experiment ID:** `exp-20260704T054609+0000-b90270df`
- **Artifact format:** `7.0.0`
- **Model version:** `2.0.0-data-pack`
- **Estimator:** `random_forest`
- **Task:** `regression`
- **Trained at:** `2026-07-04T05:46:09+00:00`
- **Synthetic demonstration:** `Yes`

## Intended use

Educational and research-oriented Drug–Target Interaction classification or
pActivity regression. This artifact is not intended for clinical diagnosis,
treatment selection, safety assessment, regulatory decisions or proof of
physical binding.

## Dataset provenance

- **Dataset:** `biointel_synthetic_foundation_dti_v2`
- **Dataset version:** `2.0`
- **Dataset SHA-256:** `eb22d30a5dd91fc17b49c60685be39c697f6332c5dea3d12e14838171a834d3c`
- **Activity type:** `SYNTHETIC_AFFINITY_SCORE`
- **Training rows:** `1080`
- **Validation rows:** `360`
- **Final test rows:** `480`

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
    "lower_95": 0.24763028762724598,
    "upper_95": 0.27639846535666074
  },
  "r2": {
    "bootstrap_samples": 50,
    "lower_95": 0.004859023050045368,
    "upper_95": 0.11009376600076708
  },
  "rmse": {
    "bootstrap_samples": 50,
    "lower_95": 0.29917851750847396,
    "upper_95": 0.33225139603246917
  }
}
```

### Conformal uncertainty calibration

```json
{
  "absolute_residual_quantile": 0.5306931170634934,
  "alpha": 0.1,
  "calibration_rows": 360,
  "coverage_target": 0.9,
  "method": "split_conformal_regression"
}
```

### Validation metrics

- **mae:** 0.262241
- **mse:** 0.100775
- **rmse:** 0.317451
- **r2:** 0.117208
- **pearson:** 0.417393
- **spearman:** 0.37925

### Final held-out test metrics

- **mae:** 0.260912
- **mse:** 0.0987236
- **rmse:** 0.314203
- **r2:** 0.0616177
- **pearson:** 0.33993
- **spearman:** 0.336796
- **conformal_coverage:** 0.933333
- **average_interval_width:** 1.06139

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
  "dataset_name": "biointel_synthetic_foundation_dti_v2",
  "dataset_version": "2.0",
  "decision_threshold": 0.5,
  "fingerprint_bits": 128,
  "fingerprint_radius": 2,
  "include_dipeptides": false,
  "model_name": "random_forest",
  "model_version": "2.0.0-data-pack",
  "n_estimators": 60,
  "random_seed": 20260704,
  "source_description": "BioIntel deterministic synthetic foundation DTI benchmark",
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
    "drug_cache_hits": 1800,
    "protein_cache_hits": 1904,
    "rows_processed": 1920,
    "unique_drugs": 120,
    "unique_targets": 16
  },
  "invalid_rows": 0,
  "original_rows": 1920,
  "p_activity_max": 7.7334,
  "p_activity_min": 5.3521,
  "split_summary": {
    "group_overlap": false,
    "strategy": "target_group",
    "test_groups": 4,
    "test_rows": 480,
    "train_groups": 9,
    "train_rows": 1080,
    "validation_groups": 3,
    "validation_rows": 360
  },
  "task": "regression",
  "valid_after_cleaning": 1920
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
