from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_MAX_ROWS_PER_TABLE = 100_000
DEFAULT_MAX_BYTES_PER_TABLE = 16 * 1024 * 1024


def _safe_name(value: str, *, fallback: str = "table") -> str:
    stem = "".join(character if character.isalnum() or character in "-_" else "_" for character in value).strip("_")
    return stem or fallback


def _bounded_csv(
    frame: pd.DataFrame,
    *,
    max_rows: int,
    max_bytes: int,
) -> tuple[bytes, dict[str, Any]]:
    table = pd.DataFrame(frame)
    original_rows = int(len(table))
    selected_rows = min(original_rows, max(1, int(max_rows)))
    selected = table.head(selected_rows)
    payload = selected.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")

    # Reduce deterministically when wide scientific tables exceed the safe in-memory target.
    if len(payload) > max_bytes and selected_rows > 1:
        ratio = max(0.01, min(1.0, max_bytes / max(1, len(payload))))
        selected_rows = max(1, int(selected_rows * ratio * 0.95))
        selected = table.head(selected_rows)
        payload = selected.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")
        while len(payload) > max_bytes and selected_rows > 1:
            selected_rows = max(1, selected_rows // 2)
            selected = table.head(selected_rows)
            payload = selected.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")

    metadata = {
        "original_rows": original_rows,
        "exported_rows": int(selected_rows),
        "columns": int(table.shape[1]),
        "truncated": bool(selected_rows < original_rows),
        "csv_bytes": int(len(payload)),
        "dtypes": {str(column): str(dtype) for column, dtype in table.dtypes.items()},
    }
    return payload, metadata


def build_peak_bundle(
    *,
    module_key: str,
    manifest: dict[str, Any],
    tables: dict[str, pd.DataFrame] | None = None,
    notes: str = "",
    max_rows_per_table: int = DEFAULT_MAX_ROWS_PER_TABLE,
    max_bytes_per_table: int = DEFAULT_MAX_BYTES_PER_TABLE,
) -> bytes:
    """Build a deterministic, bounded and portable evidence bundle in memory.

    Large tables are explicitly truncated with a machine-readable index instead of
    silently exhausting memory or freezing a Streamlit rerun.
    """
    buffer = io.BytesIO()
    timestamp = (1980, 1, 1, 0, 0, 0)

    def write(name: str, payload: bytes) -> None:
        info = zipfile.ZipInfo(name, date_time=timestamp)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        buffer_zip.writestr(info, payload)

    table_index: dict[str, Any] = {}
    table_payloads: list[tuple[str, bytes, bytes]] = []
    used_names: dict[str, int] = {}
    for label, frame in sorted((tables or {}).items(), key=lambda item: str(item[0]).lower()):
        base = _safe_name(str(label))
        count = used_names.get(base, 0)
        used_names[base] = count + 1
        safe = base if count == 0 else f"{base}_{count + 1}"
        csv_payload, metadata = _bounded_csv(
            pd.DataFrame(frame),
            max_rows=max_rows_per_table,
            max_bytes=max_bytes_per_table,
        )
        metadata["source_label"] = str(label)
        metadata["file"] = f"tables/{safe}.csv"
        metadata["schema_file"] = f"tables/{safe}.schema.json"
        table_index[safe] = metadata
        schema_payload = json.dumps(
            {
                "source_label": str(label),
                "columns": list(map(str, pd.DataFrame(frame).columns)),
                "dtypes": metadata["dtypes"],
                "original_rows": metadata["original_rows"],
                "exported_rows": metadata["exported_rows"],
                "truncated": metadata["truncated"],
            },
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        table_payloads.append((safe, csv_payload, schema_payload))

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as buffer_zip:
        write("manifest.json", json.dumps(manifest, indent=2, sort_keys=True, default=str).encode("utf-8"))
        readme = (
            "BioIntel AI peak-potential evidence bundle\n"
            f"Module: {module_key}\n"
            f"Manifest SHA-256: {manifest.get('manifest_sha256', 'not available')}\n\n"
            "This package preserves bounded result tables, quality findings and provenance. "
            "Table export limits are declared in bundle_index.json. It does not imply clinical, "
            "regulatory or experimental validation.\n"
        )
        if notes.strip():
            readme += "\nNotes\n-----\n" + notes.strip() + "\n"
        write("README.txt", readme.encode("utf-8"))
        write(
            "bundle_index.json",
            json.dumps(
                {
                    "schema": "biointel.peak_bundle.v2",
                    "module_key": module_key,
                    "max_rows_per_table": int(max_rows_per_table),
                    "max_bytes_per_table": int(max_bytes_per_table),
                    "tables": table_index,
                },
                indent=2,
                sort_keys=True,
            ).encode("utf-8"),
        )
        for safe, csv_payload, schema_payload in table_payloads:
            write(f"tables/{safe}.csv", csv_payload)
            write(f"tables/{safe}.schema.json", schema_payload)
    return buffer.getvalue()


def safe_bundle_name(module_key: str) -> str:
    stem = "".join(character if character.isalnum() or character in "-_" else "-" for character in module_key).strip("-")
    return f"{stem or 'biointel'}-peak-evidence.zip"
