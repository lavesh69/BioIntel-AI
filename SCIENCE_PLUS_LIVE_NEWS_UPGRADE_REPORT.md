# BioIntel Science Plus — Live Science News Engine Upgrade Report

## Executive Summary
The **BioIntel Science Plus** module has been upgraded with a live, continuously refreshed scientific news & intelligence engine. The backend directly interfaces with official biomedical sources (PubMed/NCBI, Europe PMC, Crossref, bioRxiv/medRxiv, ClinicalTrials.gov, NIH, NLM, ScienceDaily, CDC, FDA, WHO, EMA, UK MHRA) while enforcing zero UI/UX changes and 100% baseline capability preservation.

## Key Upgrades
- **Live Ingestion Pipeline**: Ingestion pipeline enforcing Source Fetch → Validate → Normalise → Deduplicate → Classify → Score → Store → Serve.
- **Multi-Tenant Database Resilience**: Fallback to `DEFAULT_TENANT` (`'local'`) ensures all logged-in institutions access live items.
- **Scientific Status Labelling**: Explicit badges for Peer-Reviewed, Preprints (*NOT PEER REVIEWED*), Clinical Trials, and Retractions.
- **Streamlit Navigation Safety**: Deferred pending session state key handling prevents `StreamlitAPIException` on rapid tab switches.
