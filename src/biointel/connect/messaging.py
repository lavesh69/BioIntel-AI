from __future__ import annotations

import json
from typing import Any

from biointel.database.core import json_text, utc_now
from .repositories import ConnectRepository, decode_json, new_id
from .services import Conflict, ConnectError, NotFound, PermissionDenied

GROUP_ROLES = {"owner", "administrator", "moderator", "member", "guest", "read_only"}
MESSAGE_TYPES = {"text", "markdown", "equation", "code", "image", "video", "pdf", "document", "voice_note", "reference", "announcement"}


class MessagingService:
    """Durable conversations plus a persisted single-process realtime event fallback."""

    def __init__(self, repo: ConnectRepository, network: Any) -> None:
        self.repo, self.network = repo, network

    def _user(self, user_id: str) -> dict[str, Any]:
        user = self.repo.user(user_id)
        if not user or user["state"] != "active":
            raise NotFound("Active user not found.")
        return user

    def _membership(self, actor: str, conversation_id: str, *, active: bool = True) -> dict[str, Any]:
        with self.repo.database.connection(read_only=True) as db:
            row = db.execute("SELECT * FROM connect_conversation_members WHERE conversation_id=? AND user_id=? AND deleted_at_utc IS NULL", (conversation_id, actor)).fetchone()
        if not row or (active and row["state"] != "active"):
            raise PermissionDenied("Conversation access is not permitted.")
        return dict(row)

    def _members(self, conversation_id: str, *, active: bool = True) -> list[dict[str, Any]]:
        clause = "AND m.state='active'" if active else ""
        with self.repo.database.connection(read_only=True) as db:
            rows = db.execute(f"""SELECT m.*,u.username,u.display_name FROM connect_conversation_members m
                JOIN connect_users u ON u.user_id=m.user_id WHERE m.conversation_id=? AND m.deleted_at_utc IS NULL {clause}
                ORDER BY m.created_at_utc""", (conversation_id,)).fetchall()
        return [dict(row) for row in rows]

    def _emit(self, user_id: str, channel_type: str, channel_id: str, event_type: str,
              payload: dict[str, Any], dedupe_key: str) -> str:
        now, event_id = utc_now(), new_id("rte")
        with self.repo.database.connection() as db:
            prior = db.execute("SELECT event_id FROM connect_realtime_events WHERE user_id=? AND dedupe_key=?", (user_id, dedupe_key)).fetchone()
            if prior:
                return str(prior["event_id"])
            sequence = int(db.execute("SELECT COALESCE(MAX(event_sequence),0)+1 FROM connect_realtime_events WHERE user_id=?", (user_id,)).fetchone()[0])
            db.execute("""INSERT INTO connect_realtime_events(event_id,creator_id,user_id,channel_type,channel_id,event_type,
                event_sequence,payload_json,dedupe_key,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (event_id, user_id, user_id, channel_type, channel_id, event_type, sequence, json_text(payload), dedupe_key, now, now))
        return event_id

    def create_conversation(self, actor: str, member_ids: list[str], *, conversation_type: str = "direct",
                            title: str = "", description: str = "", group_type: str = "research_team") -> dict[str, Any]:
        self._user(actor)
        members = list(dict.fromkeys([actor, *member_ids]))
        if conversation_type not in {"direct", "group"}:
            raise ConnectError("Conversation type must be direct or group.")
        if conversation_type == "direct" and len(members) != 2:
            raise ConnectError("A direct conversation requires exactly two users.")
        if conversation_type == "group" and not 2 <= len(members) <= 250:
            raise ConnectError("A group requires 2-250 users.")
        for user_id in members:
            self._user(user_id)
            if user_id != actor and self.repo.blocked(actor, user_id):
                raise PermissionDenied("A blocked user cannot be added to a conversation.")
        if conversation_type == "direct":
            other = next(user_id for user_id in members if user_id != actor)
            with self.repo.database.connection(read_only=True) as db:
                existing = db.execute("""SELECT c.conversation_id FROM connect_conversations c
                    JOIN connect_conversation_members a ON a.conversation_id=c.conversation_id AND a.user_id=?
                    JOIN connect_conversation_members b ON b.conversation_id=c.conversation_id AND b.user_id=?
                    WHERE c.conversation_type='direct' AND c.deleted_at_utc IS NULL LIMIT 1""", (actor, other)).fetchone()
            if existing:
                return self.get(actor, str(existing["conversation_id"]))
        now, conversation_id = utc_now(), new_id("cnv")
        payload = {"group_type": group_type} if conversation_type == "group" else {}
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_conversations(conversation_id,creator_id,conversation_type,title,description,
                owner_id,payload_json,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (conversation_id, actor, conversation_type, title[:160], description[:1000], actor, json_text(payload), "members", now, now))
            for user_id in members:
                role = "owner" if user_id == actor else "member"
                member_state = "active"
                if conversation_type == "direct" and user_id != actor:
                    permission = self.repo.privacy(user_id)["message_permission"]
                    allowed = permission == "everyone" or (permission == "connections" and self.repo.connected(actor, user_id))
                    member_state = "active" if allowed else "pending"
                db.execute("""INSERT INTO connect_conversation_members(membership_id,creator_id,conversation_id,user_id,role,joined_at_utc,
                    state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (new_id("cvm"), actor, conversation_id, user_id, role, now, member_state, "members", now, now))
            pending = [user_id for user_id in members if user_id != actor and not self.repo.connected(actor, user_id)] if conversation_type == "direct" else []
            for recipient in pending:
                permission = self.repo.privacy(recipient)["message_permission"]
                if permission != "everyone":
                    request_id = new_id("mreq")
                    db.execute("""INSERT INTO connect_message_requests(message_request_id,creator_id,conversation_id,requester_id,
                        recipient_id,decision,state,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,'pending','pending',?,?)""",
                        (request_id, actor, conversation_id, actor, recipient, now, now))
        for recipient in members:
            if recipient != actor:
                self.repo.notification(recipient, actor, "message_request" if recipient in pending else "conversation_invitation",
                                       "conversation", conversation_id, "New private conversation request." if recipient in pending else "You were invited to a conversation.")
        self.repo.audit(actor, "conversation_created", "conversation", conversation_id, {"type": conversation_type, "members": len(members)})
        return self.get(actor, conversation_id)

    def get(self, actor: str, conversation_id: str) -> dict[str, Any]:
        self._membership(actor, conversation_id, active=False)
        with self.repo.database.connection(read_only=True) as db:
            row = db.execute("SELECT * FROM connect_conversations WHERE conversation_id=? AND deleted_at_utc IS NULL", (conversation_id,)).fetchone()
        if not row:
            raise NotFound("Conversation not found.")
        result = dict(row)
        result["payload"] = decode_json(result.pop("payload_json"), {})
        result["members"] = self._members(conversation_id, active=False)
        return result

    def list(self, actor: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.repo.database.connection(read_only=True) as db:
            ids = [str(row[0]) for row in db.execute("""SELECT c.conversation_id FROM connect_conversations c
                JOIN connect_conversation_members m ON m.conversation_id=c.conversation_id
                WHERE m.user_id=? AND m.state='active' AND c.deleted_at_utc IS NULL
                ORDER BY c.updated_at_utc DESC LIMIT ?""", (actor, min(max(limit, 1), 250))).fetchall()]
        return [self.get(actor, conversation_id) for conversation_id in ids]

    def respond_request(self, actor: str, request_id: str, decision: str, *, reason: str = "") -> dict[str, Any]:
        if decision not in {"accepted", "declined", "blocked", "reported"}:
            raise ConnectError("Invalid message-request decision.")
        with self.repo.database.connection() as db:
            row = db.execute("SELECT * FROM connect_message_requests WHERE message_request_id=? AND decision='pending'", (request_id,)).fetchone()
            if not row:
                raise NotFound("Pending message request not found.")
            if row["recipient_id"] != actor:
                raise PermissionDenied("Only the recipient may respond.")
            now = utc_now()
            db.execute("UPDATE connect_message_requests SET decision=?,state=?,updated_at_utc=?,version=version+1 WHERE message_request_id=?",
                       (decision, decision, now, request_id))
            db.execute("UPDATE connect_conversation_members SET state=?,updated_at_utc=?,version=version+1 WHERE conversation_id=? AND user_id=?",
                       ("active" if decision == "accepted" else decision, now, row["conversation_id"], actor))
            if decision != "accepted":
                db.execute("UPDATE connect_conversations SET state='closed',updated_at_utc=?,version=version+1 WHERE conversation_id=?", (now, row["conversation_id"]))
        if decision == "blocked":
            self.network.block(actor, str(row["requester_id"]), reason)
        if decision == "reported":
            self._report(actor, "conversation", str(row["conversation_id"]), "harassment", reason)
        self.repo.audit(actor, f"message_request_{decision}", "message_request", request_id, {"reason": reason[:500]})
        return {"message_request_id": request_id, "decision": decision}

    def send(self, actor: str, conversation_id: str, body: str = "", *, message_type: str = "text",
             client_event_id: str = "", parent_message_id: str | None = None,
             media_ids: list[str] | None = None, references: list[dict[str, str]] | None = None) -> dict[str, Any]:
        member = self._membership(actor, conversation_id)
        if member["role"] == "read_only":
            raise PermissionDenied("Read-only members cannot send messages.")
        if message_type not in MESSAGE_TYPES:
            raise ConnectError("Unsupported message type.")
        media_ids = list(dict.fromkeys(media_ids or []))[:20]
        if not body.strip() and not media_ids and not references:
            raise ConnectError("A message needs text, an attachment or a reference.")
        for participant in self._members(conversation_id):
            if participant["user_id"] != actor and self.repo.blocked(actor, participant["user_id"]):
                raise PermissionDenied("Blocked users cannot exchange messages.")
        now, message_id = utc_now(), new_id("msg")
        client_event_id = client_event_id.strip()[:120] or new_id("client")
        with self.repo.database.connection() as db:
            duplicate = db.execute("SELECT message_id FROM connect_messages WHERE conversation_id=? AND client_event_id=?", (conversation_id, client_event_id)).fetchone()
            if duplicate:
                return self.message(actor, str(duplicate["message_id"]))
            if parent_message_id:
                parent = db.execute("SELECT 1 FROM connect_messages WHERE message_id=? AND conversation_id=?", (parent_message_id, conversation_id)).fetchone()
                if not parent:
                    raise NotFound("Reply target not found in this conversation.")
            sequence = int(db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM connect_messages WHERE conversation_id=?", (conversation_id,)).fetchone()[0])
            db.execute("""INSERT INTO connect_messages(message_id,creator_id,conversation_id,sender_id,parent_message_id,message_type,
                body,client_event_id,sequence,delivery_state,payload_json,visibility,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,'sent',?,'members',?,?)""",
                (message_id, actor, conversation_id, actor, parent_message_id, message_type, body.strip()[:100000], client_event_id,
                 sequence, json_text({"references": references or []}), now, now))
            for position, media_id in enumerate(media_ids):
                media = db.execute("SELECT owner_id,state FROM connect_media_objects WHERE media_id=?", (media_id,)).fetchone()
                if not media or media["owner_id"] != actor or media["state"] != "available":
                    raise PermissionDenied("Only the sender's cleared media may be attached.")
                db.execute("""INSERT INTO connect_message_attachments(attachment_id,creator_id,message_id,media_id,position,
                    visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,'members',?,?)""",
                    (new_id("matt"), actor, message_id, media_id, position, now, now))
            for participant in self._members(conversation_id):
                user_id = str(participant["user_id"])
                if user_id == actor:
                    continue
                db.execute("""INSERT INTO connect_message_receipts(receipt_id,creator_id,message_id,user_id,state,visibility,
                    created_at_utc,updated_at_utc) VALUES(?,?,?,?, 'queued','members',?,?)""",
                    (new_id("rcp"), actor, message_id, user_id, now, now))
            db.execute("UPDATE connect_conversations SET last_event_sequence=?,updated_at_utc=?,version=version+1 WHERE conversation_id=?", (sequence, now, conversation_id))
        for participant in self._members(conversation_id):
            recipient = str(participant["user_id"])
            if recipient == actor:
                continue
            self._emit(recipient, "conversation", conversation_id, "message.created", {"message_id": message_id, "sequence": sequence}, f"message:{message_id}")
            self.repo.notification(recipient, actor, "new_message", "conversation", conversation_id, "New private message.")
        self.repo.audit(actor, "message_sent", "message", message_id, {"conversation_id": conversation_id, "sequence": sequence})
        return self.message(actor, message_id)

    def message(self, actor: str, message_id: str) -> dict[str, Any]:
        with self.repo.database.connection(read_only=True) as db:
            row = db.execute("SELECT * FROM connect_messages WHERE message_id=? AND deleted_at_utc IS NULL", (message_id,)).fetchone()
            if not row:
                raise NotFound("Message not found.")
            self._membership(actor, str(row["conversation_id"]))
            result = dict(row)
            result["payload"] = decode_json(result.pop("payload_json"), {})
            result["attachments"] = [dict(item) for item in db.execute("SELECT * FROM connect_message_attachments WHERE message_id=? AND state='active'", (message_id,)).fetchall()]
            result["receipts"] = [dict(item) for item in db.execute("SELECT * FROM connect_message_receipts WHERE message_id=?", (message_id,)).fetchall()]
        return result

    def history(self, actor: str, conversation_id: str, *, after_sequence: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        self._membership(actor, conversation_id)
        with self.repo.database.connection(read_only=True) as db:
            ids = [str(row[0]) for row in db.execute("""SELECT message_id FROM connect_messages WHERE conversation_id=?
                AND sequence>? AND state NOT IN ('permanently_deleted') AND deleted_at_utc IS NULL ORDER BY sequence LIMIT ?""",
                (conversation_id, max(after_sequence, 0), min(max(limit, 1), 250))).fetchall()]
        return [self.message(actor, message_id) for message_id in ids]

    def update_receipt(self, actor: str, message_id: str, receipt_state: str) -> dict[str, Any]:
        if receipt_state not in {"delivered", "read", "failed", "retrying"}:
            raise ConnectError("Invalid receipt state.")
        message = self.message(actor, message_id)
        now = utc_now()
        with self.repo.database.connection() as db:
            row = db.execute("SELECT receipt_id FROM connect_message_receipts WHERE message_id=? AND user_id=?", (message_id, actor)).fetchone()
            if not row:
                raise PermissionDenied("No delivery receipt exists for this user.")
            delivered = now if receipt_state in {"delivered", "read"} else None
            read_at = now if receipt_state == "read" else None
            db.execute("""UPDATE connect_message_receipts SET state=?,delivered_at_utc=COALESCE(delivered_at_utc,?),
                read_at_utc=COALESCE(read_at_utc,?),updated_at_utc=?,version=version+1 WHERE receipt_id=?""",
                (receipt_state, delivered, read_at, now, row["receipt_id"]))
            if receipt_state == "read":
                db.execute("UPDATE connect_conversation_members SET last_read_sequence=MAX(last_read_sequence,?),updated_at_utc=? WHERE conversation_id=? AND user_id=?",
                           (message["sequence"], now, message["conversation_id"], actor))
        self._emit(str(message["sender_id"]), "conversation", str(message["conversation_id"]), f"message.{receipt_state}",
                   {"message_id": message_id, "user_id": actor}, f"receipt:{message_id}:{actor}:{receipt_state}")
        return {"message_id": message_id, "state": receipt_state, "updated_at_utc": now}

    def edit(self, actor: str, message_id: str, body: str) -> dict[str, Any]:
        message = self.message(actor, message_id)
        if message["sender_id"] != actor:
            raise PermissionDenied("Only the sender may edit a message.")
        if not body.strip():
            raise ConnectError("Edited message cannot be blank.")
        now = utc_now()
        with self.repo.database.connection() as db:
            revision = int(db.execute("SELECT COALESCE(MAX(revision_number),0)+1 FROM connect_message_revisions WHERE message_id=?", (message_id,)).fetchone()[0])
            db.execute("""INSERT INTO connect_message_revisions(revision_id,creator_id,message_id,editor_id,body,revision_number,
                visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,'members',?,?)""",
                (new_id("mrev"), actor, message_id, actor, message["body"], revision, now, now))
            db.execute("UPDATE connect_messages SET body=?,edited_at_utc=?,updated_at_utc=?,version=version+1 WHERE message_id=?", (body.strip()[:100000], now, now, message_id))
        self.repo.audit(actor, "message_edited", "message", message_id, {"revision": revision})
        return self.message(actor, message_id)

    def delete(self, actor: str, message_id: str) -> dict[str, Any]:
        message = self.message(actor, message_id)
        membership = self._membership(actor, str(message["conversation_id"]))
        if message["sender_id"] != actor and membership["role"] not in {"owner", "administrator", "moderator"}:
            raise PermissionDenied("Message deletion is not permitted.")
        now = utc_now()
        with self.repo.database.connection() as db:
            db.execute("UPDATE connect_messages SET body='',state='deleted',delivery_state='deleted',deleted_at_utc=?,updated_at_utc=?,version=version+1 WHERE message_id=?", (now, now, message_id))
        self.repo.audit(actor, "message_deleted", "message", message_id)
        return {"message_id": message_id, "state": "deleted"}

    def react(self, actor: str, message_id: str, reaction_type: str) -> dict[str, Any]:
        self.message(actor, message_id)
        now = utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_message_reactions(reaction_id,creator_id,message_id,user_id,reaction_type,visibility,
                created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,'members',?,?) ON CONFLICT(message_id,user_id)
                DO UPDATE SET reaction_type=excluded.reaction_type,state='active',deleted_at_utc=NULL,updated_at_utc=excluded.updated_at_utc,version=connect_message_reactions.version+1""",
                (new_id("mrea"), actor, message_id, actor, reaction_type[:40], now, now))
            row = db.execute("SELECT * FROM connect_message_reactions WHERE message_id=? AND user_id=?", (message_id, actor)).fetchone()
        return dict(row)

    def save(self, actor: str, message_id: str, saved: bool = True) -> dict[str, Any]:
        self.message(actor, message_id)
        now = utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_saved_messages(saved_message_id,creator_id,message_id,user_id,state,visibility,
                created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,'private',?,?) ON CONFLICT(message_id,user_id)
                DO UPDATE SET state=excluded.state,deleted_at_utc=CASE WHEN excluded.state='active' THEN NULL ELSE excluded.updated_at_utc END,
                updated_at_utc=excluded.updated_at_utc,version=connect_saved_messages.version+1""",
                (new_id("msav"), actor, message_id, actor, "active" if saved else "removed", now, now))
            row = db.execute("SELECT * FROM connect_saved_messages WHERE message_id=? AND user_id=?", (message_id, actor)).fetchone()
        return dict(row)

    def search(self, actor: str, query: str, *, conversation_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        needle = f"%{query.strip()}%"
        values: list[Any] = [actor, needle]
        conversation_clause = ""
        if conversation_id:
            self._membership(actor, conversation_id)
            conversation_clause = "AND m.conversation_id=?"
            values.append(conversation_id)
        values.append(min(max(limit, 1), 250))
        with self.repo.database.connection(read_only=True) as db:
            ids = [str(row[0]) for row in db.execute(f"""SELECT m.message_id FROM connect_messages m
                JOIN connect_conversation_members cm ON cm.conversation_id=m.conversation_id AND cm.user_id=? AND cm.state='active'
                WHERE m.body LIKE ? COLLATE NOCASE AND m.state NOT IN ('deleted','permanently_deleted') {conversation_clause}
                ORDER BY m.created_at_utc DESC LIMIT ?""", values).fetchall()]
        return [self.message(actor, message_id) for message_id in ids]

    def typing(self, actor: str, conversation_id: str, active: bool) -> str:
        self._membership(actor, conversation_id)
        event_key = new_id("typing")
        for member in self._members(conversation_id):
            recipient = str(member["user_id"])
            if recipient != actor:
                self._emit(recipient, "conversation", conversation_id, "typing", {"user_id": actor, "active": bool(active), "expires_in_seconds": 8}, f"{event_key}:{recipient}")
        return event_key

    def events(self, actor: str, *, after_sequence: int = 0, limit: int = 100, acknowledge: bool = False) -> list[dict[str, Any]]:
        with self.repo.database.connection() as db:
            rows = db.execute("""SELECT * FROM connect_realtime_events WHERE user_id=? AND event_sequence>?
                ORDER BY event_sequence LIMIT ?""", (actor, max(after_sequence, 0), min(max(limit, 1), 250))).fetchall()
            output = [dict(row) for row in rows]
            for row in output:
                row["payload"] = decode_json(row.pop("payload_json"), {})
            if acknowledge and output:
                now = utc_now()
                ids = [row["event_id"] for row in output]
                db.execute(f"UPDATE connect_realtime_events SET acknowledged_at_utc=?,updated_at_utc=? WHERE user_id=? AND event_id IN ({','.join('?' for _ in ids)})", (now, now, actor, *ids))
        return output

    def add_member(self, actor: str, conversation_id: str, user_id: str, role: str = "member") -> dict[str, Any]:
        membership = self._membership(actor, conversation_id)
        if membership["role"] not in {"owner", "administrator"}:
            raise PermissionDenied("Only group owners or administrators may add members.")
        if role not in GROUP_ROLES:
            raise ConnectError("Invalid group role.")
        self._user(user_id)
        if self.repo.blocked(actor, user_id):
            raise PermissionDenied("Blocked users cannot be invited.")
        now = utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_conversation_members(membership_id,creator_id,conversation_id,user_id,role,joined_at_utc,
                state,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,'active','members',?,?)
                ON CONFLICT(conversation_id,user_id) DO UPDATE SET role=excluded.role,state='active',deleted_at_utc=NULL,
                updated_at_utc=excluded.updated_at_utc,version=connect_conversation_members.version+1""",
                (new_id("cvm"), actor, conversation_id, user_id, role, now, now, now))
            row = db.execute("SELECT * FROM connect_conversation_members WHERE conversation_id=? AND user_id=?", (conversation_id, user_id)).fetchone()
        self.repo.notification(user_id, actor, "group_invitation", "conversation", conversation_id, "You were added to a private research group.")
        return dict(row)

    def remove_member(self, actor: str, conversation_id: str, user_id: str) -> dict[str, Any]:
        membership = self._membership(actor, conversation_id)
        if actor != user_id and membership["role"] not in {"owner", "administrator", "moderator"}:
            raise PermissionDenied("Member removal is not permitted.")
        target = self._membership(user_id, conversation_id, active=False)
        if target["role"] == "owner" and actor != user_id:
            raise PermissionDenied("Ownership must be transferred before removal.")
        now = utc_now()
        with self.repo.database.connection() as db:
            db.execute("UPDATE connect_conversation_members SET state='left',deleted_at_utc=?,updated_at_utc=?,version=version+1 WHERE conversation_id=? AND user_id=?", (now, now, conversation_id, user_id))
        self.repo.audit(actor, "conversation_member_removed", "conversation", conversation_id, {"user_id": user_id})
        return {"conversation_id": conversation_id, "user_id": user_id, "state": "left"}

    def _report(self, actor: str, target_type: str, target_id: str, reason: str, detail: str) -> dict[str, Any]:
        report_id, case_id, now = new_id("rpt"), new_id("case"), utc_now()
        with self.repo.database.connection() as db:
            db.execute("""INSERT INTO connect_content_reports(report_id,reporter_id,target_type,target_id,reason,detail,
                evidence_json,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,'{}',?,?)""",
                (report_id, actor, target_type, target_id, reason, detail[:5000], now, now))
            db.execute("INSERT INTO connect_moderation_cases(case_id,report_id,created_at_utc,updated_at_utc) VALUES(?,?,?,?)", (case_id, report_id, now, now))
        self.repo.audit(actor, "content_reported", target_type, target_id, {"report_id": report_id})
        return {"report_id": report_id, "case_id": case_id, "state": "submitted"}

    def report_message(self, actor: str, message_id: str, reason: str, detail: str = "") -> dict[str, Any]:
        self.message(actor, message_id)
        return self._report(actor, "message", message_id, reason, detail)
