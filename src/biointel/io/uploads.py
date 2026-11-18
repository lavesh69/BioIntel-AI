from __future__ import annotations

import csv
import gzip
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable, Mapping, Sequence

import pandas as pd


class UploadReadError(ValueError):
    """Raised when an uploaded file cannot be parsed safely or consistently."""


class UploadSchemaError(ValueError):
    """Raised when a parsed table does not satisfy its required schema."""


_TABLE_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".txt",
    ".tab",
    ".maf",
    ".csv.gz",
    ".tsv.gz",
    ".txt.gz",
    ".maf.gz",
    ".xlsx",
    ".xlsm",
    ".xls",
    ".ods",
    ".zip",
}
_TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "utf-16", "cp1252", "latin-1")
_SAFE_ARCHIVE_MEMBER = re.compile(r"^[^\x00]+$")


@dataclass(frozen=True)
class UploadedTable:
    frame: pd.DataFrame
    source_name: str
    detected_extension: str
    encoding: str
    separator: str
    sheet_name: str | int | None
    archive_member: str | None
    warnings: tuple[str, ...] = ()


def _compound_suffix(filename: str) -> str:
    lowered = str(filename or "upload").strip().lower()
    for suffix in (
        ".csv.gz",
        ".tsv.gz",
        ".txt.gz",
        ".maf.gz",
        ".vcf.gz",
        ".fastq.gz",
        ".fq.gz",
        ".fasta.gz",
        ".fa.gz",
    ):
        if lowered.endswith(suffix):
            return suffix
    dot = lowered.rfind(".")
    return lowered[dot:] if dot >= 0 else ""


def _decode_text(data: bytes, *, preferred: str | None = None) -> tuple[str, str]:
    encodings: list[str] = []
    if preferred:
        encodings.append(preferred)
    encodings.extend(value for value in _TEXT_ENCODINGS if value not in encodings)
    failures: list[str] = []
    for encoding in encodings:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            failures.append(f"{encoding}: byte {exc.start}")
    raise UploadReadError(
        "The text encoding could not be detected. Save the file as UTF-8 CSV/TSV and retry. "
        + "; ".join(failures[:3])
    )


