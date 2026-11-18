from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FlowQCResult:
    summary: dict[str, Any]
    checks: pd.DataFrame
    channel_metrics: pd.DataFrame
    flagged_events: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass(frozen=True)
class GateResult:
    name: str
    parent: str
    mask: pd.Series
    events: pd.DataFrame
    summary: dict[str, Any]


@dataclass(frozen=True)
class ControlAuditResult:
    summary: dict[str, Any]
    checks: pd.DataFrame
    normalized_manifest: pd.DataFrame
    missing_controls: tuple[str, ...] = ()


@dataclass(frozen=True)
class FlowReleaseGate:
    summary: dict[str, Any]
    checks: pd.DataFrame
    blockers: tuple[str, ...]
    release_ready: bool


def _numeric_frame(events: pd.DataFrame, channels: Iterable[str]) -> pd.DataFrame:
    selected = [str(channel) for channel in channels]
    missing = [channel for channel in selected if channel not in events.columns]
    if missing:
        raise ValueError("Missing flow-cytometry channels: " + ", ".join(missing))
    frame = events[selected].apply(pd.to_numeric, errors="coerce")
    if frame.empty:
        raise ValueError("Flow-cytometry event table is empty")
    return frame


def event_table_sha256(events: pd.DataFrame) -> str:
    stable = events.to_csv(index=False, lineterminator="\n", na_rep="<NA>").encode("utf-8")
    return sha256(stable).hexdigest()


def validate_compensation_matrix(matrix: pd.DataFrame, channels: Iterable[str]) -> pd.DataFrame:
    channel_list = [str(channel) for channel in channels]
    if not channel_list:
        raise ValueError("Select at least one fluorescence channel")
    work = matrix.copy()
    if work.shape[0] != work.shape[1]:
        raise ValueError("Compensation matrix must be square")
    if work.shape[0] != len(channel_list):
        raise ValueError("Compensation matrix dimensions must match selected channels")
    work.index = channel_list
    work.columns = channel_list
    work = work.apply(pd.to_numeric, errors="coerce")
    if work.isna().any().any():
        raise ValueError("Compensation matrix contains non-numeric or missing values")
    diagonal = np.diag(work.to_numpy(dtype=float))
    if not np.allclose(diagonal, 1.0, atol=0.15):
        raise ValueError("Compensation matrix diagonal should be approximately 1.0")
    condition_number = float(np.linalg.cond(work.to_numpy(dtype=float)))
    if not np.isfinite(condition_number) or condition_number > 1e6:
        raise ValueError("Compensation matrix is singular or numerically unstable")
    return work


