from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from biointel.neuro_cns.data import target_index, target_registry, targets
from biointel.neuro_cns.schemas import table_quality_report


VALID_AA = set("ACDEFGHIKLMNPQRSTVWYBXZJUO")
HYDROPHOBIC = set("AILMFWVY")


def normalize_target(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).upper()


def lookup_target(value: str) -> dict[str, Any] | None:
    token = normalize_target(value)
    if not token:
        return None
    direct = target_index().get(token)
    if direct:
        return dict(direct)
    # Allow a gene symbol inside labels such as "DRD2 | dopamine receptor".
    first = re.split(r"[^A-Z0-9-]+", token)[0]
    candidate = target_index().get(first) if first else None
    return dict(candidate) if candidate else None


def target_tagging(identifier: str | None = None, sequence: str | None = None) -> dict[str, Any]:
    if not identifier and not sequence:
        raise ValueError("Provide a target identifier or protein sequence.")
    registry = target_registry()
    matched = lookup_target(identifier or "") if identifier else None
    sequence_evidence: dict[str, Any] | None = None
    if matched is None and sequence:
        ion = classify_ion_channel(sequence)
        gpcr = classify_gpcr(sequence)
        categories: list[str] = []
        if ion["is_ion_channel"]:
            categories.extend(["ion_channel", str(ion.get("subtype") or "unclassified_channel")])
        if gpcr["is_neuro_gpcr"]:
            categories.extend(["gpcr", str(gpcr.get("receptor_family") or "unclassified_gpcr")])
        if categories:
            sequence_evidence = {"ion_channel": ion, "gpcr": gpcr}
            confidence = max(float(ion.get("confidence_score", 0.0)), float(gpcr.get("confidence_score", 0.0)))
            return {
                "is_neuro_relevant": True,
                "matched_by": "sequence_architecture",
                "target": None,
                "categories": sorted(set(categories)),
                "evidence_score": round(confidence, 3),
                "evidence_level": "medium" if confidence >= 0.58 else "low",
                "reference_list_version": registry.get("version"),
                "sequence_evidence": sequence_evidence,
                "coverage_boundary": registry.get("source_boundary"),
            }
    categories = list(matched.get("categories", [])) if matched else []
    diseases = list(matched.get("diseases", [])) if matched else []
    pathways = list(matched.get("pathways", [])) if matched else []
    evidence_score = 0.95 if matched and matched.get("uniprot") else 0.80 if matched else 0.0
    return {
        "is_neuro_relevant": matched is not None,
        "matched_by": "curated_identifier" if matched else "no_match",
        "target": matched,
        "categories": categories,
        "pathways": pathways,
        "disease_association_count": len(diseases),
        "evidence_score": evidence_score,
        "evidence_level": "high" if evidence_score >= 0.9 else "none",
        "reference_list_version": registry.get("version"),
        "sequence_evidence": sequence_evidence,
        "coverage_boundary": registry.get("source_boundary"),
        "recommended_next_modules": ["neurotransmitter_pathway", "cns_disease_targets", "brain_expression_atlas", "model_organism"] if matched else ["ion_channel_classifier", "gpcr_classifier"],
    }


def pathway_mapping(identifier: str) -> dict[str, Any]:
    matched = lookup_target(identifier)
    pathways = list(matched.get("pathways", [])) if matched else []
    diseases = [item[0] for item in matched.get("diseases", [])] if matched else []
    categories = list(matched.get("categories", [])) if matched else []
    return {
        "target_identifier": identifier,
        "target": matched,
        "pathways": pathways or ["unmapped"],
        "target_categories": categories,
        "disease_context": diseases,
        "mapping_confidence": "high" if pathways and matched else "unmapped",
        "reference_table_version": target_registry().get("version"),
        "scientific_boundary": "Unmapped means absent from the bundled snapshot, not proven biological absence.",
    }


