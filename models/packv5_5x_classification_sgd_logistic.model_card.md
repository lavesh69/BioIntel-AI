# BioIntel AI Model Card

## Model identity

- **Experiment ID:** `exp-20260704T090110+0000-b8f14df7`
- **Artifact format:** `7.0.0`
- **Model version:** `5.0.0-full-data`
- **Estimator:** `sgd_logistic`
- **Task:** `classification`
- **Trained at:** `2026-07-04T09:01:10+00:00`
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

- **Split strategy:** `drug_group`
- **Threshold strategy:** `optimize_balanced`
- **Probability calibration:** `none`
- **Decision threshold:** `0.5349999999999999`
- **Bootstrap confidence intervals:**

```json
{
  "accuracy": {
    "bootstrap_samples": 25,
    "lower_95": 0.6468375,
    "upper_95": 0.65739375
  },
  "balanced_accuracy": {
    "bootstrap_samples": 25,
    "lower_95": 0.6468824962264103,
    "upper_95": 0.6568403028134919
  },
  "f1": {
    "bootstrap_samples": 25,
    "lower_95": 0.6232246878951989,
    "upper_95": 0.6340520122158513
  },
  "pr_auc": {
    "bootstrap_samples": 25,
    "lower_95": 0.6772375884089324,
    "upper_95": 0.6888059324170119
  },
  "roc_auc": {
    "bootstrap_samples": 25,
    "lower_95": 0.6956395029033442,
    "upper_95": 0.704863179694271
  }
}
```

### Conformal uncertainty calibration

```json
{
  "alpha": 0.1,
  "calibration_rows": 24000,
  "coverage_target": 0.9,
  "method": "split_conformal_classification",
  "score_quantile": 0.7364298057530094
}
```

### Validation metrics

- **accuracy:** 0.651417
- **balanced_accuracy:** 0.650903
- **precision:** 0.661051
- **recall:** 0.605225
- **specificity:** 0.69658
- **f1:** 0.631908
- **mcc:** 0.30315
- **roc_auc:** 0.698966
- **pr_auc:** 0.68155
- **log_loss:** 0.642298
- **brier_score:** 0.223536

### Final held-out test metrics

- **accuracy:** 0.651875
- **balanced_accuracy:** 0.651643
- **precision:** 0.670167
- **recall:** 0.592709
- **specificity:** 0.710577
- **f1:** 0.629062
- **mcc:** 0.305456
- **roc_auc:** 0.699761
- **pr_auc:** 0.683044
- **log_loss:** 0.641773
- **brier_score:** 0.223215
- **conformal_coverage:** 0.89875
- **average_prediction_set_size:** 1.60981
- **empty_prediction_set_fraction:** 0

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
  "model_name": "sgd_logistic",
  "model_version": "5.0.0-full-data",
  "n_estimators": 1,
  "random_seed": 20260719,
  "source_description": "BioIntel deterministic synthetic 5X Ultra 160,000-pair DTI benchmark",
  "split_strategy": "drug_group",
  "synthetic_demo": true,
  "task_type": "classification",
  "test_fraction": 0.2,
  "threshold_strategy": "optimize_balanced",
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
  "class_distribution": {
    "0": 80003,
    "1": 79997
  },
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
  "p_activity_max": null,
  "p_activity_min": null,
  "split_summary": {
    "group_overlap": false,
    "strategy": "drug_group",
    "test_groups": 200,
    "test_rows": 32000,
    "train_groups": 650,
    "train_rows": 104000,
    "validation_groups": 150,
    "validation_rows": 24000
  },
  "task": "classification",
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
