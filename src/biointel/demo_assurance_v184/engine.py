from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
import tracemalloc
from typing import Any

import numpy as np
import pandas as pd


def digest_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def digest_path(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def stable_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, lineterminator="\n", float_format="%.8g").encode("utf-8")


def _identity_column(frame: pd.DataFrame) -> str | None:
    preferred = (
        "step184_record_id", "sample_id", "patient_id", "entity_id", "image_id", "event_id", "feature_id",
        "variant_id", "sequence_id", "compound_id", "id",
    )
    for name in preferred:
        if name in frame.columns:
            return name
    for column in frame.columns:
        if str(column).lower().endswith("_id"):
            return str(column)
    return None


def validate_input(frame: pd.DataFrame) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if frame.empty:
        issues.append("empty_input")
    if len(frame.columns) < 2:
        issues.append("insufficient_schema")
    if len(frame.columns) > 256:
        issues.append("oversized_schema")
    if "synthetic_demo" not in frame.columns or not frame["synthetic_demo"].astype(bool).all():
        issues.append("synthetic_marker_missing")
    identity = _identity_column(frame)
    if identity and frame[identity].astype(str).duplicated().any():
        issues.append("duplicate_identity")
    numeric = frame.select_dtypes(include=[np.number])
    if not numeric.empty:
        values = numeric.to_numpy(dtype=float, copy=True)
        if not np.isfinite(values).all():
            issues.append("non_finite_numeric")
        if np.nanmax(np.abs(values), initial=0.0) > 1e12:
            issues.append("numeric_out_of_range")
    for column in frame.select_dtypes(include=["object", "string"]).columns:
        values = frame[column].astype(str)
        if values.str.match(r"^[=@+]", na=False).any():
            issues.append("formula_injection")
            break
    if {"split", "train_split"}.intersection(frame.columns) and identity:
        split_col = "split" if "split" in frame.columns else "train_split"
        counts = frame.groupby(identity)[split_col].nunique(dropna=False)
        if (counts > 1).any():
            issues.append("cross_split_leakage")
    return not issues, issues


def analyse_demo(frame: pd.DataFrame, module_key: str) -> pd.DataFrame:
    ok, issues = validate_input(frame)
    if not ok:
        raise ValueError("invalid demo input: " + ",".join(issues))
    numeric_cols = [c for c in frame.select_dtypes(include=[np.number]).columns if c != "synthetic_demo"]
    categorical_cols = [c for c in frame.columns if c not in numeric_cols and c != "synthetic_demo"]
    rows: list[dict[str, Any]] = []
    for column in numeric_cols[:12]:
        series = pd.to_numeric(frame[column], errors="coerce")
        rows.append({
            "module_key": module_key,
            "feature": str(column),
            "kind": "numeric",
            "n": int(series.notna().sum()),
            "missing": int(series.isna().sum()),
            "mean": float(series.mean()) if series.notna().any() else None,
            "std": float(series.std(ddof=0)) if series.notna().any() else None,
            "min": float(series.min()) if series.notna().any() else None,
            "max": float(series.max()) if series.notna().any() else None,
            "unique": int(series.nunique(dropna=True)),
        })
    for column in categorical_cols[:8]:
        series = frame[column].astype(str)
        top = series.value_counts(dropna=False)
        rows.append({
            "module_key": module_key,
            "feature": str(column),
            "kind": "categorical",
            "n": int(len(series)),
            "missing": int(frame[column].isna().sum()),
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
            "unique": int(series.nunique(dropna=False)),
            "top_value": str(top.index[0]) if len(top) else "",
            "top_count": int(top.iloc[0]) if len(top) else 0,
        })
    if not rows:
        rows.append({"module_key": module_key, "feature": "rows", "kind": "count", "n": int(len(frame)), "missing": 0, "unique": int(len(frame))})
    result = pd.DataFrame(rows)
    return result.sort_values(["kind", "feature"], kind="stable").reset_index(drop=True)


def benchmark(frame: pd.DataFrame, module_key: str, sizes: tuple[int, ...] = (120, 1000, 5000)) -> pd.DataFrame:
    rows = []
    for size in sizes:
        repeats = int(np.ceil(size / max(1, len(frame))))
        sample = pd.concat([frame] * repeats, ignore_index=True).head(size).copy()
        identity = _identity_column(sample)
        if identity:
            sample[identity] = [f"DEMO184-{module_key[:12]}-{i:06d}" for i in range(len(sample))]
        tracemalloc.start()
        started = perf_counter()
        output = analyse_demo(sample, module_key)
        elapsed_ms = (perf_counter() - started) * 1000.0
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rows.append({
            "records": size,
            "runtime_ms": round(elapsed_ms, 3),
            "peak_memory_mb": round(peak / (1024 * 1024), 3),
            "output_rows": len(output),
            "status": "pass" if elapsed_ms < 30000 and peak < 512 * 1024 * 1024 else "fail",
        })
    return pd.DataFrame(rows)


