from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_EXTENSIONS = frozenset(
    {
        ".pdf", ".xlsx", ".xls", ".xlsm", ".docx", ".csv", ".tsv", ".txt",
        ".md", ".html", ".htm", ".json", ".xml", ".yaml", ".yml", ".pptx",
        ".odt", ".ods",
    }
)
MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".json": "application/json",
    ".xml": "application/xml",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
}


class DocumentSecurityError(ValueError):
    """Raised when an uploaded document violates local safety controls."""


@dataclass(frozen=True)
class DocumentSafetyPolicy:
    max_file_bytes: int = 100 * 1024 * 1024
    max_uncompressed_bytes: int = 500 * 1024 * 1024
    max_zip_members: int = 20_000
    max_compression_ratio: float = 150.0
    allow_macro_workbooks: bool = False
    allow_embedded_objects: bool = False
    block_pdf_javascript: bool = True


def safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        raise DocumentSecurityError("Document filename is empty or invalid.")
    return name[:180]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _zip_member_names(data: bytes) -> set[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {member.filename.replace("\\", "/") for member in archive.infolist()}


def _validate_zip_container(
    data: bytes,
    policy: DocumentSafetyPolicy,
    *,
    extension: str,
) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > policy.max_zip_members:
                raise DocumentSecurityError(
                    f"Document contains too many archive members ({len(members)})."
                )
            total_uncompressed = sum(max(0, item.file_size) for item in members)
            total_compressed = sum(max(1, item.compress_size) for item in members)
            if total_uncompressed > policy.max_uncompressed_bytes:
                raise DocumentSecurityError(
                    "Document expands beyond the configured safety limit."
                )
            ratio = total_uncompressed / max(total_compressed, 1)
            if ratio > policy.max_compression_ratio:
                raise DocumentSecurityError(
                    "Document has a suspicious archive compression ratio."
                )
            member_names = {member.filename.replace("\\", "/") for member in members}
            for member in members:
                path = Path(member.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise DocumentSecurityError("Document contains an unsafe archive path.")

            required = {
                ".docx": "word/document.xml",
                ".xlsx": "xl/workbook.xml",
                ".xlsm": "xl/workbook.xml",
                ".pptx": "ppt/presentation.xml",
                ".odt": "content.xml",
                ".ods": "content.xml",
            }.get(extension)
            if required and required not in member_names:
                raise DocumentSecurityError(
                    f"{extension.upper().lstrip('.')} package does not contain {required}."
                )

            contains_vba = any(name.lower().endswith("vbaproject.bin") for name in member_names)
            if contains_vba and not policy.allow_macro_workbooks:
                raise DocumentSecurityError(
                    "Workbook contains VBA macros and is blocked by the current safety policy."
                )
            embedded = [
                name
                for name in member_names
                if "/embeddings/" in name.lower() or name.lower().endswith((".bin", ".ole"))
            ]
            if embedded and not policy.allow_embedded_objects:
                # Do not block normal package binaries such as font data; flag known embedding paths.
                true_embedded = [name for name in embedded if "/embeddings/" in name.lower()]
                if true_embedded:
                    raise DocumentSecurityError(
                        "Document contains embedded objects. Enable embedded-object reading only "
                        "after reviewing the source. Embedded objects are never executed."
                    )
            external_relationships = []
            for name in member_names:
                if not name.endswith(".rels"):
                    continue
                try:
                    payload = archive.read(name).decode("utf-8", errors="ignore")
                except Exception:
                    continue
                if 'TargetMode="External"' in payload:
                    external_relationships.append(name)
            return {
                "archive_members": len(members),
                "uncompressed_bytes": total_uncompressed,
                "compression_ratio": round(ratio, 3),
                "contains_vba": contains_vba,
                "embedded_object_count": len(embedded),
                "external_relationship_files": external_relationships,
            }
    except zipfile.BadZipFile as exc:
        raise DocumentSecurityError("Document is not a valid ZIP-based file.") from exc


def inspect_pdf_security(data: bytes) -> dict[str, Any]:
    findings = {
        "javascript": False,
        "open_action": False,
        "additional_actions": False,
        "launch_action": False,
        "embedded_files": False,
    }
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data), strict=False)
        root = reader.trailer.get("/Root", {})
        names = root.get("/Names", {}) if hasattr(root, "get") else {}
        findings["javascript"] = bool(names.get("/JavaScript")) if hasattr(names, "get") else False
        findings["embedded_files"] = bool(names.get("/EmbeddedFiles")) if hasattr(names, "get") else False
        findings["open_action"] = bool(root.get("/OpenAction")) if hasattr(root, "get") else False
        findings["additional_actions"] = bool(root.get("/AA")) if hasattr(root, "get") else False
        for page in reader.pages:
            page_object = page.get_object()
            if page_object.get("/AA"):
                findings["additional_actions"] = True
            annotations = page_object.get("/Annots") or []
            for annotation in annotations:
                try:
                    action = annotation.get_object().get("/A")
                    if action and str(action.get("/S")) == "/Launch":
                        findings["launch_action"] = True
                except Exception:
                    continue
    except Exception:
        # Extraction engine will report malformed PDFs separately.
        pass
    return findings


def validate_document(
    filename: str,
    data: bytes,
    *,
    policy: DocumentSafetyPolicy | None = None,
) -> tuple[str, str, str]:
    active = policy or DocumentSafetyPolicy()
    name = safe_filename(filename)
    extension = Path(name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentSecurityError(
            "Supported types: PDF, Excel, DOCX, CSV/TSV, TXT/Markdown, HTML, "
            "JSON/XML/YAML, PPTX and OpenDocument ODT/ODS."
        )
    if not data:
        raise DocumentSecurityError("Document is empty.")
    if len(data) > active.max_file_bytes:
        raise DocumentSecurityError(
            f"Document exceeds the {active.max_file_bytes // (1024 * 1024)} MB safety limit."
        )
    if extension == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise DocumentSecurityError("File extension is PDF but the content is not a PDF.")
        findings = inspect_pdf_security(data)
        if active.block_pdf_javascript and any(
            findings[key] for key in ("javascript", "open_action", "additional_actions", "launch_action")
        ):
            raise DocumentSecurityError(
                "PDF contains JavaScript, launch or automatic actions and is blocked."
            )
    elif extension == ".xls":
        if not data.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
            raise DocumentSecurityError("File extension is XLS but the content is not legacy Excel.")
    elif extension in {".docx", ".xlsx", ".xlsm", ".pptx", ".odt", ".ods"}:
        if not data.startswith(b"PK"):
            raise DocumentSecurityError("Office/OpenDocument content does not match its extension.")
        _validate_zip_container(data, active, extension=extension)
        if extension == ".xlsm" and not active.allow_macro_workbooks:
            raise DocumentSecurityError(
                "Macro-enabled XLSM files are blocked by default. Convert to XLSX or explicitly "
                "enable macro-workbook reading. Macros are never executed."
            )
    elif extension in {".json", ".xml", ".yaml", ".yml", ".csv", ".tsv", ".txt", ".md", ".html", ".htm"}:
        if b"\x00" in data[:8192]:
            raise DocumentSecurityError("Text/structured file contains binary null bytes.")
    return name, extension, MIME_BY_EXTENSION[extension]
