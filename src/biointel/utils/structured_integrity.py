from __future__ import annotations

import csv
import json
import sqlite3
from biointel.database.core import managed_connect
import zipfile
from pathlib import Path
from typing import Any

import yaml

_SCANNED_ROOTS = ("config", "data", "reports")
_IGNORED_PARTS = {"runtime_logs", "test-shards", "step87", "step88", "__pycache__"}


def _safe_zip_name(name: str) -> bool:
    candidate = Path(name)
    return not name.startswith(("/", "\\")) and ".." not in candidate.parts


def _check_delimited(path: Path, delimiter: str) -> tuple[bool, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.reader(handle, delimiter=delimiter)
        try:
            header = next(rows)
        except StopIteration:
            return True, "empty file"
        expected = len(header)
        if expected == 0:
            return False, "missing header"
        for number, row in enumerate(rows, start=2):
            if len(row) != expected:
                return False, f"row {number} has {len(row)} columns; expected {expected}"
    return True, f"{expected} columns"


def _check_file(path: Path) -> tuple[bool, str]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        json.loads(path.read_text(encoding="utf-8"))
        return True, "valid JSON"
    if suffix == ".jsonl":
        count = 0
        for count, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip():
                json.loads(line)
        return True, f"{count} JSONL lines"
    if suffix in {".yaml", ".yml"}:
        yaml.safe_load(path.read_text(encoding="utf-8"))
        return True, "valid YAML"
    if suffix == ".csv":
        return _check_delimited(path, ",")
    if suffix in {".tsv", ".tab"}:
        return _check_delimited(path, "\t")
    if suffix in {".sqlite", ".sqlite3", ".db"}:
        connection = managed_connect(f"file:{path}?mode=ro", uri=True, timeout=10)
        try:
            row = connection.execute("PRAGMA quick_check").fetchone()
        finally:
            connection.close()
        ok = bool(row and str(row[0]).lower() == "ok")
        return ok, str(row[0] if row else "no quick_check result")
    if suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            duplicates = len(names) - len(set(names))
            unsafe = [name for name in names if not _safe_zip_name(name)]
            bad = archive.testzip()
        if duplicates or unsafe or bad:
            return False, f"duplicates={duplicates}, unsafe={len(unsafe)}, bad={bad}"
        return True, f"{len(names)} members"
    return True, "not a structured format"


def scan_structured_assets(root: str | Path) -> dict[str, Any]:
    base = Path(root).resolve()
    suffixes = {".json", ".jsonl", ".yaml", ".yml", ".csv", ".tsv", ".tab", ".sqlite", ".sqlite3", ".db", ".zip"}
    results: list[dict[str, Any]] = []
    for folder_name in _SCANNED_ROOTS:
        folder = base / folder_name
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            relative = path.relative_to(base)
            if any(part in _IGNORED_PARTS for part in relative.parts):
                continue
            try:
                passed, detail = _check_file(path)
            except Exception as exc:  # scanner must report rather than crash
                passed, detail = False, f"{type(exc).__name__}: {exc}"
            results.append({"path": relative.as_posix(), "passed": bool(passed), "detail": detail})
    failures = [item for item in results if not item["passed"]]
    return {
        "schema": "biointel.structured-integrity.v1",
        "checked": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "complete": not failures,
        "failures": failures,
        "results": results,
    }