def apply_compensation(events: pd.DataFrame, channels: Iterable[str], matrix: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    channel_list = [str(channel) for channel in channels]
    observed = _numeric_frame(events, channel_list)
    validated = validate_compensation_matrix(matrix, channel_list)
    inverse = np.linalg.inv(validated.to_numpy(dtype=float))
    compensated_values = observed.to_numpy(dtype=float) @ inverse.T
    compensated = events.copy()
    compensated.loc[:, channel_list] = compensated_values
    return compensated, {
        "channels": channel_list,
        "condition_number": float(np.linalg.cond(validated.to_numpy(dtype=float))),
        "matrix": validated.to_dict(orient="split"),
        "method": "linear spillover inversion",
    }


def arcsinh_transform(events: pd.DataFrame, channels: Iterable[str], cofactor: float = 150.0) -> pd.DataFrame:
    if cofactor <= 0:
        raise ValueError("Arcsinh cofactor must be positive")
    channel_list = [str(channel) for channel in channels]
    numeric = _numeric_frame(events, channel_list)
    transformed = events.copy()
    transformed.loc[:, channel_list] = np.arcsinh(numeric.to_numpy(dtype=float) / float(cofactor))
    return transformed


def rectangular_gate(
    events: pd.DataFrame,
    x_channel: str,
    y_channel: str,
    *,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    name: str = "Rectangle gate",
    parent: str = "All events",
) -> GateResult:
    numeric = _numeric_frame(events, [x_channel, y_channel])
    if x_min >= x_max or y_min >= y_max:
        raise ValueError("Gate minimums must be lower than maximums")
    mask = numeric[x_channel].between(x_min, x_max, inclusive="both") & numeric[y_channel].between(y_min, y_max, inclusive="both")
    selected = events.loc[mask].copy()
    return GateResult(
        name=name,
        parent=parent,
        mask=mask,
        events=selected,
        summary={
            "gate": name,
            "parent": parent,
            "x_channel": x_channel,
            "y_channel": y_channel,
            "x_min": float(x_min),
            "x_max": float(x_max),
            "y_min": float(y_min),
            "y_max": float(y_max),
            "parent_events": int(len(events)),
            "selected_events": int(mask.sum()),
            "fraction_parent": float(mask.mean()) if len(mask) else 0.0,
        },
    )


def polygon_gate(
    events: pd.DataFrame,
    x_channel: str,
    y_channel: str,
    vertices: Iterable[tuple[float, float]],
    *,
    name: str = "Polygon gate",
    parent: str = "All events",
) -> GateResult:
    points = np.asarray(list(vertices), dtype=float)
    if points.ndim != 2 or points.shape[0] < 3 or points.shape[1] != 2:
        raise ValueError("A polygon gate requires at least three (x, y) vertices")
    numeric = _numeric_frame(events, [x_channel, y_channel])
    x = numeric[x_channel].to_numpy(dtype=float)
    y = numeric[y_channel].to_numpy(dtype=float)
    inside = np.zeros(len(numeric), dtype=bool)
    j = len(points) - 1
    for i in range(len(points)):
        xi, yi = points[i]
        xj, yj = points[j]
        intersects = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-12) + xi)
        inside ^= intersects
        j = i
    mask = pd.Series(inside, index=events.index)
    selected = events.loc[mask].copy()
    return GateResult(
        name=name,
        parent=parent,
        mask=mask,
        events=selected,
        summary={
            "gate": name,
            "parent": parent,
            "x_channel": x_channel,
            "y_channel": y_channel,
            "vertices": points.tolist(),
            "parent_events": int(len(events)),
            "selected_events": int(mask.sum()),
            "fraction_parent": float(mask.mean()) if len(mask) else 0.0,
        },
    )


def singlet_gate(
    events: pd.DataFrame,
    area_channel: str,
    height_channel: str,
    *,
    ratio_tolerance: float = 0.18,
    name: str = "Singlets",
    parent: str = "All events",
) -> GateResult:
    if ratio_tolerance <= 0 or ratio_tolerance >= 1:
        raise ValueError("Singlet ratio tolerance must be between 0 and 1")
    numeric = _numeric_frame(events, [area_channel, height_channel])
    area = numeric[area_channel].replace(0, np.nan)
    ratio = numeric[height_channel] / area
    median = float(ratio.median())
    mask = ratio.between(median * (1 - ratio_tolerance), median * (1 + ratio_tolerance), inclusive="both").fillna(False)
    selected = events.loc[mask].copy()
    return GateResult(
        name=name,
        parent=parent,
        mask=mask,
        events=selected,
        summary={
            "gate": name,
            "parent": parent,
            "area_channel": area_channel,
            "height_channel": height_channel,
            "ratio_median": median,
            "ratio_tolerance": float(ratio_tolerance),
            "parent_events": int(len(events)),
            "selected_events": int(mask.sum()),
            "fraction_parent": float(mask.mean()) if len(mask) else 0.0,
        },
    )


def fmo_threshold(control_events: pd.DataFrame, channel: str, quantile: float = 0.995) -> float:
    if quantile <= 0.5 or quantile >= 1:
        raise ValueError("FMO threshold quantile must be between 0.5 and 1")
    values = _numeric_frame(control_events, [channel])[channel].dropna()
    if len(values) < 20:
        raise ValueError("At least 20 control events are required for an FMO threshold")
    return float(values.quantile(quantile))


