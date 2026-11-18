# Step 25 Real Evidence Guide

## Purpose

Step 25 separates software demonstrations from scientific evidence. Bundled
synthetic packs remain useful for UI, performance and regression testing, but
they cannot pass the scientific release gate.

## Supported intake routes

1. Generic experimental activity CSV/TSV.
2. BindingDB TSV conversion.
3. PubChem BioAssay export conversion.
4. Live ChEMBL activity intake with ChEMBL molecule structures and UniProt
   target sequences.

No third-party bulk dataset is redistributed in this package. The operator is
responsible for checking current source terms, citations and permitted uses.

## Required activity fields

- canonical_smiles
- protein_sequence
- standard_value
- standard_units

Recommended fields include relation, endpoint/activity type, assay identifier,
source record identifier, publication identifier, UniProt accession, organism,
confidence score and replicate count.

## Censored measurements

Activity values are concentration measurements and are transformed to
pActivity. This reverses inequality direction:

- `< 10 nM` becomes `pActivity > 8`
- `> 100000 nM` becomes `pActivity < 4`

Rows crossing the chosen activity threshold stay `unknown`; they are not forced
into active or inactive classes.

## Evidence lifecycle

1. Import and standardize.
2. Register source release, licence and import run.
3. Generate canonical dataframe SHA-256.
4. Link every curated row to the evidence registry.
5. Review each row as accepted, rejected, edited or pending.
6. Run leakage audit on train versus independent test.
7. Run external benchmark.
8. Submit evidence manifest, external validation and leakage audit to the
   scientific release gate.

## Windows commands

- `IMPORT_REAL_EVIDENCE_WINDOWS.bat`
- `VERIFY_STEP25_WINDOWS.bat`

Direct examples:

```bat
.venv\Scripts\python.exe scripts\import_real_evidence.py bindingdb "C:\data\BindingDB_All.tsv" --release 2026
.venv\Scripts\python.exe scripts\import_real_evidence.py generic "C:\data\activities.csv" --release lab_v1
.venv\Scripts\python.exe scripts\import_real_evidence.py chembl --target CHEMBL203 --rows 250
```

## Release requirements

Default release policy requires:

- verified non-synthetic experimental data
- complete licence coverage
- complete accepted-review coverage
- minimum mean evidence-quality score
- evidence source registration
- exact model-dataset/evidence-manifest hash match
- independent external validation
- leakage-safe split evidence
- acceptable performance, invalid-row fraction and drift
