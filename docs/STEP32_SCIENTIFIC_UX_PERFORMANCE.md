# Step 32 — Scientific UX & Performance

Step 32 separates software completeness from scientific validation and upgrades the shared Streamlit experience across the BioIntel workspace.

## Scientific-data foundation

- Adds a licensed public biomedical reference dataset: UCI Breast Cancer Wisconsin (Diagnostic), bundled through scikit-learn and labelled CC BY 4.0.
- Adds a curated identifier-only reference panel for UniProt, NCBI Gene and RCSB PDB.
- Keeps public reference, demonstration/reference and release-eligible evidence as separate scopes.
- Creates `physical_data_assets` and foreign-key-enforced `dataset_asset_bindings` so logical dataset versions no longer imply unique physical files.
- Records scientific-scope limitations in `dataset_validation_issues` instead of showing an empty issue table.
- Creates a dedicated cross-database relationship registry with canonical resource nodes, validated edges and orphan detection.

## Interface and performance

- Searchable, typo-tolerant navigation with 14 canonical categories and 12 focused featured screens.
- Active-page category synchronization, favourites and recent work.
- Live database health instead of hard-coded healthy labels.
- Dark, light and system appearance options; font scaling and colour-vision palettes.
- Cached file/database reads and model resources with file-signature invalidation.
- Form-submit workflows for expensive analyses and visible processing status.
- Research-friendly metric cards, data tables, result summaries and export controls.
- Upgraded FASTQ, variant, primer/CRISPR, transcriptomics, protein, structure, ADMET, pathway, wet-lab, microbiome, multi-omics and phylogeny workspaces.

## Scientific boundary

The UCI dataset is real public reference data, but it is not an independent validation cohort for BioIntel's bundled DTI models. Bundled DTI experiments remain synthetic benchmarks. UniProt, NCBI Gene and RCSB entries in the public-reference catalogue are identifier-level records; sequence or structure payloads are not implied unless separately downloaded and registered.
