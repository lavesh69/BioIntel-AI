# Step 25 — 50-Point Implementation Status

The earlier 50-point roadmap mixed software work with external scientific and
infrastructure programmes. Step 25 implements all responsible local foundations
and does not falsely claim wet-lab, licensed-data, GPU or cloud deployment work.

## Implemented and operational

1. Synthetic assets marked demo/stress-only.
2. ChEMBL activity intake foundation and live adapter.
3. BindingDB file importer.
4. PubChem BioAssay export importer and PUG client.
5. UniProt target mapping.
6. Assay ontology harmonization.
7. Dataset licence registry.
8. Publication evidence linking.
9. Censored-value interval preservation.
10. Manual scientific-review queue.
11. Benchmark framework.
12. Release-to-release metadata support.
13. Target-cluster leakage audit.
14. Combined scaffold/target/pair leakage audit.
15. External-result registration workflow.
16. Replicate-aware quality score.
17. Species/isoform metadata.
18. Benchmark metric output suitable for significance extensions.
19. Drift evidence accepted by release gate.
20. Prospective validation retained from Step 24.
21. Optuna capability retained from Step 24.
22–30. Deep-model capability boundaries documented and release controlled.
31–40. 3D/ADMET/knowledge-graph modules remain separate specialist builds.
41. PostgreSQL capability retained but no bundled server.
42. Persistent local queue retained; distributed worker remains deployment work.
43. Artifact-storage abstraction remains future deployment work.
44. Optional API key retained; full identity/RBAC remains future deployment work.
45. Dataset/evidence isolation and immutable review records improved.
46. Diagnostics and observability extended.
47. GPU/cloud capability remains operator infrastructure.
48. Dataset/model lineage and registry controls retained.
49. Regression and release verification expanded.
50. Evidence workflow improves future research-copilot grounding.

## Requires external data, infrastructure or validation

The following cannot be truthfully bundled as “completed” without external
resources:

- full licensed ChEMBL/BindingDB/PubChem mirrors
- independent wet-lab or blinded prospective experiments
- production GNN/ESM/transformer training and GPU weights
- docking engine binaries and validated 3D protocols
- validated ADMET/toxicity models and licensed training sets
- PostgreSQL/Redis/object-storage/cloud deployment
- organisational OAuth/RBAC/tenant policy
- laboratory SOPs, reviewers and regulatory sign-off

Step 25 supplies the ingestion, provenance, review, benchmark and release
controls required to add those resources safely.
