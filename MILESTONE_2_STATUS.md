# BioIntel AI — Milestone 2 Status

## Scope

Milestone 2 extends the working sequence-analysis project with cheminformatics and reproducible Drug–Target Interaction feature engineering. It deliberately does **not** generate interaction probabilities.

## Added

- RDKit SMILES parsing, sanitization and canonicalization
- 2D molecule rendering as PNG
- Physicochemical descriptors and Lipinski-rule summary
- Configurable Morgan fingerprints
- Tanimoto molecular similarity comparison
- Fixed-order drug descriptor and fingerprint features
- Fixed-order protein basic and amino-acid-composition features
- Optional 400 dipeptide-composition features
- Combined drug–target feature schema with SHA-256 feature-order hash
- Classification and regression DTI CSV validation
- Downloadable feature vectors, schema JSON and cleaned datasets
- Synthetic dataset template clearly marked for demonstration
- Two new Streamlit pages and ten additional unit tests

## Verification performed

- `pytest -q`: **23 passed**
- `ruff check .`: **passed**
- `black --check .`: **passed**
- Python compile check: **passed**
- Streamlit page smoke tests: **app and all four pages passed**
- Streamlit health endpoint: **OK**

## Run

On Windows, run `INSTALL_WINDOWS.bat` once, then `RUN_APP_WINDOWS.bat`.

Manual command:

```powershell
streamlit run app.py
```

## Scientific boundary

This milestone creates model-ready inputs for a later trained model. It does not claim physical binding, biological activity, safety, efficacy or regulatory approval. Synthetic demonstration data must not be used to report meaningful scientific performance.