def flow_qc(
    events: pd.DataFrame,
    *,
    event_id_column: str | None = None,
    time_column: str | None = None,
    channels: Iterable[str] | None = None,
    minimum_events: int = 1_000,
) -> FlowQCResult:
    if not isinstance(events, pd.DataFrame) or events.empty:
        raise ValueError("Flow-cytometry event table is empty")
    selected = list(channels) if channels is not None else list(events.select_dtypes(include=[np.number]).columns)
    if not selected:
        raise ValueError("No numeric flow-cytometry channels were detected")
    numeric = _numeric_frame(events, selected)
    checks: list[dict[str, Any]] = []
    checks.append({"check": "Minimum event count", "status": "pass" if len(events) >= minimum_events else "review", "detail": f"{len(events):,} events; target ≥{minimum_events:,}"})
    missing = int(numeric.isna().sum().sum())
    checks.append({"check": "Numeric channel completeness", "status": "pass" if missing == 0 else "review", "detail": f"{missing:,} missing channel values"})
    duplicate_count = int(events[event_id_column].astype(str).duplicated().sum()) if event_id_column and event_id_column in events.columns else int(events.astype(str).duplicated().sum())
    checks.append({"check": "Duplicate events", "status": "pass" if duplicate_count == 0 else "review", "detail": f"{duplicate_count:,} duplicates"})

    channel_rows: list[dict[str, Any]] = []
    flagged_mask = pd.Series(False, index=events.index)
    for channel in selected:
        values = numeric[channel]
        finite = values[np.isfinite(values)]
        if finite.empty:
            channel_rows.append({"channel": channel, "events": 0, "missing": len(values), "p01": np.nan, "median": np.nan, "p99": np.nan, "dynamic_range": np.nan, "saturation_fraction": np.nan, "zero_fraction": np.nan})
            continue
        p01, median, p99 = np.nanpercentile(finite, [1, 50, 99])
        observed_max = float(finite.max())
        saturation_fraction = float((finite >= observed_max).mean())
        zero_fraction = float((finite == 0).mean())
        dynamic_range = float(p99 - p01)
        channel_rows.append({
            "channel": channel,
            "events": int(finite.size),
            "missing": int(values.isna().sum()),
            "p01": float(p01),
            "median": float(median),
            "p99": float(p99),
            "dynamic_range": dynamic_range,
            "saturation_fraction": saturation_fraction,
            "zero_fraction": zero_fraction,
        })
        if saturation_fraction > 0.01:
            flagged_mask |= values >= observed_max
    channel_metrics = pd.DataFrame(channel_rows)
    saturated = int((channel_metrics["saturation_fraction"] > 0.01).sum()) if not channel_metrics.empty else 0
    checks.append({"check": "Channel saturation", "status": "review" if saturated else "pass", "detail": f"{saturated} channels above 1% maximum-value saturation"})

    time_drift = np.nan
    if time_column and time_column in events.columns:
        time_values = pd.to_numeric(events[time_column], errors="coerce")
        if time_values.notna().sum() >= 20:
            reference_channel = selected[0]
            ranked_time = time_values.rank(pct=True)
            early = numeric.loc[ranked_time <= 0.1, reference_channel]
            late = numeric.loc[ranked_time >= 0.9, reference_channel]
            denominator = max(abs(float(early.median())), 1e-12)
            time_drift = float((late.median() - early.median()) / denominator)
            checks.append({"check": "Acquisition-time drift", "status": "review" if abs(time_drift) > 0.2 else "pass", "detail": f"First-to-last decile median shift {time_drift:.1%} in {reference_channel}"})
        else:
            checks.append({"check": "Acquisition-time drift", "status": "review", "detail": "Insufficient valid time values"})
    else:
        checks.append({"check": "Acquisition-time metadata", "status": "review", "detail": "No time channel selected"})

    summary = {
        "schema": "biointel.flow_qc.v2",
        "events": int(len(events)),
        "channels": selected,
        "missing_values": missing,
        "duplicate_events": duplicate_count,
        "channels_with_saturation": saturated,
        "time_drift_fraction": None if not np.isfinite(time_drift) else time_drift,
        "event_table_sha256": event_table_sha256(events),
    }
    return FlowQCResult(summary, pd.DataFrame(checks), channel_metrics, events.loc[flagged_mask].head(500).copy())


