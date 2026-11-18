# Step 8 — Shortcomings Fixed

## Removed friction

- Removed login/account requirement.
- Removed API-key configuration.
- Removed authentication headers.
- Added one-click installer and launcher flow.
- Added clear local URLs.

## Safer no-login operation

- FastAPI defaults to `127.0.0.1`.
- Streamlit defaults to `127.0.0.1`.
- Docker Compose publishes only on `127.0.0.1`.
- Health endpoint clearly reports no-login local mode.
- Public-exposure warnings added throughout documentation.

## Local privacy and cleanup

- Added Local Data Manager.
- Restricted deletions to project `models` and `reports` folders.
- Protected model documentation and bundled demo models.
- Added storage-size summaries.
- Uploaded sequences and datasets remain non-persistent by default.
