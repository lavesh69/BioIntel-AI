# BioIntel AI Model Card

## Model identity

- **Experiment ID:** `exp-20260704T080443+0000-de0e9e4b`
- **Artifact format:** `7.0.0`
- **Model version:** `4.0.0-double-data`
- **Estimator:** `random_forest`
- **Task:** `classification`
- **Trained at:** `2026-07-04T08:04:43+00:00`
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
- **Training rows:** `20800`
- **Validation rows:** `4800`
- **Final test rows:** `6400`

The hash identifies the cleaned dataframe used by this run without embedding
the raw sequences or molecule records in this card.

## Evaluation design

- **Split strategy:** `drug_group`
- **Threshold strategy:** `optimize_balanced`
- **Probability calibration:** `none`
- **Decision threshold:** `0.49499999999999994`
- **Bootstrap confidence intervals:**

```json
{
  "accuracy": {
    "bootstrap_samples": 30,
    "lower_95": 0.785296875,
    "upper_95": 0.80224609375
  },
  "balanced_accuracy": {
    "bootstrap_samples": 30,
    "lower_95": 0.7852325968055888,
    "upper_95": 0.8022881919424951
  },
  "f1": {
    "bootstrap_samples": 30,
    "lower_95": 0.7814387283710058,
    "upper_95": 0.8003492913588689
  },
  "pr_auc": {
    "bootstrap_samples": 30,
    "lower_95": 0.8775984851186103,
    "upper_95": 0.8936986517167645
  },
  "roc_auc": {
    "bootstrap_samples": 30,
    "lower_95": 0.8741996441517379,
    "upper_95": 0.8869055621749117
  }
}
```

### Conformal uncertainty calibration

```json
{
  "alpha": 0.1,
  "calibration_rows": 4800,
  "coverage_target": 0.9,
  "method": "split_conformal_classification",
  "score_quantile": 0.6470309438614733
}
```

### Validation metrics

- **accuracy:** 0.802083
- **balanced_accuracy:** 0.801842
- **precision:** 0.803981
- **recall:** 0.78896
- **specificity:** 0.814724
- **f1:** 0.796399
- **mcc:** 0.603993
- **roc_auc:** 0.885604
- **pr_auc:** 0.881876
- **log_loss:** 0.432889
- **brier_score:** 0.137511

### Final held-out test metrics

- **accuracy:** 0.791562
- **balanced_accuracy:** 0.791677
- **precision:** 0.804257
- **recall:** 0.774294
- **specificity:** 0.809059
- **f1:** 0.788991
- **mcc:** 0.58362
- **roc_auc:** 0.88055
- **pr_auc:** 0.886161
- **log_loss:** 0.436442
- **brier_score:** 0.140549
- **conformal_coverage:** 0.893281
- **average_prediction_set_size:** 1.23781
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
  "bootstrap_iterations": 30,
  "calibration_method": "none",
  "conformal_alpha": 0.1,
  "dataset_name": "biointel_synthetic_double_ultra_dti_v4",
  "dataset_version": "4.0",
  "decision_threshold": 0.5,
  "fingerprint_bits": 128,
  "fingerprint_radius": 2,
  "include_dipeptides": false,
  "model_name": "random_forest",
  "model_version": "4.0.0-double-data",
  "n_estimators": 120,
  "random_seed": 20260717,
  "source_description": "BioIntel deterministic synthetic Double Ultra 32,000-pair DTI benchmark",
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
    "0": 16001,
    "1": 15999
  },
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
  "p_activity_max": null,
  "p_activity_min": null,
  "split_summary": {
    "group_overlap": false,
    "strategy": "drug_group",
    "test_groups": 128,
    "test_rows": 6400,
    "train_groups": 416,
    "train_rows": 20800,
    "validation_groups": 96,
    "validation_rows": 4800
  },
  "task": "classification",
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
