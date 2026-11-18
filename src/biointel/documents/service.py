from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import uuid4

from biointel.database.core import utc_now
from biointel.documents.exporters import export_all
from biointel.documents.extractor import extract_document
from biointel.documents.history import (
    DocumentOutput,
    add_event,
    add_output,
    complete_run,
    fail_run,
    find_duplicate_run,
    get_run,
    index_extraction,
    list_outputs,
    start_run,
)
from biointel.documents.intelligence import enrich_extraction
from biointel.documents.models import DocumentExtraction
from biointel.documents.security import DocumentSafetyPolicy, safe_filename, sha256_bytes
from biointel.runtime_paths import runtime_data_path, runtime_database_path


@dataclass(frozen=True)
class ProcessedDocument:
    run_id: str
    extraction: DocumentExtraction
    outputs: tuple[DocumentOutput, ...]
    output_directory: str
    source_saved_path: str | None
    reused_from_run_id: str | None = None

    def to_dict(self, *, include_extracted_rows: bool = False) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "extraction": self.extraction.to_dict(include_rows=include_extracted_rows),
            "outputs": [asdict(output) for output in self.outputs],
            "output_directory": self.output_directory,
            "source_saved_path": self.source_saved_path,
            "reused_from_run_id": self.reused_from_run_id,
        }


@dataclass(frozen=True)
class BatchDocumentResult:
    batch_id: str
    total: int
    completed: int
    failed: int
    processed: tuple[ProcessedDocument, ...]
    errors: tuple[dict[str, str], ...]

    def to_dict(self, *, include_extracted_rows: bool = False) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "processed": [
                item.to_dict(include_extracted_rows=include_extracted_rows)
                for item in self.processed
            ],
            "errors": list(self.errors),
        }


def resolve_document_path(project_root: str | Path, stored_path: str | Path) -> Path:
    path = Path(stored_path)
    return path if path.is_absolute() else Path(project_root).resolve() / path


