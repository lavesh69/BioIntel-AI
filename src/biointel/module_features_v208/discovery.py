from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.covariance import LedoitWolf
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler

BOUNDARY = (
    "Research-software screening only. Outputs are not measured assay values, clinical "
    "predictions, regulatory evidence or wet-lab validation."
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


def standardize_compounds(data: pd.DataFrame, *, smiles_col: str = "smiles", id_col: str = "compound_id") -> dict[str, Any]:
    frame = _normalise(data)
    smiles_key = re.sub(r"[^a-z0-9]+", "_", smiles_col.lower()).strip("_")
    id_key = re.sub(r"[^a-z0-9]+", "_", id_col.lower()).strip("_")
    if smiles_key not in frame:
        raise ValueError("Compound table requires a SMILES column.")
    from rdkit import Chem, rdBase
    from rdkit.Chem import Descriptors, Lipinski, rdMolDescriptors
    from rdkit.Chem.MolStandardize import rdMolStandardize
    from rdkit.Chem.Scaffolds import MurckoScaffold

    chooser = rdMolStandardize.LargestFragmentChooser()
    uncharger = rdMolStandardize.Uncharger()
    tautomer = rdMolStandardize.TautomerEnumerator()
    rows = []
    for index, record in frame.iterrows():
        source = str(record.get(smiles_key, "") or "").strip()
        compound_id = str(record.get(id_key, f"compound_{index+1}")) if id_key in frame else f"compound_{index+1}"
        with rdBase.BlockLogs():
            mol = Chem.MolFromSmiles(source)
        if mol is None:
            rows.append({"compound_id": compound_id, "input_smiles": source, "valid": False, "error": "SMILES could not be parsed"})
            continue
        try:
            fragment = chooser.choose(mol)
            neutral = uncharger.uncharge(fragment)
            canonical_tautomer = tautomer.Canonicalize(neutral)
            canonical = Chem.MolToSmiles(canonical_tautomer, canonical=True, isomericSmiles=True)
            scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=canonical_tautomer)
            chiral_centers = Chem.FindMolChiralCenters(canonical_tautomer, includeUnassigned=True)
            rows.append(
                {
                    "compound_id": compound_id,
                    "input_smiles": source,
                    "valid": True,
                    "standardized_smiles": canonical,
                    "murcko_scaffold": scaffold,
                    "molecular_weight": float(Descriptors.MolWt(canonical_tautomer)),
                    "logp": float(Descriptors.MolLogP(canonical_tautomer)),
                    "tpsa": float(rdMolDescriptors.CalcTPSA(canonical_tautomer)),
                    "hbd": int(Lipinski.NumHDonors(canonical_tautomer)),
                    "hba": int(Lipinski.NumHAcceptors(canonical_tautomer)),
                    "rotatable_bonds": int(Lipinski.NumRotatableBonds(canonical_tautomer)),
                    "formal_charge": int(Chem.GetFormalCharge(canonical_tautomer)),
                    "stereo_centers": len(chiral_centers),
                    "unassigned_stereo_centers": sum(label == "?" for _, label in chiral_centers),
                    "multi_fragment_input": "." in source,
                    "changed_by_standardization": canonical != Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True),
                    "error": None,
                }
            )
        except Exception as exc:
            rows.append({"compound_id": compound_id, "input_smiles": source, "valid": False, "error": f"{type(exc).__name__}: {exc}"})
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("No compounds were supplied.")
    result["duplicate_standardized_structure"] = result["standardized_smiles"].duplicated(keep=False) if "standardized_smiles" in result else False
    result["lipinski_alert_count"] = 0
    if "valid" in result:
        valid = result["valid"].fillna(False)
        for column, threshold in (("molecular_weight", 500), ("logp", 5), ("hbd", 5), ("hba", 10)):
            if column in result:
                result.loc[valid, "lipinski_alert_count"] += (result.loc[valid, column] > threshold).astype(int)
    scaffold_summary = (
        result[result.get("valid", False)].groupby("murcko_scaffold", dropna=False, as_index=False).agg(compounds=("compound_id", "size"), structures=("standardized_smiles", "nunique"))
        if "murcko_scaffold" in result else pd.DataFrame()
    )
    return {
        "compounds": result,
        "scaffolds": scaffold_summary.sort_values("compounds", ascending=False) if not scaffold_summary.empty else scaffold_summary,
        "summary": {
            "input_compounds": len(result),
            "valid_compounds": int(result["valid"].fillna(False).sum()),
            "invalid_compounds": int((~result["valid"].fillna(False)).sum()),
            "duplicate_structure_rows": int(result["duplicate_standardized_structure"].fillna(False).sum()),
            "unique_scaffolds": int(result.loc[result["valid"].fillna(False), "murcko_scaffold"].nunique()) if "murcko_scaffold" in result else 0,
        },
        "scientific_boundary": BOUNDARY + " Standardization decisions are recorded and should be reviewed before modelling.",
    }


