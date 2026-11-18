from __future__ import annotations

import io
import json
import math
from pathlib import Path
import re
from dataclasses import dataclass
from typing import Any


MAX_DOCUMENT_BYTES = 20 * 1024 * 1024


class DocumentExtractionError(ValueError):
    """Safe document validation or extraction error for the UI."""


@dataclass(frozen=True)
class RAGChunk:
    chunk_id: str
    source_name: str
    page_number: int
    content: str
    section: str = ""


@dataclass(frozen=True)
class RAGSearchResult:
    query: str
    chunks: tuple[RAGChunk, ...]
    answer: str
    scores: tuple[float, ...]
    evidence_found: bool = False
    synthesis: str = "Not generated"


class PDFRAGService:
    """Local retrieval index with real PDF/TXT/Markdown/notebook extraction."""

    def __init__(self, *, max_document_bytes: int = MAX_DOCUMENT_BYTES) -> None:
        self.chunks: list[RAGChunk] = []
        self.max_document_bytes = int(max_document_bytes)
        self.last_warnings: list[str] = []

    def index_bytes(self, content: bytes, filename: str) -> list[RAGChunk]:
        suffix = Path(filename).suffix.casefold()
        if len(content) > self.max_document_bytes:
            raise DocumentExtractionError(
                f"{filename} exceeds the {self.max_document_bytes // (1024 * 1024)} MB upload limit."
            )
        if suffix == ".pdf":
            return self.extract_text_from_pdf_bytes(content, filename)
        if suffix in {".txt", ".md"}:
            return self._index_text(self._decode_text(content, filename), filename, 1)
        if suffix == ".ipynb":
            return self._index_notebook(content, filename)
        raise DocumentExtractionError("Supported files are PDF, TXT, Markdown, and Jupyter notebooks.")

    def extract_text_from_pdf_bytes(self, pdf_bytes: bytes, filename: str = "document.pdf") -> list[RAGChunk]:
        self.last_warnings = []
        if len(pdf_bytes) > self.max_document_bytes:
            raise DocumentExtractionError("PDF exceeds the configured file-size limit.")
        if not pdf_bytes.startswith(b"%PDF-"):
            raise DocumentExtractionError("The uploaded file is not a valid PDF document.")
        try:
            from pypdf import PdfReader
            from pypdf.errors import PdfReadError
        except ImportError as exc:
            raise DocumentExtractionError("PDF extraction is unavailable because pypdf is not installed.") from exc
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes), strict=True)
            if reader.is_encrypted:
                try:
                    unlocked = reader.decrypt("")
                except Exception:
                    unlocked = 0
                if not unlocked:
                    raise DocumentExtractionError("Encrypted PDF: provide an unlocked copy for indexing.")
            extracted: list[RAGChunk] = []
            image_only_pages: list[int] = []
            for page_number, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except Exception as exc:
                    self.last_warnings.append(f"Page {page_number} extraction failed: {type(exc).__name__}.")
                    continue
                if not text.strip():
                    image_only_pages.append(page_number)
                    continue
                extracted.extend(self._chunks_from_text(text, filename, page_number))
            if image_only_pages:
                listed = ", ".join(map(str, image_only_pages[:12]))
                self.last_warnings.append(
                    f"No extractable text on page(s) {listed}. OCR or image extraction is required and is not configured."
                )
            if not extracted:
                self.last_warnings.append("No extractable PDF text found. OCR is required and unavailable.")
            self._replace_source(filename, extracted)
            return extracted
        except DocumentExtractionError:
            raise
        except PdfReadError as exc:
            raise DocumentExtractionError("The PDF is damaged or could not be parsed.") from exc
        except (OSError, ValueError) as exc:
            raise DocumentExtractionError("The PDF could not be safely parsed.") from exc

    def _decode_text(self, content: bytes, filename: str) -> str:
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError(f"{filename} is not valid UTF-8 text.") from exc

    def _index_notebook(self, content: bytes, filename: str) -> list[RAGChunk]:
        try:
            notebook = json.loads(self._decode_text(content, filename))
        except json.JSONDecodeError as exc:
            raise DocumentExtractionError("The Jupyter notebook JSON is invalid.") from exc
        if not isinstance(notebook.get("cells"), list):
            raise DocumentExtractionError("The notebook has no valid cells array.")
        extracted: list[RAGChunk] = []
        for index, cell in enumerate(notebook["cells"], start=1):
            if not isinstance(cell, dict) or cell.get("cell_type") not in {"markdown", "code"}:
                continue
            source = cell.get("source", [])
            text = "".join(source) if isinstance(source, list) else str(source)
            if text.strip():
                extracted.extend(self._chunks_from_text(text, filename, index, section=f"Cell {index}"))
        self._replace_source(filename, extracted)
        return extracted

    def _index_text(self, text: str, filename: str, page: int) -> list[RAGChunk]:
        self.last_warnings = []
        extracted = self._chunks_from_text(text, filename, page)
        self._replace_source(filename, extracted)
        return extracted

    def _replace_source(self, filename: str, chunks: list[RAGChunk]) -> None:
        self.chunks = [chunk for chunk in self.chunks if chunk.source_name != filename]
        self.chunks.extend(chunks)

    @staticmethod
    def _chunks_from_text(
        text: str,
        filename: str,
        page_number: int,
        *,
        section: str = "",
        maximum: int = 1_000,
        overlap: int = 120,
    ) -> list[RAGChunk]:
        clean = re.sub(r"[ \t]+", " ", text.replace("\x00", " "))
        clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
        if not clean:
            return []
        chunks: list[RAGChunk] = []
        start = 0
        while start < len(clean):
            end = min(len(clean), start + maximum)
            if end < len(clean):
                boundary = max(clean.rfind("\n", start + maximum // 2, end), clean.rfind(". ", start + maximum // 2, end))
                if boundary > start:
                    end = boundary + 1
            value = clean[start:end].strip()
            if value:
                chunks.append(RAGChunk(
                    chunk_id=f"{Path(filename).name}:{page_number}:{len(chunks) + 1}",
                    source_name=Path(filename).name,
                    page_number=page_number,
                    content=value,
                    section=section,
                ))
            if end >= len(clean):
                break
            start = max(start + 1, end - overlap)
        return chunks

    @staticmethod
    def _score_chunk(query: str, chunk: RAGChunk) -> float:
        terms = set(re.findall(r"[A-Za-z0-9_'-]+", query.casefold()))
        words = re.findall(r"[A-Za-z0-9_'-]+", chunk.content.casefold())
        if not terms or not words:
            return 0.0
        matches = sum(1 for term in terms if term in words)
        return round(matches / math.sqrt(len(terms) * len(words)), 4)

    def query(self, query_text: str, top_k: int = 4) -> RAGSearchResult:
        query = " ".join(query_text.strip().split())
        if not query:
            return RAGSearchResult(query, (), "Enter a scientific question or search term.", ())
        if not self.chunks:
            return RAGSearchResult(query, (), "No documents are indexed.", ())
        scored = sorted(
            ((self._score_chunk(query, chunk), chunk) for chunk in self.chunks),
            key=lambda pair: pair[0],
            reverse=True,
        )
        matches = [(score, chunk) for score, chunk in scored[: max(1, top_k)] if score > 0]
        if not matches:
            return RAGSearchResult(
                query,
                (),
                "No supporting evidence was retrieved. No synthesis was generated.",
                (),
                evidence_found=False,
                synthesis="No-evidence state",
            )
        chunks = tuple(chunk for _, chunk in matches)
        scores = tuple(score for score, _ in matches)
        citations = "\n".join(
            f"- [{chunk.source_name}, page/cell {chunk.page_number}] {chunk.content[:240]}"
            for chunk in chunks
        )
        answer = (
            "### Retrieved source content\n\n"
            + citations
            + "\n\n### Model-generated synthesis\n\n"
            + "Not generated by the local retrieval-only mode. Review the cited excerpts directly."
        )
        return RAGSearchResult(
            query,
            chunks,
            answer,
            scores,
            evidence_found=True,
            synthesis="Not generated (retrieval-only mode)",
        )