def population_summary(populations: dict[str, pd.DataFrame], channels: Iterable[str]) -> pd.DataFrame:
    channel_list = [channel for channel in channels]
    rows: list[dict[str, Any]] = []
    parent_count = len(populations.get("All events", pd.DataFrame()))
    for name, frame in populations.items():
        row: dict[str, Any] = {
            "population": name,
            "events": int(len(frame)),
            "fraction_all": float(len(frame) / parent_count) if parent_count else np.nan,
        }
        for channel in channel_list:
            if channel in frame.columns:
                values = pd.to_numeric(frame[channel], errors="coerce")
                row[f"{channel}_median"] = float(values.median())
                row[f"{channel}_p90"] = float(values.quantile(0.9))
        rows.append(row)
    return pd.DataFrame(rows)


def gate_audit_table(gates: Iterable[GateResult]) -> pd.DataFrame:
    return pd.DataFrame([gate.summary for gate in gates])


_CONTROL_ALIASES = {
    "type": "control_type",
    "control": "control_type",
    "control kind": "control_type",
    "marker": "channel",
    "detector": "channel",
    "event_count": "events",
    "n_events": "events",
    "panel": "panel_version",
    "instrument": "instrument_id",
}


def _normalise_control_type(value: Any) -> str:
    token = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "single": "single_stain",
        "single_stained": "single_stain",
        "single_colour": "single_stain",
        "single_color": "single_stain",
        "unlabelled": "unstained",
        "unlabeled": "unstained",
        "fluorescence_minus_one": "fmo",
        "fluorescence_minus_1": "fmo",
    }
    return aliases.get(token, token)


