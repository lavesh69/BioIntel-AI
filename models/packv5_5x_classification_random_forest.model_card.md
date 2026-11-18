# BioIntel AI Model Card

## Model identity

- **Experiment ID:** `exp-20260704T090904+0000-aa17b1a9`
- **Artifact format:** `7.0.0`
- **Model version:** `5.0.0-full-data`
- **Estimator:** `random_forest`
- **Task:** `classification`
- **Trained at:** `2026-07-04T09:09:04+00:00`
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
- **Decision threshold:** `0.4799999999999999`
- **Bootstrap confidence intervals:**

```json
{
  "accuracy": {
    "bootstrap_samples": 25,
    "lower_95": 0.8164375,
    "upper_95": 0.826575
  },
  "balanced_accuracy": {
    "bootstrap_samples": 25,
    "lower_95": 0.8164930842571105,
    "upper_95": 0.8267731076196327
  },
  "f1": {
    "bootstrap_samples": 25,
    "lower_95": 0.8193324900387359,
    "upper_95": 0.8288860645525366
  },
  "pr_auc": {
    "bootstrap_samples": 25,
    "lower_95": 0.9028562448283435,
    "upper_95": 0.9091206933968221
  },
  "roc_auc": {
    "bootstrap_samples": 25,
    "lower_95": 0.9040097126900128,
    "upper_95": 0.9106767935488811
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
  "score_quantile": 0.6387963245358738
}
```

### Validation metrics

- **accuracy:** 0.818
- **balanced_accuracy:** 0.818182
- **precision:** 0.804682
- **recall:** 0.834387
- **specificity:** 0.801978
- **f1:** 0.819265
- **mcc:** 0.636527
- **roc_auc:** 0.904055
- **pr_auc:** 0.901085
- **log_loss:** 0.394739
- **brier_score:** 0.125561

### Final held-out test metrics

- **accuracy:** 0.821281
- **balanced_accuracy:** 0.821349
- **precision:** 0.809411
- **recall:** 0.838615
- **specificity:** 0.804084
- **f1:** 0.823754
- **mcc:** 0.643023
- **roc_auc:** 0.907296
- **pr_auc:** 0.90541
- **log_loss:** 0.387326
- **brier_score:** 0.123324
- **conformal_coverage:** 0.905062
- **average_prediction_set_size:** 1.20016
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
  "model_name": "random_forest",
  "model_version": "5.0.0-full-data",
  "n_estimators": 20,
  "random_seed": 20260719,
  "source_description": "BioIntel deterministic synthetic 5X Ultra 160,000-pair DTI benchmark",
  "split_strategy": "drug_group",
  "synthetic_demo": true,
  "task_type": "classification",
  "test_fraction": 0.2,
  "threshold_strategy": "optimize_balanced",
  "tree_max_depth": 18,
  "tree_max_features": "sqrt",
  "tree_max_samples": 0.6,
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
