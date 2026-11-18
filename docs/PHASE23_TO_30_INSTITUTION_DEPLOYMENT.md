# Institution Deployment Guide

Start with a controlled pilot. Define data owner, privacy contact, support owner, backup policy, allowed integrations and acceptance criteria before importing production records.

The locally qualified profile is Windows + CPython 3.11 + SQLite + managed local storage. A server deployment must additionally qualify TLS/reverse proxy, PostgreSQL, Redis, S3, secret management, monitoring, backup/restore, incident response, SSO and capacity on representative data.

Run diagnostics after install and after configuration changes. Keep MCP/API keys least-privileged and rotate them. External adapters remain disabled until their connection test is successful and documented.

