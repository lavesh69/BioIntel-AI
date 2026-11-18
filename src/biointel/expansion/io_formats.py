from __future__ import annotations

import io
import json
import math
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage
from scipy.io import mmread


def _name(upload: Any) -> str:
    return str(getattr(upload, "name", "upload.dat"))


def _raw(upload: Any) -> bytes:
    if hasattr(upload, "getvalue"):
        return upload.getvalue()
    if hasattr(upload, "read"):
        return upload.read()
    raise TypeError("Unsupported upload object")


def _fasta_records(raw: bytes) -> list[tuple[str, str]]:
    text = raw.decode("utf-8-sig", errors="replace")
    records: list[tuple[str, str]] = []
    header: str | None = None
    chunks: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if header is not None:
                records.append((header, "".join(chunks).upper()))
            header = line[1:].strip() or f"sequence_{len(records) + 1}"
            chunks = []
        else:
            chunks.append(re.sub(r"[^A-Za-z*]", "", line))
    if header is not None:
        records.append((header, "".join(chunks).upper()))
    if not records:
        sequence = re.sub(r"[^A-Za-z*]", "", text).upper()
        if sequence:
            records = [("sequence_1", sequence)]
    return records


def _peptide_features(sequence: str) -> dict[str, float]:
    seq = sequence.upper()
    length = max(len(seq), 1)
    hydrophobic = set("AILMFWVY")
    charged = set("DEKR")
    aromatic = set("FWY")
    return {
        "hydrophobic_fraction": sum(a in hydrophobic for a in seq) / length,
        "charged_fraction": sum(a in charged for a in seq) / length,
        "aromatic_fraction": sum(a in aromatic for a in seq) / length,
        "cysteine_fraction": seq.count("C") / length,
    }


