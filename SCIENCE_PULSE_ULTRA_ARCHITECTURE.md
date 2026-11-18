# Science Pulse Ultra Architecture

`hidden Windows worker -> scheduler lease -> provider registry -> SafeHttpClient -> adapter -> normalized PulseRecord -> SQLite -> cached Streamlit/FastAPI readers`

Network I/O is confined to the hidden worker. HTTPS, DNS/public-address checks, approved hosts, MIME limits, payload limits and redirect preflight checks protect ingestion. Each feed has its own provider key and checkpoint.

Ultra knowledge-graph and claim-evidence services are not present in this increment.
