# Step 24 — Shortcomings Fixed

## Fixed now
- Row-by-row batch inference bottleneck.
- Repeated molecule/protein feature computation.
- Full CSV rewrite checkpoints.
- Weak crash recovery for long prediction jobs.
- Lack of real-assay unit normalization and compound standardization.
- Missing duplicate/conflict and unknown-label handling.
- Missing temporal, cold-pair and protein-cluster validation splits.
- Missing scientific release policy for synthetic/demo models.
- Missing local persistent job state.
- Missing optional API authentication, request limits and rate control.
- Missing model preloading, streaming I/O and performance qualification.
- Missing active-learning, label-noise, prospective-validation and subgroup tools.
- Missing ensemble and champion–challenger operations.

## Correctly left dependency-gated
- GNN and transformer training.
- ESM/ProtT5 model downloads.
- GPU-specific PyTorch installation.
- ONNX Runtime acceleration.
- Optuna and SHAP.
- PostgreSQL production migration.

These are exposed through capability checks and optional requirements rather than being falsely represented as bundled working models.
