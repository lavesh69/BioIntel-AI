# Step 22 Connected Research Guide

## Starting connected mode

Run `START_BIOINTEL_INTERNET_WINDOWS.bat`.

The launcher enables outbound HTTPS research access and starts the local
Streamlit/FastAPI services. The application remains bound to `127.0.0.1`.

## PDB downloads

Use Internet Research Hub or Scientific Database Lookup.

PDBx/mmCIF is the recommended coordinate format. Compatible classic entries
can also be downloaded as legacy PDB files. Extended PDB identifiers require
PDBx/mmCIF.

## Compound-name resolution

Drug SMILES Analyzer supports:

- Bundled 5,000-name directory
- PubChem online lookup
- 1,000-structure coverage library
- Built-in common examples
- Custom SMILES

Registry and screening names are explicitly labelled. A directory match does
not establish that a compound is an approved medicine.

## Public HTTPS imports

Only public HTTPS URLs on port 443 are permitted. Private IP ranges,
credentials in URLs, executable extensions and oversized files are blocked.

Archives are downloaded but never extracted automatically.

## Offline workflow

Successfully downloaded files remain in `data/internet_downloads/` and are
indexed in `reports/internet_downloads.sqlite3` with checksum and provenance
metadata.

## Network variables

```text
BIOINTEL_INTERNET_ENABLED=1
BIOINTEL_ALLOW_PUBLIC_HTTPS=1
BIOINTEL_OFFICIAL_HOSTS_ONLY=0
BIOINTEL_RESOLVE_DNS=1
BIOINTEL_MAX_DOWNLOAD_MB=250
BIOINTEL_NETWORK_TIMEOUT=30
BIOINTEL_NETWORK_RETRIES=2
```
