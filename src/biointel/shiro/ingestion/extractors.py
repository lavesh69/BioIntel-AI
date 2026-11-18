from __future__ import annotations

import csv
import io
import json
import re
import statistics
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from biointel.shiro.exceptions import CorruptDocumentError, UnsupportedDocumentError

SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".csv", ".tsv", ".json", ".pdf", ".docx", ".html", ".htm",
    ".fasta", ".fa", ".fna", ".fastq", ".fq", ".vcf", ".bed", ".gff", ".gtf", ".ipynb",
    ".png", ".jpg", ".jpeg", ".webp",
}
MIME_TYPES = {
    ".txt": "text/plain", ".md": "text/markdown", ".csv": "text/csv", ".tsv": "text/tab-separated-values",
    ".json": "application/json", ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".html": "text/html", ".htm": "text/html", ".fasta": "text/x-fasta", ".fa": "text/x-fasta",
    ".fna": "text/x-fasta", ".fastq": "text/x-fastq", ".fq": "text/x-fastq",
    ".vcf": "text/x-vcf", ".bed": "text/x-bed", ".gff": "text/x-gff", ".gtf": "text/x-gtf",
    ".ipynb": "application/x-ipynb+json",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
}


@dataclass(frozen=True)
class ExtractedSection:
    text: str
    location: str
    section: str = ""


