# Project Architecture

```mermaid
flowchart LR
    U[Streamlit UI] --> S[Sequence Modules]
    U --> C[Cheminformatics Modules]
    U --> Q[Data Quality]
    U --> T[Training Pipeline]
    U --> P[DTI Predictor]
    U --> R[Experiment Registry]
    U --> X[UniProt and ChEMBL]
    A[FastAPI] --> S
    A --> P
    T --> M[Versioned Model Artifact]
    M --> P
    T --> R
    T --> MC[Model Card]
    Q --> T
```

## Main package areas

- `biointel.sequence`: validation, parsing, statistics, ORFs, motifs,
  restriction sites, alignments, k-mers and oligo properties
- `biointel.chemistry`: SMILES, descriptors, fingerprints and rendering
- `biointel.dti`: drug/protein feature extraction and prediction
- `biointel.training`: splitting, evaluation, calibration, artifacts,
  explainability and experiment registry
- `biointel.integrations`: UniProt and ChEMBL clients
- `biointel.api`: FastAPI schemas and endpoints
- `biointel.reports`: PDF reports and model cards
