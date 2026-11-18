from __future__ import annotations

import io
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage

TABLE_EXTENSIONS = (".csv", ".tsv", ".txt", ".json", ".jsonl", ".ndjson", ".yaml", ".yml", ".xml", ".parquet", ".feather", ".xlsx", ".xls")
FASTA_EXTENSIONS = (".fa", ".fasta", ".faa", ".fna", ".fas")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff")


def _parse_fasta(payload: bytes) -> list[tuple[str, str]]:
    text = payload.decode("utf-8-sig", errors="replace")
    records: list[tuple[str, str]] = []
    name = "sequence_1"
    sequence: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if sequence:
                records.append((name, "".join(sequence).upper()))
            name = line[1:].split()[0] or f"sequence_{len(records) + 1}"
            sequence = []
        else:
            sequence.append(re.sub(r"[^A-Za-z*.-]", "", line))
    if sequence:
        records.append((name, "".join(sequence).upper()))
    return records


def _parse_vcf(payload: bytes) -> pd.DataFrame:
    text = payload.decode("utf-8-sig", errors="replace")
    sample_names: list[str] = []
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if line.startswith("#CHROM"):
            parts = line.split("\t")
            sample_names = parts[9:]
            continue
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        chrom, pos, vid, ref, alt, qual, filt, info = parts[:8]
        info_map: dict[str, str] = {}
        for token in info.split(";"):
            if "=" in token:
                key, value = token.split("=", 1)
                info_map[key.upper()] = value
        gene = info_map.get("GENE", info_map.get("ANN", "unknown").split("|")[3] if "|" in info_map.get("ANN", "") else "unknown")
        sv_type = info_map.get("SVTYPE", "SNV")
        end = int(float(info_map.get("END", pos)))
        af_text = info_map.get("AF", info_map.get("FREQ", ""))
        try:
            frequency = float(str(af_text).split(",")[0])
        except Exception:
            frequency = float("nan")
        if sample_names and len(parts) > 9:
            fmt = parts[8].split(":")
            for sample, cell in zip(sample_names, parts[9:], strict=False):
                values = dict(zip(fmt, cell.split(":"), strict=False))
                gt = values.get("GT", "./.")
                dosage = sum(int(x) for x in re.split(r"[/|]", gt) if x.isdigit()) if gt not in {"./.", ".|."} else np.nan
                rows.append({
                    "sample": sample, "variant": vid if vid != "." else f"{chrom}:{pos}:{ref}>{alt}",
                    "chrom": chrom, "position": int(pos), "start": int(pos), "end": end,
                    "ref": ref, "alt": alt, "genotype": dosage, "genotype_text": gt,
                    "frequency": frequency, "gene": gene, "sv_type": sv_type,
                    "filter": filt, "quality": pd.to_numeric(qual, errors="coerce"), "info": info,
                })
        else:
            rows.append({
                "sample": "sample_1", "variant": vid if vid != "." else f"{chrom}:{pos}:{ref}>{alt}",
                "chrom": chrom, "position": int(pos), "start": int(pos), "end": end,
                "ref": ref, "alt": alt, "genotype": np.nan, "frequency": frequency,
                "gene": gene, "sv_type": sv_type, "filter": filt,
                "quality": pd.to_numeric(qual, errors="coerce"), "info": info,
            })
    return pd.DataFrame(rows)


def _parse_bed(payload: bytes) -> pd.DataFrame:
    text = payload.decode("utf-8-sig", errors="replace")
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(text.splitlines()):
        if not line.strip() or line.startswith(('#', 'track', 'browser')):
            continue
        parts = re.split(r"\t| +", line.strip())
        if len(parts) < 3:
            continue
        start, end = int(float(parts[1])), int(float(parts[2]))
        rows.append({
            "sample": "sample_1", "sv_id": parts[3] if len(parts) > 3 else f"region_{index + 1}",
            "chrom": parts[0], "start": start, "end": end,
            "support": pd.to_numeric(parts[4], errors="coerce") if len(parts) > 4 else 1.0,
            "sv_type": "REGION", "feature": parts[3] if len(parts) > 3 else f"region_{index + 1}",
        })
    return pd.DataFrame(rows)