def sequence_quality(sequence: str) -> dict[str, Any]:
    seq = _clean_sequence(sequence)
    ambiguous = sum(residue in set("BXZJUO") for residue in seq)
    composition = {residue: seq.count(residue) / len(seq) for residue in sorted(set(seq))}
    entropy = -sum(value * np.log2(value) for value in composition.values() if value > 0)
    low_complexity = max(composition.values()) >= 0.45
    return {
        "length": len(seq),
        "ambiguous_residues": ambiguous,
        "ambiguous_fraction": round(ambiguous / len(seq), 6),
        "composition_entropy_bits": round(float(entropy), 4),
        "low_complexity_warning": bool(low_complexity),
        "quality_band": "low" if ambiguous / len(seq) > 0.05 or low_complexity else "adequate",
    }


def _clean_sequence(sequence: str) -> str:
    lines = [line.strip() for line in str(sequence or "").splitlines() if line.strip() and not line.startswith(">")]
    cleaned = re.sub(r"\s+", "", "".join(lines)).upper()
    if not cleaned:
        raise ValueError("Protein sequence is required.")
    invalid = sorted(set(cleaned) - VALID_AA)
    if invalid:
        raise ValueError(f"Invalid amino-acid characters: {', '.join(invalid)}")
    return cleaned


def _hydrophobic_segments(sequence: str, window: int = 19, threshold: float = 0.68) -> list[tuple[int, int, float]]:
    seq = _clean_sequence(sequence)
    if len(seq) < window:
        return []
    raw: list[tuple[int, int, float]] = []
    for start in range(len(seq) - window + 1):
        chunk = seq[start : start + window]
        fraction = sum(residue in HYDROPHOBIC for residue in chunk) / window
        if fraction >= threshold:
            raw.append((start + 1, start + window, fraction))
    if not raw:
        return []
    merged: list[tuple[int, int, float]] = [raw[0]]
    for start, end, score in raw[1:]:
        previous_start, previous_end, previous_score = merged[-1]
        if start <= previous_end + 4:
            merged[-1] = (previous_start, max(previous_end, end), max(previous_score, score))
        else:
            merged.append((start, end, score))
    return merged


def classify_ion_channel(sequence: str) -> dict[str, Any]:
    seq = _clean_sequence(sequence)
    segments = _hydrophobic_segments(seq)
    evidence: list[str] = []
    subtype: str | None = None
    confidence_score = 0.0

    potassium_motifs = ["TVGYG", "TXXTXGYG", "GYG"]
    if "TVGYG" in seq or ("GYG" in seq and len(segments) >= 2):
        subtype = "potassium_channel"
        evidence.append("potassium selectivity-filter-like GYG motif")
        confidence_score += 0.55
    if any(motif in seq for motif in ("DEKA", "EEEE")) and len(segments) >= 4:
        subtype = "voltage_gated_sodium_or_calcium"
        evidence.append("multi-pass architecture with sodium/calcium selectivity signature")
        confidence_score += 0.60
    if re.search(r"C.{8,18}C", seq) and len(segments) >= 3 and len(seq) < 800:
        if subtype is None:
            subtype = "ligand_gated_channel"
        evidence.append("cysteine-loop-like motif and multi-pass architecture")
        confidence_score += 0.45
    if len(segments) >= 6:
        evidence.append(f"{len(segments)} hydrophobic transmembrane-like segments")
        confidence_score += 0.30
    elif len(segments) >= 2:
        evidence.append(f"{len(segments)} hydrophobic segments")
        confidence_score += 0.12

    is_channel = bool(subtype and confidence_score >= 0.45)
    if len(seq) < 120:
        confidence_score *= 0.45
        evidence.append("sequence is short/truncated for definitive topology classification")
    confidence = "high" if confidence_score >= 0.75 else "medium" if confidence_score >= 0.5 else "low"
    return {
        "is_ion_channel": is_channel,
        "subtype": subtype if is_channel else None,
        "confidence": confidence,
        "confidence_score": round(min(confidence_score, 0.99), 3),
        "sequence_length": len(seq),
        "sequence_quality": sequence_quality(seq),
        "topology_summary": {"segment_count": len(segments), "complete_sequence_likely": len(seq) >= 120},
        "transmembrane_like_segments": [
            {"start": start, "end": end, "hydrophobic_fraction": round(score, 3)}
            for start, end, score in segments
        ],
        "motif_evidence": evidence,
        "scientific_boundary": "Heuristic sequence triage; confirm with approved domain/reference tools and experiment.",
    }


