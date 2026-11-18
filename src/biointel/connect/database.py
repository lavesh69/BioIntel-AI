from __future__ import annotations

import os
from pathlib import Path

from biointel.database.core import connect, transaction, utc_now
from .complete_schema import EXTENDED_SCHEMA_SQL, MIGRATION_ID as COMPLETE_MIGRATION_ID, ROLLBACK_TABLES as COMPLETE_ROLLBACK_TABLES

BASE_MIGRATION_ID = "001_connect_phase1_phase2"
MIGRATION_ID = COMPLETE_MIGRATION_ID

SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS connect_schema_migrations(
  migration_id TEXT PRIMARY KEY, applied_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS connect_users(
  user_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  display_name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'researcher',
  state TEXT NOT NULL DEFAULT 'active', visibility TEXT NOT NULL DEFAULT 'public',
  created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL, deleted_at_utc TEXT,
  audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS connect_profiles(
  user_id TEXT PRIMARY KEY REFERENCES connect_users(user_id) ON DELETE CASCADE,
  username TEXT NOT NULL UNIQUE COLLATE NOCASE, full_name TEXT NOT NULL,
  headline TEXT NOT NULL DEFAULT '', institution TEXT NOT NULL DEFAULT '',
  department TEXT NOT NULL DEFAULT '', laboratory TEXT NOT NULL DEFAULT '',
  city TEXT NOT NULL DEFAULT '', country TEXT NOT NULL DEFAULT '', timezone TEXT NOT NULL DEFAULT 'UTC',
  about TEXT NOT NULL DEFAULT '', website TEXT NOT NULL DEFAULT '',
  preferred_language TEXT NOT NULL DEFAULT 'English', contact_preference TEXT NOT NULL DEFAULT 'connections',
  profile_image_id TEXT, cover_image_id TEXT, research_json TEXT NOT NULL DEFAULT '{}',
  background_json TEXT NOT NULL DEFAULT '{}', identity_json TEXT NOT NULL DEFAULT '{}',
  portfolio_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'active',
  visibility TEXT NOT NULL DEFAULT 'public', created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL, deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}',
  version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS connect_privacy_preferences(
  user_id TEXT PRIMARY KEY REFERENCES connect_users(user_id) ON DELETE CASCADE,
  profile_visibility TEXT NOT NULL DEFAULT 'public', default_post_visibility TEXT NOT NULL DEFAULT 'public',
  email_visibility TEXT NOT NULL DEFAULT 'only_me', institution_visibility TEXT NOT NULL DEFAULT 'public',
  location_visibility TEXT NOT NULL DEFAULT 'connections', online_presence_visibility TEXT NOT NULL DEFAULT 'connections',
  last_active_visibility TEXT NOT NULL DEFAULT 'connections', read_receipts INTEGER NOT NULL DEFAULT 1,
  message_permission TEXT NOT NULL DEFAULT 'connections', connection_permission TEXT NOT NULL DEFAULT 'everyone',
  mention_permission TEXT NOT NULL DEFAULT 'everyone', tag_permission TEXT NOT NULL DEFAULT 'connections',
  download_permission TEXT NOT NULL DEFAULT 'ask', search_discoverable INTEGER NOT NULL DEFAULT 1,
  activity_visibility TEXT NOT NULL DEFAULT 'connections', state TEXT NOT NULL DEFAULT 'active',
  visibility TEXT NOT NULL DEFAULT 'private', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
  deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS connect_follows(
  follow_id TEXT PRIMARY KEY, follower_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  target_id TEXT NOT NULL, target_type TEXT NOT NULL DEFAULT 'user', state TEXT NOT NULL DEFAULT 'active',
  visibility TEXT NOT NULL DEFAULT 'private', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
  deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1,
  UNIQUE(follower_id,target_id,target_type)
);
CREATE TABLE IF NOT EXISTS connect_connection_requests(
  request_id TEXT PRIMARY KEY, requester_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  recipient_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE, introduction TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '', shared_research_interest TEXT NOT NULL DEFAULT '', project_reference TEXT NOT NULL DEFAULT '',
  collaboration_idea TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'pending', visibility TEXT NOT NULL DEFAULT 'private',
  created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL, deleted_at_utc TEXT,
  audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS connect_connections(
  connection_id TEXT PRIMARY KEY, user_low_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  user_high_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  source_request_id TEXT REFERENCES connect_connection_requests(request_id), state TEXT NOT NULL DEFAULT 'accepted',
  visibility TEXT NOT NULL DEFAULT 'private', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
  deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1,
  UNIQUE(user_low_id,user_high_id)
);
CREATE TABLE IF NOT EXISTS connect_user_blocks(
  block_id TEXT PRIMARY KEY, blocker_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  blocked_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE, reason TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT 'active', visibility TEXT NOT NULL DEFAULT 'private', created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL, deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}',
  version INTEGER NOT NULL DEFAULT 1, UNIQUE(blocker_id,blocked_id)
);
CREATE TABLE IF NOT EXISTS connect_user_mutes(
  mute_id TEXT PRIMARY KEY, muter_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  muted_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE, state TEXT NOT NULL DEFAULT 'active',
  visibility TEXT NOT NULL DEFAULT 'private', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
  deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1,
  UNIQUE(muter_id,muted_id)
);
CREATE TABLE IF NOT EXISTS connect_upload_sessions(
  upload_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  original_name TEXT NOT NULL, safe_extension TEXT NOT NULL, declared_mime TEXT NOT NULL,
  expected_bytes INTEGER NOT NULL, received_bytes INTEGER NOT NULL DEFAULT 0, expected_sha256 TEXT NOT NULL DEFAULT '',
  temporary_path TEXT NOT NULL, scan_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'uploading',
  visibility TEXT NOT NULL DEFAULT 'private', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
  deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS connect_media_objects(
  media_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  original_name TEXT NOT NULL, storage_path TEXT NOT NULL UNIQUE, mime_type TEXT NOT NULL, size_bytes INTEGER NOT NULL,
  sha256 TEXT NOT NULL, media_kind TEXT NOT NULL, thumbnail_path TEXT, scan_json TEXT NOT NULL DEFAULT '{}',
  state TEXT NOT NULL DEFAULT 'available', visibility TEXT NOT NULL DEFAULT 'private', created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL, deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}',
  version INTEGER NOT NULL DEFAULT 1, UNIQUE(owner_id,sha256)
);
CREATE TABLE IF NOT EXISTS connect_posts(
  post_id TEXT PRIMARY KEY, author_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  post_type TEXT NOT NULL DEFAULT 'text', title TEXT NOT NULL DEFAULT '', body TEXT NOT NULL,
  visibility TEXT NOT NULL DEFAULT 'public', community_id TEXT, project_id TEXT, institution TEXT NOT NULL DEFAULT '',
  comment_permission TEXT NOT NULL DEFAULT 'everyone', download_permission TEXT NOT NULL DEFAULT 'ask',
  collaboration_enabled INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'published',
  created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL, deleted_at_utc TEXT,
  audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS connect_post_revisions(
  revision_id TEXT PRIMARY KEY, post_id TEXT NOT NULL REFERENCES connect_posts(post_id) ON DELETE CASCADE,
  editor_id TEXT NOT NULL REFERENCES connect_users(user_id), title TEXT NOT NULL, body TEXT NOT NULL,
  version INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'preserved', visibility TEXT NOT NULL DEFAULT 'private',
  created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL, deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS connect_post_attachments(
  attachment_id TEXT PRIMARY KEY, post_id TEXT NOT NULL REFERENCES connect_posts(post_id) ON DELETE CASCADE,
  media_id TEXT NOT NULL REFERENCES connect_media_objects(media_id), position INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'active', visibility TEXT NOT NULL DEFAULT 'inherit', created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL, deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}',
  version INTEGER NOT NULL DEFAULT 1, UNIQUE(post_id,media_id)
);
CREATE TABLE IF NOT EXISTS connect_hashtags(
  hashtag_id TEXT PRIMARY KEY, normalized_tag TEXT NOT NULL UNIQUE, display_tag TEXT NOT NULL, created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS connect_post_hashtags(
  post_id TEXT NOT NULL REFERENCES connect_posts(post_id) ON DELETE CASCADE,
  hashtag_id TEXT NOT NULL REFERENCES connect_hashtags(hashtag_id) ON DELETE CASCADE, PRIMARY KEY(post_id,hashtag_id)
);
CREATE TABLE IF NOT EXISTS connect_mentions(
  mention_id TEXT PRIMARY KEY, source_type TEXT NOT NULL, source_id TEXT NOT NULL,
  mentioned_user_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  creator_id TEXT NOT NULL REFERENCES connect_users(user_id), state TEXT NOT NULL DEFAULT 'active',
  visibility TEXT NOT NULL DEFAULT 'inherit', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
  deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS connect_comments(
  comment_id TEXT PRIMARY KEY, post_id TEXT NOT NULL REFERENCES connect_posts(post_id) ON DELETE CASCADE,
  author_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  parent_comment_id TEXT REFERENCES connect_comments(comment_id) ON DELETE CASCADE, body TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'published', visibility TEXT NOT NULL DEFAULT 'inherit', pinned INTEGER NOT NULL DEFAULT 0,
  created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL, deleted_at_utc TEXT,
  audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS connect_comment_revisions(
  revision_id TEXT PRIMARY KEY, comment_id TEXT NOT NULL REFERENCES connect_comments(comment_id) ON DELETE CASCADE,
  editor_id TEXT NOT NULL REFERENCES connect_users(user_id), body TEXT NOT NULL, version INTEGER NOT NULL,
  state TEXT NOT NULL DEFAULT 'preserved', visibility TEXT NOT NULL DEFAULT 'private', created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL, deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS connect_reactions(
  reaction_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  target_type TEXT NOT NULL, target_id TEXT NOT NULL, reaction_type TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active',
  visibility TEXT NOT NULL DEFAULT 'public', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
  deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1,
  UNIQUE(user_id,target_type,target_id)
);
CREATE TABLE IF NOT EXISTS connect_bookmarks(
  bookmark_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  post_id TEXT NOT NULL REFERENCES connect_posts(post_id) ON DELETE CASCADE, state TEXT NOT NULL DEFAULT 'active',
  visibility TEXT NOT NULL DEFAULT 'private', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
  deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1,
  UNIQUE(user_id,post_id)
);
CREATE TABLE IF NOT EXISTS connect_reposts(
  repost_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  original_post_id TEXT NOT NULL REFERENCES connect_posts(post_id) ON DELETE CASCADE,
  quote_post_id TEXT REFERENCES connect_posts(post_id) ON DELETE SET NULL, state TEXT NOT NULL DEFAULT 'active',
  visibility TEXT NOT NULL DEFAULT 'public', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
  deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1,
  UNIQUE(user_id,original_post_id)
);
CREATE TABLE IF NOT EXISTS connect_notifications(
  notification_id TEXT PRIMARY KEY, recipient_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  actor_id TEXT REFERENCES connect_users(user_id) ON DELETE SET NULL, notification_type TEXT NOT NULL,
  subject_type TEXT NOT NULL DEFAULT '', subject_id TEXT NOT NULL DEFAULT '', message TEXT NOT NULL, read_at_utc TEXT,
  state TEXT NOT NULL DEFAULT 'active', visibility TEXT NOT NULL DEFAULT 'private', created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL, deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS connect_content_reports(
  report_id TEXT PRIMARY KEY, reporter_id TEXT NOT NULL REFERENCES connect_users(user_id) ON DELETE CASCADE,
  target_type TEXT NOT NULL, target_id TEXT NOT NULL, reason TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
  evidence_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'submitted', visibility TEXT NOT NULL DEFAULT 'moderators',
  created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL, deleted_at_utc TEXT,
  audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS connect_moderation_cases(
  case_id TEXT PRIMARY KEY, report_id TEXT NOT NULL REFERENCES connect_content_reports(report_id),
  assigned_moderator_id TEXT REFERENCES connect_users(user_id), action TEXT NOT NULL DEFAULT '',
  appeal_status TEXT NOT NULL DEFAULT '', resolution TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'open',
  visibility TEXT NOT NULL DEFAULT 'moderators', created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
  deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS connect_audit_events(
  event_id TEXT PRIMARY KEY, actor_id TEXT REFERENCES connect_users(user_id) ON DELETE SET NULL,
  event_type TEXT NOT NULL, subject_type TEXT NOT NULL, subject_id TEXT NOT NULL, detail_json TEXT NOT NULL DEFAULT '{}',
  state TEXT NOT NULL DEFAULT 'recorded', visibility TEXT NOT NULL DEFAULT 'administrators', created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL, deleted_at_utc TEXT, audit_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_connect_profiles_discovery ON connect_profiles(state,visibility,country,institution,updated_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_connect_follows_target ON connect_follows(target_type,target_id,state,created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_connect_connection_requests_recipient ON connect_connection_requests(recipient_id,state,created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_connect_connections_pair ON connect_connections(user_low_id,user_high_id,state);
CREATE INDEX IF NOT EXISTS idx_connect_posts_feed ON connect_posts(state,created_at_utc DESC,post_id DESC);
CREATE INDEX IF NOT EXISTS idx_connect_posts_author ON connect_posts(author_id,state,created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_connect_comments_post ON connect_comments(post_id,state,created_at_utc ASC);
CREATE INDEX IF NOT EXISTS idx_connect_reactions_target ON connect_reactions(target_type,target_id,state);
CREATE INDEX IF NOT EXISTS idx_connect_notifications_recipient ON connect_notifications(recipient_id,state,read_at_utc,created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_connect_reports_state ON connect_content_reports(state,created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_connect_media_owner_sha ON connect_media_objects(owner_id,sha256,state);
"""

ROLLBACK_TABLES = (
  "connect_audit_events","connect_moderation_cases","connect_content_reports","connect_notifications",
  "connect_reposts","connect_bookmarks","connect_reactions","connect_comment_revisions","connect_comments",
  "connect_mentions","connect_post_hashtags","connect_hashtags","connect_post_attachments","connect_post_revisions",
  "connect_posts","connect_media_objects","connect_upload_sessions","connect_user_mutes","connect_user_blocks",
  "connect_connections","connect_connection_requests","connect_follows","connect_privacy_preferences",
  "connect_profiles","connect_users"
)


def connect_database_path(project_root: str | Path | None = None) -> Path:
    configured = os.environ.get("BIOINTEL_CONNECT_DATABASE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[3]
    return root / "UserData" / "connect" / "connect.sqlite3"


class ConnectDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()

    def migrate(self) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=30000;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        with transaction(self.path) as connection:
            connection.executescript(SCHEMA_SQL)
            connection.execute(
                "INSERT OR IGNORE INTO connect_schema_migrations(migration_id,applied_at_utc) VALUES(?,?)",
                (BASE_MIGRATION_ID, utc_now()),
            )
            connection.executescript(EXTENDED_SCHEMA_SQL)
            connection.execute(
                "INSERT OR IGNORE INTO connect_schema_migrations(migration_id,applied_at_utc) VALUES(?,?)",
                (MIGRATION_ID, utc_now()),
            )
        return MIGRATION_ID

    def rollback(self, migration_id: str = MIGRATION_ID) -> None:
        if migration_id not in {MIGRATION_ID, BASE_MIGRATION_ID}:
            raise ValueError(f"Unknown Connect migration: {migration_id}")
        with transaction(self.path) as connection:
            for table in COMPLETE_ROLLBACK_TABLES:
                connection.execute(f'DROP TABLE IF EXISTS "{table}"')
            for table in ROLLBACK_TABLES:
                connection.execute(f'DROP TABLE IF EXISTS "{table}"')
            connection.execute(
                "DELETE FROM connect_schema_migrations WHERE migration_id IN (?,?)",
                (BASE_MIGRATION_ID, MIGRATION_ID),
            )

    def connection(self, *, read_only: bool = False):
        return connect(self.path, read_only=read_only)

    def migration_status(self) -> dict[str, object]:
        if not self.path.is_file():
            return {"database": str(self.path), "applied": [], "current": False}
        with self.connection(read_only=True) as connection:
            rows = connection.execute(
                "SELECT migration_id,applied_at_utc FROM connect_schema_migrations ORDER BY applied_at_utc"
            ).fetchall()
        applied = [dict(row) for row in rows]
        return {"database": str(self.path), "applied": applied,
                "current": any(row["migration_id"] == MIGRATION_ID for row in applied)}


