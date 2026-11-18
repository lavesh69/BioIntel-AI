from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import DEFAULT_TENANT, DeliveryState, PulseRecord, SourceDefinition, stable_id, utc_now
from .providers import BUILTIN_SOURCES, ProviderRegistry, capability_matrix
from .security import validate_remote_url
from .store import SciencePulseStore
from .taxonomy import classify


LOCAL_CONFIRMED_CHANNELS = {"in_app", "shiro_briefing"}
OPTIONAL_CHANNELS = {"desktop", "email", "institution"}
INTEGRATION_DESTINATIONS = {
    "shiro",
    "classroom",
    "academy",
    "studio",
    "research",
    "education_home",
    "connect",
}


CONTEXTUAL_ACTIONS: dict[str, tuple[str, str]] = {
    "ask_shiro": ("shiro", "ask_for_evidence_summary"),
    "add_classroom": ("classroom", "add_reading_material"),
    "classroom_discussion": ("classroom", "create_discussion_draft"),
    "classroom_assignment": ("classroom", "create_assignment_draft"),
    "academy_lecture": ("academy", "create_lecture_draft"),
    "studio_asset": ("studio", "create_visual_asset_draft"),
    "connect_share": ("connect", "share_source_link"),
    "research_project": ("research", "add_to_research_project"),
    "evidence_collection": ("research", "add_to_evidence_collection"),
    "research_copilot": ("research", "add_to_research_copilot"),
    "classification_review": ("research", "report_incorrect_classification"),
}
class SciencePulseService:
    def __init__(
        self,
        root: str | Path | None = None,
        *,
        store: SciencePulseStore | None = None,
        providers: ProviderRegistry | None = None,
        dispatchers: dict[str, Callable[[dict[str, Any]], tuple[bool, str]]] | None = None,
    ) -> None:
        self.root = Path(root or Path.cwd()).resolve()
        self.store = store or SciencePulseStore(self.root)
        self.providers = providers or ProviderRegistry()
        self.dispatchers = dispatchers or {}
        for source in BUILTIN_SOURCES:
            self.store.upsert_source(source)

    def register_feed(
        self,
        name: str,
        url: str,
        *,
        schedule_seconds: int = 10_800,
        approved: bool = False,
        tenant_id: str = DEFAULT_TENANT,
    ) -> str:
        safe_url = validate_remote_url(url)
        source_key = stable_id("rss_custom", tenant_id, safe_url)
        self.store.upsert_source(
            SourceDefinition(
                key=source_key,
                name=name.strip()[:300] or "Managed science feed",
                kind="rss",
                base_url=safe_url,
                content_types=("news",),
                schedule_seconds=max(3600, min(int(schedule_seconds), 604_800)),
                approved=approved,
                enabled=approved,
                ownership="Administrator registered",
                license_note="Review source ownership and feed terms before approval.",
            ),
            tenant_id,
        )
        return source_key

    def test_connection(
        self, source_key: str, *, tenant_id: str = DEFAULT_TENANT
    ) -> dict[str, Any]:
        source = next(
            (row for row in self.store.list_sources(tenant_id) if row["source_key"] == source_key),
            None,
        )
        if not source:
            raise KeyError("Science Pulse source not found.")
        started = time.monotonic()
        try:
            result = self.providers.fetch(
                source,
                query="" if source["kind"] == "rss" else "biology",
                limit=1,
            )
            duration = int((time.monotonic() - started) * 1000)
            with self.store.connect() as connection:
                connection.execute(
                    """
                    UPDATE sp_sources SET status='READY',last_error='',last_duration_ms=?,updated_at=?
                    WHERE tenant_id=? AND source_key=?
                    """,
                    (duration, utc_now(), tenant_id, source_key),
                )
            return {"source_key": source_key, "status": "connection_confirmed",
                    "sample_records": len(result.records), "duration_ms": duration}
        except Exception as exc:
            duration = int((time.monotonic() - started) * 1000)
            error = f"{type(exc).__name__}: {exc}"[:1000]
            with self.store.connect() as connection:
                connection.execute(
                    """
                    UPDATE sp_sources SET status='DEGRADED',last_error=?,last_duration_ms=?,updated_at=?
                    WHERE tenant_id=? AND source_key=?
                    """,
                    (error, duration, utc_now(), tenant_id, source_key),
                )
            return {"source_key": source_key, "status": "connection_failed",
                    "error": error, "duration_ms": duration}

    def source_status(self, tenant_id: str = DEFAULT_TENANT) -> list[dict[str, Any]]:
        return self.store.list_sources(tenant_id)

    def news_status(self, tenant_id: str = DEFAULT_TENANT) -> dict[str, Any]:
        facets = self.store.news_facets(tenant_id)
        offline = (
            os.environ.get("BIOINTEL_RUNTIME_SMOKE_TEST") == "1"
            or os.environ.get("BIOINTEL_SCIENCE_PULSE_OFFLINE") == "1"
        )
        if offline:
            state = "CACHED" if facets["total"] else "OFFLINE"
        elif facets["live_count"]:
            state = "LIVE"
        elif facets["total"]:
            state = "CACHED"
        else:
            state = "OFFLINE"
        return {
            **facets,
            "state": state,
            "offline": offline,
            "automatic_updates": "PAUSED_OFFLINE" if offline else "BACKGROUND_SYNC_ACTIVE",
        }

    def news_feed(
        self,
        *,
        tenant_id: str = DEFAULT_TENANT,
        user_id: str = "",
        **filters: Any,
    ) -> dict[str, Any]:
        result = self.store.search_news(
            tenant_id=tenant_id,
            user_id=user_id,
            **filters,
        )
        source_map = {
            str(source.get("source_key")): source
            for source in self.store.list_sources(tenant_id)
        }
        for item in result["items"]:
            source = source_map.get(str(item.get("provider_key"))) or {}
            source_status = str(source.get("status") or "").upper()
            item["source_verified"] = bool(source.get("approved")) and source_status not in {
                "DEGRADED",
                "CIRCUIT_OPEN",
            }
            item["source_last_sync"] = str(source.get("last_sync_at") or "")
            for flag in ("is_saved", "is_read", "research_backed", "official_announcement", "breaking"):
                item[flag] = bool(item.get(flag))
        return result

    def news_detail(
        self,
        item_id: str,
        *,
        user_id: str,
        tenant_id: str = DEFAULT_TENANT,
        mark_read: bool = True,
    ) -> dict[str, Any]:
        item = self.store.get_item(item_id, tenant_id)
        if not item or str(item.get("content_type")) != "news":
            raise KeyError("Science Pulse news item not found.")
        if str(item.get("live_state")) == "DEMO":
            raise ValueError("Demo records are not available in Live Science News.")
        if mark_read:
            item["read_at"] = self.store.mark_item_read(
                user_id, item_id, tenant_id=tenant_id
            )
        else:
            item["read_at"] = self.store.item_read_at(user_id, item_id, tenant_id)
        with self.store.connect() as connection:
            summaries = connection.execute(
                """
                SELECT kind,text,model_label,evidence_json,created_at FROM sp_summaries
                WHERE tenant_id=? AND item_id=? ORDER BY created_at DESC
                """,
                (tenant_id, item_id),
            ).fetchall()
            trust_events = connection.execute(
                """
                SELECT event_type,source_url,note,verified,observed_at,created_at
                FROM sp_trust_events WHERE tenant_id=? AND item_id=?
                ORDER BY observed_at DESC,created_at DESC
                """,
                (tenant_id, item_id),
            ).fetchall()
            bookmarked = connection.execute(
                "SELECT 1 FROM sp_bookmarks WHERE tenant_id=? AND user_id=? AND item_id=?",
                (tenant_id, user_id, item_id),
            ).fetchone()
        provenance = item.get("provenance") or {}
        evidence_links = {
            key: provenance.get(key)
            for key in (
                "evidence_item_id",
                "related_publication",
                "related_preprint",
                "related_trial",
                "related_dataset",
            )
            if provenance.get(key)
        }
        explicit_state = str(provenance.get("evidence_state") or "")
        allowed_states = {
            "Peer-Reviewed Evidence Linked",
            "Preprint Evidence Linked",
            "Official Institution Announcement",
            "Clinical Trial Record Linked",
            "Dataset Linked",
            "No Primary Research Linked",
            "Evidence Relationship Uncertain",
        }
        if explicit_state in allowed_states and evidence_links:
            evidence_state = explicit_state
        elif provenance.get("related_preprint"):
            evidence_state = "Preprint Evidence Linked"
        elif provenance.get("related_trial"):
            evidence_state = "Clinical Trial Record Linked"
        elif provenance.get("related_dataset"):
            evidence_state = "Dataset Linked"
        elif evidence_links:
            evidence_state = "Evidence Relationship Uncertain"
        elif str(item.get("provider_key")) in {"rss_nibib_news", "rss_nlm_news"}:
            evidence_state = "Official Institution Announcement"
        else:
            evidence_state = "No Primary Research Linked"
        item.update(
            {
                "is_saved": bool(bookmarked),
                "summaries": [self.store._row(row) for row in summaries],
                "summary_status": "AVAILABLE" if summaries else "NOT_GENERATED",
                "trust_events": [self.store._row(row) for row in trust_events],
                "evidence_links": evidence_links,
                "evidence_state": evidence_state,
                "research_backed": bool(evidence_links),
                "official_announcement": evidence_state == "Official Institution Announcement",
            }
        )
        return item

    def queue_news_refresh(
        self,
        *,
        user_id: str,
        tenant_id: str = DEFAULT_TENANT,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.store.connect() as connection:
            queued = connection.execute(
                """
                UPDATE sp_sources SET next_sync_at=?,circuit_open_until='',updated_at=?
                WHERE tenant_id=? AND enabled=1 AND approved=1
                  AND lower(content_types_json) LIKE '%news%'
                """,
                (now, now, tenant_id),
            ).rowcount
        self.store.audit(
            user_id,
            "news_refresh_queued",
            "science_pulse",
            tenant_id,
            {"queued_sources": queued},
            tenant_id,
        )
        return {"status": "queued", "queued_sources": int(queued)}

    def perform_contextual_action(
        self,
        item_id: str,
        *,
        user_id: str,
        action_key: str,
        tenant_id: str = DEFAULT_TENANT,
    ) -> dict[str, Any]:
        route = CONTEXTUAL_ACTIONS.get(action_key)
        if not route:
            raise ValueError("Unsupported Science Pulse contextual action.")
        destination, action = route
        return self.integration_draft(
            item_id,
            user_id=user_id,
            destination=destination,
            action=action,
            tenant_id=tenant_id,
        )

    def follow_item(
        self,
        item_id: str,
        *,
        user_id: str,
        kind: str,
        tenant_id: str = DEFAULT_TENANT,
    ) -> dict[str, Any]:
        item = self.store.get_item(item_id, tenant_id)
        if not item:
            raise KeyError("Science Pulse item not found.")
        preferences = self.store.preferences(user_id, tenant_id)
        if kind == "source":
            field = "followed_sources"
            value = str(item.get("source_name") or item.get("provider_key") or "")
        elif kind == "topic":
            field = "followed_topics"
            categories = item.get("categories") or []
            value = str(categories[0]) if categories else ""
        else:
            raise ValueError("Follow kind must be source or topic.")
        if not value:
            raise ValueError(f"This item has no {kind} value to follow.")
        values = [str(entry) for entry in preferences.get(field) or []]
        if value.casefold() not in {entry.casefold() for entry in values}:
            values.append(value)
        preferences[field] = values[:100]
        self.store.save_preferences(user_id, preferences, tenant_id)
        self.store.audit(
            user_id,
            f"{kind}_followed",
            "science_pulse_item",
            item_id,
            {"value": value},
            tenant_id,
        )
        return {"status": "followed", "kind": kind, "value": value}

    def create_item_alert(
        self,
        item_id: str,
        *,
        user_id: str,
        tenant_id: str = DEFAULT_TENANT,
    ) -> dict[str, Any]:
        item = self.store.get_item(item_id, tenant_id)
        if not item:
            raise KeyError("Science Pulse item not found.")
        categories = [str(value) for value in item.get("categories") or []][:1]
        if categories:
            name = f"Follow {categories[0]}"
            query = ""
        else:
            words = [word for word in str(item.get("title") or "").split() if len(word) > 4][:3]
            query = " ".join(words)
            name = f"Follow {query or 'science story'}"
        rule_id = self.store.create_alert(
            user_id,
            name=name[:300],
            query=query,
            categories=categories,
            content_types=["news"],
            channels=["in_app"],
            frequency="immediate",
            tenant_id=tenant_id,
        )
        return {"status": "created", "rule_id": rule_id, "name": name}
    def sync_source(
        self,
        source_key: str,
        *,
        query: str = "biotechnology",
        trigger: str = "scheduled",
        limit: int = 50,
        tenant_id: str = DEFAULT_TENANT,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        sources = {
            str(item["source_key"]): item for item in self.store.list_sources(tenant_id)
        }
        source = sources.get(source_key)
        if not source:
            raise KeyError(f"Unknown Science Pulse source: {source_key}")
        if not int(source["enabled"]) or not int(source["approved"]):
            return {
                "source_key": source_key,
                "status": "skipped",
                "reason": "source_disabled_or_unapproved",
            }
        bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
        key = idempotency_key or f"{tenant_id}:{source_key}:{trigger}:{bucket}"
        run_id = self.store.begin_sync(
            source_key,
            trigger=trigger,
            idempotency_key=key,
            tenant_id=tenant_id,
        )
        if not run_id:
            return {
                "source_key": source_key,
                "status": "duplicate_suppressed",
                "idempotency_key": key,
            }
        started = time.monotonic()
        inserted = updated = duplicates = 0
        checkpoint = str(source.get("checkpoint") or "")
        try:
            effective_query = "" if str(source.get("kind")) == "rss" else query
            result = self.providers.fetch(source, query=effective_query, limit=limit)
            for record in result.records:
                record.live_state = "LIVE"
                record.provenance = {
                    **record.provenance,
                    "source_key": source_key,
                    "sync_run_id": run_id,
                    "retrieved_at": utc_now(),
                }
                classify(record)
                item_id, operation = self.store.upsert_item(record, tenant_id)
                if operation == "inserted":
                    inserted += 1
                    self.evaluate_alerts(item_id, tenant_id=tenant_id)
                else:
                    updated += 1
                    duplicates += 1
            checkpoint = result.checkpoint
            duration = int((time.monotonic() - started) * 1000)
            self.store.finish_sync(
                run_id,
                source_key=source_key,
                status="completed",
                duration_ms=duration,
                fetched=len(result.records),
                inserted=inserted,
                updated=updated,
                duplicates=duplicates,
                checkpoint=checkpoint,
                tenant_id=tenant_id,
            )
            return {
                "run_id": run_id,
                "source_key": source_key,
                "status": "completed",
                "fetched": len(result.records),
                "inserted": inserted,
                "updated": updated,
                "duplicates": duplicates,
                "checkpoint": checkpoint,
                "duration_ms": duration,
            }
        except Exception as exc:
            duration = int((time.monotonic() - started) * 1000)
            safe_error = f"{type(exc).__name__}: {exc}"[:1000]
            self.store.finish_sync(
                run_id,
                source_key=source_key,
                status="failed",
                duration_ms=duration,
                error=safe_error,
                checkpoint=checkpoint,
                tenant_id=tenant_id,
            )
            return {
                "run_id": run_id,
                "source_key": source_key,
                "status": "failed",
                "error": safe_error,
                "duration_ms": duration,
            }

    @staticmethod
    def _matches(item: dict[str, Any], rule: dict[str, Any]) -> bool:
        content_types = rule.get("content_types") or []
        categories = [str(value).casefold() for value in rule.get("categories") or []]
        if content_types and item["content_type"] not in content_types:
            return False
        item_categories = [str(value).casefold() for value in item.get("categories") or []]
        if categories and not set(categories).intersection(item_categories):
            return False
        query = str(rule.get("query") or "").casefold().strip()
        if query:
            corpus = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("abstract") or ""),
                    " ".join(item.get("entities") or []),
                ]
            ).casefold()
            if not all(word in corpus for word in query.split()[:10]):
                return False
        return True

    def _quiet(self, user_id: str, tenant_id: str) -> bool:
        preferences = self.store.preferences(user_id, tenant_id)
        if preferences.get("paused") or preferences.get("frequency") == "paused":
            return True
        start = str(preferences.get("quiet_start") or "")
        end = str(preferences.get("quiet_end") or "")
        if not start or not end:
            return False
        try:
            current = datetime.now(ZoneInfo(str(preferences.get("timezone") or "UTC"))).strftime("%H:%M")
        except ZoneInfoNotFoundError:
            current = datetime.now(timezone.utc).strftime("%H:%M")
        return start <= current < end if start < end else current >= start or current < end

    def _connect_delivery(self, payload: dict[str, Any]) -> tuple[bool, str]:
        from biointel.connect.connect_service import ConnectService

        result = ConnectService(str(self.root)).send_message(
            "science-pulse",
            str(payload["user_id"]),
            f"{payload['title']}\n{payload['body']}",
            [str(payload.get("canonical_url") or "")],
        )
        return bool(result.get("message_id")), str(result.get("message_id") or "")

    def _education_home_delivery(self, payload: dict[str, Any]) -> tuple[bool, str]:
        preferences = self.store.preferences(str(payload["user_id"]), str(payload["tenant_id"]))
        institution_id = str(preferences.get("education_institution_id") or "")
        if not institution_id:
            return False, "Education institution is not configured."
        from biointel.education.paths import education_paths
        from biointel.education.phase4 import EducationPhase4Service
        from biointel.education.platform import EducationPlatform

        database, media = education_paths(self.root)
        platform = EducationPlatform(database, media)
        service = EducationPhase4Service(platform, root=self.root)
        result = service.emit_notification(
            str(payload["user_id"]),
            institution_id,
            str(payload["user_id"]),
            "science_pulse",
            str(payload["title"]),
            str(payload["body"]),
            action_url="/BioIntel_Science_Pulse",
            priority="high" if payload.get("priority") == "high" else "normal",
            dedupe_key=f"science-pulse:{payload['item_id']}:{payload['rule_id']}",
        )
        return bool(result.get("id") or result.get("suppressed")), str(
            result.get("id") or result.get("reason") or ""
        )

    def _deliver(self, channel: str, payload: dict[str, Any]) -> tuple[str, str, str]:
        if channel in LOCAL_CONFIRMED_CHANNELS:
            return DeliveryState.DELIVERED, f"local:{channel}", ""
        if channel == "connect":
            try:
                ok, reference = self._connect_delivery(payload)
                return (
                    (DeliveryState.DELIVERED, reference, "")
                    if ok
                    else (DeliveryState.FAILED, "", reference)
                )
            except Exception as exc:
                return DeliveryState.FAILED, "", f"{type(exc).__name__}: {exc}"[:1000]
        if channel == "education_home":
            try:
                ok, reference = self._education_home_delivery(payload)
                return (
                    (DeliveryState.DELIVERED, reference, "")
                    if ok
                    else (DeliveryState.CONFIGURATION_REQUIRED, "", reference)
                )
            except Exception as exc:
                return DeliveryState.FAILED, "", f"{type(exc).__name__}: {exc}"[:1000]
        dispatcher = self.dispatchers.get(channel)
        if dispatcher:
            try:
                ok, reference = dispatcher(payload)
                return (
                    (DeliveryState.DELIVERED, reference, "")
                    if ok
                    else (DeliveryState.FAILED, "", reference)
                )
            except Exception as exc:
                return DeliveryState.FAILED, "", f"{type(exc).__name__}: {exc}"[:1000]
        return DeliveryState.CONFIGURATION_REQUIRED, "", f"{channel} dispatcher is not configured."

    def evaluate_alerts(
        self, item_id: str, *, tenant_id: str = DEFAULT_TENANT
    ) -> dict[str, int]:
        item = self.store.get_item(item_id, tenant_id)
        if not item:
            return {"matched": 0, "delivered": 0, "suppressed": 0}
        matched = delivered = suppressed = 0
        for rule in self.store.enabled_alerts(tenant_id):
            if not self._matches(item, rule):
                continue
            matched += 1
            user_id = str(rule["user_id"])
            if self._quiet(user_id, tenant_id):
                suppressed += 1
                continue
            frequency = str(rule.get("frequency") or "immediate")
            if frequency not in {"instant", "immediate", "in_app_only"}:
                continue
            channels = rule.get("channels") or ["in_app"]
            max_notifications = int(
                self.store.preferences(user_id, tenant_id).get("max_notifications_per_sync", 50)
            )
            for channel in list(channels)[: max(1, min(max_notifications, 100))]:
                payload = {
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "item_id": item_id,
                    "rule_id": rule["rule_id"],
                    "title": item["title"],
                    "body": item.get("abstract") or "New source-linked Science Pulse item.",
                    "canonical_url": item.get("canonical_url") or "",
                    "priority": "high" if item.get("trust_state") != "normal" else "normal",
                }
                state, reference, error = self._deliver(str(channel), payload)
                _, created = self.store.put_notification(
                    user_id=user_id,
                    item_id=item_id,
                    rule_id=str(rule["rule_id"]),
                    channel=str(channel),
                    title=str(item["title"]),
                    body=str(payload["body"]),
                    state=str(state),
                    reference=reference,
                    error=error,
                    tenant_id=tenant_id,
                )
                if created and state == DeliveryState.DELIVERED:
                    delivered += 1
                elif not created:
                    suppressed += 1
        return {"matched": matched, "delivered": delivered, "suppressed": suppressed}

    def generate_digest(
        self,
        user_id: str,
        *,
        frequency: str = "daily",
        tenant_id: str = DEFAULT_TENANT,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        end = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        hours = {"hourly": 1, "three_hour": 3, "daily": 24, "weekly": 168}.get(
            frequency, 24
        )
        start = end - timedelta(hours=hours)
        preferences = self.store.preferences(user_id, tenant_id)
        items = self.store.search_items(
            tenant_id=tenant_id,
            category=str(preferences.get("primary_category") or ""),
            limit=50,
        )
        eligible = [
            item
            for item in items
            if not item.get("published_at")
            or str(item["published_at"]) >= start.date().isoformat()
        ][:20]
        if not eligible:
            return {"status": "insufficient_data", "item_count": 0}
        lines = [
            f"# {frequency.replace('_', ' ').title()} Science Pulse",
            "",
            f"Generated: {end.isoformat(timespec='seconds')}",
            "",
        ]
        for position, item in enumerate(eligible, start=1):
            why = (
                f"Matched {', '.join((item.get('categories') or ['stored scientific evidence'])[:2])}; "
                f"source confidence {float(item.get('confidence') or 0):.0%}."
            )
            lines.extend(
                [
                    f"{position}. {item['title']}",
                    f"   Source: {item.get('source_name') or item.get('provider_key')}",
                    f"   Link: {item.get('canonical_url') or 'not supplied'}",
                    f"   Why this matters: {why}",
                ]
            )
        body = "\n".join(lines)
        digest_id = self.store.save_digest(
            user_id=user_id,
            frequency=frequency,
            title=f"{frequency.replace('_', ' ').title()} Science Pulse",
            body=body,
            item_ids=[str(item["item_id"]) for item in eligible],
            period_start=start.isoformat(timespec="seconds"),
            period_end=end.isoformat(timespec="seconds"),
            tenant_id=tenant_id,
        )
        return {
            "status": "ready",
            "digest_id": digest_id,
            "item_count": len(eligible),
            "body": body,
        }

    def integration_draft(
        self,
        item_id: str,
        *,
        user_id: str,
        destination: str,
        action: str,
        tenant_id: str = DEFAULT_TENANT,
    ) -> dict[str, Any]:
        if destination not in INTEGRATION_DESTINATIONS:
            raise ValueError("Unsupported Science Pulse integration destination.")
        item = self.store.get_item(item_id, tenant_id)
        if not item:
            raise KeyError("Science Pulse item not found.")
        payload = {
            "title": item["title"],
            "permitted_excerpt": item.get("abstract") or "",
            "canonical_url": item.get("canonical_url") or "",
            "doi": item.get("doi") or "",
            "pmid": item.get("pmid") or "",
            "provenance": item.get("provenance") or {},
            "source_links": [
                source.get("source_url") for source in item.get("sources", []) if source.get("source_url")
            ],
            "content_boundary": "Metadata and permitted excerpt only; full paid article access is not claimed.",
            "human_approval_required": True,
        }
        draft_id = self.store.create_integration_draft(
            user_id=user_id,
            item_id=item_id,
            destination=destination,
            action=action,
            payload=payload,
            tenant_id=tenant_id,
        )
        self.store.audit(
            user_id,
            "integration_draft_created",
            destination,
            draft_id,
            {"item_id": item_id, "action": action},
            tenant_id,
        )
        return {
            "integration_id": draft_id,
            "state": "approval_required",
            "destination": destination,
            "action": action,
            "payload": payload,
        }

    def shiro_context(
        self, item_ids: list[str], *, level: str = "researcher", tenant_id: str = DEFAULT_TENANT
    ) -> dict[str, Any]:
        items = [
            item for item_id in item_ids[:10] if (item := self.store.get_item(item_id, tenant_id))
        ]
        return {
            "instruction": (
                f"Explain at {level} level using only supplied metadata/excerpts. "
                "Cite each source link and state evidence limitations."
            ),
            "items": [
                {
                    "title": item["title"],
                    "excerpt": item.get("abstract") or "",
                    "doi": item.get("doi") or "",
                    "pmid": item.get("pmid") or "",
                    "url": item.get("canonical_url") or "",
                    "trust_state": item.get("trust_state"),
                    "provenance": item.get("provenance") or {},
                }
                for item in items
            ],
            "full_text_available": False,
        }

    def trends(self, tenant_id: str = DEFAULT_TENANT, limit: int = 20) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT categories_json,published_at FROM sp_items
                WHERE tenant_id=? ORDER BY published_at DESC,last_seen_at DESC LIMIT 2000
                """,
                (tenant_id,),
            ).fetchall()
        counts: dict[str, int] = {}
        for row in rows:
            import json

            try:
                categories = json.loads(row["categories_json"])
            except json.JSONDecodeError:
                categories = []
            for category in categories:
                counts[str(category)] = counts.get(str(category), 0) + 1
        return [
            {"topic": topic, "item_count": count}
            for topic, count in sorted(counts.items(), key=lambda value: (-value[1], value[0]))[
                : max(1, min(limit, 100))
            ]
        ]

    def update_trust(
        self,
        item_id: str,
        event_type: str,
        *,
        source_url: str = "",
        note: str = "",
        verified: bool = False,
        tenant_id: str = DEFAULT_TENANT,
    ) -> dict[str, Any]:
        if event_type not in {"corrected", "retracted", "expression_of_concern"}:
            raise ValueError("Unsupported trust event type.")
        item = self.store.get_item(item_id, tenant_id)
        if not item:
            raise KeyError("Science Pulse item not found.")
        event_id = self.store.set_trust(
            item_id,
            event_type,
            source_url=source_url,
            note=note,
            verified=verified,
            tenant_id=tenant_id,
        )
        with self.store.connect() as connection:
            users = connection.execute(
                "SELECT DISTINCT user_id FROM sp_bookmarks WHERE tenant_id=? AND item_id=?",
                (tenant_id, item_id),
            ).fetchall()
            linked = connection.execute(
                "UPDATE sp_integrations SET state='review_required',updated_at=? WHERE tenant_id=? AND item_id=?",
                (utc_now(), tenant_id, item_id),
            ).rowcount
        delivered = 0
        for row in users:
            _, created = self.store.put_notification(
                user_id=str(row["user_id"]), item_id=item_id, rule_id=f"trust:{event_id}",
                channel="in_app", title=f"Trust update: {item['title']}",
                body=f"This saved item is now marked {event_type}. Historical evidence was preserved.",
                state="delivered", reference=f"trust-event:{event_id}", tenant_id=tenant_id,
            )
            delivered += int(created)
        self.store.audit("science-pulse-worker", "trust_status_updated", "science_pulse_item", item_id,
                         {"event_id": event_id, "event_type": event_type, "verified": verified}, tenant_id)
        return {"event_id": event_id, "notifications": delivered,
                "linked_integrations_flagged": linked, "history_preserved": True}

    def health(self, tenant_id: str = DEFAULT_TENANT) -> dict[str, Any]:
        metrics = self.store.metrics(tenant_id)
        return {
            **metrics,
            "scheduler_mode": (
                "offline-smoke"
                if os.environ.get("BIOINTEL_RUNTIME_SMOKE_TEST") == "1"
                else "persistent-background-worker"
            ),
            "provider_capabilities": capability_matrix(),
        }


__all__ = ["SciencePulseService", "INTEGRATION_DESTINATIONS"]
