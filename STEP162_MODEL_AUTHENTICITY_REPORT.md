# BioIntel AI Step 162 — Authentic Models and Evidence Hardening

## Completed software-owned upgrade

- **80/80 scientific modules** carry the Step 162 authenticity contract.
- **5/5 real public-data benchmark models** were trained, packaged and verified.
- **23/23 synthetic legacy models** are marked demo-only, removed from default status and recorded in the authenticity registry.
- **14/14 official/public source contracts** are checksum-protected.
- **7 provider groups** currently have local checksum-verified public/reference assets.
- Every new benchmark package includes:
  - a non-synthetic public dataset snapshot;
  - dataset SHA-256;
  - deterministic train/calibration/untouched-holdout indices;
  - untouched holdout predictions;
  - cross-validation metrics;
  - calibration or conformal uncertainty diagnostics;
  - model artifact SHA-256;
  - machine-readable and Markdown model cards;
  - environment manifest;
  - complete file manifest.

## Real public-data model suite

1. Wisconsin Diagnostic Breast Cancer classification
2. UCI Wine recognition classification
3. Fisher Iris classification
4. UCI Optical Digits classification
5. Diabetes progression regression

These models verify the ML, provenance, calibration, reproducibility and governance pipeline. They are **not substitutes for DTI, protein design, pathology, sequencing, clinical or other domain-specific models**.

## Synthetic-model policy

Legacy synthetic DTI/ML artifacts remain available only for software demonstration and regression testing. They are not authentic evidence, are not scientific defaults and cannot pass an external-release gate.

## Remaining genuine external requirements

A module can reach real domain-release readiness only after it receives the appropriate combination of:

- a task-specific real training cohort;
- production-qualified reference databases;
- installed and version-qualified specialist engines/model weights;
- locked independent external validation;
- prospective or wet-lab confirmation where applicable;
- expert review and organization-specific regulatory validation.

No fake studies, customers, approvals, publications, laboratories or authority decisions were generated.