def _fasta_to_module(raw: bytes, module_key: str) -> pd.DataFrame:
    records = _fasta_records(raw)
    if not records:
        return pd.DataFrame()

    if module_key == "immunoinformatics_vaccine":
        rows: list[dict[str, Any]] = []
        alleles = ["HLA-A*02:01", "HLA-A*24:02", "HLA-B*07:02", "HLA-DRB1*04:01"]
        for record_id, sequence in records:
            lengths = (9, 15)
            for length in lengths:
                step = max(1, length // 3)
                for start in range(0, max(1, len(sequence) - length + 1), step):
                    peptide = sequence[start : start + length]
                    if len(peptide) != length:
                        continue
                    props = _peptide_features(peptide)
                    # Transparent heuristic scores, not MHC prediction.
                    binding = float(np.clip(0.35 + 0.45 * props["hydrophobic_fraction"] + 0.2 * props["aromatic_fraction"], 0, 1))
                    immunogenicity = float(np.clip(0.25 + 0.45 * props["charged_fraction"] + 0.25 * props["aromatic_fraction"], 0, 1))
                    toxicity = float(np.clip(0.05 + 0.9 * max(0, props["hydrophobic_fraction"] - 0.65) + 0.5 * props["cysteine_fraction"], 0, 1))
                    for allele in alleles:
                        rows.append({
                            "peptide": peptide,
                            "allele": allele,
                            "binding_score": binding,
                            "immunogenicity": immunogenicity,
                            "conservancy": 1.0,
                            "toxicity_risk": toxicity,
                            "source_sequence": record_id,
                            "start": start + 1,
                            "end": start + length,
                            **props,
                        })
        return pd.DataFrame(rows)

    if module_key == "antibody_biologics":
        rows = []
        for record_id, sequence in records:
            props = _peptide_features(sequence)
            liabilities = (
                sequence.count("NG") + sequence.count("NS") + sequence.count("NT")
                + sequence.count("DG") + sequence.count("DP") + sequence.count("DS")
                + sequence.count("M") + sequence.count("W")
            )
            aggregation = float(np.clip(0.1 + 1.1 * max(0, props["hydrophobic_fraction"] - 0.38), 0, 1))
            stability = float(np.clip(0.9 - 0.5 * aggregation - 0.02 * liabilities, 0, 1))
            humanness = float(np.clip(0.55 + 0.25 * (1 - abs(props["charged_fraction"] - 0.2)), 0, 1))
            rows.append({
                "variant": record_id,
                "affinity": 1.0,
                "stability": stability,
                "humanness": humanness,
                "aggregation_risk": aggregation,
                "liability_count": liabilities,
                "sequence": sequence,
                "sequence_length": len(sequence),
                **props,
            })
        return pd.DataFrame(rows)

    if module_key == "genome_editing_safety":
        rows = []
        for record_id, sequence in records:
            dna = re.sub(r"[^ACGT]", "", sequence.upper())
            for strand_name, seq in (("+", dna), ("-", _reverse_complement(dna))):
                for match in re.finditer(r"(?=([ACGT]{20}[ACGT]GG))", seq):
                    guide = match.group(1)[:20]
                    gc = (guide.count("G") + guide.count("C")) / 20
                    complexity = len(set(guide[i : i + 2] for i in range(19))) / 16
                    on_target = float(np.clip(0.85 - 1.8 * abs(gc - 0.5) + 0.15 * complexity, 0, 1))
                    rows.append({
                        "guide": guide,
                        "on_target": on_target,
                        "off_target_count": 0,
                        "max_mismatch": 0,
                        "bulge_count": 0,
                        "snp_overlap": 0,
                        "source_sequence": record_id,
                        "strand": strand_name,
                        "position": match.start() + 1,
                        "pam": match.group(1)[20:],
                        "gc_content": gc,
                        "sequence_complexity": complexity,
                    })
        return pd.DataFrame(rows)

    if module_key == "proteogenomics_neoantigen":
        rows = []
        for record_id, sequence in records:
            protein = re.sub(r"[^ACDEFGHIKLMNPQRSTVWY]", "", sequence.upper())
            for start in range(0, max(1, len(protein) - 8), 3):
                peptide = protein[start : start + 9]
                if len(peptide) != 9:
                    continue
                props = _peptide_features(peptide)
                hla = float(np.clip(0.3 + 0.5 * props["hydrophobic_fraction"] + 0.2 * props["aromatic_fraction"], 0, 1))
                rows.append({
                    "peptide": peptide,
                    "variant": f"{record_id}:{start + 1}-{start + 9}",
                    "expression": 1.0,
                    "spectral_score": 0.5,
                    "hla_binding": hla,
                    "clonality": 0.5,
                    "source_sequence": record_id,
                    "start": start + 1,
                    **props,
                })
        return pd.DataFrame(rows)

    return pd.DataFrame({"record": [h for h, _ in records], "sequence": [s for _, s in records]})


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(str.maketrans("ACGTN", "TGCAN"))[::-1]


def _vcf_to_module(raw: bytes, module_key: str) -> pd.DataFrame:
    text = raw.decode("utf-8-sig", errors="replace")
    rows: list[dict[str, Any]] = []
    samples: list[str] = []
    for line in text.splitlines():
        if line.startswith("#CHROM"):
            fields = line.split("\t")
            samples = fields[9:]
            continue
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 8:
            continue
        chrom, pos, vid, ref, alt, qual, filt, info = fields[:8]
        info_map = {}
        for token in info.split(";"):
            if "=" in token:
                key, value = token.split("=", 1)
                info_map[key] = value
        gene = next((info_map.get(k) for k in ("GENE", "SYMBOL", "HGNC", "ANN" ) if info_map.get(k)), "Unknown")
        if gene and "|" in gene:
            ann = gene.split(",")[0].split("|")
            gene = ann[3] if len(ann) > 3 and ann[3] else ann[0]
        variant = vid if vid not in (".", "") else f"{chrom}:{pos}:{ref}>{alt}"
        sample_names = samples or ["sample_1"]
        for sample in sample_names:
            if module_key == "pharmacogenomics":
                rows.append({
                    "sample": sample,
                    "gene": gene,
                    "variant": variant,
                    "drug": "Review required",
                    "phenotype": "Indeterminate",
                    "evidence_level": "Uncurated",
                    "chrom": chrom,
                    "position": int(pos),
                    "ref": ref,
                    "alt": alt,
                    "filter": filt,
                    "quality": pd.to_numeric(qual, errors="coerce"),
                })
            else:
                rows.append({"sample": sample, "gene": gene, "variant": variant, "chrom": chrom, "position": int(pos), "ref": ref, "alt": alt})
    return pd.DataFrame(rows)


def _bed_to_epigenomics(raw: bytes) -> pd.DataFrame:
    text = raw.decode("utf-8-sig", errors="replace")
    frame = pd.read_csv(io.StringIO(text), sep="\t", header=None, comment="#")
    if frame.shape[1] < 3:
        raise ValueError("BED input requires at least chromosome, start and end columns")
    rows = pd.DataFrame({
        "sample": frame.iloc[:, 3].astype(str) if frame.shape[1] > 3 else "sample_1",
        "region": frame.iloc[:, 0].astype(str) + ":" + frame.iloc[:, 1].astype(str) + "-" + frame.iloc[:, 2].astype(str),
        "condition": "Unspecified",
        "signal": pd.to_numeric(frame.iloc[:, 4], errors="coerce").fillna(1.0) if frame.shape[1] > 4 else 1.0,
        "gc_content": 0.5,
        "methylation": np.nan,
        "chrom": frame.iloc[:, 0].astype(str),
        "start": pd.to_numeric(frame.iloc[:, 1], errors="coerce"),
        "end": pd.to_numeric(frame.iloc[:, 2], errors="coerce"),
    })
    return rows


def _structure_to_docking(raw: bytes, suffix: str, name: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if suffix in {".sdf", ".mol", ".mol2"}:
        try:
            from rdkit import Chem
            from rdkit.Chem import Descriptors

            if suffix == ".sdf":
                supplier = Chem.ForwardSDMolSupplier(io.BytesIO(raw), sanitize=True, removeHs=False)
                molecules = [mol for mol in supplier if mol is not None]
            elif suffix == ".mol":
                molecules = [Chem.MolFromMolBlock(raw.decode("utf-8", errors="replace"), removeHs=False)]
            else:
                molecules = [Chem.MolFromMol2Block(raw.decode("utf-8", errors="replace"), removeHs=False)]
            for idx, mol in enumerate(molecules):
                if mol is None:
                    continue
                ligand = mol.GetProp("_Name") if mol.HasProp("_Name") and mol.GetProp("_Name") else f"{Path(name).stem}_{idx + 1}"
                mw = float(Descriptors.MolWt(mol))
                logp = float(Descriptors.MolLogP(mol))
                hbd = float(Descriptors.NumHDonors(mol))
                hba = float(Descriptors.NumHAcceptors(mol))
                rotors = float(Descriptors.NumRotatableBonds(mol))
                strain_proxy = max(0.0, rotors * 0.35 + max(0.0, abs(logp) - 4) * 0.4)
                docking_proxy = -(4.0 + 0.006 * mw + 0.18 * hba + 0.12 * hbd - 0.12 * max(logp, -1))
                rows.append({
                    "ligand": ligand,
                    "pose": 1,
                    "docking_score": docking_proxy,
                    "rmsd": np.nan,
                    "hbond_occupancy": min(1.0, (hbd + hba) / 12),
                    "strain_energy": strain_proxy,
                    "molecular_weight": mw,
                    "logp": logp,
                    "hbd": hbd,
                    "hba": hba,
                    "rotatable_bonds": rotors,
                    "score_source": "descriptor_proxy_not_docking",
                })
        except Exception as exc:
            raise ValueError(f"Could not parse ligand structure: {exc}") from exc
    else:
        text = raw.decode("utf-8", errors="replace")
        atom_lines = [line for line in text.splitlines() if line.startswith(("ATOM", "HETATM"))]
        residues = {line[17:26].strip() for line in atom_lines if len(line) >= 26}
        rows.append({
            "ligand": Path(name).stem,
            "pose": 1,
            "docking_score": np.nan,
            "rmsd": np.nan,
            "hbond_occupancy": np.nan,
            "strain_energy": np.nan,
            "atom_count": len(atom_lines),
            "residue_count": len(residues),
            "score_source": "structure_import_only",
        })
    return pd.DataFrame(rows)


def _image_to_measurements(raw: bytes, name: str) -> pd.DataFrame:
    image = Image.open(io.BytesIO(raw))
    arr = np.asarray(image.convert("L"), dtype=float)
    if arr.size == 0:
        return pd.DataFrame()
    # Robust threshold: median + 0.5 MAD; reverse if foreground is darker.
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median))) or float(np.std(arr)) or 1.0
    bright_mask = arr > median + 0.5 * mad
    dark_mask = arr < median - 0.5 * mad
    candidates = [candidate for candidate in (bright_mask, dark_mask) if 0 < candidate.mean() < 0.75]
    mask = min(candidates, key=lambda candidate: candidate.mean()) if candidates else bright_mask
    mask = ndimage.binary_opening(mask, iterations=1)
    mask = ndimage.binary_closing(mask, iterations=1)
    labels, count = ndimage.label(mask)
    objects = ndimage.find_objects(labels)
    rows: list[dict[str, Any]] = []
    for index, slc in enumerate(objects, start=1):
        if slc is None:
            continue
        object_mask = labels[slc] == index
        area = int(object_mask.sum())
        if area < 5:
            continue
        intensities = arr[slc][object_mask]
        perimeter = int((object_mask ^ ndimage.binary_erosion(object_mask)).sum())
        circularity = float(np.clip(4 * math.pi * area / max(perimeter * perimeter, 1), 0, 1))
        rows.append({
            "image_id": Path(name).stem,
            "object_id": f"OBJ-{index:05d}",
            "condition": "Unspecified",
            "area": area,
            "intensity": float(intensities.mean()) if len(intensities) else np.nan,
            "circularity": circularity,
            "bbox_y0": slc[0].start,
            "bbox_y1": slc[0].stop,
            "bbox_x0": slc[1].start,
            "bbox_x1": slc[1].stop,
            "segmentation_method": "robust_threshold_connected_components",
        })
    return pd.DataFrame(rows)


