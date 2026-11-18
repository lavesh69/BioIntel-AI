# Step 25 Shortcomings Fixed

1. Corrected reversed inequality semantics after concentration-to-pActivity conversion.
2. Preserved lower and upper pActivity bounds for censored measurements.
3. Prevented uncertain threshold-crossing censored rows from being forced into a class.
4. Added real experimental evidence intake instead of synthetic-only growth.
5. Added ChEMBL bulk-page client and enrichment workflow.
6. Added BindingDB TSV endpoint parsing.
7. Added PubChem BioAssay export normalization.
8. Added UniProt target/isoform metadata resolution.
9. Added assay endpoint/category harmonization.
10. Added source release and licence registry.
11. Added import-run provenance and source hashes.
12. Added publication identifiers at row level.
13. Added canonical evidence keys.
14. Added human review decisions and comments.
15. Added canonical dataset hash binding.
16. Added evidence readiness metrics.
17. Added strict scaffold/target/pair leakage audit.
18. Added external benchmark utility and manifest.
19. Added evidence-aware scientific release gate.
20. Blocked synthetic demo models from scientific release.
21. Added evidence API endpoints.
22. Added eighth database to health/backup/optimization fabric.
23. Added real-evidence UI.
24. Added leakage/benchmark UI.
25. Added evidence-review UI.
26. Added Windows importer and verifier.
27. Added diagnostic licence/evidence checks.
28. Added input templates.
29. Added regression tests.
30. Updated project version/status/navigation to Step 25.
