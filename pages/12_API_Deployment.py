from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.api.security_store import ApiSecurityStore
from biointel.production.readiness import production_readiness
from biointel.ui.components import metric_cards, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, badge, hero, professional_strip, section_title

st.set_page_config(page_title="API & Deployment · BioIntel AI", page_icon="🛠️", layout="wide")
apply_theme()

hero(
    "Secure API & Production Deployment",
    "Run the role-aware localhost API immediately, or activate PostgreSQL, Redis, MinIO, OIDC and distributed observability through the production profile.",
    eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences",
    chips=["Role-aware API keys", "Request audit", "Persistent rate limits", "Production profile"],
)

security = ApiSecurityStore(ROOT / "reports" / "api_security.sqlite3")
security_status = security.status()
production = production_readiness()
metric_cards(
    [
        ("API mode", "Local professional", "No-login localhost remains supported"),
        ("API version", "v1", "Versioned platform endpoints"),
        ("Security audit rows", f"{security_status['request_log_count']:,}", None),
        ("Configured clients", f"{security_status['enabled_clients']:,}", "Role-aware clients stored as key hashes"),
        ("Production checks", f"{production['ready_checks']}/{production['total_checks']}", None),
        ("Request limit", "100 MB", "Content-Length and streamed-body enforcement"),
    ]
)

badge("● Localhost mode available · production services remain explicit and opt-in", "success")
professional_strip(
    "Security boundary",
    "Trusted hosts, role-aware keys, persistent audit logs, request IDs, streamed upload limits, security headers and restart-safe rate limiting are enabled in the API layer.",
)

local_tab, production_tab, security_tab, endpoints_tab = st.tabs(
    ["Local API", "Production stack", "Security audit", "Endpoint catalogue"]
)

with local_tab:
    section_title("Run FastAPI locally", "▶")
    st.code(
        r""".\.venv\Scripts\activate
uvicorn biointel.api.main:app --app-dir src --host 127.0.0.1 --port 8000
""",
        language="powershell",
    )
    st.code("http://127.0.0.1:8000/docs", language=None)
    st.markdown(
        """
**Local safeguards**

- Trusted-host validation
- 100 MB Content-Length and chunked-stream enforcement
- `X-Request-ID` on every response
- Persistent request audit in `api_security.sqlite3`
- Optional role-aware `X-API-Key` clients: viewer, reviewer, operator, admin
- Restart-safe per-client/IP rate windows
- `Cache-Control: no-store`, CSP, frame and content-type protections
- No public CORS origins by default
"""
    )
    st.code(
        'set BIOINTEL_API_CLIENTS_JSON={"clients":[{"client_id":"operator","role":"operator","key":"replace-me"}]}',
        language="powershell",
    )

with production_tab:
    checks = pd.DataFrame(production["checks"])
    smart_dataframe(checks, height=420)
    st.info(
        "The production profile is optional. The standard package remains fully usable with local SQLite and local files."
    )
    section_title("Production services", "🏗️")
    st.markdown(
        """
- PostgreSQL for multi-user transactions and schema migrations
- Redis for distributed queues, shared rate limits and cache coordination
- MinIO/S3 for versioned model, dataset and report artifacts
- OIDC-ready identity configuration
- Prometheus/OpenTelemetry dependencies for metrics and traces
- Separate production Dockerfile and Compose stack
"""
    )
    st.code(
        r"""copy config\production.example.env .env.production
# Edit all passwords and API clients first
docker compose --env-file .env.production -f docker-compose.production.yml up --build
""",
        language="powershell",
    )
    st.download_button(
        "Download production environment template",
        (ROOT / "config" / "production.example.env").read_text(encoding="utf-8"),
        "production.example.env",
        "text/plain",
        width="stretch",
    )

with security_tab:
    smart_json(security_status, title="API security and audit status", download_name="api_security_status.json")
    recent = pd.DataFrame(security_status.get("recent_requests", []))
    if not recent.empty:
        section_title("Recent API requests", "🔐")
        smart_dataframe(recent, height=420)
    st.caption("Raw API keys are never persisted; only SHA-256 key digests and client metadata are stored.")

with endpoints_tab:
    endpoints = pd.DataFrame(
        [
            ("System", "GET", "/health", "Health, access and scope"),
            ("System", "GET", "/v1/health", "Versioned health envelope"),
            ("System", "GET", "/v1/platform/summary", "Consolidated platform summary"),
            ("Security", "GET", "/security/status", "Request audit and client status"),
            ("Production", "GET", "/production/readiness", "PostgreSQL/Redis/MinIO/OIDC readiness"),
            ("Readiness", "GET", "/readiness/summary", "Scientific and registry readiness"),
            ("Relationships", "GET", "/relationships/summary", "Cross-database relationship status"),
            ("Jobs", "POST", "/jobs", "Submit staged/dependent job"),
            ("Jobs", "GET", "/jobs/{job_id}/timeline", "Events, stages, dependencies and artifacts"),
            ("Jobs", "GET", "/jobs/workers/status", "Worker heartbeat status"),
            ("Bioinformatics", "POST", "/bioinformatics/fastq/qc", "FASTQ QC and trimming"),
            ("Bioinformatics", "POST", "/bioinformatics/variants/summary", "VCF summary and filters"),
            ("Bioinformatics", "POST", "/bioinformatics/primers/design", "Primer design"),
            ("Bioinformatics", "POST", "/bioinformatics/crispr/guides", "CRISPR guide screening"),
            ("Bioinformatics", "POST", "/bioinformatics/protein/annotate", "Protein annotation"),
            ("Bioinformatics", "POST", "/bioinformatics/structure/analyze", "PDB structure analysis"),
            ("Chemistry", "POST", "/bioinformatics/admet/profile", "Descriptor/rule-based ADMET screen"),
            ("Evidence", "GET", "/evidence/summary", "Evidence registry status"),
            ("Documents", "POST", "/documents/extract", "Secure document extraction"),
            ("DTI", "POST", "/dti/predict", "Single DTI prediction"),
            ("DTI", "POST", "/dti/batch-predict", "Batch DTI prediction"),
        ],
        columns=["Group", "Method", "Path", "Purpose"],
    )
    smart_dataframe(endpoints, height=620)
    st.caption("The complete interactive OpenAPI catalogue is available at `/docs` when the API is running.")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
