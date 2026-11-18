# Milestone 24 — Scientific Trust, Performance and Production Foundation

Status: COMPLETE FOR THE LOCAL/OPTIONAL-DEPENDENCY SCOPE

Version: 2.4.0

## Delivered

### Scientific data foundation
- Real activity-data curation for BindingDB-style and PubChem BioAssay exports.
- Unit normalization to molar values and pActivity.
- Salt/fragment cleanup, canonical SMILES, InChIKey and tautomer handling.
- Protein target normalization, accession support and sequence checksums.
- Assay-quality scoring, row provenance, duplicate aggregation and conflict flags.
- Active/inactive/unknown separation so missing evidence is not treated as a negative.

### Leakage-safe validation
- Temporal split.
- Cold drug-and-target split.
- Protein sequence-cluster split.
- Dataset bias reporting, subgroup evaluation and label-noise detection.
- Prospective prediction freeze/outcome registry.
- Formal scientific release gate that blocks synthetic/demo models from scientific release.

### Faster prediction and batch processing
- Unique drug/protein feature extraction.
- Parallel feature calculation.
- Persistent compressed SQLite feature cache.
- Vectorized estimator calls instead of row-by-row inference.
- Transactional SQLite checkpoints plus CSV/Parquet support.
- Resumable batch jobs and persistent local job queue.
- Model preload/warm-up support.
- Streaming large CSV/TSV/Parquet datasets.
- Performance qualification report and UI.

### Model operations
- Weighted ensemble artifact builder.
- Champion–challenger comparison and controlled promotion.
- Active-learning candidate selection.
- Group-specific decision-threshold calibration.
- Model-native local feature contribution diagnostics.
- Optional ONNX export and optional capability detection for Optuna, SHAP, GNNs, protein language models, Parquet and PostgreSQL.

### API and security
- Optional API-key mode while retaining local no-login mode.
- Request-size limits.
- Per-client rate limiting.
- Trusted-host policy.
- Security response headers.
- Scientific curation, release gate, capabilities and local job endpoints.

### UI
- Scientific Data Curation screen.
- Performance & Job Center screen.
- Scientific Release Gate screen.
- Training screen support for temporal, cold-pair and sequence-cluster splits.
- Batch screen support for workers, persistent cache and transactional resume.

## Verification evidence
- 27/27 final critical scientific/performance regression tests passed.
- - 23/23 trusted model artifacts loaded and predicted.
- 53/53 diagnostics passed.
- 7/7 SQLite databases passed integrity checks.
- Black and Ruff checks passed for modified code.
- Cold-cache qualification: approximately 699 rows/second on the verification environment.
- Warm-cache qualification: approximately 773 rows/second on the verification environment.

## Scientific boundary
The bundled trained models remain deterministic synthetic software benchmarks. Step 24 supplies the curation, validation and release-control machinery needed for real evidence, but it does not claim that synthetic models are experimentally or clinically validated. Real ChEMBL/BindingDB/PubChem BioAssay records must be imported under their applicable licenses, curated, retrained and independently validated before scientific use.

## Optional heavy capabilities
GNN, molecular/protein transformers, GPU training, Optuna, SHAP, ONNX Runtime and PostgreSQL are dependency-gated. They are not silently installed because their correct CPU/GPU build, model licenses, storage requirements and deployment configuration differ between systems.
