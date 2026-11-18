from __future__ import annotations

import contextlib
import json
import re
import struct
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from Bio import SeqIO

from .formats import NativeParseResult, _base_result, _compound_suffix, _open_text

def parse_wsi(path: Path, max_side: int = 2400) -> NativeParseResult:
    result = _base_result(path, "wsi")
    metadata: dict[str, Any] = {
        "container_extension": _compound_suffix(path.name),
        "openslide_available": False,
        "level_count": None,
        "dimensions": None,
        "vendor": None,
    }
    try:
        import openslide  # type: ignore

        slide = openslide.OpenSlide(str(path))
        try:
            metadata.update({
                "openslide_available": True,
                "level_count": int(slide.level_count),
                "dimensions": [list(map(int, item)) for item in slide.level_dimensions],
                "level_downsamples": [float(item) for item in slide.level_downsamples],
                "vendor": slide.properties.get(openslide.PROPERTY_NAME_VENDOR),
                "objective_power": slide.properties.get(openslide.PROPERTY_NAME_OBJECTIVE_POWER),
                "mpp_x": slide.properties.get(openslide.PROPERTY_NAME_MPP_X),
                "mpp_y": slide.properties.get(openslide.PROPERTY_NAME_MPP_Y),
            })
            width, height = slide.dimensions
            thumbnail = slide.get_thumbnail((max_side, max_side)).convert("RGB")
            array = np.asarray(thumbnail)
            result.primary = pd.DataFrame([{
                "slide_id": path.stem,
                "width": int(width),
                "height": int(height),
                "level_count": int(slide.level_count),
                "preview_width": int(array.shape[1]),
                "preview_height": int(array.shape[0]),
                "vendor": metadata.get("vendor") or "Unknown",
            }])
            result.secondary["image_pixels"] = pd.DataFrame(array.reshape(-1, 3), columns=["red", "green", "blue"]).head(100_000)
            result.total_records = int(width * height)
            result.truncated = True
        finally:
            slide.close()
    except Exception as exc:
        result.primary = pd.DataFrame([{
            "slide_id": path.stem,
            "size_bytes": path.stat().st_size,
            "extension": _compound_suffix(path.name),
            "openslide_required": True,
        }])
        result.warnings.append(f"Whole-slide pixels were not decoded: {type(exc).__name__}: {exc}")
        result.total_records = 1
        result.engine_required = "openslide"
    result.metadata = metadata
    return result


def parse_bedmethyl_native(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "bedmethyl")
    rows: list[dict[str, Any]] = []
    total = 0
    with _open_text(path) as handle:
        for line in handle:
            if not line.strip() or line.startswith(("#", "track", "browser")):
                continue
            total += 1
            if len(rows) >= max_records:
                continue
            parts = line.rstrip("\n\r").split("\t")
            if len(parts) < 3:
                parts = re.split(r"\s+", line.strip())
            if len(parts) < 3:
                continue
            try:
                start = int(float(parts[1]))
                end = int(float(parts[2]))
            except Exception:
                continue
            coverage = pd.to_numeric(parts[9], errors="coerce") if len(parts) > 9 else np.nan
            fraction = np.nan
            for candidate in parts[10:15]:
                value = pd.to_numeric(candidate, errors="coerce")
                if pd.notna(value) and 0 <= float(value) <= 100:
                    fraction = float(value) / 100.0 if float(value) > 1 else float(value)
                    break
            label = parts[3] if len(parts) > 3 else f"site_{total}"
            rows.append({
                "chrom": parts[0],
                "start": start,
                "end": end,
                "position": start,
                "name": label,
                "coverage": coverage,
                "methylation_fraction": fraction,
                "strand": parts[5] if len(parts) > 5 else ".",
            })
    result.primary = pd.DataFrame(rows)
    result.total_records = total
    result.truncated = total > len(rows)
    result.metadata = {
        "chromosomes": int(result.primary["chrom"].nunique()) if not result.primary.empty else 0,
        "coverage_available": bool("coverage" in result.primary and result.primary["coverage"].notna().any()),
        "methylation_available": bool("methylation_fraction" in result.primary and result.primary["methylation_fraction"].notna().any()),
    }
    if result.primary.empty:
        result.warnings.append("No valid bedMethyl records were decoded.")
    return result


