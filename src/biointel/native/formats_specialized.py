from __future__ import annotations

import base64
import gzip
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.io import mmread

from .formats import (
    NativeParseResult,
    _base_result,
    _decode_h5_strings,
    _fcs_text_pairs,
    _header_int,
    _open_binary,
    _open_text,
)

def _parse_fcs(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "fcs")
    with path.open("rb") as handle:
        header = handle.read(58)
        if len(header) < 58 or not header.startswith(b"FCS"):
            raise ValueError("Invalid FCS header")
        text_start, text_end = _header_int(header, 10, 18), _header_int(header, 18, 26)
        data_start, data_end = _header_int(header, 26, 34), _header_int(header, 34, 42)
        handle.seek(text_start)
        keywords = _fcs_text_pairs(handle.read(text_end - text_start + 1))
        data_start = data_start or int(keywords.get("$BEGINDATA", "0") or 0)
        data_end = data_end or int(keywords.get("$ENDDATA", "0") or 0)
        par = int(keywords.get("$PAR", "0") or 0)
        total = int(keywords.get("$TOT", "0") or 0)
        datatype = keywords.get("$DATATYPE", "F").upper()
        byteord = keywords.get("$BYTEORD", "1,2,3,4")
        little = byteord.startswith("1,2")
        names = [keywords.get(f"$P{i}S") or keywords.get(f"$P{i}N") or f"P{i}" for i in range(1, par + 1)]
        bits = [int(keywords.get(f"$P{i}B", "32") or 32) for i in range(1, par + 1)]
        if par <= 0 or total < 0 or data_start <= 0:
            raise ValueError("FCS metadata does not define a valid data segment")
        read_events = min(total, max_records)
        handle.seek(data_start)
        raw = handle.read(max(0, min(data_end - data_start + 1 if data_end >= data_start else path.stat().st_size - data_start, 512 * 1024 * 1024)))
    endian = "<" if little else ">"
    if datatype == "F" and len(set(bits)) == 1 and bits[0] == 32:
        values = np.frombuffer(raw, dtype=endian + "f4", count=read_events * par)
    elif datatype == "D" and len(set(bits)) == 1 and bits[0] == 64:
        values = np.frombuffer(raw, dtype=endian + "f8", count=read_events * par)
    elif datatype == "I" and len(set(bits)) == 1 and bits[0] in {8, 16, 32, 64}:
        values = np.frombuffer(raw, dtype=endian + f"u{bits[0] // 8}", count=read_events * par)
    else:
        raise ValueError(f"Unsupported FCS data encoding: DATATYPE={datatype}, bits={bits}")
    complete = (len(values) // par) * par
    values = values[:complete].reshape((-1, par)) if complete else np.empty((0, par))
    result.primary = pd.DataFrame(values, columns=names)
    result.total_records = total
    result.truncated = total > len(result.primary)
    result.metadata = {"fcs_version": header[:6].decode("ascii", errors="ignore"), "parameters": names, "parameter_count": par, "events": total, "datatype": datatype, "keywords": {key: keywords[key] for key in sorted(keywords) if key in {"$CYT", "$DATE", "$BTIM", "$ETIM", "$FIL", "$MODE", "$NEXTDATA"}}}
    return result

def _decode_mzml_binary(binary_array: ET.Element) -> tuple[str | None, np.ndarray]:
    kind: str | None = None
    compressed = False
    dtype = np.dtype("<f8")
    for node in binary_array:
        tag = node.tag.rsplit("}", 1)[-1]
        if tag != "cvParam":
            continue
        accession = node.attrib.get("accession", "")
        if accession == "MS:1000514":
            kind = "mz"
        elif accession == "MS:1000515":
            kind = "intensity"
        elif accession == "MS:1000595":
            kind = "time"
        elif accession == "MS:1000574":
            compressed = True
        elif accession == "MS:1000521":
            dtype = np.dtype("<f4")
        elif accession == "MS:1000523":
            dtype = np.dtype("<f8")
    binary_node = next((node for node in binary_array if node.tag.rsplit("}", 1)[-1] == "binary"), None)
    if binary_node is None or not (binary_node.text or "").strip():
        return kind, np.array([], dtype=float)
    raw = base64.b64decode((binary_node.text or "").strip())
    if compressed:
        raw = zlib.decompress(raw)
    return kind, np.frombuffer(raw, dtype=dtype).astype(float, copy=False)

def _parse_mzml(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "mzml")
    peaks: list[dict[str, Any]] = []
    spectra: list[dict[str, Any]] = []
    chromatogram_rows: list[dict[str, Any]] = []
    with _open_binary(path) as binary:
        context = ET.iterparse(binary, events=("end",))
        spectrum_count = 0
        for _, elem in context:
            tag = elem.tag.rsplit("}", 1)[-1]
            if tag == "spectrum":
                spectrum_count += 1
                ms_level = 1
                scan_time = np.nan
                precursor_mz = np.nan
                arrays: dict[str, np.ndarray] = {}
                for node in elem.iter():
                    node_tag = node.tag.rsplit("}", 1)[-1]
                    if node_tag == "cvParam":
                        accession = node.attrib.get("accession", "")
                        if accession == "MS:1000511":
                            ms_level = int(float(node.attrib.get("value", "1") or 1))
                        elif accession == "MS:1000016":
                            scan_time = pd.to_numeric(node.attrib.get("value", np.nan), errors="coerce")
                        elif accession == "MS:1000744":
                            precursor_mz = pd.to_numeric(node.attrib.get("value", np.nan), errors="coerce")
                    elif node_tag == "binaryDataArray":
                        kind, values = _decode_mzml_binary(node)
                        if kind:
                            arrays[kind] = values
                mzs = arrays.get("mz", np.array([], dtype=float))
                intensities = arrays.get("intensity", np.array([], dtype=float))
                count = min(len(mzs), len(intensities))
                if count:
                    top_count = min(count, max(1, min(500, max_records - len(peaks))))
                    indexes = np.argsort(intensities[:count])[-top_count:]
                    for index in indexes:
                        peaks.append({"spectrum_id": elem.attrib.get("id", f"spectrum_{spectrum_count}"), "spectrum_index": spectrum_count - 1, "ms_level": ms_level, "scan_time": scan_time, "precursor_mz": precursor_mz, "mz": float(mzs[index]), "intensity": float(intensities[index])})
                spectra.append({"spectrum_id": elem.attrib.get("id", f"spectrum_{spectrum_count}"), "spectrum_index": spectrum_count - 1, "ms_level": ms_level, "scan_time": scan_time, "precursor_mz": precursor_mz, "peaks": count, "tic": float(np.sum(intensities[:count])) if count else 0.0, "base_peak": float(np.max(intensities[:count])) if count else 0.0})
                elem.clear()
                if len(peaks) >= max_records:
                    result.truncated = True
                    break
            elif tag == "chromatogram":
                arrays: dict[str, np.ndarray] = {}
                for node in elem.iter():
                    if node.tag.rsplit("}", 1)[-1] == "binaryDataArray":
                        kind, values = _decode_mzml_binary(node)
                        if kind:
                            arrays[kind] = values
                times = arrays.get("time", np.array([], dtype=float))
                intensities = arrays.get("intensity", np.array([], dtype=float))
                for idx in range(min(len(times), len(intensities), max_records - len(chromatogram_rows))):
                    chromatogram_rows.append({"chromatogram_id": elem.attrib.get("id", "chromatogram"), "time": float(times[idx]), "intensity": float(intensities[idx])})
                elem.clear()
    result.primary = pd.DataFrame(peaks)
    result.secondary["spectra"] = pd.DataFrame(spectra)
    result.secondary["chromatograms"] = pd.DataFrame(chromatogram_rows)
    result.total_records = len(peaks) if not result.truncated else None
    result.metadata = {"spectra_loaded": len(spectra), "chromatogram_points": len(chromatogram_rows), "peak_strategy": "top intensity peaks per spectrum"}
    if not peaks:
        result.warnings.append("No decoded m/z-intensity arrays were found. The mzML may use an unsupported binary encoding or external data reference.")
    return result

def _parse_mgf(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "mgf")
    peaks: list[dict[str, Any]] = []
    spectra: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    spectrum_index = -1
    with _open_text(path) as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            upper = text.upper()
            if upper == "BEGIN IONS":
                spectrum_index += 1
                current = {"spectrum_index": spectrum_index, "title": f"spectrum_{spectrum_index+1}", "pepmass": np.nan, "charge": "", "rtinseconds": np.nan, "peak_count": 0, "tic": 0.0}
                continue
            if upper == "END IONS":
                if current is not None:
                    spectra.append(current)
                current = None
                continue
            if current is None:
                continue
            if "=" in text:
                key, value = text.split("=", 1)
                key = key.lower()
                if key == "title": current["title"] = value
                elif key == "pepmass": current["pepmass"] = pd.to_numeric(value.split()[0], errors="coerce")
                elif key == "charge": current["charge"] = value
                elif key == "rtinseconds": current["rtinseconds"] = pd.to_numeric(value, errors="coerce")
                continue
            fields = text.split()
            if len(fields) >= 2:
                mz = pd.to_numeric(fields[0], errors="coerce")
                intensity = pd.to_numeric(fields[1], errors="coerce")
                if pd.notna(mz) and pd.notna(intensity):
                    current["peak_count"] += 1
                    current["tic"] += float(intensity)
                    if len(peaks) < max_records:
                        peaks.append({"spectrum_index": spectrum_index, "title": current["title"], "pepmass": current["pepmass"], "charge": current["charge"], "rtinseconds": current["rtinseconds"], "mz": float(mz), "intensity": float(intensity)})
                    else:
                        result.truncated = True
    result.primary = pd.DataFrame(peaks)
    result.secondary["spectra"] = pd.DataFrame(spectra)
    result.total_records = sum(int(row.get("peak_count", 0)) for row in spectra)
    result.metadata = {"spectra_loaded": len(spectra)}
    return result

def _parse_h5ad(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "h5ad")
    try:
        import anndata as ad

        adata = ad.read_h5ad(path, backed="r")
        try:
            n = min(int(adata.n_obs), max_records)
            obs = adata.obs.iloc[:n].copy().reset_index().rename(columns={adata.obs.index.name or "index": "cell_id"})
            embedding_key = next((key for key in ("X_umap", "X_tsne", "X_pca", "spatial") if key in adata.obsm), None)
            if embedding_key:
                embedding = np.asarray(adata.obsm[embedding_key][:n])
                for index in range(min(embedding.shape[1], 3)):
                    obs[f"{embedding_key}_{index + 1}"] = embedding[:, index]
            result.primary = obs
            result.secondary["variables"] = adata.var.iloc[: min(int(adata.n_vars), max_records)].copy().reset_index()
            result.metadata = {"n_obs": int(adata.n_obs), "n_vars": int(adata.n_vars), "layers": list(adata.layers.keys()), "obsm": list(adata.obsm.keys()), "embedding": embedding_key, "uns_keys": list(adata.uns.keys())[:100], "reader": "anndata-backed"}
            result.total_records = int(adata.n_obs)
            result.truncated = int(adata.n_obs) > n
        finally:
            if getattr(adata, "file", None) is not None:
                adata.file.close()
        return result
    except ImportError:
        pass

    import h5py

    with h5py.File(path, "r") as h5:
        obs_group = h5.get("obs")
        var_group = h5.get("var")
        obs_index = obs_group.get("_index") if obs_group is not None else h5.get("obs_names")
        var_index = var_group.get("_index") if var_group is not None else h5.get("var_names")
        if obs_index is None:
            raise ValueError("H5AD fallback requires obs/_index or obs_names")
        obs_names = _decode_h5_strings(obs_index[:])
        n_obs_total = len(obs_names)
        n = min(n_obs_total, max_records)
        columns: dict[str, Any] = {"cell_id": obs_names[:n]}
        if obs_group is not None:
            for name, node in obs_group.items():
                if name == "_index":
                    continue
                try:
                    if isinstance(node, h5py.Dataset) and len(node.shape) == 1 and len(node) >= n:
                        columns[name] = _decode_h5_strings(node[:n])
                    elif isinstance(node, h5py.Group) and "codes" in node and "categories" in node:
                        codes = np.asarray(node["codes"][:n], dtype=int)
                        categories = _decode_h5_strings(node["categories"][:])
                        columns[name] = np.array([categories[code] if 0 <= code < len(categories) else "" for code in codes])
                except Exception:
                    continue
        obs = pd.DataFrame(columns)
        embedding_key = None
        obsm = h5.get("obsm")
        if obsm is not None:
            for key in ("X_umap", "X_tsne", "X_pca", "spatial"):
                if key not in obsm:
                    continue
                node = obsm[key]
                try:
                    if isinstance(node, h5py.Dataset):
                        embedding = np.asarray(node[:n])
                    elif isinstance(node, h5py.Group) and "data" in node:
                        embedding = np.asarray(node["data"][:n])
                    else:
                        continue
                    if embedding.ndim == 2:
                        embedding_key = key
                        for index in range(min(embedding.shape[1], 3)):
                            obs[f"{key}_{index + 1}"] = embedding[:, index]
                        break
                except Exception:
                    continue
        variables = pd.DataFrame()
        n_vars = 0
        if var_index is not None:
            var_names = _decode_h5_strings(var_index[:])
            n_vars = len(var_names)
            variables = pd.DataFrame({"feature_id": var_names[: min(n_vars, max_records)]})
        result.primary = obs
        result.secondary["variables"] = variables
        result.metadata = {"n_obs": n_obs_total, "n_vars": n_vars, "obsm": list(obsm.keys()) if obsm is not None else [], "embedding": embedding_key, "reader": "h5py-fallback"}
        result.total_records = n_obs_total
        result.truncated = n_obs_total > n
    return result

def _parse_mtx(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "mtx")
    if path.name.lower().endswith(".gz"):
        with gzip.open(path, "rb") as handle:
            matrix = mmread(handle)
    else:
        matrix = mmread(path)
    shape = matrix.shape
    if hasattr(matrix, "tocoo"):
        coo = matrix.tocoo()
        count = min(len(coo.data), max_records)
        result.primary = pd.DataFrame({"row": coo.row[:count], "column": coo.col[:count], "value": coo.data[:count]})
        total = int(len(coo.data))
    else:
        array = np.asarray(matrix)
        rows, cols = np.nonzero(array)
        count = min(len(rows), max_records)
        result.primary = pd.DataFrame({"row": rows[:count], "column": cols[:count], "value": array[rows[:count], cols[:count]]})
        total = int(len(rows))
    result.total_records = total
    result.truncated = total > len(result.primary)
    result.metadata = {"shape": list(map(int, shape)), "nonzero": total}
    return result