def docking_validation(data: pd.DataFrame) -> dict[str, Any]:
    frame = _normalise(data)
    pose_col = next((column for column in ("pose_id", "pose", "rank") if column in frame), None)
    ligand_col = next((column for column in ("compound_id", "ligand_id", "ligand") if column in frame), None)
    score_col = next((column for column in ("docking_score", "score", "energy") if column in frame), None)
    if not ligand_col or not score_col:
        raise ValueError("Docking table requires ligand and score columns.")
    frame[score_col] = _numeric(frame[score_col])
    frame = frame.dropna(subset=[score_col])
    rmsd_col = next((column for column in ("redocking_rmsd", "rmsd", "pose_rmsd") if column in frame), None)
    if rmsd_col:
        frame[rmsd_col] = _numeric(frame[rmsd_col])
        frame["redocking_pass"] = frame[rmsd_col] <= 2.0
    else:
        frame["redocking_pass"] = False
    interaction_cols = [column for column in frame.columns if column.startswith("interaction_") or column in {"h_bonds", "salt_bridges", "pi_contacts"}]
    if interaction_cols:
        for column in interaction_cols:
            frame[column] = _numeric(frame[column]).fillna(0)
        frame["interaction_support"] = frame[interaction_cols].sum(axis=1)
    else:
        frame["interaction_support"] = 0.0
    direction = -1.0 if frame[score_col].median() < 0 else 1.0
    scaled_score = (frame[score_col] - frame[score_col].mean()) / (frame[score_col].std(ddof=1) or 1.0)
    frame["consensus_pose_score"] = -direction * scaled_score + 0.15 * frame["interaction_support"] + 0.5 * frame["redocking_pass"].astype(float)
    best = frame.sort_values([ligand_col, "consensus_pose_score"], ascending=[True, False]).groupby(ligand_col, as_index=False).first()
    replicate = frame.groupby(ligand_col, as_index=False).agg(poses=(score_col, "size"), score_mean=(score_col, "mean"), score_sd=(score_col, "std"), redocking_pass_fraction=("redocking_pass", "mean"), interaction_support_mean=("interaction_support", "mean"))
    return {
        "pose_review": frame.sort_values("consensus_pose_score", ascending=False).reset_index(drop=True),
        "best_pose_per_ligand": best,
        "ligand_summary": replicate,
        "summary": {
            "ligands": int(frame[ligand_col].nunique()),
            "poses": len(frame),
            "redocking_rmsd_available": bool(rmsd_col),
            "redocking_pass_fraction": float(frame["redocking_pass"].mean()),
            "interaction_columns": interaction_cols,
        },
        "scientific_boundary": BOUNDARY + " Docking scores and poses require engine qualification and experimental confirmation.",
    }