def _parse_gtf_gff(payload: bytes) -> pd.DataFrame:
    text = payload.decode("utf-8-sig", errors="replace")
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(text.splitlines()):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        chrom, source, feature, start, end, score, strand, phase = parts[:8]
        attributes = parts[8] if len(parts) > 8 else ""
        attribute_map: dict[str, str] = {}
        for token in attributes.strip().rstrip(";").split(";"):
            token = token.strip()
            if not token:
                continue
            if "=" in token:
                key, value = token.split("=", 1)
            elif " " in token:
                key, value = token.split(" ", 1)
            else:
                continue
            attribute_map[key.strip()] = value.strip().strip('"')
        gene = attribute_map.get("gene_id", attribute_map.get("gene", attribute_map.get("Name", f"gene_{index + 1}")))
        transcript = attribute_map.get("transcript_id", attribute_map.get("Parent", attribute_map.get("ID", f"tx_{index + 1}")))
        rows.append({
            "sample": "annotation", "gene": gene, "transcript": transcript, "group": "Annotation",
            "abundance": np.nan, "junction_support": np.nan, "chrom": chrom, "start": int(start), "end": int(end),
            "feature_type": feature, "source": source, "strand": strand, "phase": phase,
        })
    return pd.DataFrame(rows)


def _read_h5ad(payload: bytes) -> pd.DataFrame:
    temp_path: str | None = None
    obs = pd.DataFrame()
    n = 0
    try:
        with tempfile.NamedTemporaryFile(suffix=".h5ad", delete=False) as handle:
            handle.write(payload)
            temp_path = handle.name
        try:
            import anndata as ad

            adata = ad.read_h5ad(temp_path, backed="r")
            n = min(int(adata.n_obs), 100_000)
            obs = adata.obs.iloc[:n].copy()
            cells = obs.index.astype(str)
            try:
                adata.file.close()
            except Exception:
                pass

            # Legacy H5AD writers sometimes omit dataframe encoding metadata.
            # AnnData can open those files but may replace the actual cell IDs
            # with a RangeIndex and drop one-dimensional observation fields.
            # Recover the original obs metadata directly from HDF5 instead of
            # silently returning cells named "0", "1", ... .
            default_index = list(cells) == [str(index) for index in range(n)]
            if default_index or not len(obs.columns):
                import h5py

                with h5py.File(temp_path, "r") as h5:
                    obs_group = h5.get("obs")
                    if obs_group is not None:
                        index_node = obs_group.get("_index")
                        if index_node is None:
                            index_node = h5.get("obs_names")
                        if index_node is not None:
                            raw_cells = index_node[:n]
                            recovered_cells = pd.Index([
                                value.decode("utf-8", errors="replace")
                                if isinstance(value, (bytes, bytearray))
                                else str(value)
                                for value in raw_cells
                            ])
                            if len(recovered_cells) == n:
                                cells = recovered_cells
                                obs.index = recovered_cells
                        for column, node in obs_group.items():
                            if (
                                column == "_index"
                                or column in obs.columns
                                or not hasattr(node, "shape")
                                or len(node.shape) != 1
                                or int(node.shape[0]) < n
                            ):
                                continue
                            raw_values = node[:n]
                            obs[column] = [
                                value.decode("utf-8", errors="replace")
                                if isinstance(value, (bytes, bytearray))
                                else value
                                for value in raw_values
                            ]
        except (ImportError, ModuleNotFoundError):
            import h5py

            with h5py.File(temp_path, "r") as h5:
                obs_group = h5.get("obs")
                if obs_group is None:
                    raise ValueError("H5AD file does not contain an obs group")
                index_node = obs_group.get("_index")
                if index_node is None:
                    index_node = h5.get("obs_names")
                if index_node is None:
                    raise ValueError("H5AD observation index was not found")
                raw_cells = index_node[:]
                cells = pd.Index([
                    value.decode("utf-8", errors="replace") if isinstance(value, (bytes, bytearray)) else str(value)
                    for value in raw_cells[:100_000]
                ])
                n = len(cells)
                columns: dict[str, Any] = {}
                for column, node in obs_group.items():
                    if column == "_index" or not hasattr(node, "shape") or len(node.shape) != 1:
                        continue
                    try:
                        raw_values = node[:n]
                        columns[column] = [
                            value.decode("utf-8", errors="replace") if isinstance(value, (bytes, bytearray)) else value
                            for value in raw_values
                        ]
                    except Exception:
                        continue
                obs = pd.DataFrame(columns, index=cells)
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    def pick(candidates: list[str], default: Any) -> pd.Series:
        for candidate in candidates:
            if candidate in obs.columns:
                return obs[candidate].reset_index(drop=True)
        return pd.Series([default] * n)

    frame = pd.DataFrame({
        "cell": pd.Index(cells).astype(str),
        "reference_label": pick(["reference_label", "cell_type", "celltype", "annotation"], "Unassigned"),
        "similarity": pd.to_numeric(pick(["similarity", "prediction_score", "confidence"], 0.5), errors="coerce").fillna(0.5),
        "marker_agreement": pd.to_numeric(pick(["marker_agreement", "marker_score"], 0.5), errors="coerce").fillna(0.5),
        "batch": pick(["batch", "sample", "donor"], "Unknown"),
        "query_cluster": pick(["query_cluster", "leiden", "cluster"], "Unknown"),
    })
    frame["import_note"] = "H5AD observation metadata import; expression matrix was not materialised."
    return frame


