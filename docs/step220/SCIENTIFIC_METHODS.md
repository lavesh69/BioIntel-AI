# Step220 Scientific Methods

The production registry contains eighteen bounded, deterministic analysis families: sequencing quality, alignment/mapping, differential expression, biomarker discovery, variant prioritization, pathway enrichment, multi-omics, single-cell, proteomics, metabolomics, microbiome, structural biology, drug/target discovery, experimental design, statistical analysis, literature discovery, hypothesis generation, and laboratory validation.

Each engine validates required columns and sample sufficiency, records parameters and input hashes, applies module-specific QC, generates interpretable summaries/rankings, and persists warnings and limitations. Statistical helpers include multiple-testing correction, effect estimates, confidence intervals, cross-validation summaries, calibration, missingness, cohort balance, propensity overlap, longitudinal summaries, random-effects meta-analysis, and spatial neighborhoods where applicable.

Synthetic modules use deterministic fixtures with known truth and expected QC findings. `synthetic_adapter.py` transforms each module's generated tables into the canonical production schema. The production engine then persists the run using synthetic origin and seed metadata. Expected failure scenarios can complete with warnings or be captured as controlled failed runs; they never become real evidence.

External-tool parity depends on installed tools and databases. Native analysis of imported result tables does not imply that raw reads, spectra, images, or structures were processed by an absent external executable.
