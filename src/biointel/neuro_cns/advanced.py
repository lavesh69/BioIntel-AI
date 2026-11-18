from __future__ import annotations

import math
import re
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from biointel.neuro_cns.chemistry import (
    bbb_permeability,
    cns_adme_transporters,
    cns_drug_likeness,
    receptor_occupancy,
    simulate_brain_exposure,
)
from biointel.neuro_cns.genetics import prioritize_variants
from biointel.neuro_cns.omics import biomarker_discovery
from biointel.neuro_cns.safety import aggregation_mutation_delta, aggregation_risk
from biointel.neuro_cns.schemas import concentration_to_nm, normalize_affinity_rows, table_quality_report
from biointel.neuro_cns.signals import analyze_neural_signals
from biointel.neuro_cns.targets import (
    brain_expression_profile,
    disease_target_table,
    model_organism_cross_reference,
    neuroinflammation_lookup,
    target_tagging,
)


def _clip01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _pareto_mask(values: np.ndarray, maximize: list[bool]) -> np.ndarray:
    """Return non-dominated rows for a dense objective matrix."""
    work = np.asarray(values, dtype=float).copy()
    for column, should_maximize in enumerate(maximize):
        if not should_maximize:
            work[:, column] *= -1.0
    keep = np.ones(len(work), dtype=bool)
    for i in range(len(work)):
        if not keep[i]:
            continue
        dominates_i = np.all(work >= work[i], axis=1) & np.any(work > work[i], axis=1)
        if dominates_i.any():
            keep[i] = False
    return keep


