# Step219 Synthetic / Demo Data Mode

Release identifier: `15.6.0-Step219.0-WINDOWS-V20.2`

## Scope

Step219 adds a controlled, offline synthetic-data workspace for product demonstration, training, automated testing and pipeline verification. Synthetic records and every derived output remain clearly separated from real scientific data and cannot be promoted to clinical, regulatory, publication or scientifically validated evidence.

## Implemented capabilities

- Dedicated Synthetic Demo Data Workspace with a permanent warning banner, project creation, module/scenario selection, 12 control presets, small/medium/large sizing, explicit random seeds, advanced signal and quality controls, package export, reset, cancellation, expected-vs-observed comparison and restricted ground-truth view.
- Eighteen deterministic module generators: sequencing quality, alignment and mapping, differential expression, biomarker discovery, variant prioritization, pathway enrichment, multi-omics, single-cell, proteomics, metabolomics, microbiome, structural biology, drug-target discovery, experimental design, statistical analysis, literature discovery, hypothesis generation and laboratory validation.
- Reusable `SyntheticDatasetGenerator`, configuration, scenario, manifest, truth, validation and registry models with schema validation, resource limits, chunk checkpoints and explicit origin metadata.
- Separate synthetic project, dataset, run, recommendation, generation-job and audit tables plus a dedicated synthetic file-storage root.
- Production Step218.1 recommendation scoring, QC, evidence grading, explainability, alternatives, action plans, validation planning, what-if analysis, model consensus, persistence, history and comparison are reused for demo inputs.
- Row-level synthetic evidence origins and guards that block synthetic-to-real evidence promotion, validation, project merging and publication-ready status.
- Visible synthetic notices in JSON, CSV, evidence CSV, HTML, PDF, DOCX, XLSX, parameter configuration, audit report, reproducibility manifest and evidence-package ZIP exports.
- Controlled CLI at `python -m biointel.synthetic` and resource-limited `POST /api/v1/synthetic-datasets` endpoint requiring `demo_mode=true`.
- Thirty-six bundled lightweight Windows fixtures: baseline and known-failure packages for all 18 modules.

## Package contract

Every generated dataset ZIP contains:

- `synthetic_manifest.json`
- `README_SYNTHETIC_DATA.md`
- `generation_parameters.json`
- `expected_ground_truth.json`
- `expected_qc_findings.json`
- `expected_recommendations.json`

Generated tables use neutral `SYN-*` identifiers, preserve `data_origin=synthetic` and `is_synthetic=true`, and do not generate fake PMIDs, valid-looking fake DOIs, ClinicalTrials.gov identifiers, patient identifiers or clinical claims.

## Verification

- Step219 focused suite: 13/13 checks passed in the bundled offline verification environment.
- Step218 recommendation regression suite: 9/9 checks passed.
- Default large differential-expression fixture (500 samples x 5,000 features) generated successfully with the large-memory warning and chunk checkpoints.
- All 18 baseline and all 18 failure fixtures generated, passed CRC verification and contain unique ZIP paths.
- Synthetic recommendation exports were inspected across JSON, CSV, HTML, PDF, DOCX, XLSX and evidence ZIP formats for visible watermarks.
- Demo/evidence SQLite databases passed `PRAGMA integrity_check` after legacy demo citation placeholders were replaced with neutral synthetic labels.
- Streamlit 1.58 desktop and mobile browser flows passed: create project, generate dataset, run the production recommendation framework, compare expected/observed results and reveal ground truth only through developer/testing controls.
- Browser console reported no application errors.

## Use boundary

Synthetic data is allowed only for demonstration, testing and training. It is prohibited for scientific conclusions, clinical decisions, diagnosis, treatment, regulatory submission or publication claims.