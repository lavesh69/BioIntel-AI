# BioIntel AI Model Card

## Model identity

- **Experiment ID:** `exp-20260704T064302+0000-d048d331`
- **Artifact format:** `7.0.0`
- **Model version:** `3.0.0-ml-suite`
- **Estimator:** `sgd_logistic`
- **Task:** `classification`
- **Trained at:** `2026-07-04T06:43:02+00:00`
- **Synthetic demonstration:** `Yes`

## Intended use

Educational and research-oriented Drug–Target Interaction classification or
pActivity regression. This artifact is not intended for clinical diagnosis,
treatment selection, safety assessment, regulatory decisions or proof of
physical binding.

## Dataset provenance

- **Dataset:** `biointel_synthetic_ultra_dti_v3`
- **Dataset version:** `3.0`
- **Dataset SHA-256:** `9d600083ca0631a99c34896b8929f8e8dc69b86a74eddf2fead1039ee5ca5fdd`
- **Activity type:** `SYNTHETIC_AFFINITY_SCORE`
- **Training rows:** `10400`
- **Validation rows:** `2400`
- **Final test rows:** `3200`

The hash identifies the cleaned dataframe used by this run without embedding
the raw sequences or molecule records in this card.

## Evaluation design

- **Split strategy:** `drug_group`
- **Threshold strategy:** `optimize_balanced`
- **Probability calibration:** `none`
- **Decision threshold:** `0.7899999999999999`
- **Bootstrap confidence intervals:**

```json
{
  "accuracy": {
    "bootstrap_samples": 40,
    "lower_95": 0.6820859374999999,
    "upper_95": 0.7091796875
  },
  "balanced_accuracy": {
    "bootstrap_samples": 40,
    "lower_95": 0.6812726605367905,
    "upper_95": 0.7083989186452151
  },
  "f1": {
    "bootstrap_samples": 40,
    "lower_95": 0.6948642008902104,
    "upper_95": 0.7259259135038928
  },
  "pr_auc": {
    "bootstrap_samples": 40,
    "lower_95": 0.7538650057454762,
    "upper_95": 0.8040759287636381
  },
  "roc_auc": {
    "bootstrap_samples": 40,
    "lower_95": 0.7613006345815299,
    "upper_95": 0.7895579702109252
  }
}
```

### Conformal uncertainty calibration

```json
{
  "alpha": 0.1,
  "calibration_rows": 2400,
  "coverage_target": 0.9,
  "method": "split_conformal_classification",
  "score_quantile": 0.9999999769916049
}
```

### Validation metrics

- **accuracy:** 0.72625
- **balanced_accuracy:** 0.724244
- **precision:** 0.767406
- **recall:** 0.739676
- **specificity:** 0.708812
- **f1:** 0.753286
- **mcc:** 0.44646
- **roc_auc:** 0.784432
- **pr_auc:** 0.814904
- **log_loss:** 4.13598
- **brier_score:** 0.261319

### Final held-out test metrics

- **accuracy:** 0.696875
- **balanced_accuracy:** 0.696175
- **precision:** 0.715821
- **recall:** 0.70821
- **specificity:** 0.684141
- **f1:** 0.711995
- **mcc:** 0.392119
- **roc_auc:** 0.776667
- **pr_auc:** 0.784548
- **log_loss:** 3.57084
- **brier_score:** 0.281889
- **conformal_coverage:** 0.926875
- **average_prediction_set_size:** 1.56563
- **empty_prediction_set_fraction:** 0

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
  "dataset_name": "biointel_synthetic_ultra_dti_v3",
  "dataset_version": "3.0",
  "decision_threshold": 0.5,
  "fingerprint_bits": 128,
  "fingerprint_radius": 2,
  "include_dipeptides": false,
  "model_name": "sgd_logistic",
  "model_version": "3.0.0-ml-suite",
  "n_estimators": 1,
  "random_seed": 20260716,
  "source_description": "BioIntel deterministic synthetic ultra DTI benchmark",
  "split_strategy": "drug_group",
  "synthetic_demo": true,
  "task_type": "classification",
  "test_fraction": 0.2,
  "threshold_strategy": "optimize_balanced",
  "use_chirality": true,
  "validation_fraction": 0.15
}
```

## Data-quality summary

```json
{
  "class_distribution": {
    "0": 8000,
    "1": 8000
  },
  "conflicting_pair_groups": 0,
  "exact_duplicate_rows": 0,
  "feature_cache": {
    "drug_cache_hits": 15600,
    "protein_cache_hits": 15960,
    "rows_processed": 16000,
    "unique_drugs": 400,
    "unique_targets": 40
  },
  "invalid_rows": 0,
  "original_rows": 16000,
  "p_activity_max": null,
  "p_activity_min": null,
  "split_summary": {
    "group_overlap": false,
    "strategy": "drug_group",
    "test_groups": 80,
    "test_rows": 3200,
    "train_groups": 260,
    "train_rows": 10400,
    "validation_groups": 60,
    "validation_rows": 2400
  },
  "task": "classification",
  "valid_after_cleaning": 16000
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
