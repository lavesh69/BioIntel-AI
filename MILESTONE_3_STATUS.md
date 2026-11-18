# BioIntel AI — Milestone 3 Status

## Scope

Milestone 3 adds genuine machine-learning training, evaluation, artifact persistence and prediction to the existing sequence-analysis and DTI feature-engineering application.

## Added

- Classification and regression training pipelines
- Logistic Regression, Ridge, Random Forest and HistGradientBoosting models
- Random-pair, drug-group and target-group splits
- Held-out metrics for both task types
- Versioned model artifacts containing estimator, feature schema, metadata and applicability statistics
- JSON metadata sidecars
- Strict feature count, hash and order validation
- Single drug–target prediction
- Batch prediction with row-level errors
- Basic training-distribution warning
- Model Training, DTI Predictor and Model Evaluation pages
- Synthetic 96-row demonstration dataset
- Bundled synthetic classification and regression demo models
- Scripts to regenerate demo data and retrain demo artifacts

## Verification performed

- `pytest -q`: **29 passed**
- `ruff check .`: **passed**
- `black --check .`: **passed**
- Python compilation: **passed**
- Both demo artifacts trained successfully
- Classification artifact saved, loaded and used for prediction
- Regression artifact saved, loaded and used for prediction
- Batch invalid-row isolation tested
- Feature-schema mismatch rejection tested

## Run

On Windows, run `INSTALL_WINDOWS.bat` once and then `RUN_APP_WINDOWS.bat`.

Manual command:

```powershell
streamlit run app.py
```

## Scientific boundary

The bundled demo data are synthetic and the demo predictions are not scientifically meaningful. A real model requires high-quality experimental data, controlled activity definitions, careful negative sampling, leakage-resistant evaluation and laboratory validation.