def _detect_separator(text: str, extension: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    if extension.startswith(".tsv") or extension.startswith(".tab") or extension.startswith(".maf"):
        return "\t"
    sample_lines = [line for line in text.splitlines() if line.strip()][:30]
    sample = "\n".join(sample_lines)
    if not sample:
        return ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        return str(dialect.delimiter)
    except csv.Error:
        counts = {delimiter: sample.count(delimiter) for delimiter in (",", "\t", ";", "|")}
        delimiter, count = max(counts.items(), key=lambda item: item[1])
        return delimiter if count else ","


def _safe_zip_member(name: str) -> bool:
    if not _SAFE_ARCHIVE_MEMBER.match(name):
        return False
    normalized = PurePosixPath(name.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        return False
    return bool(normalized.name)


def _extract_single_table_from_zip(
    data: bytes,
    *,
    max_uncompressed_bytes: int,
    max_members: int = 100,
) -> tuple[bytes, str]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = [item for item in archive.infolist() if not item.is_dir()]
            if len(infos) > max_members:
                raise UploadReadError(
                    f"The ZIP contains {len(infos)} files; the interactive limit is {max_members}."
                )
            unsafe = [item.filename for item in infos if not _safe_zip_member(item.filename)]
            if unsafe:
                raise UploadReadError("The ZIP contains an unsafe path and was blocked.")
            candidates = [
                item
                for item in infos
                if _compound_suffix(item.filename) in _TABLE_EXTENSIONS - {".zip"}
                and not item.filename.startswith("__MACOSX/")
            ]
            if not candidates:
                raise UploadReadError(
                    "The ZIP does not contain a supported CSV, TSV, TXT, MAF, Excel or ODS table."
                )
            if len(candidates) > 1:
                names = ", ".join(item.filename for item in candidates[:5])
                raise UploadReadError(
                    "The ZIP contains multiple supported tables. Upload one table directly or create a ZIP "
                    f"with exactly one table. Found: {names}"
                )
            selected = candidates[0]
            if selected.file_size > max_uncompressed_bytes:
                raise UploadReadError(
                    "The uncompressed table exceeds the interactive safety limit. Use the batch workflow."
                )
            if selected.compress_size > 0 and selected.file_size / selected.compress_size > 250:
                raise UploadReadError("The ZIP compression ratio is unusually high and was blocked.")
            return archive.read(selected), selected.filename
    except zipfile.BadZipFile as exc:
        raise UploadReadError("The uploaded ZIP is corrupt or incomplete.") from exc


def _normalize_columns(frame: pd.DataFrame) -> tuple[pd.DataFrame, tuple[str, ...]]:
    warnings: list[str] = []
    normalized: list[str] = []
    for index, column in enumerate(frame.columns):
        value = str(column).replace("\ufeff", "").strip()
        if not value or value.lower().startswith("unnamed:"):
            value = f"column_{index + 1}"
            warnings.append(f"Blank column name {index + 1} was renamed to {value}.")
        normalized.append(value)
    duplicates = sorted({name for name in normalized if normalized.count(name) > 1})
    if duplicates:
        raise UploadSchemaError(
            "Duplicate column names are not supported: " + ", ".join(duplicates[:10])
        )
    result = frame.copy()
    result.columns = normalized
    empty_columns = [column for column in result.columns if result[column].isna().all()]
    if empty_columns:
        warnings.append(
            f"{len(empty_columns)} completely empty column(s) were retained for provenance."
        )
    return result, tuple(warnings)


def _read_delimited(
    data: bytes,
    *,
    extension: str,
    separator: str | None,
    encoding: str | None,
    low_memory: bool,
    index_column: str | int | None,
    max_rows: int | None,
) -> tuple[pd.DataFrame, str, str]:
    if extension.endswith(".gz"):
        try:
            data = gzip.decompress(data)
        except (OSError, EOFError) as exc:
            raise UploadReadError("The gzip file is corrupt or incomplete.") from exc
    text, detected_encoding = _decode_text(data, preferred=encoding)
    detected_separator = _detect_separator(text, extension, separator)
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    if first_line:
        try:
            raw_header = next(csv.reader([first_line], delimiter=detected_separator))
        except csv.Error:
            raw_header = []
        normalized_header = [str(value).replace("\ufeff", "").strip() for value in raw_header]
        duplicate_header = sorted(
            {value for value in normalized_header if value and normalized_header.count(value) > 1}
        )
        if duplicate_header:
            raise UploadSchemaError(
                "Duplicate column names were found in the file header: "
                + ", ".join(duplicate_header[:10])
            )
    try:
        engine = "python" if detected_separator in {";", "|"} else "c"
        read_kwargs = {
            "sep": detected_separator,
            "index_col": index_column,
            "nrows": max_rows,
            "engine": engine,
            "on_bad_lines": "error",
        }
        if engine == "c":
            read_kwargs["low_memory"] = bool(low_memory)
        frame = pd.read_csv(io.StringIO(text), **read_kwargs)
    except (pd.errors.ParserError, UnicodeError, ValueError) as exc:
        raise UploadReadError(
            "The table could not be parsed. Confirm that every row uses the same delimiter and column count. "
            f"Detected delimiter: {repr(detected_separator)}. Details: {exc}"
        ) from exc
    return frame, detected_encoding, detected_separator


def _read_excel(
    data: bytes,
    *,
    extension: str,
    sheet_name: str | int | None,
    max_rows: int | None,
) -> tuple[pd.DataFrame, str | int]:
    selected_sheet: str | int = 0 if sheet_name is None else sheet_name
    try:
        frame = pd.read_excel(io.BytesIO(data), sheet_name=selected_sheet, nrows=max_rows)
    except (ValueError, ImportError, OSError, zipfile.BadZipFile) as exc:
        hint = (
            "For legacy .xls files, ensure the workbook is not password protected or corrupted. "
            if extension == ".xls"
            else "Ensure the workbook is not password protected and contains at least one visible sheet. "
        )
        raise UploadReadError(hint + f"Details: {exc}") from exc
    if isinstance(frame, Mapping):
        if not frame:
            raise UploadReadError("The workbook does not contain a readable worksheet.")
        first_name = next(iter(frame))
        return frame[first_name], first_name
    return frame, selected_sheet


def read_uploaded_table_bytes(
    data: bytes,
    filename: str,
    *,
    separator: str | None = None,
    encoding: str | None = None,
    low_memory: bool = False,
    index_column: str | int | None = None,
    sheet_name: str | int | None = None,
    max_rows: int | None = None,
    max_columns: int = 10_000,
    max_cells: int = 25_000_000,
    max_uncompressed_mb: int = 750,
) -> UploadedTable:
    """Read a scientific table with bounded decompression and actionable errors.

    The function accepts CSV/TSV/TXT/MAF, gzip-compressed variants, Excel/ODS and
    a ZIP containing exactly one supported table. It does not silently skip bad
    rows, so malformed uploads are surfaced instead of producing partial results.
    """

    raw = bytes(data)
    if not raw:
        raise UploadReadError("The uploaded file is empty.")
    extension = _compound_suffix(filename)
    if extension not in _TABLE_EXTENSIONS:
        raise UploadReadError(
            f"Unsupported table format {extension or '(no extension)'}. "
            "Use CSV, TSV, TXT, MAF, CSV.GZ, TSV.GZ, XLSX, XLS, XLSM, ODS or a single-table ZIP."
        )
    archive_member: str | None = None
    source_name = str(filename or "upload")
    if extension == ".zip":
        raw, archive_member = _extract_single_table_from_zip(
            raw,
            max_uncompressed_bytes=int(max_uncompressed_mb * 1024 * 1024),
        )
        source_name = archive_member
        extension = _compound_suffix(archive_member)

    if extension in {".xlsx", ".xlsm", ".xls", ".ods"}:
        frame, selected_sheet = _read_excel(
            raw,
            extension=extension,
            sheet_name=sheet_name,
            max_rows=max_rows,
        )
        detected_encoding = "binary-workbook"
        detected_separator = "worksheet"
    else:
        frame, detected_encoding, detected_separator = _read_delimited(
            raw,
            extension=extension,
            separator=separator,
            encoding=encoding,
            low_memory=low_memory,
            index_column=index_column,
            max_rows=max_rows,
        )
        selected_sheet = None

    if frame.empty and len(frame.columns) == 0:
        raise UploadReadError("The uploaded table does not contain any columns or rows.")
    if frame.shape[1] > int(max_columns):
        raise UploadReadError(
            f"The table contains {frame.shape[1]:,} columns; the safety limit is {int(max_columns):,}."
        )
    cells = int(frame.shape[0]) * int(frame.shape[1])
    if cells > int(max_cells):
        raise UploadReadError(
            f"The table contains approximately {cells:,} cells; the interactive limit is {int(max_cells):,}. "
            "Use a batch/indexed workflow or reduce the table before upload."
        )
    frame, warnings = _normalize_columns(frame)
    return UploadedTable(
        frame=frame,
        source_name=source_name,
        detected_extension=extension,
        encoding=detected_encoding,
        separator=detected_separator,
        sheet_name=selected_sheet,
        archive_member=archive_member,
        warnings=warnings,
    )


def validate_required_columns(
    frame: pd.DataFrame,
    required: Sequence[str],
    *,
    aliases: Mapping[str, Iterable[str]] | None = None,
    case_sensitive: bool = False,
) -> dict[str, str]:
    """Resolve required columns and return canonical-to-observed mappings."""

    observed = [str(column) for column in frame.columns]
    normalized_lookup = {
        (column if case_sensitive else column.casefold()): column for column in observed
    }
    resolved: dict[str, str] = {}
    missing: list[str] = []
    aliases = aliases or {}
    for canonical in required:
        candidates = [canonical, *aliases.get(canonical, ())]
        found = None
        for candidate in candidates:
            key = str(candidate) if case_sensitive else str(candidate).casefold()
            if key in normalized_lookup:
                found = normalized_lookup[key]
                break
        if found is None:
            missing.append(canonical)
        else:
            resolved[canonical] = found
    if missing:
        raise UploadSchemaError(
            "Missing required column(s): "
            + ", ".join(missing)
            + ". Available columns: "
            + ", ".join(observed[:30])
        )
    if len(set(resolved.values())) != len(resolved):
        raise UploadSchemaError("One source column cannot satisfy multiple required fields.")
    return resolved
