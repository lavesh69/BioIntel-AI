from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from biointel.database.core import json_text, utc_now
from .database import ConnectDatabase
from .repositories import new_id

MAX_UPLOAD_BYTES = 250 * 1024 * 1024
ALLOWED = {
    ".jpg":{"image/jpeg"}, ".jpeg":{"image/jpeg"}, ".png":{"image/png"}, ".webp":{"image/webp"},
    ".gif":{"image/gif"}, ".mp4":{"video/mp4"}, ".webm":{"video/webm"}, ".pdf":{"application/pdf"},
    ".docx":{"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".pptx":{"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    ".xlsx":{"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".csv":{"text/csv","text/plain","application/csv"}, ".tsv":{"text/tab-separated-values","text/plain"},
    ".zip":{"application/zip","application/x-zip-compressed"},
}
EXECUTABLES = {".exe",".dll",".com",".bat",".cmd",".ps1",".msi",".scr",".sh",".jar",".js",".vbs"}
SENSITIVE = {
    "email_address": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "phone_number": re.compile(r"(?<!\d)(?:\+?\d[\d .()/-]{7,}\d)(?!\d)"),
    "medical_record_identifier": re.compile(r"\b(?:MRN|medical\s*record|patient\s*id)\s*[:#-]?\s*[A-Z0-9-]{4,}\b", re.I),
    "dicom_identifier": re.compile(r"\b(?:PatientName|PatientID|AccessionNumber|StudyInstanceUID)\b", re.I),
    "consent_or_restriction": re.compile(r"\b(?:restricted|confidential|no\s+redistribution|consent\s+required)\b", re.I),
}

class UploadRejected(ValueError):
    pass

class UploadRequiresConfirmation(ValueError):
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        super().__init__("Sensitive-content warnings require confirmation or administrator review.")

@dataclass(frozen=True)
class ScanResult:
    accepted: bool
    detected_mime: str
    media_kind: str
    malware_status: str
    warnings: tuple[str, ...]
    metadata: dict[str, Any]


def _extension(filename: str) -> str:
    suffix = Path(Path(filename).name).suffix.lower()
    if suffix not in ALLOWED:
        raise UploadRejected(f"Unsupported file extension: {suffix or 'none'}")
    return suffix


def _magic(path: Path, suffix: str) -> str:
    head = path.read_bytes()[:64]
    if head.startswith((b"MZ", b"\x7fELF", b"#!")):
        raise UploadRejected("Executable content is not permitted.")
    checks = (
        ({".jpg",".jpeg"}, head.startswith(b"\xff\xd8\xff"), "image/jpeg"),
        ({".png"}, head.startswith(b"\x89PNG\r\n\x1a\n"), "image/png"),
        ({".gif"}, head.startswith((b"GIF87a",b"GIF89a")), "image/gif"),
        ({".webp"}, head.startswith(b"RIFF") and head[8:12] == b"WEBP", "image/webp"),
        ({".mp4"}, head[4:8] == b"ftyp", "video/mp4"),
        ({".webm"}, head.startswith(b"\x1a\x45\xdf\xa3"), "video/webm"),
        ({".pdf"}, head.startswith(b"%PDF-"), "application/pdf"),
        ({".docx",".pptx",".xlsx",".zip"}, head.startswith(b"PK"), next(iter(ALLOWED[suffix]))),
        ({".csv"}, b"\x00" not in head, "text/csv"), ({".tsv"}, b"\x00" not in head, "text/tab-separated-values"),
    )
    for suffixes, valid, mime in checks:
        if suffix in suffixes and valid:
            return mime
    raise UploadRejected("File content does not match its extension.")


def _archive(path: Path, suffix: str) -> dict[str, Any]:
    with zipfile.ZipFile(path) as package:
        entries = package.infolist()
        if len(entries) > 10_000:
            raise UploadRejected("Archive contains too many entries.")
        expanded = compressed = 0
        names = []
        for entry in entries:
            name = entry.filename.replace("\\", "/")
            if name.startswith("/") or ".." in [part for part in name.split("/") if part] or re.match(r"^[A-Za-z]:", name):
                raise UploadRejected("Archive contains an unsafe path.")
            if Path(name).suffix.lower() in EXECUTABLES:
                raise UploadRejected("Archive contains an executable file.")
            expanded += int(entry.file_size); compressed += int(entry.compress_size); names.append(name)
            if expanded > 1024 * 1024 * 1024:
                raise UploadRejected("Archive expands beyond the permitted size.")
        ratio = expanded / max(compressed, 1)
        if ratio > 100 and expanded > 10 * 1024 * 1024:
            raise UploadRejected("Possible archive bomb detected.")
        marker = {".docx":"word/document.xml", ".pptx":"ppt/presentation.xml", ".xlsx":"xl/workbook.xml"}.get(suffix)
        if marker and marker not in names:
            raise UploadRejected(f"{suffix} package is missing required structure.")
        return {"archive_entries":len(entries),"uncompressed_bytes":expanded,"compression_ratio":round(ratio,2)}


def _text_and_metadata(path: Path, suffix: str) -> tuple[str, dict[str, Any]]:
    metadata: dict[str, Any] = {}
    if suffix in {".csv",".tsv"}:
        return path.read_bytes()[:2_000_000].decode("utf-8", errors="ignore"), metadata
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
            metadata = {str(k):str(v)[:500] for k,v in (reader.metadata or {}).items()}
            return "\n".join((p.extract_text() or "") for p in reader.pages[:20])[:2_000_000], metadata
        except Exception:
            return "", metadata
    if suffix in {".docx",".pptx",".xlsx"}:
        prefix = {".docx":"word/", ".pptx":"ppt/", ".xlsx":"xl/"}[suffix]
        chunks = []
        with zipfile.ZipFile(path) as package:
            for item in package.infolist():
                if item.filename.startswith(prefix) and item.filename.endswith(".xml"):
                    chunks.append(package.read(item)[:500_000].decode("utf-8",errors="ignore"))
                    if sum(map(len,chunks)) >= 2_000_000: break
            for name in ("docProps/core.xml","docProps/app.xml"):
                try: metadata[name] = package.read(name)[:50_000].decode("utf-8",errors="ignore")
                except KeyError: pass
        return "\n".join(chunks)[:2_000_000], metadata
    if suffix in {".jpg",".jpeg",".png",".webp"}:
        try:
            from PIL import Image
            with Image.open(path) as image:
                metadata = {str(k):str(v)[:500] for k,v in image.getexif().items()}
        except Exception: pass
    return "", metadata


def scan_upload(path: str | Path, *, original_name: str, declared_mime: str,
                malware_scanner: Callable[[Path], str] | None = None) -> ScanResult:
    file_path, suffix = Path(path).resolve(), _extension(original_name)
    detected = _magic(file_path, suffix)
    declared = declared_mime.split(";",1)[0].strip().lower()
    if declared and declared not in ALLOWED[suffix]:
        raise UploadRejected("Declared MIME type is not allowed for this extension.")
    metadata = _archive(file_path,suffix) if suffix in {".docx",".pptx",".xlsx",".zip"} else {}
    malware = "built_in_clear"
    if malware_scanner:
        malware = str(malware_scanner(file_path))
        if malware.lower() not in {"clear","clean","ok"}:
            raise UploadRejected("External malware scanner did not clear this file.")
    text, embedded = _text_and_metadata(file_path,suffix)
    metadata["embedded_metadata"] = embedded
    searchable = text + "\n" + json.dumps(embedded,default=str)
    warnings = tuple(name for name,pattern in SENSITIVE.items() if pattern.search(searchable))
    kind = "image" if detected.startswith("image/") else "video" if detected.startswith("video/") else "document"
    return ScanResult(True,detected,kind,malware,warnings,metadata)


class MediaService:
    def __init__(self, database: ConnectDatabase, storage_root: str | Path, *,
                 max_upload_bytes: int = MAX_UPLOAD_BYTES,
                 malware_scanner: Callable[[Path], str] | None = None) -> None:
        self.database, self.storage_root = database, Path(storage_root).resolve()
        self.max_upload_bytes, self.malware_scanner = int(max_upload_bytes), malware_scanner
        (self.storage_root/".uploads").mkdir(parents=True,exist_ok=True)
        (self.storage_root/"objects").mkdir(parents=True,exist_ok=True)

    def initialize(self, owner_id: str, *, filename: str, mime_type: str,
                   size_bytes: int, expected_sha256: str = "") -> dict[str,Any]:
        suffix, declared = _extension(filename), mime_type.split(";",1)[0].strip().lower()
        if not 1 <= size_bytes <= self.max_upload_bytes:
            raise UploadRejected(f"Upload size must be 1-{self.max_upload_bytes} bytes.")
        if declared not in ALLOWED[suffix]: raise UploadRejected("MIME type is not allowed for this extension.")
        if expected_sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}",expected_sha256): raise UploadRejected("Invalid SHA-256.")
        upload_id, now = new_id("upl"), utc_now()
        temporary = (self.storage_root/".uploads"/f"{upload_id}.part").resolve()
        with self.database.connection() as db:
            db.execute("""INSERT INTO connect_upload_sessions(upload_id,owner_id,original_name,safe_extension,
                declared_mime,expected_bytes,expected_sha256,temporary_path,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", (upload_id,owner_id,Path(filename).name[:255],suffix,declared,
                size_bytes,expected_sha256.lower(),str(temporary),now,now))
        return {"upload_id":upload_id,"offset":0,"expected_bytes":size_bytes,"state":"uploading"}

    def status(self, owner_id: str, upload_id: str) -> dict[str,Any]:
        with self.database.connection(read_only=True) as db:
            row = db.execute("SELECT * FROM connect_upload_sessions WHERE upload_id=? AND owner_id=?",(upload_id,owner_id)).fetchone()
        if not row: raise KeyError(upload_id)
        result = dict(row); result.pop("temporary_path",None); return result

    def append_chunk(self, owner_id: str, upload_id: str, *, offset: int, chunk: bytes) -> dict[str,Any]:
        if not chunk: raise UploadRejected("Upload chunk is empty.")
        with self.database.connection() as db:
            row = db.execute("SELECT * FROM connect_upload_sessions WHERE upload_id=? AND owner_id=? AND deleted_at_utc IS NULL",(upload_id,owner_id)).fetchone()
            if not row: raise KeyError(upload_id)
            received = int(row["received_bytes"])
            if row["state"] != "uploading": raise UploadRejected("Upload is not accepting chunks.")
            if offset != received: raise UploadRejected(f"Chunk offset mismatch; resume from {received}.")
            if received+len(chunk) > int(row["expected_bytes"]): raise UploadRejected("Chunk exceeds declared size.")
            temporary = Path(row["temporary_path"]).resolve()
            if (self.storage_root/".uploads").resolve() not in temporary.parents: raise UploadRejected("Unsafe upload path.")
            with temporary.open("ab") as handle:
                handle.write(chunk); handle.flush(); os.fsync(handle.fileno())
            received += len(chunk)
            db.execute("UPDATE connect_upload_sessions SET received_bytes=?,updated_at_utc=?,version=version+1 WHERE upload_id=?",
                       (received,utc_now(),upload_id))
        return {"upload_id":upload_id,"offset":received,"expected_bytes":int(row["expected_bytes"]),
                "complete":received==int(row["expected_bytes"])}

    def complete(self, owner_id: str, upload_id: str, *, visibility: str = "private",
                 confirm_sensitive: bool = False, administrator_review: bool = False) -> dict[str,Any]:
        with self.database.connection(read_only=True) as db:
            row = db.execute("SELECT * FROM connect_upload_sessions WHERE upload_id=? AND owner_id=?",(upload_id,owner_id)).fetchone()
        if not row: raise KeyError(upload_id)
        if int(row["received_bytes"]) != int(row["expected_bytes"]): raise UploadRejected("Upload is incomplete.")
        temporary = Path(row["temporary_path"]).resolve()
        sha256 = hashlib.sha256(temporary.read_bytes()).hexdigest()
        if row["expected_sha256"] and sha256 != row["expected_sha256"]: raise UploadRejected("Checksum mismatch.")
        scan = scan_upload(temporary,original_name=row["original_name"],declared_mime=row["declared_mime"],malware_scanner=self.malware_scanner)
        scan_data = {**asdict(scan),"warnings":list(scan.warnings),"sha256":sha256}
        if scan.warnings and visibility in {"public","followers","connections"} and not (confirm_sensitive or administrator_review):
            with self.database.connection() as db:
                db.execute("UPDATE connect_upload_sessions SET state='requires_confirmation',scan_json=?,updated_at_utc=? WHERE upload_id=?",
                           (json_text(scan_data),utc_now(),upload_id))
            raise UploadRequiresConfirmation({"upload_id":upload_id,"state":"requires_confirmation","warnings":list(scan.warnings)})
        with self.database.connection() as db:
            existing = db.execute("SELECT * FROM connect_media_objects WHERE owner_id=? AND sha256=? AND state='available'",(owner_id,sha256)).fetchone()
            if existing:
                temporary.unlink(missing_ok=True)
                db.execute("UPDATE connect_upload_sessions SET state='completed',scan_json=?,updated_at_utc=? WHERE upload_id=?",
                           (json_text(scan_data),utc_now(),upload_id))
                return dict(existing)
        media_id, now_dt, now = new_id("med"), datetime.now(UTC), utc_now()
        destination = (self.storage_root/"objects"/owner_id/f"{now_dt:%Y}"/f"{now_dt:%m}"/f"{media_id}{row['safe_extension']}").resolve()
        if (self.storage_root/"objects").resolve() not in destination.parents: raise UploadRejected("Unsafe storage path.")
        destination.parent.mkdir(parents=True,exist_ok=True); shutil.move(str(temporary),str(destination))
        with self.database.connection() as db:
            db.execute("""INSERT INTO connect_media_objects(media_id,owner_id,original_name,storage_path,mime_type,size_bytes,
                sha256,media_kind,scan_json,visibility,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (media_id,owner_id,row["original_name"],str(destination),scan.detected_mime,row["expected_bytes"],sha256,
                 scan.media_kind,json_text(scan_data),visibility,now,now))
            db.execute("UPDATE connect_upload_sessions SET state='completed',scan_json=?,updated_at_utc=? WHERE upload_id=?",
                       (json_text(scan_data),now,upload_id))
            media = db.execute("SELECT * FROM connect_media_objects WHERE media_id=?",(media_id,)).fetchone()
        return dict(media)

    def upload_bytes(self, owner_id: str, *, filename: str, mime_type: str, data: bytes,
                     visibility: str = "private", confirm_sensitive: bool = False,
                     progress: Callable[[int,int],None] | None = None, chunk_size: int = 1024*1024) -> dict[str,Any]:
        session = self.initialize(owner_id,filename=filename,mime_type=mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
                                  size_bytes=len(data),expected_sha256=hashlib.sha256(data).hexdigest())
        offset, stream = 0, io.BytesIO(data)
        while chunk := stream.read(chunk_size):
            offset = int(self.append_chunk(owner_id,session["upload_id"],offset=offset,chunk=chunk)["offset"])
            if progress: progress(offset,len(data))
        return self.complete(owner_id,session["upload_id"],visibility=visibility,confirm_sensitive=confirm_sensitive)

    def resolve_download(self, requester_id: str, media_id: str) -> Path:
        with self.database.connection(read_only=True) as db:
            row = db.execute("SELECT * FROM connect_media_objects WHERE media_id=? AND state='available' AND deleted_at_utc IS NULL",(media_id,)).fetchone()
        if not row: raise KeyError(media_id)
        if row["owner_id"] != requester_id and row["visibility"] == "private": raise PermissionError("Media is private.")
        path = Path(row["storage_path"]).resolve()
        if (self.storage_root/"objects").resolve() not in path.parents or not path.is_file(): raise FileNotFoundError(media_id)
        return path
