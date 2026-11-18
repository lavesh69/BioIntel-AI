from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_rdml(data: bytes) -> pd.DataFrame:
    """Parse core reaction/sample/target/Cq fields from an RDML XML export."""

    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid RDML XML: {exc}") from exc
    sample_types: dict[str, str] = {}
    for element in root.iter():
        if _local_name(element.tag) != "sample":
            continue
        sample_id = element.attrib.get("id", "")
        sample_type = ""
        for child in element.iter():
            if _local_name(child.tag) in {"type", "description"} and child.text:
                sample_type = child.text.strip()
                break
        if sample_id:
            sample_types[sample_id] = sample_type
    rows: list[dict[str, object]] = []
    for reaction in root.iter():
        if _local_name(reaction.tag) != "react":
            continue
        well = reaction.attrib.get("id", "")
        sample_id = ""
        for child in reaction:
            if _local_name(child.tag) == "sample":
                sample_id = child.attrib.get("id", "")
                break
        for data_node in reaction.iter():
            if _local_name(data_node.tag) != "data":
                continue
            target = ""
            cq = None
            for child in data_node.iter():
                name = _local_name(child.tag)
                if name == "tar":
                    target = child.attrib.get("id", "")
                elif name in {"cq", "ct"} and child.text:
                    try:
                        cq = float(child.text.strip())
                    except ValueError:
                        cq = None
            if target or cq is not None:
                sample_type = sample_types.get(sample_id, "")
                normalized_type = sample_type.lower().replace(" ", "_")
                role = "control" if normalized_type in {"ntc", "nac", "ntc-nrt", "negative_control"} else "target"
                rows.append({
                    "sample": sample_id or f"reaction_{well}", "gene": target, "ct": cq,
                    "role": role, "well": well, "rdml_sample_type": sample_type,
                    "instrument_format": "RDML",
                })
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("RDML file contains no reaction Cq/Ct measurements that could be parsed.")
    return frame


def _canonical(column: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(column).strip().lower())


@dataclass(frozen=True)
class InstrumentProfile:
    name: str
    signatures: tuple[str, ...]
    mappings: dict[str, tuple[str, ...]]


INSTRUMENT_PROFILES: tuple[InstrumentProfile, ...] = (
    InstrumentProfile("QuantStudio", ("wellposition", "ctmean"), {
        "well": ("well", "wellposition"), "sample": ("sample", "samplename"),
        "gene": ("target", "targetname", "assay"), "ct": ("ct", "ctmean", "cq"),
        "task": ("task", "sampletype"), "quantity": ("quantity", "quantitymean"),
    }),
    InstrumentProfile("Bio-Rad CFX", ("content", "cqmean"), {
        "well": ("well",), "sample": ("sample", "samplename"), "gene": ("target", "fluor"),
        "ct": ("cq", "cqmean", "ct"), "task": ("content", "sampletype"),
    }),
    InstrumentProfile("Roche LightCycler", ("pos", "crossingpoint"), {
        "well": ("pos", "position"), "sample": ("sample", "samplename"),
        "gene": ("target", "channel"), "ct": ("crossingpoint", "cp", "cq", "ct"),
    }),
    InstrumentProfile("SoftMax Pro", ("well", "read"), {
        "well": ("well",), "sample": ("sample", "name"), "response": ("read", "od", "absorbance"),
        "concentration": ("concentration", "conc"), "type": ("type", "sampletype"),
    }),
    InstrumentProfile("BioTek Gen5", ("well", "result"), {
        "well": ("well",), "sample": ("sampleid", "sample"), "response": ("result", "od", "absorbance"),
        "type": ("sampletype", "type"),
    }),
)


def detect_instrument_profile(frame: pd.DataFrame) -> InstrumentProfile | None:
    columns = {_canonical(column) for column in frame.columns}
    scored: list[tuple[int, InstrumentProfile]] = []
    for profile in INSTRUMENT_PROFILES:
        signature_score = sum(signature in columns for signature in profile.signatures)
        mapping_score = sum(any(alias in columns for alias in aliases) for aliases in profile.mappings.values())
        scored.append((3 * signature_score + mapping_score, profile))
    score, profile = max(scored, key=lambda item: item[0])
    return profile if score >= 3 else None