def parse_genbank(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "genbank")
    records: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    total = 0
    parse_warning = ""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with path.open("rt", encoding="utf-8-sig", errors="replace") as handle:
                parsed_records = list(SeqIO.parse(handle, "genbank"))
        for sequence_record in parsed_records:
            total += 1
            if len(records) >= max_records:
                continue
            sequence = str(sequence_record.seq).upper()
            gc = ((sequence.count("G") + sequence.count("C")) / len(sequence)) if sequence else np.nan
            records.append({
                "record_id": str(sequence_record.id),
                "name": str(sequence_record.name),
                "description": str(sequence_record.description),
                "length": len(sequence),
                "gc_fraction": gc,
                "feature_count": len(sequence_record.features),
                "topology": sequence_record.annotations.get("topology", ""),
                "molecule_type": sequence_record.annotations.get("molecule_type", ""),
            })
            for feature in sequence_record.features[: max_records]:
                labels = feature.qualifiers.get("label", feature.qualifiers.get("gene", feature.qualifiers.get("product", [])))
                if isinstance(labels, str):
                    labels = [labels]
                features.append({
                    "record_id": str(sequence_record.id),
                    "feature_type": str(feature.type),
                    "start": int(feature.location.start),
                    "end": int(feature.location.end),
                    "strand": int(feature.location.strand or 0),
                    "label": "; ".join(map(str, labels))[:500],
                })
    except Exception as exc:
        parse_warning = f"Biopython parser fallback used: {type(exc).__name__}: {exc}"
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        blocks = [block for block in re.split(r"^//\s*$", text, flags=re.MULTILINE) if block.strip()]
        for block_index, block in enumerate(blocks[:max_records], start=1):
            total += 1
            locus_match = re.search(r"^LOCUS\s+(\S+)", block, flags=re.MULTILINE)
            definition_match = re.search(r"^DEFINITION\s+(.+?)(?=^[A-Z][A-Z ]{2,}\s|\Z)", block, flags=re.MULTILINE | re.DOTALL)
            origin_match = re.search(r"^ORIGIN\s*(.*)$", block, flags=re.MULTILINE | re.DOTALL)
            sequence = re.sub(r"[^A-Za-z]", "", origin_match.group(1)).upper() if origin_match else ""
            record_id = locus_match.group(1) if locus_match else f"record_{block_index}"
            topology = "circular" if re.search(r"\bcircular\b", block.splitlines()[0] if block.splitlines() else "", flags=re.IGNORECASE) else ""
            gc = ((sequence.count("G") + sequence.count("C")) / len(sequence)) if sequence else np.nan
            feature_rows = []
            feature_section = re.search(r"^FEATURES.*?\n(.*?)(?=^ORIGIN|\Z)", block, flags=re.MULTILINE | re.DOTALL)
            if feature_section:
                for match in re.finditer(r"^\s{5}(\S+)\s+([<>]?\d+)\.\.([<>]?\d+)", feature_section.group(1), flags=re.MULTILINE):
                    with contextlib.suppress(Exception):
                        feature_rows.append({
                            "record_id": record_id,
                            "feature_type": match.group(1),
                            "start": int(match.group(2).lstrip("<>")) - 1,
                            "end": int(match.group(3).lstrip("<>")),
                            "strand": 0,
                            "label": "",
                        })
            records.append({
                "record_id": record_id,
                "name": record_id,
                "description": re.sub(r"\s+", " ", definition_match.group(1)).strip() if definition_match else "",
                "length": len(sequence),
                "gc_fraction": gc,
                "feature_count": len(feature_rows),
                "topology": topology,
                "molecule_type": "DNA" if sequence else "",
            })
            features.extend(feature_rows)
    result.primary = pd.DataFrame(records)
    result.secondary["features"] = pd.DataFrame(features).head(max_records)
    result.total_records = total
    result.truncated = total > len(records)
    result.metadata = {
        "records": len(records),
        "features_loaded": len(result.secondary["features"]),
        "total_sequence_bases": int(result.primary["length"].sum()) if not result.primary.empty else 0,
        "fallback_used": bool(parse_warning),
    }
    if parse_warning:
        result.warnings.append(parse_warning)
    return result