def _read_table(payload: bytes, name: str) -> pd.DataFrame:
    lower = name.lower()
    if lower.endswith(".json"):
        data = json.loads(payload.decode("utf-8-sig", errors="replace"))
        if isinstance(data, dict):
            data = data.get("records", data.get("data", [data]))
        return pd.DataFrame(data)
    if lower.endswith((".jsonl", ".ndjson")):
        rows = []
        for line in payload.decode("utf-8-sig", errors="replace").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            rows.append(item if isinstance(item, dict) else {"value": item})
        return pd.json_normalize(rows)
    if lower.endswith((".yaml", ".yml")):
        try:
            import yaml
        except Exception as exc:
            raise ValueError("PyYAML is required for YAML scientific manifests") from exc
        data = yaml.safe_load(payload.decode("utf-8-sig", errors="replace"))
        if isinstance(data, dict):
            data = data.get("records", data.get("data", data.get("steps", [data])))
        if not isinstance(data, list):
            data = [{"value": data}]
        return pd.json_normalize(data)
    if lower.endswith(".xml"):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(payload)
        rows = []
        case_tags = {"safetyreport", "case", "report", "ichicsr"}
        candidates = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() in case_tags]
        if not candidates:
            candidates = [root]
        for index, node in enumerate(candidates[:100_000], start=1):
            row = {"case_index": index, "root_tag": node.tag.rsplit("}", 1)[-1]}
            for child in node.iter():
                tag = child.tag.rsplit("}", 1)[-1]
                text = (child.text or "").strip()
                if text and tag not in row and len(row) < 80:
                    row[tag] = text[:1000]
            rows.append(row)
        return pd.json_normalize(rows)
    if lower.endswith(".parquet"):
        return pd.read_parquet(io.BytesIO(payload))
    if lower.endswith(".feather"):
        return pd.read_feather(io.BytesIO(payload))
    if lower.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(payload))
    text = payload.decode("utf-8-sig", errors="replace")
    sep = "\t" if lower.endswith((".tsv", ".txt")) else ","
    try:
        return pd.read_csv(io.StringIO(text), sep=sep)
    except Exception:
        return pd.read_csv(io.StringIO(text), sep=None, engine="python")