def normalize_instrument_export(frame: pd.DataFrame, *, profile: str | None = None, preserve_source_columns: bool = True) -> pd.DataFrame:
    selected = None
    if profile:
        selected = next((item for item in INSTRUMENT_PROFILES if item.name.lower() == profile.lower()), None)
        if selected is None:
            raise ValueError(f"Unknown instrument profile: {profile}")
    else:
        selected = detect_instrument_profile(frame)
    if selected is None:
        # Preserve generic table schemas exactly. Instrument metadata belongs in
        # DataFrame attributes unless a known export profile is positively detected.
        output = frame.copy()
        output.attrs["instrument_profile"] = "Generic table"
        output.attrs["canonical_source_columns"] = {}
        return output
    by_canonical = {_canonical(column): column for column in frame.columns}
    canonical_data: dict[str, pd.Series] = {}
    source_map: dict[str, str] = {}
    for target, aliases in selected.mappings.items():
        source = next((by_canonical[alias] for alias in aliases if alias in by_canonical), None)
        if source is not None:
            canonical_data[target] = frame[source]
            source_map[target] = str(source)
    output = frame.copy() if preserve_source_columns else pd.DataFrame(index=frame.index)
    for target, values in canonical_data.items():
        output[target] = values
    if "ct" in output:
        output["ct"] = pd.to_numeric(output["ct"], errors="coerce")
    if "response" in output:
        output["response"] = pd.to_numeric(output["response"], errors="coerce")
    output["instrument_format"] = selected.name
    output.attrs["instrument_profile"] = selected.name
    output.attrs["canonical_source_columns"] = source_map
    return output


def _read_delimited(data: bytes, suffix: str) -> pd.DataFrame:
    text = data.decode("utf-8-sig", errors="replace")
    separator = "\t" if suffix in {".tsv", ".txt"} or text.count("\t") > text.count(",") else ","
    # Instrument exports frequently include metadata lines before the actual header.
    lines = text.splitlines()
    header_index = 0
    for index, line in enumerate(lines[:80]):
        cells = [cell.strip() for cell in line.split(separator)]
        normalized = {_canonical(cell) for cell in cells if cell.strip()}
        if len(normalized) >= 2 and normalized.intersection({"well", "wellposition", "sample", "samplename", "cq", "ct", "result", "read"}):
            header_index = index
            break
    return pd.read_csv(io.StringIO("\n".join(lines[header_index:])), sep=separator, low_memory=False)


def read_lab_table(
    uploaded_file: Any,
    *,
    sheet_name: str | int | None = 0,
    normalize_instrument: bool = True,
    qualification_metadata: Mapping[str, Any] | None = None,
    reviewer: str = "",
    reviewed_at_utc: str = "",
    raw_file_preserved: bool = True,
) -> pd.DataFrame:
    """Read instrument exports, retain raw provenance and attach fail-closed qualification.

    Existing callers remain compatible. Qualification metadata is optional, but an
    incomplete manifest is explicitly marked ``Blocked`` rather than treated as a
    qualified laboratory import.
    """

    name = str(getattr(uploaded_file, "name", "upload")).lower()
    data = uploaded_file.getvalue()
    suffix = Path(name).suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        frame = pd.read_excel(io.BytesIO(data), sheet_name=sheet_name)
    elif suffix == ".rdml":
        frame = parse_rdml(data)
    else:
        frame = _read_delimited(data, suffix)
    output = normalize_instrument_export(frame) if normalize_instrument and suffix != ".rdml" else frame

    from .instrument_qualification import audit_instrument_import, qualification_to_dict

    profile = str(output.attrs.get("instrument_profile", output.get("instrument_format", pd.Series(["Generic table"])).iloc[0]))
    source_map = output.attrs.get("canonical_source_columns", {})
    qualification = audit_instrument_import(
        output,
        raw_bytes=data,
        metadata=qualification_metadata,
        source_map=source_map,
        profile=profile,
        raw_file_preserved=raw_file_preserved,
        reviewer=reviewer,
        reviewed_at_utc=reviewed_at_utc,
    )
    output.attrs["raw_sha256"] = qualification.raw_sha256
    output.attrs["instrument_qualification"] = qualification_to_dict(qualification)
    return output


def list_excel_sheets(uploaded_file: Any) -> list[str]:
    name = str(getattr(uploaded_file, "name", "")).lower()
    if not name.endswith((".xlsx", ".xlsm", ".xls")):
        return []
    with pd.ExcelFile(io.BytesIO(uploaded_file.getvalue())) as workbook:
        return list(workbook.sheet_names)
