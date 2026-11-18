# BioIntel AI Step 68 — Runtime Repair & Structure Visualization Report

## Scope

Step 68 is based on the verified Step 67 Theme & Font Excellence build. It addresses runtime failures shown in user screenshots and performs a broader stability pass across chemistry, Discovery, structural bioinformatics, molecular design, page identity, database health and end-user error handling.

## Screenshot-reproduced defects fixed

### Appearance Studio widget-state crash

The Appearance Studio applied presets and accessibility payloads by mutating widget-backed `st.session_state` keys after those widgets had already been instantiated. Current Streamlit versions reject that operation with `StreamlitAPIException`.

Step 68 introduces transaction-safe preference handling:

- Apply, Cancel, Undo, preset import and profile actions queue a transaction.
- The queued transaction is consumed before widgets are created on the following rerun.
- Non-appearance preferences are preserved through dataclass replacement.
- Theme preview and saved state remain separate.
- Applying accessibility settings no longer mutates active widget keys illegally.

### DTI Predictor RDKit Boost.Python error

The DTI page passed a SMILES string directly to RDKit descriptor functions that require an RDKit molecule. A second latent issue expected an object with `.descriptors` even though the descriptor service returns a dictionary.

Step 68 fixes both paths:

- `calculate_descriptors()` now accepts either SMILES or an RDKit molecule.
- Invalid SMILES produce an actionable `ValueError` instead of a Boost.Python signature failure.
- Unsupported object types produce a clear `TypeError`.
- DTI uses the canonical SMILES returned by prediction.
- Descriptor results are consumed as a dictionary.
- Descriptor-panel failure cannot discard a completed interaction prediction.
- Single and batch workflows are regression-tested.
- Batch processing supports up to 5,000 rows and uses available CPU workers.

### Primer design apparent freeze

The default thermodynamic search evaluated a very large candidate-pair space before the interface received useful completion feedback.

Step 68 adds:

- Fast, Balanced and Exhaustive search modes.
- Early candidate-length pruning.
- Bounded candidate combinations in Fast and Balanced modes.
- Heap-limited top-pair retention.
- Progress callbacks for forward search, reverse search and pair ranking.
- Input validation and large-template guidance.

On the bundled 1,203-base template:

- Fast: 0.8958 seconds
- Balanced: 1.8011 seconds
- Exhaustive: 10.3672 seconds
- Balanced speed-up versus Exhaustive: 5.76×

Balanced remains the default and returns 100 ranked pairs in the benchmark.

### Incorrect shell and breadcrumb context

Some child pages rendered as `Start / Home` because page detection trusted the `__main__` module before checking the live page frame.

Step 68 prioritizes exact `pages/` frame matches, then stack inspection, and uses `__main__` only as the final fallback. DTI, Primer/CRISPR and Structural Bioinformatics now report their real title and category.

### Database-health count mismatch

The global shell reported 20/20 databases while the release contains 22 active databases. Discovery and Lab Analytics registries live under `data/`, while the original health discovery only scanned `reports/`.

Step 68 includes both registries and dynamically discovers future SQLite databases under both locations. The shell and health service now report 22/22.

### End-user stack-path disclosure

Uncaught errors displayed local Windows paths and internal stack details in the UI. The Streamlit configuration now uses `showErrorDetails = "none"`. Detailed failures remain available in logs without exposing local paths to normal users.

## Structural Bioinformatics upgrade

A new reusable visualization service was added in `src/biointel/structural/visualization.py`.

### Larger and controllable molecular view

- Viewer height: 600–1,080 px; default 840 px
- Perspective or orthographic camera
- Atom size and opacity controls
- Chain and atom-group visibility controls
- Backbone line toggle
- Camera state preserved across reruns
- Self-contained interactive HTML export
- Ångström-labelled axes and detailed atom/residue hover text

### View presets

- Backbone + ligands
- All selected atoms
- Ligand focus
- C-alpha trace

### Large-structure handling

- Display budget from 2,000 to 20,000 atoms
- Ligands and C-alpha atoms preserved during sampling
- Total, selected, displayed, ligand and protein atom metrics
- Explicit sampling indicator
- Cached structure parsing and analysis

### Residue network visualization

- Interactive residue-contact graph
- Degree-scaled node size
- Network colour scale
- Configurable graph height and node limit
- Deterministic layout

### Tab usability

Long tab labels were shortened to prevent horizontal truncation:

`3D viewer`, `Summary`, `Contacts`, `Quality`, `Ramachandran`, `SASA`, `Interfaces`, `Network`, `Pockets`, and `PDB/mmCIF`.

## Additional reliability work

- DTI renders the canonical molecular structure after prediction.
- Batch errors identify the affected compound rows.
- Structure failures are converted into user-facing recovery messages.
- Structure figure generation benchmark: 0.2126 seconds for the bundled reference structure.
- Cached structural option reruns avoid repeated full parsing.
- Product version aligned to 6.8.0 across Python, Android, iOS, Electron/Windows, Docker, Helm and Terraform.

## Verification

- Ruff repository scan: passed
- Python compilation: passed
- Step 68 screenshot-regression tests: 9/9 passed
- Focused and compatibility regressions: 171 passed across 16 files
- Representative Streamlit pages: 15/15 passed
- API workflows: 9/9 passed
- SQLite databases: 22/22 healthy
- Database rows checked: 107,189
- Foreign-key violations: 0
- Secret scan: 1,194 files, 0 findings
- Store internal failures: 0

## Honest boundary

A single monolithic historical test run can exceed the bounded execution window because some third-party Streamlit and SQLite test processes remain alive after completing their assertions. Therefore Step 68 does not claim a complete historical-suite pass. Release evidence is based on isolated focused/regression tests, interactive page checks, API cases, repository lint and compilation, database integrity, security scanning and deterministic package verification.
