from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

ASSAY_SCHEMAS: dict[str, dict[str, tuple[str, ...]]] = {
    "qpcr": {
        "sample": ("sample", "sample_id", "sample name", "specimen", "id"),
        "target_ct": ("target_ct", "target ct", "ct_target", "cq_target", "target_cq", "cq mean", "cq", "ct mean"),
        "reference_ct": ("reference_ct", "reference ct", "ct_reference", "cq_reference", "ref_ct", "housekeeping_ct", "reference cq", "endogenous control cq"),
        "group": ("group", "condition", "treatment", "cohort"),
        "replicate": ("replicate", "technical_replicate", "tech_rep", "well_replicate"),
        "well": ("well", "well_position", "position"),
    },
    "elisa": {
        "type": ("type", "sample_type", "well_type", "role"),
        "name": ("name", "sample", "sample_id", "standard_name"),
        "concentration": ("concentration", "conc", "standard_concentration", "x"),
        "absorbance": ("absorbance", "od", "optical_density", "response", "signal", "od450", "read", "result", "raw data"),
        "dilution_factor": ("dilution_factor", "dilution", "df"),
        "expected_concentration": ("expected_concentration", "nominal_concentration", "spike_expected", "target_concentration"),
        "well": ("well", "well_position", "position"),
        "plate": ("plate", "plate_id", "run"),
    },
    "enzyme": {
        "substrate": ("substrate", "substrate_mm", "substrate_concentration", "s"),
        "velocity": ("velocity", "rate", "initial_velocity", "v"),
        "condition": ("condition", "inhibitor_condition", "treatment"),
        "inhibitor": ("inhibitor", "inhibitor_concentration", "inhibitor_um", "i"),
        "replicate": ("replicate", "rep", "technical_replicate"),
        "weight": ("weight", "inverse_variance_weight"),
    },
    "bioprocess": {
        "time": ("time", "time_h", "hours", "elapsed_time"),
        "biomass": ("biomass", "od", "od600", "dcw", "x"),
        "substrate": ("substrate", "substrate_g_l", "glucose", "s"),
        "product": ("product", "product_g_l", "titre", "titer", "p"),
        "replicate": ("replicate", "batch", "run", "reactor"),
        "batch": ("batch", "batch_id", "run_id", "reactor_id"),
        "feed": ("feed", "feed_rate", "feed_volume"),
        "volume": ("volume", "working_volume", "reactor_volume", "volume_l"),
        "bleed": ("bleed", "bleed_rate", "harvest_rate", "perfusion_bleed"),
        "ph": ("ph",),
        "do": ("do", "dissolved_oxygen", "do_percent"),
        "temperature": ("temperature", "temp", "temperature_c"),
        "agitation": ("agitation", "rpm"),
        "airflow": ("airflow", "vvm", "gas_flow"),
        "our": ("our", "oxygen_uptake_rate"),
        "cer": ("cer", "carbon_dioxide_evolution_rate"),
        "kla": ("kla", "k_l_a", "oxygen_transfer_coefficient"),
        "oxygen_saturation": ("oxygen_saturation", "c_star", "oxygen_solubility"),
        "event": ("event", "process_event", "event_type"),
    },
}


@dataclass(frozen=True)
class SchemaAudit:
    assay: str
    mapping: dict[str, str]
    missing_required: tuple[str, ...]
    unused_columns: tuple[str, ...]
    duplicate_columns: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.missing_required and not self.duplicate_columns


def _normalise(name: object) -> str:
    value = str(name).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def infer_column_mapping(frame: pd.DataFrame, assay: str) -> dict[str, str]:
    schema = ASSAY_SCHEMAS.get(assay.lower())
    if schema is None:
        raise ValueError(f"Unknown assay schema: {assay}")
    normalised = {_normalise(column): str(column) for column in frame.columns}
    mapping: dict[str, str] = {}
    for canonical, aliases in schema.items():
        candidates = (_normalise(canonical), *(_normalise(alias) for alias in aliases))
        for candidate in candidates:
            if candidate in normalised:
                mapping[canonical] = normalised[candidate]
                break
    return mapping


