# Step 26 Document Intelligence Guide

## Supported files

- PDF (`.pdf`)
- Excel Open XML (`.xlsx`)
- Legacy Excel (`.xls`, requires `xlrd`)
- Macro-enabled Excel (`.xlsm`, opt-in reading; macros never run)
- Word Open XML (`.docx`)

## Extraction outputs

Every successful run generates:

- Excel workbook with Summary, Extracted Text and one sheet per detected table
- DOCX extraction report
- PDF extraction report
- Full JSON result
- ZIP containing CSV tables, text and metadata
- Complete ZIP containing all output formats

## History

`reports/document_history.sqlite3` records source filename, type, size, SHA-256, timestamps,
status, pages/sheets, table/row counts, warnings, errors and generated output checksums.
Source documents are not retained unless the operator enables **Keep source**.

## Safety controls

- 100 MB maximum document size
- extension/content signature validation
- Office ZIP expansion and member-count limits
- path-traversal blocking
- macro workbooks blocked by default
- macros never executed
- formula-like strings neutralized in generated Excel files
- API downloads restricted to the managed extraction output directory

## Scanned PDFs

Step 26 flags PDFs with little extractable text. OCR is intentionally not automatic because OCR
can produce incorrect scientific values. Convert the PDF to a reviewed searchable PDF before
using extracted results for scientific decisions.

## Windows usage

- Drag a document onto `EXTRACT_DOCUMENT_WINDOWS.bat`
- Run the application and open **Document Intelligence Center**
- Re-download old results from **Document Extraction History**
- Verify the release with `VERIFY_STEP26_WINDOWS.bat`
