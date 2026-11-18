from __future__ import annotations

import math
import re
from typing import Any, Iterable

import numpy as np
import pandas as pd

from biointel.neuro_cns.data import side_effect_map
from biointel.neuro_cns.schemas import concentration_to_nm
from biointel.neuro_cns.targets import lookup_target, normalize_target


AGGREGATION_FAVOURED = set("VILFWY")
BETA_PROPENSITY = set("VILFTY")
AROMATIC = set("FWY")
CHARGED = set("DEKR")
BREAKERS = set("PG")
VALID_AA = set("ACDEFGHIKLMNPQRSTVWYBXZJUO")


def _clean_sequence(sequence: str) -> str:
    lines = [line.strip() for line in str(sequence or "").splitlines() if line.strip() and not line.startswith(">")]
    cleaned = re.sub(r"\s+", "", "".join(lines)).upper()
    if not cleaned:
        raise ValueError("Protein sequence is required.")
    invalid = sorted(set(cleaned) - VALID_AA)
    if invalid:
        raise ValueError(f"Invalid amino-acid characters: {', '.join(invalid)}")
    return cleaned


def _sequence_entropy(sequence: str) -> float:
    counts = np.asarray([sequence.count(residue) for residue in set(sequence)], dtype=float)
    frequencies = counts / max(counts.sum(), 1.0)
    return float(-np.sum(frequencies * np.log2(frequencies + 1e-12)))


def aggregation_risk(sequence: str, window: int = 9, threshold: float = 0.62) -> dict[str, Any]:
    seq = _clean_sequence(sequence)
    if len(seq) < max(7, window):
        raise ValueError("Sequence is too short for meaningful sliding-window aggregation analysis.")
    window = int(max(7, min(31, window)))
    ambiguous_fraction = sum(residue in set("BXZJUO") for residue in seq) / len(seq)
    entropy = _sequence_entropy(seq)
    local: list[dict[str, Any]] = []
    for start in range(len(seq) - window + 1):
        chunk = seq[start : start + window]
        hydrophobic = sum(residue in AGGREGATION_FAVOURED for residue in chunk) / window
        beta = sum(residue in BETA_PROPENSITY for residue in chunk) / window
        aromatic = sum(residue in AROMATIC for residue in chunk) / window
        charged = sum(residue in CHARGED for residue in chunk) / window
        breakers = sum(residue in BREAKERS for residue in chunk) / window
        local_entropy = _sequence_entropy(chunk) / max(math.log2(20), 1e-9)
        low_complexity_component = 1.0 - min(1.0, local_entropy)
        score = (
            0.38 * hydrophobic
            + 0.24 * beta
            + 0.15 * aromatic
            + 0.12 * (1.0 - charged)
            + 0.07 * (1.0 - breakers)
            + 0.04 * low_complexity_component
        )
        local.append(
            {
                "start_position": start + 1,
                "end_position": start + window,
                "sequence": chunk,
                "local_score": round(float(score), 4),
                "hydrophobic_fraction": round(hydrophobic, 4),
                "beta_propensity_fraction": round(beta, 4),
                "charged_fraction": round(charged, 4),
                "breaker_fraction": round(breakers, 4),
            }
        )
    high = [row for row in local if float(row["local_score"]) >= float(threshold)]
    regions: list[dict[str, Any]] = []
    for row in high:
        if not regions or int(row["start_position"]) > int(regions[-1]["end_position"]) + 1:
            regions.append(dict(row))
        else:
            current = regions[-1]
            current["end_position"] = max(int(current["end_position"]), int(row["end_position"]))
            current["local_score"] = round(max(float(current["local_score"]), float(row["local_score"])), 4)
            current["sequence"] = seq[int(current["start_position"]) - 1 : int(current["end_position"])]
    scores = np.asarray([float(row["local_score"]) for row in local], dtype=float)
    overall = 0.50 * float(np.percentile(scores, 90)) + 0.30 * float(scores.mean()) + 0.20 * float(scores.max())
    uncertainty = min(1.0, 0.20 + 2.5 * ambiguous_fraction + (0.20 if len(seq) < 50 else 0.0))
    return {
        "aggregation_risk_score": round(overall, 4),
        "risk_band": "high" if overall >= 0.67 else "moderate" if overall >= 0.52 else "low",
        "uncertainty_score": round(uncertainty, 4),
        "confidence_band": "low" if uncertainty >= 0.5 else "moderate" if uncertainty >= 0.25 else "higher-screening-confidence",
        "window_size": window,
        "threshold": threshold,
        "sequence_length": len(seq),
        "sequence_entropy_bits": round(entropy, 4),
        "ambiguous_fraction": round(ambiguous_fraction, 6),
        "high_risk_regions": regions,
        "position_track": local,
        "method_features": ["hydrophobicity", "beta propensity", "aromaticity", "charge", "breakers", "local complexity"],
        "scientific_boundary": "Transparent multi-feature heuristic propensity; not a validated TANGO/WALTZ replacement.",
    }


