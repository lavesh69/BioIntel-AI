# BioIntel AI Step209 / Windows V19.4 — Release Test Report

## Scope

Professional hardening of the non-protected Neuro/CNS, Bioinformatics, Discovery and Lab Analytics experience. The Windows V19.1 install/run repair architecture and the V19.2/V19.3 scientific workflows are retained.

## Implemented software capability

- Explicit choice between clearly labelled synthetic demo input and local upload; upload mode does not silently substitute demo data.
- Deterministic synthetic input bundles for all 81 non-protected target pages, including every one of the 41 Neuro/CNS modules.
- Curated module-relevant scientific website access through approved HTTPS hosts, privacy warnings and calm offline/unavailable states.
- Safe structured ZIP ingestion for multi-table microbiome, ADMET, protein-design and primer/CRISPR workflows, including traversal, duplicate-name, expansion and size checks.
- Complete downloadable result/provenance packages with tables, arrays, run metadata, input profile and scientific boundary.
- Error reference IDs and sanitized local diagnostics instead of raw upload/workflow tracebacks.
- Expanded calculated visuals for all 17 advanced Neuro workflows; each validated workflow provides at least two result-derived figures.
- Neuro portfolio coverage, readiness and input/output depth views.
- FastICA convergence warning handling and quieter invalid-SMILES parsing without hiding invalid-record status in results.

## Automated validation completed

- Combined current regression set: **230 passed**.
- Neuro/CNS backend regression: **117 passed**.
- Step209 focused hardening tests: **9 passed**.
- Advanced feature registry: **42/42 workflows executed from labelled demo payloads**.
- Neuro/CNS catalog: **41 modules registered**.
- Generated demo coverage: **81/81 non-protected target pages**.
- Scientific-resource mapping: **81/81 target pages and 41/41 Neuro modules**.
- Protected-module integrity: **17/17 recorded hashes unchanged**.
- Python source compilation: **completed without syntax errors** for `src/biointel`, `pages` and `scripts`.
- Windows install/run static contract: **24/24 passed**.
- Deep source-manifest gate on clean extraction: **11/11 passed**, **23,980 tracked hashes**, **0 bad hashes**.
- Final four-part package: **25,367 source files**, **0 missing**, **0 extra**, **0 duplicates**, **0 CRC errors**, **0 unsafe paths**.
- Clean extraction from a folder containing spaces: **passed**.

## Validation boundary

The build environment is Linux with Python 3.13 and does not provide Streamlit, so native Windows BAT execution and Streamlit AppTest could not be executed here. The delivered installer requires CPython 3.11.9 x64 and performs blocking native-Windows UI, API, worker, SQLite and Streamlit startup checks before activating the managed installation.

Synthetic/demo inputs are not patient data, clinical evidence, wet-lab validation or external scientific qualification. Website availability is not evidence quality and online content is never claimed when a provider is unavailable.

## Protected modules

The DTI Predictor, DTI Validation Evidence Center, LIMS/ELN/Sample Chain of Custody, Lab Instrument Import Center and Instrument Integration Hub were not redesigned, refactored or upgraded.
