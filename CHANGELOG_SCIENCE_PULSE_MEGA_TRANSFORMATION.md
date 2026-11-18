# Science Pulse Mega Transformation Changelog

- Added canonical versioned local Science Pulse data model and legacy migration facade.
- Added real metadata adapters for PubMed, Europe PMC, Crossref, OpenAlex, bioRxiv, medRxiv, arXiv, ClinicalTrials.gov, DataCite, and Crossref Event Data.
- Added secure managed RSS/Atom feeds and administrator registration/approval.
- Added persistent automatic scheduler within the existing hidden worker.
- Added normalization, taxonomy, entity extraction, deduplication, source clustering, trust events, search, offline cache, trends, alerts, confirmed delivery, and digests.
- Added Shiro, Classroom, Academy, Studio, Research, Education Home, and Connect workflows with provenance and approval boundaries.
- Replaced the Science Pulse Streamlit route with a local-database dashboard and added FastAPI endpoints.
- Added Windows worker controls, deterministic mega tests, reports, matrices, migration and rollback guidance.
