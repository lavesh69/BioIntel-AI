# UCI Wine recognition public benchmark

**Authenticity tier:** Public benchmark / immutable snapshot / reproducible holdout  
**Task:** classification  
**Dataset SHA-256:** `20d00cffdb11ca25b0c3282da98607f0eb42df2c6657a63492b7b836e44cd66e`  
**Artifact SHA-256:** `759b1165bd1d77cad2a85e78213341c3fe98bd34aed82dbaccd5f44dc1f8596c`

## Intended use

Reproducible multiclass scientific-ML benchmark only.

## Source

- UCI Wine recognition dataset via scikit-learn
- https://archive.ics.uci.edu/dataset/109/wine

## Untouched holdout metrics

- **accuracy:** 1
- **balanced_accuracy:** 1
- **f1_macro:** 1
- **precision_macro:** 1
- **recall_macro:** 1
- **log_loss:** 0.0697368
- **brier_score:** 0.00931698
- **expected_calibration_error:** 0.0600684
- **roc_auc_ovr_macro:** 1

## Limitations

Chemical-class benchmark; it is not a drug, toxicity or clinical prediction model.

## Release boundary

The public dataset, immutable local snapshot, deterministic split, artifact hash, holdout predictions, calibration diagnostics and model card are verified. This is a public benchmark model, not an independently validated domain or clinical model. External release eligibility is therefore false.