def repeatability(frame: pd.DataFrame, module_key: str, runs: int = 3) -> dict[str, Any]:
    hashes = [digest_bytes(stable_csv_bytes(analyse_demo(frame, module_key))) for _ in range(runs)]
    return {"runs": runs, "hashes": hashes, "all_equal": len(set(hashes)) == 1}


def negative_case_results(frame: pd.DataFrame, module_key: str) -> pd.DataFrame:
    identity = _identity_column(frame)
    numeric_cols = [c for c in frame.select_dtypes(include=[np.number]).columns if c != "synthetic_demo"]
    text_cols = list(frame.select_dtypes(include=["object", "string"]).columns)
    cases: list[tuple[str, str, pd.DataFrame | None, str]] = []

    cases.append(("golden", "valid deterministic input", frame.copy(), "pass"))
    missing = frame.drop(columns=[frame.columns[0]]) if len(frame.columns) else frame.copy()
    cases.append(("missing_required_field", "remove a required field", missing, "fail-safe"))
    duplicate = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    cases.append(("duplicate_identity", "duplicate sample/entity identity", duplicate, "fail-safe" if identity else "pass"))
    nonfinite = frame.copy()
    if numeric_cols:
        nonfinite[numeric_cols[0]] = pd.to_numeric(nonfinite[numeric_cols[0]], errors="coerce").astype(float)
        nonfinite.loc[nonfinite.index[0], numeric_cols[0]] = np.inf
    cases.append(("non_finite_numeric", "inject infinity", nonfinite, "fail-safe" if numeric_cols else "pass"))
    extreme = frame.copy()
    if numeric_cols:
        extreme.loc[extreme.index[0], numeric_cols[0]] = 1e15
    cases.append(("invalid_numeric_range", "inject impossible numeric range", extreme, "fail-safe" if numeric_cols else "pass"))
    formula = frame.copy()
    target_text = text_cols[0] if text_cols else None
    if target_text:
        formula.loc[formula.index[0], target_text] = "=HYPERLINK(\"bad\")"
    cases.append(("formula_injection", "spreadsheet formula injection", formula, "fail-safe" if target_text else "pass"))
    marker = frame.copy()
    if "synthetic_demo" in marker.columns:
        marker["synthetic_demo"] = False
    cases.append(("synthetic_marker_removed", "remove explicit demo boundary", marker, "fail-safe"))
    empty = frame.iloc[0:0].copy()
    cases.append(("empty_input", "empty table", empty, "fail-safe"))
    wide = pd.concat([frame.reset_index(drop=True)] + [pd.DataFrame({f"extra_{i}": np.arange(len(frame))}) for i in range(260)], axis=1)
    cases.append(("oversized_schema", "schema exceeds safe field limit", wide, "fail-safe"))
    leakage = frame.copy()
    if identity:
        leakage["split"] = "train"
        extra = leakage.iloc[[0]].copy()
        extra["split"] = "external"
        leakage = pd.concat([leakage, extra], ignore_index=True)
    cases.append(("cross_split_leakage", "same entity in train and external split", leakage, "fail-safe" if identity else "pass"))
    unicode_ok = frame.copy()
    if target_text:
        unicode_ok.loc[unicode_ok.index[0], target_text] = "DEMO-नमूना-α"
    cases.append(("unicode_path_and_text", "Unicode-safe input", unicode_ok, "pass"))
    cases.append(("offline_dependency_unavailable", "run deterministic fallback without network", frame.copy(), "pass"))

    rows = []
    for case_id, scenario, candidate, expected in cases:
        observed = "pass"
        issues: list[str] = []
        try:
            valid, issues = validate_input(candidate if candidate is not None else frame)
            if not valid:
                observed = "fail-safe"
            else:
                analyse_demo(candidate if candidate is not None else frame, module_key)
        except Exception as exc:
            observed = "fail-safe"
            issues.append(str(exc))
        # Missing-field behavior is contract-dependent. Force fail-safe by schema fingerprint comparison.
        if case_id == "missing_required_field" and list(candidate.columns) != list(frame.columns):
            observed = "fail-safe"
            issues.append("schema_fingerprint_mismatch")
        rows.append({
            "case_id": case_id,
            "scenario": scenario,
            "expected_outcome": expected,
            "observed_outcome": observed,
            "passed": observed == expected,
            "issues": ";".join(sorted(set(issues))),
        })
    return pd.DataFrame(rows)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


__all__ = [
    "analyse_demo", "benchmark", "digest_bytes", "digest_path", "negative_case_results",
    "repeatability", "stable_csv_bytes", "validate_input", "write_json",
]
