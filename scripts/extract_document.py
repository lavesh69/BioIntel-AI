from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.documents.service import process_document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract and index PDF, Office, structured or text documents with Step 28 "
            "OCR, provenance and scientific entity controls."
        )
    )
    parser.add_argument("path", type=Path, help="Supported document path")
    parser.add_argument("--password", default=None, help="Password for an encrypted PDF")
    parser.add_argument("--keep-source", action="store_true")
    parser.add_argument("--allow-xlsm", action="store_true")
    parser.add_argument("--allow-embedded-objects", action="store_true")
    parser.add_argument("--ocr", choices=("off", "auto", "force"), default="auto")
    parser.add_argument("--ocr-language", default="eng")
    parser.add_argument("--redact-sensitive", action="store_true")
    parser.add_argument("--duplicate-policy", choices=("warn", "reuse", "force"), default="warn")
    parser.add_argument("--project-code", default="")
    parser.add_argument("--tags", default="", help="Comma-separated tags")
    parser.add_argument("--notes", default="")
    parser.add_argument("--max-rows", type=int, default=50_000)
    parser.add_argument("--max-columns", type=int, default=256)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    source = args.path.resolve()
    if not source.is_file():
        raise SystemExit(f"Document not found: {source}")
    processed = process_document(
        source.name,
        source.read_bytes(),
        project_root=ROOT,
        password=args.password,
        keep_source=args.keep_source,
        max_rows_per_table=args.max_rows,
        max_columns=args.max_columns,
        allow_macro_workbooks=args.allow_xlsm,
        allow_embedded_objects=args.allow_embedded_objects,
        ocr_mode=args.ocr,
        ocr_language=args.ocr_language,
        redact_sensitive=args.redact_sensitive,
        duplicate_policy=args.duplicate_policy,
        project_code=args.project_code,
        tags=[value.strip() for value in args.tags.split(",") if value.strip()],
        notes=args.notes,
    )
    print(
        json.dumps(
            processed.to_dict(include_extracted_rows=False), indent=2, sort_keys=True, default=str
        )
    )


if __name__ == "__main__":
    main()
