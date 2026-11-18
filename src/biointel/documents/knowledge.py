from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

from pathlib import Path
from typing import Any

from biointel.documents.history import search_content
from biointel.documents.intelligence import answer_question, compare_extractions
from biointel.documents.service import load_processed_document


def ask_document_history(
    project_root: str | Path,
    question: str,
    *,
    run_ids: list[str] | None = None,
    maximum_documents: int = 10,
    maximum_citations: int = 5,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    history = runtime_database_path(root, "document_history.sqlite3")
    selected = list(run_ids or [])
    if not selected:
        hits = search_content(history, question, limit=maximum_documents * 3)
        selected = list(dict.fromkeys(str(hit["run_id"]) for hit in hits))[:maximum_documents]
    extractions = []
    errors = []
    for run_id in selected[:maximum_documents]:
        try:
            extractions.append(load_processed_document(root, run_id).extraction)
        except Exception as exc:
            errors.append({"run_id": run_id, "error": str(exc)})
    if not extractions:
        return {
            "question": question,
            "answer": "No indexed extraction could be loaded for this question.",
            "citations": [],
            "errors": errors,
            "method": "local_extract_query_v1",
        }
    result = answer_question(extractions, question, limit=maximum_citations)
    result["run_ids"] = selected
    result["errors"] = errors
    return result


def compare_document_runs(
    project_root: str | Path,
    left_run_id: str,
    right_run_id: str,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    left = load_processed_document(root, left_run_id).extraction
    right = load_processed_document(root, right_run_id).extraction
    result = compare_extractions(left, right)
    result["left_run_id"] = left_run_id
    result["right_run_id"] = right_run_id
    return result
