# Step 52 — Proper Live Connection Upgrade

## Objective

Step 52 upgrades the Step 51 connected biotechnology layer from a functional integration framework into a hardened operational connection system for OpenAI and official public biotechnology providers. The upgrade preserves the existing local-first research workspace and all scientific databases.

## Connected application modules

### BioIntel Copilot

- OpenAI Responses API orchestration with provider function tools.
- Session-only or environment-managed API key support.
- Authenticated connection test and model-visibility diagnostic.
- Approved-provider allowlist for every Copilot run.
- Bounded provider-tool rounds and duplicate-call protection.
- Compact normalized evidence sent to OpenAI; bulky raw provider payloads remain local.
- Required provider/accession citation labels in the form `[provider:record_id]`.
- Verified-provider appendix added to completed answers.
- OpenAI response/request identifiers and token usage captured without storing credentials.
- `store=false` by default, configurable by the operator.
- Evidence-only mode remains available without an OpenAI key.

### Connected Data Explorer

- Cross-provider search by gene, protein, compound, structure, variant, literature, clinical trial, pathway, interaction, expression study or sequence.
- Provider/entity compatibility filtering.
- Exact-identifier recognition where supported.
- Structured per-provider output, normalized records, source links and provenance manifest.
- Typed failure categories with recovery guidance.
- CSV and JSON export plus workbench handoff.

### Provider Integration Center

- Non-secret configuration dashboard.
- OpenAI credential/model test that does not generate a paid answer.
- Live provider application-query probes.
- Latency, request ID, cache state, HTTP status and typed error visibility.
- Persistent provider-health history.
- Cache and query-history inspection.
- Security and outbound-network policy display.

## Provider adapters

1. NCBI Entrez E-utilities
2. PubChem PUG REST
3. UniProt REST
4. RCSB PDB Search/Data APIs
5. ChEMBL Web Services
6. Ensembl REST
7. ClinicalTrials.gov API v2
8. Reactome Content Service
9. STRING API
10. InterPro API
11. Europe PMC REST

Each adapter implements provider-specific request construction and normalization instead of returning a generic raw response.

## Connection and transport hardening

- HTTPS-only requests.
- Official-host allowlists.
- DNS resolution and public-IP validation before live calls.
- Private, loopback, link-local and reserved network targets rejected.
- Redirects disabled or strictly bounded and revalidated.
- Streaming response-size enforcement.
- Separate connect/read/write/pool timeouts.
- Retry handling for transient network failures, HTTP 429 and server errors.
- `Retry-After` support.
- Provider-specific request throttling.
- Fresh cache and stale-on-provider-failure behavior for scientific providers.
- OpenAI requests are never cached.
- Typed error taxonomy: configuration, authentication, authorization, DNS, timeout, rate limit, not found, server, redirect, content and response-size failures.
- Request IDs and selected non-sensitive response metadata retained.

## Credential and provenance controls

- No real credentials in source code, examples, reports or release archives.
- URL query secrets and authorization values redacted from errors, cache metadata and provenance.
- Windows configuration wizard stores keys in the user environment, outside the project directory.
- Official OpenAI API host enforced by default; custom gateways require explicit operator opt-in.
- Optional OpenAI project and organization headers.
- NCBI tool/contact identity support.
- STRING caller identity support.
- Local provenance registry stores normalized records, SHA-256 response hashes, retrieval time, source URL, latency, provider version/cache metadata and health checks.

## Windows operator workflow

1. `INSTALL_WINDOWS.bat`
2. `CONFIGURE_STEP52_CONNECTIONS_WINDOWS.bat`
3. Open a new terminal.
4. `TEST_STEP52_CONNECTIONS_WINDOWS.bat`
5. `RUN_STEP52_CONNECTED_WINDOWS.bat`

The test launcher creates `reports/step52_connection_test.json` with OpenAI and provider diagnostics.

## FastAPI surface

- `GET /v1/connectors/providers`
- `POST /v1/connectors/search`
- `POST /v1/connectors/health`
- `GET /v1/connectors/history`
- `GET /v1/copilot/status`
- `POST /v1/copilot/connection-test`
- `POST /v1/copilot/query`

## Qualification completed

- Step 51 and Step 52 connected tests: 17 passed.
- Step 43/45/46/50 assurance and UI tests: 19 passed.
- Step 47/48/49 biotechnology project compatibility tests: 24 passed.
- Total selected automated tests: 60 passed.
- Application default-render smoke: 87/87 routes passed.
- Python source compilation: 484 files passed.
- SQLite integrity: 19/19 databases healthy after release cleanup.
- Foreign-key checks: no violations.
- Original non-connected scientific and operational databases restored byte-for-byte after testing.
- Connected provenance registry released empty and schema-ready.

## External verification boundary

The build environment could not resolve public DNS, so real outbound OpenAI and biotechnology-provider calls could not be executed from the packaging container. The adapters, authentication flow and error paths were verified with deterministic mocked HTTP transports, provider-specific response fixtures, API/UI tests and offline-safe route execution. The supplied Windows connection test must be run on the operator's internet-connected machine with the operator's own credentials. No live provider result or OpenAI response was fabricated.
