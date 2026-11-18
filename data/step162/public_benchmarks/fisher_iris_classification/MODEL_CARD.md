# Fisher Iris public benchmark

**Authenticity tier:** Public benchmark / immutable snapshot / reproducible holdout  
**Task:** classification  
**Dataset SHA-256:** `1c4da6110b845a828bf245faa15b02586a4b45ca0a79f01fe534ed65cf55d63e`  
**Artifact SHA-256:** `7b2e523c03fe981bad34db03767bbf32afa9a47a39f9068566546bba0c84320f`

## Intended use

Small multiclass pipeline and reproducibility benchmark only.

## Source

- Fisher Iris dataset distributed with scikit-learn
- https://scikit-learn.org/stable/modules/generated/sklearn.datasets.load_iris.html

## Untouched holdout metrics

- **accuracy:** 0.966667
- **balanced_accuracy:** 0.966667
- **f1_macro:** 0.966583
- **precision_macro:** 0.969697
- **recall_macro:** 0.966667
- **log_loss:** 0.155719
- **brier_score:** 0.0234402
- **expected_calibration_error:** 0.0884019
- **roc_auc_ovr_macro:** 1

## Limitations

Educational botanical dataset; not representative of high-dimensional biomedical deployment.

## Release boundary

The public dataset, immutable local snapshot, deterministic split, artifact hash, holdout predictions, calibration diagnostics and model card are verified. This is a public benchmark model, not an independently validated domain or clinical model. External release eligibility is therefore false.