def _decode_h5_strings(values: Any) -> np.ndarray:
    array = np.asarray(values)
    if array.dtype.kind in {"S", "O", "U"}:
        return np.array([item.decode("utf-8", errors="replace") if isinstance(item, (bytes, bytearray)) else str(item) for item in array])
    return array.astype(str)


def _h5ad_to_module(raw: bytes, module_key: str) -> pd.DataFrame:
    obs_names: np.ndarray
    var_names: np.ndarray
    obs = pd.DataFrame()
    coords = None
    matrix: np.ndarray

    try:
        import anndata as ad

        with tempfile.NamedTemporaryFile(suffix=".h5ad", delete=True) as handle:
            handle.write(raw)
            handle.flush()
            obj = ad.read_h5ad(handle.name)
        n_obs = min(obj.n_obs, 5000)
        obs_names = np.asarray(obj.obs_names[:n_obs]).astype(str)
        var_names = np.asarray(obj.var_names).astype(str)
        obs = obj.obs.iloc[:n_obs].copy()
        if hasattr(obj.X, "toarray"):
            matrix = obj.X[:n_obs].toarray()
        else:
            matrix = np.asarray(obj.X[:n_obs])
        for key in ("spatial", "X_spatial"):
            if key in obj.obsm:
                coords = np.asarray(obj.obsm[key])[:n_obs]
                break
    except Exception:
        # Lightweight fallback for standard H5AD layouts when anndata is not installed.
        import h5py
        from scipy.sparse import csr_matrix

        with tempfile.NamedTemporaryFile(suffix=".h5ad", delete=True) as handle:
            handle.write(raw)
            handle.flush()
            with h5py.File(handle.name, "r") as h5:
                obs_group = h5.get("obs")
                var_group = h5.get("var")
                obs_index = obs_group.get("_index") if obs_group is not None else None
                var_index = var_group.get("_index") if var_group is not None else None
                if obs_index is None and "obs_names" in h5:
                    obs_index = h5["obs_names"]
                if var_index is None and "var_names" in h5:
                    var_index = h5["var_names"]
                if obs_index is None or var_index is None:
                    raise ValueError("H5AD fallback requires obs/_index and var/_index datasets")
                obs_names = _decode_h5_strings(obs_index[:])
                var_names = _decode_h5_strings(var_index[:])
                n_obs = min(len(obs_names), 5000)
                obs_names = obs_names[:n_obs]
                if obs_group is not None:
                    columns = {}
                    for name, node in obs_group.items():
                        if name == "_index" or not hasattr(node, "shape") or len(node.shape) != 1:
                            continue
                        try:
                            columns[name] = _decode_h5_strings(node[:n_obs])
                        except Exception:
                            continue
                    obs = pd.DataFrame(columns, index=obs_names)
                x_node = h5.get("X")
                if x_node is None:
                    raise ValueError("H5AD file does not contain X")
                if isinstance(x_node, h5py.Dataset):
                    matrix = np.asarray(x_node[:n_obs])
                elif all(name in x_node for name in ("data", "indices", "indptr")):
                    shape = tuple(int(v) for v in x_node.attrs.get("shape", (len(obs_names), len(var_names))))
                    sparse = csr_matrix((x_node["data"][:], x_node["indices"][:], x_node["indptr"][:]), shape=shape)
                    matrix = sparse[:n_obs].toarray()
                else:
                    raise ValueError("Unsupported H5AD X encoding")
                obsm = h5.get("obsm")
                if obsm is not None:
                    for key in ("spatial", "X_spatial"):
                        if key in obsm:
                            coords = np.asarray(obsm[key][:n_obs])
                            break

    n_obs = min(len(obs_names), matrix.shape[0], 5000)
    obs_names = obs_names[:n_obs]
    matrix = np.asarray(matrix[:n_obs])
    if matrix.ndim == 1:
        matrix = matrix[:, None]
    gene_index = int(np.nanargmax(np.nanvar(matrix, axis=0))) if matrix.shape[1] else 0
    expression = matrix[:, gene_index] if matrix.shape[1] else np.zeros(n_obs)
    gene = str(var_names[gene_index]) if len(var_names) else "feature_1"

    if module_key == "single_cell_trajectory":
        cluster_col = next((c for c in ("cluster", "leiden", "cell_type", "celltype") if c in obs.columns), None)
        cluster = obs[cluster_col].astype(str).to_numpy() if cluster_col else np.array(["Unassigned"] * n_obs)
        centered = matrix - np.nanmean(matrix, axis=0, keepdims=True)
        try:
            _, _, vt = np.linalg.svd(np.nan_to_num(centered), full_matrices=False)
            pc1 = centered @ vt[0]
            order = pd.Series(pc1).rank(pct=True).to_numpy()
        except Exception:
            order = np.linspace(0, 1, n_obs)
        return pd.DataFrame({
            "cell": obs_names,
            "cluster": cluster,
            "pseudotime": order,
            "ligand": "Unspecified",
            "receptor": "Unspecified",
            "expression": expression,
            "source_feature": gene,
        })

    if module_key == "spatial_omics_pathology":
        if coords is None or coords.shape[1] < 2:
            coords = np.column_stack((np.arange(n_obs), np.zeros(n_obs)))
        region_col = next((c for c in ("region", "cluster", "leiden", "cell_type") if c in obs.columns), None)
        region = obs[region_col].astype(str).to_numpy() if region_col else np.array(["Unassigned"] * n_obs)
        return pd.DataFrame({
            "spot": obs_names,
            "x": coords[:, 0],
            "y": coords[:, 1],
            "region": region,
            "gene": gene,
            "expression": expression,
        })

    return pd.DataFrame({"sample": obs_names, "feature": gene, "value": expression})


