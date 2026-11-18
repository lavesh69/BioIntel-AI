# Hosted store backend

1. Copy `config/store-production.example.env` to `config/store-production.env`.
2. Replace every placeholder and set a real DNS name that points to the server.
3. Generate the UI password hash with `python scripts/create_ui_user.py --username admin`.
4. Run from the repository root:

```bash
docker compose --env-file config/store-production.env -f deploy/store/docker-compose.yml up -d --build
```

Caddy terminates TLS, routes `/v1`, `/legal`, health and API documentation to FastAPI, and routes the remaining browser traffic to Streamlit. The Android/iOS companion should connect to `BIOINTEL_PUBLIC_URL` over HTTPS. Back up PostgreSQL, MinIO, `data/`, and `reports/` before upgrades.
