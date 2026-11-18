# BioIntel AI Model Card

## Model identity

- **Experiment ID:** `exp-20260704T080535+0000-3ea5a3b9`
- **Artifact format:** `7.0.0`
- **Model version:** `4.0.0-double-data`
- **Estimator:** `sgd_logistic`
- **Task:** `classification`
- **Trained at:** `2026-07-04T08:05:35+00:00`
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
- **Decision threshold:** `0.4649999999999999`
- **Bootstrap confidence intervals:**

```json
{
  "accuracy": {
    "bootstrap_samples": 30,
    "lower_95": 0.5903125,
    "upper_95": 0.6113828125
  },
  "balanced_accuracy": {
    "bootstrap_samples": 30,
    "lower_95": 0.5905816617480214,
    "upper_95": 0.6112957265091195
  },
  "f1": {
    "bootstrap_samples": 30,
    "lower_95": 0.5819761177500798,
    "upper_95": 0.6049939930390694
  },
  "pr_auc": {
    "bootstrap_samples": 30,
    "lower_95": 0.6049924466438727,
    "upper_95": 0.6359058839967446
  },
  "roc_auc": {
    "bootstrap_samples": 30,
    "lower_95": 0.6257050752921348,
    "upper_95": 0.6454109430131267
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
  "score_quantile": 0.9990351544745225
}
```

### Validation metrics

- **accuracy:** 0.595417
- **balanced_accuracy:** 0.594821
- **precision:** 0.592229
- **recall:** 0.563057
- **specificity:** 0.626585
- **f1:** 0.577275
- **mcc:** 0.190037
- **roc_auc:** 0.630515
- **pr_auc:** 0.618677
- **log_loss:** 2.04487
- **brier_score:** 0.354486

### Final held-out test metrics

- **accuracy:** 0.600313
- **balanced_accuracy:** 0.600439
- **precision:** 0.607595
- **recall:** 0.581186
- **specificity:** 0.619692
- **f1:** 0.594097
- **mcc:** 0.201012
- **roc_auc:** 0.637797
- **pr_auc:** 0.621263
- **log_loss:** 2.23177
- **brier_score:** 0.352103
- **conformal_coverage:** 0.88125
- **average_prediction_set_size:** 1.63766
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
  "model_name": "sgd_logistic",
  "model_version": "4.0.0-double-data",
  "n_estimators": 1,
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