def _mtx_to_single_cell(raw: bytes, module_key: str) -> pd.DataFrame:
    matrix = mmread(io.BytesIO(raw))
    if hasattr(matrix, "toarray"):
        matrix = matrix.toarray()
    matrix = np.asarray(matrix)
    if matrix.shape[0] < matrix.shape[1]:
        matrix = matrix.T
    n = min(matrix.shape[0], 5000)
    values = matrix[:n, 0] if matrix.shape[1] else np.zeros(n)
    if module_key == "single_cell_trajectory":
        order = pd.Series(values).rank(pct=True).to_numpy()
        return pd.DataFrame({
            "cell": [f"cell_{i + 1}" for i in range(n)],
            "cluster": "Unassigned",
            "pseudotime": order,
            "ligand": "Unspecified",
            "receptor": "Unspecified",
            "expression": values,
        })
    if module_key == "spatial_omics_pathology":
        side = int(math.ceil(math.sqrt(n)))
        return pd.DataFrame({
            "spot": [f"spot_{i + 1}" for i in range(n)],
            "x": np.arange(n) % side,
            "y": np.arange(n) // side,
            "region": "Unassigned",
            "gene": "feature_1",
            "expression": values,
        })
    return pd.DataFrame(matrix[:n])


def _mzml_to_features(raw: bytes) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(raw)
        spectra = [node for node in root.iter() if node.tag.endswith("spectrum")]
        for index, spectrum in enumerate(spectra[:10000], start=1):
            spectrum_id = spectrum.attrib.get("id", f"spectrum_{index}")
            default_len = int(spectrum.attrib.get("defaultArrayLength", "0") or 0)
            ms_level = None
            tic = None
            base_peak = None
            scan_time = None
            for node in spectrum.iter():
                accession = node.attrib.get("accession", "")
                value = node.attrib.get("value")
                if accession == "MS:1000511":
                    ms_level = value
                elif accession == "MS:1000285":
                    tic = value
                elif accession == "MS:1000504":
                    base_peak = value
                elif accession == "MS:1000016":
                    scan_time = value
            rows.append({
                "sample": "mzML_import",
                "feature": spectrum_id,
                "group": "Unspecified",
                "intensity": pd.to_numeric(tic if tic is not None else base_peak, errors="coerce"),
                "blank_intensity": 0.0,
                "annotation_confidence": 0.0,
                "ms_level": pd.to_numeric(ms_level, errors="coerce"),
                "scan_time": pd.to_numeric(scan_time, errors="coerce"),
                "peak_count": default_len,
            })
    except Exception as exc:
        raise ValueError(f"Could not parse mzML/mzXML metadata: {exc}") from exc
    return pd.DataFrame(rows)