def parse_sdf(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "sdf")
    text = path.read_text(encoding="utf-8", errors="replace")
    rows: list[dict[str, Any]] = []
    lower = path.name.lower()
    if lower.endswith(".mol2"):
        blocks = text.split("@<TRIPOS>MOLECULE")
        for index, block in enumerate(blocks[1:max_records + 1], start=1):
            lines = [line.rstrip() for line in block.splitlines() if line.strip()]
            name = lines[0] if lines else f"molecule_{index}"
            counts = re.findall(r"\d+", lines[1]) if len(lines) > 1 else []
            rows.append({
                "molecule_index": index,
                "name": name[:250],
                "atom_count": int(counts[0]) if counts else None,
                "bond_count": int(counts[1]) if len(counts) > 1 else None,
                "format": "MOL2",
            })
        total = max(text.count("@<TRIPOS>MOLECULE"), len(rows))
    else:
        blocks = text.split("$$$$") if "$$$$" in text else [text]
        total = len([block for block in blocks if block.strip()])
        for index, block in enumerate((block for block in blocks if block.strip()), start=1):
            if len(rows) >= max_records:
                break
            lines = block.splitlines()
            name = lines[0].strip() if lines else f"molecule_{index}"
            atom_count = bond_count = None
            if len(lines) > 3:
                counts_line = lines[3]
                with contextlib.suppress(Exception):
                    atom_count = int(counts_line[:3])
                    bond_count = int(counts_line[3:6])
            properties = re.findall(r">\s*<([^>]+)>\s*\n([^\n]+)", block)
            rows.append({
                "molecule_index": index,
                "name": name[:250],
                "atom_count": atom_count,
                "bond_count": bond_count,
                "property_count": len(properties),
                "properties": json.dumps(dict(properties), sort_keys=True)[:4000],
                "format": "SDF/MOL",
            })
    result.primary = pd.DataFrame(rows)
    result.total_records = total
    result.truncated = total > len(rows)
    result.metadata = {"molecules_loaded": len(rows), "external_conversion_engine": "obabel"}
    return result


def parse_model_asset(path: Path) -> NativeParseResult:
    result = _base_result(path, "model_asset")
    head = path.read_bytes()[:4096]
    lower = path.name.lower()
    metadata: dict[str, Any] = {
        "extension": _compound_suffix(path.name),
        "deserialised": False,
        "security_policy": "metadata_only",
        "header_hex": head[:32].hex(),
    }
    if lower.endswith(".safetensors") and len(head) >= 8:
        with contextlib.suppress(Exception):
            header_length = struct.unpack("<Q", head[:8])[0]
            metadata["safetensors_header_bytes"] = int(header_length)
    if lower.endswith(".gguf"):
        metadata["gguf_magic_valid"] = head[:4] == b"GGUF"
    if lower.endswith(".onnx"):
        metadata["protobuf_like_header"] = bool(head)
    result.primary = pd.DataFrame([{
        "asset_name": path.name,
        "size_bytes": path.stat().st_size,
        "extension": metadata["extension"],
        "deserialised": False,
        "expected_runtime": "external approved engine",
    }])
    result.total_records = 1
    result.metadata = metadata
    result.warnings.append("Binary model assets are not loaded or executed during inspection.")
    return result


def parse_safety_xml(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "safety_xml")
    rows: list[dict[str, Any]] = []
    total = 0
    case_tags = {"safetyreport", "case", "report", "ichicsr"}
    for _event, element in ET.iterparse(path, events=("end",)):
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag not in case_tags:
            continue
        total += 1
        if len(rows) < max_records:
            flat: dict[str, Any] = {"case_index": total, "root_tag": tag}
            for child in element.iter():
                child_tag = child.tag.rsplit("}", 1)[-1]
                text = (child.text or "").strip()
                if text and child_tag not in flat and len(flat) < 80:
                    flat[child_tag] = text[:1000]
            rows.append(flat)
        element.clear()
    if total == 0:
        tree = ET.parse(path)
        root = tree.getroot()
        rows = [{"case_index": 1, "root_tag": root.tag.rsplit("}", 1)[-1], "note": "No standard case container tags were detected."}]
        total = 1
    result.primary = pd.DataFrame(rows)
    result.total_records = total
    result.truncated = total > len(rows)
    result.metadata = {"case_like_records": total, "terminology_normalisation": "requires external dictionary"}
    return result