def _load_extraction_json(
    outputs: Iterable[DocumentOutput], project_root: str | Path
) -> DocumentExtraction:
    json_output = next((item for item in outputs if item.format == "json"), None)
    if json_output is None:
        raise FileNotFoundError("Stored extraction JSON is unavailable.")
    path = resolve_document_path(project_root, json_output.path)
    if not path.is_file():
        raise FileNotFoundError("Stored extraction JSON is unavailable.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return DocumentExtraction.from_dict(payload)


def load_processed_document(project_root: str | Path, run_id: str) -> ProcessedDocument:
    root = Path(project_root).resolve()
    history = runtime_database_path(root, "document_history.sqlite3")
    run = get_run(history, run_id)
    outputs = tuple(list_outputs(history, run_id))
    extraction = _load_extraction_json(outputs, root)
    return ProcessedDocument(
        run_id=run_id,
        extraction=extraction,
        outputs=outputs,
        output_directory=run.output_directory or "",
        source_saved_path=run.source_saved_path,
    )


def process_document(
    filename: str,
    data: bytes,
    *,
    project_root: str | Path,
    password: str | None = None,
    keep_source: bool = False,
    max_rows_per_table: int = 50_000,
    max_columns: int = 256,
    allow_macro_workbooks: bool = False,
    allow_embedded_objects: bool = False,
    ocr_mode: str = "off",
    ocr_language: str = "eng",
    ocr_confidence_threshold: float = 70.0,
    redact_sensitive: bool = False,
    duplicate_policy: str = "warn",
    parent_run_id: str | None = None,
    tags: list[str] | None = None,
    project_code: str = "",
    notes: str = "",
) -> ProcessedDocument:
    if duplicate_policy not in {"warn", "force", "reuse"}:
        raise ValueError("duplicate_policy must be warn, force or reuse.")
    root = Path(project_root).resolve()
    history_path = runtime_database_path(root, "document_history.sqlite3")
    name = safe_filename(filename)
    extension = Path(name).suffix.lower().lstrip(".")
    source_hash = sha256_bytes(data)
    options = {
        "keep_source": bool(keep_source),
        "max_rows_per_table": int(max_rows_per_table),
        "max_columns": int(max_columns),
        "allow_macro_workbooks": bool(allow_macro_workbooks),
        "allow_embedded_objects": bool(allow_embedded_objects),
        "password_supplied": bool(password),
        "ocr_mode": ocr_mode,
        "ocr_language": ocr_language,
        "ocr_confidence_threshold": float(ocr_confidence_threshold),
        "redact_sensitive": bool(redact_sensitive),
    }
    duplicate = find_duplicate_run(history_path, source_hash, options=options)
    if duplicate and duplicate_policy == "reuse":
        existing = load_processed_document(root, duplicate.run_id)
        return ProcessedDocument(
            run_id=existing.run_id,
            extraction=existing.extraction,
            outputs=existing.outputs,
            output_directory=existing.output_directory,
            source_saved_path=existing.source_saved_path,
            reused_from_run_id=duplicate.run_id,
        )
    mime_hint = {
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "csv": "text/csv",
        "tsv": "text/tab-separated-values",
        "txt": "text/plain",
        "md": "text/markdown",
        "html": "text/html",
        "htm": "text/html",
        "json": "application/json",
        "xml": "application/xml",
        "yaml": "application/yaml",
        "yml": "application/yaml",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "odt": "application/vnd.oasis.opendocument.text",
        "ods": "application/vnd.oasis.opendocument.spreadsheet",
    }.get(extension, "application/octet-stream")
    run_id = start_run(
        history_path,
        source_name=name,
        file_type=extension,
        mime_type=mime_hint,
        source_sha256=source_hash,
        source_size_bytes=len(data),
        options=options,
        parent_run_id=parent_run_id,
        duplicate_of_run_id=duplicate.run_id if duplicate else None,
        tags=tags,
        project_code=project_code,
        notes=notes,
        engine_version="2.7.0",
    )
    output_directory = runtime_data_path(root, "document_extractions", run_id)
    output_directory.mkdir(parents=True, exist_ok=True)
    source_saved_path: str | None = None
    try:
        extraction = extract_document(
            name,
            data,
            password=password,
            max_rows_per_table=max_rows_per_table,
            max_columns=max_columns,
            policy=DocumentSafetyPolicy(
                allow_macro_workbooks=allow_macro_workbooks,
                allow_embedded_objects=allow_embedded_objects,
            ),
            ocr_mode=ocr_mode,
            ocr_language=ocr_language,
            ocr_confidence_threshold=ocr_confidence_threshold,
        )
        extraction = enrich_extraction(extraction, redact_sensitive=redact_sensitive)
        if duplicate and duplicate_policy == "warn":
            warnings = list(extraction.warnings)
            warnings.append(f"Duplicate source detected; previous completed run: {duplicate.run_id}.")
            from dataclasses import replace

            extraction = replace(extraction, warnings=tuple(dict.fromkeys(warnings)))
        if keep_source:
            source_path = output_directory / f"source_{name}"
            source_path.write_bytes(data)
            source_saved_path = str(source_path)
        generated = export_all(extraction)
        outputs: list[DocumentOutput] = []
        for output_name, output_data in generated.items():
            path = output_directory / output_name
            path.write_bytes(output_data)
            format_name = path.suffix.lower().lstrip(".")
            if output_name.endswith("_csv_tables.zip"):
                format_name = "csv_zip"
            elif output_name.endswith("_complete_export.zip"):
                format_name = "bundle_zip"
            output = DocumentOutput(
                output_id=uuid4().hex,
                run_id=run_id,
                format=format_name,
                filename=output_name,
                path=str(path),
                size_bytes=len(output_data),
                sha256=sha256_bytes(output_data),
                created_at_utc=utc_now(),
            )
            add_output(history_path, output)
            outputs.append(output)
        manifest = {
            "run_id": run_id,
            "engine_version": "2.7.0",
            "source": extraction.summary(),
            "outputs": [asdict(output) for output in outputs],
            "warnings": list(extraction.warnings),
            "structured_fields": extraction.structured_fields,
            "duplicate_of_run_id": duplicate.run_id if duplicate else None,
        }
        (output_directory / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        complete_run(
            history_path,
            run_id,
            summary=extraction.summary(),
            warnings=list(extraction.warnings),
            output_directory=str(output_directory),
            source_saved_path=source_saved_path,
            metadata=extraction.metadata,
        )
        index_extraction(history_path, run_id, extraction)
        add_event(
            history_path,
            run_id,
            "indexed",
            f"Indexed {len(extraction.sections)} section(s), {len(extraction.tables)} table(s) "
            f"and {len(extraction.entities)} scientific entity record(s).",
        )
        return ProcessedDocument(
            run_id=run_id,
            extraction=extraction,
            outputs=tuple(outputs),
            output_directory=str(output_directory),
            source_saved_path=source_saved_path,
        )
    except Exception as exc:
        fail_run(history_path, run_id, str(exc))
        raise


def process_documents(
    documents: Iterable[tuple[str, bytes]],
    *,
    project_root: str | Path,
    progress_callback: Callable[[int, int, str], None] | None = None,
    **options: Any,
) -> BatchDocumentResult:
    items = list(documents)
    processed: list[ProcessedDocument] = []
    errors: list[dict[str, str]] = []
    batch_id = uuid4().hex
    for index, (filename, data) in enumerate(items, start=1):
        if progress_callback:
            progress_callback(index - 1, len(items), filename)
        try:
            processed.append(
                process_document(filename, data, project_root=project_root, **options)
            )
        except Exception as exc:
            errors.append({"filename": filename, "error": str(exc)})
        if progress_callback:
            progress_callback(index, len(items), filename)
    return BatchDocumentResult(
        batch_id=batch_id,
        total=len(items),
        completed=len(processed),
        failed=len(errors),
        processed=tuple(processed),
        errors=tuple(errors),
    )
