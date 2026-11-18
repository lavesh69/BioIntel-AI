from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import mimetypes
import os
import platform as runtime_platform
import re
import secrets
import shutil
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
except ImportError:
    class hashes:
        class SHA256: pass
    class padding:
        class OAEP: pass
        class MGF1: pass
    class rsa: pass

from .phase11 import ADMIN_ROLES, TEACHER_ROLES, EducationPhase11Service, _json
from .phase6_adapters import _environment_secret, _fetch_json, _validate_public_https
from .platform import Conflict, Denied, EducationError, Missing, ident, now, parse_time

MIGRATION_ID = "education_phase12_final_completion_v1"

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS education_oidc_login_states(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 provider_id TEXT NOT NULL REFERENCES education_identity_providers(id),
 state_hash TEXT NOT NULL UNIQUE,
 nonce_hash TEXT NOT NULL,
 verifier_cipher TEXT NOT NULL,
 redirect_uri TEXT NOT NULL,
 login_hint TEXT NOT NULL DEFAULT '',
 discovery_json TEXT NOT NULL DEFAULT '{}',
 state TEXT NOT NULL DEFAULT 'pending',
 created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_education_oidc_state_expiry
 ON education_oidc_login_states(state,expires_at);
CREATE TABLE IF NOT EXISTS education_external_identity_links(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 provider_id TEXT NOT NULL REFERENCES education_identity_providers(id),
 external_subject TEXT NOT NULL,
 user_id TEXT NOT NULL,
 email TEXT NOT NULL DEFAULT '',
 claims_json TEXT NOT NULL DEFAULT '{}',
 linked_by TEXT NOT NULL DEFAULT '',
 linked_at TEXT NOT NULL,
 last_login_at TEXT NOT NULL,
 UNIQUE(provider_id,external_subject)
);

CREATE TABLE IF NOT EXISTS education_database_migration_exports(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 profile_id TEXT REFERENCES education_database_profiles(id),
 output_path TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 table_count INTEGER NOT NULL,
 row_count INTEGER NOT NULL,
 manifest_json TEXT NOT NULL DEFAULT '{}',
 state TEXT NOT NULL DEFAULT 'ready',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_storage_transfers(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 backend_id TEXT NOT NULL REFERENCES education_storage_backends(id),
 object_key TEXT NOT NULL,
 local_path TEXT NOT NULL DEFAULT '',
 direction TEXT NOT NULL,
 sha256 TEXT NOT NULL DEFAULT '',
 size_bytes INTEGER NOT NULL DEFAULT 0,
 etag TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'pending',
 detail_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_storage_transfers
 ON education_storage_transfers(institution_id,backend_id,state,created_at);

CREATE TABLE IF NOT EXISTS education_originality_fingerprints(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 subject_id TEXT NOT NULL REFERENCES subjects(id),
 submission_id TEXT NOT NULL UNIQUE REFERENCES submissions(id),
 student_id TEXT NOT NULL,
 text_sha256 TEXT NOT NULL,
 normalized_text TEXT NOT NULL,
 shingles_json TEXT NOT NULL DEFAULT '[]',
 token_count INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_originality_matches(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 source_submission_id TEXT NOT NULL REFERENCES submissions(id),
 candidate_submission_id TEXT NOT NULL REFERENCES submissions(id),
 similarity REAL NOT NULL,
 matched_shingles INTEGER NOT NULL DEFAULT 0,
 source_tokens INTEGER NOT NULL DEFAULT 0,
 candidate_tokens INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'needs_review',
 reviewed_by TEXT NOT NULL DEFAULT '',
 review_note TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(source_submission_id,candidate_submission_id)
);

CREATE TABLE IF NOT EXISTS education_exam_governance(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 exam_id TEXT NOT NULL UNIQUE REFERENCES examinations(id),
 lifecycle_state TEXT NOT NULL DEFAULT 'draft',
 paper_author_id TEXT NOT NULL,
 paper_reviewer_id TEXT NOT NULL DEFAULT '',
 answer_key_reviewer_id TEXT NOT NULL DEFAULT '',
 controller_id TEXT NOT NULL DEFAULT '',
 moderation_tolerance REAL NOT NULL DEFAULT 5,
 paper_approved_at TEXT,
 answer_key_approved_at TEXT,
 controller_approved_at TEXT,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_exam_governance_events(
 id TEXT PRIMARY KEY,
 governance_id TEXT NOT NULL REFERENCES education_exam_governance(id) ON DELETE CASCADE,
 actor_id TEXT NOT NULL,
 event_type TEXT NOT NULL,
 detail_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_exam_evaluations(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 exam_id TEXT NOT NULL REFERENCES examinations(id),
 session_id TEXT NOT NULL REFERENCES education_exam_sessions(id),
 examiner_id TEXT NOT NULL,
 stage TEXT NOT NULL,
 score REAL NOT NULL,
 max_score REAL NOT NULL,
 rubric_json TEXT NOT NULL DEFAULT '{}',
 comments TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'submitted',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(session_id,examiner_id,stage)
);
CREATE TABLE IF NOT EXISTS education_exam_appeals(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 exam_id TEXT NOT NULL REFERENCES examinations(id),
 session_id TEXT NOT NULL REFERENCES education_exam_sessions(id),
 student_id TEXT NOT NULL,
 reason TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'submitted',
 assigned_to TEXT NOT NULL DEFAULT '',
 decision_note TEXT NOT NULL DEFAULT '',
 original_score REAL,
 revised_score REAL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS education_exam_heartbeats(
 session_id TEXT PRIMARY KEY REFERENCES education_exam_sessions(id) ON DELETE CASCADE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 exam_id TEXT NOT NULL REFERENCES examinations(id),
 student_id TEXT NOT NULL,
 connection_state TEXT NOT NULL DEFAULT 'online',
 current_question_id TEXT NOT NULL DEFAULT '',
 answered_count INTEGER NOT NULL DEFAULT 0,
 client_clock_offset_ms INTEGER NOT NULL DEFAULT 0,
 detail_json TEXT NOT NULL DEFAULT '{}',
 last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_ai_model_profiles(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 name TEXT NOT NULL,
 provider_type TEXT NOT NULL,
 endpoint TEXT NOT NULL DEFAULT '',
 model_name TEXT NOT NULL,
 embedding_model TEXT NOT NULL DEFAULT '',
 reranker_model TEXT NOT NULL DEFAULT '',
 secret_reference TEXT NOT NULL DEFAULT '',
 context_window INTEGER NOT NULL DEFAULT 4096,
 state TEXT NOT NULL DEFAULT 'draft',
 readiness_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,name)
);
CREATE TABLE IF NOT EXISTS education_rag_documents(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 project_id TEXT NOT NULL,
 title TEXT NOT NULL,
 source_path TEXT NOT NULL,
 source_name TEXT NOT NULL,
 mime_type TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 size_bytes INTEGER NOT NULL,
 version INTEGER NOT NULL DEFAULT 1,
 permission_json TEXT NOT NULL DEFAULT '{}',
 safety_json TEXT NOT NULL DEFAULT '{}',
 state TEXT NOT NULL DEFAULT 'registered',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,project_id,sha256)
);
CREATE TABLE IF NOT EXISTS education_rag_evaluations(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 project_id TEXT NOT NULL,
 query_text TEXT NOT NULL,
 expected_refs_json TEXT NOT NULL DEFAULT '[]',
 retrieved_refs_json TEXT NOT NULL DEFAULT '[]',
 recall_at_k REAL NOT NULL DEFAULT 0,
 citation_coverage REAL NOT NULL DEFAULT 0,
 grounded INTEGER NOT NULL DEFAULT 0,
 evaluated_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_delivery_providers(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 channel TEXT NOT NULL,
 name TEXT NOT NULL,
 endpoint TEXT NOT NULL DEFAULT '',
 sender TEXT NOT NULL DEFAULT '',
 secret_reference TEXT NOT NULL DEFAULT '',
 settings_json TEXT NOT NULL DEFAULT '{}',
 state TEXT NOT NULL DEFAULT 'draft',
 readiness_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,channel,name)
);

CREATE TABLE IF NOT EXISTS education_release_qualifications(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 qualification_type TEXT NOT NULL,
 state TEXT NOT NULL,
 evidence_json TEXT NOT NULL DEFAULT '{}',
 performed_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);

INSERT OR IGNORE INTO education_migrations(id,applied_at)
 VALUES('education_phase12_final_completion_v1',datetime('now'));
"""

OIDC_TYPES = {"oidc", "google_workspace", "microsoft_entra"}
EXAM_LIFECYCLE = (
    "draft", "paper_review", "answer_key_review", "controller_approval", "scheduled",
    "live", "grading", "moderation", "published", "archived", "cancelled",
)
MODEL_PROVIDERS = {"ollama", "openai_compatible", "local_file", "disabled"}
DELIVERY_CHANNELS = {"smtp", "webhook", "sms", "whatsapp", "desktop", "in_app"}
INJECTION_PATTERNS = (
    r"ignore\s+(all|any|the)\s+(previous|prior)\s+instructions",
    r"system\s+prompt",
    r"developer\s+message",
    r"reveal\s+(your|the)\s+(hidden|secret)",
    r"bypass\s+(policy|safety|guardrail)",
    r"act\s+as\s+(root|administrator|system)",
)


def _decode(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError):
        return fallback


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_text(text: str) -> str:
    clean = re.sub(r"[^\w\s]", " ", str(text).lower(), flags=re.UNICODE)
    return " ".join(clean.split())


def _shingles(text: str, size: int = 5) -> set[str]:
    tokens = _normalize_text(text).split()
    if len(tokens) < size:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[index:index + size]) for index in range(len(tokens) - size + 1)}


def _jaccard(left: set[str], right: set[str]) -> tuple[float, int]:
    if not left and not right:
        return 0.0, 0
    intersection = len(left & right)
    union = len(left | right)
    return (intersection / union if union else 0.0), intersection


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * ((4 - len(text) % 4) % 4))


def _safe_redirect_uri(uri: str) -> str:
    parsed = urllib.parse.urlparse(str(uri or "").strip())
    if parsed.scheme == "https" and parsed.hostname:
        return parsed.geturl()
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return parsed.geturl()
    raise EducationError("OIDC redirect URI must use HTTPS or localhost HTTP.")


def _post_form(url: str, form: dict[str, str], *, timeout: float = 15.0) -> dict[str, Any]:
    _validate_public_https(url)
    body = urllib.parse.urlencode(form).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": "BioIntel-Phase12/15.6"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=max(3.0, min(timeout, 30.0)), context=ssl.create_default_context()) as response:
            payload = response.read(1_048_577)
            if len(payload) > 1_048_576:
                raise Conflict("OIDC token response exceeded the 1 MiB safety limit.")
            if not 200 <= int(response.status) < 300:
                raise Conflict(f"OIDC token endpoint returned HTTP {response.status}.")
    except urllib.error.HTTPError as exc:
        detail = exc.read(8192).decode("utf-8", errors="replace")
        raise Conflict(f"OIDC token exchange failed with HTTP {exc.code}: {detail[:500]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Conflict(f"OIDC token exchange failed: {exc}") from exc
    try:
        result = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Conflict("OIDC token endpoint did not return valid JSON.") from exc
    if not isinstance(result, dict):
        raise Conflict("OIDC token endpoint returned an unsupported response.")
    result["_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return result


def _verify_rs256_jwt(token: str, jwks: dict[str, Any], *, issuer: str, audience: str, nonce: str) -> dict[str, Any]:
    parts = str(token).split(".")
    if len(parts) != 3:
        raise Denied("OIDC ID token format is invalid.")
    try:
        header = json.loads(_b64url_decode(parts[0]))
        claims = json.loads(_b64url_decode(parts[1]))
        signature = _b64url_decode(parts[2])
    except Exception as exc:
        raise Denied("OIDC ID token could not be decoded.") from exc
    if header.get("alg") != "RS256":
        raise Denied("Only RS256 OIDC ID tokens are accepted in this release.")
    kid = str(header.get("kid") or "")
    keys = jwks.get("keys") if isinstance(jwks, dict) else None
    key = next((item for item in (keys or []) if isinstance(item, dict) and str(item.get("kid") or "") == kid), None)
    if not key or key.get("kty") != "RSA":
        raise Denied("Matching OIDC signing key was not found.")
    try:
        modulus = int.from_bytes(_b64url_decode(str(key["n"])), "big")
        exponent = int.from_bytes(_b64url_decode(str(key["e"])), "big")
        public_key = rsa.RSAPublicNumbers(exponent, modulus).public_key()
        public_key.verify(signature, f"{parts[0]}.{parts[1]}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    except Exception as exc:
        raise Denied("OIDC ID token signature verification failed.") from exc
    current = int(time.time())
    if str(claims.get("iss") or "").rstrip("/") != str(issuer).rstrip("/"):
        raise Denied("OIDC issuer mismatch.")
    aud = claims.get("aud")
    audiences = {str(aud)} if isinstance(aud, str) else {str(item) for item in (aud or [])}
    if audience not in audiences:
        raise Denied("OIDC audience mismatch.")
    if int(claims.get("exp") or 0) <= current:
        raise Denied("OIDC ID token has expired.")
    if int(claims.get("iat") or current) > current + 120:
        raise Denied("OIDC ID token issue time is invalid.")
    if not hmac.compare_digest(str(claims.get("nonce") or ""), nonce):
        raise Denied("OIDC nonce mismatch.")
    if not claims.get("sub"):
        raise Denied("OIDC subject claim is missing.")
    return claims


class EducationPhase12Service(EducationPhase11Service):
    """Final local/code-level completion layer.

    External providers are executed only when administrators configure explicit env: secret
    references and network access. Missing credentials are reported as unqualified rather than
    silently replaced with demo success.
    """

    def __init__(self, platform: Any, *, root: str | Path | None = None):
        super().__init__(platform, root=root)
        self.root = Path(root or self.root)
        self.migrate_phase12()

    def migrate_phase12(self) -> str:
        with self.db.connection() as db:
            db.executescript(SCHEMA)
        return MIGRATION_ID

    # ---------- OIDC PKCE authentication ----------
    def begin_oidc_authorization(self, provider_id: str, redirect_uri: str, *, login_hint: str = "") -> dict[str, Any]:
        provider = self.platform._one("SELECT * FROM education_identity_providers WHERE id=?", (provider_id,))
        if not provider or provider["provider_type"] not in OIDC_TYPES:
            raise Missing("Active OIDC-compatible identity provider not found.")
        if provider["state"] not in {"ready", "verified", "configuration_ready"}:
            raise Conflict("Identity provider is not active.")
        issuer = str(provider["issuer_url"] or "").rstrip("/")
        if not issuer or not provider["client_id"]:
            raise Conflict("OIDC issuer and client ID are required.")
        status, discovery, _, _ = _fetch_json(issuer + "/.well-known/openid-configuration")
        if not 200 <= status < 300 or str(discovery.get("issuer") or "").rstrip("/") != issuer:
            raise Conflict("OIDC discovery verification failed.")
        authorization_endpoint = str(discovery.get("authorization_endpoint") or "")
        token_endpoint = str(discovery.get("token_endpoint") or "")
        jwks_uri = str(discovery.get("jwks_uri") or "")
        if not authorization_endpoint or not token_endpoint or not jwks_uri:
            raise Conflict("OIDC discovery document is incomplete.")
        _validate_public_https(authorization_endpoint)
        _validate_public_https(token_endpoint)
        _validate_public_https(jwks_uri)
        redirect = _safe_redirect_uri(redirect_uri)
        state_plain = secrets.token_urlsafe(32)
        nonce_plain = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        stamp = now()
        row_id = ident("oidc")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_oidc_login_states VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row_id, provider["institution_id"], provider_id,
                    hashlib.sha256(state_plain.encode()).hexdigest(), hashlib.sha256(nonce_plain.encode()).hexdigest(),
                    self._fernet.encrypt(verifier.encode()).decode(), redirect, str(login_hint).strip(), _json(discovery),
                    "pending", stamp, (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(), None,
                ),
            )
        params = {
            "response_type": "code", "client_id": provider["client_id"], "redirect_uri": redirect,
            "scope": "openid email profile", "state": state_plain, "nonce": nonce_plain,
            "code_challenge": challenge, "code_challenge_method": "S256",
        }
        if login_hint:
            params["login_hint"] = str(login_hint).strip()
        return {
            "authorization_url": authorization_endpoint + "?" + urllib.parse.urlencode(params),
            "state": state_plain, "nonce": nonce_plain, "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            "provider": provider["display_name"],
        }

    def complete_oidc_authorization(self, state: str, code: str, nonce: str) -> dict[str, Any]:
        state_hash = hashlib.sha256(str(state).encode()).hexdigest()
        row = self.platform._one("SELECT * FROM education_oidc_login_states WHERE state_hash=?", (state_hash,))
        if not row or row["state"] != "pending":
            raise Denied("OIDC login state is invalid or already used.")
        if parse_time(row["expires_at"]) <= datetime.now(timezone.utc):
            raise Denied("OIDC login state has expired.")
        if not hmac.compare_digest(row["nonce_hash"], hashlib.sha256(str(nonce).encode()).hexdigest()):
            raise Denied("OIDC browser nonce mismatch.")
        provider = self.platform._one("SELECT * FROM education_identity_providers WHERE id=?", (row["provider_id"],))
        if not provider:
            raise Missing("OIDC provider no longer exists.")
        discovery = _decode(row["discovery_json"], {})
        verifier = self._fernet.decrypt(row["verifier_cipher"].encode()).decode()
        form = {
            "grant_type": "authorization_code", "code": str(code), "redirect_uri": row["redirect_uri"],
            "client_id": provider["client_id"], "code_verifier": verifier,
        }
        if provider["secret_reference"]:
            form["client_secret"] = _environment_secret(provider["secret_reference"])
        token_response = _post_form(str(discovery["token_endpoint"]), form)
        id_token = str(token_response.get("id_token") or "")
        if not id_token:
            raise Denied("OIDC provider did not return an ID token.")
        status, jwks, _, _ = _fetch_json(str(discovery["jwks_uri"]))
        if not 200 <= status < 300:
            raise Denied("OIDC signing keys could not be retrieved.")
        claims = _verify_rs256_jwt(id_token, jwks, issuer=str(discovery["issuer"]), audience=provider["client_id"], nonce=str(nonce))
        email = str(claims.get("email") or "").strip().lower()
        allowed = set(_decode(provider["allowed_domains_json"], []))
        if allowed and (not email or email.rsplit("@", 1)[-1] not in allowed):
            raise Denied("OIDC email domain is not allowed for this institution.")
        account = self.platform._one(
            "SELECT * FROM education_identity_accounts WHERE institution_id=? AND lower(email)=lower(?) AND state='active'",
            (provider["institution_id"], email),
        ) if email else None
        existing_link = self.platform._one(
            "SELECT * FROM education_external_identity_links WHERE provider_id=? AND external_subject=?",
            (provider["id"], str(claims["sub"])),
        )
        user_id = str(existing_link["user_id"]) if existing_link else str(account["user_id"]) if account else ""
        if not user_id or not self.platform.membership(user_id, provider["institution_id"]):
            raise Denied("OIDC identity is not linked to an active institution account.")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_external_identity_links VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(provider_id,external_subject) DO UPDATE SET user_id=excluded.user_id,email=excluded.email,
                claims_json=excluded.claims_json,last_login_at=excluded.last_login_at""",
                (ident("idlink"), provider["institution_id"], provider["id"], str(claims["sub"]), user_id, email, _json(claims), user_id, stamp, stamp),
            )
            db.execute("UPDATE education_oidc_login_states SET state='completed',completed_at=? WHERE id=?", (stamp, row["id"]))
        session = self._create_desktop_session(provider["institution_id"], user_id, f"OIDC · {provider['display_name']}")
        self.security_event(provider["institution_id"], "oidc_login_completed", actor_id=user_id, detail={"provider_id": provider["id"], "email": email})
        return {**session, "provider_id": provider["id"], "email": email, "external_subject": str(claims["sub"]), "mfa_verified": True}

    # ---------- portable PostgreSQL migration bundle ----------
    def create_database_migration_export(self, actor: str, institution_id: str, *, profile_id: str = "") -> dict[str, Any]:
        self._admin(actor, institution_id)
        if profile_id:
            profile = self.platform._one("SELECT * FROM education_database_profiles WHERE id=? AND institution_id=?", (profile_id, institution_id))
            if not profile or profile["engine"] != "postgresql":
                raise Missing("PostgreSQL migration profile not found.")
        output_dir = self.root / "education" / "migration_exports" / institution_id
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = output_dir / f"postgresql-migration-{stamp}.jsonl"
        manifest: dict[str, Any] = {"schema": "biointel.postgresql-portable-export.v1", "institution_id": institution_id, "generated_at": now(), "tables": []}
        row_count = 0
        with self.db.connection() as db, output.open("w", encoding="utf-8") as handle:
            tables = [str(row[0]) for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            for table in tables:
                columns = [str(row[1]) for row in db.execute(f'PRAGMA table_info("{table}")')]
                if "institution_id" not in columns:
                    continue
                rows = db.execute(f'SELECT * FROM "{table}" WHERE institution_id=?', (institution_id,)).fetchall()
                manifest["tables"].append({"name": table, "columns": columns, "rows": len(rows)})
                for row in rows:
                    handle.write(_json({"table": table, "row": dict(row)}) + "\n")
                row_count += len(rows)
        manifest_path = output.with_suffix(".manifest.json")
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        sha = _sha256_file(output)
        export_id = ident("dbexport")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_database_migration_exports VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (export_id, institution_id, profile_id or None, str(output), sha, len(manifest["tables"]), row_count, _json(manifest), "ready", actor, now()),
            )
        return {"id": export_id, "output_path": str(output), "manifest_path": str(manifest_path), "sha256": sha, "table_count": len(manifest["tables"]), "row_count": row_count, "state": "ready"}

    def verify_database_migration_export(self, actor: str, export_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_database_migration_exports WHERE id=?", (export_id,))
        if not row:
            raise Missing("Database migration export not found.")
        self._admin(actor, row["institution_id"])
        path = Path(row["output_path"])
        actual = _sha256_file(path) if path.is_file() else ""
        return {"id": export_id, "valid": bool(actual and hmac.compare_digest(actual, row["sha256"])), "expected_sha256": row["sha256"], "actual_sha256": actual, "row_count": row["row_count"], "table_count": row["table_count"]}

    def apply_database_migration_export(self, actor: str, export_id: str, *, dry_run: bool = True) -> dict[str, Any]:
        """Validate or apply a tenant-scoped JSONL export to an already migrated PostgreSQL schema.

        This method deliberately does not invent or silently create a production schema. The target
        schema must first be deployed through the institution's governed migration process. Every
        table and column is quoted through psycopg identifiers, and the operation runs in one
        transaction with ON CONFLICT DO NOTHING so a retry remains idempotent.
        """
        export = self.platform._one("SELECT * FROM education_database_migration_exports WHERE id=?", (export_id,))
        if not export:
            raise Missing("Database migration export not found.")
        self._admin(actor, export["institution_id"])
        profile_id = str(export.get("profile_id") or "")
        profile = self.platform._one("SELECT * FROM education_database_profiles WHERE id=? AND institution_id=?", (profile_id, export["institution_id"])) if profile_id else None
        if not profile or profile["engine"] != "postgresql":
            raise Conflict("A PostgreSQL database profile is required before applying this export.")
        verification = self.verify_database_migration_export(actor, export_id)
        if not verification["valid"]:
            raise Conflict("Migration export hash verification failed.")
        dsn = _environment_secret(str(profile["dsn_reference"] or ""))
        if not dsn:
            raise Conflict("PostgreSQL DSN environment secret is unavailable.")
        try:
            import psycopg  # type: ignore
            from psycopg import sql  # type: ignore
        except ImportError as exc:
            raise Conflict("psycopg is required for live PostgreSQL migration. Install requirements-production.txt.") from exc
        rows_by_table: dict[str, list[dict[str, Any]]] = {}
        path = Path(export["output_path"])
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise Conflict(f"Migration export JSONL is invalid at line {line_number}.") from exc
                table = str(item.get("table") or "")
                row = item.get("row")
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table) or not isinstance(row, dict):
                    raise Conflict(f"Migration export line {line_number} contains an unsafe table or row.")
                if str(row.get("institution_id") or "") != export["institution_id"]:
                    raise Denied("Migration export contains a cross-institution row.")
                rows_by_table.setdefault(table, []).append(row)
        inserted, examined = 0, 0
        started = time.perf_counter()
        try:
            with psycopg.connect(dsn, connect_timeout=10) as connection:
                with connection.cursor() as cursor:
                    for table, table_rows in rows_by_table.items():
                        cursor.execute("SELECT to_regclass(%s)", (table,))
                        if not cursor.fetchone()[0]:
                            raise Conflict(f"Target PostgreSQL schema is missing table {table}.")
                        for row in table_rows:
                            columns = list(row.keys())
                            if not columns or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(column)) for column in columns):
                                raise Conflict(f"Migration row for {table} has unsafe columns.")
                            query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
                                sql.Identifier(table),
                                sql.SQL(",").join(sql.Identifier(str(column)) for column in columns),
                                sql.SQL(",").join(sql.Placeholder() for _ in columns),
                            )
                            examined += 1
                            if not dry_run:
                                cursor.execute(query, [row[column] for column in columns])
                                inserted += max(int(cursor.rowcount or 0), 0)
                    if dry_run:
                        connection.rollback()
                    else:
                        connection.commit()
        except (Conflict, Denied):
            raise
        except Exception as exc:
            raise Conflict(f"PostgreSQL migration {'validation' if dry_run else 'apply'} failed: {exc}") from exc
        detail = {
            "dry_run": bool(dry_run), "tables": len(rows_by_table), "rows_examined": examined,
            "rows_inserted": 0 if dry_run else inserted,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "target_schema_preexisting": True,
        }
        state = "validated" if dry_run else "applied"
        with self.db.connection() as db:
            manifest = _decode(export.get("manifest_json"), {})
            manifest["postgresql_apply"] = {**detail, "performed_by": actor, "performed_at": now()}
            db.execute("UPDATE education_database_migration_exports SET state=?,manifest_json=? WHERE id=?", (state, _json(manifest), export_id))
            readiness = _decode(profile.get("readiness_json"), {})
            readiness.update({"network_verified": True, "credentials_verified": True, "migration_contract_ready": True, "migration_dry_run_verified": bool(dry_run), "migration_applied": not dry_run})
            db.execute("UPDATE education_database_profiles SET state=?,readiness_json=?,updated_at=? WHERE id=?", ("migration_validated" if dry_run else "production_ready", _json(readiness), now(), profile_id))
        return {"export_id": export_id, "profile_id": profile_id, "state": state, **detail}

    # ---------- external S3/MinIO transfers ----------
    def _storage_backend_and_client(self, actor: str, backend_id: str):
        backend = self.platform._one("SELECT * FROM education_storage_backends WHERE id=?", (backend_id,))
        if not backend:
            raise Missing("Storage backend not found.")
        self.permissions.require(actor, backend["institution_id"], "storage.manage")
        if backend["backend_type"] not in {"s3", "minio"}:
            raise Conflict("External object transfer requires an S3 or MinIO backend.")
        credentials = _decode(_environment_secret(backend["secret_reference"]), {})
        if not isinstance(credentials, dict):
            raise Conflict("Storage secret must be a JSON object.")
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise Conflict("boto3 is required for live S3/MinIO transfers. Install requirements-production.txt.") from exc
        client = boto3.client(
            "s3", endpoint_url=backend["endpoint"] or None, region_name=backend["region"] or None,
            aws_access_key_id=credentials.get("aws_access_key_id"),
            aws_secret_access_key=credentials.get("aws_secret_access_key"),
            aws_session_token=credentials.get("aws_session_token"),
        )
        return backend, client

    def upload_external_object(self, actor: str, backend_id: str, source_path: str | Path, object_key: str) -> dict[str, Any]:
        backend, client = self._storage_backend_and_client(actor, backend_id)
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise Missing("Source file not found.")
        key = str(object_key).strip().lstrip("/")
        if not key or ".." in Path(key).parts:
            raise EducationError("Unsafe object key.")
        sha = _sha256_file(source)
        size = source.stat().st_size
        transfer_id, stamp = ident("xfer"), now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_storage_transfers VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (transfer_id, backend["institution_id"], backend_id, key, str(source), "upload", sha, size, "", "processing", "{}", actor, stamp, stamp),
            )
        try:
            with source.open("rb") as handle:
                client.upload_fileobj(handle, backend["bucket"], key, ExtraArgs={"Metadata": {"sha256": sha, "institution-id": backend["institution_id"]}})
            head = client.head_object(Bucket=backend["bucket"], Key=key)
            remote_sha = str((head.get("Metadata") or {}).get("sha256") or "")
            remote_size = int(head.get("ContentLength") or 0)
            if remote_size != size or not hmac.compare_digest(remote_sha, sha):
                raise Conflict("Remote object verification failed after upload.")
            etag = str(head.get("ETag") or "").strip('"')
            with self.db.connection() as db:
                db.execute("UPDATE education_storage_transfers SET state='verified',etag=?,detail_json=?,updated_at=? WHERE id=?", (etag, _json({"remote_size": remote_size, "metadata_sha256": remote_sha}), now(), transfer_id))
        except Exception as exc:
            with self.db.connection() as db:
                db.execute("UPDATE education_storage_transfers SET state='failed',detail_json=?,updated_at=? WHERE id=?", (_json({"error": str(exc)}), now(), transfer_id))
            raise Conflict(f"External object upload failed: {exc}") from exc
        return self.storage_transfer(actor, transfer_id)

    def storage_transfer(self, actor: str, transfer_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_storage_transfers WHERE id=?", (transfer_id,))
        if not row:
            raise Missing("Storage transfer not found.")
        self.platform._require(actor, row["institution_id"])
        row["detail"] = _decode(row.pop("detail_json", "{}"), {})
        return row

    # ---------- originality and human review ----------
    def _submission_text(self, submission: dict[str, Any]) -> str:
        pieces = [str(submission.get("body") or "")]
        path = Path(str(submission.get("file_path") or ""))
        if path.is_file() and path.stat().st_size <= 2 * 1024 * 1024 and path.suffix.lower() in {".txt", ".md", ".csv", ".json", ".py", ".r", ".fasta", ".fa"}:
            pieces.append(path.read_text(encoding="utf-8", errors="replace"))
        return "\n".join(pieces)

    def analyze_submission_originality(self, actor: str, submission_id: str, *, threshold: float = 0.35) -> dict[str, Any]:
        submission = self.platform._one(
            """SELECT s.*,a.subject_id FROM submissions s JOIN assignments a ON a.id=s.assignment_id WHERE s.id=?""",
            (submission_id,),
        )
        if not submission:
            raise Missing("Submission not found.")
        roles = self._roles(actor, submission["institution_id"])
        if actor != submission["student_id"] and not roles & TEACHER_ROLES:
            raise Denied("Submission originality is limited to the learner and authorized educators.")
        if submission["state"] != "submitted":
            raise Conflict("Only sealed final submissions may be analyzed.")
        text = self._submission_text(submission)
        normalized = _normalize_text(text)
        shingles = _shingles(normalized)
        stamp = now()
        fingerprint_id = ident("origfp")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_originality_fingerprints VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(submission_id) DO UPDATE SET text_sha256=excluded.text_sha256,normalized_text=excluded.normalized_text,
                shingles_json=excluded.shingles_json,token_count=excluded.token_count,updated_at=excluded.updated_at""",
                (fingerprint_id, submission["institution_id"], submission["subject_id"], submission_id, submission["student_id"], hashlib.sha256(normalized.encode()).hexdigest(), normalized, _json(sorted(shingles)), len(normalized.split()), stamp, stamp),
            )
        candidates = self.platform._all(
            """SELECT f.* FROM education_originality_fingerprints f
            WHERE f.institution_id=? AND f.subject_id=? AND f.submission_id<>? ORDER BY f.created_at""",
            (submission["institution_id"], submission["subject_id"], submission_id),
        )
        matches = []
        for candidate in candidates:
            score, overlap = _jaccard(shingles, set(_decode(candidate["shingles_json"], [])))
            if score < max(0.05, min(float(threshold), 1.0)):
                continue
            pair = tuple(sorted((submission_id, candidate["submission_id"])))
            match_id = ident("origmatch")
            with self.db.connection() as db:
                db.execute(
                    """INSERT INTO education_originality_matches VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(source_submission_id,candidate_submission_id) DO UPDATE SET similarity=excluded.similarity,
                    matched_shingles=excluded.matched_shingles,source_tokens=excluded.source_tokens,candidate_tokens=excluded.candidate_tokens,updated_at=excluded.updated_at""",
                    (match_id, submission["institution_id"], pair[0], pair[1], score, overlap, len(normalized.split()), candidate["token_count"], "needs_review", "", "", stamp, stamp),
                )
            matches.append({"candidate_submission_id": candidate["submission_id"], "similarity": round(score, 4), "matched_shingles": overlap, "state": "needs_review"})
        return {"submission_id": submission_id, "text_sha256": hashlib.sha256(normalized.encode()).hexdigest(), "token_count": len(normalized.split()), "comparison_count": len(candidates), "matches": sorted(matches, key=lambda item: item["similarity"], reverse=True), "automatic_penalty": False, "human_review_required": bool(matches)}

    def review_originality_match(self, actor: str, match_id: str, *, state: str, note: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_originality_matches WHERE id=?", (match_id,))
        if not row:
            raise Missing("Originality match not found.")
        if not self._roles(actor, row["institution_id"]) & TEACHER_ROLES:
            raise Denied("Educator permission required.")
        if state not in {"confirmed", "dismissed", "needs_revision", "appealed"}:
            raise EducationError("Unsupported originality review state.")
        if not str(note).strip():
            raise EducationError("Human review note is required.")
        with self.db.connection() as db:
            db.execute("UPDATE education_originality_matches SET state=?,reviewed_by=?,review_note=?,updated_at=? WHERE id=?", (state, actor, str(note).strip(), now(), match_id))
        return self.platform._one("SELECT * FROM education_originality_matches WHERE id=?", (match_id,))

    # ---------- examination governance and monitoring ----------
    def configure_exam_governance(self, actor: str, exam_id: str, *, paper_reviewer_id: str, answer_key_reviewer_id: str, controller_id: str, moderation_tolerance: float = 5.0) -> dict[str, Any]:
        exam = self.platform._one("SELECT * FROM examinations WHERE id=?", (exam_id,))
        if not exam:
            raise Missing("Examination not found.")
        self._admin(actor, exam["institution_id"])
        people = {paper_reviewer_id, answer_key_reviewer_id, controller_id}
        if exam["creator_id"] in people or len(people) != 3 or not all(people):
            raise Conflict("Paper author, reviewers and examination controller must be distinct accounts.")
        for person in people:
            if not self.platform.membership(person, exam["institution_id"]):
                raise Missing(f"Governance member {person} is not active in the institution.")
        if not 0 <= float(moderation_tolerance) <= 25:
            raise EducationError("Moderation tolerance must be between 0 and 25 percentage points.")
        stamp = now()
        governance_id = ident("exgov")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_exam_governance VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(exam_id) DO UPDATE SET paper_reviewer_id=excluded.paper_reviewer_id,
                answer_key_reviewer_id=excluded.answer_key_reviewer_id,controller_id=excluded.controller_id,
                moderation_tolerance=excluded.moderation_tolerance,updated_at=excluded.updated_at""",
                (governance_id, exam["institution_id"], exam_id, "paper_review", exam["creator_id"], paper_reviewer_id, answer_key_reviewer_id, controller_id, float(moderation_tolerance), None, None, None, actor, stamp, stamp),
            )
            row = db.execute("SELECT id FROM education_exam_governance WHERE exam_id=?", (exam_id,)).fetchone()
            governance_id = row["id"]
            db.execute("INSERT INTO education_exam_governance_events VALUES(?,?,?,?,?,?)", (ident("exge"), governance_id, actor, "governance_configured", _json({"paper_reviewer": paper_reviewer_id, "answer_key_reviewer": answer_key_reviewer_id, "controller": controller_id}), stamp))
        return self.exam_governance(actor, exam_id)

    def approve_exam_stage(self, actor: str, exam_id: str, stage: str, *, note: str = "") -> dict[str, Any]:
        governance = self.platform._one("SELECT * FROM education_exam_governance WHERE exam_id=?", (exam_id,))
        if not governance:
            raise Missing("Examination governance is not configured.")
        required = {"paper": ("paper_review", "paper_reviewer_id", "answer_key_review", "paper_approved_at"), "answer_key": ("answer_key_review", "answer_key_reviewer_id", "controller_approval", "answer_key_approved_at"), "controller": ("controller_approval", "controller_id", "scheduled", "controller_approved_at")}
        if stage not in required:
            raise EducationError("Stage must be paper, answer_key or controller.")
        current, role_field, next_state, time_field = required[stage]
        if governance["lifecycle_state"] != current:
            raise Conflict(f"Examination is not awaiting {stage} approval.")
        if actor != governance[role_field]:
            raise Denied("This approval is assigned to a different reviewer.")
        stamp = now()
        with self.db.connection() as db:
            db.execute(f"UPDATE education_exam_governance SET lifecycle_state=?,{time_field}=?,updated_at=? WHERE id=?", (next_state, stamp, stamp, governance["id"]))
            db.execute("INSERT INTO education_exam_governance_events VALUES(?,?,?,?,?,?)", (ident("exge"), governance["id"], actor, f"{stage}_approved", _json({"note": str(note).strip()}), stamp))
        return self.exam_governance(actor, exam_id)

    def transition_exam_lifecycle(self, actor: str, exam_id: str, target: str, *, reason: str = "") -> dict[str, Any]:
        governance = self.platform._one("SELECT * FROM education_exam_governance WHERE exam_id=?", (exam_id,))
        if not governance:
            raise Missing("Examination governance is not configured.")
        self._admin(actor, governance["institution_id"])
        if target not in EXAM_LIFECYCLE:
            raise EducationError("Unsupported examination lifecycle state.")
        allowed = {
            "scheduled": {"live", "cancelled"}, "live": {"grading", "cancelled"},
            "grading": {"moderation"}, "moderation": {"published"}, "published": {"archived"},
        }
        if target not in allowed.get(governance["lifecycle_state"], set()):
            raise Conflict(f"Cannot transition examination from {governance['lifecycle_state']} to {target}.")
        if target == "cancelled" and not str(reason).strip():
            raise EducationError("Cancellation reason is required.")
        with self.db.connection() as db:
            db.execute("UPDATE education_exam_governance SET lifecycle_state=?,updated_at=? WHERE id=?", (target, now(), governance["id"]))
            db.execute("INSERT INTO education_exam_governance_events VALUES(?,?,?,?,?,?)", (ident("exge"), governance["id"], actor, "lifecycle_transition", _json({"from": governance["lifecycle_state"], "to": target, "reason": reason}), now()))
        return self.exam_governance(actor, exam_id)

    def submit_exam_evaluation(self, actor: str, session_id: str, *, stage: str, score: float, max_score: float, comments: str = "", rubric: dict[str, Any] | None = None) -> dict[str, Any]:
        session = self.platform._one("SELECT * FROM education_exam_sessions WHERE id=?", (session_id,))
        if not session:
            raise Missing("Examination session not found.")
        governance = self.platform._one("SELECT * FROM education_exam_governance WHERE exam_id=?", (session["exam_id"],))
        if not governance:
            raise Missing("Examination governance is not configured.")
        if stage not in {"first", "second", "moderator"}:
            raise EducationError("Evaluation stage must be first, second or moderator.")
        roles = self._roles(actor, session["institution_id"])
        if not roles & TEACHER_ROLES:
            raise Denied("Authorized examiner permission required.")
        if stage == "second":
            first = self.platform._one("SELECT examiner_id FROM education_exam_evaluations WHERE session_id=? AND stage='first'", (session_id,))
            if not first:
                raise Conflict("First evaluation is required before second evaluation.")
            if first["examiner_id"] == actor:
                raise Denied("Second evaluation must be independent.")
        if stage == "moderator":
            previous = self.platform._all("SELECT examiner_id FROM education_exam_evaluations WHERE session_id=? AND stage IN ('first','second')", (session_id,))
            if len(previous) < 2:
                raise Conflict("Two examiner evaluations are required before moderation.")
            if actor in {row["examiner_id"] for row in previous}:
                raise Denied("Moderator must be independent from both examiners.")
        score_value, maximum = float(score), float(max_score)
        if maximum <= 0 or not 0 <= score_value <= maximum:
            raise EducationError("Evaluation score must be within the assessment maximum.")
        stamp = now()
        evaluation_id = ident("xeval")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_exam_evaluations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(session_id,examiner_id,stage) DO UPDATE SET score=excluded.score,max_score=excluded.max_score,
                rubric_json=excluded.rubric_json,comments=excluded.comments,updated_at=excluded.updated_at""",
                (evaluation_id, session["institution_id"], session["exam_id"], session_id, actor, stage, score_value, maximum, _json(rubric or {}), str(comments), "submitted", stamp, stamp),
            )
        return self.exam_evaluation_summary(actor, session_id)

    def exam_evaluation_summary(self, actor: str, session_id: str) -> dict[str, Any]:
        session = self.platform._one("SELECT * FROM education_exam_sessions WHERE id=?", (session_id,))
        if not session:
            raise Missing("Examination session not found.")
        roles = self._roles(actor, session["institution_id"])
        if actor != session["student_id"] and not roles & TEACHER_ROLES:
            raise Denied("Evaluation summary is restricted.")
        rows = self.platform._all("SELECT * FROM education_exam_evaluations WHERE session_id=? ORDER BY created_at", (session_id,))
        governance = self.platform._one("SELECT moderation_tolerance FROM education_exam_governance WHERE exam_id=?", (session["exam_id"],)) or {"moderation_tolerance": 5}
        normalized = [(float(row["score"]) / float(row["max_score"]) * 100) for row in rows if float(row["max_score"]) > 0 and row["stage"] in {"first", "second"}]
        difference = abs(normalized[0] - normalized[1]) if len(normalized) >= 2 else None
        moderator = next((row for row in rows if row["stage"] == "moderator"), None)
        final_percent = float(moderator["score"]) / float(moderator["max_score"]) * 100 if moderator else sum(normalized) / len(normalized) if normalized else None
        return {"session_id": session_id, "evaluations": rows, "difference_percent": round(difference, 2) if difference is not None else None, "moderation_required": difference is not None and difference > float(governance["moderation_tolerance"]), "final_percent": round(final_percent, 2) if final_percent is not None else None}

    def submit_exam_appeal(self, actor: str, session_id: str, reason: str) -> dict[str, Any]:
        session = self.platform._one("SELECT * FROM education_exam_sessions WHERE id=?", (session_id,))
        if not session or session["student_id"] != actor:
            raise Denied("Students may appeal only their own examination session.")
        if not str(reason).strip():
            raise EducationError("Appeal reason is required.")
        score = self.platform._one("SELECT final_score FROM education_exam_scores WHERE session_id=? AND released=1", (session_id,))
        if not score:
            raise Conflict("Only released results may be appealed.")
        appeal_id, stamp = ident("appeal"), now()
        with self.db.connection() as db:
            db.execute("INSERT INTO education_exam_appeals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (appeal_id, session["institution_id"], session["exam_id"], session_id, actor, str(reason).strip(), "submitted", "", "", float(score["final_score"]), None, stamp, stamp, None))
        return self.platform._one("SELECT * FROM education_exam_appeals WHERE id=?", (appeal_id,))

    def decide_exam_appeal(self, actor: str, appeal_id: str, *, state: str, note: str, revised_score: float | None = None) -> dict[str, Any]:
        appeal = self.platform._one("SELECT * FROM education_exam_appeals WHERE id=?", (appeal_id,))
        if not appeal:
            raise Missing("Examination appeal not found.")
        self._admin(actor, appeal["institution_id"])
        if state not in {"accepted", "rejected", "completed"} or not str(note).strip():
            raise EducationError("Appeal decision and note are required.")
        if revised_score is not None and float(revised_score) < 0:
            raise EducationError("Revised score cannot be negative.")
        stamp = now()
        with self.db.connection() as db:
            db.execute("UPDATE education_exam_appeals SET state=?,assigned_to=?,decision_note=?,revised_score=?,updated_at=?,resolved_at=? WHERE id=?", (state, actor, str(note).strip(), revised_score, stamp, stamp, appeal_id))
        return self.platform._one("SELECT * FROM education_exam_appeals WHERE id=?", (appeal_id,))

    def record_exam_heartbeat(self, actor: str, session_id: str, *, connection_state: str = "online", current_question_id: str = "", answered_count: int = 0, client_clock_offset_ms: int = 0, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        session = self.platform._one("SELECT * FROM education_exam_sessions WHERE id=?", (session_id,))
        if not session or session["student_id"] != actor:
            raise Denied("Exam heartbeat may be recorded only by the session owner.")
        if connection_state not in {"online", "unstable", "offline", "reconnected"}:
            raise EducationError("Unsupported connection state.")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_exam_heartbeats VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET connection_state=excluded.connection_state,
                current_question_id=excluded.current_question_id,answered_count=excluded.answered_count,
                client_clock_offset_ms=excluded.client_clock_offset_ms,detail_json=excluded.detail_json,last_seen_at=excluded.last_seen_at""",
                (session_id, session["institution_id"], session["exam_id"], actor, connection_state, current_question_id, max(0, int(answered_count)), int(client_clock_offset_ms), _json(detail or {}), stamp),
            )
        return self.platform._one("SELECT * FROM education_exam_heartbeats WHERE session_id=?", (session_id,))

    def live_exam_monitor(self, actor: str, exam_id: str, *, stale_seconds: int = 45) -> dict[str, Any]:
        exam = self.platform._one("SELECT * FROM examinations WHERE id=?", (exam_id,))
        if not exam or not self._roles(actor, exam["institution_id"]) & TEACHER_ROLES:
            raise Denied("Live examination monitoring requires educator permission.")
        rows = self.platform._all(
            """SELECT s.id session_id,s.student_id,s.state session_state,s.started_at,s.submitted_at,s.last_seen_at,
            h.connection_state,h.current_question_id,h.answered_count,h.client_clock_offset_ms,h.last_seen_at heartbeat_at,
            (SELECT COUNT(*) FROM education_exam_events e WHERE e.session_id=s.id) integrity_events
            FROM education_exam_sessions s LEFT JOIN education_exam_heartbeats h ON h.session_id=s.id
            WHERE s.exam_id=? ORDER BY s.student_id""",
            (exam_id,),
        )
        current = datetime.now(timezone.utc)
        for row in rows:
            seen = row.get("heartbeat_at") or row.get("last_seen_at")
            age = (current - parse_time(seen)).total_seconds() if seen else math.inf
            row["heartbeat_age_seconds"] = round(age, 1) if math.isfinite(age) else None
            row["online"] = bool(age <= max(10, int(stale_seconds)) and row.get("connection_state") != "offline")
        return {"exam_id": exam_id, "candidates": rows, "online": sum(1 for row in rows if row["online"]), "offline": sum(1 for row in rows if not row["online"]), "generated_at": now()}

    def exam_governance(self, actor: str, exam_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_exam_governance WHERE exam_id=?", (exam_id,))
        if not row:
            raise Missing("Examination governance not found.")
        self.platform._require(actor, row["institution_id"])
        row["events"] = self.platform._all("SELECT * FROM education_exam_governance_events WHERE governance_id=? ORDER BY created_at", (row["id"],))
        return row

    # ---------- Shiro model and RAG governance ----------
    def register_ai_model_profile(self, actor: str, institution_id: str, name: str, *, provider_type: str, model_name: str, endpoint: str = "", embedding_model: str = "", reranker_model: str = "", secret_reference: str = "", context_window: int = 4096, activate: bool = False) -> dict[str, Any]:
        self._admin(actor, institution_id)
        provider = str(provider_type).lower().strip()
        if provider not in MODEL_PROVIDERS:
            raise EducationError("Unsupported AI model provider.")
        if not 512 <= int(context_window) <= 2_000_000:
            raise EducationError("Model context window is outside supported bounds.")
        if secret_reference and not str(secret_reference).startswith("env:"):
            raise Denied("AI provider secrets must use env:VARIABLE references.")
        readiness = {
            "provider_supported": True,
            "endpoint_present": bool(endpoint) or provider in {"local_file", "disabled"},
            "model_name_present": bool(str(model_name).strip()),
            "secret_reference_present": bool(secret_reference) or provider in {"ollama", "local_file", "disabled"},
            "live_verified": False,
        }
        state = "configuration_ready" if activate and all(value for key, value in readiness.items() if key != "live_verified") else "draft"
        profile_id, stamp = ident("aimodel"), now()
        with self.db.connection() as db:
            db.execute("INSERT INTO education_ai_model_profiles VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (profile_id, institution_id, str(name).strip(), provider, str(endpoint).strip(), str(model_name).strip(), str(embedding_model).strip(), str(reranker_model).strip(), str(secret_reference).strip(), int(context_window), state, _json(readiness), actor, stamp, stamp))
        return self.ai_model_profile(actor, profile_id)

    def qualify_ai_model_profile(self, actor: str, profile_id: str) -> dict[str, Any]:
        profile = self.platform._one("SELECT * FROM education_ai_model_profiles WHERE id=?", (profile_id,))
        if not profile:
            raise Missing("AI model profile not found.")
        self._admin(actor, profile["institution_id"])
        readiness = _decode(profile["readiness_json"], {})
        evidence: dict[str, Any] = {"provider": profile["provider_type"], "model_name": profile["model_name"]}
        verified = False
        error = ""
        try:
            if profile["provider_type"] == "ollama":
                endpoint = str(profile["endpoint"] or "http://127.0.0.1:11434").rstrip("/")
                parsed = urllib.parse.urlparse(endpoint)
                if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} and parsed.scheme != "https":
                    raise Denied("Remote Ollama endpoints must use HTTPS.")
                with urllib.request.urlopen(endpoint + "/api/tags", timeout=5) as response:
                    data = json.loads(response.read(524288))
                models = [str(item.get("name") or "") for item in data.get("models", [])]
                verified = profile["model_name"] in models or any(name.startswith(profile["model_name"] + ":") for name in models)
                evidence["available_models"] = models[:50]
            elif profile["provider_type"] == "openai_compatible":
                status, payload, _, latency = _fetch_json(str(profile["endpoint"]).rstrip("/") + "/models", token=_environment_secret(profile["secret_reference"]))
                verified = 200 <= status < 300
                evidence.update({"http_status": status, "latency_ms": latency, "response_keys": sorted(payload)[:20]})
            elif profile["provider_type"] == "local_file":
                path = Path(profile["endpoint"]).expanduser().resolve()
                verified = path.is_file()
                evidence.update({"path": str(path), "size_bytes": path.stat().st_size if path.is_file() else 0, "sha256": _sha256_file(path) if path.is_file() else ""})
            else:
                verified = True
                evidence["disabled_by_policy"] = True
        except Exception as exc:
            error = str(exc)
        readiness["live_verified"] = bool(verified)
        readiness["last_evidence"] = evidence
        readiness["last_error"] = error
        with self.db.connection() as db:
            db.execute("UPDATE education_ai_model_profiles SET state=?,readiness_json=?,updated_at=? WHERE id=?", ("verified" if verified else "qualification_failed", _json(readiness), now(), profile_id))
        return self.ai_model_profile(actor, profile_id)

    def ai_model_profile(self, actor: str, profile_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_ai_model_profiles WHERE id=?", (profile_id,))
        if not row:
            raise Missing("AI model profile not found.")
        self.platform._require(actor, row["institution_id"])
        row["readiness"] = _decode(row.pop("readiness_json", "{}"), {})
        row["secret_reference"] = "configured" if row.get("secret_reference") else "missing"
        return row

    def runtime_hardware_posture(self) -> dict[str, Any]:
        memory_bytes = 0
        try:
            if hasattr(os, "sysconf"):
                memory_bytes = int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
        except (ValueError, OSError):
            memory_bytes = 0
        gpu = []
        try:
            output = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=4, check=False)
            if output.returncode == 0:
                for line in output.stdout.splitlines():
                    name, _, memory = line.partition(",")
                    gpu.append({"name": name.strip(), "memory_mib": int(memory.strip()) if memory.strip().isdigit() else None})
        except (OSError, subprocess.SubprocessError):
            pass
        return {"os": runtime_platform.platform(), "python": sys.version.split()[0], "cpu_count": os.cpu_count() or 1, "memory_bytes": memory_bytes, "gpus": gpu, "recommended_quantization": "Q4/Q5" if not gpu else "Q5/Q8 depending on VRAM"}

    def register_rag_document(self, actor: str, institution_id: str, project_id: str, source_path: str | Path, *, title: str = "", permissions: dict[str, Any] | None = None) -> dict[str, Any]:
        roles = self._roles(actor, institution_id)
        if not roles & TEACHER_ROLES:
            raise Denied("RAG source registration requires educator permission.")
        path = Path(source_path).expanduser().resolve()
        if not path.is_file():
            raise Missing("RAG source file not found.")
        if path.stat().st_size > 250 * 1024 * 1024:
            raise EducationError("RAG source exceeds 250 MiB.")
        sample = path.read_bytes()[:2_000_000]
        text = sample.decode("utf-8", errors="ignore")
        findings = sorted({pattern for pattern in INJECTION_PATTERNS if re.search(pattern, text, flags=re.IGNORECASE)})
        sha = _sha256_file(path)
        existing = self.platform._one("SELECT * FROM education_rag_documents WHERE institution_id=? AND project_id=? AND sha256=?", (institution_id, project_id, sha))
        if existing:
            return existing
        state = "quarantined" if findings else "registered"
        document_id, stamp = ident("ragdoc"), now()
        with self.db.connection() as db:
            db.execute("INSERT INTO education_rag_documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (document_id, institution_id, str(project_id), str(title or path.stem), str(path), path.name, mimetypes.guess_type(path.name)[0] or "application/octet-stream", sha, path.stat().st_size, 1, _json(permissions or {"roles": ["subject_teacher", "university_student"]}), _json({"prompt_injection_patterns": findings, "sample_bytes_scanned": len(sample)}), state, actor, stamp, stamp))
        return self.rag_document(actor, document_id)

    def rag_document(self, actor: str, document_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_rag_documents WHERE id=?", (document_id,))
        if not row:
            raise Missing("RAG document not found.")
        self.platform._require(actor, row["institution_id"])
        row["permissions"] = _decode(row.pop("permission_json", "{}"), {})
        row["safety"] = _decode(row.pop("safety_json", "{}"), {})
        return row

    def approve_rag_document(self, actor: str, document_id: str, *, approve: bool, reason: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_rag_documents WHERE id=?", (document_id,))
        if not row:
            raise Missing("RAG document not found.")
        self._admin(actor, row["institution_id"])
        if not str(reason).strip():
            raise EducationError("RAG review reason is required.")
        safety = _decode(row["safety_json"], {})
        safety["human_review"] = {"approved": bool(approve), "reason": str(reason).strip(), "reviewed_by": actor, "reviewed_at": now()}
        with self.db.connection() as db:
            db.execute("UPDATE education_rag_documents SET state=?,safety_json=?,updated_at=? WHERE id=?", ("approved" if approve else "rejected", _json(safety), now(), document_id))
        return self.rag_document(actor, document_id)

    def record_rag_evaluation(self, actor: str, institution_id: str, project_id: str, query_text: str, *, expected_refs: list[str], retrieved_refs: list[str], cited_refs: list[str]) -> dict[str, Any]:
        if not self._roles(actor, institution_id) & TEACHER_ROLES:
            raise Denied("RAG evaluation requires educator permission.")
        expected, retrieved, cited = set(expected_refs), list(dict.fromkeys(retrieved_refs)), set(cited_refs)
        recall = len(expected & set(retrieved)) / len(expected) if expected else 1.0
        coverage = len(set(retrieved) & cited) / len(set(retrieved)) if retrieved else 1.0
        evaluation_id = ident("rageval")
        with self.db.connection() as db:
            db.execute("INSERT INTO education_rag_evaluations VALUES(?,?,?,?,?,?,?,?,?,?,?)", (evaluation_id, institution_id, str(project_id), str(query_text), _json(sorted(expected)), _json(retrieved), recall, coverage, int(recall >= 0.8 and coverage >= 0.8), actor, now()))
        return self.platform._one("SELECT * FROM education_rag_evaluations WHERE id=?", (evaluation_id,))

    # ---------- notification providers ----------
    def configure_delivery_provider(self, actor: str, institution_id: str, channel: str, name: str, *, endpoint: str = "", sender: str = "", secret_reference: str = "", settings: dict[str, Any] | None = None, activate: bool = False) -> dict[str, Any]:
        self._admin(actor, institution_id)
        channel = str(channel).lower().strip()
        if channel not in DELIVERY_CHANNELS:
            raise EducationError("Unsupported delivery channel.")
        if secret_reference and not str(secret_reference).startswith("env:"):
            raise Denied("Provider credentials must use env:VARIABLE references.")
        if channel in {"webhook", "sms", "whatsapp"} and activate:
            _validate_public_https(endpoint)
        readiness = {"endpoint_present": bool(endpoint) or channel in {"desktop", "in_app", "smtp"}, "secret_reference_present": bool(secret_reference) or channel in {"desktop", "in_app"}, "live_verified": channel in {"desktop", "in_app"}}
        provider_id, stamp = ident("delivery"), now()
        with self.db.connection() as db:
            db.execute("INSERT INTO education_delivery_providers VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (provider_id, institution_id, channel, str(name).strip(), str(endpoint).strip(), str(sender).strip(), str(secret_reference).strip(), _json(settings or {}), "verified" if readiness["live_verified"] else "configuration_ready" if activate else "draft", _json(readiness), actor, stamp, stamp))
        return self.delivery_provider(actor, provider_id)

    def delivery_provider(self, actor: str, provider_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_delivery_providers WHERE id=?", (provider_id,))
        if not row:
            raise Missing("Delivery provider not found.")
        self.platform._require(actor, row["institution_id"])
        row["settings"] = _decode(row.pop("settings_json", "{}"), {})
        row["readiness"] = _decode(row.pop("readiness_json", "{}"), {})
        row["secret_reference"] = "configured" if row.get("secret_reference") else "missing"
        return row

    def deliver_signed_webhook(self, actor: str, provider_id: str, payload: dict[str, Any], *, event_type: str, idempotency_key: str) -> dict[str, Any]:
        provider = self.platform._one("SELECT * FROM education_delivery_providers WHERE id=?", (provider_id,))
        if not provider or provider["channel"] not in {"webhook", "sms", "whatsapp"}:
            raise Missing("HTTP delivery provider not found.")
        self._admin(actor, provider["institution_id"])
        endpoint = str(provider["endpoint"])
        _validate_public_https(endpoint)
        secret = _environment_secret(provider["secret_reference"])
        body = _json({"event_type": event_type, "idempotency_key": idempotency_key, "institution_id": provider["institution_id"], "payload": payload, "sent_at": now()}).encode("utf-8")
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        request = urllib.request.Request(endpoint, data=body, method="POST", headers={"Content-Type": "application/json", "X-BioIntel-Signature": "sha256=" + signature, "Idempotency-Key": idempotency_key, "User-Agent": "BioIntel-Phase12/15.6"})
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=15, context=ssl.create_default_context()) as response:
                response_body = response.read(65536).decode("utf-8", errors="replace")
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            response_body = exc.read(65536).decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise Conflict(f"Provider delivery failed: {exc}") from exc
        if not 200 <= status < 300:
            raise Conflict(f"Provider returned HTTP {status}: {response_body[:500]}")
        return {"delivered": True, "http_status": status, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "response_excerpt": response_body[:1000], "idempotency_key": idempotency_key}

    # ---------- release qualification and completion posture ----------
    def record_release_qualification(self, actor: str, institution_id: str, qualification_type: str, *, state: str, evidence: dict[str, Any]) -> dict[str, Any]:
        self._admin(actor, institution_id)
        if state not in {"passed", "failed", "not_run", "external_required"}:
            raise EducationError("Unsupported qualification state.")
        qualification_id = ident("releaseq")
        with self.db.connection() as db:
            db.execute("INSERT INTO education_release_qualifications VALUES(?,?,?,?,?,?,?)", (qualification_id, institution_id, str(qualification_type), state, _json(evidence), actor, now()))
        return self.platform._one("SELECT * FROM education_release_qualifications WHERE id=?", (qualification_id,))

    def final_completion_posture(self, actor: str, institution_id: str) -> dict[str, Any]:
        self.platform._require(actor, institution_id)
        count = lambda sql: int((self.platform._one(sql, (institution_id,)) or {"n": 0})["n"])
        model_profiles = count("SELECT COUNT(*) n FROM education_ai_model_profiles WHERE institution_id=?")
        approved_rag = count("SELECT COUNT(*) n FROM education_rag_documents WHERE institution_id=? AND state='approved'")
        governed_exams = count("SELECT COUNT(*) n FROM education_exam_governance WHERE institution_id=?")
        originality = count("SELECT COUNT(*) n FROM education_originality_fingerprints WHERE institution_id=?")
        providers = count("SELECT COUNT(*) n FROM education_delivery_providers WHERE institution_id=?")
        exports = count("SELECT COUNT(*) n FROM education_database_migration_exports WHERE institution_id=?")
        external = self.external_dependency_posture(actor, institution_id)
        local_score = min(100, 45 + min(10, governed_exams * 3) + min(10, originality * 2) + min(10, approved_rag * 3) + min(10, model_profiles * 3) + min(5, providers * 2) + min(10, exports * 5))
        return {
            "institution_id": institution_id,
            "local_code_completion_score": local_score,
            "governed_exams": governed_exams,
            "originality_fingerprints": originality,
            "approved_rag_documents": approved_rag,
            "ai_model_profiles": model_profiles,
            "delivery_providers": providers,
            "database_migration_exports": exports,
            "external_dependencies": external,
            "external_qualification_still_required": [
                "Signed Windows MSI/EXE and SmartScreen reputation",
                "Live identity-provider credentials and provider-side approval",
                "Live PostgreSQL/S3/MinIO migration and failover drills",
                "Independent penetration, load and WCAG audits",
                "Real institution pilot and legal/compliance approval",
            ],
        }
