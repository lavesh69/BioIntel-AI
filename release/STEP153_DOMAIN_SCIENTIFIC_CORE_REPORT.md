# BioIntel AI Step 153 — Domain-Specific Scientific Core Upgrade

## Release outcome

Step 153 replaces broad generic fallback routing with 36 domain-specific native workflow families across all 80 registered scientific profiles. It also fixes metadata/rendering defects, separates native fallback availability from specialist-toolchain availability, adds explicit tool/reference readiness reporting, and preserves fail-closed evidence boundaries.

## Major improvements

- Expanded native workflow routing from 19 to 36 scientific families.
- Added dedicated CRISPR safety, antibody engineering, vaccine design, long-read, isoform, single-cell, epigenomics, genomic-variant, pathology, glycomics, proteogenomics, AMR, gene-therapy, cell-therapy, protein-design, enzyme-design, structural-protein, virology and synthetic-biology workflows.
- Added univariate Cox proportional-hazards analysis with confidence intervals and an exploratory proportional-hazards diagnostic.
- Added pharmacovigilance shrinkage proxy, duplicate-case audit, coding-version gate and exposure-denominator gate.
- Added specialist executable/Python-package readiness detection and reference-asset readiness reporting.
- Corrected ten malformed native-format declarations, duplicate pharmacovigilance mapping, and Knowledge Graph family collision.
- Replaced the misleading local-availability flag with separate native-fallback and specialist-toolchain fields.
- Kept every native workflow bounded to desktop-safe exploratory execution and explicit provenance.

## Verification

- 1,290 tests collected.
- 1,263 passed.
- 27 skipped because live browser/external runtime services were unavailable.
- 0 failed.
- 80/80 native workflow demos executed without an unhandled crash.
- 36 native workflow families registered.
- Python compile scan passed.
- Engineering quality/module-size budget passed without adding an exemption.

## Honest validation boundary

This release improves software quality and local exploratory scientific execution. It does not bundle every referenced specialist executable or full licensed database, and it does not establish clinical validity, GxP qualification, regulatory clearance, physical-instrument qualification or prospective wet-lab validation.
