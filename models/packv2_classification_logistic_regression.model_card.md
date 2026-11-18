# BioIntel AI Model Card

## Model identity

- **Experiment ID:** `exp-20260704T054516+0000-1e4bd3f5`
- **Artifact format:** `7.0.0`
- **Model version:** `2.0.0-data-pack`
- **Estimator:** `logistic_regression`
- **Task:** `classification`
- **Trained at:** `2026-07-04T05:45:16+00:00`
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
- **Training rows:** `3744`
- **Validation rows:** `864`
- **Final test rows:** `1152`

The hash identifies the cleaned dataframe used by this run without embedding
the raw sequences or molecule records in this card.

## Evaluation design

- **Split strategy:** `drug_group`
- **Threshold strategy:** `optimize_balanced`
- **Probability calibration:** `none`
- **Decision threshold:** `0.3999999999999999`
- **Bootstrap confidence intervals:**

```json
{
  "accuracy": {
    "bootstrap_samples": 80,
    "lower_95": 0.7872395833333333,
    "upper_95": 0.8317274305555555
  },
  "balanced_accuracy": {
    "bootstrap_samples": 80,
    "lower_95": 0.7840012902893073,
    "upper_95": 0.8301262126990466
  },
  "f1": {
    "bootstrap_samples": 80,
    "lower_95": 0.80230783322271,
    "upper_95": 0.8453906087998341
  },
  "pr_auc": {
    "bootstrap_samples": 80,
    "lower_95": 0.8843050327760091,
    "upper_95": 0.9183021913792053
  },
  "roc_auc": {
    "bootstrap_samples": 80,
    "lower_95": 0.8795936765968392,
    "upper_95": 0.9128469308909539
  }
}
```

### Conformal uncertainty calibration

```json
{
  "alpha": 0.1,
  "calibration_rows": 864,
  "coverage_target": 0.9,
  "method": "split_conformal_classification",
  "score_quantile": 0.7128742354941751
}
```

### Validation metrics

- **accuracy:** 0.819444
- **balanced_accuracy:** 0.820412
- **precision:** 0.783898
- **recall:** 0.872642
- **specificity:** 0.768182
- **f1:** 0.825893
- **mcc:** 0.643478
- **roc_auc:** 0.890636
- **pr_auc:** 0.878088
- **log_loss:** 0.430856
- **brier_score:** 0.134713

### Final held-out test metrics

- **accuracy:** 0.80816
- **balanced_accuracy:** 0.806044
- **precision:** 0.780451
- **recall:** 0.873737
- **specificity:** 0.738351
- **f1:** 0.824464
- **mcc:** 0.619226
- **roc_auc:** 0.895385
- **pr_auc:** 0.90029
- **log_loss:** 0.41266
- **brier_score:** 0.133103
- **conformal_coverage:** 0.900174
- **average_prediction_set_size:** 1.23003
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
  "bootstrap_iterations": 80,
  "calibration_method": "none",
  "conformal_alpha": 0.1,
  "dataset_name": "biointel_synthetic_extended_dti_v2",
  "dataset_version": "2.0",
  "decision_threshold": 0.5,
  "fingerprint_bits": 128,
  "fingerprint_radius": 2,
  "include_dipeptides": false,
  "model_name": "logistic_regression",
  "model_version": "2.0.0-data-pack",
  "n_estimators": 140,
  "random_seed": 20260704,
  "source_description": "BioIntel deterministic synthetic extended DTI benchmark",
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
    "0": 2881,
    "1": 2879
  },
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
  "p_activity_max": null,
  "p_activity_min": null,
  "split_summary": {
    "group_overlap": false,
    "strategy": "drug_group",
    "test_groups": 48,
    "test_rows": 1152,
    "train_groups": 156,
    "train_rows": 3744,
    "validation_groups": 36,
    "validation_rows": 864
  },
  "task": "classification",
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
