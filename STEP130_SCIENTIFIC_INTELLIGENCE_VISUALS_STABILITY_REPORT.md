# Step 130 — Cross-Module Scientific Intelligence, Visual Review & Stability

## Release

- Product version: **13.0.0**
- Base preserved: **Step 129**
- Next-generation scientific modules integrated: **15/15**
- New central workspaces: **6**
- Existing baseline files removed: **0**
- Source-locked pages preserved byte-identically: **5/5**

## Added to every new biomedical module

Each of the fifteen Step 128/129 biomedical workspaces now includes a shared **Scientific intelligence** tab with:

1. Persistent multi-run comparison
2. Module-wide linked scientific selection
3. Scenario and threshold sensitivity simulation
4. Candidate-level annotation and review decisions
5. Cross-module evidence-board publishing
6. Auditable cross-module handoffs
7. Scientific story mode
8. SVG/PDF/DOCX/PPTX publication figure packages
9. Automated visual quality inspection
10. Persistent run, scenario and review registries

Selections made in compatible Plotly visuals publish a shared entity context. On the following rerun, compatible result tables and visual builders use that context, allowing a patient, sample, gene, variant, compound, isolate, construct or candidate selection to remain linked across the module.

## New central workspaces

- Scientific Visual Workspace Studio
- Cross-Module Evidence Board
- Scientific Scenario & Sensitivity Lab
- Validation Cohort Manager
- Visual Review & Approval Center
- Scientific Intelligence Hub

## Persistence and reproducibility

A new runtime-created SQLite registry supports:

- Run snapshots with parameters, summary, bounded preview and result hash
- Candidate review decisions
- Evidence-board items
- Cross-module handoffs
- Scenario runs
- Validation cohort manifests

The registry is created at runtime and is not pre-populated with fabricated research history. Run and scenario retention is bounded to 200 records per module to prevent uncontrolled local database growth.

## Scenario safety and performance

- Scenario analysis is bounded to the first **50,000 records**
- Run previews are bounded to **200 result rows**
- Evidence-board publishing is bounded to **50 items per run**
- Publication previews are bounded to **500 rows**
- Validation-cohort registration is capped at **250 MB**
- Existing interactive analysis cap remains **500,000 rows**
- Existing output cap remains **250,000 rows**
- Non-finite output values remain sanitised
- Memory errors and visual-rendering errors retain deterministic recovery paths

## Publication and figure workflow

The publication package includes:

- Vector SVG figure
- Interactive HTML report
- PDF report
- DOCX report
- PPTX report
- Result and advanced tables
- Scientific story
- Machine-readable evidence manifest
- Explicit scientific boundary

The package supports research communication and figure editing. It does not claim journal acceptance, external validation or regulatory approval.

## Completed validation

| Check | Result |
|---|---:|
| Step 130 verifier | **14/14 passed** |
| New Step 130 core tests | **5 passed** |
| Next-generation/UI regression group | **68 passed** |
| Release/compatibility regression group | **144 passed** |
| Native-format/stability regression group | **36 passed** |
| Completed targeted tests | **253 passed** |
| New and next-generation runtime pages | **22/22 passed** |
| Runtime page exceptions | **0** |
| Python source syntax | **931/931 passed** |
| SQLite databases | **36/36 healthy** |
| Database rows checked | **108,425** |
| Foreign-key issues | **0** |
| Full test collection | **1,030 tests collected** |
| Locked pages | **5/5 byte-identical** |
| Missing baseline files | **0** |

A combined all-target test command crossed the execution window after partial progress, so that incomplete combined run is not counted as a pass. The four completed non-overlapping validation groups above all finished successfully. The complete 1,030-test monolithic suite was collected but not claimed as fully executed.

## Error and bug fixes

- Corrected semantic-version compatibility regression test after the version moved from 12.9.0 to 13.0.0
- Updated visual-suite regression to accept linked filtered result, secondary and advanced tables
- Prevented linked-selection publishing failures from interrupting chart rendering
- Added safe fallbacks when entity identifiers, score columns, cohort fields or visual metadata are unavailable
- Added deterministic result hashes for run comparison
- Added retention limits for persistent run and scenario registries
- Added source/target validation for module handoffs
- Added bounded parsing and file-size protection to cohort registration
- Preserved all existing database files byte-identically after runtime testing
- Removed test-created databases, SQLite sidecars, bytecode and test-cache residue from the release tree

## Scientific boundary

This release improves local research decision support, visual review, reproducibility and workflow continuity. It does not fabricate proprietary foundation-model weights, licensed reference databases, independent clinical cohorts, wet-lab confirmation, journal acceptance, regulatory approval or real operating history. Missing external evidence remains an explicit blocker rather than a generated claim.
