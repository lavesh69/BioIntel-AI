from __future__ import annotations

import hashlib
import html
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class QualityGate:
    gate_id: str
    name: str
    status: str
    score: float
    evidence: str
    recommendation: str


@dataclass(frozen=True)
class ConfidenceInterval:
    estimate: float
    lower: float
    upper: float
    confidence: float
    samples: int


def benjamini_hochberg(p_values: Sequence[float]) -> np.ndarray:
    values = np.asarray(p_values, dtype=float)
    if values.size == 0:
        return values
    safe = np.where(np.isfinite(values), np.clip(values, 0.0, 1.0), 1.0)
    order = np.argsort(safe)
    ranked = safe[order]
    adjusted = ranked * len(ranked) / np.arange(1, len(ranked) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    output = np.empty_like(adjusted)
    output[order] = np.clip(adjusted, 0.0, 1.0)
    return output


def bootstrap_ci(
    values: Sequence[float],
    *,
    statistic: str = "mean",
    confidence: float = 0.95,
    samples: int = 1000,
    random_state: int = 42,
) -> ConfidenceInterval:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return ConfidenceInterval(float("nan"), float("nan"), float("nan"), confidence, 0)
    if statistic == "median":
        function = np.median
    elif statistic == "mean":
        function = np.mean
    else:
        raise ValueError("statistic must be 'mean' or 'median'")
    rng = np.random.default_rng(random_state)
    estimate = float(function(array))
    if array.size == 1:
        return ConfidenceInterval(estimate, estimate, estimate, confidence, 1)
    draws = rng.choice(array, size=(max(int(samples), 100), array.size), replace=True)
    statistics = function(draws, axis=1)
    alpha = (1.0 - confidence) / 2.0
    lower, upper = np.quantile(statistics, [alpha, 1.0 - alpha])
    return ConfidenceInterval(estimate, float(lower), float(upper), confidence, int(array.size))


def population_stability_index(reference: Sequence[float], current: Sequence[float], *, bins: int = 10) -> float:
    left = np.asarray(reference, dtype=float)
    right = np.asarray(current, dtype=float)
    left = left[np.isfinite(left)]
    right = right[np.isfinite(right)]
    if left.size < 5 or right.size < 5:
        return float("nan")
    quantiles = np.unique(np.quantile(left, np.linspace(0.0, 1.0, bins + 1)))
    if len(quantiles) < 3:
        return 0.0
    quantiles[0], quantiles[-1] = -np.inf, np.inf
    left_counts = np.histogram(left, bins=quantiles)[0].astype(float)
    right_counts = np.histogram(right, bins=quantiles)[0].astype(float)
    left_rate = np.clip(left_counts / max(left_counts.sum(), 1), 1e-6, None)
    right_rate = np.clip(right_counts / max(right_counts.sum(), 1), 1e-6, None)
    return float(np.sum((right_rate - left_rate) * np.log(right_rate / left_rate)))


def numeric_drift_report(reference: pd.DataFrame, current: pd.DataFrame) -> pd.DataFrame:
    common = [column for column in reference.columns if column in current.columns]
    rows: list[dict[str, Any]] = []
    for column in common:
        ref = pd.to_numeric(reference[column], errors="coerce").dropna()
        cur = pd.to_numeric(current[column], errors="coerce").dropna()
        if len(ref) < 5 or len(cur) < 5:
            continue
        psi = population_stability_index(ref, cur)
        denominator = float(ref.std(ddof=0)) or 1.0
        standardized_mean_shift = abs(float(cur.mean() - ref.mean())) / denominator
        rows.append(
            {
                "feature": column,
                "reference_mean": float(ref.mean()),
                "current_mean": float(cur.mean()),
                "standardized_mean_shift": standardized_mean_shift,
                "population_stability_index": psi,
                "drift_status": "high" if (psi >= 0.25 or standardized_mean_shift >= 1.0) else "review" if (psi >= 0.1 or standardized_mean_shift >= 0.5) else "stable",
            }
        )
    return pd.DataFrame(rows).sort_values(["drift_status", "population_stability_index"], ascending=[True, False]).reset_index(drop=True) if rows else pd.DataFrame(columns=["feature", "reference_mean", "current_mean", "standardized_mean_shift", "population_stability_index", "drift_status"])


def quality_gate_table(gates: Iterable[QualityGate]) -> pd.DataFrame:
    return pd.DataFrame([asdict(gate) for gate in gates])


def overall_quality_score(gates: Iterable[QualityGate]) -> float:
    records = list(gates)
    if not records:
        return 0.0
    weights = {"pass": 1.0, "review": 0.6, "block": 0.0}
    return float(np.mean([float(gate.score) * weights.get(gate.status, 0.0) for gate in records]))


def frame_profile(name: str, frame: pd.DataFrame) -> dict[str, Any]:
    missing = int(frame.isna().sum().sum())
    duplicates = int(frame.duplicated().sum())
    numeric = frame.select_dtypes(include=[np.number])
    digest = hashlib.sha256(frame.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest()
    return {
        "name": name,
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "missing_cells": missing,
        "duplicate_rows": duplicates,
        "numeric_columns": int(len(numeric.columns)),
        "sha256": digest,
    }


def model_card_payload(
    *,
    project_code: str,
    title: str,
    intended_use: str,
    out_of_scope: Sequence[str],
    methodology: Sequence[str],
    metrics: Mapping[str, Any],
    validation: Sequence[str],
    limitations: Sequence[str],
    quality_gates: pd.DataFrame,
    run_fingerprint: str,
) -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "project_code": project_code,
        "title": title,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "run_fingerprint": run_fingerprint,
        "intended_use": intended_use,
        "out_of_scope": list(out_of_scope),
        "methodology": list(methodology),
        "metrics": dict(metrics),
        "validation": list(validation),
        "limitations": list(limitations),
        "quality_gates": quality_gates.to_dict(orient="records"),
    }


def build_html_report(
    *,
    project_name: str,
    project_code: str,
    run_fingerprint: str,
    summary: Mapping[str, Any],
    parameters: Mapping[str, Any],
    quality_gates: pd.DataFrame,
    tables: Mapping[str, pd.DataFrame],
    scientific_boundary: str,
    methods: Sequence[str],
) -> bytes:
    def esc(value: Any) -> str:
        return html.escape(str(value))

    summary_rows = "".join(f"<tr><th>{esc(key)}</th><td>{esc(value)}</td></tr>" for key, value in summary.items())
    parameter_rows = "".join(f"<tr><th>{esc(key)}</th><td>{esc(value)}</td></tr>" for key, value in parameters.items())
    method_items = "".join(f"<li>{esc(item)}</li>" for item in methods)
    sections: list[str] = []
    for name, frame in tables.items():
        preview = frame.head(100).copy()
        sections.append(f"<section><h2>{esc(name.replace('_', ' ').title())}</h2><p>{len(frame):,} rows × {len(frame.columns):,} columns; first 100 rows shown.</p>{preview.to_html(index=False, border=0, classes='data-table', escape=True)}</section>")
    gates_html = quality_gates.to_html(index=False, border=0, classes="data-table", escape=True) if not quality_gates.empty else "<p>No gates recorded.</p>"
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(project_name)} · Research Report</title>
<style>
:root{{--ink:#102337;--muted:#5c6f82;--line:#dce4eb;--paper:#fff;--soft:#f5f8fb;--accent:#0e7490;--warn:#9a6700}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--soft);color:var(--ink);font:15px/1.55 Inter,Arial,sans-serif}}
main{{max-width:1120px;margin:32px auto;padding:0 24px}} header,section{{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:24px;margin-bottom:18px;box-shadow:0 10px 30px rgba(16,35,55,.05)}}
h1{{margin:0 0 6px;font-size:30px}} h2{{font-size:19px;margin:0 0 14px}} .meta{{color:var(--muted)}} .boundary{{border-left:4px solid var(--warn);padding:12px 16px;background:#fff9e8}}
table{{width:100%;border-collapse:collapse;overflow:auto;display:block}} th,td{{padding:9px 11px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}} th{{background:var(--soft);font-weight:650}}
code{{font-size:12px;word-break:break-all}} footer{{color:var(--muted);padding:16px 4px 40px}}
</style></head><body><main>
<header><p class="meta">BioIntel AI · {esc(project_code)}</p><h1>{esc(project_name)}</h1><p class="meta">Run fingerprint: <code>{esc(run_fingerprint)}</code></p></header>
<section><h2>Executive summary</h2><table>{summary_rows}</table></section>
<section><h2>Scientific boundary</h2><div class="boundary">{esc(scientific_boundary)}</div></section>
<section><h2>Methods</h2><ol>{method_items}</ol></section>
<section><h2>Parameters</h2><table>{parameter_rows}</table></section>
<section><h2>Quality gates</h2>{gates_html}</section>
{''.join(sections)}
<footer>Generated by BioIntel AI. This report is an implementation/research artifact and does not replace qualified scientific, clinical or regulatory review.</footer>
</main></body></html>"""
    return document.encode("utf-8")


def deterministic_seed_from_fingerprint(fingerprint: str) -> int:
    return int(hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:8], 16)
