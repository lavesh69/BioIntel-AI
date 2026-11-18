import os
import sqlite3
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

def get_science_pulse_db_path(root_dir: Optional[str] = None) -> str:
    if root_dir is None:
        root_dir = os.getcwd()
    user_data = os.path.join(root_dir, "UserData", "databases")
    os.makedirs(user_data, exist_ok=True)
    return os.path.join(user_data, "biointel_science_pulse.sqlite")

def init_science_pulse_db(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pulse_articles (
        article_id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        doi_pmid TEXT,
        title TEXT NOT NULL,
        authors TEXT,
        abstract TEXT,
        journal TEXT,
        pub_date TEXT,
        licence TEXT,
        url TEXT,
        retracted INTEGER DEFAULT 0,
        saved INTEGER DEFAULT 0,
        tags JSON,
        ingested_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pulse_alerts (
        alert_id TEXT PRIMARY KEY,
        query TEXT NOT NULL,
        frequency TEXT DEFAULT 'daily',
        enabled INTEGER DEFAULT 1,
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()

class SciencePulseService:
    def __init__(self, root_dir: Optional[str] = None):
        self.db_path = get_science_pulse_db_path(root_dir)
        init_science_pulse_db(self.db_path)

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def add_article(self, article: Dict[str, Any]) -> str:
        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        art_id = article.get("article_id") or f"art_{int(datetime.now().timestamp()*1000)}"
        cur.execute("""
            INSERT INTO pulse_articles (article_id, source, doi_pmid, title, authors, abstract, journal, pub_date, licence, url, retracted, saved, tags, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(article_id) DO UPDATE SET title=excluded.title, abstract=excluded.abstract
        """, (
            art_id, article.get("source", "PubMed"), article.get("doi_pmid", ""),
            article.get("title", ""), article.get("authors", ""), article.get("abstract", ""),
            article.get("journal", ""), article.get("pub_date", ""), article.get("licence", "CC-BY"),
            article.get("url", ""), 1 if article.get("retracted") else 0, 1 if article.get("saved") else 0,
            json.dumps(article.get("tags", [])), now
        ))
        conn.commit()
        conn.close()
        return art_id

    def list_articles(self, saved_only: bool = False, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.cursor()
        query = "SELECT article_id, source, doi_pmid, title, authors, abstract, journal, pub_date, licence, url, retracted, saved, tags, ingested_at FROM pulse_articles"
        if saved_only:
            query += " WHERE saved = 1"
        query += " ORDER BY ingested_at DESC LIMIT ?"
        cur.execute(query, (limit,))
        rows = cur.fetchall()
        conn.close()
        return [{
            "article_id": r[0], "source": r[1], "doi_pmid": r[2], "title": r[3], "authors": r[4],
            "abstract": r[5], "journal": r[6], "pub_date": r[7], "licence": r[8], "url": r[9],
            "retracted": bool(r[10]), "saved": bool(r[11]), "tags": json.loads(r[12]) if r[12] else [], "ingested_at": r[13]
        } for r in rows]

    def toggle_save_article(self, article_id: str) -> bool:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE pulse_articles SET saved = CASE WHEN saved = 1 THEN 0 ELSE 1 END WHERE article_id = ?", (article_id,))
        conn.commit()
        conn.close()
        return True


# Backward-compatible facade over the canonical normalized Science Pulse store.
# The legacy class above remains readable for migration archaeology; all imports
# resolve to this facade so new writes no longer create a disconnected database.
class CanonicalSciencePulseService:
    def __init__(self, root_dir: Optional[str] = None):
        from biointel.science_pulse.service import SciencePulseService as CanonicalService

        self.root_dir = root_dir or os.getcwd()
        self._service = CanonicalService(self.root_dir)
        self.db_path = str(self._service.store.path)

    def add_article(self, article: Dict[str, Any]) -> str:
        from biointel.science_pulse.models import PulseRecord
        from biointel.science_pulse.taxonomy import classify

        article_id = str(article.get("article_id") or f"art_{int(datetime.now().timestamp()*1000)}")
        identifier = str(article.get("doi_pmid") or "").strip()
        doi = identifier.removeprefix("DOI:").strip() if "10." in identifier else ""
        pmid = identifier.removeprefix("PMID:").strip() if "PMID" in identifier.upper() else ""
        record = classify(
            PulseRecord(
                provider_key="legacy_local", external_id=article_id,
                title=str(article.get("title") or ""), canonical_url=str(article.get("url") or ""),
                source_name=str(article.get("source") or "Local import"), doi=doi, pmid=pmid,
                abstract=str(article.get("abstract") or ""), authors=[str(article.get("authors") or "")],
                journal=str(article.get("journal") or ""), published_at=str(article.get("pub_date") or ""),
                license_note=str(article.get("licence") or ""),
                trust_state="retracted" if article.get("retracted") else "normal",
                categories=list(article.get("tags") or []),
                live_state="DEMO" if article.get("is_demo", True) else "LOCAL",
                provenance={"import": "legacy_education_facade", "original_article_id": article_id},
            )
        )
        item_id, _ = self._service.store.upsert_item(record)
        if article.get("saved"):
            self._service.store.toggle_bookmark("legacy-user", item_id)
        return article_id

    def list_articles(self, saved_only: bool = False, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self._service.store.search_items(saved_by="legacy-user" if saved_only else "", limit=limit)
        return [{
            "article_id": row["external_id"], "item_id": row["item_id"],
            "source": row.get("source_name") or row.get("provider_key"),
            "doi_pmid": row.get("doi") or row.get("pmid") or "", "title": row["title"],
            "authors": ", ".join(row.get("authors") or []), "abstract": row.get("abstract") or "",
            "journal": row.get("journal") or "", "pub_date": row.get("published_at") or "",
            "licence": row.get("license_note") or "", "url": row.get("canonical_url") or "",
            "retracted": row.get("trust_state") == "retracted", "saved": False,
            "tags": row.get("categories") or [], "ingested_at": row.get("first_seen_at") or "",
        } for row in rows]

    def toggle_save_article(self, article_id: str) -> bool:
        rows = self._service.store.search_items(limit=500)
        match = next((row for row in rows if row["external_id"] == article_id or row["item_id"] == article_id), None)
        return bool(match and self._service.store.toggle_bookmark("legacy-user", match["item_id"]))


SciencePulseService = CanonicalSciencePulseService
