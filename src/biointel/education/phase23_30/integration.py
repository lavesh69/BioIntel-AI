from __future__ import annotations

import hashlib
import hmac
import importlib.util
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..platform import Conflict, Denied, EducationError, ident, now
from .base import ADMIN_ROLES, Phase30Base, decode_json, encode_json, normalized_key

ADAPTERS: dict[str, dict[str, Any]] = {
    "moodle": {"category": "lms", "capabilities": ["courses", "enrolments", "assignments", "results"]},
    "canvas": {"category": "lms", "capabilities": ["courses", "enrolments", "assignments", "results"]},
    "google_classroom": {"category": "lms", "capabilities": ["courses", "coursework", "rosters"]},
    "generic_lti": {"category": "lms", "capabilities": ["launch", "deep_linking", "grades"]},
    "generic_oneroster": {"category": "sis", "capabilities": ["orgs", "users", "classes", "enrolments"]},
    "orcid": {"category": "identity", "capabilities": ["researcher_profile", "works"]},
    "crossref": {"category": "scientific", "capabilities": ["works_metadata"]},
    "pubmed_ncbi": {"category": "scientific", "capabilities": ["pubmed_metadata"]},
    "europe_pmc": {"category": "scientific", "capabilities": ["articles", "citations"]},
    "institutional_smtp": {"category": "email", "capabilities": ["transactional_email"]},
    "calendar_feed": {"category": "calendar", "capabilities": ["ics_export", "ics_import"]},
    "s3_compatible": {"category": "storage", "capabilities": ["objects", "presigned_access"]},
    "oauth2": {"category": "identity", "capabilities": ["authorization", "account_linking"]},
    "openid_connect": {"category": "identity", "capabilities": ["authentication", "claims", "session_revocation"]},
    "saml_metadata": {"category": "identity", "capabilities": ["metadata_configuration", "role_mapping"]},
}
PLUGIN_PERMISSION_ALLOWLIST = {
    "education.read",
    "education.draft",
    "science.read",
    "portfolio.read",
    "notifications.draft",
    "storage.plugin_scoped",
    "network.declared_hosts",
}
MCP_TOOLS: dict[str, dict[str, Any]] = {
    "search_courses": {"write": False, "permission": "education.read"},
    "read_course_material": {"write": False, "permission": "education.read"},
    "search_science_pulse": {"write": False, "permission": "science.read"},
    "query_approved_shiro": {"write": False, "permission": "education.read"},
    "retrieve_assignment_status": {"write": False, "permission": "education.read"},
    "retrieve_student_progress": {"write": False, "permission": "education.read"},
    "retrieve_project_metadata": {"write": False, "permission": "education.read"},
    "create_draft_lesson": {"write": True, "permission": "education.draft"},
    "create_draft_quiz": {"write": True, "permission": "education.draft"},
    "create_support_ticket": {"write": True, "permission": "support.create"},
    "start_approved_agent_task": {"write": True, "permission": "agent.start"},
}
JOB_TYPES = {
    "document_ingestion",
    "ai_task",
    "report_generation",
    "media_processing",
    "scientific_source_sync",
    "notification",
    "credential_generation",
    "export",
    "large_import",
    "analytics_refresh",
    "webhook_delivery",
}