def validate_control_manifest(
    manifest: pd.DataFrame,
    fluorescence_channels: Iterable[str],
    *,
    require_fmo_channels: Iterable[str] = (),
    minimum_events: int = 500,
) -> ControlAuditResult:
    """Validate flow controls without silently treating study samples as controls.

    Expected fields are ``control_type``, ``channel`` and ``events``. Optional
    but release-relevant fields include ``panel_version`` and ``instrument_id``.
    """
    channels = [str(channel).strip() for channel in fluorescence_channels if str(channel).strip()]
    required_fmo = [str(channel).strip() for channel in require_fmo_channels if str(channel).strip()]
    if not channels:
        raise ValueError("At least one fluorescence channel is required for control auditing")
    if minimum_events < 20:
        raise ValueError("minimum_events must be at least 20")
    if not isinstance(manifest, pd.DataFrame) or manifest.empty:
        empty = pd.DataFrame(columns=["control_type", "channel", "events", "panel_version", "instrument_id"])
        missing = ("unstained", *tuple(f"single_stain:{channel}" for channel in channels), *tuple(f"fmo:{channel}" for channel in required_fmo))
        checks = pd.DataFrame([
            {"check": "Control manifest", "status": "block", "detail": "No control manifest was supplied."},
        ])
        return ControlAuditResult(
            summary={"schema": "biointel.flow_controls.v2", "controls": 0, "channels": channels, "release_ready": False},
            checks=checks,
            normalized_manifest=empty,
            missing_controls=missing,
        )

    work = manifest.copy()
    renamed: dict[Any, str] = {}
    for column in work.columns:
        normal = str(column).strip().lower().replace("_", " ")
        renamed[column] = _CONTROL_ALIASES.get(normal, str(column).strip().lower().replace(" ", "_"))
    work = work.rename(columns=renamed)
    required_columns = {"control_type", "channel", "events"}
    missing_columns = sorted(required_columns - set(work.columns))
    if missing_columns:
        raise ValueError("Control manifest is missing columns: " + ", ".join(missing_columns))
    for optional in ("panel_version", "instrument_id", "lot_id", "acquisition_date", "file_name"):
        if optional not in work.columns:
            work[optional] = ""
    work["control_type"] = work["control_type"].map(_normalise_control_type)
    work["channel"] = work["channel"].fillna("").astype(str).str.strip()
    work["events"] = pd.to_numeric(work["events"], errors="coerce")
    work["panel_version"] = work["panel_version"].fillna("").astype(str).str.strip()
    work["instrument_id"] = work["instrument_id"].fillna("").astype(str).str.strip()

    checks: list[dict[str, Any]] = []
    missing_controls: list[str] = []

    invalid_event_rows = int((work["events"].isna() | (work["events"] < 0)).sum())
    checks.append({
        "check": "Control event counts",
        "status": "pass" if invalid_event_rows == 0 else "block",
        "detail": f"{invalid_event_rows} controls have missing or invalid event counts.",
    })

    unstained = work.loc[work["control_type"] == "unstained"]
    unstained_ok = bool((unstained["events"] >= minimum_events).any())
    if not unstained_ok:
        missing_controls.append("unstained")
    checks.append({
        "check": "Unstained control",
        "status": "pass" if unstained_ok else "block",
        "detail": f"Required ≥{minimum_events:,} events; qualifying controls: {int((unstained['events'] >= minimum_events).sum())}.",
    })

    for channel in channels:
        single = work.loc[(work["control_type"] == "single_stain") & (work["channel"].str.casefold() == channel.casefold())]
        ok = bool((single["events"] >= minimum_events).any())
        if not ok:
            missing_controls.append(f"single_stain:{channel}")
        checks.append({
            "check": f"Single-stain control · {channel}",
            "status": "pass" if ok else "block",
            "detail": f"Required ≥{minimum_events:,} events; qualifying controls: {int((single['events'] >= minimum_events).sum())}.",
        })

    for channel in required_fmo:
        fmo = work.loc[(work["control_type"] == "fmo") & (work["channel"].str.casefold() == channel.casefold())]
        ok = bool((fmo["events"] >= minimum_events).any())
        if not ok:
            missing_controls.append(f"fmo:{channel}")
        checks.append({
            "check": f"FMO control · {channel}",
            "status": "pass" if ok else "block",
            "detail": f"Required ≥{minimum_events:,} events; qualifying controls: {int((fmo['events'] >= minimum_events).sum())}.",
        })

    panel_values = sorted(value for value in work["panel_version"].unique().tolist() if value)
    instrument_values = sorted(value for value in work["instrument_id"].unique().tolist() if value)
    panel_ok = len(panel_values) == 1 and bool(panel_values)
    instrument_ok = len(instrument_values) == 1 and bool(instrument_values)
    checks.extend([
        {
            "check": "Locked panel version",
            "status": "pass" if panel_ok else "review",
            "detail": panel_values[0] if panel_ok else ("Missing panel version." if not panel_values else f"Multiple panel versions: {', '.join(panel_values)}"),
        },
        {
            "check": "Instrument identity",
            "status": "pass" if instrument_ok else "review",
            "detail": instrument_values[0] if instrument_ok else ("Missing instrument identifier." if not instrument_values else f"Multiple instruments: {', '.join(instrument_values)}"),
        },
    ])
    status_values = [str(row["status"]) for row in checks]
    release_ready = "block" not in status_values and panel_ok and instrument_ok
    summary = {
        "schema": "biointel.flow_controls.v2",
        "controls": int(len(work)),
        "channels": channels,
        "required_fmo_channels": required_fmo,
        "minimum_events": int(minimum_events),
        "panel_versions": panel_values,
        "instrument_ids": instrument_values,
        "missing_controls": missing_controls,
        "manifest_sha256": event_table_sha256(work.fillna("")),
        "release_ready": bool(release_ready),
    }
    return ControlAuditResult(summary, pd.DataFrame(checks), work, tuple(missing_controls))