def classify_gpcr(sequence: str) -> dict[str, Any]:
    seq = _clean_sequence(sequence)
    segments = _hydrophobic_segments(seq, window=19, threshold=0.66)
    evidence: list[str] = []
    score = 0.0
    family: str | None = None

    if 6 <= len(segments) <= 10:
        evidence.append(f"seven-transmembrane-compatible architecture ({len(segments)} segments)")
        score += 0.45
    if re.search(r"D[RK]Y", seq):
        evidence.append("class-A-like DRY motif")
        score += 0.25
    if re.search(r"NP..Y", seq):
        evidence.append("class-A-like NPxxY motif")
        score += 0.20
    if "CWXP" in seq or re.search(r"C.W.P", seq):
        evidence.append("class-A-like CWxP motif")
        score += 0.10

    if score >= 0.60:
        family = "aminergic_neuro_gpcr"
    if len(seq) >= 700 and 6 <= len(segments) <= 10 and ("PKT" in seq or "HSDC" in seq):
        family = "class_c_metabotropic_or_gabab_like"
        score = max(score, 0.62)
        evidence.append("long N-terminal/class-C-compatible architecture")
    if "DRY" in seq and "NPVIY" in seq:
        family = "dopamine_or_serotonin_receptor_like"
        score = max(score, 0.78)

    is_gpcr = score >= 0.58
    confidence = "high" if score >= 0.78 else "medium" if score >= 0.58 else "low"
    return {
        "is_neuro_gpcr": is_gpcr,
        "receptor_family": family if is_gpcr else None,
        "confidence": confidence,
        "confidence_score": round(min(score, 0.99), 3),
        "sequence_length": len(seq),
        "sequence_quality": sequence_quality(seq),
        "topology_summary": {"segment_count": len(segments), "seven_tm_compatible": 6 <= len(segments) <= 10},
        "transmembrane_like_segments": [
            {"start": start, "end": end, "hydrophobic_fraction": round(value, 3)}
            for start, end, value in segments
        ],
        "motif_evidence": evidence,
        "scientific_boundary": "Sequence-pattern triage; confirm family with approved GPCR reference alignment.",
    }


