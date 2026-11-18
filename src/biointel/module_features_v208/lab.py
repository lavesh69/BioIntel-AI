from __future__ import annotations

import math
import re
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from scipy import ndimage, signal, stats

BOUNDARY = (
    "Research-software analysis only. Outputs do not replace calibrated instruments, "
    "validated assays, laboratory quality systems, biosafety review or expert sign-off."
)


def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Input must be a pandas DataFrame.")
    if frame.empty:
        raise ValueError("Input table is empty.")
    output = frame.copy()
    output.columns = [re.sub(r"[^a-z0-9]+", "_", str(column).strip().lower()).strip("_") for column in output.columns]
    return output


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def microscopy_image_qc(image: np.ndarray, *, segmentation_percentile: float = 75.0) -> dict[str, Any]:
    array = np.asarray(image)
    if array.ndim == 2:
        channels = array[..., None]
    elif array.ndim == 3:
        channels = array[..., : min(array.shape[2], 4)]
    else:
        raise ValueError("Microscopy image must be 2D or channel-last 3D.")
    data = channels.astype(float)
    finite = np.isfinite(data)
    if not finite.any():
        raise ValueError("Image contains no finite pixels.")
    channel_rows = []
    object_rows = []
    for channel_index in range(data.shape[2]):
        plane = data[..., channel_index]
        values = plane[np.isfinite(plane)]
        lower = float(np.nanpercentile(values, 1))
        upper = float(np.nanpercentile(values, 99))
        normalized = np.clip((plane - lower) / (upper - lower + 1e-12), 0, 1)
        laplace = ndimage.laplace(np.nan_to_num(normalized))
        focus = float(np.nanvar(laplace))
        saturation = float((normalized >= 0.995).mean())
        background = float(np.nanmedian(normalized))
        threshold = float(np.nanpercentile(normalized, segmentation_percentile))
        mask = normalized > threshold
        mask = ndimage.binary_opening(mask)
        mask = ndimage.binary_closing(mask)
        labels, count = ndimage.label(mask)
        areas = np.bincount(labels.ravel())[1:] if count else np.array([], dtype=int)
        channel_rows.append(
            {
                "channel": channel_index + 1,
                "focus_laplacian_variance": focus,
                "saturation_fraction": saturation,
                "background_median": background,
                "segmentation_threshold": threshold,
                "candidate_objects": int((areas >= 5).sum()),
                "candidate_area_fraction": float(mask.mean()),
            }
        )
        for object_index, area in enumerate(areas, start=1):
            if area < 5:
                continue
            coords = np.argwhere(labels == object_index)
            object_rows.append(
                {
                    "channel": channel_index + 1,
                    "object_id": object_index,
                    "area_pixels": int(area),
                    "centroid_y": float(coords[:, 0].mean()),
                    "centroid_x": float(coords[:, 1].mean()),
                }
            )
    channel_qc = pd.DataFrame(channel_rows)
    return {
        "channel_qc": channel_qc,
        "candidate_objects": pd.DataFrame(object_rows),
        "summary": {
            "image_shape": tuple(int(value) for value in array.shape),
            "channels": int(data.shape[2]),
            "low_focus_channels": int((channel_qc["focus_laplacian_variance"] < channel_qc["focus_laplacian_variance"].median() * 0.2).sum()) if len(channel_qc) > 1 else 0,
            "high_saturation_channels": int((channel_qc["saturation_fraction"] > 0.05).sum()),
            "candidate_objects": len(object_rows),
        },
        "scientific_boundary": BOUNDARY + " Segmentation is a transparent threshold workflow and requires assay-specific validation.",
    }