class IntegrationMixin(Phase30Base):
    def adapter_catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "adapter_type": key,
                **definition,
                "external_service_optional": True,
                "local_verification_state": "configuration_contract_verified",
                "live_connection_state": "requires_external_validation",
            }
            for key, definition in sorted(ADAPTERS.items())
        ]

    def configure_integration(
        self,
        actor: str,
        institution_id: str,
        *,
        adapter_type: str,
        name: str,
        configuration: dict[str, Any],
        secret_reference: str = "",
        enabled: bool = False,
        timeout_seconds: int = 30,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "admin")
        adapter = normalized_key(adapter_type)
        if adapter not in ADAPTERS:
            raise EducationError("Unsupported integration adapter.")
        if any(
            key.casefold() in {"password", "secret", "token", "api_key", "client_secret"}
            and str(value)
            for key, value in configuration.items()
        ):
            raise Denied("Raw integration secrets must use an external secret reference.")
        if timeout_seconds < 1 or timeout_seconds > 300:
            raise EducationError("Integration timeout must be between 1 and 300 seconds.")
        integration_id = ident("integration")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_integrations
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,name) DO UPDATE SET
                adapter_type=excluded.adapter_type,
                configuration_json=excluded.configuration_json,
                secret_reference=excluded.secret_reference,
                capability_json=excluded.capability_json,
                state=excluded.state,timeout_seconds=excluded.timeout_seconds,
                max_retries=excluded.max_retries,updated_at=excluded.updated_at""",
                (
                    integration_id,
                    institution_id,
                    adapter,
                    name.strip(),
                    encode_json(configuration),
                    secret_reference,
                    encode_json(ADAPTERS[adapter]["capabilities"]),
                    "enabled" if enabled else "disabled",
                    "not_tested",
                    "",
                    None,
                    int(timeout_seconds),
                    max(0, min(10, int(max_retries))),
                    actor,
                    timestamp,
                    timestamp,
                ),
            )
        return self._one(
            "SELECT * FROM education_p30_integrations WHERE institution_id=? AND name=?",
            (institution_id, name.strip()),
        ) or {}

    def test_integration(
        self,
        actor: str,
        integration_id: str,
        *,
        external_probe_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        integration = self._tenant_row("education_p30_integrations", integration_id)
        institution_id = str(integration["institution_id"])
        self._require(actor, institution_id, "admin")
        config = decode_json(integration["configuration_json"], {})
        required_by_adapter = {
            "moodle": {"base_url"},
            "canvas": {"base_url"},
            "google_classroom": {"project_id"},
            "generic_lti": {"issuer", "client_id", "deployment_id"},
            "generic_oneroster": {"base_url"},
            "orcid": {"client_id"},
            "institutional_smtp": {"host", "port"},
            "s3_compatible": {"endpoint_url", "bucket"},
            "oauth2": {"authorization_endpoint", "token_endpoint", "client_id"},
            "openid_connect": {"issuer", "client_id"},
            "saml_metadata": {"metadata_url"},
        }
        missing = sorted(
            key
            for key in required_by_adapter.get(str(integration["adapter_type"]), set())
            if not str(config.get(key, "")).strip()
        )
        if missing:
            state = "configuration_invalid"
            detail = f"Missing configuration: {', '.join(missing)}"
        elif external_probe_result is None:
            state = "requires_external_validation"
            detail = "Configuration contract is valid; no live credentialed probe was supplied."
        elif external_probe_result.get("connected") is True:
            state = "externally_reported_connected"
            detail = str(external_probe_result.get("detail", "External probe reported success."))
        else:
            state = "external_probe_failed"
            detail = str(external_probe_result.get("detail", "External probe failed."))
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_integrations
                SET last_test_state=?,last_test_detail=?,last_test_at=?,updated_at=? WHERE id=?""",
                (state, detail[:2000], timestamp, timestamp, integration_id),
            )
        return self._tenant_row(
            "education_p30_integrations",
            integration_id,
            institution_id,
        )

    def dry_run_sync(
        self,
        actor: str,
        integration_id: str,
        *,
        direction: str,
        sample_records: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        integration = self._tenant_row("education_p30_integrations", integration_id)
        institution_id = str(integration["institution_id"])
        self._require(actor, institution_id, "admin")
        if integration["state"] != "enabled":
            raise Conflict("Integration must be enabled before synchronization.")
        if direction not in {"import", "export", "bidirectional"}:
            raise EducationError("Unsupported synchronization direction.")
        records = sample_records or []
        conflicts = [
            {
                "index": index,
                "reason": "missing_external_id",
            }
            for index, record in enumerate(records)
            if not str(record.get("external_id", "")).strip()
        ]
        run_id = ident("syncrun")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_sync_runs
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    integration_id,
                    institution_id,
                    direction,
                    1,
                    "dry_run_complete",
                    "",
                    len(records),
                    0,
                    len(conflicts),
                    0,
                    encode_json(conflicts),
                    "",
                    timestamp,
                    timestamp,
                ),
            )
        return self._tenant_row(
            "education_p30_sync_runs",
            run_id,
            institution_id,
        )

    def create_api_key(
        self,
        actor: str,
        institution_id: str,
        *,
        name: str,
        scopes: list[str],
        expires_at: str = "",
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "admin")
        allowed_scopes = {
            "institutions:read",
            "courses:read",
            "courses:write",
            "classrooms:read",
            "enrolments:read",
            "assignments:read",
            "assessments:read",
            "results:read",
            "lectures:read",
            "science:read",
            "portfolios:read",
            "credentials:read",
            "notifications:read",
            "agent_tasks:read",
            "agent_tasks:write",
            "support:write",
        }
        normalized_scopes = sorted(set(scopes))
        unknown = sorted(set(normalized_scopes) - allowed_scopes)
        if unknown or not normalized_scopes:
            raise EducationError(f"Unsupported or empty API scopes: {', '.join(unknown)}")
        if expires_at:
            expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= datetime.now(timezone.utc):
                raise EducationError("API key expiry must be in the future.")
        raw_key = "bia_" + secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        key_id = ident("apikey")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_api_keys
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    key_id,
                    institution_id,
                    name.strip(),
                    raw_key[:12],
                    key_hash,
                    encode_json(normalized_scopes),
                    actor,
                    "active",
                    expires_at or None,
                    None,
                    None,
                    timestamp,
                ),
            )
        self._audit(actor, institution_id, "api_key_created", "api_key", key_id)
        return {
            "id": key_id,
            "institution_id": institution_id,
            "name": name.strip(),
            "key": raw_key,
            "key_prefix": raw_key[:12],
            "scopes": normalized_scopes,
            "expires_at": expires_at or None,
        }

    def authenticate_api_key(
        self,
        raw_key: str,
        *,
        required_scope: str,
        route: str = "",
        method: str = "GET",
        request_id: str = "",
        idempotency_key: str = "",
        rate_limit_per_minute: int = 120,
    ) -> dict[str, Any]:
        key_hash = hashlib.sha256(str(raw_key).encode("utf-8")).hexdigest()
        row = self._one(
            """SELECT * FROM education_p30_api_keys
            WHERE key_sha256=? AND state='active'""",
            (key_hash,),
        )
        if not row:
            raise Denied("Invalid API key.")
        if row["expires_at"]:
            expiry = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= datetime.now(timezone.utc):
                raise Denied("API key has expired.")
        scopes = set(decode_json(row["scopes_json"], []))
        if required_scope not in scopes:
            raise Denied("API key scope denied.")
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        usage = self._one(
            """SELECT COUNT(*) count FROM education_p30_api_usage
            WHERE api_key_id=? AND created_at>=?""",
            (row["id"], cutoff),
        )
        if int((usage or {}).get("count", 0)) >= int(rate_limit_per_minute):
            raise Denied("API key rate limit exceeded.")
        with self.db.connection() as db:
            db.execute(
                "UPDATE education_p30_api_keys SET last_used_at=? WHERE id=?",
                (now(), row["id"]),
            )
        return {
            "id": row["id"],
            "institution_id": row["institution_id"],
            "scopes": sorted(scopes),
            "route": route,
            "method": method,
            "request_id": request_id,
            "idempotency_key": idempotency_key,
        }

    def record_api_usage(
        self,
        auth: dict[str, Any],
        *,
        route: str,
        method: str,
        status_code: int,
        latency_ms: float,
        request_id: str,
        idempotency_key: str = "",
    ) -> None:
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_api_usage
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ident("apiusage"),
                    auth["institution_id"],
                    auth["id"],
                    "",
                    route,
                    method,
                    int(status_code),
                    max(0.0, float(latency_ms)),
                    request_id,
                    idempotency_key,
                    now(),
                ),
            )

    def register_webhook(
        self,
        actor: str,
        institution_id: str,
        *,
        name: str,
        target_url: str,
        event_types: list[str],
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "admin")
        parsed = urlparse(target_url)
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise Denied("Webhook target must use HTTPS except for local development.")
        if not parsed.hostname:
            raise EducationError("Webhook target URL is invalid.")
        events = sorted({normalized_key(item) for item in event_types})
        if not events:
            raise EducationError("At least one webhook event type is required.")
        raw_secret = secrets.token_urlsafe(32)
        webhook_id = ident("webhook")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_webhooks
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    webhook_id,
                    institution_id,
                    name.strip(),
                    target_url,
                    encode_json(events),
                    self._encrypt(raw_secret),
                    1,
                    "active",
                    0,
                    "",
                    actor,
                    timestamp,
                    timestamp,
                ),
            )
        return {
            "id": webhook_id,
            "institution_id": institution_id,
            "name": name.strip(),
            "target_url": target_url,
            "event_types": events,
            "signing_secret": raw_secret,
            "secret_version": 1,
        }

    @staticmethod
    def webhook_signature(secret: str, timestamp: str, nonce: str, payload_json: str) -> str:
        signed = f"{timestamp}.{nonce}.{payload_json}".encode("utf-8")
        return "v1=" + hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()

    def verify_webhook_signature(
        self,
        secret: str,
        timestamp: str,
        nonce: str,
        payload_json: str,
        signature: str,
        *,
        tolerance_seconds: int = 300,
    ) -> bool:
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        if abs((datetime.now(timezone.utc) - parsed).total_seconds()) > tolerance_seconds:
            return False
        expected = self.webhook_signature(secret, timestamp, nonce, payload_json)
        return hmac.compare_digest(expected, signature)

    def queue_webhook(
        self,
        actor: str,
        webhook_id: str,
        *,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        webhook = self._tenant_row("education_p30_webhooks", webhook_id)
        institution_id = str(webhook["institution_id"])
        self._require(actor, institution_id, "member")
        if webhook["state"] != "active":
            raise Conflict("Webhook is disabled.")
        event = normalized_key(event_type)
        if event not in set(decode_json(webhook["event_types_json"], [])):
            raise Denied("Webhook is not registered for this event type.")
        payload_json = encode_json(payload)
        timestamp = now()
        nonce = secrets.token_urlsafe(16)
        signature = self.webhook_signature(
            self._decrypt(str(webhook["signing_secret_encrypted"])),
            timestamp,
            nonce,
            payload_json,
        )
        delivery_id = ident("webhookdelivery")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_webhook_deliveries
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    delivery_id,
                    webhook_id,
                    institution_id,
                    event_id,
                    event,
                    payload_json,
                    hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
                    signature,
                    nonce,
                    "pending",
                    0,
                    timestamp,
                    None,
                    "",
                    timestamp,
                    timestamp,
                ),
            )
        return self._tenant_row(
            "education_p30_webhook_deliveries",
            delivery_id,
            institution_id,
        )

    def register_plugin(
        self,
        actor: str,
        institution_id: str,
        manifest: dict[str, Any],
        *,
        development_mode: bool = False,
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "admin")
        required = {"key", "name", "version", "compatibility", "permissions"}
        missing = sorted(required - set(manifest))
        if missing:
            raise EducationError(f"Plugin manifest is missing: {', '.join(missing)}")
        key = normalized_key(str(manifest["key"]))
        permissions = sorted({str(item) for item in manifest["permissions"]})
        unknown = sorted(set(permissions) - PLUGIN_PERMISSION_ALLOWLIST)
        if unknown:
            raise Denied(f"Plugin declares forbidden permissions: {', '.join(unknown)}")
        if manifest.get("filesystem_root") or manifest.get("database_access") == "unrestricted":
            raise Denied("Plugins cannot request unrestricted filesystem or database access.")
        plugin_id = ident("plugin")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_plugins
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,key) DO UPDATE SET
                name=excluded.name,version=excluded.version,
                compatibility=excluded.compatibility,manifest_json=excluded.manifest_json,
                configuration_schema_json=excluded.configuration_schema_json,
                development_mode=excluded.development_mode,state='disabled',
                updated_at=excluded.updated_at""",
                (
                    plugin_id,
                    institution_id,
                    key,
                    str(manifest["name"]),
                    str(manifest["version"]),
                    str(manifest["compatibility"]),
                    encode_json(manifest),
                    encode_json(manifest.get("configuration_schema", {})),
                    "untrusted",
                    "not_verified",
                    int(development_mode),
                    "disabled",
                    "not_run",
                    "",
                    actor,
                    timestamp,
                    timestamp,
                ),
            )
            stored = db.execute(
                "SELECT id FROM education_p30_plugins WHERE institution_id=? AND key=?",
                (institution_id, key),
            ).fetchone()[0]
            db.execute(
                "DELETE FROM education_p30_plugin_permissions WHERE plugin_id=?",
                (stored,),
            )
            db.executemany(
                """INSERT INTO education_p30_plugin_permissions
                VALUES(?,?,?,?,?,?)""",
                [
                    (ident("pluginperm"), stored, permission, 0, "", None)
                    for permission in permissions
                ],
            )
        return self._one(
            "SELECT * FROM education_p30_plugins WHERE institution_id=? AND key=?",
            (institution_id, key),
        ) or {}

    def grant_plugin_permission(
        self,
        actor: str,
        plugin_id: str,
        permission: str,
        *,
        granted: bool,
    ) -> dict[str, Any]:
        plugin = self._tenant_row("education_p30_plugins", plugin_id)
        institution_id = str(plugin["institution_id"])
        self._require(actor, institution_id, "admin")
        if permission not in PLUGIN_PERMISSION_ALLOWLIST:
            raise Denied("Plugin permission is not allowed.")
        declared = self._one(
            """SELECT * FROM education_p30_plugin_permissions
            WHERE plugin_id=? AND permission=?""",
            (plugin_id, permission),
        )
        if not declared:
            raise Denied("Plugin did not declare this permission.")
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_plugin_permissions
                SET granted=?,granted_by=?,granted_at=? WHERE id=?""",
                (int(granted), actor if granted else "", now() if granted else None, declared["id"]),
            )
        return self._one(
            "SELECT * FROM education_p30_plugin_permissions WHERE id=?",
            (declared["id"],),
        ) or {}

    def set_plugin_state(
        self,
        actor: str,
        plugin_id: str,
        *,
        enabled: bool,
    ) -> dict[str, Any]:
        plugin = self._tenant_row("education_p30_plugins", plugin_id)
        institution_id = str(plugin["institution_id"])
        self._require(actor, institution_id, "admin")
        if enabled:
            ungranted = self._one(
                """SELECT COUNT(*) count FROM education_p30_plugin_permissions
                WHERE plugin_id=? AND granted=0""",
                (plugin_id,),
            )
            if int((ungranted or {}).get("count", 0)):
                raise Conflict("All declared plugin permissions require administrator review.")
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_plugins SET state=?,health_state=?,
                last_error='',updated_at=? WHERE id=?""",
                (
                    "enabled" if enabled else "disabled",
                    "configuration_only" if enabled else "not_run",
                    now(),
                    plugin_id,
                ),
            )
        return self._tenant_row(
            "education_p30_plugins",
            plugin_id,
            institution_id,
        )

    def set_mcp_policy(
        self,
        actor: str,
        institution_id: str,
        *,
        principal_id: str,
        tool_key: str,
        allowed: bool,
        write_approval_required: bool = True,
        rate_limit_per_minute: int = 30,
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "admin")
        tool = normalized_key(tool_key)
        if tool not in MCP_TOOLS:
            raise EducationError("Unsupported MCP tool.")
        policy_id = ident("mcppolicy")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_mcp_policies
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,principal_id,tool_key) DO UPDATE SET
                allowed=excluded.allowed,
                write_approval_required=excluded.write_approval_required,
                rate_limit_per_minute=excluded.rate_limit_per_minute,
                created_by=excluded.created_by,updated_at=excluded.updated_at""",
                (
                    policy_id,
                    institution_id,
                    principal_id,
                    tool,
                    int(allowed),
                    int(write_approval_required),
                    min(600, max(1, int(rate_limit_per_minute))),
                    actor,
                    timestamp,
                    timestamp,
                ),
            )
        return self._one(
            """SELECT * FROM education_p30_mcp_policies
            WHERE institution_id=? AND principal_id=? AND tool_key=?""",
            (institution_id, principal_id, tool),
        ) or {}

    def authorize_mcp_tool(
        self,
        principal_id: str,
        institution_id: str,
        tool_key: str,
        *,
        human_approved: bool = False,
    ) -> dict[str, Any]:
        self._require(principal_id, institution_id, "member")
        tool = normalized_key(tool_key)
        definition = MCP_TOOLS.get(tool)
        if not definition:
            raise Denied("Unknown MCP tool.")
        policy = self._one(
            """SELECT * FROM education_p30_mcp_policies
            WHERE institution_id=? AND principal_id=? AND tool_key=?""",
            (institution_id, principal_id, tool),
        )
        if not policy or not policy["allowed"]:
            raise Denied("MCP tool policy denied.")
        if (
            definition["write"]
            and policy["write_approval_required"]
            and not human_approved
        ):
            raise Denied("MCP write tool requires human approval.")
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        usage = self._one(
            """SELECT COUNT(*) count FROM education_p30_audit_chain
            WHERE institution_id=? AND actor_id=? AND action='mcp_tool_called'
            AND created_at>=?""",
            (institution_id, principal_id, cutoff),
        )
        if int((usage or {}).get("count", 0)) >= int(policy["rate_limit_per_minute"]):
            raise Denied("MCP tool rate limit exceeded.")
        return {
            "tool": tool,
            "definition": definition,
            "policy": policy,
        }

    def call_mcp_tool(
        self,
        principal_id: str,
        institution_id: str,
        tool_key: str,
        arguments: dict[str, Any],
        *,
        human_approved: bool = False,
    ) -> dict[str, Any]:
        authorized = self.authorize_mcp_tool(
            principal_id,
            institution_id,
            tool_key,
            human_approved=human_approved,
        )
        tool = str(authorized["tool"])
        if tool == "search_courses":
            query = f"%{str(arguments.get('query', '')).strip()}%"
            result = self._all(
                """SELECT id,title,description,difficulty,state FROM courses
                WHERE institution_id=? AND state IN ('published','active')
                AND (title LIKE ? OR description LIKE ?) ORDER BY title LIMIT 50""",
                (institution_id, query, query),
            )
        elif tool == "search_science_pulse":
            query = f"%{str(arguments.get('query', '')).strip()}%"
            result = self._all(
                """SELECT id,doi,pmid,title,published_at,retraction_state
                FROM publications WHERE title LIKE ? ORDER BY published_at DESC LIMIT 50""",
                (query,),
            )
        elif tool == "retrieve_project_metadata":
            result = self._all(
                """SELECT id,title,supervisor_id,state,created_at,updated_at
                FROM education_p30_research_projects
                WHERE institution_id=? ORDER BY updated_at DESC LIMIT 50""",
                (institution_id,),
            )
        elif tool == "retrieve_student_progress":
            student_id = str(arguments.get("student_id", principal_id))
            if student_id != principal_id and not self._roles(
                principal_id,
                institution_id,
            ).intersection(ADMIN_ROLES):
                raise Denied("MCP progress access denied.")
            result = self._all(
                """SELECT concept_id,score,state,evidence_count,updated_at
                FROM education_p30_mastery_records
                WHERE institution_id=? AND student_id=?
                ORDER BY updated_at DESC LIMIT 100""",
                (institution_id, student_id),
            )
        elif tool in {"create_draft_lesson", "create_draft_quiz"}:
            result = {
                "state": "draft",
                "title": str(arguments.get("title", "")).strip(),
                "content": arguments.get("content", {}),
                "published": False,
                "human_review_required": True,
            }
        elif tool == "create_support_ticket":
            result = self.create_support_ticket(
                principal_id,
                institution_id,
                module=str(arguments.get("module", "mcp")),
                severity=str(arguments.get("severity", "medium")),
                title=str(arguments.get("title", "MCP support request")),
                description=str(arguments.get("description", "")),
            )
        elif tool == "start_approved_agent_task":
            result = self.create_agent_task(
                principal_id,
                institution_id,
                agent_key=str(arguments.get("agent_key", "student_tutor")),
                task_input=dict(arguments.get("task_input", {})),
                idempotency_key=str(arguments.get("idempotency_key", ident("mcp"))),
            )
        elif tool in {
            "read_course_material",
            "query_approved_shiro",
            "retrieve_assignment_status",
        }:
            result = {
                "state": "permission_checked",
                "records": [],
                "detail": "No matching permitted record was supplied.",
            }
        else:
            raise EducationError("MCP tool implementation is unavailable.")
        self._audit(
            principal_id,
            institution_id,
            "mcp_tool_called",
            "mcp_tool",
            tool,
            {"write": bool(authorized["definition"]["write"])},
        )
        return {
            "tool": tool,
            "result": result,
            "arbitrary_code_execution": False,
            "unrestricted_database_access": False,
        }

    def enqueue_job(
        self,
        actor: str,
        institution_id: str,
        *,
        job_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
        queue: str = "default",
        priority: int = 100,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "member")
        kind = normalized_key(job_type)
        if kind not in JOB_TYPES:
            raise EducationError("Unsupported background job type.")
        key = normalized_key(idempotency_key, maximum=160)
        existing = self._one(
            """SELECT * FROM education_p30_jobs
            WHERE institution_id=? AND job_type=? AND idempotency_key=?""",
            (institution_id, kind, key),
        )
        if existing:
            return existing
        job_id = ident("job")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_jobs
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id,
                    institution_id,
                    normalized_key(queue),
                    kind,
                    encode_json(payload),
                    key,
                    "queued",
                    int(priority),
                    0.0,
                    "{}",
                    "",
                    0,
                    max(0, min(20, int(max_retries))),
                    0,
                    timestamp,
                    "",
                    None,
                    actor,
                    timestamp,
                    timestamp,
                ),
            )
        return self._tenant_row("education_p30_jobs", job_id, institution_id)

    def claim_job(
        self,
        worker_id: str,
        *,
        queue: str = "default",
    ) -> dict[str, Any] | None:
        worker = normalized_key(worker_id)
        timestamp = now()
        with self.db.connection() as db:
            row = db.execute(
                """SELECT * FROM education_p30_jobs
                WHERE queue=? AND state IN ('queued','retry') AND available_at<=?
                AND cancel_requested=0
                ORDER BY priority,created_at LIMIT 1""",
                (normalized_key(queue), timestamp),
            ).fetchone()
            if not row:
                return None
            updated = db.execute(
                """UPDATE education_p30_jobs
                SET state='running',locked_by=?,locked_at=?,updated_at=?
                WHERE id=? AND state IN ('queued','retry')""",
                (worker, timestamp, timestamp, row["id"]),
            )
            if updated.rowcount != 1:
                return None
            attempt = int(row["retry_count"]) + 1
            db.execute(
                """INSERT INTO education_p30_job_attempts
                VALUES(?,?,?,?,?,?,?,?)""",
                (
                    ident("jobattempt"),
                    row["id"],
                    worker,
                    attempt,
                    "running",
                    "",
                    timestamp,
                    None,
                ),
            )
        return self._one("SELECT * FROM education_p30_jobs WHERE id=?", (row["id"],))

    def complete_job(
        self,
        worker_id: str,
        job_id: str,
        *,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        job = self._tenant_row("education_p30_jobs", job_id)
        if job["state"] != "running" or job["locked_by"] != normalized_key(worker_id):
            raise Denied("Worker does not own this job lease.")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_jobs SET state='completed',progress=1,
                result_json=?,updated_at=? WHERE id=?""",
                (encode_json(result), timestamp, job_id),
            )
            db.execute(
                """UPDATE education_p30_job_attempts SET state='completed',completed_at=?
                WHERE job_id=? AND state='running'""",
                (timestamp, job_id),
            )
        return self._tenant_row(
            "education_p30_jobs",
            job_id,
            str(job["institution_id"]),
        )

    def fail_job(
        self,
        worker_id: str,
        job_id: str,
        *,
        error: str,
    ) -> dict[str, Any]:
        job = self._tenant_row("education_p30_jobs", job_id)
        if job["state"] != "running" or job["locked_by"] != normalized_key(worker_id):
            raise Denied("Worker does not own this job lease.")
        retry_count = int(job["retry_count"]) + 1
        retry = retry_count <= int(job["max_retries"])
        delay = min(3600, 2 ** min(retry_count, 10))
        available = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_jobs SET state=?,error=?,retry_count=?,
                available_at=?,locked_by='',locked_at=NULL,updated_at=? WHERE id=?""",
                (
                    "retry" if retry else "dead_letter",
                    error[:2000],
                    retry_count,
                    available,
                    timestamp,
                    job_id,
                ),
            )
            db.execute(
                """UPDATE education_p30_job_attempts SET state='failed',error=?,completed_at=?
                WHERE job_id=? AND state='running'""",
                (error[:2000], timestamp, job_id),
            )
        return self._tenant_row(
            "education_p30_jobs",
            job_id,
            str(job["institution_id"]),
        )

    def store_object(
        self,
        actor: str,
        institution_id: str,
        source_path: str | Path,
        *,
        tenant_key: str,
        content_type: str = "application/octet-stream",
        metadata: dict[str, Any] | None = None,
        backend: str = "local",
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "member")
        if backend != "local":
            raise Conflict("S3 object storage requires external configuration validation.")
        key = normalized_key(tenant_key, maximum=120)
        source = Path(source_path)
        suffix = source.suffix.casefold()
        destination = self._safe_storage_path(
            institution_id,
            "objects",
            key[:2],
            key + suffix,
        )
        copied = self._copy_managed_file(
            source,
            destination,
            maximum_bytes=2 * 1024 * 1024 * 1024,
            allowed_suffixes={
                ".pdf",
                ".txt",
                ".csv",
                ".xlsx",
                ".json",
                ".png",
                ".jpg",
                ".jpeg",
                ".zip",
                ".mp4",
                ".webm",
                ".fasta",
                ".fastq",
            },
        )
        object_id = ident("object")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_objects
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,tenant_key) DO UPDATE SET
                original_name=excluded.original_name,content_type=excluded.content_type,
                size_bytes=excluded.size_bytes,sha256=excluded.sha256,
                storage_path=excluded.storage_path,metadata_json=excluded.metadata_json,
                state='active',deleted_at=NULL""",
                (
                    object_id,
                    institution_id,
                    backend,
                    key,
                    copied["original_name"],
                    content_type,
                    copied["size_bytes"],
                    copied["sha256"],
                    copied["path"],
                    encode_json(metadata or {}),
                    "active",
                    actor,
                    now(),
                    None,
                ),
            )
        return self._one(
            """SELECT * FROM education_p30_objects
            WHERE institution_id=? AND tenant_key=?""",
            (institution_id, key),
        ) or {}

    def configure_deployment_profile(
        self,
        actor: str,
        institution_id: str,
        *,
        profile_type: str,
        configuration: dict[str, Any],
        version: str = "1.0",
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "admin")
        profile = normalized_key(profile_type)
        if profile not in {"local_desktop", "institution_server", "enterprise_cluster"}:
            raise EducationError("Unsupported deployment profile.")
        profile_id = ident("deployment")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_deployment_profiles
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,profile_type,version) DO UPDATE SET
                configuration_json=excluded.configuration_json,
                validation_json='{}',validation_state='not_validated',
                updated_at=excluded.updated_at""",
                (
                    profile_id,
                    institution_id,
                    profile,
                    encode_json(configuration),
                    "{}",
                    "not_validated",
                    version,
                    actor,
                    timestamp,
                    timestamp,
                ),
            )
        return self._one(
            """SELECT * FROM education_p30_deployment_profiles
            WHERE institution_id=? AND profile_type=? AND version=?""",
            (institution_id, profile, version),
        ) or {}

    def validate_deployment_profile(
        self,
        actor: str,
        profile_id: str,
    ) -> dict[str, Any]:
        profile = self._tenant_row("education_p30_deployment_profiles", profile_id)
        institution_id = str(profile["institution_id"])
        self._require(actor, institution_id, "admin")
        profile_type = str(profile["profile_type"])
        config = decode_json(profile["configuration_json"], {})
        checks: dict[str, Any] = {
            "local_database": self.db.quick_check(),
            "managed_storage": self.storage.is_dir() and os.access(self.storage, os.W_OK),
            "profile": profile_type,
        }
        if profile_type == "local_desktop":
            checks.update(
                {
                    "sqlite": True,
                    "local_files": True,
                    "required_cloud_services": 0,
                }
            )
            state = "verified_local"
        else:
            required_config = (
                {"postgres_dsn", "redis_url", "object_storage"}
                if profile_type == "institution_server"
                else {
                    "postgres_dsn",
                    "redis_url",
                    "object_storage",
                    "api_replicas",
                    "worker_replicas",
                }
            )
            missing_config = sorted(
                key for key in required_config if not config.get(key)
            )
            drivers = {
                "psycopg": importlib.util.find_spec("psycopg") is not None,
                "redis": importlib.util.find_spec("redis") is not None,
                "boto3": importlib.util.find_spec("boto3") is not None,
            }
            checks.update(
                {
                    "missing_configuration": missing_config,
                    "drivers": drivers,
                    "live_infrastructure_tested": False,
                }
            )
            state = (
                "configuration_valid_requires_external_validation"
                if not missing_config and all(drivers.values())
                else "partial_missing_dependencies_or_configuration"
            )
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_deployment_profiles
                SET validation_json=?,validation_state=?,updated_at=? WHERE id=?""",
                (encode_json(checks), state, now(), profile_id),
            )
        return self._tenant_row(
            "education_p30_deployment_profiles",
            profile_id,
            institution_id,
        )

    def backup_phase30_database(
        self,
        actor: str,
        institution_id: str,
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "admin")
        destination = self._safe_storage_path(
            institution_id,
            "backups",
            f"education-{ident('backup')}.sqlite3",
        )
        source = sqlite3.connect(self.db.path)
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        check = sqlite3.connect(destination)
        try:
            quick = check.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            check.close()
        if quick != "ok":
            raise Conflict("Database backup verification failed.")
        result = {
            "path": str(destination),
            "size_bytes": destination.stat().st_size,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "quick_check": quick,
        }
        self._audit(
            actor,
            institution_id,
            "phase30_database_backup",
            "backup",
            result["sha256"],
        )
        return result