def derive_compensation_matrix(
    single_stain_events: Mapping[str, pd.DataFrame],
    channels: Iterable[str],
    *,
    unstained_events: pd.DataFrame | None = None,
    positive_quantile: float = 0.80,
    minimum_positive_events: int = 50,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Derive a spillover matrix from explicit single-stain controls.

    Rows are detector channels and columns are source fluorochromes, matching
    :func:`apply_compensation`'s ``observed = true @ spill.T`` convention.
    """
    channel_list = [str(channel) for channel in channels]
    if len(channel_list) < 2:
        raise ValueError("At least two fluorescence channels are required")
    if not 0.5 <= positive_quantile < 1:
        raise ValueError("positive_quantile must be in [0.5, 1)")
    if minimum_positive_events < 20:
        raise ValueError("minimum_positive_events must be at least 20")
    missing = [channel for channel in channel_list if channel not in single_stain_events]
    if missing:
        raise ValueError("Missing single-stain event tables: " + ", ".join(missing))

    if unstained_events is not None and not unstained_events.empty:
        baseline_frame = _numeric_frame(unstained_events, channel_list)
        baseline = baseline_frame.median(axis=0)
        baseline_sha = event_table_sha256(unstained_events)
    else:
        pooled_lows: list[pd.Series] = []
        for frame in single_stain_events.values():
            numeric = _numeric_frame(frame, channel_list)
            pooled_lows.append(numeric.quantile(0.10))
        baseline = pd.concat(pooled_lows, axis=1).median(axis=1)
        baseline_sha = None

    spill = pd.DataFrame(np.eye(len(channel_list)), index=channel_list, columns=channel_list, dtype=float)
    source_details: list[dict[str, Any]] = []
    for source in channel_list:
        numeric = _numeric_frame(single_stain_events[source], channel_list).dropna()
        if len(numeric) < minimum_positive_events:
            raise ValueError(f"Single-stain control for {source} has fewer than {minimum_positive_events} complete events")
        cutoff = float(numeric[source].quantile(positive_quantile))
        positives = numeric.loc[numeric[source] >= cutoff]
        if len(positives) < minimum_positive_events:
            positives = numeric.nlargest(min(minimum_positive_events, len(numeric)), source)
        source_signal = float(positives[source].median() - baseline[source])
        if not np.isfinite(source_signal) or source_signal <= 0:
            raise ValueError(f"Single-stain control for {source} has no usable positive signal above baseline")
        for detector in channel_list:
            if detector == source:
                spill.loc[detector, source] = 1.0
                continue
            detector_signal = float(positives[detector].median() - baseline[detector])
            spill.loc[detector, source] = float(max(0.0, detector_signal / source_signal))
        source_details.append({
            "source_channel": source,
            "events": int(len(numeric)),
            "positive_events": int(len(positives)),
            "positive_cutoff": cutoff,
            "source_signal": source_signal,
            "table_sha256": event_table_sha256(single_stain_events[source]),
        })
    validated = validate_compensation_matrix(spill, channel_list)
    return validated, {
        "schema": "biointel.flow_compensation_derivation.v2",
        "method": "robust single-stain median spillover",
        "channels": channel_list,
        "positive_quantile": float(positive_quantile),
        "minimum_positive_events": int(minimum_positive_events),
        "unstained_table_sha256": baseline_sha,
        "source_controls": source_details,
        "condition_number": float(np.linalg.cond(validated.to_numpy(dtype=float))),
        "matrix": validated.to_dict(orient="split"),
    }


def audit_gate_hierarchy(gates: Iterable[GateResult], *, minimum_events: int = 50) -> pd.DataFrame:
    gate_list = list(gates)
    rows: list[dict[str, Any]] = []
    known = {"All events"}
    seen: set[str] = set()
    for gate in gate_list:
        summary = gate.summary
        name = str(gate.name).strip()
        parent = str(gate.parent).strip()
        parent_events = int(summary.get("parent_events", len(gate.mask)))
        selected_events = int(summary.get("selected_events", len(gate.events)))
        reported_fraction = float(summary.get("fraction_parent", selected_events / parent_events if parent_events else 0.0))
        expected_fraction = selected_events / parent_events if parent_events else 0.0
        checks = {
            "unique_name": bool(name and name not in seen),
            "known_parent": parent in known,
            "count_consistency": 0 <= selected_events <= parent_events,
            "fraction_consistency": 0.0 <= reported_fraction <= 1.0 and abs(reported_fraction - expected_fraction) <= 1e-6,
            "minimum_events": selected_events >= minimum_events,
            "mask_consistency": int(gate.mask.sum()) == selected_events and len(gate.events) == selected_events,
        }
        failed = [key for key, value in checks.items() if not value]
        rows.append({
            "gate": name,
            "parent": parent,
            "parent_events": parent_events,
            "selected_events": selected_events,
            "fraction_parent": reported_fraction,
            "status": "pass" if not failed else ("review" if failed == ["minimum_events"] else "block"),
            "failed_checks": ", ".join(failed),
        })
        if checks["unique_name"]:
            seen.add(name)
            known.add(name)
    if not rows:
        rows.append({
            "gate": "No gates",
            "parent": "",
            "parent_events": 0,
            "selected_events": 0,
            "fraction_parent": 0.0,
            "status": "block",
            "failed_checks": "gating hierarchy is empty",
        })
    return pd.DataFrame(rows)


def flow_release_gate(
    qc: FlowQCResult,
    controls: ControlAuditResult,
    compensation_provenance: Mapping[str, Any],
    gates: Iterable[GateResult],
    *,
    reviewer: str = "",
    instrument_qc_confirmed: bool = False,
    source_mode: str = "uploaded",
    minimum_gate_events: int = 50,
) -> FlowReleaseGate:
    hierarchy = audit_gate_hierarchy(gates, minimum_events=minimum_gate_events)
    qc_block = bool((qc.checks["status"].astype(str).str.casefold() == "block").any()) if not qc.checks.empty else True
    control_block = bool((controls.checks["status"].astype(str).str.casefold() == "block").any()) if not controls.checks.empty else True
    hierarchy_block = bool((hierarchy["status"].astype(str).str.casefold() == "block").any())
    source_token = str(source_mode or "").casefold()
    demo_source = any(token in source_token for token in ("demo", "synthetic", "demonstration"))
    comp_applied = bool(compensation_provenance.get("applied") or compensation_provenance.get("method"))
    comp_has_evidence = bool(compensation_provenance.get("control_manifest_sha256") or compensation_provenance.get("source_controls") or compensation_provenance.get("matrix_source") == "instrument/export")

    check_rows = [
        {"check": "Acquisition QC", "status": "pass" if not qc_block else "block", "detail": "No blocking acquisition-QC findings." if not qc_block else "Blocking acquisition-QC findings remain."},
        {"check": "Required controls", "status": "pass" if controls.summary.get("release_ready") and not control_block else "block", "detail": "Control set is complete and metadata-locked." if controls.summary.get("release_ready") and not control_block else "Control set or metadata is incomplete."},
        {"check": "Compensation provenance", "status": "pass" if comp_applied and comp_has_evidence else "block", "detail": "Compensation is linked to explicit controls/instrument provenance." if comp_applied and comp_has_evidence else "Compensation lacks explicit single-stain or instrument provenance."},
        {"check": "Gate hierarchy", "status": "pass" if not hierarchy_block else "block", "detail": "Gate parentage, counts and masks are internally consistent." if not hierarchy_block else "Gate hierarchy contains blocking inconsistencies."},
        {"check": "Instrument QC", "status": "pass" if instrument_qc_confirmed else "block", "detail": "Daily instrument QC was confirmed." if instrument_qc_confirmed else "Daily instrument QC was not confirmed."},
        {"check": "Independent reviewer", "status": "pass" if str(reviewer).strip() else "block", "detail": str(reviewer).strip() or "Reviewer identity is missing."},
        {"check": "Source eligibility", "status": "block" if demo_source else "pass", "detail": "Demonstration/synthetic data cannot be released." if demo_source else "Uploaded/non-demo source declared."},
    ]
    checks = pd.DataFrame(check_rows)
    blockers = tuple(checks.loc[checks["status"] == "block", "check"].astype(str).tolist())
    release_ready = not blockers
    summary = {
        "schema": "biointel.flow_release_gate.v2",
        "release_ready": bool(release_ready),
        "blockers": list(blockers),
        "reviewer": str(reviewer).strip(),
        "instrument_qc_confirmed": bool(instrument_qc_confirmed),
        "source_mode": source_mode,
        "qc_sha256": sha256(qc.checks.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest(),
        "controls_sha256": controls.summary.get("manifest_sha256"),
        "gate_audit_sha256": sha256(hierarchy.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest(),
    }
    return FlowReleaseGate(summary, checks, blockers, release_ready)
