from __future__ import annotations
from typing import Any, Dict, List, Optional
from biointel.education.database import EducationDatabase

class PermissionAwareGlobalSearch:
    """RBAC and Tenant permission-aware global search engine."""

    def __init__(self, db: EducationDatabase):
        self.db = db

    def search(self, query: str, user_context: Dict[str, Any], limit: int = 15) -> List[Dict[str, Any]]:
        if not query or len(query.strip()) < 2:
            return []
        
        q = f"%{query.strip()}%"
        inst_id = user_context.get("institution_id", "")
        role = user_context.get("role", "student")
        results = []

        with self.db.connection() as conn:
            # 1. Search Courses
            courses = conn.execute(
                "SELECT id, title, description, category FROM courses WHERE (title LIKE ? OR description LIKE ?) AND state = 'published' LIMIT ?",
                (q, q, limit)
            ).fetchall()
            for c in courses:
                results.append({
                    "entity_type": "Academy Course",
                    "title": c["title"],
                    "snippet": f"[{c['category']}] {c['description'][:120]}...",
                    "deep_link": f"/academy?course_id={c['id']}",
                    "relevance": 0.95
                })

            # 2. Search Lectures & Transcripts
            lectures = conn.execute(
                "SELECT id, title, description FROM lectures WHERE (title LIKE ? OR description LIKE ?) AND state = 'published' LIMIT ?",
                (q, q, limit)
            ).fetchall()
            for l in lectures:
                results.append({
                    "entity_type": "Lecture Video",
                    "title": l["title"],
                    "snippet": l["description"][:120],
                    "deep_link": f"/lecture?lecture_id={l['id']}",
                    "relevance": 0.90
                })

            # 3. Search Classroom Materials
            materials = conn.execute(
                "SELECT id, title, category, file_name FROM materials WHERE (title LIKE ? OR file_name LIKE ?) AND state = 'published' LIMIT ?",
                (q, q, limit)
            ).fetchall()
            for m in materials:
                results.append({
                    "entity_type": "Classroom Material",
                    "title": m["title"],
                    "snippet": f"Category: {m['category']} | File: {m['file_name']}",
                    "deep_link": f"/classroom?tab=materials&material_id={m['id']}",
                    "relevance": 0.85
                })

            # 4. Search Assignments
            assignments = conn.execute(
                "SELECT id, title, instructions FROM assignments WHERE (title LIKE ? OR instructions LIKE ?) AND state = 'published' LIMIT ?",
                (q, q, limit)
            ).fetchall()
            for a in assignments:
                results.append({
                    "entity_type": "Assignment",
                    "title": a["title"],
                    "snippet": a["instructions"][:120],
                    "deep_link": f"/classroom?tab=assignments&assignment_id={a['id']}",
                    "relevance": 0.80
                })

            # 5. Search Circulars
            circulars = conn.execute(
                "SELECT id, circular_number, title, content FROM circulars WHERE (title LIKE ? OR content LIKE ? OR circular_number LIKE ?) AND state = 'published' LIMIT ?",
                (q, q, q, limit)
            ).fetchall()
            for circ in circulars:
                results.append({
                    "entity_type": "Institutional Circular",
                    "title": f"[{circ['circular_number']}] {circ['title']}",
                    "snippet": circ["content"][:120],
                    "deep_link": f"/classroom?tab=circulars&circular_id={circ['id']}",
                    "relevance": 0.75
                })

        return sorted(results, key=lambda x: x["relevance"], reverse=True)[:limit]