def admet_calibration_and_domain(
    reference: pd.DataFrame,
    query: pd.DataFrame,
    *,
    measured_col: str = "measured",
    predicted_col: str = "predicted",
    id_col: str = "compound_id",
) -> dict[str, Any]:
    ref = _normalise(reference)
    qry = _normalise(query)
    measured_key = re.sub(r"[^a-z0-9]+", "_", measured_col.lower()).strip("_")
    predicted_key = re.sub(r"[^a-z0-9]+", "_", predicted_col.lower()).strip("_")
    if measured_key not in ref or predicted_key not in ref:
        raise ValueError("Reference data requires measured and predicted columns.")
    measured = _numeric(ref[measured_key])
    predicted = _numeric(ref[predicted_key])
    valid = measured.notna() & predicted.notna()
    if valid.sum() < 8:
        raise ValueError("At least eight measured/predicted reference pairs are required.")
    error = predicted[valid] - measured[valid]
    slope, intercept, r_value, p_value, slope_stderr = stats.linregress(predicted[valid], measured[valid])
    ref["calibrated_prediction"] = intercept + slope * _numeric(ref[predicted_key])
    descriptor_candidates = [column for column in ref.columns if column not in {measured_key, predicted_key, id_col} and _numeric(ref[column]).notna().sum() >= valid.sum() * 0.8 and column in qry]
    domain = pd.DataFrame()
    if descriptor_candidates:
        X_ref = ref[descriptor_candidates].apply(_numeric).fillna(ref[descriptor_candidates].apply(_numeric).median())
        X_qry = qry[descriptor_candidates].apply(_numeric).fillna(X_ref.median())
        scaler = StandardScaler().fit(X_ref)
        Z_ref = scaler.transform(X_ref)
        Z_qry = scaler.transform(X_qry)
        covariance = LedoitWolf().fit(Z_ref)
        distances = np.sqrt(covariance.mahalanobis(Z_qry))
        threshold = float(np.quantile(np.sqrt(covariance.mahalanobis(Z_ref)), 0.975))
        identifier = qry[id_col].astype(str) if id_col in qry else pd.Series([f"query_{i+1}" for i in range(len(qry))])
        domain = pd.DataFrame({"compound_id": identifier, "mahalanobis_distance": distances, "domain_threshold_97_5": threshold, "inside_applicability_domain": distances <= threshold})
    else:
        threshold = None
    calibration = pd.DataFrame({"measured": measured[valid], "predicted": predicted[valid], "calibrated_prediction": intercept + slope * predicted[valid], "residual": error})
    return {
        "calibration": calibration,
        "query_applicability_domain": domain,
        "summary": {
            "reference_pairs": int(valid.sum()),
            "mae_raw": float(mean_absolute_error(measured[valid], predicted[valid])),
            "r2_raw": float(r2_score(measured[valid], predicted[valid])),
            "calibration_slope": float(slope),
            "calibration_intercept": float(intercept),
            "calibration_r": float(r_value),
            "descriptor_features": descriptor_candidates,
            "domain_threshold": threshold,
            "inside_domain_fraction": float(domain["inside_applicability_domain"].mean()) if not domain.empty else None,
        },
        "scientific_boundary": BOUNDARY + " Applicability domain and calibration are dataset-specific.",
    }


def lead_optimization_ranking(
    data: pd.DataFrame,
    *,
    maximize: Sequence[str],
    minimize: Sequence[str],
    id_col: str = "compound_id",
    scaffold_col: str | None = "scaffold",
) -> dict[str, Any]:
    frame = _normalise(data)
    maximize_keys = [re.sub(r"[^a-z0-9]+", "_", column.lower()).strip("_") for column in maximize]
    minimize_keys = [re.sub(r"[^a-z0-9]+", "_", column.lower()).strip("_") for column in minimize]
    objectives = maximize_keys + minimize_keys
    missing = [column for column in objectives if column not in frame]
    if missing:
        raise ValueError("Missing optimization objective(s): " + ", ".join(missing))
    values = frame[objectives].apply(_numeric)
    valid = values.notna().all(axis=1)
    working = frame.loc[valid].copy()
    values = values.loc[valid]
    if len(working) < 2:
        raise ValueError("At least two candidates with complete objectives are required.")
    normalized = pd.DataFrame(index=working.index)
    for column in maximize_keys:
        series = values[column]
        normalized[column] = (series - series.min()) / (series.max() - series.min() + 1e-12)
    for column in minimize_keys:
        series = values[column]
        normalized[column] = (series.max() - series) / (series.max() - series.min() + 1e-12)
    scores = normalized.to_numpy(float)
    dominated = np.zeros(len(scores), dtype=bool)
    for i in range(len(scores)):
        for j in range(len(scores)):
            if i != j and np.all(scores[j] >= scores[i]) and np.any(scores[j] > scores[i]):
                dominated[i] = True
                break
    working["pareto_front"] = ~dominated
    working["balanced_objective_score"] = normalized.mean(axis=1)
    scaffold_key = re.sub(r"[^a-z0-9]+", "_", str(scaffold_col or "").lower()).strip("_") or None
    if scaffold_key and scaffold_key in working:
        scaffold_count = working[scaffold_key].astype(str).map(working[scaffold_key].astype(str).value_counts())
        working["scaffold_diversity_bonus"] = 1 / np.sqrt(scaffold_count)
    else:
        working["scaffold_diversity_bonus"] = 0.0
    working["internal_progression_score"] = working["balanced_objective_score"] + 0.1 * working["scaffold_diversity_bonus"] + 0.15 * working["pareto_front"].astype(float)
    working = working.sort_values(["pareto_front", "internal_progression_score"], ascending=[False, False]).reset_index(drop=True)
    working["internal_rank"] = np.arange(1, len(working) + 1)
    return {
        "ranking": working,
        "objective_normalized": normalized.reset_index(drop=True),
        "summary": {"input_candidates": len(frame), "ranked_candidates": len(working), "pareto_front": int(working["pareto_front"].sum()), "maximize": maximize_keys, "minimize": minimize_keys},
        "scientific_boundary": BOUNDARY + " Progression ranking reflects selected objectives and weights, not efficacy or safety proof.",
    }