def audit_schema(
    frame: pd.DataFrame,
    assay: str,
    *,
    required: Iterable[str],
    mapping: dict[str, str] | None = None,
) -> SchemaAudit:
    resolved = dict(mapping or infer_column_mapping(frame, assay))
    missing = tuple(sorted(column for column in required if column not in resolved))
    mapped_values = [str(value) for value in resolved.values()]
    duplicates = tuple(sorted({value for value in mapped_values if mapped_values.count(value) > 1}))
    unused = tuple(str(column) for column in frame.columns if str(column) not in set(mapped_values))
    return SchemaAudit(assay.lower(), resolved, missing, unused, duplicates)


def column_mapping_ready(mapping: dict[str, str], *, required: Iterable[str]) -> bool:
    """Return True only for a complete one-to-one source mapping."""
    required_set = {str(column) for column in required}
    if not required_set.issubset(mapping):
        return False
    sources = [str(source) for source in mapping.values()]
    return len(sources) == len(set(sources))


def apply_column_mapping(
    frame: pd.DataFrame,
    mapping: dict[str, str],
    *,
    required: Iterable[str] = (),
    preserve_unmapped: bool = False,
    metadata_prefix: str = "meta__",
    allow_duplicate_sources: bool = False,
) -> pd.DataFrame:
    """Apply an explicit canonical mapping without silently reusing one source column.

    ``preserve_unmapped`` keeps instrument/run metadata in a namespaced form so
    provenance is not discarded during analysis. Duplicate source mappings are
    blocked by default because mapping one instrument column to two biological
    meanings can produce plausible but invalid results.
    """

    required_set = set(required)
    missing = sorted(column for column in required_set if column not in mapping)
    if missing:
        raise ValueError("Required column mapping is incomplete: " + ", ".join(missing))
    sources = [str(source) for source in mapping.values()]
    duplicates = sorted({source for source in sources if sources.count(source) > 1})
    if duplicates and not allow_duplicate_sources:
        raise ValueError(
            "Each source column can map to only one canonical field. Duplicate mappings: "
            + ", ".join(duplicates)
        )
    selected: dict[str, pd.Series] = {}
    for canonical, source in mapping.items():
        if source not in frame.columns:
            raise ValueError(f"Mapped source column '{source}' does not exist.")
        selected[canonical] = frame[source]
    output = pd.DataFrame(selected, index=frame.index).copy()
    if preserve_unmapped:
        used = set(mapping.values())
        for source in frame.columns:
            if source in used:
                continue
            name = f"{metadata_prefix}{_normalise(source) or 'column'}"
            candidate = name
            suffix = 2
            while candidate in output.columns:
                candidate = f"{name}_{suffix}"
                suffix += 1
            output[candidate] = frame[source]
    return output


def parse_well(value: object, *, plate_format: int = 96) -> tuple[str, int]:
    match = re.fullmatch(r"\s*([A-Za-z]+)\s*0*([1-9][0-9]*)\s*", str(value))
    if not match:
        raise ValueError(f"Invalid well position: {value}")
    row = match.group(1).upper()
    column = int(match.group(2))
    if plate_format == 96:
        valid_rows, maximum_column = tuple("ABCDEFGH"), 12
    elif plate_format == 384:
        valid_rows, maximum_column = tuple(chr(code) for code in range(ord("A"), ord("P") + 1)), 24
    else:
        raise ValueError("Plate format must be 96 or 384.")
    if row not in valid_rows or not 1 <= column <= maximum_column:
        raise ValueError(f"Well {row}{column} is outside a {plate_format}-well plate.")
    return row, column


def plate_map_audit(
    frame: pd.DataFrame,
    *,
    well_column: str = "well",
    plate_column: str | None = None,
    plate_format: int = 96,
) -> dict[str, object]:
    if well_column not in frame.columns:
        return {
            "plate_format": plate_format,
            "wells_present": False,
            "valid_wells": 0,
            "invalid_wells": [],
            "duplicate_wells": [],
            "edge_wells": 0,
        }
    parsed: list[tuple[str, int] | None] = []
    invalid: list[str] = []
    for value in frame[well_column]:
        try:
            parsed.append(parse_well(value, plate_format=plate_format))
        except ValueError:
            parsed.append(None)
            invalid.append(str(value))
    identities = []
    for index, item in enumerate(parsed):
        if item is None:
            continue
        plate = str(frame.iloc[index][plate_column]) if plate_column and plate_column in frame.columns else "plate_1"
        identities.append((plate, item[0], item[1]))
    duplicate_wells = sorted({f"{plate}:{row}{column}" for plate, row, column in identities if identities.count((plate, row, column)) > 1})
    max_row = "H" if plate_format == 96 else "P"
    max_column = 12 if plate_format == 96 else 24
    edge = sum(1 for _, row, column in identities if row in {"A", max_row} or column in {1, max_column})
    return {
        "plate_format": plate_format,
        "wells_present": True,
        "valid_wells": len(identities),
        "invalid_wells": invalid,
        "duplicate_wells": duplicate_wells,
        "edge_wells": edge,
        "edge_fraction": edge / len(identities) if identities else 0.0,
    }


