# BioIntel AI Milestone 25 Status

**Version:** 2.5.0  
**Milestone:** Real Evidence Edition  
**Status:** Implemented and regression tested

## Completed

- Eighth SQLite Evidence Registry
- Source, release, licence, publication and import-run records
- Row-level evidence keys and dataset links
- Correct censored activity interval semantics
- Generic, BindingDB and PubChem export importers
- Live ChEMBL activity intake with UniProt sequence resolution
- Real-evidence dataset registration
- Manual scientific-review queue
- Evidence readiness manifest
- Strict compound/scaffold/target/cluster/pair leakage audit
- Independent benchmark utility
- Evidence-aware scientific release gate
- API endpoints for registry/readiness/links/reviews
- Three new Streamlit screens
- Windows import and verification launchers
- Step 25 tests, templates and documentation

## Scientific boundary

The package does not include licensed third-party bulk datasets, wet-lab
results, GPU deep-learning weights, a production PostgreSQL cluster or cloud
credentials. Those require the operator's data rights, infrastructure and
validation programme. Bundled synthetic models remain demo-only.