def parse_parquet(path: Path, max_records: int, format_key: str = "parquet") -> NativeParseResult:
    result = _base_result(path, format_key)
    if path.name.lower().endswith(".feather"):
        frame = pd.read_feather(path)
    else:
        frame = pd.read_parquet(path)
    total = len(frame)
    result.primary = frame.head(max_records).copy()
    result.total_records = total
    result.truncated = total > len(result.primary)
    result.metadata = {"columns": list(map(str, frame.columns)), "column_count": len(frame.columns)}
    return result



def parse_jsonl(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "jsonl")
    rows: list[dict[str, Any]] = []
    total = 0
    with path.open("rt", encoding="utf-8-sig", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            total += 1
            if len(rows) >= max_records:
                continue
            try:
                obj = json.loads(line)
                rows.append(obj if isinstance(obj, dict) else {"value": obj})
            except Exception as exc:
                rows.append({"_parse_error": f"{type(exc).__name__}: {exc}", "_raw": line[:2000]})
    result.primary = pd.json_normalize(rows) if rows else pd.DataFrame()
    result.total_records = total
    result.truncated = total > len(rows)
    result.metadata = {"records_loaded": len(rows), "parse_errors": int(result.primary.get("_parse_error", pd.Series(dtype=str)).notna().sum()) if not result.primary.empty else 0}
    return result


def parse_yaml(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "yaml")
    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise RuntimeError("PyYAML is required to inspect YAML manifests") from exc
    obj = yaml.safe_load(path.read_text(encoding="utf-8-sig", errors="replace"))
    if isinstance(obj, list):
        frame = pd.json_normalize(obj[:max_records])
        total = len(obj)
    elif isinstance(obj, dict):
        records = obj.get("records") or obj.get("data") or obj.get("steps")
        if isinstance(records, list):
            frame = pd.json_normalize(records[:max_records])
            total = len(records)
        else:
            frame = pd.json_normalize([obj])
            total = 1
    else:
        frame = pd.DataFrame([{"value": obj}])
        total = 1
    result.primary = frame
    result.total_records = total
    result.truncated = total > len(frame)
    result.metadata = {"top_level_type": type(obj).__name__}
    return result


def parse_hdf5(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "hdf5")
    try:
        import h5py  # type: ignore
    except Exception as exc:
        raise RuntimeError("h5py is required to inspect HDF5 containers") from exc
    rows: list[dict[str, Any]] = []
    with h5py.File(path, "r") as handle:
        def visitor(name: str, obj: Any) -> None:
            if len(rows) >= max_records:
                return
            if isinstance(obj, h5py.Dataset):
                rows.append({
                    "path": "/" + name,
                    "object_type": "dataset",
                    "shape": json.dumps(list(obj.shape)),
                    "dtype": str(obj.dtype),
                    "size": int(obj.size),
                    "compression": str(obj.compression or ""),
                })
            elif isinstance(obj, h5py.Group):
                rows.append({
                    "path": "/" + name,
                    "object_type": "group",
                    "shape": "",
                    "dtype": "",
                    "size": len(obj),
                    "compression": "",
                })
        handle.visititems(visitor)
        root_keys = list(handle.keys())
    result.primary = pd.DataFrame(rows)
    result.total_records = len(rows)
    result.metadata = {"root_keys": root_keys, "inventory_only": True}
    return result


def parse_binary_placeholder(path: Path, format_key: str, engine: str) -> NativeParseResult:
    result = _base_result(path, format_key)
    result.primary = pd.DataFrame([{
        "asset_name": path.name,
        "size_bytes": path.stat().st_size,
        "extension": _compound_suffix(path.name),
        "decode_state": "external_engine_required",
        "required_engine": engine,
    }])
    result.total_records = 1
    result.engine_required = engine
    result.warnings.append(f"{format_key} is a binary format and was not deserialised; install and configure {engine} for decoding.")
    return result



__all__ = ['parse_bedmethyl_native', 'parse_binary_placeholder', 'parse_genbank', 'parse_hdf5', 'parse_jsonl', 'parse_model_asset', 'parse_parquet', 'parse_safety_xml', 'parse_sdf', 'parse_wsi', 'parse_yaml']