def protein_design_qc(
    reference_sequence: str,
    candidates: pd.DataFrame,
    *,
    sequence_col: str = "sequence",
    id_col: str = "candidate_id",
    conserved_positions: Sequence[int] = (),
) -> dict[str, Any]:
    reference = re.sub(r"[^A-Za-z]", "", str(reference_sequence)).upper()
    if not reference:
        raise ValueError("Reference protein sequence is empty.")
    frame = _normalise(candidates)
    sequence_key = re.sub(r"[^a-z0-9]+", "_", sequence_col.lower()).strip("_")
    id_key = re.sub(r"[^a-z0-9]+", "_", id_col.lower()).strip("_")
    if sequence_key not in frame:
        raise ValueError("Candidate table requires a sequence column.")
    hydrophobic = set("AILMFWVY")
    charged = set("DEKR")
    rows = []
    for index, record in frame.iterrows():
        sequence = re.sub(r"[^A-Za-z]", "", str(record[sequence_key])).upper()
        candidate_id = str(record.get(id_key, f"candidate_{index+1}")) if id_key in frame else f"candidate_{index+1}"
        if not sequence:
            rows.append({"candidate_id": candidate_id, "valid": False, "error": "Empty sequence"})
            continue
        max_len = max(len(reference), len(sequence))
        matches = sum(reference[i] == sequence[i] for i in range(min(len(reference), len(sequence))))
        identity = matches / max_len
        changes = [i + 1 for i in range(min(len(reference), len(sequence))) if reference[i] != sequence[i]]
        changes.extend(range(min(len(reference), len(sequence)) + 1, max_len + 1))
        conserved_violations = [position for position in conserved_positions if position in changes]
        hydro_fraction = sum(char in hydrophobic for char in sequence) / len(sequence)
        charge = sum(char in "KR" for char in sequence) - sum(char in "DE" for char in sequence)
        aggregation_windows = sum(sum(char in hydrophobic for char in sequence[i:i+7]) >= 6 for i in range(max(0, len(sequence)-6)))
        rows.append({"candidate_id": candidate_id, "valid": True, "length": len(sequence), "sequence_identity": identity, "mutation_count": len(changes), "conserved_position_violations": len(conserved_violations), "conserved_positions_changed": ",".join(map(str, conserved_violations)), "hydrophobic_fraction": hydro_fraction, "net_charge_proxy": charge, "hydrophobic_aggregation_windows": aggregation_windows, "sequence": sequence, "error": None})
    result = pd.DataFrame(rows)
    if "valid" in result:
        result["design_review_score"] = result["sequence_identity"].fillna(0) - 0.08 * result["conserved_position_violations"].fillna(0) - 0.02 * result["hydrophobic_aggregation_windows"].fillna(0)
    return {"candidate_qc": result.sort_values("design_review_score", ascending=False, na_position="last"), "summary": {"reference_length": len(reference), "candidates": len(result), "valid_candidates": int(result["valid"].fillna(False).sum()), "conserved_positions": list(conserved_positions)}, "scientific_boundary": BOUNDARY + " Sequence heuristics do not establish structure, activity, stability or manufacturability."}


