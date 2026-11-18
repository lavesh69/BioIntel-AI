# BioIntel AI Model Card

## Model identity

- **Experiment ID:** `exp-20260704T064723+0000-92ea46b2`
- **Artifact format:** `7.0.0`
- **Model version:** `3.0.0-ml-suite`
- **Estimator:** `sgd_regression`
- **Task:** `regression`
- **Trained at:** `2026-07-04T06:47:23+00:00`
- **Synthetic demonstration:** `Yes`

## Intended use

Educational and research-oriented Drug–Target Interaction classification or
pActivity regression. This artifact is not intended for clinical diagnosis,
treatment selection, safety assessment, regulatory decisions or proof of
physical binding.

## Dataset provenance

- **Dataset:** `biointel_synthetic_extended_dti_v3`
- **Dataset version:** `3.0`
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
    "bootstrap_samples": 40,
    "lower_95": 0.2565998693853823,
    "upper_95": 0.2792400751834505
  },
  "r2": {
    "bootstrap_samples": 40,
    "lower_95": -0.5023270987776037,
    "upper_95": -0.2234663365819478
  },
  "rmse": {
    "bootstrap_samples": 40,
    "lower_95": 0.32169133812565465,
    "upper_95": 0.34744826502603793
  }
}
```

### Conformal uncertainty calibration

```json
{
  "absolute_residual_quantile": 0.7572482541386405,
  "alpha": 0.1,
  "calibration_rows": 960,
  "coverage_target": 0.9,
  "method": "split_conformal_regression"
}
```

### Validation metrics

- **mae:** 0.370405
- **mse:** 0.20786
- **rmse:** 0.455917
- **r2:** -0.352547
- **pearson:** 0.74592
- **spearman:** 0.556635

### Final held-out test metrics

- **mae:** 0.265254
- **mse:** 0.110679
- **rmse:** 0.332684
- **r2:** -0.344167
- **pearson:** 0.454817
- **spearman:** 0.484569
- **conformal_coverage:** 0.986667
- **average_interval_width:** 1.5145

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
  "dataset_name": "biointel_synthetic_extended_dti_v3",
  "dataset_version": "3.0",
  "decision_threshold": 0.5,
  "fingerprint_bits": 128,
  "fingerprint_radius": 2,
  "include_dipeptides": false,
  "model_name": "sgd_regression",
  "model_version": "3.0.0-ml-suite",
  "n_estimators": 1,
  "random_seed": 20260716,
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
