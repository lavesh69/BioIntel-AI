# BioIntel AI Model Card

## Model identity

- **Experiment ID:** `exp-20260704T040150+0000-0dd6b084`
- **Artifact format:** `7.0.0`
- **Model version:** `1.0.0-demo`
- **Estimator:** `random_forest`
- **Task:** `classification`
- **Trained at:** `2026-07-04T04:01:50+00:00`
- **Synthetic demonstration:** `Yes`

## Intended use

Educational and research-oriented Drug–Target Interaction classification or
pActivity regression. This artifact is not intended for clinical diagnosis,
treatment selection, safety assessment, regulatory decisions or proof of
physical binding.

## Dataset provenance

- **Dataset:** `synthetic_dti_demo`
- **Dataset version:** `1.0`
- **Dataset SHA-256:** `a3112f390dc5bacb62092db9a0f66a5cd2084543638b93e6d4df2234fbcb4d64`
- **Activity type:** `Not specified`
- **Training rows:** `57`
- **Validation rows:** `15`
- **Final test rows:** `24`

The hash identifies the cleaned dataframe used by this run without embedding
the raw sequences or molecule records in this card.

## Evaluation design

- **Split strategy:** `random_pair`
- **Threshold strategy:** `fixed`
- **Probability calibration:** `none`
- **Decision threshold:** `0.5`
- **Bootstrap confidence intervals:**

```json
{
  "accuracy": {
    "bootstrap_samples": 200,
    "lower_95": 0.665625,
    "upper_95": 0.9166666666666666
  },
  "balanced_accuracy": {
    "bootstrap_samples": 200,
    "lower_95": 0.6572979797979798,
    "upper_95": 0.9333333333333333
  },
  "f1": {
    "bootstrap_samples": 200,
    "lower_95": 0.6,
    "upper_95": 0.9166666666666666
  },
  "pr_auc": {
    "bootstrap_samples": 200,
    "lower_95": 0.3382176157176157,
    "upper_95": 0.7951127891468801
  },
  "roc_auc": {
    "bootstrap_samples": 200,
    "lower_95": 0.44055944055944063,
    "upper_95": 0.8751620370370371
  }
}
```

### Conformal uncertainty calibration

```json
{
  "alpha": 0.1,
  "calibration_rows": 15,
  "coverage_target": 0.9,
  "method": "split_conformal_classification",
  "score_quantile": 0.8763575245701319
}
```

### Validation metrics

- **accuracy:** 0.4
- **balanced_accuracy:** 0.416667
- **precision:** 0.333333
- **recall:** 0.5
- **specificity:** 0.333333
- **f1:** 0.4
- **mcc:** -0.166667
- **roc_auc:** 0.462963
- **pr_auc:** 0.424903
- **log_loss:** 0.767991
- **brier_score:** 0.285875

### Final held-out test metrics

- **accuracy:** 0.791667
- **balanced_accuracy:** 0.807143
- **precision:** 0.692308
- **recall:** 0.9
- **specificity:** 0.714286
- **f1:** 0.782609
- **mcc:** 0.607808
- **roc_auc:** 0.664286
- **pr_auc:** 0.511734
- **log_loss:** 0.660225
- **brier_score:** 0.230469
- **conformal_coverage:** 1
- **average_prediction_set_size:** 1.95833
- **empty_prediction_set_fraction:** 0

## Feature schema

- **Feature count:** `295`
- **Feature hash:** `b989f240b3066eaf54f14201f2e41204d6a83686e606057facc2d97488c377f6`
- **Morgan radius:** `2`
- **Morgan bits:** `256`
- **Use chirality:** `True`
- **Dipeptide features:** `False`

## Training configuration

```json
{
  "activity_type": null,
  "bootstrap_iterations": 200,
  "calibration_method": "none",
  "conformal_alpha": 0.1,
  "dataset_name": "synthetic_dti_demo",
  "dataset_version": "1.0",
  "decision_threshold": 0.5,
  "fingerprint_bits": 256,
  "fingerprint_radius": 2,
  "include_dipeptides": false,
  "model_name": "random_forest",
  "model_version": "1.0.0-demo",
  "n_estimators": 80,
  "random_seed": 42,
  "source_description": "User-provided or local dataset",
  "split_strategy": "random_pair",
  "synthetic_demo": true,
  "task_type": "classification",
  "test_fraction": 0.25,
  "threshold_strategy": "fixed",
  "use_chirality": true,
  "validation_fraction": 0.15
}
```

## Data-quality summary

```json
{
  "class_distribution": {
    "0": 57,
    "1": 39
  },
  "conflicting_pair_groups": 0,
  "exact_duplicate_rows": 0,
  "invalid_rows": 0,
  "original_rows": 96,
  "p_activity_max": null,
  "p_activity_min": null,
  "split_summary": {
    "strategy": "random_pair",
    "test_rows": 24,
    "train_rows": 57,
    "validation_rows": 15
  },
  "task": "classification",
  "valid_after_cleaning": 96
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