def aggregation_mutation_delta(reference_sequence: str, variant_sequence: str, *, window: int = 9) -> dict[str, Any]:
    reference = _clean_sequence(reference_sequence)
    variant = _clean_sequence(variant_sequence)
    if len(reference) != len(variant):
        raise ValueError("Mutation comparison currently requires reference and variant sequences of equal length.")
    changed = [index + 1 for index, (left, right) in enumerate(zip(reference, variant)) if left != right]
    if not changed:
        raise ValueError("Reference and variant sequences are identical.")
    ref = aggregation_risk(reference, window=window)
    alt = aggregation_risk(variant, window=window)
    return {
        "changed_positions": changed,
        "reference_score": ref["aggregation_risk_score"],
        "variant_score": alt["aggregation_risk_score"],
        "score_delta": round(float(alt["aggregation_risk_score"]) - float(ref["aggregation_risk_score"]), 4),
        "risk_band_change": f"{ref['risk_band']} -> {alt['risk_band']}",
        "reference_high_risk_regions": ref["high_risk_regions"],
        "variant_high_risk_regions": alt["high_risk_regions"],
        "scientific_boundary": ref["scientific_boundary"],
    }


def _binding_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        target = str(row.get("target_id") or row.get("target") or row.get("gene") or "").strip()
        record: dict[str, Any] = {"row": index + 1, "target_id": target, "error": None}
        if not target:
            record.update({"binding_score": np.nan, "error": "missing target"})
            normalized.append(record)
            continue
        raw_score = row.get("binding_score", row.get("score", row.get("probability", row.get("affinity_score"))))
        try:
            if raw_score not in (None, ""):
                score = float(raw_score)
                if not math.isfinite(score):
                    raise ValueError("binding score is not finite")
                if not 0 <= score <= 1:
                    raise ValueError("binding score must be between 0 and 1")
                record["binding_score"] = score
                record["score_basis"] = "supplied_normalized_score"
            else:
                affinity = row.get("kd", row.get("ki", row.get("affinity")))
                unit = str(row.get("unit") or row.get("affinity_unit") or "nM")
                affinity_nm = concentration_to_nm(float(affinity), unit)
                record["binding_score"] = 1.0 / (1.0 + affinity_nm / 100.0)
                record["affinity_nm"] = affinity_nm
                record["score_basis"] = "transparent_affinity_transform"
        except (TypeError, ValueError) as exc:
            record.update({"binding_score": np.nan, "error": str(exc)})
        normalized.append(record)
    return normalized


def _expression_factor(target: dict[str, Any]) -> float:
    values = list(target.get("expression", {}).values()) if target else []
    return float(max(values)) if values else 0.5


def off_target_neurotoxicity(
    rows: Iterable[dict[str, Any]],
    threshold: float = 0.5,
    *,
    primary_target: str | None = None,
    brain_exposure_factor: float = 1.0,
) -> dict[str, Any]:
    if not 0 <= float(threshold) <= 1:
        raise ValueError("Threshold must be between 0 and 1.")
    if not 0 <= float(brain_exposure_factor) <= 5:
        raise ValueError("Brain exposure factor must be between 0 and 5.")
    flags: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    primary_token = normalize_target(primary_target or "")
    for row in _binding_rows(rows):
        if row["error"] or not math.isfinite(float(row["binding_score"])):
            skipped.append(row)
            continue
        matched = lookup_target(row["target_id"])
        if not matched or float(row["binding_score"]) < float(threshold):
            continue
        gene = str(matched.get("gene"))
        if primary_token and normalize_target(gene) == primary_token:
            continue
        categories = list(matched.get("categories", []))
        expression = _expression_factor(matched)
        integrated_risk = min(1.0, float(row["binding_score"]) * min(1.0, float(brain_exposure_factor)) * (0.55 + 0.45 * expression))
        flags.append(
            {
                "source_row": row["row"],
                "target_id": gene,
                "uniprot": matched.get("uniprot"),
                "target_name": matched.get("name"),
                "binding_score": round(float(row["binding_score"]), 4),
                "score_basis": row.get("score_basis"),
                "brain_expression_factor": round(expression, 4),
                "brain_exposure_factor": round(float(brain_exposure_factor), 4),
                "integrated_risk_score": round(integrated_risk, 4),
                "categories": categories,
                "severity": "high" if integrated_risk >= 0.75 else "moderate" if integrated_risk >= 0.45 else "low",
                "recommended_follow_up": ["confirm affinity units", "review free-brain exposure", "run CNS side-effect mapping", "check selectivity panel"],
            }
        )
    flags.sort(key=lambda item: float(item["integrated_risk_score"]), reverse=True)
    return {
        "flag_count": len(flags),
        "flags": flags,
        "skipped_entries": skipped,
        "threshold": threshold,
        "primary_target_excluded": bool(primary_token),
        "primary_target_identifier": primary_target,
        "coverage": {"supplied_rows": len(flags) + len(skipped), "registry_matched_flags": len(flags)},
        "scientific_boundary": "Flags only CNS targets present in the supplied profile and bundled registry; novel off-target discovery is not claimed.",
    }


