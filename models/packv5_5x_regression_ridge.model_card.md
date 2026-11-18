# BioIntel AI Model Card

## Model identity

- **Experiment ID:** `exp-20260704T090743+0000-329e2461`
- **Artifact format:** `7.0.0`
- **Model version:** `5.0.0-full-data`
- **Estimator:** `ridge`
- **Task:** `regression`
- **Trained at:** `2026-07-04T09:07:43+00:00`
- **Synthetic demonstration:** `Yes`

## Intended use

Educational and research-oriented Drug–Target Interaction classification or
pActivity regression. This artifact is not intended for clinical diagnosis,
treatment selection, safety assessment, regulatory decisions or proof of
physical binding.

## Dataset provenance

- **Dataset:** `biointel_synthetic_5x_ultra_dti_v5`
- **Dataset version:** `5.0`
- **Dataset SHA-256:** `5ecf426209af9814a282f1c60b16b74efac270af08a5c6aba746a9a2f74dbcd8`
- **Activity type:** `SYNTHETIC_AFFINITY_SCORE`
- **Training rows:** `104000`
- **Validation rows:** `24000`
- **Final test rows:** `32000`

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
    "bootstrap_samples": 25,
    "lower_95": 0.2943927733318424,
    "upper_95": 0.2986176986683798
  },
  "r2": {
    "bootstrap_samples": 25,
    "lower_95": -0.3468116184990698,
    "upper_95": -0.327020512228917
  },
  "rmse": {
    "bootstrap_samples": 25,
    "lower_95": 0.3564249997922743,
    "upper_95": 0.36022665306927054
  }
}
```

### Conformal uncertainty calibration

```json
{
  "absolute_residual_quantile": 0.5355911437988281,
  "alpha": 0.1,
  "calibration_rows": 24000,
  "coverage_target": 0.9,
  "method": "split_conformal_regression"
}
```

### Validation metrics

- **mae:** 0.264054
- **mse:** 0.106598
- **rmse:** 0.326494
- **r2:** 0.201999
- **pearson:** 0.514084
- **spearman:** 0.493084

### Final held-out test metrics

- **mae:** 0.296539
- **mse:** 0.128331
- **rmse:** 0.358233
- **r2:** -0.334673
- **pearson:** 0.046171
- **spearman:** 0.0162904
- **conformal_coverage:** 0.864688
- **average_interval_width:** 1.07118

## Feature schema

- **Feature count:** `103`
- **Feature hash:** `fdeb2fb3f138cbbe517a6e6bc3bfdcedd3d6009c73f0f5784890d6334a11f4ff`
- **Morgan radius:** `2`
- **Morgan bits:** `64`
- **Use chirality:** `True`
- **Dipeptide features:** `False`

## Training configuration

```json
{
  "activity_type": "SYNTHETIC_AFFINITY_SCORE",
  "bootstrap_iterations": 25,
  "calibration_method": "none",
  "conformal_alpha": 0.1,
  "dataset_name": "biointel_synthetic_5x_ultra_dti_v5",
  "dataset_version": "5.0",
  "decision_threshold": 0.5,
  "fingerprint_bits": 64,
  "fingerprint_radius": 2,
  "include_dipeptides": false,
  "model_name": "ridge",
  "model_version": "5.0.0-full-data",
  "n_estimators": 1,
  "random_seed": 20260719,
  "source_description": "BioIntel deterministic synthetic 5X Ultra 160,000-pair DTI benchmark",
  "split_strategy": "target_group",
  "synthetic_demo": true,
  "task_type": "regression",
  "test_fraction": 0.2,
  "threshold_strategy": "fixed",
  "tree_max_depth": 18,
  "tree_max_features": "sqrt",
  "tree_max_samples": null,
  "tree_min_samples_leaf": 12,
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
    "drug_cache_hits": 159000,
    "feature_count": 103,
    "matrix_bytes": 65920000,
    "matrix_dtype": "float32",
    "protein_cache_hits": 159840,
    "rows_processed": 160000,
    "unique_drugs": 1000,
    "unique_targets": 160
  },
  "invalid_rows": 0,
  "original_rows": 160000,
  "p_activity_max": 7.7669,
  "p_activity_min": 4.8337,
  "split_summary": {
    "group_overlap": false,
    "strategy": "target_group",
    "test_groups": 32,
    "test_rows": 32000,
    "train_groups": 104,
    "train_rows": 104000,
    "validation_groups": 24,
    "validation_rows": 24000
  },
  "task": "regression",
  "unique_proteins_validated": 160,
  "unique_smiles_validated": 1000,
  "valid_after_cleaning": 160000
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