def plate_coordinates(
    frame: pd.DataFrame,
    *,
    well_column: str = "well",
    plate_format: int = 96,
) -> pd.DataFrame:
    output = frame.copy()
    rows: list[str | None] = []
    columns: list[int | None] = []
    for value in output[well_column]:
        try:
            row, column = parse_well(value, plate_format=plate_format)
        except ValueError:
            row, column = None, None
        rows.append(row)
        columns.append(column)
    output["plate_row"] = rows
    output["plate_column"] = columns
    return output


def plate_spatial_qc(
    frame: pd.DataFrame,
    *,
    value_column: str,
    well_column: str = "well",
    plate_column: str | None = None,
    plate_format: int = 96,
) -> pd.DataFrame:
    """Screen plate-level edge, row, column and local-neighbour effects.

    This is an exploratory QC screen, not a validated correction method. Results
    are returned per plate with transparent effect-size diagnostics.
    """

    if value_column not in frame.columns or well_column not in frame.columns:
        raise ValueError("Plate spatial QC requires value and well columns.")
    data = plate_coordinates(frame, well_column=well_column, plate_format=plate_format)
    data[value_column] = pd.to_numeric(data[value_column], errors="coerce")
    data = data.dropna(subset=[value_column, "plate_row", "plate_column"]).copy()
    if data.empty:
        return pd.DataFrame()
    data["_plate"] = data[plate_column].astype(str) if plate_column and plate_column in data.columns else "plate_1"
    maximum_row = "H" if plate_format == 96 else "P"
    maximum_column = 12 if plate_format == 96 else 24
    rows: list[dict[str, object]] = []
    for plate, part in data.groupby("_plate", dropna=False):
        values = part[value_column].to_numpy(float)
        overall_sd = float(np.nanstd(values, ddof=1)) if len(values) > 1 else 0.0
        edge_mask = part["plate_row"].isin(["A", maximum_row]) | part["plate_column"].isin([1, maximum_column])
        edge = part.loc[edge_mask, value_column]
        interior = part.loc[~edge_mask, value_column]
        edge_shift = float(edge.mean() - interior.mean()) if len(edge) and len(interior) else np.nan
        row_means = part.groupby("plate_row")[value_column].mean()
        column_means = part.groupby("plate_column")[value_column].mean()
        row_span = float(row_means.max() - row_means.min()) if len(row_means) > 1 else 0.0
        column_span = float(column_means.max() - column_means.min()) if len(column_means) > 1 else 0.0
        coordinates = {(str(r.plate_row), int(r.plate_column)): float(getattr(r, value_column)) for r in part.itertuples()}
        local_differences = []
        for (row, column), value in coordinates.items():
            row_number = ord(row) - ord("A")
            for row_delta, column_delta in ((1, 0), (0, 1)):
                neighbour = (chr(ord("A") + row_number + row_delta), column + column_delta)
                if neighbour in coordinates:
                    local_differences.append(abs(value - coordinates[neighbour]))
        neighbour_median = float(np.median(local_differences)) if local_differences else np.nan
        threshold = max(overall_sd, 1e-12)
        flags = []
        if np.isfinite(edge_shift) and abs(edge_shift) > threshold:
            flags.append("edge_effect")
        if row_span > 2 * threshold:
            flags.append("row_drift")
        if column_span > 2 * threshold:
            flags.append("column_drift")
        rows.append({
            "plate": str(plate),
            "wells": int(len(part)),
            "overall_sd": overall_sd,
            "edge_mean_shift": edge_shift,
            "row_mean_span": row_span,
            "column_mean_span": column_span,
            "median_adjacent_difference": neighbour_median,
            "spatial_qc": "Review" if flags else "Pass",
            "flags": ", ".join(flags),
        })
    return pd.DataFrame(rows)