def _segment_image(payload: bytes, name: str) -> pd.DataFrame:
    image = Image.open(io.BytesIO(payload)).convert("L")
    array = np.asarray(image, dtype=float)
    if array.size > 16_000_000:
        scale = math.sqrt(16_000_000 / array.size)
        new_size = (max(64, int(image.width * scale)), max(64, int(image.height * scale)))
        image = image.resize(new_size)
        array = np.asarray(image, dtype=float)
    smooth = ndimage.gaussian_filter(array, sigma=1.2)
    low, high = np.percentile(smooth, [1, 99])
    if high - low < 1e-9:
        return pd.DataFrame()
    midpoint = float(low + (high - low) * 0.5)
    candidates = [smooth >= midpoint, smooth <= midpoint]
    best_rows: list[dict[str, Any]] = []
    for mask in candidates:
        mask = ndimage.binary_opening(mask, iterations=1)
        mask = ndimage.binary_closing(mask, iterations=1)
        labels, count = ndimage.label(mask)
        objects = ndimage.find_objects(labels)
        rows: list[dict[str, Any]] = []
        for label_id, slc in enumerate(objects, start=1):
            if slc is None:
                continue
            region = labels[slc] == label_id
            area = int(region.sum())
            if area < 12 or area > array.size * 0.4:
                continue
            coords = np.argwhere(labels == label_id)
            y0, x0 = coords.min(axis=0); y1, x1 = coords.max(axis=0)
            perimeter_proxy = max(2 * ((x1 - x0 + 1) + (y1 - y0 + 1)), 1)
            rows.append({
                "image": name, "organoid": f"OBJ-{label_id:04d}", "time": 0.0, "condition": "Imported",
                "area": area, "viability": float(np.mean(array[labels == label_id]) / 255.0),
                "mean_intensity": float(np.mean(array[labels == label_id])),
                "circularity": float(np.clip(4 * math.pi * area / (perimeter_proxy ** 2), 0, 1)),
                "bbox_x": int(x0), "bbox_y": int(y0), "bbox_width": int(x1 - x0 + 1), "bbox_height": int(y1 - y0 + 1),
                "segmentation_method": "bounded_local_threshold",
            })
        if len(rows) > len(best_rows):
            best_rows = rows
    return pd.DataFrame(best_rows)



def _pathology_tiles(payload: bytes, name: str, *, grid: int = 8) -> pd.DataFrame:
    """Create bounded image-tile QC features; this is not a diagnostic foundation-model inference."""
    image = Image.open(io.BytesIO(payload)).convert("RGB")
    if image.width * image.height > 24_000_000:
        scale = math.sqrt(24_000_000 / (image.width * image.height))
        image = image.resize((max(256, int(image.width * scale)), max(256, int(image.height * scale))))
    array = np.asarray(image, dtype=float) / 255.0
    height, width = array.shape[:2]
    rows: list[dict[str, Any]] = []
    slide_id = Path(name).stem
    tile_number = 0
    for gy in range(grid):
        for gx in range(grid):
            y0, y1 = int(gy * height / grid), int((gy + 1) * height / grid)
            x0, x1 = int(gx * width / grid), int((gx + 1) * width / grid)
            tile = array[y0:y1, x0:x1]
            if tile.size == 0:
                continue
            tile_number += 1
            brightness = tile.mean(axis=2)
            saturation = tile.max(axis=2) - tile.min(axis=2)
            tissue_fraction = float(np.mean((brightness < 0.92) & (saturation > 0.035)))
            texture = float(np.std(brightness))
            stain_proxy = float(np.clip((1 - tile[..., 0].mean()) * 0.45 + (1 - tile[..., 2].mean()) * 0.55, 0, 1))
            embedding_score = float(np.clip(0.45 + 1.8 * texture + 0.35 * tissue_fraction, 0, 1))
            tumour_probability = float(np.clip(0.15 + 0.55 * stain_proxy + 0.30 * texture, 0, 1))
            rows.append({
                "slide_id": slide_id,
                "tile_id": f"TILE-{tile_number:04d}",
                "tissue_fraction": tissue_fraction,
                "embedding_score": embedding_score,
                "tumour_probability": tumour_probability,
                "scanner": "Imported image",
                "site": "Unknown",
                "tile_x": gx,
                "tile_y": gy,
                "feature_source": "bounded_image_qc_proxy",
            })
    return pd.DataFrame(rows)


