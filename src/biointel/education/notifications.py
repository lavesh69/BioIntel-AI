from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from biointel.education.database import EducationDatabase

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class EducationNotificationService:
    """Shared notification manager across all education modules."""

    def __init__(self, db: EducationDatabase):
        self.db = db

    def send_notification(
        self,
        user_id: str,
        title: str,
        message: str,
        category: str = "academic",
        priority: str = "normal",
        deep_link: str = "",
        institution_id: str = "",
        is_demo: bool = False
    ) -> str:
        notif_id = f"notif_{uuid.uuid4().hex[:8]}"
        with self.db.connection() as conn:
            conn.execute(
                "INSERT INTO notifications VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                (notif_id, institution_id, user_id, title, message, category, priority, deep_link, int(is_demo), now_iso())
            )
        return notif_id

    def get_user_notifications(self, user_id: str, unread_only: bool = False, limit: int = 20) -> List[Dict[str, Any]]:
        with self.db.connection() as conn:
            query = "SELECT * FROM notifications WHERE user_id = ?"
            params = [user_id]
            if unread_only:
                query += " AND is_read = 0"
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def mark_as_read(self, notification_id: str) -> bool:
        with self.db.connection() as conn:
            conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
        return True

    def mark_all_read(self, user_id: str) -> int:
        with self.db.connection() as conn:
            cur = conn.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0", (user_id,))
            return cur.rowcount