def high_content_plate_qc(
    data: pd.DataFrame,
    *,
    measurement_col: str = "measurement",
    well_col: str = "well",
    plate_col: str = "plate",
    control_col: str = "control_type",
) -> dict[str, Any]:
    frame = _normalise(data)
    keys = [measurement_col, well_col, plate_col, control_col]
    keys = [re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_") for key in keys]
    measurement_col, well_col, plate_col, control_col = keys
    missing = [column for column in keys if column not in frame]
    if missing:
        raise ValueError("Plate table missing: " + ", ".join(missing))
    frame[measurement_col] = _numeric(frame[measurement_col])
    frame = frame.dropna(subset=[measurement_col])
    if frame.empty:
        raise ValueError("No valid plate measurements remain.")
    frame["row"] = frame[well_col].astype(str).str.extract(r"([A-Za-z]+)", expand=False).str.upper()
    frame["column"] = _numeric(frame[well_col].astype(str).str.extract(r"(\d+)", expand=False))
    controls = frame[control_col].astype(str).str.lower()
    positive = frame.loc[controls.str.contains("positive|pos"), measurement_col]
    negative = frame.loc[controls.str.contains("negative|neg|vehicle"), measurement_col]
    z_prime = np.nan
    ssmd = np.nan
    if len(positive) >= 2 and len(negative) >= 2:
        difference = abs(float(positive.mean() - negative.mean()))
        z_prime = 1 - 3 * (float(positive.std(ddof=1)) + float(negative.std(ddof=1))) / difference if difference > 0 else np.nan
        ssmd = (float(positive.mean() - negative.mean())) / math.sqrt(float(positive.var(ddof=1) + negative.var(ddof=1))) if positive.var(ddof=1) + negative.var(ddof=1) > 0 else np.nan
    max_col = int(frame["column"].max()) if frame["column"].notna().any() else 0
    frame["edge_well"] = frame["row"].isin([frame["row"].dropna().min(), frame["row"].dropna().max()]) | frame["column"].isin([1, max_col])
    edge_mean = float(frame.loc[frame["edge_well"], measurement_col].mean()) if frame["edge_well"].any() else np.nan
    interior_mean = float(frame.loc[~frame["edge_well"], measurement_col].mean()) if (~frame["edge_well"]).any() else np.nan
    edge_effect = (edge_mean - interior_mean) / (frame[measurement_col].std(ddof=1) or 1.0) if math.isfinite(edge_mean) and math.isfinite(interior_mean) else np.nan
    plate_summary = frame.groupby(plate_col, as_index=False).agg(rows=(measurement_col, "size"), mean=(measurement_col, "mean"), sd=(measurement_col, "std"), missing=(measurement_col, lambda values: values.isna().sum()))
    median = float(negative.median()) if len(negative) else float(frame[measurement_col].median())
    mad = float(np.median(np.abs((negative if len(negative) else frame[measurement_col]) - median))) * 1.4826 + 1e-12
    frame["robust_activity_z"] = (frame[measurement_col] - median) / mad
    frame["hit_candidate"] = frame["robust_activity_z"].abs() >= 3.0
    return {
        "well_qc": frame.sort_values(["hit_candidate", "robust_activity_z"], ascending=[False, False]),
        "plate_summary": plate_summary,
        "summary": {
            "rows": len(frame),
            "plates": int(frame[plate_col].nunique()),
            "z_prime": float(z_prime) if math.isfinite(z_prime) else None,
            "ssmd": float(ssmd) if math.isfinite(ssmd) else None,
            "edge_effect_z": float(edge_effect) if math.isfinite(edge_effect) else None,
            "hit_candidates": int(frame["hit_candidate"].sum()),
        },
        "scientific_boundary": BOUNDARY + " Hit thresholds and controls require assay-specific qualification.",
    }


def bioprocess_time_series(
    data: pd.DataFrame,
    *,
    time_col: str = "time_hours",
    biomass_col: str = "biomass",
    product_col: str | None = "product",
    substrate_col: str | None = "substrate",
) -> dict[str, Any]:
    frame = _normalise(data)
    time_key = re.sub(r"[^a-z0-9]+", "_", time_col.lower()).strip("_")
    biomass_key = re.sub(r"[^a-z0-9]+", "_", biomass_col.lower()).strip("_")
    if time_key not in frame or biomass_key not in frame:
        raise ValueError("Bioprocess table requires time and biomass columns.")
    frame[time_key] = _numeric(frame[time_key])
    frame[biomass_key] = _numeric(frame[biomass_key])
    frame = frame.dropna(subset=[time_key, biomass_key]).sort_values(time_key)
    if len(frame) < 5 or frame[time_key].nunique() < 3:
        raise ValueError("At least five observations across three time points are required.")
    elapsed = frame[time_key].to_numpy(float)
    biomass = frame[biomass_key].clip(lower=1e-12).to_numpy(float)
    log_biomass = np.log(biomass)
    local_mu = np.gradient(log_biomass, elapsed)
    frame["specific_growth_rate_per_hour"] = local_mu
    frame["doubling_time_hours"] = np.where(local_mu > 0, math.log(2) / local_mu, np.nan)
    result_summary: dict[str, Any] = {
        "observations": len(frame),
        "peak_biomass": float(np.max(biomass)),
        "maximum_specific_growth_rate": float(np.nanmax(local_mu)),
        "median_doubling_time_hours": float(np.nanmedian(frame["doubling_time_hours"])),
    }
    product_key = re.sub(r"[^a-z0-9]+", "_", str(product_col or "").lower()).strip("_") or None
    substrate_key = re.sub(r"[^a-z0-9]+", "_", str(substrate_col or "").lower()).strip("_") or None
    if product_key and product_key in frame:
        frame[product_key] = _numeric(frame[product_key])
        frame["productivity_per_hour"] = np.gradient(frame[product_key], elapsed)
        result_summary["peak_product"] = float(frame[product_key].max())
        result_summary["mean_productivity_per_hour"] = float(np.nanmean(frame["productivity_per_hour"]))
    if substrate_key and substrate_key in frame:
        frame[substrate_key] = _numeric(frame[substrate_key])
        consumed = float(frame[substrate_key].iloc[0] - frame[substrate_key].iloc[-1])
        produced = float(frame[product_key].iloc[-1] - frame[product_key].iloc[0]) if product_key and product_key in frame else float(frame[biomass_key].iloc[-1] - frame[biomass_key].iloc[0])
        result_summary["yield_proxy"] = produced / consumed if consumed > 0 else None
    sensor_columns = [column for column in ("ph", "do", "temperature", "feed_rate") if column in frame]
    anomalies = []
    for column in sensor_columns:
        values = _numeric(frame[column]).interpolate(limit_direction="both")
        robust_scale = float(np.median(np.abs(values - np.median(values))) * 1.4826) or 1e-12
        z = np.abs(values - np.median(values)) / robust_scale
        for index in np.where(z > 5)[0]:
            anomalies.append({"time_hours": float(frame[time_key].iloc[index]), "sensor": column, "value": float(values.iloc[index]), "robust_z": float(z.iloc[index])})
    return {"time_series": frame, "sensor_anomalies": pd.DataFrame(anomalies), "summary": result_summary, "scientific_boundary": BOUNDARY + " Process recommendations require calibrated sensors and engineering review."}


def metagenomics_control_qc(
    data: pd.DataFrame,
    *,
    sample_col: str = "sample_id",
    feature_col: str = "taxon",
    abundance_col: str = "abundance",
    control_col: str = "is_negative_control",
) -> dict[str, Any]:
    frame = _normalise(data)
    keys = [sample_col, feature_col, abundance_col, control_col]
    keys = [re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_") for key in keys]
    sample_col, feature_col, abundance_col, control_col = keys
    missing = [key for key in keys if key not in frame]
    if missing:
        raise ValueError("Metagenomics QC missing: " + ", ".join(missing))
    frame[abundance_col] = _numeric(frame[abundance_col]).fillna(0)
    frame["negative_control"] = frame[control_col].astype(str).str.lower().isin({"1", "true", "yes", "negative", "control"})
    if not frame["negative_control"].any():
        raise ValueError("At least one negative-control sample is required.")
    presence = frame.assign(present=frame[abundance_col] > 0)
    feature = presence.groupby(feature_col, as_index=False).agg(
        control_prevalence=("present", lambda values: float(values[presence.loc[values.index, "negative_control"]].mean()) if presence.loc[values.index, "negative_control"].any() else 0.0),
        sample_prevalence=("present", lambda values: float(values[~presence.loc[values.index, "negative_control"]].mean()) if (~presence.loc[values.index, "negative_control"]).any() else 0.0),
        total_abundance=(abundance_col, "sum"),
    )
    feature["contamination_candidate"] = (feature["control_prevalence"] >= 0.5) & (feature["control_prevalence"] >= feature["sample_prevalence"])
    candidates = set(feature.loc[feature["contamination_candidate"], feature_col].astype(str))
    frame["candidate_contaminant_abundance"] = np.where(frame[feature_col].astype(str).isin(candidates), frame[abundance_col], 0.0)
    sample = frame.groupby(sample_col, as_index=False).agg(total_abundance=(abundance_col, "sum"), candidate_contaminant_abundance=("candidate_contaminant_abundance", "sum"), negative_control=("negative_control", "max"))
    sample["candidate_contaminant_fraction"] = sample["candidate_contaminant_abundance"] / sample["total_abundance"].replace(0, np.nan)
    return {"feature_qc": feature.sort_values(["contamination_candidate", "control_prevalence"], ascending=False), "sample_qc": sample, "summary": {"samples": int(frame[sample_col].nunique()), "negative_controls": int(frame.loc[frame["negative_control"], sample_col].nunique()), "features": int(frame[feature_col].nunique()), "candidate_contaminants": len(candidates)}, "scientific_boundary": BOUNDARY + " Taxonomic classifications and contamination candidates require database-version and protocol review."}


def synthetic_construct_qc(sequence: str, *, construct_name: str = "construct") -> dict[str, Any]:
    seq = re.sub(r"[^ACGTNacgtn]", "", str(sequence)).upper()
    if len(seq) < 20:
        raise ValueError("DNA sequence must contain at least 20 bases.")
    gc = (seq.count("G") + seq.count("C")) / len(seq)
    homopolymers = []
    for base in "ACGT":
        for match in re.finditer(base + "{6,}", seq):
            homopolymers.append({"base": base, "start_1based": match.start() + 1, "length": len(match.group())})
    restriction_sites = {
        "EcoRI": "GAATTC",
        "BamHI": "GGATCC",
        "HindIII": "AAGCTT",
        "BsaI": "GGTCTC",
        "BsmBI": "CGTCTC",
        "NotI": "GCGGCCGC",
    }
    site_rows = []
    for enzyme, motif in restriction_sites.items():
        positions = [match.start() + 1 for match in re.finditer(f"(?={motif})", seq)]
        site_rows.append({"enzyme": enzyme, "motif": motif, "count": len(positions), "positions_1based": ",".join(map(str, positions))})
    repeats = []
    for size in range(8, 21):
        counts: dict[str, list[int]] = {}
        for index in range(len(seq) - size + 1):
            kmer = seq[index:index+size]
            counts.setdefault(kmer, []).append(index + 1)
        for kmer, positions in counts.items():
            if len(positions) >= 3:
                repeats.append({"kmer": kmer, "length": size, "occurrences": len(positions), "positions_1based": ",".join(map(str, positions[:20]))})
        if repeats:
            break
    sbol_like = {
        "schema": "biointel.sbol-like.v208",
        "displayId": re.sub(r"[^A-Za-z0-9_]+", "_", construct_name),
        "type": "DNA",
        "length": len(seq),
        "sequence": seq,
        "note": "Interoperability JSON; not a full SBOL document.",
    }
    return {"restriction_sites": pd.DataFrame(site_rows), "homopolymers": pd.DataFrame(homopolymers), "repeats": pd.DataFrame(repeats), "summary": {"construct_name": construct_name, "length": len(seq), "gc_fraction": gc, "ambiguous_bases": seq.count("N"), "homopolymer_runs": len(homopolymers), "repeat_flags": len(repeats)}, "sbol_like_export": sbol_like, "scientific_boundary": BOUNDARY + " Construct feasibility and biosafety require sequence verification and institutional review."}


def primer_crispr_qc(
    *,
    primers: pd.DataFrame | None = None,
    target_sequence: str | None = None,
    genome_sequence: str | None = None,
    pam: str = "NGG",
) -> dict[str, Any]:
    primer_rows = []
    if primers is not None and not primers.empty:
        frame = _normalise(primers)
        sequence_col = next((column for column in ("sequence", "primer_sequence", "primer") if column in frame), None)
        if sequence_col is None:
            raise ValueError("Primer table requires a sequence column.")
        for index, record in frame.iterrows():
            sequence = re.sub(r"[^ACGTacgt]", "", str(record[sequence_col])).upper()
            if not sequence:
                continue
            gc = (sequence.count("G") + sequence.count("C")) / len(sequence)
            tm = 2 * (sequence.count("A") + sequence.count("T")) + 4 * (sequence.count("G") + sequence.count("C"))
            reverse_complement = sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]
            window = min(8, len(sequence))
            self_complement = max(
                (
                    sum(a == b for a, b in zip(sequence[i : i + window], reverse_complement[j : j + window]))
                    for i in range(max(1, len(sequence) - window + 1))
                    for j in range(max(1, len(sequence) - window + 1))
                ),
                default=0,
            )
            matches = genome_sequence.upper().count(sequence) if genome_sequence else None
            primer_rows.append({"primer_id": str(record.get("primer_id", f"primer_{index+1}")), "sequence": sequence, "length": len(sequence), "gc_fraction": gc, "wallace_tm_c": tm, "self_complementarity_proxy": self_complement, "exact_genome_matches": matches, "specificity_status": "review" if matches is None else "unique" if matches == 1 else "non-unique"})
    guide_rows = []
    if target_sequence:
        sequence = re.sub(r"[^ACGTacgt]", "", target_sequence).upper()
        pam_regex = pam.upper().replace("N", "[ACGT]")
        for match in re.finditer(f"(?=([ACGT]{{20}})({pam_regex}))", sequence):
            guide = match.group(1)
            gc = (guide.count("G") + guide.count("C")) / 20
            exact_matches = genome_sequence.upper().count(guide) if genome_sequence else None
            guide_rows.append({"start_1based": match.start() + 1, "guide": guide, "pam": match.group(2), "gc_fraction": gc, "poly_t_flag": "TTTT" in guide, "exact_genome_matches": exact_matches, "off_target_status": "adapter/reference required" if exact_matches is None else "unique exact match" if exact_matches == 1 else "multiple exact matches"})
    return {"primer_qc": pd.DataFrame(primer_rows), "guide_candidates": pd.DataFrame(guide_rows), "summary": {"primers": len(primer_rows), "guides": len(guide_rows), "reference_genome_supplied": bool(genome_sequence)}, "scientific_boundary": BOUNDARY + " Exact-string matching is not a genome-wide mismatch/bulge off-target model."}


def organoid_3d_analysis(data: pd.DataFrame) -> dict[str, Any]:
    frame = _normalise(data)
    id_col = next((column for column in ("organoid_id", "object_id", "sample_id") if column in frame), None)
    if id_col is None:
        raise ValueError("Organoid table requires an organoid identifier.")
    if "volume" in frame:
        volume = _numeric(frame["volume"])
    elif all(column in frame for column in ("diameter_x", "diameter_y", "diameter_z")):
        dx, dy, dz = (_numeric(frame[column]) for column in ("diameter_x", "diameter_y", "diameter_z"))
        volume = math.pi / 6 * dx * dy * dz
        frame["volume"] = volume
    else:
        raise ValueError("Provide volume or three orthogonal diameters.")
    frame["volume"] = volume
    frame["equivalent_diameter"] = (6 * frame["volume"] / math.pi).clip(lower=0) ** (1 / 3)
    if "time" in frame:
        frame["time"] = _numeric(frame["time"])
        rows = []
        for organoid, group in frame.groupby(id_col):
            valid = group[["time", "volume"]].dropna()
            slope = float(np.polyfit(valid["time"], valid["volume"], 1)[0]) if len(valid) >= 2 and valid["time"].nunique() > 1 else np.nan
            rows.append({"organoid_id": organoid, "observations": len(valid), "volume_change_per_time": slope, "initial_volume": float(valid["volume"].iloc[0]) if len(valid) else np.nan, "final_volume": float(valid["volume"].iloc[-1]) if len(valid) else np.nan})
        trajectory = pd.DataFrame(rows)
    else:
        trajectory = pd.DataFrame()
    return {"measurements": frame, "trajectories": trajectory, "summary": {"organoids": int(frame[id_col].nunique()), "rows": len(frame), "median_volume": float(frame["volume"].median())}, "scientific_boundary": BOUNDARY + " Volumes and growth require calibrated imaging and replicate-aware experimental design."}


def gene_therapy_vector_qc(
    sequence: str,
    *,
    vector_type: str = "AAV",
    promoter: str | None = None,
    target_tissue: str | None = None,
) -> dict[str, Any]:
    seq = re.sub(r"[^ACGTNacgtn]", "", str(sequence)).upper()
    if len(seq) < 100:
        raise ValueError("Vector sequence must contain at least 100 bases.")
    vector_type_upper = vector_type.upper()
    capacity = {"AAV": 4700, "LENTIVIRAL": 8000, "ADENOVIRAL": 36000}.get(vector_type_upper, 5000)
    cpg = len(re.findall(r"CG", seq))
    itr_like = len(re.findall(r"G{3,}C{3,}|C{3,}G{3,}", seq))
    homology = max((len(match.group()) for match in re.finditer(r"(A{8,}|C{8,}|G{8,}|T{8,})", seq)), default=0)
    return {"vector_qc": pd.DataFrame([{"vector_type": vector_type_upper, "length": len(seq), "capacity": capacity, "capacity_remaining": capacity-len(seq), "over_capacity": len(seq) > capacity, "gc_fraction": (seq.count("G")+seq.count("C"))/len(seq), "cpg_count": cpg, "itr_like_motif_count": itr_like, "longest_homopolymer": homology, "promoter": promoter, "target_tissue": target_tissue}]), "summary": {"packaging_feasible_by_length": len(seq) <= capacity, "sequence_length": len(seq), "capacity": capacity, "ambiguous_bases": seq.count("N")}, "scientific_boundary": BOUNDARY + " Packaging, integration, biodistribution and immunogenicity require platform-specific assays."}


def autonomous_experiment_plan(
    *,
    groups: Sequence[str],
    replicates: int,
    blocks: Sequence[str] = (),
    controls: Sequence[str] = ("negative_control", "positive_control"),
    seed: int = 208,
) -> dict[str, Any]:
    if len(groups) < 2:
        raise ValueError("At least two experimental groups are required.")
    if replicates < 2:
        raise ValueError("At least two replicates per group are required.")
    blocks = tuple(blocks or ("Block-1",))
    assignments = []
    for group in groups:
        for replicate in range(1, replicates + 1):
            assignments.append({"group": group, "replicate": replicate, "record_type": "sample"})
    for control in controls:
        for replicate in range(1, max(2, min(replicates, 4)) + 1):
            assignments.append({"group": control, "replicate": replicate, "record_type": "control"})
    rng = np.random.default_rng(seed)
    rng.shuffle(assignments)
    for index, assignment in enumerate(assignments):
        assignment["run_order"] = index + 1
        assignment["block"] = blocks[index % len(blocks)]
    plan = pd.DataFrame(assignments).sort_values("run_order")
    approvals = pd.DataFrame(
        [
            {"gate": "Scientific objective and endpoint review", "required": True, "status": "pending human approval"},
            {"gate": "Biosafety/ethics review when applicable", "required": True, "status": "pending human approval"},
            {"gate": "Instrument method qualification", "required": True, "status": "pending human approval"},
            {"gate": "Control and stopping-rule approval", "required": True, "status": "pending human approval"},
        ]
    )
    return {"run_plan": plan, "approval_gates": approvals, "summary": {"groups": list(groups), "replicates": replicates, "blocks": list(blocks), "controls": list(controls), "runs": len(plan), "direct_instrument_control": False}, "scientific_boundary": BOUNDARY + " This planner cannot autonomously execute instruments or bypass human approval."}


LAB_V208_FEATURES: tuple[tuple[str, str, str], ...] = (
    ("microscopy_qc", "Bioimage & Microscopy QC", "Focus, saturation, background, channel QC and candidate segmentation."),
    ("plate_qc", "High-Content Plate QC", "Controls, Z-prime, SSMD, edge effects and hit candidates."),
    ("bioprocess", "Bioprocess & Fermentation Time-Series", "Growth, doubling time, yield, productivity and sensor anomalies."),
    ("metagenomics_controls", "Metagenomics Control & Contamination QC", "Negative controls, prevalence and contaminant burden."),
    ("synthetic_biology", "Synthetic Construct & SBOL-like Review", "Restriction sites, repeats, GC, homopolymers and interoperable JSON."),
    ("primer_crispr", "Primer, CRISPR & Codon Safety QC", "Primer properties, guide candidates and explicit off-target limits."),
    ("organoid", "Organoid & 3D Model Analytics", "Volumes, equivalent diameters and longitudinal growth trajectories."),
    ("gene_therapy", "Gene Therapy Vector Engineering QC", "Cargo capacity, GC/CpG, ITR-like motifs and sequence risks."),
    ("experiment_planner", "Human-Gated Experiment Planner", "Randomization, blocking, controls and explicit approval gates."),
)
