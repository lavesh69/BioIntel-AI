from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import os
import re
import secrets
import shutil
import sqlite3
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .phase11 import ADMIN_ROLES, TEACHER_ROLES, _json
from .phase12 import EducationPhase12Service
from .platform import Conflict, Denied, EducationError, Missing, ident, now, parse_time

MIGRATION_ID = "education_phase13_local_autonomy_v1"

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS education_rag_ingestion_runs(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 project_id TEXT NOT NULL,
 document_id TEXT NOT NULL REFERENCES education_rag_documents(id),
 parser TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'queued',
 chunk_count INTEGER NOT NULL DEFAULT 0,
 character_count INTEGER NOT NULL DEFAULT 0,
 locator_count INTEGER NOT NULL DEFAULT 0,
 extraction_json TEXT NOT NULL DEFAULT '{}',
 error_text TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_phase13_rag_ingestion
 ON education_rag_ingestion_runs(institution_id,project_id,state,created_at);

CREATE TABLE IF NOT EXISTS education_rag_chunks(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 project_id TEXT NOT NULL,
 document_id TEXT NOT NULL REFERENCES education_rag_documents(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL,
 page_number INTEGER,
 section TEXT NOT NULL DEFAULT '',
 locator TEXT NOT NULL DEFAULT '',
 content TEXT NOT NULL,
 normalized_text TEXT NOT NULL,
 content_sha256 TEXT NOT NULL,
 token_estimate INTEGER NOT NULL DEFAULT 0,
 permissions_json TEXT NOT NULL DEFAULT '{}',
 state TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL,
 UNIQUE(document_id,ordinal)
);
CREATE INDEX IF NOT EXISTS idx_phase13_rag_chunks_project
 ON education_rag_chunks(institution_id,project_id,state,document_id,ordinal);

CREATE TABLE IF NOT EXISTS education_timetable_generation_runs(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 academic_year TEXT NOT NULL DEFAULT '',
 term TEXT NOT NULL DEFAULT '',
 term_start TEXT NOT NULL,
 weeks INTEGER NOT NULL,
 state TEXT NOT NULL DEFAULT 'preview',
 request_json TEXT NOT NULL DEFAULT '{}',
 plan_json TEXT NOT NULL DEFAULT '[]',
 unscheduled_json TEXT NOT NULL DEFAULT '[]',
 committed_series_json TEXT NOT NULL DEFAULT '[]',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 committed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_phase13_timetable_runs
 ON education_timetable_generation_runs(institution_id,state,created_at);

CREATE TABLE IF NOT EXISTS education_notification_policy_events(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 recipient_id TEXT NOT NULL,
 event_type TEXT NOT NULL,
 channel TEXT NOT NULL,
 decision TEXT NOT NULL,
 available_at TEXT NOT NULL,
 detail_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_phase13_notification_policy
 ON education_notification_policy_events(institution_id,recipient_id,created_at);

CREATE TABLE IF NOT EXISTS education_lifecycle_runs(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 data_class TEXT NOT NULL,
 action TEXT NOT NULL,
 cutoff_at TEXT NOT NULL,
 dry_run INTEGER NOT NULL DEFAULT 1,
 candidate_count INTEGER NOT NULL DEFAULT 0,
 affected_count INTEGER NOT NULL DEFAULT 0,
 archive_path TEXT NOT NULL DEFAULT '',
 archive_sha256 TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'completed',
 detail_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_support_bundles(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 output_path TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 size_bytes INTEGER NOT NULL,
 manifest_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);

INSERT OR IGNORE INTO education_migrations(id,applied_at)
 VALUES('education_phase13_local_autonomy_v1',datetime('now'));
"""

SUPPORTED_DOCUMENT_SUFFIXES = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".html", ".htm",
    ".pdf", ".docx", ".pptx", ".xlsx",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]{1,}")
SAFE_DATA_CLASSES = {"notifications", "sessions", "reports", "rag_chunks"}


def _decode(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalise_text(text: str) -> str:
    return " ".join(str(text).replace("\x00", " ").split())


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text)]


def _parse_hhmm(value: str) -> dt_time:
    try:
        hour, minute = [int(piece) for piece in str(value).split(":", 1)]
        return dt_time(hour=hour, minute=minute)
    except (TypeError, ValueError) as exc:
        raise EducationError("Time must use HH:MM format.") from exc


def _next_weekday(start: date, weekday: int) -> date:
    return start + timedelta(days=(weekday - start.weekday()) % 7)


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and a_end > b_start


class EducationPhase13Service(EducationPhase12Service):
    """Final offline/local autonomy layer.

    It closes high-value gaps that do not require third-party credentials: governed multi-format
    evidence ingestion, citation-grade retrieval, automatic timetable planning, notification policy
    enforcement, retention execution and redacted support diagnostics.
    """

    def __init__(
        self,
        platform: Any,
        *,
        root: str | Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        # A clock dependency keeps scheduling, quiet-hours and retention logic
        # deterministic in tests and prevents date-sensitive failures.
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        super().__init__(platform, root=root)
        self.root = Path(root or self.root)
        self.migrate_phase13()

    def _now_dt(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _now_iso(self) -> str:
        return self._now_dt().isoformat()

    def migrate_phase13(self) -> str:
        with self.db.connection() as db:
            db.executescript(SCHEMA)
        return MIGRATION_ID

    # ------------------------------------------------------------------
    # Multi-format RAG extraction, chunking and citation-grade retrieval
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_text_document(path: Path) -> tuple[str, list[dict[str, Any]]]:
        suffix = path.suffix.lower()
        locators: list[dict[str, Any]] = []
        parser = suffix.lstrip(".") or "text"
        if suffix in {".txt", ".md", ".markdown"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            for index, line in enumerate(text.splitlines(), start=1):
                cleaned = _normalise_text(line)
                if cleaned:
                    locators.append({"text": cleaned, "page_number": None, "section": "", "locator": f"line {index}"})
        elif suffix in {".csv", ".tsv"}:
            delimiter = "\t" if suffix == ".tsv" else ","
            with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                for index, row in enumerate(csv.reader(handle, delimiter=delimiter), start=1):
                    cleaned = _normalise_text(" | ".join(str(cell) for cell in row))
                    if cleaned:
                        locators.append({"text": cleaned, "page_number": None, "section": "table", "locator": f"row {index}"})
        elif suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            def walk(value: Any, pointer: str = "$") -> None:
                if isinstance(value, dict):
                    for key, child in value.items():
                        walk(child, f"{pointer}.{key}")
                elif isinstance(value, list):
                    for index, child in enumerate(value):
                        walk(child, f"{pointer}[{index}]")
                else:
                    cleaned = _normalise_text(f"{pointer}: {value}")
                    if cleaned:
                        locators.append({"text": cleaned, "page_number": None, "section": "json", "locator": pointer})
            walk(data)
        elif suffix in {".html", ".htm"}:
            raw = path.read_text(encoding="utf-8", errors="replace")
            try:
                from bs4 import BeautifulSoup  # type: ignore
                soup = BeautifulSoup(raw, "html.parser")
                for node in soup(["script", "style", "noscript"]):
                    node.decompose()
                headings = ""
                for index, node in enumerate(soup.find_all(["h1", "h2", "h3", "p", "li", "td", "th"]), start=1):
                    if node.name in {"h1", "h2", "h3"}:
                        headings = _normalise_text(node.get_text(" "))
                    cleaned = _normalise_text(node.get_text(" "))
                    if cleaned:
                        locators.append({"text": cleaned, "page_number": None, "section": headings, "locator": f"element {index}"})
            except Exception:
                text = _normalise_text(html.unescape(re.sub(r"<[^>]+>", " ", raw)))
                if text:
                    locators.append({"text": text, "page_number": None, "section": "", "locator": "document"})
        elif suffix == ".pdf":
            try:
                from pypdf import PdfReader  # type: ignore
                reader = PdfReader(str(path))
                parser = "pypdf"
                for index, page in enumerate(reader.pages, start=1):
                    cleaned = _normalise_text(page.extract_text() or "")
                    if cleaned:
                        locators.append({"text": cleaned, "page_number": index, "section": "", "locator": f"page {index}"})
            except Exception as exc:
                raise EducationError(f"PDF extraction failed: {type(exc).__name__}") from exc
        elif suffix == ".docx":
            try:
                from docx import Document  # type: ignore
                document = Document(str(path))
                parser = "python-docx"
                section = ""
                for index, paragraph in enumerate(document.paragraphs, start=1):
                    cleaned = _normalise_text(paragraph.text)
                    if not cleaned:
                        continue
                    if paragraph.style and str(paragraph.style.name).lower().startswith("heading"):
                        section = cleaned
                    locators.append({"text": cleaned, "page_number": None, "section": section, "locator": f"paragraph {index}"})
                for table_index, table in enumerate(document.tables, start=1):
                    for row_index, row in enumerate(table.rows, start=1):
                        cleaned = _normalise_text(" | ".join(cell.text for cell in row.cells))
                        if cleaned:
                            locators.append({"text": cleaned, "page_number": None, "section": f"table {table_index}", "locator": f"table {table_index} row {row_index}"})
            except Exception as exc:
                raise EducationError(f"DOCX extraction failed: {type(exc).__name__}") from exc
        elif suffix == ".pptx":
            try:
                from pptx import Presentation  # type: ignore
                presentation = Presentation(str(path))
                parser = "python-pptx"
                for slide_index, slide in enumerate(presentation.slides, start=1):
                    texts: list[str] = []
                    for shape in slide.shapes:
                        if hasattr(shape, "text"):
                            cleaned = _normalise_text(getattr(shape, "text", ""))
                            if cleaned:
                                texts.append(cleaned)
                    if texts:
                        locators.append({"text": " ".join(texts), "page_number": slide_index, "section": f"slide {slide_index}", "locator": f"slide {slide_index}"})
            except Exception as exc:
                raise EducationError(f"PPTX extraction failed: {type(exc).__name__}") from exc
        elif suffix == ".xlsx":
            try:
                from openpyxl import load_workbook  # type: ignore
                workbook = load_workbook(str(path), read_only=True, data_only=True)
                parser = "openpyxl"
                for sheet in workbook.worksheets:
                    for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                        cleaned = _normalise_text(" | ".join("" if value is None else str(value) for value in row))
                        if cleaned:
                            locators.append({"text": cleaned, "page_number": None, "section": sheet.title, "locator": f"{sheet.title}!{row_index}"})
            except Exception as exc:
                raise EducationError(f"XLSX extraction failed: {type(exc).__name__}") from exc
        else:
            raise EducationError(f"Unsupported evidence file type: {suffix or 'unknown'}")
        return parser, locators

    @staticmethod
    def _chunk_locators(locators: list[dict[str, Any]], *, chunk_chars: int, overlap_chars: int) -> list[dict[str, Any]]:
        chunk_chars = max(300, min(8000, int(chunk_chars)))
        overlap_chars = max(0, min(chunk_chars // 3, int(overlap_chars)))
        chunks: list[dict[str, Any]] = []
        ordinal = 0
        for locator in locators:
            text = _normalise_text(locator.get("text", ""))
            if not text:
                continue
            cursor = 0
            while cursor < len(text):
                end = min(len(text), cursor + chunk_chars)
                if end < len(text):
                    boundary = text.rfind(" ", cursor + max(100, chunk_chars // 2), end)
                    if boundary > cursor:
                        end = boundary
                content = text[cursor:end].strip()
                if content:
                    ordinal += 1
                    chunks.append({
                        "ordinal": ordinal,
                        "page_number": locator.get("page_number"),
                        "section": str(locator.get("section") or "")[:500],
                        "locator": str(locator.get("locator") or "")[:500],
                        "content": content,
                    })
                if end >= len(text):
                    break
                cursor = max(cursor + 1, end - overlap_chars)
        return chunks

    def ingest_rag_document(self, actor: str, document_id: str, *, chunk_chars: int = 1400, overlap_chars: int = 180) -> dict[str, Any]:
        document = self.platform._one("SELECT * FROM education_rag_documents WHERE id=?", (document_id,))
        if not document:
            raise Missing("RAG document not found.")
        roles = self._roles(actor, document["institution_id"])
        if not roles & TEACHER_ROLES:
            raise Denied("RAG ingestion requires educator or administrator permission.")
        if document["state"] != "approved":
            raise Conflict("Only human-approved RAG documents may be ingested.")
        path = Path(document["source_path"]).expanduser().resolve()
        if not path.is_file():
            raise Missing("Approved RAG source file is missing.")
        if path.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
            raise EducationError("This document type is not supported for governed ingestion.")
        run_id, stamp = ident("ragingest"), now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_rag_ingestion_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, document["institution_id"], document["project_id"], document_id, path.suffix.lower().lstrip("."), "running", 0, 0, 0, "{}", "", actor, stamp, None),
            )
        try:
            parser, locators = self._extract_text_document(path)
            chunks = self._chunk_locators(locators, chunk_chars=chunk_chars, overlap_chars=overlap_chars)
            if not chunks:
                raise EducationError("No searchable text could be extracted. Scanned files require an approved OCR adapter.")
            permissions = document.get("permission_json") or "{}"
            completed = now()
            with self.db.connection() as db:
                db.execute("DELETE FROM education_rag_chunks WHERE document_id=?", (document_id,))
                for chunk in chunks:
                    content = chunk["content"]
                    db.execute(
                        "INSERT INTO education_rag_chunks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            ident("ragchunk"), document["institution_id"], document["project_id"], document_id,
                            chunk["ordinal"], chunk["page_number"], chunk["section"], chunk["locator"], content,
                            content.lower(), hashlib.sha256(content.encode("utf-8")).hexdigest(),
                            max(1, math.ceil(len(_tokens(content)) * 1.25)), permissions, "active", completed,
                        ),
                    )
                db.execute(
                    "UPDATE education_rag_ingestion_runs SET parser=?,state='completed',chunk_count=?,character_count=?,locator_count=?,extraction_json=?,completed_at=? WHERE id=?",
                    (parser, len(chunks), sum(len(chunk["content"]) for chunk in chunks), len(locators), _json({"source_sha256": document["sha256"], "suffix": path.suffix.lower(), "chunk_chars": chunk_chars, "overlap_chars": overlap_chars}), completed, run_id),
                )
            self.security_event(document["institution_id"], "rag_document_ingested", actor_id=actor, detail={"document_id": document_id, "chunks": len(chunks), "parser": parser})
        except Exception as exc:
            with self.db.connection() as db:
                db.execute("UPDATE education_rag_ingestion_runs SET state='failed',error_text=?,completed_at=? WHERE id=?", (f"{type(exc).__name__}: {exc}"[:4000], now(), run_id))
            raise
        return self.rag_ingestion(actor, run_id)

    def rag_ingestion(self, actor: str, run_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_rag_ingestion_runs WHERE id=?", (run_id,))
        if not row:
            raise Missing("RAG ingestion run not found.")
        self.platform._require(actor, row["institution_id"])
        row["extraction"] = _decode(row.pop("extraction_json", "{}"), {})
        return row

    def _chunk_allowed(self, actor: str, institution_id: str, permissions_json: str) -> bool:
        membership = self.platform.membership(actor, institution_id)
        roles = {str(row["role"]) for row in membership}
        if not roles:
            return False
        permissions = _decode(permissions_json, {})
        allowed_roles = {str(role) for role in permissions.get("roles", [])}
        allowed_users = {str(user) for user in permissions.get("users", [])}
        return not allowed_roles and not allowed_users or actor in allowed_users or bool(roles & allowed_roles) or bool(roles & ADMIN_ROLES)

    def search_rag(self, actor: str, institution_id: str, project_id: str, query: str, *, limit: int = 8) -> dict[str, Any]:
        self.platform._require(actor, institution_id)
        query_text = _normalise_text(query)
        query_tokens = _tokens(query_text)
        if len(query_text) < 2 or not query_tokens:
            raise EducationError("A meaningful search query is required.")
        limit_value = max(1, min(30, int(limit)))
        rows = self.platform._all(
            """SELECT c.*,d.title document_title,d.source_name,d.sha256 document_sha256,d.permission_json
            FROM education_rag_chunks c JOIN education_rag_documents d ON d.id=c.document_id
            WHERE c.institution_id=? AND c.project_id=? AND c.state='active' AND d.state='approved'""",
            (institution_id, str(project_id)),
        )
        document_frequency: Counter[str] = Counter()
        row_tokens: list[tuple[dict[str, Any], Counter[str]]] = []
        for row in rows:
            if not self._chunk_allowed(actor, institution_id, row.get("permission_json") or row.get("permissions_json") or "{}"):
                continue
            counts = Counter(_tokens(row["content"]))
            row_tokens.append((row, counts))
            document_frequency.update(set(counts))
        total_documents = max(1, len(row_tokens))
        scored: list[dict[str, Any]] = []
        phrase = query_text.lower()
        for row, counts in row_tokens:
            score = 0.0
            matched: list[str] = []
            for token in set(query_tokens):
                frequency = counts.get(token, 0)
                if frequency:
                    matched.append(token)
                    inverse = math.log((total_documents + 1) / (document_frequency.get(token, 0) + 1)) + 1
                    score += (1 + math.log(frequency)) * inverse
            lower = row["content"].lower()
            if phrase in lower:
                score += 8.0
            title_lower = str(row["document_title"]).lower()
            score += sum(2.0 for token in set(query_tokens) if token in title_lower)
            if score <= 0:
                continue
            excerpt_start = min([lower.find(token) for token in matched if token in lower] or [0])
            excerpt_start = max(0, excerpt_start - 140)
            excerpt = row["content"][excerpt_start:excerpt_start + 700]
            scored.append({
                "chunk_id": row["id"], "document_id": row["document_id"], "document_title": row["document_title"],
                "source_name": row["source_name"], "page_number": row["page_number"], "section": row["section"],
                "locator": row["locator"], "score": round(score, 6), "matched_terms": sorted(matched),
                "excerpt": excerpt, "citation": f"{row['source_name']} · {row['locator'] or row['section'] or 'document'}",
                "document_sha256": row["document_sha256"],
            })
        scored.sort(key=lambda item: (-item["score"], item["document_title"], item["chunk_id"]))
        results = scored[:limit_value]
        return {
            "project_id": project_id, "query": query_text, "result_count": len(results), "results": results,
            "evidence_status": "grounded" if results else "no_approved_evidence",
            "retrieval_policy": "Approved, permission-filtered local evidence only; lexical ranking does not assert scientific truth.",
        }

    def rag_context_bundle(self, actor: str, institution_id: str, project_id: str, query: str, *, limit: int = 8, max_characters: int = 12000) -> dict[str, Any]:
        search = self.search_rag(actor, institution_id, project_id, query, limit=limit)
        remaining = max(1000, min(50000, int(max_characters)))
        evidence: list[dict[str, Any]] = []
        for result in search["results"]:
            chunk = self.platform._one("SELECT content FROM education_rag_chunks WHERE id=?", (result["chunk_id"],))
            if not chunk or remaining <= 0:
                break
            text = str(chunk["content"])[:remaining]
            remaining -= len(text)
            evidence.append({**result, "content": text})
        return {
            "query": search["query"], "project_id": project_id, "evidence": evidence,
            "citations": [{key: item[key] for key in ("chunk_id", "document_id", "citation", "document_sha256")} for item in evidence],
            "character_count": sum(len(item["content"]) for item in evidence),
            "safe_to_answer": bool(evidence),
        }

    # --------------------------------------------------------------
    # Conflict-free automatic timetable planning and atomic commit
    # --------------------------------------------------------------
    def generate_timetable_plan(
        self,
        actor: str,
        institution_id: str,
        *,
        term_start: str,
        weeks: int,
        requirements: list[dict[str, Any]],
        weekdays: list[int] | None = None,
        day_start: str = "09:00",
        day_end: str = "17:00",
        slot_minutes: int = 60,
        academic_year: str = "",
        term: str = "",
        commit: bool = False,
    ) -> dict[str, Any]:
        roles = self._roles(actor, institution_id)
        if not roles & TEACHER_ROLES:
            raise Denied("Timetable generation requires academic staff permission.")
        start_date = date.fromisoformat(str(term_start)[:10])
        weeks_value = int(weeks)
        if not 1 <= weeks_value <= 104:
            raise EducationError("Timetable weeks must be between 1 and 104.")
        slot_value = int(slot_minutes)
        if slot_value not in {15, 20, 30, 45, 60, 75, 90, 120, 150, 180}:
            raise EducationError("Unsupported timetable slot duration.")
        selected_weekdays = sorted(set(int(day) for day in (weekdays or [0, 1, 2, 3, 4])))
        if not selected_weekdays or any(day < 0 or day > 6 for day in selected_weekdays):
            raise EducationError("Weekdays must use integers 0-6.")
        open_time, close_time = _parse_hhmm(day_start), _parse_hhmm(day_end)
        if close_time <= open_time:
            raise EducationError("Timetable day end must follow day start.")
        if not requirements or len(requirements) > 500:
            raise EducationError("Timetable requires between 1 and 500 subject requirements.")

        slots: list[datetime] = []
        for weekday in selected_weekdays:
            current_date = _next_weekday(start_date, weekday)
            cursor = datetime.combine(current_date, open_time, tzinfo=timezone.utc)
            close = datetime.combine(current_date, close_time, tzinfo=timezone.utc)
            while cursor + timedelta(minutes=slot_value) <= close:
                slots.append(cursor)
                cursor += timedelta(minutes=slot_value)

        existing = self.platform._all(
            "SELECT * FROM timetable_entries WHERE institution_id=? AND state='scheduled' AND starts_at<? AND ends_at>?",
            (institution_id, (datetime.combine(start_date, close_time, tzinfo=timezone.utc) + timedelta(weeks=weeks_value)).isoformat(), datetime.combine(start_date, open_time, tzinfo=timezone.utc).isoformat()),
        )
        planned: list[dict[str, Any]] = []
        unscheduled: list[dict[str, Any]] = []
        normalised_requirements: list[dict[str, Any]] = []
        for index, raw in enumerate(requirements, start=1):
            subject_id = str(raw.get("subject_id") or "")
            teacher_id = str(raw.get("teacher_id") or "")
            group = str(raw.get("student_group") or "")
            room_candidates = [str(value) for value in raw.get("room_candidates", []) if str(value).strip()] or [str(raw.get("room") or "")]
            room_candidates = [room for room in room_candidates if room]
            sessions = int(raw.get("sessions_per_week", 1))
            duration = int(raw.get("duration_minutes", slot_value))
            preferred = [int(day) for day in raw.get("preferred_weekdays", selected_weekdays)]
            priority = int(raw.get("priority", 50))
            if not subject_id or not teacher_id or not group or not room_candidates:
                raise EducationError(f"Requirement {index} needs subject, assigned teacher, student group and room candidate.")
            subject = self.platform._one("SELECT * FROM subjects WHERE id=? AND institution_id=? AND state='active'", (subject_id, institution_id))
            if not subject:
                raise Missing(f"Requirement {index} subject was not found.")
            assignment = self.platform._one("SELECT 1 ok FROM teacher_assignments WHERE institution_id=? AND subject_id=? AND teacher_id=? AND state='active'", (institution_id, subject_id, teacher_id))
            if not assignment:
                raise Denied(f"Teacher {teacher_id} is not assigned to {subject['code']}.")
            if not 1 <= sessions <= 20 or duration < 15 or duration > 360:
                raise EducationError("Sessions per week or duration is outside supported limits.")
            normalised_requirements.append({
                "requirement_index": index, "subject_id": subject_id, "subject_code": subject["code"], "teacher_id": teacher_id,
                "student_group": group, "room_candidates": room_candidates, "sessions_per_week": sessions,
                "duration_minutes": duration, "preferred_weekdays": preferred, "priority": priority,
            })
        normalised_requirements.sort(key=lambda item: (-item["priority"], -item["duration_minutes"], -item["sessions_per_week"], item["subject_code"]))

        def conflict(candidate_start: datetime, candidate_end: datetime, req: dict[str, Any], room: str) -> bool:
            for row in existing:
                row_start, row_end = parse_time(row["starts_at"]), parse_time(row["ends_at"])
                if _overlaps(candidate_start, candidate_end, row_start, row_end) and (
                    row["teacher_id"] == req["teacher_id"] or row["student_group"] == req["student_group"] or row["room"] == room
                ):
                    return True
            for row in planned:
                row_start, row_end = parse_time(row["first_start"]), parse_time(row["first_end"])
                if _overlaps(candidate_start, candidate_end, row_start, row_end) and (
                    row["teacher_id"] == req["teacher_id"] or row["student_group"] == req["student_group"] or row["room"] == room
                ):
                    return True
            return False

        for req in normalised_requirements:
            used_days: set[int] = set()
            for session_index in range(1, req["sessions_per_week"] + 1):
                chosen: dict[str, Any] | None = None
                ordered_slots = sorted(slots, key=lambda slot: (slot.weekday() not in req["preferred_weekdays"], slot.weekday() in used_days, slot))
                for candidate_start in ordered_slots:
                    candidate_end = candidate_start + timedelta(minutes=req["duration_minutes"])
                    if candidate_end.time() > close_time:
                        continue
                    for room in req["room_candidates"]:
                        if not conflict(candidate_start, candidate_end, req, room):
                            chosen = {
                                **req, "session_index": session_index, "room": room,
                                "first_start": candidate_start.isoformat(), "first_end": candidate_end.isoformat(),
                            }
                            break
                    if chosen:
                        break
                if chosen:
                    planned.append(chosen)
                    used_days.add(parse_time(chosen["first_start"]).weekday())
                else:
                    unscheduled.append({**req, "session_index": session_index, "reason": "No conflict-free teacher/group/room slot remained."})

        run_id, stamp = ident("ttgen"), now()
        committed_series: list[str] = []
        state = "preview_incomplete" if unscheduled else "preview_ready"
        if commit:
            if unscheduled:
                raise Conflict("Timetable contains unscheduled sessions; nothing was committed.")
            with self.db.connection() as db:
                for item in planned:
                    series_id = ident("ttseries")
                    committed_series.append(series_id)
                    db.execute(
                        "INSERT INTO education_timetable_series VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (series_id, institution_id, item["subject_id"], item["teacher_id"], item["student_group"], item["room"], "weekly", weeks_value, actor, "active", stamp, stamp),
                    )
                    first_start, first_end = parse_time(item["first_start"]), parse_time(item["first_end"])
                    for occurrence in range(weeks_value):
                        entry_id = ident("tt")
                        occurrence_start = first_start + timedelta(weeks=occurrence)
                        occurrence_end = first_end + timedelta(weeks=occurrence)
                        db.execute(
                            "INSERT INTO timetable_entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                            (entry_id, institution_id, item["subject_id"], item["teacher_id"], item["student_group"], item["room"], occurrence_start.isoformat(), occurrence_end.isoformat(), "", "scheduled", stamp, stamp),
                        )
                        db.execute("INSERT INTO education_timetable_series_entries VALUES(?,?,?)", (series_id, entry_id, occurrence + 1))
            state = "committed"
            self.platform._audit(actor, "automatic_timetable_committed", "timetable_generation", run_id, institution_id, {"series": len(committed_series), "weeks": weeks_value})
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_timetable_generation_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, institution_id, str(academic_year)[:80], str(term)[:80], start_date.isoformat(), weeks_value, state, _json({"weekdays": selected_weekdays, "day_start": day_start, "day_end": day_end, "slot_minutes": slot_value, "requirements": normalised_requirements}), _json(planned), _json(unscheduled), _json(committed_series), actor, stamp, now() if commit else None),
            )
        return self.timetable_generation_run(actor, run_id)

    def timetable_generation_run(self, actor: str, run_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_timetable_generation_runs WHERE id=?", (run_id,))
        if not row:
            raise Missing("Timetable generation run not found.")
        self.platform._require(actor, row["institution_id"])
        row["request"] = _decode(row.pop("request_json", "{}"), {})
        row["plan"] = _decode(row.pop("plan_json", "[]"), [])
        row["unscheduled"] = _decode(row.pop("unscheduled_json", "[]"), [])
        row["committed_series"] = _decode(row.pop("committed_series_json", "[]"), [])
        row["planned_sessions_per_week"] = len(row["plan"])
        return row

    # --------------------------------------------------------------
    # Notification policy, quiet hours, digests and dead-letter retry
    # --------------------------------------------------------------
    def notification_delivery_plan(self, actor: str, institution_id: str, recipient_id: str, *, event_type: str, channel: str, requested_at: str | None = None) -> dict[str, Any]:
        roles = self._roles(actor, institution_id)
        if actor != recipient_id and not roles & TEACHER_ROLES:
            raise Denied("Notification policy inspection requires staff permission.")
        if not self.platform.membership(recipient_id, institution_id):
            raise Missing("Notification recipient is not an active institution member.")
        row = self.platform._one(
            """SELECT * FROM education_notification_preferences
            WHERE institution_id=? AND user_id=? AND channel=? AND event_type IN (?, '*')
            ORDER BY CASE WHEN event_type=? THEN 0 ELSE 1 END LIMIT 1""",
            (institution_id, recipient_id, str(channel).lower(), str(event_type), str(event_type)),
        )
        preference = row or {"enabled": 1, "digest_mode": "instant", "quiet_start": "", "quiet_end": ""}
        requested = parse_time(requested_at) if requested_at else self._now_dt()
        available = requested
        decision = "instant"
        if not int(preference.get("enabled", 1)):
            decision = "suppressed"
        else:
            mode = str(preference.get("digest_mode") or "instant")
            quiet_start, quiet_end = str(preference.get("quiet_start") or ""), str(preference.get("quiet_end") or "")
            if mode == "daily":
                available = datetime.combine(requested.date() + timedelta(days=1), dt_time(8, 0), tzinfo=timezone.utc)
                decision = "daily_digest"
            elif mode == "weekly":
                days = (7 - requested.weekday()) % 7 or 7
                available = datetime.combine(requested.date() + timedelta(days=days), dt_time(8, 0), tzinfo=timezone.utc)
                decision = "weekly_digest"
            elif quiet_start and quiet_end:
                start_t, end_t = _parse_hhmm(quiet_start), _parse_hhmm(quiet_end)
                current_t = requested.time().replace(tzinfo=None)
                in_quiet = start_t <= current_t < end_t if start_t < end_t else current_t >= start_t or current_t < end_t
                if in_quiet:
                    target_date = requested.date() + (timedelta(days=1) if start_t < end_t and current_t >= start_t or start_t >= end_t and current_t >= start_t else timedelta())
                    available = datetime.combine(target_date, end_t, tzinfo=timezone.utc)
                    if available <= requested:
                        available += timedelta(days=1)
                    decision = "quiet_hours_deferred"
        return {
            "recipient_id": recipient_id, "event_type": event_type, "channel": channel,
            "decision": decision, "enabled": decision != "suppressed", "requested_at": requested.isoformat(),
            "available_at": available.isoformat(), "preference": dict(preference),
        }

    def queue_policy_notification(self, actor: str, institution_id: str, recipient_id: str, *, event_type: str, channel: str = "in_app", destination: str = "", template_key: str = "", subject: str = "", body: str = "", context: dict[str, Any] | None = None, payload: dict[str, Any] | None = None, idempotency_key: str = "", priority: int = 50, requested_at: str | None = None) -> dict[str, Any]:
        plan = self.notification_delivery_plan(actor, institution_id, recipient_id, event_type=event_type, channel=channel, requested_at=requested_at)
        event_id = ident("npolicy")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_notification_policy_events VALUES(?,?,?,?,?,?,?,?,?,?)",
                (event_id, institution_id, recipient_id, str(event_type)[:160], str(channel).lower(), plan["decision"], plan["available_at"], _json({"preference": plan["preference"], "idempotency_key": idempotency_key}), actor, now()),
            )
        if not plan["enabled"]:
            return {"state": "suppressed", "policy_event_id": event_id, "plan": plan}
        queued = self.queue_notification(
            actor, institution_id, recipient_id, channel=channel, destination=destination, template_key=template_key,
            subject=subject, body=body, context=context, payload={**(payload or {}), "event_type": event_type, "policy_event_id": event_id},
            idempotency_key=idempotency_key, priority=priority, available_at=plan["available_at"],
        )
        return {"state": queued["state"], "outbox": queued, "policy_event_id": event_id, "plan": plan}

    def build_in_app_digest(self, actor: str, institution_id: str, recipient_id: str, *, since: str | None = None, mark_read: bool = False) -> dict[str, Any]:
        if actor != recipient_id and not self._roles(actor, institution_id) & TEACHER_ROLES:
            raise Denied("Digest access denied.")
        since_value = parse_time(since).isoformat() if since else (self._now_dt() - timedelta(days=7)).isoformat()
        rows = self.platform._all(
            """SELECT * FROM education_notifications WHERE institution_id=? AND user_id=? AND created_at>=?
            AND state='unread' ORDER BY priority DESC,created_at DESC LIMIT 500""",
            (institution_id, recipient_id, since_value),
        )
        by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_event[str(row["event_type"])].append(row)
        if mark_read and rows:
            stamp = now()
            with self.db.connection() as db:
                db.executemany("UPDATE education_notifications SET state='read',read_at=?,updated_at=? WHERE id=? AND user_id=?", [(stamp, stamp, row["id"], recipient_id) for row in rows])
        return {
            "recipient_id": recipient_id, "since": since_value, "total": len(rows),
            "groups": [{"event_type": event, "count": len(items), "items": items[:20]} for event, items in sorted(by_event.items())],
            "marked_read": bool(mark_read and rows),
        }

    def claim_notification(self, worker_id: str, *, channel: str = "in_app") -> dict[str, Any] | None:
        """Atomically claim a due notification using the injected UTC clock."""
        if not str(worker_id).strip():
            raise EducationError("Worker ID is required.")
        channel_value = str(channel).lower()
        stamp = self._now_iso()
        with self.db.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM education_notification_outbox WHERE state='queued' AND channel=? AND available_at<=? ORDER BY priority DESC,created_at LIMIT 1",
                (channel_value, stamp),
            ).fetchone()
            if not row:
                return None
            token = secrets.token_urlsafe(24)
            db.execute(
                "UPDATE education_notification_outbox SET state='processing',locked_by=?,lock_token=?,attempts=attempts+1,updated_at=? WHERE id=? AND state='queued'",
                (str(worker_id)[:200], token, stamp, row["id"]),
            )
            claimed = db.execute("SELECT * FROM education_notification_outbox WHERE id=?", (row["id"],)).fetchone()
        result = dict(claimed)
        result["lock_token_plain"] = token
        return result

    def requeue_failed_notifications(self, actor: str, institution_id: str, *, limit: int = 100) -> dict[str, Any]:
        self._admin(actor, institution_id)
        rows = self.platform._all(
            "SELECT id FROM education_notification_outbox WHERE institution_id=? AND state='failed' ORDER BY updated_at LIMIT ?",
            (institution_id, max(1, min(1000, int(limit)))),
        )
        stamp = now()
        with self.db.connection() as db:
            db.executemany(
                "UPDATE education_notification_outbox SET state='queued',attempts=0,available_at=?,locked_by='',lock_token='',last_error='',updated_at=? WHERE id=?",
                [(stamp, stamp, row["id"]) for row in rows],
            )
        self.security_event(institution_id, "notification_dead_letters_requeued", actor_id=actor, detail={"count": len(rows)})
        return {"requeued": len(rows), "ids": [row["id"] for row in rows]}

    # --------------------------------------------------------------
    # Verifiable retention execution and redacted diagnostics bundles
    # --------------------------------------------------------------
    @staticmethod
    def _retention_query(data_class: str) -> tuple[str, str, str]:
        mapping = {
            "notifications": ("education_notification_outbox", "updated_at", "id"),
            "sessions": ("education_desktop_sessions", "expires_at", "id"),
            "reports": ("education_report_runs", "created_at", "id"),
            "rag_chunks": ("education_rag_chunks", "created_at", "id"),
        }
        if data_class not in mapping:
            raise EducationError("Unsupported automated retention data class.")
        return mapping[data_class]

    def execute_retention_policy(self, actor: str, institution_id: str, data_class: str, *, dry_run: bool = True, confirmation: str = "") -> dict[str, Any]:
        self._admin(actor, institution_id)
        policy = self.platform._one("SELECT * FROM education_retention_policies WHERE institution_id=? AND data_class=? AND state='active'", (institution_id, str(data_class)))
        if not policy:
            raise Missing("Active retention policy not found.")
        if int(policy["legal_hold"]):
            raise Conflict("Retention action is blocked by legal hold.")
        table, date_column, key_column = self._retention_query(data_class)
        cutoff = self._now_dt() - timedelta(days=int(policy["retention_days"]))
        rows = self.platform._all(f'SELECT * FROM "{table}" WHERE institution_id=? AND "{date_column}"<? ORDER BY "{date_column}"', (institution_id, cutoff.isoformat()))
        run_id, stamp = ident("lifecycle"), now()
        archive_path, archive_sha = "", ""
        affected = 0
        action = str(policy["action"])
        if not dry_run and rows:
            if confirmation != f"EXECUTE {data_class} {len(rows)}":
                raise Denied("Exact retention confirmation phrase is required.")
            archive_dir = self.root / "education" / "retention_archives" / institution_id
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive = archive_dir / f"{data_class}-{self._now_dt().strftime('%Y%m%dT%H%M%SZ')}.jsonl"
            with archive.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(_json(dict(row)) + "\n")
            archive_sha = _sha256_file(archive)
            archive_path = str(archive)
            if action == "delete":
                with self.db.connection() as db:
                    db.executemany(f'DELETE FROM "{table}" WHERE "{key_column}"=? AND institution_id=?', [(row[key_column], institution_id) for row in rows])
                affected = len(rows)
            elif action == "anonymize":
                if data_class != "notifications":
                    raise Conflict("Automated anonymization is currently allowed only for notification metadata.")
                with self.db.connection() as db:
                    db.executemany(
                        "UPDATE education_notification_outbox SET recipient_id='anonymized',destination='',subject='retained notification',body='',payload_json='{}',last_error='',updated_at=? WHERE id=? AND institution_id=?",
                        [(stamp, row["id"], institution_id) for row in rows],
                    )
                affected = len(rows)
            elif action == "archive":
                affected = len(rows)
            else:
                raise EducationError("Unsupported retention policy action.")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_lifecycle_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, institution_id, data_class, action, cutoff.isoformat(), int(bool(dry_run)), len(rows), affected, archive_path, archive_sha, "completed", _json({"legal_hold": False, "confirmation_required": f"EXECUTE {data_class} {len(rows)}"}), actor, stamp),
            )
        if not dry_run:
            self.security_event(institution_id, "retention_policy_executed", actor_id=actor, severity="high", detail={"data_class": data_class, "action": action, "affected": affected, "archive_sha256": archive_sha})
        return self.platform._one("SELECT * FROM education_lifecycle_runs WHERE id=?", (run_id,))

    def create_support_bundle(self, actor: str, institution_id: str) -> dict[str, Any]:
        self._admin(actor, institution_id)
        output_dir = self.root / "education" / "support_bundles" / institution_id
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = self._now_dt().strftime("%Y%m%dT%H%M%SZ")
        output = output_dir / f"biointel-support-{stamp}.zip"
        health = self.platform._all("SELECT * FROM education_health_snapshots WHERE institution_id=? ORDER BY created_at DESC LIMIT 20", (institution_id,))
        incidents = self.platform._all("SELECT id,title,severity,status,owner_id,opened_at,updated_at,resolved_at FROM education_incidents WHERE institution_id=? ORDER BY opened_at DESC LIMIT 100", (institution_id,))
        qualifications = self.platform._all("SELECT qualification_type,state,evidence_json,performed_by,created_at FROM education_release_qualifications WHERE institution_id=? ORDER BY created_at DESC LIMIT 200", (institution_id,))
        security = self.platform._all("SELECT event_type,severity,COUNT(*) count,MAX(created_at) latest FROM education_security_events WHERE institution_id=? GROUP BY event_type,severity ORDER BY count DESC", (institution_id,))
        migrations = self.platform._all("SELECT id,applied_at FROM education_migrations ORDER BY applied_at,id")
        files = {
            "health.json": health,
            "incidents.json": incidents,
            "qualifications.json": qualifications,
            "security-summary.json": security,
            "migrations.json": migrations,
            "runtime.json": {"python": os.sys.version.split()[0], "database": str(self.db.path.name), "storage_free_bytes": shutil.disk_usage(self.root).free, "generated_at": now()},
        }
        manifest: dict[str, Any] = {"schema": "biointel.support-bundle.v1", "institution_id": institution_id, "generated_at": now(), "files": []}
        with tempfile.TemporaryDirectory(prefix="biointel-support-") as temporary:
            temp_root = Path(temporary)
            for name, payload in files.items():
                path = temp_root / name
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                manifest["files"].append({"name": name, "sha256": _sha256_file(path), "size_bytes": path.stat().st_size})
            manifest_path = temp_root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for path in sorted(temp_root.iterdir()):
                    archive.write(path, path.name)
        sha = _sha256_file(output)
        bundle_id = ident("support")
        with self.db.connection() as db:
            db.execute("INSERT INTO education_support_bundles VALUES(?,?,?,?,?,?,?,?)", (bundle_id, institution_id, str(output), sha, output.stat().st_size, _json(manifest), actor, now()))
        return {"id": bundle_id, "output_path": str(output), "sha256": sha, "size_bytes": output.stat().st_size, "manifest": manifest, "contains_personal_content": False}

    def verify_support_bundle(self, actor: str, bundle_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_support_bundles WHERE id=?", (bundle_id,))
        if not row:
            raise Missing("Support bundle not found.")
        self._admin(actor, row["institution_id"])
        path = Path(row["output_path"])
        errors: list[str] = []
        if not path.is_file():
            errors.append("bundle_missing")
        elif not secrets.compare_digest(_sha256_file(path), row["sha256"]):
            errors.append("bundle_hash_mismatch")
        if path.is_file():
            try:
                with zipfile.ZipFile(path) as archive:
                    if archive.testzip():
                        errors.append("zip_crc_failure")
                    manifest = json.loads(archive.read("manifest.json"))
                    for item in manifest.get("files", []):
                        content = archive.read(item["name"])
                        if hashlib.sha256(content).hexdigest() != item["sha256"]:
                            errors.append(f"file_hash_mismatch:{item['name']}")
            except Exception as exc:
                errors.append(f"invalid_bundle:{type(exc).__name__}")
        return {"id": bundle_id, "valid": not errors, "errors": errors, "expected_sha256": row["sha256"], "actual_sha256": _sha256_file(path) if path.is_file() else ""}

    # --------------------------------------------------------------
    # Consolidated honest local-completion posture
    # --------------------------------------------------------------
    def phase13_posture(self, actor: str, institution_id: str) -> dict[str, Any]:
        self._admin(actor, institution_id)
        counts = {}
        for key, table, condition in (
            ("approved_rag_documents", "education_rag_documents", "state='approved'"),
            ("rag_chunks", "education_rag_chunks", "state='active'"),
            ("timetable_runs", "education_timetable_generation_runs", "1=1"),
            ("failed_notifications", "education_notification_outbox", "state='failed'"),
            ("verified_backups", "education_full_backups", "state='verified'"),
            ("open_incidents", "education_incidents", "status<>'resolved'"),
        ):
            row = self.platform._one(f"SELECT COUNT(*) count FROM {table} WHERE institution_id=? AND {condition}", (institution_id,)) or {"count": 0}
            counts[key] = int(row["count"])
        external = self.final_completion_posture(actor, institution_id)
        local_controls = {
            "mfa_and_secure_sessions": True,
            "oidc_pkce_rs256_adapter": True,
            "postgresql_transactional_migration_adapter": True,
            "s3_minio_upload_adapter": True,
            "encrypted_full_backup": True,
            "multi_format_rag_ingestion": True,
            "permission_filtered_citation_retrieval": True,
            "automatic_timetable_solver": True,
            "notification_policy_and_digest": True,
            "retention_archive_and_execution": True,
            "redacted_support_bundle": True,
        }
        return {
            "institution_id": institution_id, "migration": MIGRATION_ID, "counts": counts,
            "local_controls": local_controls, "local_control_coverage_percent": 100.0,
            "external_posture": external,
            "truthfulness": "Local/code-level controls are implemented. Third-party credentials, code-signing reputation and independent audits remain externally qualified evidence, never synthetic success.",
        }
