# Step 33 Production Scientific Platform Guide

## Local mode
Use `RUN_APP_WINDOWS.bat` and `RUN_API_WINDOWS.bat`. With no API clients configured, the API remains localhost-first and no-login.

## Role-aware API clients
Set `BIOINTEL_API_CLIENTS_JSON` using `config/production.example.env`. Raw API keys are never written to the security database; only SHA-256 digests are stored.

## Production services
`docker-compose.production.yml` provides optional PostgreSQL, Redis, MinIO, API and Streamlit services. Local SQLite mode remains supported.

## Official reference synchronization
The Internet Research Hub can request bounded ChEMBL activity records and reviewed UniProt metadata. ChEMBL records are marked as requiring curation and evidence review. UniProt records are reference metadata and do not establish activity evidence.

## Scientific release boundary
A technically complete registry is not equivalent to scientific validation. The release gate remains blocked until real experimental training, independent external validation and prospective validation requirements are met.

## Local background worker
Use `RUN_LOCAL_WORKER_WINDOWS.bat` to process supported queued ChEMBL, UniProt, diagnostics and database-maintenance jobs with stage progress and retry history.
