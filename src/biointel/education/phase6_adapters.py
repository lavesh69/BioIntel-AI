from __future__ import annotations

import ipaddress
import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .permissions import PermissionService
from .platform import Conflict, Denied, EducationError, Missing, ident, now

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS education_external_qualifications(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 target_type TEXT NOT NULL,
 target_id TEXT NOT NULL,
 qualification_type TEXT NOT NULL,
 state TEXT NOT NULL,
 latency_ms REAL,
 evidence_json TEXT NOT NULL DEFAULT '{}',
 error_text TEXT NOT NULL DEFAULT '',
 checked_by TEXT NOT NULL,
 checked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_external_qualification_target
 ON education_external_qualifications(institution_id,target_type,target_id,checked_at);
"""


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _decode(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError):
        return fallback


def _environment_secret(reference: str) -> str:
    text = str(reference or "").strip()
    if not text:
        return ""
    if not text.startswith("env:"):
        raise Conflict("Runtime verification accepts only env:VARIABLE secret references.")
    name = text[4:].strip()
    if not name or not name.replace("_", "").isalnum():
        raise EducationError("Invalid environment secret reference.")
    value = os.environ.get(name, "")
    if not value:
        raise Conflict(f"Environment secret {name} is not configured on this machine.")
    return value


def _public_addresses(hostname: str) -> list[str]:
    try:
        results = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise Conflict(f"Hostname resolution failed: {exc}") from exc
    addresses = sorted({row[4][0] for row in results})
    for value in addresses:
        address = ipaddress.ip_address(value.split("%")[0])
        if any((address.is_private, address.is_loopback, address.is_link_local, address.is_multicast, address.is_reserved, address.is_unspecified)):
            raise Denied("Private, loopback, link-local and reserved network targets are blocked.")
    return addresses


def _validate_public_https(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise EducationError("External verification requires a public HTTPS URL.")
    if parsed.username or parsed.password:
        raise Denied("Credentials must not be embedded in URLs.")
    _public_addresses(parsed.hostname)
    return parsed


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        _validate_public_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_json(url: str, *, token: str = "", timeout: float = 10.0) -> tuple[int, dict[str, Any], dict[str, str], float]:
    _validate_public_https(url)
    headers = {"User-Agent": "BioIntel-Education-Qualification/15.6", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()), _SafeRedirect())
    started = time.perf_counter()
    try:
        with opener.open(request, timeout=max(2.0, min(float(timeout), 20.0))) as response:
            payload = response.read(262_145)
            if len(payload) > 262_144:
                raise Conflict("Verification response exceeded the 256 KiB safety limit.")
            status = int(response.status)
            response_headers = {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        payload = exc.read(32_768)
        response_headers = {key.lower(): value for key, value in exc.headers.items()}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Conflict(f"External verification failed: {exc}") from exc
    latency = round((time.perf_counter() - started) * 1000, 2)
    try:
        data = json.loads(payload.decode("utf-8", errors="strict")) if payload else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = {"response_excerpt": payload.decode("utf-8", errors="replace")[:2000]}
    return status, data if isinstance(data, dict) else {"value": data}, response_headers, latency


class ExternalQualificationService:
    """Runs explicit, bounded external checks without ever returning configured secrets."""

    def __init__(self, platform: Any):
        self.platform = platform
        self.db = platform.db
        self.permissions = PermissionService(platform)
        with self.db.connection() as db:
            db.executescript(SCHEMA)

    def _store(self, actor: str, institution_id: str, target_type: str, target_id: str, qualification_type: str, state: str, *, latency_ms: float | None = None, evidence: dict[str, Any] | None = None, error_text: str = "") -> dict[str, Any]:
        qualification_id = ident("qual")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_external_qualifications VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (qualification_id, institution_id, target_type, target_id, qualification_type, state, latency_ms, _json(evidence or {}), error_text[:4000], actor, now()),
            )
        row = self.platform._one("SELECT * FROM education_external_qualifications WHERE id=?", (qualification_id,))
        row["evidence"] = _decode(row.pop("evidence_json", "{}"), {})
        return row

    def history(self, actor: str, institution_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        self.platform._require(actor, institution_id)
        if not self.permissions.has(actor, institution_id, "institution.manage"):
            raise Denied("External qualification history requires institution management permission.")
        rows = self.platform._all(
            "SELECT * FROM education_external_qualifications WHERE institution_id=? ORDER BY checked_at DESC LIMIT ?",
            (institution_id, max(1, min(int(limit), 500))),
        )
        for row in rows:
            row["evidence"] = _decode(row.pop("evidence_json", "{}"), {})
        return rows

    def verify_identity_provider(self, actor: str, provider_id: str) -> dict[str, Any]:
        provider = self.platform._one("SELECT * FROM education_identity_providers WHERE id=?", (provider_id,))
        if not provider:
            raise Missing("Identity provider not found.")
        institution_id = provider["institution_id"]
        self.permissions.require(actor, institution_id, "identity.manage")
        if provider["provider_type"] not in {"oidc", "google_workspace", "microsoft_entra"}:
            raise Conflict("Automated metadata verification currently supports OIDC-compatible providers.")
        issuer = str(provider["issuer_url"] or "").rstrip("/")
        if not issuer:
            raise Conflict("Issuer URL is missing.")
        url = issuer + "/.well-known/openid-configuration"
        try:
            status, payload, headers, latency = _fetch_json(url)
            valid = 200 <= status < 300 and str(payload.get("issuer", "")).rstrip("/") == issuer
            evidence = {
                "http_status": status,
                "issuer_match": valid,
                "authorization_endpoint_present": bool(payload.get("authorization_endpoint")),
                "token_endpoint_present": bool(payload.get("token_endpoint")),
                "jwks_uri_present": bool(payload.get("jwks_uri")),
                "content_type": headers.get("content-type", ""),
            }
            return self._store(actor, institution_id, "identity_provider", provider_id, "oidc_metadata", "verified" if valid else "failed", latency_ms=latency, evidence=evidence, error_text="" if valid else "OIDC metadata did not match the configured issuer.")
        except EducationError as exc:
            return self._store(actor, institution_id, "identity_provider", provider_id, "oidc_metadata", "failed", error_text=str(exc))

    def verify_database_profile(self, actor: str, profile_id: str) -> dict[str, Any]:
        profile = self.platform._one("SELECT * FROM education_database_profiles WHERE id=?", (profile_id,))
        if not profile:
            raise Missing("Database profile not found.")
        institution_id = profile["institution_id"]
        self.permissions.require(actor, institution_id, "database.manage")
        if profile["engine"] == "sqlite":
            started = time.perf_counter()
            valid = self.db.quick_check()
            return self._store(actor, institution_id, "database_profile", profile_id, "database_connection", "verified" if valid else "failed", latency_ms=round((time.perf_counter() - started) * 1000, 2), evidence={"engine": "sqlite", "quick_check": bool(valid)})
        if profile["engine"] != "postgresql":
            raise Conflict("Unsupported database engine.")
        try:
            dsn = _environment_secret(profile["dsn_reference"])
            import psycopg  # type: ignore
            started = time.perf_counter()
            with psycopg.connect(dsn, connect_timeout=8, autocommit=True) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT current_database(), current_user, current_setting('server_version')")
                    database, user, version = cursor.fetchone()
            latency = round((time.perf_counter() - started) * 1000, 2)
            return self._store(actor, institution_id, "database_profile", profile_id, "database_connection", "verified", latency_ms=latency, evidence={"engine": "postgresql", "database": database, "user": user, "server_version": version, "ssl_mode": profile["ssl_mode"]})
        except Exception as exc:  # driver/network failures are stored as qualification evidence
            return self._store(actor, institution_id, "database_profile", profile_id, "database_connection", "failed", error_text=str(exc))

    def verify_storage_backend(self, actor: str, backend_id: str) -> dict[str, Any]:
        backend = self.platform._one("SELECT * FROM education_storage_backends WHERE id=?", (backend_id,))
        if not backend:
            raise Missing("Storage backend not found.")
        institution_id = backend["institution_id"]
        self.permissions.require(actor, institution_id, "storage.manage")
        if backend["backend_type"] == "local":
            return self._store(actor, institution_id, "storage_backend", backend_id, "storage_connection", "verified", evidence={"backend": "local", "path": "governed local object store"})
        try:
            raw = _environment_secret(backend["secret_reference"])
            credentials = json.loads(raw)
            if not isinstance(credentials, dict):
                raise EducationError("Storage credential environment value must be a JSON object.")
            import boto3  # type: ignore
            client = boto3.client(
                "s3",
                endpoint_url=backend["endpoint"] or None,
                region_name=backend["region"] or None,
                aws_access_key_id=credentials.get("aws_access_key_id"),
                aws_secret_access_key=credentials.get("aws_secret_access_key"),
                aws_session_token=credentials.get("aws_session_token"),
            )
            started = time.perf_counter()
            response = client.head_bucket(Bucket=backend["bucket"])
            latency = round((time.perf_counter() - started) * 1000, 2)
            return self._store(actor, institution_id, "storage_backend", backend_id, "storage_connection", "verified", latency_ms=latency, evidence={"backend": backend["backend_type"], "bucket": backend["bucket"], "http_status": response.get("ResponseMetadata", {}).get("HTTPStatusCode")})
        except Exception as exc:
            return self._store(actor, institution_id, "storage_backend", backend_id, "storage_connection", "failed", error_text=str(exc))

    def verify_integration(self, actor: str, integration_id: str) -> dict[str, Any]:
        integration = self.platform._one("SELECT * FROM education_integrations WHERE id=?", (integration_id,))
        if not integration:
            raise Missing("Integration not found.")
        institution_id = integration["institution_id"]
        self.permissions.require(actor, institution_id, "integrations.manage")
        token = ""
        if integration["secret_reference"]:
            try:
                token = _environment_secret(integration["secret_reference"])
            except EducationError as exc:
                return self._store(actor, institution_id, "integration", integration_id, "provider_connection", "failed", error_text=str(exc))
        try:
            status, payload, headers, latency = _fetch_json(integration["base_url"], token=token)
            valid = 200 <= status < 300
            return self._store(actor, institution_id, "integration", integration_id, "provider_connection", "verified" if valid else "failed", latency_ms=latency, evidence={"provider_type": integration["provider_type"], "http_status": status, "content_type": headers.get("content-type", ""), "response_keys": sorted(payload)[:20]}, error_text="" if valid else f"Provider returned HTTP {status}.")
        except EducationError as exc:
            return self._store(actor, institution_id, "integration", integration_id, "provider_connection", "failed", error_text=str(exc))