def antibody_developability(data: pd.DataFrame, *, sequence_col: str = "sequence", id_col: str = "antibody_id") -> dict[str, Any]:
    frame = _normalise(data)
    sequence_key = re.sub(r"[^a-z0-9]+", "_", sequence_col.lower()).strip("_")
    id_key = re.sub(r"[^a-z0-9]+", "_", id_col.lower()).strip("_")
    if sequence_key not in frame:
        raise ValueError("Antibody table requires a sequence column.")
    liability_patterns = {
        "deamidation_ng": r"NG",
        "deamidation_ns": r"NS",
        "isomerization_dg": r"DG",
        "oxidation_m": r"M",
        "unpaired_cysteine_proxy": r"C",
        "glycosylation_motif": r"N[^P][ST]",
    }
    rows = []
    for index, record in frame.iterrows():
        sequence = re.sub(r"[^A-Za-z]", "", str(record[sequence_key])).upper()
        antibody_id = str(record.get(id_key, f"antibody_{index+1}")) if id_key in frame else f"antibody_{index+1}"
        if len(sequence) < 50:
            rows.append({"antibody_id": antibody_id, "valid": False, "error": "Sequence is too short for antibody developability review"})
            continue
        counts = {name: len(re.findall(pattern, sequence)) for name, pattern in liability_patterns.items()}
        charge = sum(char in "KR" for char in sequence) - sum(char in "DE" for char in sequence)
        hydrophobic_fraction = sum(char in "AILMFWVY" for char in sequence) / len(sequence)
        cysteine_count = sequence.count("C")
        rows.append({"antibody_id": antibody_id, "valid": True, "length": len(sequence), "net_charge_proxy": charge, "hydrophobic_fraction": hydrophobic_fraction, "cysteine_count": cysteine_count, "odd_cysteine_count": cysteine_count % 2 == 1, **counts, "liability_count": sum(counts.values()) + int(cysteine_count % 2 == 1), "error": None})
    result = pd.DataFrame(rows)
    return {"developability": result.sort_values(["valid", "liability_count"], ascending=[False, True]), "summary": {"antibodies": len(result), "valid": int(result["valid"].fillna(False).sum()), "numbering_status": "IMGT/Chothia numbering adapter not silently approximated"}, "scientific_boundary": BOUNDARY + " Liability motifs are sequence alerts and require structure, formulation and assay confirmation."}


def neoantigen_prioritization(data: pd.DataFrame) -> dict[str, Any]:
    frame = _normalise(data)
    required = ("peptide", "hla", "binding_affinity_nm")
    missing = [column for column in required if column not in frame]
    if missing:
        raise ValueError("Neoantigen table missing: " + ", ".join(missing))
    affinity = _numeric(frame["binding_affinity_nm"])
    expression = _numeric(frame["rna_expression"]) if "rna_expression" in frame else pd.Series(1.0, index=frame.index)
    vaf = _numeric(frame["variant_allele_fraction"]) if "variant_allele_fraction" in frame else pd.Series(0.5, index=frame.index)
    normal = _numeric(frame["normal_tissue_expression"]) if "normal_tissue_expression" in frame else pd.Series(0.0, index=frame.index)
    clonality = _numeric(frame["clonality"]) if "clonality" in frame else vaf
    affinity_score = np.clip(-np.log10(affinity.clip(lower=1e-3) / 50000), 0, 1)
    expression_score = np.clip(np.log1p(expression) / max(float(np.log1p(expression.max())), 1e-12), 0, 1)
    normal_penalty = np.clip(np.log1p(normal) / max(float(np.log1p(max(normal.max(), 1.0))), 1e-12), 0, 1)
    frame["research_priority_score"] = 0.4 * affinity_score + 0.25 * expression_score + 0.2 * np.clip(clonality, 0, 1) + 0.15 * np.clip(vaf, 0, 1) - 0.25 * normal_penalty
    frame["strong_binding_proxy"] = affinity <= 500
    frame["normal_tissue_filter_flag"] = normal > 1
    frame["peptide_unique_within_upload"] = ~frame["peptide"].astype(str).duplicated(keep=False)
    return {"ranking": frame.sort_values("research_priority_score", ascending=False).reset_index(drop=True), "hla_summary": frame.groupby("hla", as_index=False).agg(peptides=("peptide", "size"), strong_binding_candidates=("strong_binding_proxy", "sum"), mean_priority=("research_priority_score", "mean")), "summary": {"candidates": len(frame), "hla_alleles": int(frame["hla"].nunique()), "strong_binding_candidates": int(frame["strong_binding_proxy"].sum()), "normal_expression_flags": int(frame["normal_tissue_filter_flag"].sum())}, "scientific_boundary": BOUNDARY + " Binding, processing and immunogenicity require qualified models and experimental assays."}


