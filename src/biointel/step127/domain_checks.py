from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PairAudit:
    paired: int
    missing_mates: tuple[str, ...]
    duplicate_ids: tuple[str, ...]
    status: str


def _read_id(name: str) -> tuple[str, str | None]:
    stem = Path(name).name
    for suffix in (".fastq.gz", ".fq.gz", ".fastq", ".fq"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    for marker in ("_R1", "_R2", "_1", "_2", ".R1", ".R2"):
        if stem.endswith(marker):
            return stem[: -len(marker)], "R1" if marker.endswith("1") else "R2"
    return stem, None


def audit_fastq_pairs(filenames: Iterable[str]) -> PairAudit:
    pairs: dict[str, set[str]] = {}
    duplicates: list[str] = []
    seen: set[str] = set()
    for filename in filenames:
        if filename in seen:
            duplicates.append(filename)
        seen.add(filename)
        sample, mate = _read_id(filename)
        pairs.setdefault(sample, set())
        if mate:
            pairs[sample].add(mate)
    missing = tuple(sorted(sample for sample, mates in pairs.items() if mates and mates != {"R1", "R2"}))
    paired = sum(mates == {"R1", "R2"} for mates in pairs.values())
    status = "blocked" if missing or duplicates else "ready"
    return PairAudit(paired, missing, tuple(sorted(set(duplicates))), status)


def normalize_variant(chrom: str, position: int, reference: str, alternate: str) -> tuple[str, int, str, str]:
    chrom = str(chrom).strip()
    ref = str(reference).upper().strip()
    alt = str(alternate).upper().strip()
    pos = int(position)
    if not chrom or pos < 1 or not ref or not alt:
        raise ValueError("chromosome, positive position, reference and alternate are required")
    if any(base not in "ACGTN" for base in ref + alt):
        raise ValueError("Only A/C/G/T/N alleles are supported by the built-in normalizer")
    while len(ref) > 1 and len(alt) > 1 and ref[-1] == alt[-1]:
        ref, alt = ref[:-1], alt[:-1]
    while len(ref) > 1 and len(alt) > 1 and ref[0] == alt[0]:
        ref, alt, pos = ref[1:], alt[1:], pos + 1
    return chrom, pos, ref, alt


def build_design_matrix(metadata: pd.DataFrame, *, group: str, covariates: Sequence[str] = ()) -> pd.DataFrame:
    required = [group, *covariates]
    missing = [column for column in required if column not in metadata.columns]
    if missing:
        raise ValueError(f"Missing design columns: {', '.join(missing)}")
    design = pd.get_dummies(metadata[required].copy(), columns=[column for column in required if metadata[column].dtype == object], drop_first=True, dtype=float)
    design.insert(0, "intercept", 1.0)
    if design.shape[0] < design.shape[1]:
        raise ValueError("Design has fewer samples than coefficients")
    if np.linalg.matrix_rank(design.to_numpy(dtype=float)) < design.shape[1]:
        raise ValueError("Design matrix is rank deficient")
    return design


def filter_qpcr_roles(frame: pd.DataFrame, *, role_column: str) -> dict[str, pd.DataFrame]:
    if role_column not in frame.columns:
        raise ValueError(f"Role column not found: {role_column}")
    normalized = frame[role_column].fillna("").astype(str).str.strip().str.lower().str.replace("_", " ")
    aliases = {
        "target": "target", "reference": "reference", "housekeeping": "reference",
        "ntc": "ntc", "no template control": "ntc", "no rt": "no-rt", "no-rt": "no-rt",
        "positive control": "positive-control", "extraction control": "extraction-control", "ignore": "ignore",
    }
    mapped = normalized.map(aliases)
    unknown = frame[mapped.isna() & normalized.ne("")].copy()
    result: dict[str, pd.DataFrame] = {key: frame[mapped.eq(key)].copy() for key in sorted(set(aliases.values()))}
    result["unknown"] = unknown
    return result


def safe_calibration_inverse(response: float, *, response_min: float, response_max: float, inverse_function) -> tuple[float | None, str]:
    value = float(response)
    low, high = sorted((float(response_min), float(response_max)))
    if value < low:
        return None, "Below calibration response"
    if value > high:
        return None, "Above calibration response; dilute and repeat"
    concentration = float(inverse_function(value))
    if not np.isfinite(concentration) or concentration < 0:
        return None, "Calibration inversion failed"
    return concentration, "Within calibration range"


def split_bioprocess_batches(frame: pd.DataFrame, *, batch_column: str, time_column: str) -> dict[str, pd.DataFrame]:
    if batch_column not in frame.columns or time_column not in frame.columns:
        raise ValueError("Batch and time columns are required")
    output: dict[str, pd.DataFrame] = {}
    for batch, group in frame.groupby(batch_column, dropna=False, sort=False):
        ordered = group.sort_values(time_column).copy()
        times = pd.to_numeric(ordered[time_column], errors="coerce")
        if times.isna().any() or times.duplicated().any() or not times.is_monotonic_increasing:
            raise ValueError(f"Batch {batch!r} requires unique increasing time points")
        output[str(batch)] = ordered
    return output


def validate_column_mapping(mapping: Mapping[str, str], *, aliases_allowed: Iterable[tuple[str, str]] = ()) -> None:
    reverse: dict[str, list[str]] = {}
    for semantic, source in mapping.items():
        if not source:
            continue
        reverse.setdefault(source, []).append(semantic)
    allowed = {frozenset(pair) for pair in aliases_allowed}
    conflicts = []
    for source, semantics in reverse.items():
        if len(semantics) > 1 and frozenset(semantics) not in allowed:
            conflicts.append(f"{source}: {', '.join(semantics)}")
    if conflicts:
        raise ValueError("One source column cannot map to multiple meanings: " + "; ".join(conflicts))
