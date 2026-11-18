# BioIntel AI Step201 - Neuro/CNS Completion Changelog

## Added

- Scientific Resource Binding Studio with local file profiling, SHA-256 identity, provider release, licence, commercial-use, schema and validation metadata.
- Specialist Engine Qualification Center covering HMMER, InterProScan, MNE-Python, NiBabel, pydicom, SimpleITK, Ensembl VEP, bcftools, PLINK 2, FreeSurfer, FSL and ANTs.
- Privacy & De-identification Guard with direct-identifier detection, column removal, salted pseudonymisation and deterministic date shifting.
- Study Design & Power Planner for two-group continuous, paired continuous and binary designs.
- Data Leakage & Cohort Split Auditor for duplicate subjects, subject/group overlap, outcome-like columns and near-perfect outcome correlation.
- Dataset Drift & Monitoring Center with PSI, KS, standardized mean shift, categorical total-variation distance and new-level detection.
- Multi-Site Reproducibility Analyzer with fixed/random effects, Cochran Q, tau-squared and I-squared.
- Professional PDF scientific report in the unified report workflow.
- Release Evidence Pack ZIP containing JSON, Markdown, PDF, resource/engine/privacy evidence and SHA-256 manifest.
- Background queue support for privacy scans, leakage audits, drift analysis and multi-site analysis.

## Fixed and hardened

- Step201 four-part extraction markers and critical-file checks added to installation and launch.
- PDF output is bounded to prevent pathological multi-thousand-page reports; complete raw results remain in JSON/HTML/evidence pack.
- User-bound resources are loaded into the provenance registry only when their local assets still exist and match their tracked identity.
- Resource binding refuses empty files, invalid identifiers, missing metadata and checksum mismatches.
- Specialist-engine detection never marks an installed engine as scientifically qualified.
- Privacy, leakage, drift and reproducibility results preserve explicit research/review boundaries.

## Scientific boundary

Step201 closes remaining software-side gaps. It cannot create provider licences, external cohorts, wet-lab evidence, clinical validation, regulatory approval or expert sign-off. Those gates remain fail-closed.
