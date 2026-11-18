from __future__ import annotations

import base64
import json
import re
from typing import Any, Iterable
from uuid import uuid4

from biointel.database.core import json_text, utc_now

from .database import ConnectDatabase

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def decode_json(value: object, default: object) -> object:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def encode_cursor(created_at_utc: str, record_id: str) -> str:
    return base64.urlsafe_b64encode(f"{created_at_utc}\n{record_id}".encode()).decode().rstrip("=")


def decode_cursor(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    try:
        created_at, record_id = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode().split("\n", 1)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("Invalid feed cursor.") from None
    return created_at, record_id


class ConnectRepository:
    def __init__(self, database: ConnectDatabase) -> None:
        self.database = database

    def ensure_user(self, username: str, display_name: str, role: str = "researcher") -> dict[str, Any]:
        normalized = username.strip().lower()
        if not USERNAME_PATTERN.fullmatch(normalized):
            normalized = re.sub(r"[^a-z0-9._-]+", "-", normalized).strip("-._")[:63]
            normalized = normalized if len(normalized) >= 3 else f"user-{uuid4().hex[:8]}"
        now = utc_now()
        with self.database.connection() as db:
            db.execute("""
                INSERT INTO connect_users(user_id,username,display_name,role,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?) ON CONFLICT(username) DO UPDATE SET
                display_name=excluded.display_name,role=excluded.role,updated_at_utc=excluded.updated_at_utc,
                version=connect_users.version+1
            """, (new_id("usr"), normalized, display_name.strip()[:120] or normalized, role, now, now))
            row = db.execute("SELECT * FROM connect_users WHERE username=? COLLATE NOCASE", (normalized,)).fetchone()
            user_id = str(row["user_id"])
            db.execute("""
                INSERT OR IGNORE INTO connect_profiles(user_id,username,full_name,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?)
            """, (user_id, normalized, display_name.strip()[:120] or normalized, now, now))
            db.execute("""
                INSERT OR IGNORE INTO connect_privacy_preferences(user_id,created_at_utc,updated_at_utc)
                VALUES(?,?,?)
            """, (user_id, now, now))
        return dict(row)

    def user(self, user_id: str) -> dict[str, Any] | None:
        with self.database.connection(read_only=True) as db:
            row = db.execute("SELECT * FROM connect_users WHERE user_id=? AND deleted_at_utc IS NULL", (user_id,)).fetchone()
        return dict(row) if row else None

    def user_by_username(self, username: str) -> dict[str, Any] | None:
        with self.database.connection(read_only=True) as db:
            row = db.execute("SELECT * FROM connect_users WHERE username=? COLLATE NOCASE AND deleted_at_utc IS NULL", (username.strip().lower(),)).fetchone()
        return dict(row) if row else None

    def profile(self, user_id: str) -> dict[str, Any] | None:
        with self.database.connection(read_only=True) as db:
            row = db.execute("""
                SELECT p.*,u.display_name,u.role FROM connect_profiles p JOIN connect_users u ON u.user_id=p.user_id
                WHERE p.user_id=? AND p.deleted_at_utc IS NULL AND u.deleted_at_utc IS NULL
            """, (user_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        for key in ("research_json","background_json","identity_json","portfolio_json"):
            result[key.removesuffix("_json")] = decode_json(result.pop(key), {})
        return result

    def privacy(self, user_id: str) -> dict[str, Any]:
        with self.database.connection(read_only=True) as db:
            row = db.execute("SELECT * FROM connect_privacy_preferences WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            raise KeyError(user_id)
        return dict(row)

    def update_profile(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"username","full_name","headline","institution","department","laboratory","city","country",
                   "timezone","about","website","preferred_language","contact_preference","profile_image_id",
                   "cover_image_id","visibility"}
        values = {key: payload[key] for key in allowed if key in payload}
        for key in ("research","background","identity","portfolio"):
            if key in payload:
                values[f"{key}_json"] = json_text(payload[key])
        if values:
            assignments = ",".join(f"{key}=?" for key in values)
            now = utc_now()
            with self.database.connection() as db:
                db.execute(f"UPDATE connect_profiles SET {assignments},updated_at_utc=?,version=version+1 WHERE user_id=?",
                           (*values.values(), now, user_id))
                if "username" in values:
                    db.execute("UPDATE connect_users SET username=?,updated_at_utc=?,version=version+1 WHERE user_id=?",
                               (values["username"], now, user_id))
        return self.profile(user_id) or {}

    def update_privacy(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"profile_visibility","default_post_visibility","email_visibility","institution_visibility",
                   "location_visibility","online_presence_visibility","last_active_visibility","read_receipts",
                   "message_permission","connection_permission","mention_permission","tag_permission",
                   "download_permission","search_discoverable","activity_visibility"}
        values = {key: payload[key] for key in allowed if key in payload}
        if values:
            assignments = ",".join(f"{key}=?" for key in values)
            with self.database.connection() as db:
                db.execute(f"UPDATE connect_privacy_preferences SET {assignments},updated_at_utc=?,version=version+1 WHERE user_id=?",
                           (*values.values(), utc_now(), user_id))
        return self.privacy(user_id)

    def blocked(self, left_id: str, right_id: str) -> bool:
        with self.database.connection(read_only=True) as db:
            row = db.execute("""
                SELECT 1 FROM connect_user_blocks WHERE state='active' AND deleted_at_utc IS NULL AND
                ((blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)) LIMIT 1
            """, (left_id,right_id,right_id,left_id)).fetchone()
        return bool(row)

    def follows(self, follower_id: str, target_id: str) -> bool:
        with self.database.connection(read_only=True) as db:
            row = db.execute("""SELECT 1 FROM connect_follows WHERE follower_id=? AND target_id=? AND
                target_type='user' AND state='active' AND deleted_at_utc IS NULL""", (follower_id,target_id)).fetchone()
        return bool(row)

    def connected(self, left_id: str, right_id: str) -> bool:
        low, high = sorted((left_id,right_id))
        with self.database.connection(read_only=True) as db:
            row = db.execute("""SELECT 1 FROM connect_connections WHERE user_low_id=? AND user_high_id=?
                AND state='accepted' AND deleted_at_utc IS NULL""", (low,high)).fetchone()
        return bool(row)

    def notification(self, recipient_id: str, actor_id: str | None, kind: str,
                     subject_type: str, subject_id: str, message: str) -> str:
        notification_id, now = new_id("ntf"), utc_now()
        with self.database.connection() as db:
            db.execute("""INSERT INTO connect_notifications(notification_id,recipient_id,actor_id,notification_type,
                subject_type,subject_id,message,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?)""",
                (notification_id,recipient_id,actor_id,kind,subject_type,subject_id,message[:500],now,now))
        return notification_id

    def audit(self, actor_id: str | None, kind: str, subject_type: str,
              subject_id: str, detail: dict[str, Any] | None = None) -> None:
        now = utc_now()
        with self.database.connection() as db:
            db.execute("""INSERT INTO connect_audit_events(event_id,actor_id,event_type,subject_type,subject_id,
                detail_json,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?)""",
                (new_id("aud"),actor_id,kind,subject_type,subject_id,json_text(detail or {}),now,now))

    def search_profiles(self, query: str, limit: int = 25) -> list[dict[str, Any]]:
        needle = f"%{query.strip()}%"
        with self.database.connection(read_only=True) as db:
            rows = db.execute("""
                SELECT p.*,u.display_name,u.role,pr.profile_visibility,pr.search_discoverable
                FROM connect_profiles p JOIN connect_users u ON u.user_id=p.user_id
                JOIN connect_privacy_preferences pr ON pr.user_id=p.user_id
                WHERE p.deleted_at_utc IS NULL AND p.state='active' AND u.state='active' AND
                pr.search_discoverable=1 AND (p.username LIKE ? COLLATE NOCASE OR p.full_name LIKE ? COLLATE NOCASE OR
                p.headline LIKE ? COLLATE NOCASE OR p.institution LIKE ? COLLATE NOCASE OR p.research_json LIKE ? COLLATE NOCASE)
                ORDER BY p.full_name COLLATE NOCASE LIMIT ?
            """, (needle,needle,needle,needle,needle,min(max(limit,1),100))).fetchall()
        return [dict(row) for row in rows]

    def post(self, post_id: str) -> dict[str, Any] | None:
        with self.database.connection(read_only=True) as db:
            row = db.execute("""
                SELECT p.*,u.username author_username,u.display_name author_name,pr.headline author_headline,
                pr.institution author_institution,
                (SELECT COUNT(*) FROM connect_comments c WHERE c.post_id=p.post_id AND c.state='published' AND c.deleted_at_utc IS NULL) comment_count,
                (SELECT COUNT(*) FROM connect_reactions r WHERE r.target_type='post' AND r.target_id=p.post_id AND r.state='active' AND r.deleted_at_utc IS NULL) reaction_count
                FROM connect_posts p JOIN connect_users u ON u.user_id=p.author_id JOIN connect_profiles pr ON pr.user_id=p.author_id
                WHERE p.post_id=? AND p.deleted_at_utc IS NULL
            """, (post_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["attachments"] = [dict(item) for item in db.execute("""
                SELECT a.position,m.media_id,m.original_name,m.mime_type,m.size_bytes,m.sha256,m.media_kind
                FROM connect_post_attachments a JOIN connect_media_objects m ON m.media_id=a.media_id
                WHERE a.post_id=? AND a.state='active' AND m.state='available' ORDER BY a.position
            """, (post_id,)).fetchall()]
            result["reactions"] = {str(item["reaction_type"]): int(item["count"]) for item in db.execute("""
                SELECT reaction_type,COUNT(*) count FROM connect_reactions WHERE target_type='post' AND target_id=?
                AND state='active' AND deleted_at_utc IS NULL GROUP BY reaction_type
            """, (post_id,)).fetchall()}
        return result

    def candidate_posts(self, cursor: tuple[str,str] | None, author_ids: Iterable[str] | None, limit: int) -> list[dict[str,Any]]:
        clauses, values = ["deleted_at_utc IS NULL","state IN ('published','draft')"], []
        if cursor:
            clauses.append("(created_at_utc<? OR (created_at_utc=? AND post_id<?))")
            values += [cursor[0],cursor[0],cursor[1]]
        selected = list(dict.fromkeys(author_ids or ()))
        if selected:
            clauses.append(f"author_id IN ({','.join('?' for _ in selected)})")
            values += selected
        values.append(min(max(limit,1),500))
        with self.database.connection(read_only=True) as db:
            ids = [row["post_id"] for row in db.execute(
                f"SELECT post_id FROM connect_posts WHERE {' AND '.join(clauses)} ORDER BY created_at_utc DESC,post_id DESC LIMIT ?", values)]
        return [post for post_id in ids if (post := self.post(str(post_id)))]

    def comments(self, post_id: str) -> list[dict[str,Any]]:
        with self.database.connection(read_only=True) as db:
            rows = db.execute("""SELECT c.*,u.username author_username,u.display_name author_name FROM connect_comments c
                JOIN connect_users u ON u.user_id=c.author_id WHERE c.post_id=? AND c.state='published'
                AND c.deleted_at_utc IS NULL ORDER BY c.created_at_utc,c.comment_id""", (post_id,)).fetchall()
        return [dict(row) for row in rows]

    def notifications(self, user_id: str, limit: int = 100) -> list[dict[str,Any]]:
        with self.database.connection(read_only=True) as db:
            rows = db.execute("""SELECT n.*,u.display_name actor_name,u.username actor_username FROM connect_notifications n
                LEFT JOIN connect_users u ON u.user_id=n.actor_id WHERE n.recipient_id=? AND n.state='active'
                AND n.deleted_at_utc IS NULL ORDER BY n.created_at_utc DESC LIMIT ?""", (user_id,min(max(limit,1),250))).fetchall()
        return [dict(row) for row in rows]
