from __future__ import annotations

from biointel.runtime_paths import runtime_reports_directory

import html
import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from docx import Document
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class LocalCopilot:
    """Bounded, evidence-retrieval-only assistant over local project documentation."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()

    def _documents(self, max_documents: int = 500, max_chars_each: int = 100_000) -> list[dict[str, str]]:
        candidates: list[dict[str, str]] = []
        for folder in [self.project_root / "docs", runtime_reports_directory(self.project_root), self.project_root]:
            if not folder.exists():
                continue
            for path in folder.rglob("*"):
                if len(candidates) >= max_documents:
                    break
                if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".json"}:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")[:max_chars_each]
                    if text.strip():
                        candidates.append({"source": str(path.relative_to(self.project_root)), "text": text})
                except (OSError, UnicodeError):
                    continue
        return candidates

    @staticmethod
    def _blocked(question: str) -> str | None:
        q = question.lower()
        clinical = [
            "diagnose me",
            "what dose",
            "change my dose",
            "should i stop",
            "treat my",
            "prescribe",
            "medical emergency",
        ]
        if any(token in q for token in clinical):
            return (
                "This offline research copilot cannot provide diagnosis, treatment, prescribing "
                "or dose instructions. Use a qualified healthcare professional and validated clinical systems."
            )
        return None

    def answer(self, question: str, *, top_k: int = 5) -> dict[str, Any]:
        blocked = self._blocked(question)
        if blocked:
            return {"blocked": True, "answer": blocked, "sources": [], "uncertainty": "high"}
        docs = self._documents()
        if not docs:
            return {
                "blocked": False,
                "answer": "No approved local documentation was available for retrieval.",
                "sources": [],
                "uncertainty": "high",
            }
        corpus = [document["text"] for document in docs] + [question]
        matrix = TfidfVectorizer(
            stop_words="english", max_features=25_000, ngram_range=(1, 2)
        ).fit_transform(corpus)
        scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
        order = np.argsort(scores)[::-1][: max(1, min(int(top_k), 20))]
        sources: list[dict[str, Any]] = []
        snippets: list[str] = []
        terms = [term for term in re.findall(r"[A-Za-z0-9_-]{4,}", question.lower())][:12]
        for idx in order:
            if scores[idx] <= 0:
                continue
            text = docs[idx]["text"].replace("\r", "")
            lower = text.lower()
            positions = [lower.find(term) for term in terms if lower.find(term) >= 0]
            start = max(0, (min(positions) if positions else 0) - 180)
            snippet = re.sub(r"\s+", " ", text[start : start + 800]).strip()
            sources.append(
                {"source": docs[idx]["source"], "score": float(scores[idx]), "snippet": snippet}
            )
            snippets.append(f"[{len(sources)}] {snippet}")
        if not sources:
            return {
                "blocked": False,
                "answer": "The local knowledge base did not contain enough matching evidence.",
                "sources": [],
                "uncertainty": "high",
            }
        answer = (
            "Local evidence indicates the following:\n\n"
            + "\n\n".join(snippets[:3])
            + "\n\nReview the cited local sources before using this draft."
        )
        uncertainty = "medium" if sources[0]["score"] < 0.35 else "low-to-medium"
        return {"blocked": False, "answer": answer, "sources": sources, "uncertainty": uncertainty}


def build_report_bundle(
    title: str, sections: list[dict[str, Any]], manifest: dict[str, Any]
) -> dict[str, bytes]:
    """Create equivalent bounded HTML, DOCX, PDF and manifest report artifacts."""
    title = title.strip() or "BioIntel AI Scientific Report"
    generated = _utc_now()
    html_sections = []
    for section in sections:
        heading = html.escape(str(section.get("heading", "Section")))
        body = html.escape(str(section.get("body", ""))).replace("\n", "<br>")
        html_sections.append(f"<section><h2>{heading}</h2><p>{body}</p></section>")
    manifest_text = json.dumps(manifest, indent=2, default=str)
    html_doc = (
        "<!doctype html><html><head><meta charset='utf-8'><title>"
        f"{html.escape(title)}</title><style>body{{font-family:Segoe UI,Arial,sans-serif;"
        "max-width:980px;margin:auto;padding:40px;color:#182033}}h1{font-size:38px}"
        "section{border:1px solid #dbe3ef;border-radius:14px;padding:20px;margin:16px 0}"
        "p{line-height:1.65}footer{color:#64748b;margin-top:30px}</style></head><body>"
        f"<h1>{html.escape(title)}</h1><p>Generated {html.escape(generated)}</p>"
        f"{''.join(html_sections)}<section><h2>Evidence manifest</h2><pre>"
        f"{html.escape(manifest_text)}</pre></section><footer>Research use only. "
        "Human scientific review is required.</footer></body></html>"
    ).encode("utf-8")

    document = Document()
    document.add_heading(title, 0)
    document.add_paragraph(f"Generated {generated}")
    for section in sections:
        document.add_heading(str(section.get("heading", "Section")), level=1)
        document.add_paragraph(str(section.get("body", "")))
    document.add_heading("Evidence manifest", level=1)
    document.add_paragraph(manifest_text)
    docx_buffer = io.BytesIO()
    document.save(docx_buffer)

    pdf_buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    story = [
        Paragraph(html.escape(title), styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"Generated {generated}", styles["Normal"]),
        Spacer(1, 12),
    ]
    for section in sections:
        story.extend(
            [
                Paragraph(html.escape(str(section.get("heading", "Section"))), styles["Heading2"]),
                Paragraph(
                    html.escape(str(section.get("body", ""))).replace("\n", "<br/>"),
                    styles["BodyText"],
                ),
                Spacer(1, 10),
            ]
        )
    manifest_rows = [["Field", "Value"]] + [
        [str(key), json.dumps(value, default=str)[:500]] for key, value in manifest.items()
    ]
    table = Table(manifest_rows, colWidths=[120, 380])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#94A3B8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(table)
    SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=42,
        bottomMargin=42,
    ).build(story)
    return {
        "html": html_doc,
        "docx": docx_buffer.getvalue(),
        "pdf": pdf_buffer.getvalue(),
        "manifest": manifest_text.encode("utf-8"),
    }
