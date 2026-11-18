import os
import sqlite3
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

def get_connect_db_path(root_dir: Optional[str] = None) -> str:
    if root_dir is None:
        root_dir = os.getcwd()
    configured = os.environ.get("BIOINTEL_USER_DATA_DIR", "").strip()
    user_data = os.path.join(configured or os.path.join(root_dir, "UserData"), "databases")
    os.makedirs(user_data, exist_ok=True)
    return os.path.join(user_data, "biointel_connect.sqlite")

def init_connect_db(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS connect_profiles (
        user_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        headline TEXT,
        institution TEXT,
        lab TEXT,
        bio TEXT,
        avatar_url TEXT,
        cover_url TEXT,
        orcid TEXT,
        skills JSON,
        interests JSON,
        publications JSON,
        datasets JSON,
        followers_count INTEGER DEFAULT 0,
        following_count INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS connect_posts (
        post_id TEXT PRIMARY KEY,
        author_id TEXT NOT NULL,
        author_name TEXT NOT NULL,
        post_type TEXT NOT NULL,
        content TEXT NOT NULL,
        media_urls JSON,
        metadata JSON,
        likes_count INTEGER DEFAULT 0,
        reposts_count INTEGER DEFAULT 0,
        comments_count INTEGER DEFAULT 0,
        created_at TEXT,
        FOREIGN KEY(author_id) REFERENCES connect_profiles(user_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS connect_messages (
        message_id TEXT PRIMARY KEY,
        sender_id TEXT NOT NULL,
        receiver_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        content TEXT NOT NULL,
        attachments JSON,
        read_status INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS connect_communities (
        community_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        category TEXT,
        member_count INTEGER DEFAULT 1,
        created_by TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS connect_audit_log (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        action TEXT NOT NULL,
        details JSON,
        timestamp TEXT
    )
    """)

    conn.commit()
    conn.close()

class ConnectService:
    def __init__(self, root_dir: Optional[str] = None):
        self.db_path = get_connect_db_path(root_dir)
        init_connect_db(self.db_path)

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def create_or_update_profile(self, user_id: str, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cur.execute("""
            INSERT INTO connect_profiles (user_id, name, headline, institution, lab, bio, avatar_url, cover_url, orcid, skills, interests, publications, datasets, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name=excluded.name,
                headline=excluded.headline,
                institution=excluded.institution,
                lab=excluded.lab,
                bio=excluded.bio,
                avatar_url=excluded.avatar_url,
                cover_url=excluded.cover_url,
                orcid=excluded.orcid,
                skills=excluded.skills,
                interests=excluded.interests,
                publications=excluded.publications,
                datasets=excluded.datasets
        """, (
            user_id,
            profile_data.get("name", "Dr. BioIntel User"),
            profile_data.get("headline", "Principal Investigator & Bioinformatician"),
            profile_data.get("institution", "BioIntel Research Institute"),
            profile_data.get("lab", "Omics & Systems Biology Lab"),
            profile_data.get("bio", "Exploring spatial genomics, deep learning and AI-assisted drug discovery."),
            profile_data.get("avatar_url", ""),
            profile_data.get("cover_url", ""),
            profile_data.get("orcid", "0000-0002-1825-0097"),
            json.dumps(profile_data.get("skills", ["BioIntel Sequence Intelligence", "Spatial Omics", "BioIntel Predictive Computing"])),
            json.dumps(profile_data.get("interests", ["Single-cell RNA-seq", "CRISPR screens"])),
            json.dumps(profile_data.get("publications", [])),
            json.dumps(profile_data.get("datasets", [])),
            now
        ))
        conn.commit()
        conn.close()
        return self.get_profile(user_id)

    def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT user_id, name, headline, institution, lab, bio, avatar_url, cover_url, orcid, skills, interests, publications, datasets, followers_count, following_count, created_at FROM connect_profiles WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "user_id": row[0],
            "name": row[1],
            "headline": row[2],
            "institution": row[3],
            "lab": row[4],
            "bio": row[5],
            "avatar_url": row[6],
            "cover_url": row[7],
            "orcid": row[8],
            "skills": json.loads(row[9]) if row[9] else [],
            "interests": json.loads(row[10]) if row[10] else [],
            "publications": json.loads(row[11]) if row[11] else [],
            "datasets": json.loads(row[12]) if row[12] else [],
            "followers_count": row[13],
            "following_count": row[14],
            "created_at": row[15]
        }

    def create_post(self, author_id: str, author_name: str, post_type: str, content: str, media_urls: List[str] = None, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        post_id = f"post_{int(datetime.now().timestamp()*1000)}"
        cur.execute("""
            INSERT INTO connect_posts (post_id, author_id, author_name, post_type, content, media_urls, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            post_id,
            author_id,
            author_name,
            post_type,
            content,
            json.dumps(media_urls or []),
            json.dumps(metadata or {}),
            now
        ))
        conn.commit()
        conn.close()
        return {"post_id": post_id, "author_id": author_id, "author_name": author_name, "post_type": post_type, "content": content, "created_at": now}

    def get_feed(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT post_id, author_id, author_name, post_type, content, media_urls, metadata, likes_count, reposts_count, comments_count, created_at FROM connect_posts ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        conn.close()
        feed = []
        for r in rows:
            feed.append({
                "post_id": r[0],
                "author_id": r[1],
                "author_name": r[2],
                "post_type": r[3],
                "content": r[4],
                "media_urls": json.loads(r[5]) if r[5] else [],
                "metadata": json.loads(r[6]) if r[6] else {},
                "likes_count": r[7],
                "reposts_count": r[8],
                "comments_count": r[9],
                "created_at": r[10]
            })
        return feed

    def send_message(self, sender_id: str, receiver_id: str, content: str, attachments: List[str] = None) -> Dict[str, Any]:
        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        msg_id = f"msg_{int(datetime.now().timestamp()*1000)}"
        conv_id = "_".join(sorted([sender_id, receiver_id]))
        cur.execute("""
            INSERT INTO connect_messages (message_id, sender_id, receiver_id, conversation_id, content, attachments, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (msg_id, sender_id, receiver_id, conv_id, content, json.dumps(attachments or []), now))
        conn.commit()
        conn.close()
        return {"message_id": msg_id, "conversation_id": conv_id, "sender_id": sender_id, "receiver_id": receiver_id, "content": content, "created_at": now}

    def get_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT message_id, sender_id, receiver_id, content, attachments, read_status, created_at FROM connect_messages WHERE conversation_id = ? ORDER BY created_at ASC", (conversation_id,))
        rows = cur.fetchall()
        conn.close()
        messages = []
        for r in rows:
            messages.append({
                "message_id": r[0],
                "sender_id": r[1],
                "receiver_id": r[2],
                "content": r[3],
                "attachments": json.loads(r[4]) if r[4] else [],
                "read_status": r[5],
                "created_at": r[6]
            })
        return messages