def _parse_bedmethyl(payload: bytes, name: str) -> pd.DataFrame:
    text = payload.decode("utf-8-sig", errors="replace")
    rows: list[dict[str, Any]] = []
    sample = Path(name).stem
    for index, line in enumerate(text.splitlines()):
        if not line.strip() or line.startswith(("#", "track", "browser")):
            continue
        parts = line.rstrip().split("\t")
        if len(parts) < 3:
            parts = re.split(r"\s+", line.strip())
        if len(parts) < 3:
            continue
        try:
            start, end = int(float(parts[1])), int(float(parts[2]))
        except Exception:
            continue
        label = parts[3] if len(parts) > 3 and parts[3] else f"region_{index + 1}"
        coverage = pd.to_numeric(parts[9], errors="coerce") if len(parts) > 9 else np.nan
        fraction = np.nan
        for candidate in parts[10:14]:
            value = pd.to_numeric(candidate, errors="coerce")
            if pd.notna(value) and 0 <= float(value) <= 100:
                fraction = float(value) / 100.0 if float(value) > 1 else float(value)
                break
        haplotype = "H1" if "H1" in label.upper() else "H2" if "H2" in label.upper() else "Unphased"
        rows.append({
            "sample": sample,
            "chrom": parts[0],
            "position": start,
            "haplotype": haplotype,
            "methylation_fraction": fraction,
            "coverage": coverage,
            "region": f"{parts[0]}:{start}-{end}",
            "condition": "Unknown",
            "source_label": label,
        })
    return pd.DataFrame(rows)


def _parse_gfa_population(payload: bytes, name: str) -> pd.DataFrame:
    text = payload.decode("utf-8-sig", errors="replace")
    segments: dict[str, int] = {}
    paths: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        parts = line.rstrip().split("\t")
        if not parts:
            continue
        if parts[0] == "S" and len(parts) >= 3:
            segments[parts[1]] = len(parts[2]) if parts[2] != "*" else 0
        elif parts[0] in {"P", "W"} and len(parts) >= 3:
            path_name = parts[1]
            tokens = re.split(r"[,><]", parts[2])
            paths.append((path_name, [token.rstrip("+-") for token in tokens if token]))
    if not paths and segments:
        paths = [(Path(name).stem, list(segments))]
    counts: dict[str, int] = {}
    for _, tokens in paths:
        for token in set(tokens):
            counts[token] = counts.get(token, 0) + 1
    total_paths = max(len(paths), 1)
    rows: list[dict[str, Any]] = []
    for path_name, tokens in paths:
        for token in tokens[:5000]:
            frequency = counts.get(token, 1) / total_paths
            rows.append({
                "sample": path_name,
                "population": "Unknown",
                "path": path_name,
                "variant": f"segment:{token}",
                "allele_frequency": float(frequency),
                "clinical_weight": 0.0,
                "reference_bias": float(1.0 - frequency),
                "segment_length": segments.get(token, 0),
                "source": "GFA path summary",
            })
    return pd.DataFrame(rows)


def _parse_genbank_sequence(payload: bytes, name: str) -> list[tuple[str, str]]:
    text = payload.decode("utf-8-sig", errors="replace")
    locus = Path(name).stem
    match = re.search(r"^LOCUS\s+(\S+)", text, flags=re.MULTILINE)
    if match:
        locus = match.group(1)
    origin = re.search(r"^ORIGIN\s*(.*?)^//", text, flags=re.MULTILINE | re.DOTALL)
    if not origin:
        return []
    sequence = re.sub(r"[^A-Za-z]", "", origin.group(1)).upper()
    return [(locus, sequence)] if sequence else []


def _structure_candidate(payload: bytes, name: str) -> pd.DataFrame:
    text = payload.decode("utf-8", errors="replace")
    lower = name.lower()
    atoms = sum(1 for line in text.splitlines() if line.startswith(("ATOM", "HETATM")))
    residues = len({line[21:27].strip() for line in text.splitlines() if line.startswith("ATOM") and len(line) >= 27})
    ligands = len({line[17:20].strip() for line in text.splitlines() if line.startswith("HETATM") and len(line) >= 20})
    records = max(text.count("$$$$"), 1) if lower.endswith((".sdf", ".mol")) else 1
    rows = []
    for index in range(records):
        scale = float(np.clip(math.log1p(max(atoms, 1)) / 12.0, 0, 1))
        rows.append({
            "candidate": f"{Path(name).stem}-{index + 1}",
            "protein_variant": Path(name).stem,
            "ligand": f"Imported-{index + 1}",
            "protein_score": scale,
            "ligand_score": float(np.clip(0.35 + 0.08 * ligands, 0, 1)),
            "interface_score": float(np.clip(0.25 + 0.015 * residues + 0.05 * ligands, 0, 1)),
            "selectivity_risk": 0.5,
            "atom_count": atoms,
            "residue_count": residues,
            "score_source": "structure_summary_proxy_requires_docking",
        })
    return pd.DataFrame(rows)


