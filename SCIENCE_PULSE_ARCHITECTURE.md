# Science Pulse Architecture

`providers/security -> scheduler -> service pipeline -> canonical SQLite -> FastAPI/Streamlit`

- The hidden background worker is the only network synchronization owner.
- Streamlit and read APIs query cached normalized rows and never synchronize on page rerun.
- Source runs are idempotent and checkpointed; a persistent scheduler lease prevents duplicate workers.
- Normalization, taxonomy, trust signals, clustering, alert matching, notifications, and digest persistence occur after fetch.
- Provenance is retained in both the canonical item and every contributing source link.
- Tenant ID participates in every user, alert, bookmark, search, notification, digest, and item query.
