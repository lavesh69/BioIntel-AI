# Steps 1–5 — Shortcomings Fixed

## Usability

- Added a guided Quick Start page and downloadable dataset templates.
- Fixed Streamlit training results disappearing on rerun before model saving.
- Added direct Windows scripts for UI, API and combined startup.
- Added dedicated pages for deployment, external databases and experiment history.
- Added cross-page handoff for retrieved UniProt sequences and ChEMBL SMILES.

## Reproducibility

- Added cleaned-dataset SHA-256 fingerprints.
- Added unique experiment IDs.
- Added versioned artifact format `5.0.0`.
- Added local SQLite experiment registry without raw sequence storage.
- Added automatic JSON metadata and Markdown model cards.
- Added training configuration and software versions to artifacts.

## Evaluation

- Preserved separate training, validation and final test sets.
- Threshold tuning remains validation-only.
- Added bootstrap confidence intervals.
- Added model-native global feature importance with non-causality warnings.
- Retained calibration and leakage-resistant group/scaffold splitting.

## Sequence analysis

- Added multi-record FASTA, IUPAC motifs and screened regex.
- Added restriction sites and cumulative GC skew.
- Improved ORF and alignment reporting.
- Added k-mer profiles.
- Added DNA oligo molecular-weight and melting-temperature estimates.

## DTI data and prediction

- Added activity-unit conversion and pActivity calculation.
- Added invalid-row, duplicate and conflict reports.
- Added stronger applicability checks and nearest training-drug similarity.
- Added trusted model-path, extension and size validation.
- Added model cards, experiment registry and batch row isolation.

## Integration and deployment

- Added official UniProt and ChEMBL REST clients with timeouts and safe failures.
- Added FastAPI endpoints; Step 8 later simplified them to no-login localhost-only access.
- Added Dockerfile, Docker Compose and deployment documentation.
- Added API batch limits and model-path traversal protection.

## Verification

- 52 automated tests passed.
- 14/14 Streamlit screens passed.
- Ruff and Black passed.
- Streamlit and FastAPI live health checks passed.
- A live schema-checked DTI API prediction passed.