def cns_side_effects(rows: Iterable[dict[str, Any]], *, brain_exposure_factor: float = 1.0) -> dict[str, Any]:
    if not 0 <= float(brain_exposure_factor) <= 5:
        raise ValueError("Brain exposure factor must be between 0 and 5.")
    mapping = side_effect_map()
    associations = mapping.get("associations", {})
    category_no_risk: dict[str, float] = {}
    contributors: dict[str, list[dict[str, Any]]] = {}
    covered = 0
    total = 0
    excluded: list[str] = []
    invalid: list[dict[str, Any]] = []
    for row in _binding_rows(rows):
        total += 1
        if row.get("error"):
            invalid.append(row)
            continue
        target_token = normalize_target(row["target_id"])
        matched = lookup_target(target_token)
        gene = str(matched.get("gene")) if matched else target_token
        target_map = associations.get(gene)
        score = float(row["binding_score"])
        if not target_map or not math.isfinite(score):
            excluded.append(row["target_id"])
            continue
        covered += 1
        normalized_score = min(1.0, max(0.0, score))
        expression = _expression_factor(matched or {})
        exposure = min(1.0, float(brain_exposure_factor))
        for category, base_weight in target_map.items():
            contribution = min(0.99, normalized_score * float(base_weight) * exposure * (0.60 + 0.40 * expression))
            category_no_risk[category] = category_no_risk.get(category, 1.0) * (1.0 - contribution)
            contributors.setdefault(category, []).append(
                {
                    "target_id": gene,
                    "binding_score": round(normalized_score, 4),
                    "association_weight": round(float(base_weight), 4),
                    "brain_expression_factor": round(expression, 4),
                    "contribution": round(contribution, 4),
                }
            )
    coverage_fraction = covered / total if total else 0.0
    estimates: list[dict[str, Any]] = []
    for category, no_risk in category_no_risk.items():
        likelihood = 1.0 - no_risk
        n_contributors = len(contributors.get(category, []))
        uncertainty = min(0.45, 0.12 + 0.25 * (1.0 - coverage_fraction) + 0.08 / max(math.sqrt(n_contributors), 1.0))
        estimates.append(
            {
                "side_effect_category": category,
                "likelihood": round(likelihood, 4),
                "likelihood_proxy": round(likelihood, 4),
                "uncertainty_interval": [round(max(0.0, likelihood - uncertainty), 4), round(min(1.0, likelihood + uncertainty), 4)],
                "risk_band": "high" if likelihood >= 0.70 else "moderate" if likelihood >= 0.40 else "low",
                "confidence": "moderate" if coverage_fraction >= 0.70 and n_contributors >= 2 else "low",
                "contributing_targets": contributors.get(category, []),
            }
        )
    estimates.sort(key=lambda row: float(row["likelihood_proxy"]), reverse=True)
    return {
        "side_effect_estimates": estimates,
        "coverage": {"covered_targets": covered, "total_targets": total, "coverage_fraction": round(coverage_fraction, 4)},
        "excluded_targets": sorted(set(excluded)),
        "invalid_entries": invalid,
        "brain_exposure_factor": brain_exposure_factor,
        "association_map_version": mapping.get("version"),
        "coverage_warning": "Low coverage: absent associations are not evidence of low risk." if coverage_fraction < 0.5 else None,
        "scientific_boundary": "Exploratory association model; likelihood values are transparent proxies, not calibrated clinical probabilities.",
    }


