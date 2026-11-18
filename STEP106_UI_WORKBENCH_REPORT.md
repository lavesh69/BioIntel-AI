# BioIntel AI Step 106 · Scientific Workbench UI and Workflow Optimization

- Product version: **10.6.0**
- Upload transport limit: **1 GB per file**
- Interactive processing threshold: **100 MB**
- Scientific workbenches refactored: **35**
- Platform-service pages refined: **15**
- Highest-risk legacy workspaces restructured: **3**

## What was repaired

### Module hierarchy and visual density

- Replaced repeated full-page scientific heroes with a compact workbench header in the 35 expansion modules.
- Limited visible chips and moved evidence boundaries into an expandable, persistent notice.
- Added a final workbench stylesheet so uploader, tabs, headers and disabled states no longer depend on conflicting theme-rule order.
- Supported-format lists are grouped by Tables, Genomics, Single-cell, Structures, Mass spectrometry and Images instead of one clipped caption.

### Upload and data readiness

- Upload mode is the default in the 35 shared-renderer scientific modules.
- Demo-only controls and upload-only controls are conditionally rendered instead of displayed as dead disabled widgets.
- Required fields, missing values, duplicate rows and parsing status are shown in a dedicated readiness panel.
- Missing required fields can be mapped to uploaded columns without editing the source file.
- The application transport limit is 1 GB per file. Up to 100 MB can be analysed interactively; larger files are staged to protected local storage and submitted to a persistent background inspection job.
- Large-file inspection streams SHA-256 calculation and reads only a bounded sample, avoiding a full 1 GB in-memory copy.

### Analysis execution and performance

- Analysis is no longer executed independently in hidden Analysis, Results and Export tabs.
- Each module has one explicit **Run analysis** action.
- Results are cached in session state and reused by visualisation and export tabs.
- Changing input data or parameters marks the result outdated until the operator reruns it.
- Advanced category and numeric filters are applied before analysis and included in the run signature.

### Scientific result presentation

Domain-aware views now include spatial maps, microscopy phenotype plots, docking pose comparisons, GWAS Manhattan-style views, single-cell trajectories, bioprocess timelines, antibody developability plots, guide-safety views, viral-frequency views and other module-relevant charts.

Result tables provide search/filter support, row selection, selected-row export and complete CSV export. Extra output tables are placed behind one selector rather than a long page of download buttons.

### Export and reproducibility

Each refactored scientific module provides:

- one complete ZIP evidence package;
- primary results CSV;
- JSON evidence manifest;
- grouped or advanced result tables in a collapsed download section;
- explicit completion time, parameters, input profile and scientific boundary.

### Navigation and overloaded legacy pages

- Large navigation categories receive focus-area grouping.
- Overlapping platform tools were given distinct product-facing names.
- Internal Step-number branding was removed from the two expansion hubs.
- Metagenomics results were reduced from 13 horizontal result tabs to five workflow stages with conditional subviews.
- Discovery Command Center was reduced from eight horizontal workspace tabs to five stages with conditional subviews.
- Dataset Registry’s six nested detail tabs were replaced by one conditional detail selector.

### Windows startup stability retained

The Step 105 Windows PID repair remains included. Windows process liveness uses a non-destructive process handle instead of `os.kill(pid, 0)`, and stale worker state is removed before restart.

## Verification

- **69/69** focused release and regression tests passed.
- **7/7** Step 106-specific UI architecture tests passed.
- **52/52** expansion/platform pages default-loaded with zero captured exceptions or UI errors.
- **35/35** scientific demonstration workflows completed through the new Run analysis path.
- Home, Dataset Registry, Metagenomics and Discovery Command Center default-load tests: **4/4 passed**.
- Source/build self-test: **7/7 passed**.
- Python compilation: **passed**.
- Large-file staging and worker completion probe: **passed**.

`ruff` was not installed in the build environment, so this report does not make a lint-pass claim.

## Scientific and operational boundary

The UI and workflow layer can be verified locally. Genuine MACS2, Vina, GROMACS, Cellpose, NetMHC, clinical interpretation, current provider databases, independent wet-lab validation and regulated operating evidence remain external requirements. The software continues to label heuristic or local screening outputs separately from those specialist results.
