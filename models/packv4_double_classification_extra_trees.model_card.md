# BioIntel AI Model Card

## Model identity

- **Experiment ID:** `exp-20260704T080433+0000-be6c49c5`
- **Artifact format:** `7.0.0`
- **Model version:** `4.0.0-double-data`
- **Estimator:** `extra_trees`
- **Task:** `classification`
- **Trained at:** `2026-07-04T08:04:33+00:00`
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
- **Decision threshold:** `0.4749999999999999`
- **Bootstrap confidence intervals:**

```json
{
  "accuracy": {
    "bootstrap_samples": 30,
    "lower_95": 0.781171875,
    "upper_95": 0.8043046875
  },
  "balanced_accuracy": {
    "bootstrap_samples": 30,
    "lower_95": 0.781251756952382,
    "upper_95": 0.8043355550302499
  },
  "f1": {
    "bootstrap_samples": 30,
    "lower_95": 0.7812425231061944,
    "upper_95": 0.8049229974212657
  },
  "pr_auc": {
    "bootstrap_samples": 30,
    "lower_95": 0.8783363897023905,
    "upper_95": 0.8956622671860128
  },
  "roc_auc": {
    "bootstrap_samples": 30,
    "lower_95": 0.8724247657856901,
    "upper_95": 0.8877607081523674
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
  "score_quantile": 0.6582978069125451
}
```

### Validation metrics

- **accuracy:** 0.803333
- **balanced_accuracy:** 0.803335
- **precision:** 0.797303
- **recall:** 0.803397
- **specificity:** 0.803272
- **f1:** 0.800338
- **mcc:** 0.606601
- **roc_auc:** 0.884387
- **pr_auc:** 0.881146
- **log_loss:** 0.427391
- **brier_score:** 0.137853

### Final held-out test metrics

- **accuracy:** 0.790781
- **balanced_accuracy:** 0.79079
- **precision:** 0.793695
- **recall:** 0.789506
- **specificity:** 0.792073
- **f1:** 0.791595
- **mcc:** 0.581567
- **roc_auc:** 0.879535
- **pr_auc:** 0.886304
- **log_loss:** 0.432869
- **brier_score:** 0.141189
- **conformal_coverage:** 0.892031
- **average_prediction_set_size:** 1.23891
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
  "model_name": "extra_trees",
  "model_version": "4.0.0-double-data",
  "n_estimators": 160,
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
