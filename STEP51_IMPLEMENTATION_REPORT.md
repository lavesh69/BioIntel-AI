# Step 51 — Connected Biotechnology Platform Implementation Report

## Scope

Step 51 adds an operator-controlled connection layer for OpenAI and official biotechnology data providers while preserving the existing local-first scientific workspace.

## New user-facing modules

1. **BioIntel Copilot** (`pages/83_BioIntel_Copilot.py`)
   - OpenAI Responses API integration.
   - Approved provider tools selected per run.
   - Session-only API-key input and environment-variable support.
   - Evidence-only mode when OpenAI is not configured.
   - Visible provider evidence separated from generated interpretation.
   - Optional user-authorized local context, bounded to 20,000 characters.
   - Copilot run registry with status, model, tool-call count and answer checksum.

2. **Connected Data Explorer** (`pages/84_Connected_Data_Explorer.py`)
   - Federated search by gene, protein, compound, structure, variant, publication, trial, pathway, interaction or expression study.
   - Provider selection and per-provider record limits.
   - Normalized result table with source links.
   - CSV and evidence-JSON export.
   - Session handoff to domain-specific workbenches.

3. **Provider Integration Center** (`pages/85_Provider_Integration_Center.py`)
   - Non-secret OpenAI/NCBI configuration status.
   - Provider catalogue and domain coverage.
   - User-triggered live health probes.
   - Cache usage and provenance history.
   - HTTPS, host allowlist, response-size, retry and offline-fallback controls.

## Connected providers

- NCBI Entrez: Gene, PubMed, ClinVar, GEO/GDS, SRA, nucleotide and protein records.
- PubChem: compound properties and identifiers.
- UniProt: protein sequence and annotation records.
- RCSB PDB: structure lookup and full-text structure search.
- ChEMBL: molecule search and drug-like compound metadata.
- Ensembl: gene-symbol lookup and genomic coordinates.
- ClinicalTrials.gov: structured study search.
- Reactome: pathway search.
- STRING: protein-association networks.
- InterPro: protein family/domain lookup.
- Europe PMC: biomedical publication search.

## Backend implementation

New package: `src/biointel/connected/`

- `config.py`: non-secret runtime configuration.
- `models.py`: provider, record and query result contracts.
- `http.py`: HTTPS validation, official-host allowlists, bounded retries, rate limiting, response limits and local cache.
- `providers.py`: eleven normalized provider adapters and universal search.
- `tools.py`: OpenAI function-tool definitions and dispatch.
- `copilot.py`: OpenAI Responses API loop, function-call outputs, evidence collection and safe failure behavior.
- `registry.py`: SQLite provenance and Copilot run registry.

## Security and privacy

- No real API key is included in source, `.env.example`, tests, reports or release archives.
- OpenAI key is read from `OPENAI_API_KEY` or entered into a password field for the current Streamlit session.
- NCBI key and email are read from `NCBI_API_KEY` and `NCBI_EMAIL`.
- Every provider adapter uses an explicit official-host allowlist.
- Only HTTPS is accepted.
- Private, loopback, link-local and reserved network destinations remain blocked by the network policy.
- Provider errors are surfaced; no substitute result is fabricated.
- OpenAI receives only the question and optional context explicitly supplied by the operator.

## Provenance and caching

New database: `reports/connected_sources.sqlite3`

Tables:

- `connected_queries`
- `connected_records`
- `copilot_runs`

Each successful provider query records provider, query, entity type, source URL, retrieval time, response SHA-256, cache state, record count and warnings. Normalized records retain provider record IDs and source links.

## API additions

- `GET /v1/connectors/providers`
- `POST /v1/connectors/search`
- `GET /v1/connectors/history`
- `GET /v1/copilot/status`
- `POST /v1/copilot/query`

## Navigation and integration

- Application catalogue increased from 84 to 87 routes.
- Home and BioIntel Studio include connected-research launch surfaces.
- Search synonyms include ChatGPT, OpenAI, NCBI and internet/provider terminology.
- Workflow groups include Copilot, Connected Data Explorer and Provider Integration Center.
- Database discovery now includes `connected_sources.sqlite3` as a named registry.

## Windows operation

- `RUN_STEP51_CONNECTED_WINDOWS.bat`
- `CHECK_STEP51_CONNECTIONS_WINDOWS.bat`

The connected launcher enables approved outbound HTTPS. OpenAI remains optional because evidence-only provider search does not require an OpenAI key.

## Scientific boundary

Connected records are provider references, not independent experimental confirmation. OpenAI synthesis is interpretation, not evidence. Patient-specific, diagnostic, treatment, regulatory or publication-grade use requires appropriate governance, licences, expert review and independent validation.