def read_scientific_upload(upload: Any, module_key: str) -> pd.DataFrame:
    """Read a supported scientific file and convert it to the module's analysis schema.

    Converters are deliberately transparent. Where a file cannot provide a required
    biological annotation, a neutral placeholder is inserted and clearly labelled.
    """
    raw = _raw(upload)
    name = _name(upload)
    suffix = Path(name.lower()).suffix

    if suffix == ".json":
        payload = json.loads(raw.decode("utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("records", payload.get("data", payload))
        return pd.DataFrame(payload)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(io.BytesIO(raw))
    if suffix in {".csv", ".tsv", ".txt"}:
        text = raw.decode("utf-8-sig", errors="replace")
        separator = "\t" if suffix in {".tsv", ".txt"} else ","
        try:
            return pd.read_csv(io.StringIO(text), sep=separator)
        except Exception:
            return pd.read_csv(io.StringIO(text), sep=None, engine="python")
    if suffix in {".fasta", ".fa", ".fna", ".faa", ".fas"}:
        return _fasta_to_module(raw, module_key)
    if suffix == ".vcf":
        return _vcf_to_module(raw, module_key)
    if suffix in {".bed", ".narrowpeak", ".broadpeak"} and module_key == "epigenomics_chromatin":
        return _bed_to_epigenomics(raw)
    if suffix in {".pdb", ".cif", ".mmcif", ".sdf", ".mol", ".mol2"} and module_key == "docking_dynamics":
        return _structure_to_docking(raw, suffix, name)
    if suffix in {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp"} and module_key == "bioimage_microscopy":
        return _image_to_measurements(raw, name)
    if suffix == ".h5ad" and module_key in {"single_cell_trajectory", "spatial_omics_pathology"}:
        return _h5ad_to_module(raw, module_key)
    if suffix == ".mtx" and module_key in {"single_cell_trajectory", "spatial_omics_pathology"}:
        return _mtx_to_single_cell(raw, module_key)
    if suffix in {".mzml", ".mzxml"} and module_key == "metabolomics_lipidomics":
        return _mzml_to_features(raw)
    raise ValueError(f"The file type '{suffix or 'unknown'}' is not supported by this module.")


TABLE_UPLOAD_EXTENSIONS = ["csv", "tsv", "txt", "json", "xlsx", "xls"]

MODULE_UPLOAD_EXTENSIONS: dict[str, list[str]] = {
    "epigenomics_chromatin": ["bed", "narrowpeak", "broadpeak"],
    "metabolomics_lipidomics": ["mzml", "mzxml"],
    "immunoinformatics_vaccine": ["fasta", "fa", "fna", "faa", "fas"],
    "antibody_biologics": ["fasta", "fa", "fna", "faa", "fas"],
    "docking_dynamics": ["pdb", "cif", "mmcif", "sdf", "mol", "mol2"],
    "pharmacogenomics": ["vcf"],
    "spatial_omics_pathology": ["h5ad", "mtx"],
    "single_cell_trajectory": ["h5ad", "mtx"],
    "bioimage_microscopy": ["tif", "tiff", "png", "jpg", "jpeg", "bmp"],
    "genome_editing_safety": ["fasta", "fa", "fna", "fas"],
    "proteogenomics_neoantigen": ["fasta", "fa", "faa", "fas"],
}


def supported_extensions_for_module(module_key: str) -> list[str]:
    """Return only the formats that the selected module can actually parse."""

    return list(dict.fromkeys(TABLE_UPLOAD_EXTENSIONS + MODULE_UPLOAD_EXTENSIONS.get(module_key, [])))


SUPPORTED_EXTENSIONS = sorted(
    {extension for values in [TABLE_UPLOAD_EXTENSIONS, *MODULE_UPLOAD_EXTENSIONS.values()] for extension in values}
)