def disease_target_table(disease: str | None = None, target: str | None = None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    disease_token = str(disease or "").strip().lower()
    target_token = normalize_target(target or "")
    confidence_score = {"high": 0.9, "medium": 0.65, "low": 0.35}
    for entry in targets():
        accepted_tokens = {normalize_target(entry.get("gene", "")), normalize_target(entry.get("uniprot", "")), normalize_target(entry.get("name", ""))}
        accepted_tokens.update(normalize_target(value) for value in entry.get("aliases", []))
        if target_token and target_token not in accepted_tokens:
            continue
        for association in entry.get("diseases", []):
            if isinstance(association, dict):
                disease_name = str(association.get("disease", ""))
                confidence = str(association.get("confidence", "medium"))
                evidence_type = str(association.get("evidence_type", "curated reference"))
                source = association.get("source")
            else:
                disease_name, confidence = association[:2]
                evidence_type = "bundled curated reference"
                source = None
            if disease_token and disease_token not in str(disease_name).lower():
                continue
            rows.append({
                "target_id": entry.get("gene"),
                "uniprot": entry.get("uniprot"),
                "target_name": entry.get("name"),
                "disease_category": disease_name,
                "confidence_level": confidence,
                "evidence_score": confidence_score.get(str(confidence).lower(), 0.5),
                "evidence_type": evidence_type,
                "source_reference": source,
                "target_categories": ", ".join(entry.get("categories", [])),
                "registry_version": target_registry().get("version"),
            })
    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values(["evidence_score", "target_id"], ascending=[False, True], ignore_index=True)
    return result


def neuroinflammation_lookup(identifier: str) -> dict[str, Any]:
    matched = lookup_target(identifier)
    context = matched.get("inflammation") if matched else None
    categories = set(matched.get("categories", [])) if matched else set()
    relevant = bool(context or "neuroinflammation" in categories or "microglia" in categories)
    mechanisms: list[str] = []
    text = f"{context or ''} {' '.join(categories)}".lower()
    for token, label in (("complement", "complement cascade"), ("inflammasome", "inflammasome"), ("microgl", "microglial state"), ("cytokine", "cytokine signaling"), ("tlr", "innate immune receptor"), ("anti-inflammatory", "anti-inflammatory signaling")):
        if token in text:
            mechanisms.append(label)
    return {
        "target_identifier": identifier,
        "is_neuroinflammation_relevant": relevant,
        "pathway_context": context,
        "mechanism_tags": mechanisms,
        "evidence_level": "medium" if relevant else "not_in_snapshot",
        "target": matched,
        "reference_list_version": target_registry().get("version"),
        "scientific_boundary": "Versioned curated snapshot requiring periodic evidence review.",
    }


def model_organism_cross_reference(identifier: str) -> dict[str, Any]:
    matched = lookup_target(identifier)
    organisms = list(matched.get("models", [])) if matched else []
    source_by_organism = {
        "mouse": {"provider": "MGI-compatible binding", "orthology_status": "binding_required"},
        "rat": {"provider": "RGD-compatible binding", "orthology_status": "binding_required"},
        "zebrafish": {"provider": "ZFIN-compatible binding", "orthology_status": "binding_required"},
    }
    details = matched.get("model_details", {}) if matched else {}
    available = []
    for organism in organisms:
        base = source_by_organism.get(organism, {"provider": "approved source required", "orthology_status": "unknown"})
        available.append({
            "organism": organism,
            "data_source_reference": base["provider"],
            "orthology_status": details.get(organism, {}).get("orthology_status", base["orthology_status"]),
            "phenotype_summary": details.get(organism, {}).get("phenotype_summary"),
            "sequence_identity_percent": details.get(organism, {}).get("sequence_identity_percent"),
            "model_suitability": details.get(organism, {}).get("model_suitability", "not_assessed"),
        })
    return {
        "target_identifier": identifier,
        "target": matched,
        "available_models": available,
        "coverage": {"organisms_listed": len(available), "approved_orthology_binding_present": any(item["orthology_status"] != "binding_required" for item in available)},
        "scientific_boundary": "Model availability is metadata and does not establish experimental suitability.",
    }


def brain_expression_profile(identifier: str) -> dict[str, Any]:
    matched = lookup_target(identifier)
    if not matched:
        return {
            "target_identifier": identifier,
            "found": False,
            "regional_expression": {},
            "cell_type_expression": {},
            "registry_version": target_registry().get("version"),
            "coverage_warning": "Not found in bundled snapshot; absence is not biological evidence.",
        }
    regional = {str(key): float(value) for key, value in dict(matched.get("expression", {})).items()}
    cells = {str(key): float(value) for key, value in dict(matched.get("cell_types", {})).items()}
    top_region = max(regional, key=regional.get) if regional else None
    top_cell = max(cells, key=cells.get) if cells else None
    regional_values = np.asarray(list(regional.values()), dtype=float) if regional else np.asarray([])
    cell_values = np.asarray(list(cells.values()), dtype=float) if cells else np.asarray([])
    region_specificity = float((regional_values.max() - np.median(regional_values)) / max(regional_values.max(), 1e-9)) if regional_values.size else None
    cell_specificity = float((cell_values.max() - np.median(cell_values)) / max(cell_values.max(), 1e-9)) if cell_values.size else None
    return {
        "target_identifier": identifier,
        "found": True,
        "target": {key: matched.get(key) for key in ("gene", "uniprot", "name")},
        "regional_expression": regional,
        "cell_type_expression": cells,
        "top_region": top_region,
        "top_cell_type": top_cell,
        "regional_specificity_index": round(region_specificity, 4) if region_specificity is not None else None,
        "cell_type_specificity_index": round(cell_specificity, 4) if cell_specificity is not None else None,
        "expression_source_status": matched.get("expression_source_status", "bundled_demo_summary"),
        "registry_version": target_registry().get("version"),
        "scientific_boundary": "Bundled normalized reference/demo profile, not raw expression quantification.",
    }



def _resolve_expression_column(frame: pd.DataFrame, explicit: str | None, aliases: tuple[str, ...]) -> str | None:
    if explicit and explicit in frame.columns:
        return explicit
    lower = {str(column).strip().lower(): str(column) for column in frame.columns}
    for alias in aliases:
        if alias.lower() in lower:
            return lower[alias.lower()]
    return None


def _expression_specificity(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce").dropna().clip(lower=0)
    if numeric.empty:
        return None
    maximum = float(numeric.max())
    if maximum <= 0 or len(numeric) == 1:
        return 0.0
    tau = float(((1.0 - numeric / maximum).sum()) / (len(numeric) - 1))
    return round(max(0.0, min(1.0, tau)), 6)


def expression_atlas_analysis(
    identifier: str,
    atlas_frame: pd.DataFrame | None = None,
    *,
    gene_column: str | None = None,
    expression_column: str | None = None,
    region_column: str | None = None,
    cell_type_column: str | None = None,
    disease_column: str | None = None,
    developmental_stage_column: str | None = None,
    sample_type_column: str | None = None,
    disease_filter: str | None = None,
    developmental_stage_filter: str | None = None,
    sample_type_filter: str | None = None,
    source_name: str | None = None,
    source_version: str | None = None,
) -> dict[str, Any]:
    """Build a provenance-aware regional/cell-type expression review.

    Uploaded values are summarized exactly as supplied. The function does not
    mix external rows with the bundled demonstration snapshot and never treats
    absence from a source as biological absence.
    """
    token = str(identifier or "").strip()
    if not token:
        raise ValueError("Target identifier is required.")
    if atlas_frame is None:
        profile = brain_expression_profile(token)
        if not profile.get("found"):
            return {
                **profile,
                "regional_summary": pd.DataFrame(columns=["region", "mean_expression", "median_expression", "sample_count"]),
                "cell_type_summary": pd.DataFrame(columns=["cell_type", "mean_expression", "median_expression", "sample_count"]),
                "disease_summary": pd.DataFrame(),
                "developmental_summary": pd.DataFrame(),
                "sample_records": pd.DataFrame(),
                "provenance": {
                    "source_kind": "bundled_demo_reference",
                    "source_name": "BioIntel target registry",
                    "source_version": target_registry().get("version"),
                    "release_eligible": False,
                },
            }
        regional = pd.DataFrame([
            {"region": key, "mean_expression": value, "median_expression": value, "sample_count": 1}
            for key, value in profile["regional_expression"].items()
        ]).sort_values("mean_expression", ascending=False, ignore_index=True)
        cells = pd.DataFrame([
            {"cell_type": key, "mean_expression": value, "median_expression": value, "sample_count": 1}
            for key, value in profile["cell_type_expression"].items()
        ]).sort_values("mean_expression", ascending=False, ignore_index=True)
        return {
            **profile,
            "regional_summary": regional,
            "cell_type_summary": cells,
            "disease_summary": pd.DataFrame(),
            "developmental_summary": pd.DataFrame(),
            "sample_records": pd.DataFrame(),
            "regional_tau_specificity": _expression_specificity(regional["mean_expression"]) if not regional.empty else None,
            "cell_type_tau_specificity": _expression_specificity(cells["mean_expression"]) if not cells.empty else None,
            "provenance": {
                "source_kind": "bundled_demo_reference",
                "source_name": "BioIntel target registry",
                "source_version": target_registry().get("version"),
                "release_eligible": False,
            },
        }

    if atlas_frame.empty:
        raise ValueError("Uploaded expression atlas table is empty.")
    frame = atlas_frame.copy()
    gene_col = _resolve_expression_column(frame, gene_column, ("gene", "symbol", "gene_symbol", "target", "feature"))
    value_col = _resolve_expression_column(frame, expression_column, ("expression", "normalized_expression", "value", "tpm", "counts", "abundance"))
    region_col = _resolve_expression_column(frame, region_column, ("region", "brain_region", "anatomical_region", "tissue"))
    cell_col = _resolve_expression_column(frame, cell_type_column, ("cell_type", "celltype", "cell", "cluster", "cell_class"))
    disease_col = _resolve_expression_column(frame, disease_column, ("disease", "condition", "diagnosis", "phenotype"))
    stage_col = _resolve_expression_column(frame, developmental_stage_column, ("developmental_stage", "stage", "age_group", "development"))
    sample_col = _resolve_expression_column(frame, sample_type_column, ("sample_type", "sample", "assay_type", "modality"))
    if gene_col is None or value_col is None:
        raise ValueError("Expression table requires gene/target and numeric expression columns.")
    if region_col is None and cell_col is None:
        raise ValueError("Expression table requires at least a brain-region or cell-type column.")
    frame[value_col] = pd.to_numeric(frame[value_col], errors="coerce")
    frame = frame.loc[frame[value_col].notna()].copy()
    matched = frame.loc[frame[gene_col].astype(str).str.strip().str.upper() == token.upper()].copy()
    filters_applied: dict[str, str] = {}
    for column, requested, label in (
        (disease_col, disease_filter, "disease"),
        (stage_col, developmental_stage_filter, "developmental_stage"),
        (sample_col, sample_type_filter, "sample_type"),
    ):
        if column and requested and str(requested).strip().lower() not in {"all", "<all>"}:
            requested_text = str(requested).strip()
            matched = matched.loc[matched[column].astype(str).str.casefold() == requested_text.casefold()].copy()
            filters_applied[label] = requested_text
    if matched.empty:
        return {
            "target_identifier": token,
            "found": False,
            "regional_summary": pd.DataFrame(),
            "cell_type_summary": pd.DataFrame(),
            "disease_summary": pd.DataFrame(),
            "developmental_summary": pd.DataFrame(),
            "sample_records": matched,
            "filters_applied": filters_applied,
            "coverage_warning": "No matching rows in the uploaded source/filter combination; this is not evidence of absent expression.",
            "provenance": {
                "source_kind": "user_supplied",
                "source_name": source_name or "uploaded expression table",
                "source_version": source_version or "unspecified",
                "release_eligible": False,
            },
        }

    def summarize(column: str | None, output_name: str) -> pd.DataFrame:
        if not column:
            return pd.DataFrame()
        summary = (
            matched.groupby(column, dropna=False)[value_col]
            .agg(["mean", "median", "std", "count", "min", "max"])
            .reset_index()
            .rename(columns={
                column: output_name,
                "mean": "mean_expression",
                "median": "median_expression",
                "std": "standard_deviation",
                "count": "sample_count",
                "min": "minimum_expression",
                "max": "maximum_expression",
            })
        )
        summary[output_name] = summary[output_name].fillna("Unspecified").astype(str)
        return summary.sort_values(["mean_expression", "sample_count"], ascending=[False, False], ignore_index=True)

    regional = summarize(region_col, "region")
    cells = summarize(cell_col, "cell_type")
    diseases = summarize(disease_col, "disease")
    stages = summarize(stage_col, "developmental_stage")
    quality = table_quality_report(atlas_frame)
    top_region = str(regional.iloc[0]["region"]) if not regional.empty else None
    top_cell = str(cells.iloc[0]["cell_type"]) if not cells.empty else None
    return {
        "target_identifier": token,
        "found": True,
        "regional_summary": regional,
        "cell_type_summary": cells,
        "disease_summary": diseases,
        "developmental_summary": stages,
        "sample_records": matched.reset_index(drop=True),
        "top_region": top_region,
        "top_cell_type": top_cell,
        "regional_tau_specificity": _expression_specificity(regional["mean_expression"]) if not regional.empty else None,
        "cell_type_tau_specificity": _expression_specificity(cells["mean_expression"]) if not cells.empty else None,
        "matched_rows": int(len(matched)),
        "unique_regions": int(matched[region_col].nunique(dropna=True)) if region_col else 0,
        "unique_cell_types": int(matched[cell_col].nunique(dropna=True)) if cell_col else 0,
        "filters_applied": filters_applied,
        "column_mapping": {
            "gene": gene_col,
            "expression": value_col,
            "region": region_col,
            "cell_type": cell_col,
            "disease": disease_col,
            "developmental_stage": stage_col,
            "sample_type": sample_col,
        },
        "provenance": {
            "source_kind": "user_supplied",
            "source_name": source_name or "uploaded expression table",
            "source_version": source_version or "unspecified",
            "input_fingerprint_sha256": quality.fingerprint_sha256,
            "release_eligible": False,
        },
        "scientific_boundary": "Uploaded/reference expression summary for research review; source qualification, normalization comparability and independent biological validation remain required.",
    }

def target_registry_frame() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for entry in targets():
        rows.append(
            {
                "gene": entry.get("gene"),
                "uniprot": entry.get("uniprot"),
                "name": entry.get("name"),
                "categories": ", ".join(entry.get("categories", [])),
                "pathways": ", ".join(entry.get("pathways", [])),
                "disease_count": len(entry.get("diseases", [])),
                "model_organisms": ", ".join(entry.get("models", [])),
                "neuroinflammation_context": entry.get("inflammation"),
                "aliases": ", ".join(entry.get("aliases", [])),
                "expression_source_status": entry.get("expression_source_status", "bundled_demo_summary"),
            }
        )
    return pd.DataFrame(rows)


def sequence_topology_track(sequence: str, *, protein_class: str = "auto") -> dict[str, Any]:
    """Build an auditable topology/motif track for GPCR and ion-channel review."""
    seq = _clean_sequence(sequence)
    segments = _hydrophobic_segments(seq)
    class_token = str(protein_class or "auto").strip().lower()
    gpcr = classify_gpcr(seq)
    ion = classify_ion_channel(seq)
    if class_token == "auto":
        class_token = "gpcr" if float(gpcr.get("confidence_score", 0.0)) >= float(ion.get("confidence_score", 0.0)) else "ion_channel"
    motifs: list[dict[str, Any]] = []
    motif_patterns = {
        "gpcr": {"DRY-like": r"D.RY", "NPxxY-like": r"NP..Y", "CWxP-like": r"CW.P"},
        "ion_channel": {"selectivity-filter-like": r"[TVI]G[DEK][WYF]", "p-loop-like": r"[ST]..[DE].{2}[WYF]"},
    }
    for label, pattern in motif_patterns.get(class_token, {}).items():
        for match in re.finditer(pattern, seq):
            motifs.append({
                "motif": label,
                "start_position": match.start() + 1,
                "end_position": match.end(),
                "sequence": match.group(0),
            })
    residue_rows: list[dict[str, Any]] = []
    for index, residue in enumerate(seq, start=1):
        segment_number = None
        for number, (start, end, score) in enumerate(segments, start=1):
            if start <= index <= end:
                segment_number = number
                break
        residue_rows.append({
            "position": index,
            "residue": residue,
            "hydrophobic": residue in HYDROPHOBIC,
            "transmembrane_like_segment": segment_number,
        })
    return {
        "protein_class_review": class_token,
        "sequence_length": len(seq),
        "transmembrane_like_segments": [
            {"segment": number, "start": start, "end": end, "hydrophobic_fraction": round(float(score), 6)}
            for number, (start, end, score) in enumerate(segments, start=1)
        ],
        "motifs": pd.DataFrame(motifs),
        "residue_track": pd.DataFrame(residue_rows),
        "gpcr_classification": gpcr,
        "ion_channel_classification": ion,
        "scientific_boundary": "Sequence topology and motif triage only; experimental topology, alignment and specialist database confirmation remain required.",
    }


def target_evidence_graph(identifier: str, evidence_frame: pd.DataFrame | None = None) -> dict[str, Any]:
    """Create a versioned target/pathway/disease evidence graph with conflict review."""
    matched = lookup_target(identifier)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    target_id = normalize_target(identifier)
    if matched:
        target_id = str(matched.get("gene") or target_id)
        nodes.append({"node_id": target_id, "node_type": "target", "label": matched.get("name") or target_id, "source": "bundled registry"})
        for relation, values, node_type in (
            ("participates_in", matched.get("pathways", []), "pathway"),
            ("associated_with", matched.get("diseases", []), "disease"),
            ("classified_as", matched.get("categories", []), "target_class"),
            ("has_model", matched.get("models", []), "organism"),
        ):
            for value in values or []:
                node_id = f"{node_type}:{str(value).strip()}"
                nodes.append({"node_id": node_id, "node_type": node_type, "label": value, "source": "bundled registry"})
                edges.append({
                    "source": target_id, "target": node_id, "relationship": relation,
                    "direction": "supporting", "evidence_level": "bundled_snapshot",
                    "evidence_source": "BioIntel target registry",
                })
    else:
        nodes.append({"node_id": target_id, "node_type": "target", "label": identifier, "source": "user query"})

    if evidence_frame is not None and not evidence_frame.empty:
        lower = {str(column).lower(): str(column) for column in evidence_frame.columns}
        entity_col = lower.get("entity") or lower.get("related_entity") or lower.get("pathway") or lower.get("disease")
        relation_col = lower.get("relationship") or lower.get("relation")
        direction_col = lower.get("direction") or lower.get("effect")
        level_col = lower.get("evidence_level") or lower.get("confidence")
        source_col = lower.get("source") or lower.get("publication") or lower.get("reference")
        type_col = lower.get("entity_type") or lower.get("type")
        if entity_col is None:
            raise ValueError("Uploaded target evidence requires an entity/related_entity column.")
        direction_index: dict[tuple[str, str], set[str]] = {}
        for row_index, row in evidence_frame.iterrows():
            entity = str(row.get(entity_col) or "").strip()
            if not entity:
                continue
            node_type = str(row.get(type_col) or "evidence_entity").strip().lower() if type_col else "evidence_entity"
            node_id = f"{node_type}:{entity}"
            relationship = str(row.get(relation_col) or "related_to").strip() if relation_col else "related_to"
            direction = str(row.get(direction_col) or "unspecified").strip().lower() if direction_col else "unspecified"
            nodes.append({"node_id": node_id, "node_type": node_type, "label": entity, "source": "user evidence"})
            edges.append({
                "source": target_id,
                "target": node_id,
                "relationship": relationship,
                "direction": direction,
                "evidence_level": str(row.get(level_col) or "unspecified") if level_col else "unspecified",
                "evidence_source": str(row.get(source_col) or "uploaded row") if source_col else "uploaded row",
                "source_row": int(row_index) + 1,
            })
            direction_index.setdefault((node_id, relationship), set()).add(direction)
        for (node_id, relationship), directions in direction_index.items():
            meaningful = {direction for direction in directions if direction not in {"", "unspecified", "neutral"}}
            if len(meaningful) > 1:
                conflicts.append({
                    "entity": node_id,
                    "relationship": relationship,
                    "directions": ", ".join(sorted(meaningful)),
                    "review_required": True,
                })
    node_frame = pd.DataFrame(nodes).drop_duplicates("node_id", keep="first").reset_index(drop=True)
    edge_frame = pd.DataFrame(edges).drop_duplicates().reset_index(drop=True)
    return {
        "target_identifier": identifier,
        "target_found_in_registry": matched is not None,
        "nodes": node_frame,
        "edges": edge_frame,
        "conflicting_evidence": pd.DataFrame(conflicts),
        "registry_version": target_registry().get("version"),
        "scientific_boundary": "Evidence graph is a provenance-preserving research view; edges are not automatically causal or clinically validated.",
    }


def target_mechanism_workflow(
    identifier: str,
    *,
    sequence: str | None = None,
    evidence_frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    graph = target_evidence_graph(identifier, evidence_frame)
    pathway = pathway_mapping(identifier)
    topology = sequence_topology_track(sequence) if sequence and str(sequence).strip() else None
    return {
        "target_tagging": target_tagging(identifier, sequence),
        "pathway_mapping": pathway,
        "evidence_graph": graph,
        "sequence_topology": topology,
        "scientific_boundary": "Integrated target-mechanism research review; specialist databases, isoform alignment and experimental confirmation remain required.",
    }