def read_upload(upload: Any, module_key: str) -> pd.DataFrame:
    payload = upload.getvalue()
    name = str(upload.name)
    lower = name.lower()
    if module_key == "digital_pathology_foundation" and lower.endswith(IMAGE_EXTENSIONS):
        return _pathology_tiles(payload, name)
    if module_key == "long_read_epigenome" and lower.endswith((".bed", ".bedmethyl")):
        return _parse_bedmethyl(payload, name)
    if module_key == "pangenome_population_medicine" and lower.endswith(".gfa"):
        return _parse_gfa_population(payload, name)
    if module_key == "protein_ligand_codesign" and lower.endswith((".pdb", ".cif", ".mmcif", ".sdf", ".mol", ".mol2")):
        return _structure_candidate(payload, name)
    if lower.endswith((".gb", ".gbk", ".genbank")):
        records = _parse_genbank_sequence(payload, name)
        if module_key == "gene_therapy_vector":
            return pd.DataFrame({
                "construct": [record[0] for record in records],
                "vector_type": ["Unknown"] * len(records),
                "cargo_bp": [len(record[1]) for record in records],
                "promoter": ["Unknown"] * len(records),
                "tropism_score": [np.nan] * len(records),
                "immunogenicity_risk": [np.nan] * len(records),
                "integration_risk": [np.nan] * len(records),
                "sequence": [record[1] for record in records],
                "score_source": ["sequence_import_requires_evidence"] * len(records),
            })
    if lower.endswith(TABLE_EXTENSIONS):
        return _read_table(payload, name)
    if lower.endswith((".vcf", ".vcf.gz")):
        if lower.endswith(".gz"):
            import gzip
            payload = gzip.decompress(payload)
        return _parse_vcf(payload)
    if lower.endswith((".gtf", ".gff", ".gff3")):
        return _parse_gtf_gff(payload)
    if lower.endswith((".bed", ".bedpe")):
        return _parse_bed(payload)
    if lower.endswith(".h5ad"):
        obs = _read_h5ad(payload)
        if module_key == "cell_atlas_mapping":
            return obs
        if module_key == "single_cell_long_read_isoforms":
            return pd.DataFrame({
                "cell": obs["cell"].astype(str),
                "cluster": obs["query_cluster"].astype(str),
                "gene": "Unassigned",
                "transcript": "Unassigned",
                "umi_count": 0,
                "full_length": False,
                "splice_junctions": 0,
                "reference_label": obs["reference_label"].astype(str),
                "import_note": "H5AD observation metadata imported; long-read transcript evidence must be joined separately.",
            })
        if module_key == "spatial_medicine_tme":
            n = len(obs)
            side = max(int(math.ceil(math.sqrt(max(n, 1)))), 1)
            return pd.DataFrame({
                "patient": obs["batch"].astype(str),
                "region": obs["query_cluster"].astype(str),
                "cell_type": obs["reference_label"].astype(str),
                "gene": "Imported marker score",
                "expression": pd.to_numeric(obs["similarity"], errors="coerce").fillna(0.0),
                "x": np.arange(n) % side,
                "y": np.arange(n) // side,
                "import_note": "H5AD observation metadata spatialised for QC; real tissue coordinates were not present.",
            })
        raise ValueError("H5AD import is enabled for Cell Atlas Mapping, Single-Cell Long-Read Isoforms and Spatial Medicine")
    if lower.endswith(FASTA_EXTENSIONS):
        records = _parse_fasta(payload)
        if module_key == "gene_therapy_vector":
            return pd.DataFrame({
                "construct": [x[0] for x in records],
                "vector_type": ["Unknown"] * len(records),
                "cargo_bp": [len(x[1]) for x in records],
                "promoter": ["Unknown"] * len(records),
                "tropism_score": [np.nan] * len(records),
                "immunogenicity_risk": [np.nan] * len(records),
                "integration_risk": [np.nan] * len(records),
                "sequence": [x[1] for x in records],
                "score_source": ["sequence_import_requires_evidence"] * len(records),
            })
        if module_key == "cell_therapy_cart":
            return pd.DataFrame({
                "construct": [x[0] for x in records],
                "antigen": ["Unknown"] * len(records),
                "scfv_affinity": [np.nan] * len(records),
                "costim_domain": ["Unknown"] * len(records),
                "off_tumour_risk": [np.nan] * len(records),
                "exhaustion_score": [np.nan] * len(records),
                "manufacturability": [np.nan] * len(records),
                "sequence": [x[1] for x in records],
                "score_source": ["sequence_import_requires_antigen_and_assay_evidence"] * len(records),
            })
        if module_key == "amr_surveillance":
            return pd.DataFrame({
                "sample": [x[0] for x in records],
                "species": ["Unknown"] * len(records),
                "lineage": ["Unassigned"] * len(records),
                "amr_gene": ["Not screened"] * len(records),
                "phenotype": ["Unknown"] * len(records),
                "resistant_probability": [np.nan] * len(records),
                "location": ["Unknown"] * len(records),
                "date": [pd.NaT] * len(records),
                "sequence_length": [len(x[1]) for x in records],
                "score_source": ["sequence_import_requires_amr_tool_execution"] * len(records),
            })
        if module_key == "protein_language_design":
            return pd.DataFrame({"sequence_id": [x[0] for x in records], "sequence": [x[1] for x in records]})
        if module_key == "enzyme_pathway_design":
            return pd.DataFrame({"enzyme": [x[0] for x in records], "variant": ["WT"] * len(records), "reaction": ["Unspecified"] * len(records), "activity": [np.nan] * len(records), "stability": [np.nan] * len(records), "flux": [np.nan] * len(records), "sequence": [x[1] for x in records]})
        if module_key == "virology_evolution":
            rows: list[dict[str, Any]] = []
            if not records:
                return pd.DataFrame()
            reference_name, reference = records[0]
            for sample, seq in records[1:]:
                for pos, (ref_base, alt_base) in enumerate(zip(reference, seq, strict=False), start=1):
                    if ref_base in "ACGT" and alt_base in "ACGT" and ref_base != alt_base:
                        rows.append({"sample": sample, "position": pos, "ref": ref_base, "alt": alt_base, "frequency": 1.0, "gene": "genome", "reference_sample": reference_name, "sequence_source": True})
            if len(records) == 1:
                rows.append({"sample": reference_name, "position": 0, "ref": "", "alt": "", "frequency": np.nan, "gene": "genome", "reference_sample": reference_name, "sequence_source": True, "review_note": "A second aligned genome is required for variant comparison."})
            return pd.DataFrame(rows)
        if module_key == "strain_microbiome":
            return pd.DataFrame({"sample": [x[0] for x in records], "taxon": ["Unclassified"] * len(records), "strain": [x[0] for x in records], "feature": ["sequence_length"] * len(records), "abundance": [len(x[1]) for x in records], "feature_type": ["sequence_summary"] * len(records)})
        return pd.DataFrame({"sequence_id": [x[0] for x in records], "sequence": [x[1] for x in records]})
    if lower.endswith(IMAGE_EXTENSIONS):
        segmented = _segment_image(payload, name)
        if module_key == "spatial_medicine_tme":
            if segmented.empty:
                return pd.DataFrame()
            return pd.DataFrame({
                "patient": segmented["image"].astype(str),
                "region": "Imported image",
                "cell_type": "Segmented object",
                "gene": "Mean intensity",
                "expression": pd.to_numeric(segmented["mean_intensity"], errors="coerce"),
                "x": pd.to_numeric(segmented["bbox_x"], errors="coerce") + pd.to_numeric(segmented["bbox_width"], errors="coerce") / 2,
                "y": pd.to_numeric(segmented["bbox_y"], errors="coerce") + pd.to_numeric(segmented["bbox_height"], errors="coerce") / 2,
                "segmentation_method": segmented["segmentation_method"],
            })
        return segmented
    raise ValueError(f"Unsupported file type for {module_key}: {name}")



__all__ = ["read_upload", "TABLE_EXTENSIONS", "FASTA_EXTENSIONS", "IMAGE_EXTENSIONS"]
