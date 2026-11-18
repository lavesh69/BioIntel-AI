# BioIntel AI — Milestone 5 Status

## Status

**Complete and verified**

## New Step 5 features

- Guided Quick Start page
- Classification and regression CSV templates
- UniProt FASTA lookup
- ChEMBL molecule and target lookup
- Cross-page sequence/SMILES handoff
- Dataset SHA-256 and experiment IDs
- SQLite experiment registry
- Automatic Markdown model cards
- Bootstrap 95% confidence intervals
- Global model-native feature importance
- Overlapping k-mer profiles
- DNA oligo molecular weight and melting-temperature estimates
- FastAPI health, model, sequence, alignment and DTI endpoints
- Optional API-key protection
- Dockerfile and Docker Compose
- Windows scripts for app, API and combined startup
- Training results preserved across Streamlit reruns

## Verification

- Python compilation: passed
- Pytest: **52 passed**
- Ruff: passed
- Black: passed
- Streamlit AppTest: **14/14 screens passed**
- Streamlit live health: **HTTP 200 — ok**
- FastAPI live health: **HTTP 200**
- FastAPI docs: **HTTP 200**
- Trusted model status endpoint: passed
- Schema-checked DTI prediction endpoint: passed
- Classification and regression demo artifacts regenerated as version `5.0.0`
- Model cards and experiment registry generated
- ZIP integrity and SHA-256 manifest generated

## Scientific limitation

The bundled dataset and models are synthetic demonstrations. Their metrics and
predictions have no biological, therapeutic or clinical validity. Real use
requires curated experimental data, consistent assays, realistic negatives,
independent validation and laboratory confirmation.
