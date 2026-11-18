# BioIntel AI Model Card

## Model identity

- **Experiment ID:** `exp-20260704T064724+0000-7101bc29`
- **Artifact format:** `7.0.0`
- **Model version:** `3.0.0-ml-suite`
- **Estimator:** `extra_trees`
- **Task:** `regression`
- **Trained at:** `2026-07-04T06:47:24+00:00`
- **Synthetic demonstration:** `Yes`

## Intended use

Educational and research-oriented Drug–Target Interaction classification or
pActivity regression. This artifact is not intended for clinical diagnosis,
treatment selection, safety assessment, regulatory decisions or proof of
physical binding.

## Dataset provenance

- **Dataset:** `biointel_synthetic_foundation_dti_v3`
- **Dataset version:** `3.0`
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
    "bootstrap_samples": 40,
    "lower_95": 0.23497118144354545,
    "upper_95": 0.2626539961059577
  },
  "r2": {
    "bootstrap_samples": 40,
    "lower_95": 0.14099723435132552,
    "upper_95": 0.2700490777815288
  },
  "rmse": {
    "bootstrap_samples": 40,
    "lower_95": 0.2962487906588075,
    "upper_95": 0.3303843621644327
  }
}
```

### Conformal uncertainty calibration

```json
{
  "absolute_residual_quantile": 1.04596137797619,
  "alpha": 0.1,
  "calibration_rows": 360,
  "coverage_target": 0.9,
  "method": "split_conformal_regression"
}
```

### Validation metrics

- **mae:** 0.440045
- **mse:** 0.345768
- **rmse:** 0.58802
- **r2:** -1.42649
- **pearson:** -0.263473
- **spearman:** -0.276111

### Final held-out test metrics

- **mae:** 0.246979
- **mse:** 0.0951525
- **rmse:** 0.308468
- **r2:** 0.201699
- **pearson:** 0.456424
- **spearman:** 0.442027
- **conformal_coverage:** 0.997917
- **average_interval_width:** 2.09192

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
  "bootstrap_iterations": 40,
  "calibration_method": "none",
  "conformal_alpha": 0.1,
  "dataset_name": "biointel_synthetic_foundation_dti_v3",
  "dataset_version": "3.0",
  "decision_threshold": 0.5,
  "fingerprint_bits": 128,
  "fingerprint_radius": 2,
  "include_dipeptides": false,
  "model_name": "extra_trees",
  "model_version": "3.0.0-ml-suite",
  "n_estimators": 80,
  "random_seed": 20260716,
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
