# Diabetes progression public regression benchmark

**Authenticity tier:** Public benchmark / immutable snapshot / reproducible holdout  
**Task:** regression  
**Dataset SHA-256:** `234091ed70a373b59de7b6382b946e70416204645d615f4e6d92d816bc1b0fd0`  
**Artifact SHA-256:** `299feebfa0991e50fc8f949f2c9d603e1eca06f50c6d27cca782c9d7cc4a5572`

## Intended use

Reproducible regression, interval and residual-governance benchmark only.

## Source

- Diabetes progression dataset distributed with scikit-learn
- https://scikit-learn.org/stable/modules/generated/sklearn.datasets.load_diabetes.html

## Untouched holdout metrics

- **r2:** 0.462436
- **rmse:** 59.1803
- **mae:** 48.4664
- **pearson:** 0.691257
- **spearman:** 0.656976
- **conformal_coverage:** 0.88764
- **mean_prediction_interval_width:** 181.394

## Limitations

Not a patient-level clinical forecasting model and not validated for treatment decisions.

## Release boundary

The public dataset, immutable local snapshot, deterministic split, artifact hash, holdout predictions, calibration diagnostics and model card are verified. This is a public benchmark model, not an independently validated domain or clinical model. External release eligibility is therefore false.
