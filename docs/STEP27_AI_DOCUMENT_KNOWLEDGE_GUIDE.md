# Step 27 AI Document Knowledge Guide

## Supported inputs

PDF, XLSX, XLS, XLSM, DOCX, CSV, TSV, TXT, Markdown, HTML, JSON, XML,
YAML, PPTX, ODT and ODS.

## OCR policy

- `off`: never run OCR.
- `auto`: OCR only pages with little extractable text.
- `force`: OCR every PDF page.

OCR words include normalized page bounding boxes and confidence values. Numeric
or low-confidence values are flagged for human review. Corrections are stored as
separate audit records and never modify the original file.

Tesseract is a system dependency, not a Python-only package. The application
continues to extract non-scanned content when Tesseract is unavailable.

## Search and knowledge

Every completed extraction indexes paragraphs and tables into local SQLite FTS.
Scientific entities are stored separately. Cited Q&A selects passages from the
local extraction index; it does not invent an answer or contact an external AI
service.

## Dataset and evidence bridge

A reviewed table can be registered as a dataset with document/run/table
provenance. Real-evidence import requires mappings for SMILES, protein sequence,
activity value and units. Imported evidence remains pending until Step 25 human
review is completed.

## Security

- 100 MB request/document limit
- extension and true package validation
- Office archive expansion and traversal checks
- macro and embedded-object blocking by default
- PDF JavaScript/launch/automatic-action blocking
- formula-injection-safe Excel exports
- possible PII/API-key detection and optional redaction
- source files not retained by default
- output SHA-256 verification
- soft delete before permanent purge
