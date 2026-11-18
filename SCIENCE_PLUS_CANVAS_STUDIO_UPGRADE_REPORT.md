# BioIntel Science Plus Canvas Studio Upgrade

Date: 2026-07-31  
Release base: BioIntel AI 15.6.0 Phase 31–35 Windows Fixed  
Scope: Science Plus / Science Pulse UI + UX and scientific canvas templates

## Delivered

- 35 professional canvas templates in eight scientific categories.
- Template gallery with search, category and canvas-type filters.
- User-scoped local persistence under `UserData/science_plus_canvases` or `BIOINTEL_USER_DATA_DIR`.
- Board, table, graph and timeline representations.
- Canvas details, objective, status, cards, owners, due dates, tags and evidence links.
- Persisted Science Plus record linking; demo records are excluded from the evidence linker.
- JSON, Markdown and CSV exports.
- Readiness and governance checks with explicit scientific-review boundaries.
- Navigation integration as **Canvas Studio** inside Science Plus.

## Template coverage

1. Research Question Builder
2. Hypothesis & Experiment Canvas
3. Study Design Blueprint
4. Systematic Review / PRISMA Canvas
5. Literature Review Matrix
6. Evidence Synthesis Board
7. Citation & Influence Map
8. Scientific Paper Reading Canvas
9. Genomics & Variant Interpretation Canvas
10. Multi-Omics Integration Canvas
11. Single-Cell Analysis Canvas
12. Spatial Omics Canvas
13. Transcriptomics Expression Canvas
14. Proteomics & Metabolomics Canvas
15. Pathway & Mechanism Canvas
16. Protein Structure Analysis Canvas
17. Drug Discovery Decision Canvas
18. Biomarker Discovery Canvas
19. Clinical Trial Landscape Canvas
20. Regulatory Intelligence Canvas
21. Grant & Funding Strategy Canvas
22. Patent & Translation Canvas
23. Outbreak Intelligence Canvas
24. One Health Evidence Canvas
25. Microbiome Study Canvas
26. Science News Digest Canvas
27. Publication Planning Canvas
28. Conference & Event Canvas
29. Scientific Collaboration Canvas
30. Scientific Trend Radar
31. Database & Tool Release Watch
32. Research Portfolio Canvas
33. Reproducibility & Audit Canvas
34. Scientific Data Readiness Canvas
35. Scientific Decision Canvas

## Truth and safety boundary

Template starter cards contain questions and planning prompts only. They do not contain fabricated experimental results, performance claims, clinical decisions or regulatory conclusions. Evidence cards can be created from persisted non-demo Science Plus records and retain their item identifiers for traceability.

## Validation completed in the build environment

- All four input ZIP archives passed compressed-data integrity tests.
- Combined project extraction produced 13,757 source files before the upgrade.
- Changed Python files passed bytecode compilation.
- Template catalogue uniqueness, storage, duplicate/delete, Markdown export and validation logic passed runtime-independent smoke checks.
- Full Streamlit AppTest execution was not available in the build container because Streamlit is not installed there; the project already declares Streamlit 1.58 in its dependency manifests.
