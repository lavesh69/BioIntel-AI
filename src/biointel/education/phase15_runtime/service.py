from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import mimetypes
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from ..phase11 import ADMIN_ROLES, TEACHER_ROLES, _json
from ..phase14 import EducationPhase14Service
from ..platform import Conflict, Denied, EducationError, Missing, ident, now, parse_time
from .providers import PROVIDERS, fetch_provider
from .schema import MIGRATION_ID, SCHEMA
from .vectors import bm25_scores, cosine, hashed_embedding, pack_vector, unpack_vector

MODEL_PROVIDERS = {"ollama", "openai_compatible", "llama_cpp"}
MEDIA_EVENTS = {"play", "pause", "progress", "seek", "ended", "rate_change"}
VIDEO_SUFFIXES = {".mp4", ".m4v", ".mov", ".webm", ".mkv"}


def _decode(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _environment_secret(reference: str) -> str:
    text = str(reference or "").strip()
    if not text:
        return ""
    if not text.startswith("env:"):
        raise Conflict("Secrets must use env:VARIABLE references.")
    name = text[4:].strip()
    if not name or not name.replace("_", "").isalnum():
        raise EducationError("Invalid environment secret reference.")
    value = os.environ.get(name, "")
    if not value:
        raise Conflict(f"Environment secret {name} is not configured.")
    return value


def _endpoint(url: str, *, resolve: bool = True) -> tuple[urllib.parse.ParseResult, bool]:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if parsed.username or parsed.password or not parsed.hostname:
        raise EducationError("Model endpoint must not contain embedded credentials.")
    host = parsed.hostname.lower().rstrip(".")
    local = host in {"localhost", "127.0.0.1", "::1"}
    if local:
        if parsed.scheme != "http":
            raise EducationError("Local model endpoints must use HTTP on loopback.")
        return parsed, True
    if parsed.scheme != "https":
        raise EducationError("Remote model endpoints require HTTPS.")
    if not resolve:
        return parsed, False
    try:
        addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise Conflict(f"Model endpoint resolution failed: {exc}") from exc
    for row in addresses:
        address = ipaddress.ip_address(row[4][0].split("%")[0])
        if any((address.is_private, address.is_loopback, address.is_link_local, address.is_multicast, address.is_reserved, address.is_unspecified)):
            raise Denied("Private and non-routable remote model endpoints are blocked.")
    return parsed, False


class EducationPhase15Service(EducationPhase14Service):
    """Production-runtime and research-intelligence layer.

    The layer implements a durable event stream, hybrid semantic retrieval, local/opt-in model
    runtimes, provider-normalised Science Pulse ingestion and server-governed lecture telemetry.
    It does not claim that third-party infrastructure is available until a live check succeeds.
    """

    def __init__(
        self,
        platform: Any,
        *,
        root: str | Path | None = None,
        http_opener: Callable[..., Any] | None = None,
        provider_opener: Callable[..., Any] | None = None,
    ):
        super().__init__(platform, root=root)
        self.root = Path(root or self.root)
        self.http_opener = http_opener or urllib.request.urlopen
        self.provider_opener = provider_opener or urllib.request.urlopen
        self.migrate_phase15()

    def migrate_phase15(self) -> str:
        with self.db.connection() as db:
            db.executescript(SCHEMA)
        return MIGRATION_ID

    # ------------------------------------------------------------------
    # Durable real-time event stream. APIs can expose these rows via SSE.
    # ------------------------------------------------------------------
    def publish_event(
        self,
        actor: str,
        institution_id: str,
        *,
        channel: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        target_type: str = "",
        target_id: str = "",
        audience: dict[str, Any] | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        self.platform._require(actor, institution_id)
        channel_text = str(channel).strip().lower()
        event_text = str(event_type).strip().lower()
        if not channel_text or len(channel_text) > 120 or not event_text or len(event_text) > 120:
            raise EducationError("Event channel and type are required and must be at most 120 characters.")
        if expires_at and parse_time(expires_at) <= datetime.now(timezone.utc):
            raise EducationError("Event expiry must be in the future.")
        event_id = ident("event")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_realtime_events(
                id,institution_id,channel,event_type,target_type,target_id,audience_json,payload_json,created_by,created_at,expires_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (event_id, institution_id, channel_text, event_text, str(target_type)[:120], str(target_id)[:300], _json(audience or {}), _json(payload or {}), actor, now(), expires_at),
            )
        return self._event(event_id)

    def _event(self, event_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_realtime_events WHERE id=?", (event_id,))
        if not row:
            raise Missing("Real-time event not found.")
        row["audience"] = _decode(row.pop("audience_json", "{}"), {})
        row["payload"] = _decode(row.pop("payload_json", "{}"), {})
        return row

    def _event_allowed(self, actor: str, institution_id: str, audience_json: str) -> bool:
        memberships = self.platform.membership(actor, institution_id)
        roles = {str(item["role"]) for item in memberships}
        if not roles:
            return False
        audience = _decode(audience_json, {})
        users = {str(value) for value in audience.get("users", [])}
        allowed_roles = {str(value) for value in audience.get("roles", [])}
        return not users and not allowed_roles or actor in users or bool(roles & allowed_roles) or bool(roles & ADMIN_ROLES)

    def poll_events(
        self,
        actor: str,
        institution_id: str,
        *,
        after_sequence: int = 0,
        channels: Iterable[str] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        self.platform._require(actor, institution_id)
        channel_values = [str(value).strip().lower() for value in (channels or []) if str(value).strip()]
        parameters: list[Any] = [institution_id, max(0, int(after_sequence)), now()]
        clause = ""
        if channel_values:
            clause = " AND channel IN (" + ",".join("?" for _ in channel_values) + ")"
            parameters.extend(channel_values)
        parameters.append(max(1, min(int(limit), 500)))
        rows = self.platform._all(
            f"""SELECT * FROM education_realtime_events
            WHERE institution_id=? AND sequence>? AND (expires_at IS NULL OR expires_at>?) {clause}
            ORDER BY sequence ASC LIMIT ?""",
            tuple(parameters),
        )
        events: list[dict[str, Any]] = []
        for row in rows:
            if not self._event_allowed(actor, institution_id, row.get("audience_json") or "{}"):
                continue
            row["audience"] = _decode(row.pop("audience_json", "{}"), {})
            row["payload"] = _decode(row.pop("payload_json", "{}"), {})
            events.append(row)
        return {
            "events": events,
            "event_count": len(events),
            "next_sequence": max([int(item["sequence"]) for item in events] or [int(after_sequence)]),
            "transport": "durable-event-stream",
        }

    # ------------------------------------------------------------------
    # Hybrid lexical + deterministic local semantic retrieval.
    # ------------------------------------------------------------------
    def build_hybrid_rag_index(
        self,
        actor: str,
        institution_id: str,
        project_id: str,
        *,
        model_name: str = "biointel-hash-embedding-v1",
        dimensions: int = 384,
    ) -> dict[str, Any]:
        self._require_staff(actor, institution_id)
        dimensions = int(dimensions)
        if dimensions < 64 or dimensions > 4096:
            raise EducationError("Vector dimensions must be between 64 and 4096.")
        rows = self.platform._all(
            """SELECT c.id,c.content,c.content_sha256 FROM education_rag_chunks c
            JOIN education_rag_documents d ON d.id=c.document_id
            WHERE c.institution_id=? AND c.project_id=? AND c.state='active' AND d.state='approved'
            ORDER BY c.document_id,c.ordinal""",
            (institution_id, str(project_id)),
        )
        if not rows:
            raise Conflict("No approved RAG chunks are available to index.")
        existing = self.platform._one(
            "SELECT * FROM education_rag_vector_indexes WHERE institution_id=? AND project_id=? AND model_name=?",
            (institution_id, str(project_id), str(model_name)),
        )
        index_id = existing["id"] if existing else ident("ragindex")
        digest = hashlib.sha256()
        stamp = now()
        with self.db.connection() as db:
            if existing:
                db.execute("DELETE FROM education_rag_chunk_embeddings WHERE index_id=?", (index_id,))
            else:
                db.execute(
                    "INSERT INTO education_rag_vector_indexes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (index_id, institution_id, str(project_id), str(model_name), dimensions, 0, "", "building", actor, stamp, stamp),
                )
            for row in rows:
                vector = hashed_embedding(row["content"], dimensions)
                blob = pack_vector(vector)
                digest.update(str(row["id"]).encode("utf-8"))
                digest.update(str(row["content_sha256"]).encode("ascii"))
                db.execute(
                    "INSERT INTO education_rag_chunk_embeddings VALUES(?,?,?,?,?,?,?,?)",
                    (row["id"], index_id, institution_id, str(project_id), blob, 1.0, row["content_sha256"], stamp),
                )
            db.execute(
                "UPDATE education_rag_vector_indexes SET dimensions=?,chunk_count=?,index_sha256=?,state='ready',created_by=?,updated_at=? WHERE id=?",
                (dimensions, len(rows), digest.hexdigest(), actor, stamp, index_id),
            )
        self.publish_event(actor, institution_id, channel="rag", event_type="index_ready", target_type="rag_project", target_id=str(project_id), payload={"index_id": index_id, "chunks": len(rows), "model": model_name})
        return self.platform._one("SELECT * FROM education_rag_vector_indexes WHERE id=?", (index_id,))

    def hybrid_rag_search(
        self,
        actor: str,
        institution_id: str,
        project_id: str,
        query: str,
        *,
        limit: int = 8,
        vector_weight: float = 0.55,
        model_name: str = "biointel-hash-embedding-v1",
    ) -> dict[str, Any]:
        self.platform._require(actor, institution_id)
        query_text = " ".join(str(query).split())
        if len(query_text) < 2:
            raise EducationError("A meaningful search query is required.")
        vector_weight = max(0.0, min(1.0, float(vector_weight)))
        lexical_weight = 1.0 - vector_weight
        index = self.platform._one(
            "SELECT * FROM education_rag_vector_indexes WHERE institution_id=? AND project_id=? AND model_name=? AND state='ready'",
            (institution_id, str(project_id), str(model_name)),
        )
        if not index:
            raise Conflict("Hybrid vector index is not ready for this project.")
        rows = self.platform._all(
            """SELECT c.*,d.title document_title,d.source_name,d.sha256 document_sha256,d.permission_json,e.vector_blob
            FROM education_rag_chunk_embeddings e
            JOIN education_rag_chunks c ON c.id=e.chunk_id
            JOIN education_rag_documents d ON d.id=c.document_id
            WHERE e.index_id=? AND c.state='active' AND d.state='approved'""",
            (index["id"],),
        )
        allowed = [row for row in rows if self._chunk_allowed(actor, institution_id, row.get("permission_json") or row.get("permissions_json") or "{}")]
        query_vector = hashed_embedding(query_text, int(index["dimensions"]))
        lexical = bm25_scores(query_text, [str(row["content"]) for row in allowed])
        scored: list[dict[str, Any]] = []
        for row, lexical_score in zip(allowed, lexical):
            vector_score = max(0.0, cosine(query_vector, unpack_vector(row["vector_blob"], int(index["dimensions"]))))
            combined = lexical_weight * lexical_score + vector_weight * vector_score
            if combined <= 0:
                continue
            content = str(row["content"])
            scored.append({
                "chunk_id": row["id"], "document_id": row["document_id"], "document_title": row["document_title"],
                "source_name": row["source_name"], "page_number": row["page_number"], "section": row["section"], "locator": row["locator"],
                "lexical_score": round(lexical_score, 6), "vector_score": round(vector_score, 6), "score": round(combined, 6),
                "excerpt": content[:900], "citation": f"{row['source_name']} · {row['locator'] or row['section'] or 'document'}",
                "document_sha256": row["document_sha256"],
            })
        scored.sort(key=lambda item: (-item["score"], item["document_title"], item["chunk_id"]))
        results = scored[: max(1, min(int(limit), 30))]
        run_id = ident("hybridsearch")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_rag_hybrid_search_runs VALUES(?,?,?,?,?,?,?,?,?,?)",
                (run_id, institution_id, str(project_id), query_text, lexical_weight, vector_weight, len(results), _json([{"chunk_id": item["chunk_id"], "score": item["score"]} for item in results]), actor, now()),
            )
        return {
            "id": run_id, "project_id": project_id, "query": query_text, "result_count": len(results), "results": results,
            "evidence_status": "grounded" if results else "no_approved_evidence",
            "retrieval_policy": "Approved permission-filtered evidence; BM25 and deterministic local semantic vectors; results require scientific review.",
        }

    # ------------------------------------------------------------------
    # Local/opt-in model runtime manager.
    # ------------------------------------------------------------------
    def register_model_runtime(
        self,
        actor: str,
        institution_id: str,
        *,
        name: str,
        provider_type: str,
        model_name: str,
        endpoint: str = "",
        secret_reference: str = "",
        context_window: int = 4096,
        external_processing: bool = False,
    ) -> dict[str, Any]:
        self._require_admin(actor, institution_id)
        provider = str(provider_type).strip().lower()
        if provider not in MODEL_PROVIDERS:
            raise EducationError("Unsupported model runtime provider.")
        if provider in {"ollama", "openai_compatible"}:
            _endpoint(endpoint, resolve=False)
        else:
            executable = Path(endpoint).expanduser().resolve()
            if not executable.is_file():
                raise Missing("llama.cpp executable was not found.")
        if secret_reference and not str(secret_reference).startswith("env:"):
            raise Conflict("Model runtime secrets must use env:VARIABLE references.")
        runtime_id, stamp = ident("modelrt"), now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_model_runtimes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,name) DO UPDATE SET provider_type=excluded.provider_type,endpoint=excluded.endpoint,
                model_name=excluded.model_name,secret_reference=excluded.secret_reference,context_window=excluded.context_window,
                external_processing=excluded.external_processing,state='configured',readiness_json='{}',updated_at=excluded.updated_at""",
                (runtime_id, institution_id, str(name).strip(), provider, str(endpoint).strip(), str(model_name).strip(), str(secret_reference).strip(), max(512, int(context_window)), int(bool(external_processing)), "configured", "{}", actor, stamp, stamp),
            )
        return self.platform._one("SELECT * FROM education_model_runtimes WHERE institution_id=? AND name=?", (institution_id, str(name).strip()))

    def _http(self, request: urllib.request.Request, *, timeout: float = 15.0) -> tuple[int, dict[str, Any], float]:
        started = time.perf_counter()
        try:
            with self.http_opener(request, timeout=timeout) as response:
                payload = response.read(1024 * 1024 + 1)
                status = int(getattr(response, "status", 200))
        except urllib.error.HTTPError as exc:
            payload = exc.read(65536)
            status = int(exc.code)
        except Exception as exc:
            raise Conflict(f"Model runtime request failed: {exc}") from exc
        if len(payload) > 1024 * 1024:
            raise Conflict("Model runtime response exceeded 1 MiB safety limit.")
        try:
            data = json.loads(payload.decode("utf-8")) if payload else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = {"text": payload.decode("utf-8", errors="replace")[:5000]}
        return status, data if isinstance(data, dict) else {"value": data}, round((time.perf_counter() - started) * 1000, 2)

    def verify_model_runtime(self, actor: str, runtime_id: str) -> dict[str, Any]:
        runtime = self.platform._one("SELECT * FROM education_model_runtimes WHERE id=?", (runtime_id,))
        if not runtime:
            raise Missing("Model runtime not found.")
        self._require_admin(actor, runtime["institution_id"])
        state, error, latency, evidence = "failed", "", None, {}
        try:
            if runtime["provider_type"] == "llama_cpp":
                started = time.perf_counter()
                endpoint = str(runtime["endpoint"])
                command = [endpoint, "--version"]
                if os.name == "nt" and Path(endpoint).suffix.casefold() in {".bat", ".cmd"}:
                    endpoint = str(Path(endpoint).expanduser().resolve())
                    command = f'"{os.environ.get("COMSPEC", "cmd.exe")}" /d /s /c ""{endpoint}" --version"'
                completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
                latency = round((time.perf_counter() - started) * 1000, 2)
                state = "verified" if completed.returncode == 0 else "failed"
                evidence = {"return_code": completed.returncode, "version_excerpt": (completed.stdout or completed.stderr)[:1000]}
                if state != "verified":
                    error = "llama.cpp version command failed."
            else:
                parsed, local = _endpoint(runtime["endpoint"])
                path = "/api/tags" if runtime["provider_type"] == "ollama" else "/v1/models"
                url = urllib.parse.urlunparse(parsed._replace(path=path, query="", fragment=""))
                headers = {"Accept": "application/json", "User-Agent": "BioIntel-Phase15"}
                if runtime["secret_reference"]:
                    headers["Authorization"] = "Bearer " + _environment_secret(runtime["secret_reference"])
                status, data, latency = self._http(urllib.request.Request(url, headers=headers, method="GET"))
                state = "verified" if 200 <= status < 300 else "failed"
                evidence = {"http_status": status, "local_endpoint": local, "response_keys": sorted(data)[:20]}
                if state != "verified":
                    error = f"Runtime returned HTTP {status}."
        except Exception as exc:
            error = str(exc)
        check_id = ident("modelcheck")
        with self.db.connection() as db:
            db.execute("INSERT INTO education_model_runtime_checks VALUES(?,?,?,?,?,?,?,?,?)", (check_id, runtime_id, runtime["institution_id"], state, latency, _json(evidence), error[:4000], actor, now()))
            db.execute("UPDATE education_model_runtimes SET state=?,readiness_json=?,updated_at=? WHERE id=?", (state, _json(evidence), now(), runtime_id))
        return self.platform._one("SELECT * FROM education_model_runtime_checks WHERE id=?", (check_id,))

    def generate_with_runtime(
        self,
        actor: str,
        runtime_id: str,
        prompt: str,
        *,
        system_prompt: str = "",
        allow_external_processing: bool = False,
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        runtime = self.platform._one("SELECT * FROM education_model_runtimes WHERE id=?", (runtime_id,))
        if not runtime:
            raise Missing("Model runtime not found.")
        self.platform._require(actor, runtime["institution_id"])
        if runtime["state"] != "verified":
            raise Conflict("Model runtime must pass a live verification before generation.")
        if runtime["external_processing"] and not allow_external_processing:
            raise Denied("External processing requires explicit per-request consent.")
        if runtime["provider_type"] == "llama_cpp":
            raise Conflict("Direct llama.cpp generation requires a configured HTTP server; executable verification alone is not a generation transport.")
        parsed, _ = _endpoint(runtime["endpoint"])
        headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "BioIntel-Phase15"}
        if runtime["secret_reference"]:
            headers["Authorization"] = "Bearer " + _environment_secret(runtime["secret_reference"])
        if runtime["provider_type"] == "ollama":
            url = urllib.parse.urlunparse(parsed._replace(path="/api/generate", query="", fragment=""))
            body = {"model": runtime["model_name"], "prompt": str(prompt), "system": str(system_prompt), "stream": False, "options": {"num_predict": max(1, min(int(max_tokens), 4096))}}
        else:
            url = urllib.parse.urlunparse(parsed._replace(path="/v1/chat/completions", query="", fragment=""))
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": str(system_prompt)})
            messages.append({"role": "user", "content": str(prompt)})
            body = {"model": runtime["model_name"], "messages": messages, "max_tokens": max(1, min(int(max_tokens), 4096)), "stream": False}
        request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        status, data, latency = self._http(request, timeout=60)
        if not 200 <= status < 300:
            raise Conflict(f"Model runtime returned HTTP {status}.")
        if runtime["provider_type"] == "ollama":
            text = str(data.get("response") or "")
        else:
            choices = data.get("choices") or []
            text = str((choices[0].get("message") or {}).get("content") or "") if choices else ""
        self.publish_event(actor, runtime["institution_id"], channel=f"user:{actor}", event_type="model_generation_completed", target_type="model_runtime", target_id=runtime_id, payload={"latency_ms": latency, "characters": len(text)})
        return {"runtime_id": runtime_id, "model": runtime["model_name"], "text": text, "latency_ms": latency, "external_processing": bool(runtime["external_processing"])}

    # ------------------------------------------------------------------
    # Built-in Science Pulse provider synchronisation.
    # ------------------------------------------------------------------
    def configure_pulse_provider(
        self,
        actor: str,
        institution_id: str,
        *,
        provider: str,
        name: str,
        query: str,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_admin(actor, institution_id)
        provider_name = str(provider).strip().lower()
        if provider_name not in PROVIDERS:
            raise EducationError("Unsupported Science Pulse provider.")
        config_id, stamp = ident("pulseprovider"), now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_pulse_provider_configs VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,provider,name) DO UPDATE SET query_text=excluded.query_text,config_json=excluded.config_json,state='active',updated_at=excluded.updated_at""",
                (config_id, institution_id, provider_name, str(name).strip(), str(query).strip(), "", "active", _json(config or {}), actor, stamp, stamp),
            )
        return self.platform._one("SELECT * FROM education_pulse_provider_configs WHERE institution_id=? AND provider=? AND name=?", (institution_id, provider_name, str(name).strip()))

    def sync_pulse_provider(self, actor: str, config_id: str, *, limit: int = 20) -> dict[str, Any]:
        config = self.platform._one("SELECT * FROM education_pulse_provider_configs WHERE id=?", (config_id,))
        if not config:
            raise Missing("Science Pulse provider configuration not found.")
        self._require_admin(actor, config["institution_id"])
        run_id, stamp = ident("pulserun"), now()
        with self.db.connection() as db:
            db.execute("INSERT INTO education_pulse_provider_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (run_id, config_id, config["institution_id"], "running", 0, 0, config["cursor_text"], "{}", "", actor, stamp, None))
        try:
            records, next_cursor = fetch_provider(config["provider"], config["query_text"], limit=limit, cursor=config["cursor_text"], opener=self.provider_opener)
            inserted = 0
            with self.db.connection() as db:
                for item in records:
                    record_id = ident("pulseext")
                    before = self.platform._one("SELECT id FROM education_pulse_external_records WHERE institution_id=? AND provider=? AND external_id=?", (config["institution_id"], config["provider"], item["external_id"]))
                    db.execute(
                        """INSERT INTO education_pulse_external_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(institution_id,provider,external_id) DO UPDATE SET doi=excluded.doi,pmid=excluded.pmid,title=excluded.title,
                        abstract_excerpt=excluded.abstract_excerpt,authors_json=excluded.authors_json,source_url=excluded.source_url,published_at=excluded.published_at,
                        record_type=excluded.record_type,metadata_json=excluded.metadata_json,updated_at=excluded.updated_at""",
                        (record_id, config["institution_id"], config["provider"], item["external_id"], item.get("doi", ""), item.get("pmid", ""), item["title"], item.get("abstract_excerpt", ""), _json(item.get("authors", [])), item["source_url"], item.get("published_at", ""), item.get("record_type", "journal"), _json(item.get("metadata", {})), stamp, now()),
                    )
                    if not before:
                        inserted += 1
                db.execute("UPDATE education_pulse_provider_configs SET cursor_text=?,updated_at=? WHERE id=?", (next_cursor, now(), config_id))
                db.execute("UPDATE education_pulse_provider_runs SET state='completed',received_count=?,inserted_count=?,cursor_text=?,evidence_json=?,completed_at=? WHERE id=?", (len(records), inserted, next_cursor, _json({"provider": config["provider"], "query": config["query_text"]}), now(), run_id))
            self.publish_event(actor, config["institution_id"], channel="science-pulse", event_type="provider_sync_completed", target_type="pulse_provider", target_id=config_id, payload={"received": len(records), "inserted": inserted})
        except Exception as exc:
            with self.db.connection() as db:
                db.execute("UPDATE education_pulse_provider_runs SET state='failed',error_text=?,completed_at=? WHERE id=?", (f"{type(exc).__name__}: {exc}"[:4000], now(), run_id))
        row = self.platform._one("SELECT * FROM education_pulse_provider_runs WHERE id=?", (run_id,))
        row["evidence"] = _decode(row.pop("evidence_json", "{}"), {})
        return row

    # ------------------------------------------------------------------
    # Academy media registration and server-governed playback telemetry.
    # ------------------------------------------------------------------
    def register_media_asset(self, actor: str, lecture_id: str, source_path: str | Path, *, probe: bool = True) -> dict[str, Any]:
        lecture = self.platform._one("SELECT * FROM lectures WHERE id=?", (lecture_id,))
        if not lecture:
            raise Missing("Lecture not found.")
        self._require_staff(actor, lecture["institution_id"])
        path = Path(source_path).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() not in VIDEO_SUFFIXES:
            raise EducationError("A supported local video file is required.")
        probe_data: dict[str, Any] = {}
        duration, width, height, video_codec, audio_codec = 0.0, 0, 0, "", ""
        if probe and shutil.which("ffprobe"):
            completed = subprocess.run(
                ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                capture_output=True, text=True, timeout=30, check=False,
            )
            if completed.returncode == 0:
                probe_data = json.loads(completed.stdout or "{}")
                duration = float((probe_data.get("format") or {}).get("duration") or 0)
                for stream in probe_data.get("streams", []):
                    if stream.get("codec_type") == "video" and not video_codec:
                        video_codec = str(stream.get("codec_name") or "")
                        width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
                    if stream.get("codec_type") == "audio" and not audio_codec:
                        audio_codec = str(stream.get("codec_name") or "")
        duration = duration or float(lecture.get("duration_seconds") or 0)
        asset_id, stamp = ident("mediaasset"), now()
        digest = _sha256_file(path)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_media_assets_v15 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(lecture_id,sha256) DO UPDATE SET source_path=excluded.source_path,size_bytes=excluded.size_bytes,mime_type=excluded.mime_type,
                duration_seconds=excluded.duration_seconds,width=excluded.width,height=excluded.height,video_codec=excluded.video_codec,audio_codec=excluded.audio_codec,
                probe_json=excluded.probe_json,processing_state=excluded.processing_state,updated_at=excluded.updated_at""",
                (asset_id, lecture["institution_id"], lecture_id, str(path), digest, path.stat().st_size, mime, duration, width, height, video_codec, audio_codec, _json(probe_data), "probed" if probe_data else "registered", actor, stamp, stamp),
            )
            if duration > 0:
                db.execute("UPDATE lectures SET duration_seconds=?,processing_state='ready',video_path=?,sha256=?,size_bytes=?,mime_type=?,updated_at=? WHERE id=?", (duration, str(path), digest, path.stat().st_size, mime, stamp, lecture_id))
        return self.platform._one("SELECT * FROM education_media_assets_v15 WHERE lecture_id=? AND sha256=?", (lecture_id, digest))

    def _lecture_access(self, actor: str, lecture: dict[str, Any]) -> None:
        roles = self._roles(actor, lecture["institution_id"])
        if roles & TEACHER_ROLES:
            return
        enrolled = self.platform._one("SELECT id FROM academy_enrollments WHERE course_id=? AND student_id=? AND state='active'", (lecture["course_id"], actor))
        if not enrolled:
            raise Denied("Active course enrollment is required for lecture playback.")

    def record_playback_event(
        self,
        actor: str,
        lecture_id: str,
        *,
        event_type: str,
        position_seconds: float,
        session_id: str,
        client_event_id: str,
        playback_rate: float = 1.0,
    ) -> dict[str, Any]:
        lecture = self.platform._one("SELECT * FROM lectures WHERE id=?", (lecture_id,))
        if not lecture:
            raise Missing("Lecture not found.")
        self._lecture_access(actor, lecture)
        event = str(event_type).strip().lower()
        if event not in MEDIA_EVENTS:
            raise EducationError("Unsupported playback event.")
        position = max(0.0, float(position_seconds))
        duration = float(lecture.get("duration_seconds") or 0)
        if duration and position > duration + 5:
            raise EducationError("Playback position exceeds lecture duration.")
        rate = max(0.25, min(float(playback_rate), 4.0))
        previous = self.platform._one(
            "SELECT * FROM education_media_playback_events_v15 WHERE lecture_id=? AND user_id=? AND session_id=? ORDER BY created_at DESC LIMIT 1",
            (lecture_id, actor, str(session_id)),
        )
        if previous and event in {"progress", "pause", "ended"} and previous["event_type"] != "seek":
            elapsed = max(0.0, (datetime.now(timezone.utc) - parse_time(previous["created_at"])).total_seconds())
            maximum = float(previous["position_seconds"]) + elapsed * max(rate, float(previous["playback_rate"])) * 2.0 + 20.0
            if position > maximum:
                raise Conflict("Playback telemetry jump exceeded the server-side plausibility bound; submit a seek event first.")
        row_id = ident("playback")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_media_playback_events_v15 VALUES(?,?,?,?,?,?,?,?,?,?)",
                (row_id, lecture["institution_id"], lecture_id, actor, event, position, rate, str(session_id)[:200], str(client_event_id)[:200], now()),
            )
        summary = self.playback_summary(actor, lecture_id)
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO watch_progress(id,lecture_id,user_id,seconds,completed,updated_at) VALUES(?,?,?,?,?,?)
                ON CONFLICT(lecture_id,user_id) DO UPDATE SET seconds=excluded.seconds,completed=excluded.completed,updated_at=excluded.updated_at""",
                (ident("watch"), lecture_id, actor, summary["observed_watch_seconds"], int(summary["completed"]), now()),
            )
        return {"event_id": row_id, **summary}

    def playback_summary(self, actor: str, lecture_id: str) -> dict[str, Any]:
        lecture = self.platform._one("SELECT * FROM lectures WHERE id=?", (lecture_id,))
        if not lecture:
            raise Missing("Lecture not found.")
        self._lecture_access(actor, lecture)
        rows = self.platform._all(
            "SELECT * FROM education_media_playback_events_v15 WHERE lecture_id=? AND user_id=? ORDER BY session_id,created_at,id",
            (lecture_id, actor),
        )
        by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_session[str(row["session_id"])].append(row)
        observed = 0.0
        maximum_position = 0.0
        for events in by_session.values():
            for previous, current in zip(events, events[1:]):
                maximum_position = max(maximum_position, float(current["position_seconds"]))
                if current["event_type"] == "seek" or previous["event_type"] == "seek":
                    continue
                delta = float(current["position_seconds"]) - float(previous["position_seconds"])
                elapsed = max(0.0, (parse_time(current["created_at"]) - parse_time(previous["created_at"])).total_seconds())
                if delta > 0:
                    observed += min(delta, elapsed * max(float(current["playback_rate"]), 1.0) * 1.5 + 5.0)
        duration = float(lecture.get("duration_seconds") or 0)
        observed = min(duration, observed) if duration else observed
        threshold = duration * 0.85 if duration else math.inf
        return {
            "lecture_id": lecture_id, "user_id": actor, "event_count": len(rows), "observed_watch_seconds": round(observed, 2),
            "max_position_seconds": round(maximum_position, 2), "duration_seconds": duration,
            "completion_threshold_seconds": round(threshold, 2) if math.isfinite(threshold) else None,
            "completed": bool(duration and observed >= threshold),
            "policy": "Completion uses server-observed plausible playback intervals; seek-only progress does not count.",
        }

    def phase15_posture(self, actor: str, institution_id: str) -> dict[str, Any]:
        self._require_admin(actor, institution_id)
        def count(table: str, condition: str = "1=1") -> int:
            row = self.platform._one(f"SELECT COUNT(*) count FROM {table} WHERE institution_id=? AND {condition}", (institution_id,)) or {"count": 0}
            return int(row["count"])
        controls = {
            "durable_realtime_events": True,
            "hybrid_bm25_vector_rag": True,
            "permission_filtered_retrieval": True,
            "local_and_opt_in_model_runtimes": True,
            "built_in_science_pulse_connectors": True,
            "server_governed_media_telemetry": True,
            "external_runtime_truthfulness": True,
        }
        return {
            "institution_id": institution_id,
            "migration": MIGRATION_ID,
            "counts": {
                "events": count("education_realtime_events"),
                "rag_indexes": count("education_rag_vector_indexes"),
                "verified_model_runtimes": count("education_model_runtimes", "state='verified'"),
                "pulse_records": count("education_pulse_external_records"),
                "media_assets": count("education_media_assets_v15"),
            },
            "local_controls": controls,
            "local_control_coverage_percent": 100.0,
            "qualification_boundaries": [
                "A configured remote model endpoint is not verified until a live HTTP check succeeds.",
                "Science provider availability and rate limits depend on public services.",
                "Media transcoding requires ffmpeg/ffprobe on the deployment machine.",
                "The durable event stream is SSE-ready; multi-node fan-out requires Redis or another external broker.",
                "The legacy application database remains SQLite-first until a complete repository cutover is independently rehearsed.",
            ],
        }