def assay_design_and_power(
    *,
    groups: Sequence[str],
    effect_size: float,
    alpha: float = 0.05,
    power: float = 0.8,
    controls_per_plate: int = 8,
    plate_size: int = 96,
    seed: int = 208,
) -> dict[str, Any]:
    if len(groups) < 2:
        raise ValueError("At least two experimental groups are required.")
    if effect_size <= 0 or not 0 < alpha < 1 or not 0 < power < 1:
        raise ValueError("Effect size, alpha and power are invalid.")
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_power = stats.norm.ppf(power)
    n_per_group = int(math.ceil(2 * ((z_alpha + z_power) / effect_size) ** 2))
    samples = [(group, replicate + 1) for group in groups for replicate in range(n_per_group)]
    rng = np.random.default_rng(seed)
    rng.shuffle(samples)
    wells = [f"{row}{column}" for row in "ABCDEFGH" for column in range(1, plate_size // 8 + 1)]
    controls_per_plate = max(2, min(int(controls_per_plate), len(wells) // 2))
    layouts = []
    remaining = list(samples)
    plate = 1
    while remaining:
        usable = wells[controls_per_plate:]
        batch = remaining[: len(usable)]
        remaining = remaining[len(usable):]
        control_wells = wells[:controls_per_plate]
        for index, well in enumerate(control_wells):
            layouts.append({"plate": plate, "well": well, "group": "positive_control" if index % 2 == 0 else "negative_control", "replicate": None})
        for well, (group, replicate) in zip(usable, batch):
            layouts.append({"plate": plate, "well": well, "group": group, "replicate": replicate})
        plate += 1
    return {"plate_layout": pd.DataFrame(layouts), "summary": {"groups": list(groups), "effect_size": effect_size, "alpha": alpha, "power": power, "replicates_per_group": n_per_group, "plates": plate - 1, "controls_per_plate": controls_per_plate}, "scientific_boundary": BOUNDARY + " Power formula assumes a simple standardized two-group comparison and requires design-specific review."}


DISCOVERY_V208_FEATURES: tuple[tuple[str, str, str], ...] = (
    ("compound_standardization", "Compound Preparation & Standardization", "Fragment, charge, tautomer, stereochemistry, duplicate and scaffold review."),
    ("docking_validation", "Docking Pose & Redocking Validation", "Pose ranking, RMSD checks, interaction support and replicate consistency."),
    ("admet_calibration", "ADMET Calibration & Applicability Domain", "Measured/predicted calibration, errors and chemical-space domain checks."),
    ("lead_optimization", "Hit-to-Lead Multi-Objective Optimization", "Pareto fronts, balanced objectives and scaffold diversity."),
    ("protein_design", "Protein Design Constraint & Liability QC", "Identity, conserved residues, charge, hydrophobicity and aggregation windows."),
    ("antibody_developability", "Antibody & Biologics Developability", "Sequence liability, charge, hydrophobicity and cysteine review."),
    ("neoantigen", "Neoantigen Evidence-Aware Prioritization", "HLA binding, expression, clonality, VAF and normal-tissue filters."),
    ("assay_planning", "Assay Design, Controls & Power", "Replicates, randomized plate layouts, control allocation and power assumptions."),
)
