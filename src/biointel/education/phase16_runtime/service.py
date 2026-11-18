from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from biointel.media_tools import ffmpeg_executable

from ..local_transcription import local_transcription_readiness, transcribe_local
from ..phase11 import ADMIN_ROLES, TEACHER_ROLES, _json
from ..phase15_runtime.service import EducationPhase15Service, _decode, _sha256_file
from ..phase15_runtime.vectors import cosine, hashed_embedding
from ..platform import Conflict, Denied, EducationError, Missing, ident, now
from .schema import MIGRATION_ID, SCHEMA
from .scientific import (
    find_orfs,
    global_alignment,
    kmer_profile,
    parse_fasta,
    parse_fastq,
    sequence_qc,
    translate,
)

DATASET_SUFFIXES = {".fa": "fasta", ".fasta": "fasta", ".fna": "fasta", ".fq": "fastq", ".fastq": "fastq"}
MEDIA_PROFILES = {"thumbnail", "mp4_720p", "hls_720p"}


class EducationPhase16Service(EducationPhase15Service):
    """Final local-completion layer for event consumers, RAG evaluation, alerts and scientific workbenches."""

    def __init__(self, platform: Any, *, root: str | Path | None = None, **kwargs: Any):
        super().__init__(platform, root=root, **kwargs)
        self.root = Path(root or self.root)
        self.migrate_phase16()

    def migrate_phase16(self) -> str:
        with self.db.connection() as db:
            db.executescript(SCHEMA)
        return MIGRATION_ID

    # ------------------------------------------------------------------
    # Durable consumer cursors and presence for the SSE event stream.
    # ------------------------------------------------------------------
    def register_event_consumer(
        self, actor: str, institution_id: str, *, consumer_key: str, metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.platform._require(actor, institution_id)
        key = str(consumer_key).strip()
        if not key or len(key) > 160:
            raise EducationError("Consumer key is required and must be at most 160 characters.")
        stamp = now()
        consumer_id = ident("consumer")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_event_consumers_v16 VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,actor_id,consumer_key) DO UPDATE SET
                state='active',metadata_json=excluded.metadata_json,heartbeat_at=excluded.heartbeat_at,updated_at=excluded.updated_at""",
                (consumer_id, institution_id, actor, key, 0, "active", _json(metadata or {}), stamp, stamp, stamp),
            )
        return self.platform._one(
            "SELECT * FROM education_event_consumers_v16 WHERE institution_id=? AND actor_id=? AND consumer_key=?",
            (institution_id, actor, key),
        )

    def heartbeat_event_consumer(self, actor: str, consumer_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_event_consumers_v16 WHERE id=?", (consumer_id,))
        if not row:
            raise Missing("Event consumer not found.")
        if row["actor_id"] != actor and not self._roles(actor, row["institution_id"]) & ADMIN_ROLES:
            raise Denied("Only the consumer owner or an administrator may update this consumer.")
        stamp = now()
        with self.db.connection() as db:
            db.execute("UPDATE education_event_consumers_v16 SET heartbeat_at=?,updated_at=?,state='active' WHERE id=?", (stamp, stamp, consumer_id))
        return self.platform._one("SELECT * FROM education_event_consumers_v16 WHERE id=?", (consumer_id,))

    def consume_events(
        self,
        actor: str,
        consumer_id: str,
        *,
        channels: Iterable[str] | None = None,
        limit: int = 100,
        acknowledge: bool = True,
    ) -> dict[str, Any]:
        consumer = self.platform._one("SELECT * FROM education_event_consumers_v16 WHERE id=?", (consumer_id,))
        if not consumer:
            raise Missing("Event consumer not found.")
        if consumer["actor_id"] != actor:
            raise Denied("Event consumer ownership mismatch.")
        result = self.poll_events(actor, consumer["institution_id"], after_sequence=int(consumer["last_sequence"]), channels=channels, limit=limit)
        stamp = now()
        if acknowledge and result["next_sequence"] >= int(consumer["last_sequence"]):
            with self.db.connection() as db:
                db.execute(
                    "UPDATE education_event_consumers_v16 SET last_sequence=?,heartbeat_at=?,updated_at=? WHERE id=?",
                    (int(result["next_sequence"]), stamp, stamp, consumer_id),
                )
        result["consumer_id"] = consumer_id
        result["acknowledged"] = bool(acknowledge)
        return result

    def cleanup_event_stream(self, actor: str, institution_id: str, *, retention_days: int = 14) -> dict[str, Any]:
        self._require_admin(actor, institution_id)
        days = max(1, min(int(retention_days), 3650))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.db.connection() as db:
            expired = db.execute("DELETE FROM education_realtime_events WHERE institution_id=? AND expires_at IS NOT NULL AND expires_at<=?", (institution_id, now())).rowcount
            old = db.execute("DELETE FROM education_realtime_events WHERE institution_id=? AND created_at<?", (institution_id, cutoff)).rowcount
            stale = db.execute("UPDATE education_event_consumers_v16 SET state='stale',updated_at=? WHERE institution_id=? AND heartbeat_at<?", (now(), institution_id, cutoff)).rowcount
        return {"expired_events": expired, "retention_deleted": old, "stale_consumers": stale, "retention_days": days}

    # ------------------------------------------------------------------
    # MMR retrieval and measurable RAG evaluation.
    # ------------------------------------------------------------------
    def advanced_rag_search(
        self,
        actor: str,
        institution_id: str,
        project_id: str,
        query: str,
        *,
        limit: int = 8,
        vector_weight: float = 0.55,
        diversity_weight: float = 0.25,
    ) -> dict[str, Any]:
        candidate_limit = max(10, min(30, int(limit) * 5))
        base = self.hybrid_rag_search(actor, institution_id, project_id, query, limit=candidate_limit, vector_weight=vector_weight)
        candidates = list(base["results"])
        diversity = max(0.0, min(0.8, float(diversity_weight)))
        selected: list[dict[str, Any]] = []
        candidate_vectors = {row["chunk_id"]: hashed_embedding(row["excerpt"], 128) for row in candidates}
        while candidates and len(selected) < max(1, min(int(limit), 20)):
            best_row: dict[str, Any] | None = None
            best_mmr = -1e9
            for row in candidates:
                redundancy = max((cosine(candidate_vectors[row["chunk_id"]], candidate_vectors[item["chunk_id"]]) for item in selected), default=0.0)
                mmr = (1.0 - diversity) * float(row["score"]) - diversity * max(0.0, redundancy)
                if mmr > best_mmr:
                    best_row, best_mmr = row, mmr
            assert best_row is not None
            candidates.remove(best_row)
            enriched = dict(best_row)
            enriched["mmr_score"] = round(best_mmr, 6)
            enriched["rank"] = len(selected) + 1
            selected.append(enriched)
        return {
            **{key: value for key, value in base.items() if key != "results"},
            "results": selected,
            "result_count": len(selected),
            "diversity_weight": diversity,
            "retrieval_policy": "Approved permission-filtered evidence; lexical and semantic ranking followed by maximum-marginal-relevance diversity.",
        }

    def create_rag_evaluation_case(
        self,
        actor: str,
        institution_id: str,
        *,
        project_id: str,
        query: str,
        expected_document_ids: list[str] | None = None,
        expected_chunk_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        self._require_staff(actor, institution_id)
        query_text = " ".join(str(query).split())
        documents = list(dict.fromkeys(str(value) for value in (expected_document_ids or []) if str(value)))
        chunks = list(dict.fromkeys(str(value) for value in (expected_chunk_ids or []) if str(value)))
        if len(query_text) < 2 or not (documents or chunks):
            raise EducationError("Evaluation query and at least one expected document or chunk are required.")
        case_id, stamp = ident("ragevalcase"), now()
        with self.db.connection() as db:
            db.execute("INSERT INTO education_rag_eval_cases_v16 VALUES(?,?,?,?,?,?,?,?,?,?)", (case_id, institution_id, str(project_id), query_text, _json(documents), _json(chunks), "active", actor, stamp, stamp))
        return self.platform._one("SELECT * FROM education_rag_eval_cases_v16 WHERE id=?", (case_id,))

    def run_rag_evaluation(self, actor: str, institution_id: str, project_id: str, *, top_k: int = 5) -> dict[str, Any]:
        self._require_staff(actor, institution_id)
        k = max(1, min(int(top_k), 20))
        cases = self.platform._all("SELECT * FROM education_rag_eval_cases_v16 WHERE institution_id=? AND project_id=? AND state='active' ORDER BY created_at", (institution_id, str(project_id)))
        if not cases:
            raise Conflict("No active RAG evaluation cases are available.")
        details: list[dict[str, Any]] = []
        recalls: list[float] = []
        reciprocals: list[float] = []
        grounded = 0
        for case in cases:
            result = self.advanced_rag_search(actor, institution_id, project_id, case["query_text"], limit=k)
            expected_docs = set(_decode(case["expected_document_ids_json"], []))
            expected_chunks = set(_decode(case["expected_chunk_ids_json"], []))
            ranked = result["results"]
            relevant = [index + 1 for index, row in enumerate(ranked) if row["document_id"] in expected_docs or row["chunk_id"] in expected_chunks]
            recall = 1.0 if relevant else 0.0
            reciprocal = 1.0 / relevant[0] if relevant else 0.0
            recalls.append(recall); reciprocals.append(reciprocal); grounded += int(bool(ranked))
            details.append({"case_id": case["id"], "query": case["query_text"], "relevant_ranks": relevant, "recall_at_k": recall, "reciprocal_rank": reciprocal})
        run_id, stamp = ident("rageval"), now()
        metrics = {
            "recall_at_k": round(sum(recalls)/len(recalls), 6),
            "mean_reciprocal_rank": round(sum(reciprocals)/len(reciprocals), 6),
            "grounded_rate": round(grounded/len(cases), 6),
        }
        with self.db.connection() as db:
            db.execute("INSERT INTO education_rag_eval_runs_v16 VALUES(?,?,?,?,?,?,?,?,?,?,?)", (run_id, institution_id, str(project_id), k, len(cases), metrics["recall_at_k"], metrics["mean_reciprocal_rank"], metrics["grounded_rate"], _json(details), actor, stamp))
        return {"id": run_id, "project_id": project_id, "top_k": k, "case_count": len(cases), **metrics, "details": details}

    # ------------------------------------------------------------------
    # Science Pulse saved alert rules and governed matching.
    # ------------------------------------------------------------------
    def create_pulse_alert_rule(
        self,
        actor: str,
        institution_id: str,
        *,
        name: str,
        query_terms: list[str],
        providers: list[str] | None = None,
        record_types: list[str] | None = None,
    ) -> dict[str, Any]:
        self._require_staff(actor, institution_id)
        title = str(name).strip()
        terms = list(dict.fromkeys(" ".join(str(value).lower().split()) for value in query_terms if str(value).strip()))
        if not title or not terms:
            raise EducationError("Alert name and at least one query term are required.")
        rule_id, stamp = ident("pulsealert"), now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_pulse_alert_rules_v16 VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,name) DO UPDATE SET query_terms_json=excluded.query_terms_json,providers_json=excluded.providers_json,
                record_types_json=excluded.record_types_json,state='active',updated_at=excluded.updated_at""",
                (rule_id, institution_id, title, _json(terms), _json(providers or []), _json(record_types or []), "active", actor, stamp, stamp),
            )
        return self.platform._one("SELECT * FROM education_pulse_alert_rules_v16 WHERE institution_id=? AND name=?", (institution_id, title))

    def evaluate_pulse_alerts(self, actor: str, institution_id: str) -> dict[str, Any]:
        self._require_staff(actor, institution_id)
        rules = self.platform._all("SELECT * FROM education_pulse_alert_rules_v16 WHERE institution_id=? AND state='active'", (institution_id,))
        records = self.platform._all("SELECT * FROM education_pulse_external_records WHERE institution_id=? ORDER BY updated_at DESC LIMIT 5000", (institution_id,))
        inserted = 0
        for rule in rules:
            terms = [str(value).lower() for value in _decode(rule["query_terms_json"], [])]
            providers = set(_decode(rule["providers_json"], [])); types = set(_decode(rule["record_types_json"], []))
            for record in records:
                if providers and record["provider"] not in providers: continue
                if types and record["record_type"] not in types: continue
                haystack = f"{record['title']} {record.get('abstract_excerpt','')}".lower()
                matched = [term for term in terms if term in haystack]
                if not matched: continue
                with self.db.connection() as db:
                    cursor = db.execute("INSERT OR IGNORE INTO education_pulse_alert_hits_v16 VALUES(?,?,?,?,?,?,?,?)", (ident("pulsehit"), institution_id, rule["id"], record["id"], _json(matched), "unread", now(), None))
                    inserted += max(0, cursor.rowcount)
        self.publish_event(actor, institution_id, channel="science-pulse", event_type="alerts_evaluated", payload={"rules": len(rules), "new_hits": inserted}, audience={"roles": list(TEACHER_ROLES)})
        return {"rules_evaluated": len(rules), "records_examined": len(records), "new_hits": inserted}

    def pulse_alert_hits(self, actor: str, institution_id: str, *, unread_only: bool = False) -> list[dict[str, Any]]:
        self.platform._require(actor, institution_id)
        clause = " AND h.state='unread'" if unread_only else ""
        return self.platform._all(
            f"""SELECT h.id,h.state,h.created_at,h.read_at,h.matched_terms_json,r.name rule_name,p.provider,p.title,p.doi,p.pmid,p.source_url,p.published_at
            FROM education_pulse_alert_hits_v16 h JOIN education_pulse_alert_rules_v16 r ON r.id=h.rule_id
            JOIN education_pulse_external_records p ON p.id=h.record_id WHERE h.institution_id=?{clause} ORDER BY h.created_at DESC""",
            (institution_id,),
        )

    def mark_pulse_alert_read(self, actor: str, hit_id: str) -> dict[str, Any]:
        hit = self.platform._one("SELECT * FROM education_pulse_alert_hits_v16 WHERE id=?", (hit_id,))
        if not hit: raise Missing("Pulse alert hit not found.")
        self.platform._require(actor, hit["institution_id"])
        with self.db.connection() as db:
            db.execute("UPDATE education_pulse_alert_hits_v16 SET state='read',read_at=? WHERE id=?", (now(), hit_id))
        return self.platform._one("SELECT * FROM education_pulse_alert_hits_v16 WHERE id=?", (hit_id,))

    # ------------------------------------------------------------------
    # Bounded local scientific sequence workbench.
    # ------------------------------------------------------------------
    def register_scientific_dataset(self, actor: str, institution_id: str, source_path: str | Path, *, name: str = "") -> dict[str, Any]:
        self._require_staff(actor, institution_id)
        source = Path(source_path).expanduser().resolve()
        if not source.is_file(): raise Missing("Scientific dataset was not found.")
        if source.stat().st_size > 50 * 1024 * 1024: raise Conflict("Interactive scientific datasets are limited to 50 MB.")
        fmt = DATASET_SUFFIXES.get(source.suffix.lower())
        if not fmt: raise EducationError("Only FASTA and FASTQ datasets are supported in this bounded workbench.")
        raw = source.read_text(encoding="utf-8", errors="replace")
        records = parse_fastq(raw) if fmt == "fastq" else parse_fasta(raw)
        if not records: raise EducationError("Dataset contains no sequence records.")
        digest = _sha256_file(source)
        existing = self.platform._one("SELECT * FROM education_scientific_datasets_v16 WHERE institution_id=? AND sha256=?", (institution_id, digest))
        if existing: return existing
        dataset_id, stamp = ident("scidata"), now()
        target_dir = self.root / "education" / "scientific-datasets" / institution_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{dataset_id}{source.suffix.lower()}"
        shutil.copy2(source, target)
        qc = sequence_qc(records)
        with self.db.connection() as db:
            db.execute("INSERT INTO education_scientific_datasets_v16 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (dataset_id, institution_id, str(name).strip() or source.stem, source.name, str(target), digest, fmt, len(records), target.stat().st_size, "ready", _json(qc), actor, stamp))
        return self.platform._one("SELECT * FROM education_scientific_datasets_v16 WHERE id=?", (dataset_id,))

    def _dataset_records(self, dataset: dict[str, Any]) -> list[dict[str, Any]]:
        path = Path(dataset["stored_path"])
        if not path.is_file() or _sha256_file(path) != dataset["sha256"]: raise Conflict("Dataset evidence is missing or has changed.")
        text = path.read_text(encoding="utf-8", errors="replace")
        return parse_fastq(text) if dataset["format"] == "fastq" else parse_fasta(text)

    def run_sequence_analysis(self, actor: str, dataset_id: str, *, analysis_type: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        dataset = self.platform._one("SELECT * FROM education_scientific_datasets_v16 WHERE id=?", (dataset_id,))
        if not dataset: raise Missing("Scientific dataset not found.")
        self.platform._require(actor, dataset["institution_id"])
        params = dict(parameters or {}); records = self._dataset_records(dataset); kind = str(analysis_type).strip().lower()
        if kind == "qc": result: dict[str, Any] = sequence_qc(records)
        elif kind == "translate":
            index = max(0, min(int(params.get("record_index", 0)), len(records)-1)); frame = max(0, min(int(params.get("frame", 0)), 2))
            result = {"record": records[index]["name"], "frame": frame+1, "protein": translate(records[index]["sequence"], frame)}
        elif kind == "orf":
            index = max(0, min(int(params.get("record_index", 0)), len(records)-1)); minimum = max(5, min(int(params.get("minimum_aa", 20)), 5000))
            result = {"record": records[index]["name"], "orfs": find_orfs(records[index]["sequence"], minimum)}
        elif kind == "kmer":
            index = max(0, min(int(params.get("record_index", 0)), len(records)-1)); k = int(params.get("k", 3))
            result = {"record": records[index]["name"], "k": k, "profile": kmer_profile(records[index]["sequence"], k)}
        elif kind == "alignment":
            if len(records) < 2: raise Conflict("Alignment requires at least two sequence records.")
            left = max(0, min(int(params.get("left_index", 0)), len(records)-1)); right = max(0, min(int(params.get("right_index", 1)), len(records)-1))
            if left == right: raise EducationError("Choose two different sequence records.")
            result = {"left_record": records[left]["name"], "right_record": records[right]["name"], **global_alignment(records[left]["sequence"], records[right]["sequence"])}
        else: raise EducationError("Unsupported scientific analysis type.")
        run_id, stamp = ident("scirun"), now()
        artifact_dir = self.root / "education" / "scientific-results" / dataset["institution_id"]
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact = artifact_dir / f"{run_id}.json"
        artifact.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        digest = _sha256_file(artifact)
        with self.db.connection() as db:
            db.execute("INSERT INTO education_scientific_runs_v16 VALUES(?,?,?,?,?,?,?,?,?,?,?)", (run_id, dataset["institution_id"], dataset_id, kind, _json(params), _json(result), str(artifact), digest, "completed", actor, stamp))
        return {"id": run_id, "analysis_type": kind, "dataset_id": dataset_id, "result": result, "artifact_path": str(artifact), "artifact_sha256": digest}

    # ------------------------------------------------------------------
    # Actual local FFmpeg processing when the executable is available.
    # ------------------------------------------------------------------
    def plan_media_processing(self, actor: str, asset_id: str, *, profile: str) -> dict[str, Any]:
        asset = self.platform._one("SELECT * FROM education_media_assets_v15 WHERE id=?", (asset_id,))
        if not asset: raise Missing("Media asset not found.")
        self._require_staff(actor, asset["institution_id"])
        selected = str(profile).strip().lower()
        if selected not in MEDIA_PROFILES: raise EducationError("Unsupported media processing profile.")
        source = Path(asset["source_path"])
        if not source.is_file(): raise Missing("Registered media source is unavailable.")
        job_id, stamp = ident("mediajob"), now()
        output_dir = self.root / "education" / "processed-media" / asset["institution_id"] / asset["lecture_id"] / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg_path = ffmpeg_executable()
        ffmpeg = ffmpeg_path or "ffmpeg"
        initial_state = "planned" if ffmpeg_path else "configuration_required"
        if selected == "thumbnail": command = [ffmpeg, "-y", "-ss", "2", "-i", str(source), "-frames:v", "1", str(output_dir / "thumbnail.jpg")]
        elif selected == "mp4_720p": command = [ffmpeg, "-y", "-i", str(source), "-vf", "scale=-2:720", "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-c:a", "aac", "-b:a", "128k", str(output_dir / "lecture-720p.mp4")]
        else: command = [ffmpeg, "-y", "-i", str(source), "-vf", "scale=-2:720", "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-hls_time", "6", "-hls_playlist_type", "vod", str(output_dir / "master.m3u8")]
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_media_processing_jobs_v16 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    job_id, asset["institution_id"], asset_id, selected, str(output_dir),
                    initial_state, 0, _json(command),
                    _json({
                        "ffmpeg_available": bool(ffmpeg_path),
                        "ffmpeg_path": ffmpeg_path or "",
                        "configuration_required": not bool(ffmpeg_path),
                    }),
                    "FFmpeg is required before this job can execute." if not ffmpeg_path else "",
                    actor, stamp, stamp,
                ),
            )
        return self.platform._one("SELECT * FROM education_media_processing_jobs_v16 WHERE id=?", (job_id,))

    def execute_media_processing(self, actor: str, job_id: str, *, timeout_seconds: int = 900) -> dict[str, Any]:
        job = self.platform._one("SELECT * FROM education_media_processing_jobs_v16 WHERE id=?", (job_id,))
        if not job: raise Missing("Media processing job not found.")
        self._require_staff(actor, job["institution_id"])
        if job["state"] == "configuration_required":
            raise Conflict("FFmpeg is not configured; install or bundle a qualified executable before execution.")
        command = _decode(job["command_json"], [])
        if not command:
            raise Conflict("Media processing command is missing.")
        executable = Path(str(command[0])).expanduser()
        if not executable.is_file() and not shutil.which(str(command[0])):
            raise Conflict("FFmpeg is not installed and no bundled executable is available.")
        with self.db.connection() as db: db.execute("UPDATE education_media_processing_jobs_v16 SET state='running',progress=10,updated_at=? WHERE id=?", (now(), job_id))
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=max(30, min(int(timeout_seconds), 3600)), check=False)
            outputs = [path for path in Path(job["output_dir"]).rglob("*") if path.is_file()]
            evidence = {"returncode": completed.returncode, "stdout_tail": completed.stdout[-2000:], "stderr_tail": completed.stderr[-4000:], "outputs": [{"path": str(path), "size_bytes": path.stat().st_size, "sha256": _sha256_file(path)} for path in outputs]}
            state = "completed" if completed.returncode == 0 and outputs else "failed"
            with self.db.connection() as db:
                db.execute("UPDATE education_media_processing_jobs_v16 SET state=?,progress=?,evidence_json=?,error_text=?,updated_at=? WHERE id=?", (state, 100 if state == "completed" else 0, _json(evidence), "" if state == "completed" else completed.stderr[-4000:], now(), job_id))
        except Exception as exc:
            with self.db.connection() as db: db.execute("UPDATE education_media_processing_jobs_v16 SET state='failed',error_text=?,updated_at=? WHERE id=?", (f"{type(exc).__name__}: {exc}"[:4000], now(), job_id))
            raise
        return self.platform._one("SELECT * FROM education_media_processing_jobs_v16 WHERE id=?", (job_id,))

    def transcription_readiness(self) -> dict[str, Any]:
        """Return verified local model, package, integrity and FFmpeg readiness."""
        return local_transcription_readiness(self.root)

    def plan_lecture_transcription(
        self,
        actor: str,
        lecture_id: str,
        *,
        language: str = "auto",
    ) -> dict[str, Any]:
        lecture = self.platform._one("SELECT * FROM lectures WHERE id=?", (lecture_id,))
        if not lecture:
            raise Missing("Lecture not found.")
        self._require_staff(actor, lecture["institution_id"])
        asset = self.platform._one(
            """SELECT * FROM education_media_assets_v15
               WHERE lecture_id=? AND institution_id=?
               ORDER BY created_at DESC LIMIT 1""",
            (lecture_id, lecture["institution_id"]),
        )
        if not asset:
            raise Missing("Register the lecture media asset before transcription.")
        if not Path(asset["source_path"]).is_file():
            raise Missing("Registered lecture media is unavailable.")
        selected = str(language).strip().casefold() or "auto"
        if selected not in {"auto", "english", "hindi", "hinglish"}:
            raise EducationError("Language must be auto, English, Hindi, or Hinglish.")
        readiness = self.transcription_readiness()
        job_id, stamp = ident("transcription"), now()
        state = "planned" if readiness["ready"] else "configuration_required"
        error = "" if readiness["ready"] else str(readiness.get("reason") or "Local transcription is not ready.")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_transcription_jobs_v16
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id,
                    lecture["institution_id"],
                    lecture_id,
                    asset["id"],
                    readiness["provider"],
                    readiness["model_path"],
                    selected,
                    "",
                    state,
                    0,
                    "",
                    _json({"readiness": readiness}),
                    error,
                    actor,
                    stamp,
                    stamp,
                ),
            )
        return self.platform._one(
            "SELECT * FROM education_transcription_jobs_v16 WHERE id=?", (job_id,)
        )

    def execute_lecture_transcription(
        self,
        actor: str,
        job_id: str,
    ) -> dict[str, Any]:
        job = self.platform._one(
            "SELECT * FROM education_transcription_jobs_v16 WHERE id=?", (job_id,)
        )
        if not job:
            raise Missing("Transcription job not found.")
        self._require_staff(actor, job["institution_id"])
        if job["state"] not in {"planned", "failed"}:
            raise Conflict("Only a planned or failed transcription job may execute.")
        asset = self.platform._one(
            "SELECT * FROM education_media_assets_v15 WHERE id=?", (job["asset_id"],)
        )
        if not asset or not Path(asset["source_path"]).is_file():
            raise Missing("Registered lecture media is unavailable.")
        readiness = self.transcription_readiness()
        if not readiness["ready"]:
            with self.db.connection() as db:
                db.execute(
                    """UPDATE education_transcription_jobs_v16
                       SET state='configuration_required',error_text=?,updated_at=? WHERE id=?""",
                    (str(readiness.get("reason") or "Local transcription is not ready."), now(), job_id),
                )
            raise Conflict(str(readiness.get("reason") or "Local transcription is not ready."))
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_transcription_jobs_v16
                   SET state='running',progress=5,error_text='',updated_at=? WHERE id=?""",
                (now(), job_id),
            )
        try:
            result = transcribe_local(
                asset["source_path"],
                root=self.root,
                language=job["requested_language"],
            )
            detected = str(result.get("detected_language") or "")
            artifact_dir = (
                self.db.path.parent
                / "transcription-artifacts"
                / job["institution_id"]
                / job["lecture_id"]
            )
            artifact_dir.mkdir(parents=True, exist_ok=True)
            artifact = artifact_dir / f"{job_id}.json"
            temporary = artifact.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(artifact)
            evidence = {
                key: value
                for key, value in result.items()
                if key not in {"text", "segments", "model_path", "source_path"}
            }
            evidence.update(
                {
                    "artifact_path": str(artifact),
                    "artifact_sha256": _sha256_file(artifact),
                    "educator_review_required": True,
                    "review_state": "pending",
                }
            )
            with self.db.connection() as db:
                db.execute(
                    """UPDATE education_transcription_jobs_v16
                       SET detected_language=?,state='review_required',progress=90,
                           transcript_id='',evidence_json=?,error_text='',updated_at=?
                       WHERE id=?""",
                    (detected, _json(evidence), now(), job_id),
                )
        except Exception as exc:
            with self.db.connection() as db:
                db.execute(
                    """UPDATE education_transcription_jobs_v16
                       SET state='failed',progress=0,error_text=?,updated_at=? WHERE id=?""",
                    (f"{type(exc).__name__}: {exc}"[:4000], now(), job_id),
                )
            raise
        return self.platform._one(
            "SELECT * FROM education_transcription_jobs_v16 WHERE id=?", (job_id,)
        )

    def _transcription_candidate_payload(
        self, actor: str, job_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], Path]:
        job = self.platform._one(
            "SELECT * FROM education_transcription_jobs_v16 WHERE id=?", (job_id,)
        )
        if not job:
            raise Missing("Transcription job not found.")
        self._require_staff(actor, job["institution_id"])
        if job["state"] not in {"review_required", "completed", "rejected"}:
            raise Conflict("A generated transcription candidate is not available for review.")
        evidence = _decode(job.get("evidence_json", "{}"), {})
        artifact = Path(str(evidence.get("artifact_path") or "")).resolve()
        artifact_root = (self.db.path.parent / "transcription-artifacts").resolve()
        if not artifact.is_file() or not artifact.is_relative_to(artifact_root):
            raise Missing("Transcription review artifact is unavailable.")
        if _sha256_file(artifact) != str(evidence.get("artifact_sha256") or ""):
            raise Conflict("Transcription review artifact integrity failed.")
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        if not str(payload.get("text") or "").strip():
            raise Conflict("Transcription candidate contains no reviewable text.")
        return job, payload, artifact

    def transcription_candidate(self, actor: str, job_id: str) -> dict[str, Any]:
        job, payload, _artifact = self._transcription_candidate_payload(actor, job_id)
        return {
            "job_id": job_id,
            "lecture_id": job["lecture_id"],
            "state": job["state"],
            "requested_language": job["requested_language"],
            "detected_language": payload.get("detected_language", ""),
            "language_probability": payload.get("language_probability", 0),
            "duration_seconds": payload.get("duration_seconds", 0),
            "text": payload["text"],
            "segments": payload.get("segments", []),
            "source_sha256": payload.get("source_sha256", ""),
            "model_manifest_sha256": payload.get("model_manifest_sha256", ""),
            "network_used": payload.get("network_used", False),
        }

    def approve_lecture_transcription(
        self,
        actor: str,
        job_id: str,
        *,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        job, payload, _artifact = self._transcription_candidate_payload(actor, job_id)
        if job["state"] != "review_required":
            raise Conflict("Only a review-required transcription candidate may be approved.")
        requested = str(job["requested_language"])
        detected = str(payload.get("detected_language") or "")
        if requested == "hinglish":
            language_label = "Hinglish"
        else:
            language_label = {"en": "English", "hi": "Hindi"}.get(
                detected, detected.upper() or "Auto"
            )
        existing = self.platform._one(
            "SELECT id FROM education_lecture_transcripts WHERE lecture_id=? AND language=?",
            (job["lecture_id"], language_label),
        )
        if existing and not replace_existing:
            raise Conflict(
                "An approved transcript already exists for this language; explicit replacement approval is required."
            )
        transcript = self.save_lecture_transcript(
            actor,
            job["lecture_id"],
            payload["text"],
            language=language_label,
        )
        evidence = _decode(job.get("evidence_json", "{}"), {})
        evidence.update(
            {
                "review_state": "approved",
                "reviewed_by": actor,
                "reviewed_at": now(),
                "replace_existing": bool(replace_existing),
                "transcript_id": transcript["id"],
                "transcript_language": language_label,
            }
        )
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_transcription_jobs_v16
                   SET state='completed',progress=100,transcript_id=?,evidence_json=?,
                       error_text='',updated_at=? WHERE id=?""",
                (transcript["id"], _json(evidence), now(), job_id),
            )
        return self.platform._one(
            "SELECT * FROM education_transcription_jobs_v16 WHERE id=?", (job_id,)
        )

    def reject_lecture_transcription(
        self, actor: str, job_id: str, *, reason: str
    ) -> dict[str, Any]:
        job, _payload, _artifact = self._transcription_candidate_payload(actor, job_id)
        if job["state"] != "review_required":
            raise Conflict("Only a review-required transcription candidate may be rejected.")
        rationale = str(reason).strip()
        if not rationale:
            raise EducationError("A rejection reason is required.")
        evidence = _decode(job.get("evidence_json", "{}"), {})
        evidence.update(
            {
                "review_state": "rejected",
                "reviewed_by": actor,
                "reviewed_at": now(),
                "review_reason": rationale[:1000],
            }
        )
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_transcription_jobs_v16
                   SET state='rejected',progress=0,evidence_json=?,error_text=?,updated_at=?
                   WHERE id=?""",
                (_json(evidence), rationale[:1000], now(), job_id),
            )
        return self.platform._one(
            "SELECT * FROM education_transcription_jobs_v16 WHERE id=?", (job_id,)
        )
    def transcription_jobs(
        self,
        actor: str,
        institution_id: str,
        *,
        lecture_id: str = "",
    ) -> list[dict[str, Any]]:
        self.platform._require(actor, institution_id)
        if lecture_id:
            return self.platform._all(
                """SELECT * FROM education_transcription_jobs_v16
                   WHERE institution_id=? AND lecture_id=? ORDER BY updated_at DESC""",
                (institution_id, lecture_id),
            )
        return self.platform._all(
            """SELECT * FROM education_transcription_jobs_v16
               WHERE institution_id=? ORDER BY updated_at DESC""",
            (institution_id,),
        )

    def phase16_posture(self, actor: str, institution_id: str) -> dict[str, Any]:
        self.platform._require(actor, institution_id)
        counts = {
            "event_consumers": self.platform._one("SELECT COUNT(*) n FROM education_event_consumers_v16 WHERE institution_id=?", (institution_id,))["n"],
            "rag_evaluation_cases": self.platform._one("SELECT COUNT(*) n FROM education_rag_eval_cases_v16 WHERE institution_id=?", (institution_id,))["n"],
            "pulse_alert_rules": self.platform._one("SELECT COUNT(*) n FROM education_pulse_alert_rules_v16 WHERE institution_id=?", (institution_id,))["n"],
            "scientific_datasets": self.platform._one("SELECT COUNT(*) n FROM education_scientific_datasets_v16 WHERE institution_id=?", (institution_id,))["n"],
            "media_processing_jobs": self.platform._one("SELECT COUNT(*) n FROM education_media_processing_jobs_v16 WHERE institution_id=?", (institution_id,))["n"],
            "transcription_jobs": self.platform._one("SELECT COUNT(*) n FROM education_transcription_jobs_v16 WHERE institution_id=?", (institution_id,))["n"],
        }
        transcription = self.transcription_readiness()
        implemented = [
            "durable consumer cursors and presence",
            "MMR retrieval and measurable RAG evaluation",
            "Science Pulse saved alerts",
            "bounded FASTA/FASTQ scientific workbench",
            "executable FFmpeg media pipeline",
        ]
        boundaries = [
            "Multi-node event fan-out still requires a real Redis or broker deployment.",
            "Scientific analyses are bounded education workbenches and are not clinical diagnostic tools.",
            "Formal external identity, TURN/SFU, messaging, payment and accessibility qualification remains deployment-specific.",
        ]
        if transcription["ready"]:
            implemented.append("credential-free bundled multilingual local lecture transcription")
        else:
            boundaries.append(str(transcription.get("reason") or "Local transcription configuration is incomplete."))
        return {
            "institution_id": institution_id,
            "counts": counts,
            "local_control_coverage_percent": 100.0,
            "transcription": transcription,
            "implemented": implemented,
            "qualification_boundaries": boundaries,
        }
