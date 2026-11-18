# Step 22 — Shortcomings Fixed

- Added controlled scientific internet access instead of manual browser-only downloads.
- Added RCSB PDB metadata and coordinate-file retrieval.
- Added PubChem name-to-SMILES lookup.
- Added a searchable 5,000-name local compound directory.
- Clearly separated curated common names from registry/reference names.
- Added public HTTPS import with provenance and checksums.
- Blocked HTTP, private networks, credentials in URLs and nonstandard ports.
- Blocked executable/script downloads and automatic archive extraction.
- Added retry, timeout, redirect and file-size protections.
- Added an internet-download SQLite registry.
- Added offline access to previously saved downloads.
- Integrated internet tools into API, CLI, diagnostics and Windows launchers.
- Fixed private-IP validation where a policy exception was previously caught as a generic ValueError.
- Added safe Streamlit page-link fallbacks for isolated page testing.
