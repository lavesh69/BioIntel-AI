# BioIntel AI Step 136 — Non-AI Visual Peak Expansion

## Requested scope

The visual expansion is intentionally applied to every registered module except the three excluded families:

- AI Lab
- Operations
- Governance

Those excluded families were not patched by this visual-expansion pass.

## Coverage

- Registered modules reviewed: 198
- Excluded modules left unchanged: 63
- Targeted modules: 135
- Legacy pages receiving the new visual extension: 104
- Next-generation pages retaining their native data-linked visual workbench: 31
- Visual families: 25
- Visual definitions per targeted module: 5
- Total module-to-visual assignments: 675

## Targeted categories

- Start: 18 modules
- Bioinformatics: 39 modules
- Discovery: 18 modules
- Data: 18 modules
- Intelligence: 17 modules
- Lab Analytics: 15 modules
- Clinical Research: 6 modules
- Research Planning: 2 modules
- Settings: 2 modules

## Main implementation

A new shared module was added:

```text
src/biointel/ui/domain_visual_peak.py
```

It provides:

- Domain-aware module classification
- Five scientific visual layers per targeted module
- Current-session data discovery when compatible results are available
- Clearly labelled deterministic previews when no run data is available
- One-chart-at-a-time rendering to protect desktop responsiveness
- Bounded record handling capped at 5,000 plotted rows
- Safe error containment so a chart cannot crash the scientific page
- Visual catalogue with scientific purpose and method descriptions
- Data download and provenance support through the existing scientific chart card

## Visual families

The shared system includes specialist families for:

- Home and workspace dashboards
- Sequence analysis
- FASTQ quality control
- Variant interpretation
- Transcriptomics and multi-omics
- Protein and proteomics
- Phylogeny and pathogen genomics
- Single-cell analysis
- Cancer genomics
- Drug discovery
- DTI prediction
- Structural bioinformatics
- Pathway and network analysis
- Laboratory assays
- Microbiome and metagenomics
- Bioprocess analytics
- Data quality and lineage
- Document and OCR workflows
- Biomedical knowledge and evidence
- Appearance, accessibility and privacy
- Clinical research
- Therapy and translational workflows
- Experimental design and research planning
- Spatial biology and pathology
- Generic scientific fallback views

## Performance and stability controls

- Only the selected visual is rendered.
- Large tables are deterministically bounded.
- Duplicate columns and non-finite values are normalised before plotting.
- Plot failures produce a stable `VIS-...` recovery identifier rather than a page crash.
- Preview visuals are explicitly described as previews and never represented as experimental or clinical validation.
- Next-generation modules keep their existing native result-linked visual workbench instead of receiving a duplicate extension.

## Verification completed

- New targeted regression tests: 5/5 passed
- Visual-family render checks: 125/125 passed
- Targeted module coverage: 135/135
- Legacy visual-extension markers: 104/104
- Next-generation native visual pages: 31/31
- Excluded-category visual-extension markers: 0
- Python files compiled: 974/974
- SQLite databases healthy: 40/40
- Foreign-key violations: 0
- Database rows inspected: 108,493

## Validation boundary

The current environment does not contain Streamlit, so live browser screenshot certification could not be executed here. Source compilation, figure generation, module coverage, database integrity and packaging checks are completed. Preview graphics are UI demonstrations until a module produces compatible run data.