def off_target_safety_workflow(
    rows: Iterable[dict[str, Any]],
    *,
    primary_target: str | None = None,
    brain_exposure_factor: float = 1.0,
    free_brain_concentration: float | None = None,
    concentration_unit: str = "nM",
    metabolite_rows: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Integrate target coverage, exposure-aware occupancy and side-effect proxies."""
    source_parent = rows.to_dict(orient="records") if isinstance(rows, pd.DataFrame) else list(rows)
    source_metabolites = metabolite_rows.to_dict(orient="records") if isinstance(metabolite_rows, pd.DataFrame) else list(metabolite_rows)
    parent_rows = [dict(row) | {"molecule_role": str(row.get("molecule_role") or "parent")} for row in source_parent]
    metabolite_list = [dict(row) | {"molecule_role": str(row.get("molecule_role") or "active_metabolite")} for row in source_metabolites]
    combined = parent_rows + metabolite_list
    if not combined:
        raise ValueError("At least one target-binding row is required.")
    flags = off_target_neurotoxicity(
        combined,
        threshold=0.5,
        primary_target=primary_target,
        brain_exposure_factor=brain_exposure_factor,
    )
    side_effects = cns_side_effects(combined, brain_exposure_factor=brain_exposure_factor)

    supplied_targets: set[str] = set()
    unmatched: list[dict[str, Any]] = []
    normalized_rows = _binding_rows(combined)
    for source, normalized in zip(combined, normalized_rows):
        matched = lookup_target(normalized.get("target_id", ""))
        if matched:
            supplied_targets.add(str(matched.get("gene")))
        else:
            unmatched.append({
                "target_id": normalized.get("target_id"),
                "molecule_role": source.get("molecule_role", "parent"),
                "reason": normalized.get("error") or "target not present in bundled registry",
            })

    from biointel.neuro_cns.data import targets as registry_targets
    category_to_registry: dict[str, set[str]] = {}
    category_to_supplied: dict[str, set[str]] = {}
    for target in registry_targets():
        gene = str(target.get("gene") or "")
        for category in target.get("categories", []) or []:
            category_to_registry.setdefault(str(category), set()).add(gene)
            if gene in supplied_targets:
                category_to_supplied.setdefault(str(category), set()).add(gene)
    coverage_rows = []
    for category, registry_genes in sorted(category_to_registry.items()):
        supplied = category_to_supplied.get(category, set())
        coverage_rows.append({
            "target_family": category,
            "registry_target_count": len(registry_genes),
            "supplied_target_count": len(supplied),
            "coverage_fraction": round(len(supplied) / max(len(registry_genes), 1), 6),
            "untested_registry_targets": ", ".join(sorted(registry_genes - supplied)),
        })
    family_coverage = pd.DataFrame(coverage_rows)

    occupancy = pd.DataFrame()
    safety_margins = pd.DataFrame()
    if free_brain_concentration is not None:
        from biointel.neuro_cns.chemistry import receptor_occupancy
        affinity_rows = []
        for source in combined:
            if any(key in source for key in ("kd", "ki", "affinity")):
                affinity_rows.append({
                    "target": source.get("target_id") or source.get("target") or source.get("gene"),
                    "kd": source.get("kd", source.get("ki", source.get("affinity"))),
                    "unit": source.get("unit", source.get("affinity_unit", "nM")),
                    "role": "primary" if primary_target and normalize_target(str(source.get("target_id") or source.get("target") or source.get("gene"))) == normalize_target(primary_target) else "off_target",
                })
        if affinity_rows:
            occupancy = receptor_occupancy(
                float(free_brain_concentration), affinity_rows,
                concentration_unit=concentration_unit, default_affinity_unit="nM",
            )
            valid = occupancy.dropna(subset=["occupancy_percent"]).copy()
            if not valid.empty:
                primary_max = valid.loc[valid["role"] == "primary", "occupancy_percent"].max()
                valid["occupancy_margin_vs_primary"] = float(primary_max) - valid["occupancy_percent"] if pd.notna(primary_max) else np.nan
                safety_margins = valid

    warnings: list[str] = []
    if unmatched:
        warnings.append("Some supplied targets are unknown to the bundled registry and remain unassessed, not low-risk.")
    if not family_coverage.empty and float(family_coverage["coverage_fraction"].mean()) < 0.5:
        warnings.append("Target-family panel coverage is limited.")
    if metabolite_list:
        warnings.append("Active-metabolite rows were included exactly as supplied; metabolite exposure was not inferred.")
    return {
        "off_target_flags": flags,
        "side_effect_estimates": side_effects,
        "occupancy": occupancy,
        "safety_margins": safety_margins,
        "target_family_coverage": family_coverage,
        "unmatched_or_unknown_targets": pd.DataFrame(unmatched),
        "parent_rows": len(parent_rows),
        "metabolite_rows": len(metabolite_list),
        "warnings": warnings,
        "scientific_boundary": "Exposure-aware research safety review limited to supplied targets, affinities, metabolites and bundled associations; absence from the panel is unknown risk, not safety evidence.",
    }
