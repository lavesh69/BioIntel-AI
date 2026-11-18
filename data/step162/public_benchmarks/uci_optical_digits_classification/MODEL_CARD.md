# UCI Optical Digits public benchmark

**Authenticity tier:** Public benchmark / immutable snapshot / reproducible holdout  
**Task:** classification  
**Dataset SHA-256:** `7e5e64cd662d533eeec739bb699bf718243fc2c2f6993db801f062cd0dae337d`  
**Artifact SHA-256:** `44321cb05da288dde27820dfd564598362b73d0042352026eeccec6f560b87b4`

## Intended use

Image-feature multiclass software and model-governance benchmark only.

## Source

- UCI Optical Recognition of Handwritten Digits via scikit-learn
- https://archive.ics.uci.edu/dataset/80/optical+recognition+of+handwritten+digits

## Untouched holdout metrics

- **accuracy:** 0.980556
- **balanced_accuracy:** 0.980626
- **f1_macro:** 0.980626
- **precision_macro:** 0.98099
- **recall_macro:** 0.980626
- **log_loss:** 0.0876755
- **brier_score:** 0.00371755
- **expected_calibration_error:** 0.025174
- **roc_auc_ovr_macro:** 0.999648

## Limitations

Not a biomedical image model and not a substitute for pathology or microscopy validation.

## Release boundary

The public dataset, immutable local snapshot, deterministic split, artifact hash, holdout predictions, calibration diagnostics and model card are verified. This is a public benchmark model, not an independently validated domain or clinical model. External release eligibility is therefore false.