@dataclass(frozen=True)
class ExtractionResult:
    sections: tuple[ExtractedSection, ...]
    source_type: str
    mime_type: str
    warnings: tuple[str, ...] = ()
    author: str = ""


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        elif not self.skip and tag in {"p", "br", "h1", "h2", "h3", "h4", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1
        elif not self.skip and tag in {"p", "h1", "h2", "h3", "h4", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def safe_filename(filename: str) -> str:
    value = filename.strip()
    if not value or len(value) > 240 or any(ord(char) < 32 for char in value):
        raise UnsupportedDocumentError("The filename is empty, too long, or contains control characters.")
    if Path(value).name != value or "/" in value or "\\" in value or value in {".", ".."}:
        raise UnsupportedDocumentError("Path components are not allowed in uploaded filenames.")
    suffix = Path(value).suffix.casefold()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentError(f"Unsupported evidence type: {suffix or 'no extension'}.")
    return value


def _decode(content: bytes) -> tuple[str, list[str]]:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            text = content.decode(encoding)
            return text, ([] if encoding == "utf-8-sig" else ["Text decoded as UTF-16."])
        except UnicodeDecodeError:
            continue
    try:
        return content.decode("cp1252"), ["Text decoded as Windows-1252; verify non-ASCII scientific symbols."]
    except UnicodeDecodeError as exc:
        raise CorruptDocumentError("The document encoding is unsupported or corrupt.") from exc


def _markdown_sections(text: str) -> list[ExtractedSection]:
    sections: list[ExtractedSection] = []
    heading = "Document"
    buffer: list[str] = []
    start_line = 1
    for line_number, line in enumerate(text.splitlines(), start=1):
        if re.match(r"^#{1,6}\s+", line):
            if buffer and "\n".join(buffer).strip():
                sections.append(ExtractedSection("\n".join(buffer).strip(), f"lines {start_line}-{line_number - 1}", heading))
            heading = re.sub(r"^#{1,6}\s+", "", line).strip() or "Section"
            buffer = [line]
            start_line = line_number
        else:
            buffer.append(line)
    if buffer and "\n".join(buffer).strip():
        sections.append(ExtractedSection("\n".join(buffer).strip(), f"lines {start_line}-{len(text.splitlines()) or 1}", heading))
    return sections


def _table_sections(text: str, delimiter: str) -> list[ExtractedSection]:
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return []
    width = max(len(row) for row in rows)
    if width > 1000:
        raise CorruptDocumentError("The table has an unsafe number of columns.")
    header = rows[0]
    sections: list[ExtractedSection] = []
    for start in range(1, len(rows), 50):
        batch = rows[start:start + 50]
        output = io.StringIO()
        writer = csv.writer(output, delimiter=delimiter, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(batch)
        end = start + len(batch)
        sections.append(ExtractedSection(output.getvalue().strip(), f"rows {start + 1}-{end + 1}", "Table"))
    if len(rows) == 1:
        sections.append(ExtractedSection(delimiter.join(header), "row 1", "Table header"))
    return sections


def _json_sections(text: str) -> list[ExtractedSection]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CorruptDocumentError(f"Invalid JSON at line {exc.lineno}.") from exc
    sections: list[ExtractedSection] = []
    if isinstance(value, list):
        for start in range(0, len(value), 25):
            batch = value[start:start + 25]
            sections.append(ExtractedSection(json.dumps(batch, indent=2, ensure_ascii=False), f"items {start + 1}-{start + len(batch)}", "JSON records"))
    elif isinstance(value, dict):
        for key, item in value.items():
            sections.append(ExtractedSection(json.dumps({key: item}, indent=2, ensure_ascii=False), f"key {key}", str(key)))
    else:
        sections.append(ExtractedSection(json.dumps(value, ensure_ascii=False), "root", "JSON value"))
    return sections


def _fasta_summary(text: str) -> list[ExtractedSection]:
    records: list[tuple[str, int, float]] = []
    current = ""
    sequence: list[str] = []
    def finish() -> None:
        if not current:
            return
        value = "".join(sequence).upper()
        gc = 100.0 * sum(char in {"G", "C"} for char in value) / len(value) if value else 0.0
        records.append((current, len(value), gc))
    for line in text.splitlines():
        if line.startswith(">"):
            finish()
            current = line[1:].strip()[:500] or f"record-{len(records) + 1}"
            sequence = []
        elif line.strip():
            if not re.fullmatch(r"[A-Za-z*.-]+", line.strip()):
                raise CorruptDocumentError("FASTA contains invalid sequence characters.")
            sequence.append(line.strip())
    finish()
    if not records:
        raise CorruptDocumentError("No FASTA records were found.")
    sections = [ExtractedSection(f"FASTA records: {len(records)}\nTotal residues/bases: {sum(row[1] for row in records)}", "summary", "FASTA summary")]
    for start in range(0, len(records), 100):
        lines = ["identifier\tlength\tgc_percent"] + [f"{identifier}\t{length}\t{gc:.3f}" for identifier, length, gc in records[start:start + 100]]
        sections.append(ExtractedSection("\n".join(lines), f"records {start + 1}-{min(len(records), start + 100)}", "FASTA record metadata"))
    return sections


def _fastq_summary(text: str) -> list[ExtractedSection]:
    lines = text.splitlines()
    if len(lines) % 4:
        raise CorruptDocumentError("FASTQ must contain complete four-line records.")
    lengths: list[int] = []
    identifiers: list[str] = []
    for index in range(0, len(lines), 4):
        if not lines[index].startswith("@") or not lines[index + 2].startswith("+") or len(lines[index + 1]) != len(lines[index + 3]):
            raise CorruptDocumentError(f"Invalid FASTQ record near line {index + 1}.")
        lengths.append(len(lines[index + 1]))
        if len(identifiers) < 200:
            identifiers.append(lines[index][1:].split()[0][:200])
    summary = (
        f"FASTQ reads: {len(lengths)}\nMinimum read length: {min(lengths, default=0)}\n"
        f"Maximum read length: {max(lengths, default=0)}\nMean read length: {statistics.fmean(lengths) if lengths else 0:.2f}"
    )
    return [ExtractedSection(summary, "summary", "FASTQ metadata"), ExtractedSection("read_identifier\n" + "\n".join(identifiers), f"first {len(identifiers)} read identifiers", "FASTQ identifiers")]


def _pdf_sections(
    content: bytes,
    *,
    ocr_enabled: bool = False,
    ocr_language: str = "eng",
    ocr_max_pages: int = 25,
) -> tuple[list[ExtractedSection], list[str], str]:
    if not content.startswith(b"%PDF-"):
        raise CorruptDocumentError("The file extension is PDF but the signature is invalid.")
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:
        raise UnsupportedDocumentError("PDF extraction requires the optional pypdf dependency.") from exc
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted and not reader.decrypt(""):
            raise CorruptDocumentError("Encrypted PDFs must be unlocked before ingestion.")
        sections: list[ExtractedSection] = []
        warnings: list[str] = []
        missing_text_pages: list[int] = []
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                sections.append(ExtractedSection(text.strip(), f"page {number}", f"Page {number}"))
            else:
                missing_text_pages.append(number)

        ocr_error = ""
        if missing_text_pages and ocr_enabled:
            selected_pages = missing_text_pages[:ocr_max_pages]
            if len(missing_text_pages) > len(selected_pages):
                warnings.append(
                    f"OCR was bounded to {len(selected_pages)} of {len(missing_text_pages)} image-only pages."
                )
            try:
                from biointel.documents.ocr import ocr_pdf

                for result in ocr_pdf(content, selected_pages, language=ocr_language):
                    if result.text.strip():
                        sections.append(
                            ExtractedSection(
                                result.text.strip(),
                                f"page {result.page_number} (OCR)",
                                f"Page {result.page_number}",
                            )
                        )
                    else:
                        warnings.append(f"Page {result.page_number} OCR returned no text; review the source image.")
                    warnings.extend(result.warnings)
            except Exception as exc:  # optional local binary/dependency boundary
                ocr_error = f"{type(exc).__name__}: {exc}"
                warnings.append(
                    "OCR was requested but could not run locally. Install the Tesseract OCR engine "
                    "and requested language data, or disable SHIRO_OCR_ENABLED."
                )
        elif missing_text_pages:
            for number in missing_text_pages:
                warnings.append(
                    f"Page {number} has no extractable text; set SHIRO_OCR_ENABLED=true to use reviewed local OCR."
                )

        if not sections and missing_text_pages:
            if ocr_enabled and ocr_error:
                raise UnsupportedDocumentError(
                    "This is an image-only PDF and local OCR could not run. Install Tesseract OCR "
                    f"with language '{ocr_language}', then retry."
                )
            if ocr_enabled:
                raise CorruptDocumentError("OCR completed but found no reviewable evidence text in the PDF.")
            raise UnsupportedDocumentError(
                "This PDF is image-only. Enable reviewed local OCR with SHIRO_OCR_ENABLED=true, "
                "or provide a text-searchable PDF."
            )
        author = str((reader.metadata or {}).get("/Author", ""))[:300]
        sections.sort(key=lambda item: int(re.search(r"page\s+(\d+)", item.location).group(1)))
        return sections, warnings, author
    except (CorruptDocumentError, UnsupportedDocumentError):
        raise
    except (PdfReadError, OSError, ValueError) as exc:
        raise CorruptDocumentError("The PDF is corrupt or cannot be parsed safely.") from exc

def _docx_sections(content: bytes) -> tuple[list[ExtractedSection], str]:
    if not content.startswith(b"PK"):
        raise CorruptDocumentError("The DOCX ZIP signature is invalid.")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            if "word/document.xml" not in names:
                raise CorruptDocumentError("The DOCX document body is missing.")
            root = ElementTree.fromstring(archive.read("word/document.xml"))
            namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            paragraphs = []
            for paragraph in root.iter(namespace + "p"):
                value = "".join(node.text or "" for node in paragraph.iter(namespace + "t")).strip()
                if value:
                    paragraphs.append(value)
            author = ""
            if "docProps/core.xml" in names:
                core = ElementTree.fromstring(archive.read("docProps/core.xml"))
                creator = core.find("{http://purl.org/dc/elements/1.1/}creator")
                author = (creator.text or "")[:300] if creator is not None else ""
    except zipfile.BadZipFile as exc:
        raise CorruptDocumentError("The DOCX archive is corrupt.") from exc
    return [ExtractedSection("\n\n".join(paragraphs[start:start + 40]), f"paragraphs {start + 1}-{min(len(paragraphs), start + 40)}", "Document paragraphs") for start in range(0, len(paragraphs), 40)], author



def _image_sections(content: bytes, *, ocr_enabled: bool = False, ocr_language: str = "eng") -> tuple[list[ExtractedSection], list[str]]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise UnsupportedDocumentError("Image evidence requires Pillow.") from exc
    warnings: list[str] = []
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
            mode = image.mode
            fmt = image.format or "image"
            text = f"Image evidence\nFormat: {fmt}\nDimensions: {width} x {height} pixels\nColour mode: {mode}"
            sections = [ExtractedSection(text, "image metadata", "Image metadata")]
            if ocr_enabled:
                try:
                    import pytesseract
                    ocr_text = pytesseract.image_to_string(image, lang=ocr_language).strip()
                    if ocr_text:
                        sections.append(ExtractedSection(ocr_text, "image OCR", "Recognized text"))
                    else:
                        warnings.append("Local OCR found no readable text in the image.")
                except Exception as exc:
                    warnings.append(f"Local image OCR was unavailable: {type(exc).__name__}: {exc}")
            else:
                warnings.append("Image metadata was indexed. Visual interpretation is available only when a qualified Shiro vision model is selected; enable local OCR to index visible text.")
            return sections, warnings
    except Exception as exc:
        raise CorruptDocumentError("The uploaded image is corrupt or unsupported.") from exc

def extract_document(
    content: bytes,
    filename: str,
    maximum_bytes: int,
    *,
    ocr_enabled: bool = False,
    ocr_language: str = "eng",
    ocr_max_pages: int = 25,
) -> ExtractionResult:
    safe = safe_filename(filename)
    if not content:
        raise CorruptDocumentError("The uploaded document is empty.")
    if len(content) > maximum_bytes:
        raise UnsupportedDocumentError(f"The document exceeds the {maximum_bytes // (1024 * 1024)} MB limit.")
    suffix = Path(safe).suffix.casefold()
    warnings: list[str] = []
    author = ""
    if suffix == ".pdf":
        sections, warnings, author = _pdf_sections(
            content,
            ocr_enabled=ocr_enabled,
            ocr_language=ocr_language,
            ocr_max_pages=ocr_max_pages,
        )
    elif suffix == ".docx":
        sections, author = _docx_sections(content)
    elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        sections, image_warnings = _image_sections(content, ocr_enabled=ocr_enabled, ocr_language=ocr_language)
        warnings.extend(image_warnings)
    else:
        text, decode_warnings = _decode(content)
        warnings.extend(decode_warnings)
        if suffix == ".md":
            sections = _markdown_sections(text)
        elif suffix == ".txt":
            sections = [ExtractedSection(text, "document", "Text")]
        elif suffix in {".csv", ".tsv", ".bed", ".gff", ".gtf", ".vcf"}:
            delimiter = "," if suffix == ".csv" else "\t"
            sections = _table_sections(text, delimiter)
        elif suffix in {".json", ".ipynb"}:
            sections = _json_sections(text)
        elif suffix in {".html", ".htm"}:
            parser = _HTMLText()
            parser.feed(text)
            sections = _markdown_sections("".join(parser.parts))
        elif suffix in {".fasta", ".fa", ".fna"}:
            sections = _fasta_summary(text)
            warnings.append("FASTA sequences were summarized; raw sequence content was not copied into the conversational index.")
        elif suffix in {".fastq", ".fq"}:
            sections = _fastq_summary(text)
            warnings.append("FASTQ reads were summarized; raw reads and quality strings were not copied into the conversational index.")
        else:
            raise UnsupportedDocumentError(f"Unsupported evidence type: {suffix}.")
    clean_sections = tuple(section for section in sections if section.text.strip())
    if not clean_sections:
        raise CorruptDocumentError("No extractable evidence text was found.")
    source_type = {
        ".pdf": "document", ".docx": "document", ".md": "report", ".txt": "text",
        ".csv": "table", ".tsv": "table", ".json": "structured_data", ".ipynb": "notebook",
        ".html": "report", ".htm": "report", ".fasta": "genomic_summary", ".fa": "genomic_summary",
        ".fna": "genomic_summary", ".fastq": "genomic_summary", ".fq": "genomic_summary",
        ".vcf": "variant_data", ".bed": "genomic_annotation", ".gff": "genomic_annotation", ".gtf": "genomic_annotation",
        ".png": "image_evidence", ".jpg": "image_evidence", ".jpeg": "image_evidence", ".webp": "image_evidence",
    }[suffix]
    return ExtractionResult(clean_sections, source_type, MIME_TYPES[suffix], tuple(warnings), author)
