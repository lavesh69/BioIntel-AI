# BioIntel AI Step 53 — Critical Functional Fixes and Reliability Upgrade

## Release intent

This release repairs the internally verifiable functional and engineering issues found during the Step 52 project audit. No existing biotechnology project, provider integration, database, model, page, or dataset was removed.

## Fixed project workflows

### Protein–protein interaction ML

- The selected decision threshold is now applied to held-out labels, candidate labels, metrics, and the displayed confusion matrix.
- Duplicate unordered pairs are audited before deduplication.
- Contradictory labels for the same unordered pair are detected and blocked before training.
- Model fingerprints now include the canonical training content, feature contract, algorithm, seed, and threshold.
- Fitted preprocessing/model pipelines are retained for inference.
- Reusable `.joblib` model export, reload, compatibility validation, and candidate rescoring were added.
- Candidate outputs now record the decision threshold and complete model fingerprint.

### Comparative pathogen genomics

- Position-only variant comparison was replaced with matching-block alignment-aware variant extraction.
- Insertions and deletions no longer shift every downstream base into false substitutions.
- Variant outputs now include reference and query coordinates plus the alignment method.
- Pairwise summaries report alignment-aware identity and indel counts.

### Single-cell heterogeneity

- Optional heuristic-doublet exclusion is now wired into cell filtering before clustering.
- Doublet score and flag are retained in the QC table and export bundle.
- Marker discovery now includes Welch-test p-values and Benjamini–Hochberg FDR values.
- Raw-count pseudobulk aggregation by sample and cluster was added alongside the existing log-expression summary.

### Cancer genomics

- Mixed VAF inputs are normalized row by row: fractions such as `0.20` and percentages such as `20` can coexist safely.
- Original VAF values and inferred units are retained for auditability.
- Samples with zero QC-passing variants are retained in sample summaries with zero counts.
- Gene-pair association screening now includes Fisher exact tests, odds ratios, and FDR correction.

### Metagenomics

- The PERMANOVA quality gate now reads the actual `permutation_p_value` result.
- Sample QC gates now read `qc_status` instead of a nonexistent field.
- User-selected comparison groups are applied consistently to the pipeline, PERMANOVA, differential abundance, dispersion, indicator taxa, metadata export, and model card.
- Datasets containing more than two groups can now run a selected pairwise comparison without crashing.
- Metadata sample uniqueness and group/sample matching are validated.
- Beta dispersion now uses PCoA-coordinate distance to each group centroid while retaining the old column alias for compatibility.

## Application and engineering fixes

- Removed the duplicate `Modelling` navigation alias collision.
- Removed the overwritten `read_csv_cached` import in the DTI Feature Builder.
- Replaced remaining raw `st.json` result rendering with the professional structured-result component.
- Split an oversized scientific validation module so the engineering module-size gate passes without increasing the budget.
- Updated an outdated version assertion to the packaged application version `4.3.1`.
- Applied safe lint autofixes and formatting throughout affected modules.
- Project-wide Ruff result: **0 errors**.
- Python compilation: **passed**.

## Verification performed

- Verified tests: **82 passed** across biotechnology projects, production controls, scientific golden regressions, runtime recovery, provider integrations, Copilot/live connections, and new critical-fix regressions.
- New Step 53 regression tests: **6 passed**.
- SQLite databases: **20/20 integrity OK**.
- SQLite foreign-key violations: **0**.
- Five biotechnology project pages rendered successfully in Streamlit tests.

## Scientific boundary

Software logic, validation controls, reporting, and reusable artifacts were fixed. Genuine external laboratory results, regulatory approvals, peer-reviewed acceptance, paying customers, independent clinical validation, and long-duration production history cannot be manufactured inside a repository and remain evidence-gated.
