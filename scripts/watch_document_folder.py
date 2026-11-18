from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.documents.security import SUPPORTED_EXTENSIONS, sha256_bytes
from biointel.documents.service import process_document


def load_state(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return {}


def save_state(path: Path, state: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def scan_once(
    folder: Path, state_path: Path, *, ocr_mode: str, recursive: bool
) -> dict[str, object]:
    state = load_state(state_path)
    pattern = "**/*" if recursive else "*"
    processed, skipped, errors = [], [], []
    for path in sorted(folder.glob(pattern)):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            data = path.read_bytes()
            digest = sha256_bytes(data)
            key = str(path.resolve())
            if state.get(key) == digest:
                skipped.append(str(path))
                continue
            result = process_document(
                path.name,
                data,
                project_root=ROOT,
                keep_source=False,
                ocr_mode=ocr_mode,
                duplicate_policy="reuse",
                project_code=folder.name,
                tags=["folder-watch"],
                notes=f"Imported from watched folder: {folder}",
            )
            state[key] = digest
            processed.append({"path": str(path), "run_id": result.run_id})
        except Exception as exc:
            errors.append({"path": str(path), "error": str(exc)})
    save_state(state_path, state)
    return {"processed": processed, "skipped": skipped, "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Watch a local folder for supported Step 28 documents."
    )
    parser.add_argument("folder", type=Path)
    parser.add_argument(
        "--interval", type=int, default=0, help="Seconds between scans; 0 runs once"
    )
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--ocr", choices=("off", "auto", "force"), default="auto")
    args = parser.parse_args()
    folder = args.folder.resolve()
    if not folder.is_dir():
        raise SystemExit(f"Folder not found: {folder}")
    state_path = ROOT / "reports" / "document_folder_watch_state.json"
    while True:
        result = scan_once(folder, state_path, ocr_mode=args.ocr, recursive=args.recursive)
        print(json.dumps(result, indent=2, default=str))
        if args.interval <= 0:
            break
        time.sleep(max(60, args.interval))


if __name__ == "__main__":
    main()