def compound_optimization_board(
    compound_rows: Iterable[dict[str, Any]],
    *,
    reference_compound_id: str | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compare analogue series across transparent CNS screening objectives.

    Optional input columns: potency_nm, measured_stability_fraction,
    measured_efflux_ratio and toxicity_penalty (0-1). Missing experimental
    fields are replaced by explicitly labelled local proxies.
    """
    default_weights = {
        "bbb": 0.20,
        "mpo": 0.20,
        "developability": 0.15,
        "stability": 0.15,
        "low_efflux": 0.10,
        "potency": 0.15,
        "low_toxicity": 0.05,
    }
    selected = default_weights | dict(weights or {})
    total_weight = sum(max(float(value), 0.0) for value in selected.values())
    if total_weight <= 0:
        raise ValueError("At least one positive optimization weight is required.")
    selected = {key: max(float(value), 0.0) / total_weight for key, value in selected.items()}

    rows: list[dict[str, Any]] = []
    for index, source in enumerate(compound_rows):
        compound_id = str(source.get("compound_id") or source.get("id") or f"compound_{index + 1}").strip()
        smiles = str(source.get("smiles") or source.get("compound_structure") or "").strip()
        try:
            bbb = bbb_permeability(smiles, compound_id)
            likeness = cns_drug_likeness(smiles)
            adme = cns_adme_transporters(smiles)
            desc = bbb["descriptors"]
            bbb_score = float(bbb.get("local_probability_proxy", 0.0))
            mpo = float(bbb["cns_mpo_proxy"]["score"]) / 6.0
            developability = float(desc.get("qed", 0.0))
            proxy_stability = float(adme.get("metabolic_stability_proxy", likeness.get("contributing_factors", {}).get("metabolic_stability_proxy", 0.5)))
            proxy_efflux = float(adme.get("pgp_efflux_proxy", likeness.get("contributing_factors", {}).get("pgp_efflux_proxy", 0.5)))
            measured_stability = source.get("measured_stability_fraction")
            measured_efflux = source.get("measured_efflux_ratio")
            stability = _clip01(float(measured_stability)) if measured_stability not in (None, "") else _clip01(proxy_stability)
            if measured_efflux not in (None, ""):
                efflux_value = max(float(measured_efflux), 0.0)
                low_efflux = 1.0 / (1.0 + efflux_value)
                efflux_source = "supplied"
            else:
                low_efflux = 1.0 - _clip01(proxy_efflux)
                efflux_value = proxy_efflux
                efflux_source = "local_proxy"
            potency_nm = source.get("potency_nm")
            if potency_nm in (None, ""):
                potency_score = 0.5
                potency_source = "not_supplied_neutral"
                potency_value = np.nan
            else:
                potency_value = float(potency_nm)
                if not math.isfinite(potency_value) or potency_value <= 0:
                    raise ValueError("potency_nm must be a finite positive value")
                potency_score = _clip01((4.0 - math.log10(potency_value)) / 4.0)
                potency_source = "supplied"
            toxicity_penalty = _clip01(float(source.get("toxicity_penalty", 0.0) or 0.0))
            metrics = {
                "bbb": _clip01(bbb_score),
                "mpo": _clip01(mpo),
                "developability": _clip01(developability),
                "stability": stability,
                "low_efflux": _clip01(low_efflux),
                "potency": potency_score,
                "low_toxicity": 1.0 - toxicity_penalty,
            }
            score = sum(selected[key] * metrics[key] for key in selected)
            rows.append({
                "compound_id": compound_id,
                "smiles": smiles,
                "optimization_score": round(score, 6),
                "bbb_score": round(metrics["bbb"], 6),
                "cns_mpo_normalized": round(metrics["mpo"], 6),
                "qed_developability": round(metrics["developability"], 6),
                "stability_score": round(metrics["stability"], 6),
                "low_efflux_score": round(metrics["low_efflux"], 6),
                "potency_score": round(metrics["potency"], 6),
                "low_toxicity_score": round(metrics["low_toxicity"], 6),
                "potency_nm": potency_value,
                "efflux_value": round(float(efflux_value), 6),
                "stability_source": "supplied" if measured_stability not in (None, "") else "local_proxy",
                "efflux_source": efflux_source,
                "potency_source": potency_source,
                "bbb_classification": bbb["classification"],
                "inside_applicability_domain": bool(bbb["applicability_domain"]["inside"]),
                "warnings": "; ".join([*bbb.get("warnings", []), *likeness.get("warnings", []), *adme.get("warnings", [])]),
                "error": None,
            })
        except Exception as exc:
            rows.append({"compound_id": compound_id, "smiles": smiles, "error": str(exc)})
    frame = pd.DataFrame(rows)
    valid = frame[frame["error"].isna()].copy() if "error" in frame else frame.copy()
    if not valid.empty:
        objective_columns = ["bbb_score", "cns_mpo_normalized", "qed_developability", "stability_score", "low_efflux_score", "potency_score", "low_toxicity_score"]
        pareto = _pareto_mask(valid[objective_columns].to_numpy(float), [True] * len(objective_columns))
        valid["pareto_optimal"] = pareto
        valid["rank"] = valid["optimization_score"].rank(method="dense", ascending=False).astype(int)
        reference_id = reference_compound_id or str(valid.iloc[0]["compound_id"])
        match = valid[valid["compound_id"].astype(str) == str(reference_id)]
        reference = match.iloc[0] if not match.empty else valid.iloc[0]
        for column in objective_columns + ["optimization_score"]:
            valid[f"delta_{column}"] = valid[column] - float(reference[column])
        frame = frame.drop(columns=[column for column in valid.columns if column in frame.columns and column not in {"compound_id", "smiles", "error"}], errors="ignore").merge(valid, on=["compound_id", "smiles", "error"], how="left")
        best = str(valid.sort_values("optimization_score", ascending=False).iloc[0]["compound_id"])
        pareto_ids = valid.loc[valid["pareto_optimal"], "compound_id"].astype(str).tolist()
    else:
        reference_id, best, pareto_ids = None, None, []
    return {
        "comparison": frame.sort_values(["error", "optimization_score"], ascending=[True, False], na_position="last", ignore_index=True),
        "weights": selected,
        "reference_compound_id": reference_id,
        "recommended_screening_candidate": best,
        "pareto_optimal_compounds": pareto_ids,
        "scientific_boundary": "Multi-objective analogue prioritization combines supplied values and transparent proxies; it is not experimental lead optimization.",
    }


def safety_margin_matrix(
    free_brain_concentration: float,
    affinity_rows: Iterable[dict[str, Any]],
    *,
    concentration_unit: str = "nM",
    primary_targets: Iterable[str] = (),
) -> dict[str, Any]:
    source_rows = [dict(row) for row in affinity_rows]
    primary = {str(value).strip().upper() for value in primary_targets if str(value).strip()}
    for row in source_rows:
        target = str(row.get("target") or row.get("target_id") or row.get("gene") or "").strip().upper()
        if target in primary:
            row["role"] = "primary"
        elif not row.get("role"):
            row["role"] = "off_target"
    occupancy = receptor_occupancy(free_brain_concentration, source_rows, concentration_unit=concentration_unit)
    free_nm = concentration_to_nm(free_brain_concentration, concentration_unit)
    rows: list[dict[str, Any]] = []
    for row in occupancy.to_dict(orient="records"):
        target = str(row.get("target", ""))
        affinity = float(row.get("affinity_nm", np.nan))
        occ = float(row.get("occupancy_percent", np.nan))
        tag = target_tagging(target)
        expression = brain_expression_profile(target)
        role = str(row.get("role", "unspecified"))
        margin = affinity / max(free_nm, 1e-12) if math.isfinite(affinity) and affinity > 0 else np.nan
        risk = "unresolved"
        if math.isfinite(occ):
            if role.lower() in {"primary", "on_target", "on-target"}:
                risk = "desired_high_engagement" if occ >= 70 else "desired_low_engagement"
            elif occ >= 70:
                risk = "high_off_target_occupancy"
            elif occ >= 30:
                risk = "moderate_off_target_occupancy"
            else:
                risk = "low_off_target_occupancy"
        rows.append({
            **row,
            "affinity_to_exposure_margin": round(margin, 6) if math.isfinite(margin) else np.nan,
            "cns_relevant": bool(tag.get("is_neuro_relevant")),
            "target_categories": ", ".join(tag.get("categories") or []),
            "expression_available": bool(expression.get("matched")),
            "safety_interpretation": risk,
        })
    frame = pd.DataFrame(rows)
    high = int((frame.get("safety_interpretation", pd.Series(dtype=str)) == "high_off_target_occupancy").sum())
    moderate = int((frame.get("safety_interpretation", pd.Series(dtype=str)) == "moderate_off_target_occupancy").sum())
    return {
        "matrix": frame.sort_values("occupancy_percent", ascending=False, na_position="last", ignore_index=True),
        "free_brain_concentration_nm": round(free_nm, 6),
        "high_off_target_count": high,
        "moderate_off_target_count": moderate,
        "overall_flag": "high_review_priority" if high else "review" if moderate else "no_high_occupancy_flag_in_supplied_panel",
        "scientific_boundary": "Safety margins are exposure/affinity calculations over the supplied panel; absent targets and unknown metabolites remain coverage gaps.",
    }


def _apply_substitution(sequence: str, notation: str) -> tuple[str, dict[str, Any]]:
    cleaned = re.sub(r"\s+", "", str(sequence or "")).upper()
    match = re.fullmatch(r"([A-Z])(\d+)([A-Z])", str(notation or "").strip().upper())
    if not match:
        raise ValueError(f"Unsupported mutation notation {notation!r}; use forms such as A53T.")
    reference, position_text, alternate = match.groups()
    position = int(position_text)
    if position < 1 or position > len(cleaned):
        raise ValueError(f"Mutation position {position} is outside sequence length {len(cleaned)}.")
    observed = cleaned[position - 1]
    if observed != reference:
        raise ValueError(f"Mutation expects {reference} at position {position}, but sequence contains {observed}.")
    variant = cleaned[: position - 1] + alternate + cleaned[position:]
    return variant, {"notation": f"{reference}{position}{alternate}", "position": position, "reference": reference, "alternate": alternate}


def aggregation_mutation_engineering(
    reference_sequence: str,
    mutations: Iterable[str],
    *,
    window: int = 9,
) -> dict[str, Any]:
    baseline = aggregation_risk(reference_sequence, window=window)
    comparison_rows: list[dict[str, Any]] = []
    for notation in mutations:
        try:
            variant, parsed = _apply_substitution(reference_sequence, str(notation))
            delta = aggregation_mutation_delta(reference_sequence, variant, window=window)
            variant_result = aggregation_risk(variant, window=window)
            comparison_rows.append({
                **parsed,
                "reference_risk": baseline["aggregation_risk_score"],
                "variant_risk": variant_result["aggregation_risk_score"],
                "risk_delta": delta["score_delta"],
                "interpretation": "risk_increased" if delta["score_delta"] > 0.03 else "risk_decreased" if delta["score_delta"] < -0.03 else "minimal_change",
                "variant_high_risk_regions": len(variant_result.get("high_risk_regions", [])),
                "error": None,
            })
        except Exception as exc:
            comparison_rows.append({"notation": str(notation), "error": str(exc)})
    high_regions = pd.DataFrame(baseline.get("high_risk_regions", []))
    rescue_rows: list[dict[str, Any]] = []
    if not high_regions.empty:
        hydrophobic = set("VILMFWY")
        for region in high_regions.head(8).to_dict(orient="records"):
            start = int(region.get("start_position", region.get("start", 1)))
            end = int(region.get("end_position", region.get("end", start)))
            segment = re.sub(r"\s+", "", reference_sequence).upper()[start - 1 : end]
            candidates = [start + index for index, residue in enumerate(segment) if residue in hydrophobic]
            for position in candidates[:2]:
                residue = re.sub(r"\s+", "", reference_sequence).upper()[position - 1]
                rescue_rows.append({
                    "candidate_mutation": f"{residue}{position}S",
                    "region_start": start,
                    "region_end": end,
                    "rationale": "Replace one hydrophobic/aromatic residue with a polar residue for in-silico screening only",
                    "requires_structure_and_function_review": True,
                })
    return {
        "baseline": baseline,
        "mutation_comparison": pd.DataFrame(comparison_rows),
        "screening_rescue_candidates": pd.DataFrame(rescue_rows).drop_duplicates("candidate_mutation", ignore_index=True) if rescue_rows else pd.DataFrame(),
        "scientific_boundary": "Mutation deltas and rescue candidates are heuristic design hypotheses; structure, function and experimental aggregation testing are mandatory.",
    }


def experimental_model_selection_assistant(
    target: str,
    *,
    disease: str | None = None,
    desired_context: str = "mechanism",
) -> dict[str, Any]:
    cross = model_organism_cross_reference(target)
    tag = target_tagging(target)
    expression = brain_expression_profile(target)
    inflammation = neuroinflammation_lookup(target)
    available = {str(row.get("organism", "")).lower() for row in cross.get("available_models", [])}
    disease_token = str(disease or "").lower()
    context = str(desired_context or "mechanism").lower()
    candidates = [
        ("mouse", 0.70, "Whole-organism genetics, behaviour and longitudinal disease studies"),
        ("rat", 0.62, "Neurophysiology, behaviour, dosing and surgical procedures"),
        ("zebrafish", 0.52, "Rapid developmental, imaging and medium-throughput screening"),
        ("human iPSC-derived neuron", 0.78, "Patient-genotype and human neuronal cell-autonomous mechanisms"),
        ("brain organoid", 0.66, "Human multicellular development and disease architecture"),
        ("microglia-neuron co-culture", 0.60, "Neuroimmune and non-cell-autonomous mechanisms"),
    ]
    rows: list[dict[str, Any]] = []
    for model, base, rationale in candidates:
        score = base
        reasons: list[str] = [rationale]
        if model in available:
            score += 0.15
            reasons.append("Bundled cross-reference indicates model data availability")
        if model.startswith("human") or model == "brain organoid":
            if "rare" in disease_token or "genetic" in context or "patient" in context:
                score += 0.08
                reasons.append("Human genotype context is especially relevant")
        if "microglia" in model and inflammation.get("is_neuroinflammation_relevant"):
            score += 0.20
            reasons.append("Target is mapped to neuroinflammation context")
        if model in {"mouse", "rat"} and any(token in disease_token for token in ("parkinson", "alzheimer", "epilep", "multiple sclerosis", "als")):
            score += 0.08
            reasons.append("Established whole-organism disease-model class")
        if expression.get("matched"):
            score += 0.04
            reasons.append("Brain expression context is available")
        if not tag.get("is_neuro_relevant"):
            score -= 0.12
            reasons.append("Target is not matched in the local CNS registry")
        rows.append({
            "model": model,
            "suitability_score": round(_clip01(score), 4),
            "target": target,
            "disease": disease,
            "desired_context": desired_context,
            "rationale": "; ".join(reasons),
            "key_limitation": "Species translation and construct validity require protocol-specific expert review" if model in {"mouse", "rat", "zebrafish"} else "In-vitro models do not reproduce full systemic pharmacology or behaviour",
        })
    frame = pd.DataFrame(rows).sort_values("suitability_score", ascending=False, ignore_index=True)
    return {
        "ranked_models": frame,
        "target_context": tag,
        "model_cross_reference": cross,
        "recommended_primary_model": str(frame.iloc[0]["model"]) if not frame.empty else None,
        "recommended_orthogonal_model": str(frame.iloc[1]["model"]) if len(frame) > 1 else None,
        "scientific_boundary": "The assistant ranks experimental-model options from limited metadata; protocol design, ethics, feasibility and construct validity require specialist review.",
    }


def dose_to_effect_simulator(
    pk_parameters: dict[str, Any],
    affinity_rows: Iterable[dict[str, Any]],
    *,
    concentration_unit: str = "nM",
    primary_targets: Iterable[str] = (),
    desired_primary_occupancy_percent: float = 70.0,
    maximum_off_target_occupancy_percent: float = 30.0,
) -> dict[str, Any]:
    pk = simulate_brain_exposure(**dict(pk_parameters))
    curve = pk["curve"].copy()
    normalized = normalize_affinity_rows(list(affinity_rows))
    primary = {str(value).strip().upper() for value in primary_targets if str(value).strip()}
    occupancy_rows: list[dict[str, Any]] = []
    for target_row in normalized:
        affinity = float(target_row.get("affinity_nm", np.nan))
        target = str(target_row.get("target", ""))
        if not math.isfinite(affinity) or affinity <= 0:
            continue
        concentrations = curve["brain_unbound"].to_numpy(float)
        if concentration_unit.lower() != "nm":
            concentrations = np.asarray([concentration_to_nm(value, concentration_unit) for value in concentrations], dtype=float)
        occupancy = 100.0 * concentrations / (concentrations + affinity)
        role = "primary" if target.upper() in primary else "off_target"
        for time, concentration, value in zip(curve["time_hours"], concentrations, occupancy):
            occupancy_rows.append({
                "time_hours": float(time),
                "target": target,
                "role": role,
                "brain_unbound_concentration_nm": float(concentration),
                "occupancy_percent": float(value),
            })
    occupancy_frame = pd.DataFrame(occupancy_rows)
    if occupancy_frame.empty:
        effect_curve = curve[["time_hours", "brain_unbound"]].copy()
        effect_curve["primary_occupancy_max"] = np.nan
        effect_curve["off_target_occupancy_max"] = np.nan
        effect_curve["inside_effect_window"] = False
    else:
        pivot = occupancy_frame.pivot_table(index="time_hours", columns="role", values="occupancy_percent", aggfunc="max")
        effect_curve = curve.merge(pivot, left_on="time_hours", right_index=True, how="left")
        effect_curve = effect_curve.rename(columns={"primary": "primary_occupancy_max", "off_target": "off_target_occupancy_max"})
        if "primary_occupancy_max" not in effect_curve:
            effect_curve["primary_occupancy_max"] = np.nan
        if "off_target_occupancy_max" not in effect_curve:
            effect_curve["off_target_occupancy_max"] = 0.0
        effect_curve["inside_effect_window"] = (
            effect_curve["primary_occupancy_max"].fillna(0.0) >= float(desired_primary_occupancy_percent)
        ) & (
            effect_curve["off_target_occupancy_max"].fillna(0.0) <= float(maximum_off_target_occupancy_percent)
        )
    time_inside = float(np.trapezoid(effect_curve["inside_effect_window"].astype(float), effect_curve["time_hours"])) if len(effect_curve) > 1 else 0.0
    return {
        "pk": pk,
        "target_occupancy_long": occupancy_frame,
        "dose_to_effect_curve": effect_curve,
        "time_inside_effect_window_hours": round(time_inside, 4),
        "effect_window_definition": {
            "minimum_primary_occupancy_percent": desired_primary_occupancy_percent,
            "maximum_off_target_occupancy_percent": maximum_off_target_occupancy_percent,
        },
        "scientific_boundary": "Integrated PK/occupancy scenario simulation from supplied parameters; no efficacy or clinical dose recommendation is implied.",
    }


def rare_neurological_disease_board(
    variant_frame: pd.DataFrame,
    *,
    phenotype_terms: Iterable[str] = (),
    disease: str | None = None,
    inheritance_model: str | None = None,
) -> dict[str, Any]:
    variants = prioritize_variants(variant_frame)
    if variants.empty:
        return {"variant_board": variants, "gene_summary": pd.DataFrame(), "scientific_boundary": "No variants passed parsing/triage."}
    phenotype_tokens = {str(term).strip().lower() for term in phenotype_terms if str(term).strip()}
    rows: list[dict[str, Any]] = []
    for row in variants.to_dict(orient="records"):
        gene = str(row.get("gene", "")).upper()
        disease_links = disease_target_table(target=gene)
        target_context = target_tagging(gene)
        expression = brain_expression_profile(gene)
        models = model_organism_cross_reference(gene)
        phenotype_bonus = 0.0
        reasons = str(row.get("reasons", ""))
        if phenotype_tokens and any(token in reasons.lower() for token in phenotype_tokens):
            phenotype_bonus = 0.10
        disease_bonus = 0.0
        if disease and not disease_links.empty:
            disease_bonus = 0.12 if disease_links["disease_category"].astype(str).str.contains(str(disease), case=False, regex=False).any() else 0.0
        base = float(row.get("priority_score", 0.0))
        board_score = _clip01(base / 10.0 + phenotype_bonus + disease_bonus + (0.05 if target_context.get("is_neuro_relevant") else 0.0))
        rows.append({
            **row,
            "board_score": round(board_score, 6),
            "cns_target_registry_match": bool(target_context.get("is_neuro_relevant")),
            "brain_expression_context_available": bool(expression.get("matched")),
            "model_organism_count": len(models.get("available_models", [])),
            "disease_association_count": int(len(disease_links)),
            "phenotype_terms_supplied": ", ".join(sorted(phenotype_tokens)),
            "disease_context": disease,
        })
    board = pd.DataFrame(rows).sort_values("board_score", ascending=False, ignore_index=True)
    gene_summary = board.groupby("gene", dropna=False).agg(
        variant_count=("gene", "size"),
        top_board_score=("board_score", "max"),
        top_priority_score=("priority_score", "max"),
        pathogenic_label_count=("clinvar_uploaded", lambda values: int(pd.Series(values).astype(str).str.contains("pathogenic", case=False).sum())),
    ).reset_index().sort_values("top_board_score", ascending=False, ignore_index=True)
    return {
        "variant_board": board,
        "gene_summary": gene_summary,
        "phenotype_terms": sorted(phenotype_tokens),
        "disease": disease,
        "scientific_boundary": "Research prioritization board; ACMG classification, segregation confirmation and clinical sign-out are not performed.",
    }


def multiomics_disease_signature_builder(
    frame: pd.DataFrame,
    group_column: str,
    *,
    batch_column: str | None = None,
    maximum_features: int = 10,
    random_state: int = 42,
) -> dict[str, Any]:
    ranking = biomarker_discovery(frame, group_column, batch_column=batch_column, bootstrap_iterations=60, random_state=random_state)
    if ranking.empty:
        raise ValueError("No biomarker features were available for signature construction.")
    selected = ranking.head(max(2, min(int(maximum_features), len(ranking))))["feature"].astype(str).tolist()
    matrix = frame[selected].apply(pd.to_numeric, errors="coerce")
    matrix = matrix.fillna(matrix.median(numeric_only=True)).fillna(0.0)
    labels = frame[group_column].astype(str)
    unique = list(dict.fromkeys(labels.tolist()))
    if len(unique) != 2:
        raise ValueError("Signature builder currently requires exactly two groups.")
    y = (labels == unique[1]).astype(int).to_numpy()
    min_class = int(np.bincount(y).min())
    splits = min(5, min_class)
    if splits < 2:
        raise ValueError("At least two samples per group are required for cross-validation.")
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced", random_state=random_state))
    cv = StratifiedKFold(n_splits=splits, shuffle=True, random_state=random_state)
    probabilities = cross_val_predict(model, matrix, y, cv=cv, method="predict_proba")[:, 1]
    auc = float(roc_auc_score(y, probabilities))
    model.fit(matrix, y)
    coefficients = model.named_steps["logisticregression"].coef_[0]
    coefficient_frame = pd.DataFrame({
        "feature": selected,
        "standardized_coefficient": coefficients,
        "absolute_coefficient": np.abs(coefficients),
    }).sort_values("absolute_coefficient", ascending=False, ignore_index=True)
    sample_scores = pd.DataFrame({
        "sample_index": np.arange(len(frame)),
        "observed_group": labels.to_numpy(),
        "cross_validated_signature_probability": probabilities,
    })
    quality = table_quality_report(frame)
    return {
        "feature_ranking": ranking,
        "selected_signature_features": coefficient_frame,
        "sample_scores": sample_scores,
        "cross_validated_auc": round(auc, 6),
        "group_reference": unique[0],
        "group_positive": unique[1],
        "input_quality": quality.to_dict(),
        "scientific_boundary": "Internally cross-validated exploratory signature; nested selection and independent cohort replication are required before biomarker claims.",
    }


def neurophysiology_review_board(
    frame: pd.DataFrame,
    sampling_rate_hz: float,
    time_column: str | None = None,
    *,
    reviewer_event_rows: Iterable[dict[str, Any]] = (),
    line_noise_hz: float | None = None,
) -> dict[str, Any]:
    analysis = analyze_neural_signals(frame, sampling_rate_hz, time_column, line_noise_hz=line_noise_hz)
    candidates = analysis["candidate_events"].copy()
    reviewer = pd.DataFrame(list(reviewer_event_rows))
    if not reviewer.empty and {"channel", "time_seconds"}.issubset(reviewer.columns) and not candidates.empty:
        reviewer["time_seconds"] = pd.to_numeric(reviewer["time_seconds"], errors="coerce")
        decisions: list[dict[str, Any]] = []
        for row in candidates.to_dict(orient="records"):
            matches = reviewer[
                (reviewer["channel"].astype(str) == str(row.get("channel")))
                & ((reviewer["time_seconds"] - float(row.get("time_seconds", 0.0))).abs() <= 0.25)
            ]
            decision = str(matches.iloc[0].get("decision", "unreviewed")) if not matches.empty else "unreviewed"
            note = str(matches.iloc[0].get("note", "")) if not matches.empty else ""
            decisions.append({**row, "review_decision": decision, "review_note": note})
        reviewed_events = pd.DataFrame(decisions)
    else:
        reviewed_events = candidates.copy()
        if not reviewed_events.empty:
            reviewed_events["review_decision"] = "unreviewed"
            reviewed_events["review_note"] = ""
    channel_summary = analysis["channel_summary"].copy()
    if not channel_summary.empty:
        channel_summary["review_priority"] = np.where(
            channel_summary["artifact_flags"].astype(str) != "none", "artifact_review",
            np.where(channel_summary["candidate_event_count"] > 0, "event_review", "routine"),
        )
    return {
        **analysis,
        "channel_review_board": channel_summary,
        "reviewed_events": reviewed_events,
        "review_completion_fraction": round(float((reviewed_events.get("review_decision", pd.Series(dtype=str)) != "unreviewed").mean()), 6) if not reviewed_events.empty else 1.0,
        "scientific_boundary": "Synchronized analytics and annotation board for research review; event labels are not diagnostic determinations.",
    }


def brain_digital_twin_viewer(
    volume: np.ndarray,
    *,
    threshold: float | None = None,
    region_labels: dict[int, str] | None = None,
    overlay_points: Iterable[dict[str, Any]] = (),
    maximum_surface_points: int = 20_000,
) -> dict[str, Any]:
    values = np.asarray(volume, dtype=float)
    if values.ndim not in {2, 3}:
        raise ValueError("Digital-twin viewer requires a 2D or 3D numeric array.")
    finite = np.isfinite(values)
    if not finite.any():
        raise ValueError("Volume contains no finite values.")
    observed = values[finite]
    cut = float(threshold) if threshold is not None else float(np.nanpercentile(observed, 90))
    mask = finite & (values >= cut)
    coordinates = np.argwhere(mask)
    intensities = values[mask]
    if len(coordinates) > maximum_surface_points:
        rng = np.random.default_rng(42)
        selected = np.sort(rng.choice(len(coordinates), size=int(maximum_surface_points), replace=False))
        coordinates = coordinates[selected]
        intensities = intensities[selected]
    if values.ndim == 2 and len(coordinates):
        coordinates = np.column_stack([coordinates, np.zeros(len(coordinates), dtype=int)])
    surface = pd.DataFrame({
        "x": coordinates[:, 0] if len(coordinates) else [],
        "y": coordinates[:, 1] if len(coordinates) else [],
        "z": coordinates[:, 2] if len(coordinates) else [],
        "intensity": intensities if len(coordinates) else [],
    })
    overlays = pd.DataFrame(list(overlay_points))
    region_rows: list[dict[str, Any]] = []
    if region_labels:
        integer_volume = np.asarray(values, dtype=int)
        for label, name in region_labels.items():
            region_mask = integer_volume == int(label)
            if region_mask.any():
                region_rows.append({
                    "label": int(label),
                    "region": str(name),
                    "voxel_count": int(region_mask.sum()),
                    "mean_value": round(float(np.nanmean(values[region_mask])), 6),
                })
    return {
        "shape": list(values.shape),
        "threshold": cut,
        "surface_points": surface,
        "overlay_points": overlays,
        "region_summary": pd.DataFrame(region_rows),
        "surface_point_count": int(len(surface)),
        "downsampled": int(mask.sum()) > len(surface),
        "scientific_boundary": "Exploratory 3D array visualization; anatomical orientation, registration and atlas validity must be supplied and qualified separately.",
    }


ADVANCED_FEATURES = (
    (1, "CNS Compound Optimization Board", "compound_optimization_board"),
    (2, "CNS Safety Margin Matrix", "safety_margin_matrix"),
    (3, "Aggregation Mutation Engineering Lab", "aggregation_mutation_engineering"),
    (4, "Experimental Model Selection Assistant", "experimental_model_selection_assistant"),
    (5, "Dose-to-Brain-to-Effect Simulator", "dose_to_effect_simulator"),
    (6, "Rare Neurological Disease Board", "rare_neurological_disease_board"),
    (7, "Neuro Multi-Omics Disease Signature Builder", "multiomics_disease_signature_builder"),
    (8, "Digital Neurophysiology Review Board", "neurophysiology_review_board"),
    (9, "3D Brain Digital Twin Viewer", "brain_digital_twin_viewer"),
)
