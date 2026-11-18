# Wisconsin Diagnostic Breast Cancer public benchmark

**Authenticity tier:** Public benchmark / immutable snapshot / reproducible holdout  
**Task:** classification  
**Dataset SHA-256:** `6ace0ad2c71bcd8214d6995d1d4ad5ebe89b8342387b6a021c7a80a0f8ecb555`  
**Artifact SHA-256:** `e1e26554146d8c9bd96f74a684647532990d6b55cbf153f1709271cbe7a3ac86`

## Intended use

Reproducible binary-classification, calibration and provenance benchmark only.

## Source

- UCI Wisconsin Diagnostic Breast Cancer via scikit-learn
- https://archive.ics.uci.edu/dataset/17/breast+cancer+wisconsin+diagnostic

## Untouched holdout metrics

- **accuracy:** 0.938596
- **balanced_accuracy:** 0.941468
- **f1_macro:** 0.934947
- **precision_macro:** 0.929952
- **recall_macro:** 0.941468
- **log_loss:** 0.104908
- **brier_score:** 0.0356178
- **expected_calibration_error:** 0.0359412
- **roc_auc:** 0.994048

## Limitations

Not a clinical diagnostic device and not externally validated for deployment at a healthcare site.

## Release boundary

The public dataset, immutable local snapshot, deterministic split, artifact hash, holdout predictions, calibration diagnostics and model card are verified. This is a public benchmark model, not an independently validated domain or clinical model. External release eligibility is therefore false.
