from __future__ import annotations

import hashlib
import io
import json
import platform
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from biointel.projects.professional import build_html_report, frame_profile


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        number = float(value)
        return number if np.isfinite(number) else None
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if pd.isna(value) if not isinstance(value, (str, bytes, bytearray)) else False:
        return None
    return value


def dataframe_digest(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_run_manifest(
    *,
    project_code: str,
    project_name: str,
    parameters: Mapping[str, Any],
    inputs: Mapping[str, pd.DataFrame],
    outputs: Mapping[str, pd.DataFrame],
    scientific_boundary: str,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    input_records = {
        name: {"rows": int(len(frame)), "columns": int(len(frame.columns)), "sha256": dataframe_digest(frame)}
        for name, frame in sorted(inputs.items())
    }
    output_records = {
        name: {"rows": int(len(frame)), "columns": int(len(frame.columns)), "sha256": dataframe_digest(frame)}
        for name, frame in sorted(outputs.items())
    }
    fingerprint_payload = json.dumps(
        {
            "project_code": project_code,
            "parameters": _json_safe(parameters),
            "inputs": input_records,
            "outputs": output_records,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": "2.0",
        "project_code": project_code,
        "project_name": project_name,
        "generated_at_utc": generated_at,
        "run_fingerprint": hashlib.sha256(fingerprint_payload).hexdigest(),
        "parameters": _json_safe(parameters),
        "inputs": input_records,
        "outputs": output_records,
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "executable": Path(sys.executable).name,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "input_profiles": {name: frame_profile(name, frame) for name, frame in sorted(inputs.items())},
        "output_profiles": {name: frame_profile(name, frame) for name, frame in sorted(outputs.items())},
        "scientific_boundary": scientific_boundary,
    }


def build_project_bundle(
    *,
    project_code: str,
    project_name: str,
    parameters: Mapping[str, Any],
    inputs: Mapping[str, pd.DataFrame],
    outputs: Mapping[str, pd.DataFrame],
    scientific_boundary: str,
    notes: str = "",
    quality_gates: pd.DataFrame | None = None,
    summary: Mapping[str, Any] | None = None,
    methods: Sequence[str] = (),
    model_card: Mapping[str, Any] | None = None,
) -> bytes:
    manifest = build_run_manifest(
        project_code=project_code,
        project_name=project_name,
        parameters=parameters,
        inputs=inputs,
        outputs=outputs,
        scientific_boundary=scientific_boundary,
    )
    gates = quality_gates.copy() if quality_gates is not None else pd.DataFrame()
    report_html = build_html_report(
        project_name=project_name,
        project_code=project_code,
        run_fingerprint=manifest["run_fingerprint"],
        summary=summary or {"Input tables": len(inputs), "Output tables": len(outputs)},
        parameters=parameters,
        quality_gates=gates,
        tables=outputs,
        scientific_boundary=scientific_boundary,
        methods=methods or ("Validated tabular inputs", "Executed deterministic local analysis", "Generated checksum-bound outputs"),
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        archive.writestr("report.html", report_html)
        archive.writestr("quality_gates.csv", gates.to_csv(index=False, lineterminator="\n"))
        archive.writestr("methods.json", json.dumps(list(methods), indent=2))
        if model_card is not None:
            archive.writestr("model_card.json", json.dumps(dict(model_card), indent=2, sort_keys=True, default=str))
        archive.writestr(
            "README.txt",
            "\n".join(
                [
                    project_name,
                    "=" * len(project_name),
                    f"Project code: {project_code}",
                    f"Run fingerprint: {manifest['run_fingerprint']}",
                    "",
                    "Scientific boundary:",
                    scientific_boundary,
                    "",
                    notes.strip(),
                ]
            ).strip()
            + "\n",
        )
        for name, frame in sorted(inputs.items()):
            archive.writestr(f"inputs/{name}.csv", frame.to_csv(index=False, lineterminator="\n"))
        for name, frame in sorted(outputs.items()):
            archive.writestr(f"outputs/{name}.csv", frame.to_csv(index=False, lineterminator="\n"))
    payload = buffer.getvalue()
    # Reopen once to verify the generated research archive before returning it.
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ValueError(f"Generated project bundle failed integrity verification at {bad_member}")
    return payload
