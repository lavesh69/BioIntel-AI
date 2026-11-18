from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LastMileProfile:
    module_key: str
    features: tuple[str, ...]
    specialist_confirmations: tuple[str, ...]


LAST_MILE_PROFILES: dict[str, LastMileProfile] = {
    "population_gwas_peak": LastMileProfile("population_gwas_peak", ("Fixed-effect meta-analysis when beta/SE/study are supplied", "Gene burden summary", "Ancestry transferability audit", "PRS utility boundary"), ("REGENIE/SAIGE/PLINK2", "independent cohort", "ancestry-matched LD panel")),
    "epigenomics_peak": LastMileProfile("epigenomics_peak", ("Allele-specific accessibility", "contact-supported peak-to-gene links", "replicate concordance", "chromatin-state transitions"), ("replicate-aware peak caller", "Hi-C/contact map", "orthogonal regulatory assay")),
    "pharmacogenomics_peak": LastMileProfile("pharmacogenomics_peak", ("CNV/hybrid allele review", "phasing evidence", "uncallable locus audit", "guideline change impact"), ("validated star-allele caller", "orthogonal genotyping", "qualified clinical review")),
    "structural_variant_peak": LastMileProfile("structural_variant_peak", ("BAF/CNV evidence integration", "mosaic confidence", "complex-event grouping", "caller conflict queue"), ("raw-read inspection", "long-read/orthogonal confirmation", "validated SV truth set")),
    "rna_splicing_peak": LastMileProfile("rna_splicing_peak", ("Cryptic exon flagging", "reading-frame consequence", "protein-domain impact", "tissue outlier support"), ("splice-aware alignment", "RT-PCR/long-read confirmation", "tissue-matched reference")),
    "immune_repertoire": LastMileProfile("immune_repertoire", ("Antigen-specificity evidence", "paired-chain completeness", "clonal lineage readiness", "compartment migration"), ("AIRR-compliant processing", "antigen binding evidence", "matched sampling design")),
    "single_cell_multiome": LastMileProfile("single_cell_multiome", ("WNN-style modality weighting proxy", "batch method audit", "marker agreement", "perturbation-aware trajectory readiness"), ("qualified multimodal integration", "independent label validation", "held-out atlas")),
    "proteogenomics_peak": LastMileProfile("proteogenomics_peak", ("Spectrum evidence tier", "immunopeptidomics support", "normal-tissue exclusion", "vaccine panel diversity"), ("target-decoy/FDR search", "validated HLA typing", "functional immune assay")),
    "gene_regulatory_network": LastMileProfile("gene_regulatory_network", ("Condition-specific network rewiring", "edge bootstrap stability", "causal evidence tier", "time-series transition readiness"), ("perturbation evidence", "binding/accessibility confirmation", "independent cohort")),
    "federated_genomic_discovery": LastMileProfile("federated_genomic_discovery", ("VRS-compatible identities", "source availability audit", "consent policy matrix", "query retry manifest"), ("authenticated source", "source-specific governance", "human case review")),
    "viral_within_host": LastMileProfile("viral_within_host", ("Amplicon protocol awareness", "mixed-infection confidence", "transmission uncertainty", "resistance evidence tier"), ("validated caller", "replicate controls", "epidemiological confirmation")),
    "genome_annotation": LastMileProfile("genome_annotation", ("Evidence-weighted model reconciliation", "annotation conflict queue", "transfer confidence", "curator-ready corrected export"), ("RNA/protein evidence", "BUSCO/orthology validation", "manual curation")),
    "circular_dna_instability": LastMileProfile("circular_dna_instability", ("ecDNA-versus-BFB evidence proxy", "purity-aware confidence", "topology recurrence", "long-read confirmation plan"), ("AmpliconArchitect/Circle-Map", "long-read/FISH validation", "tumour purity estimate")),
    "environmental_edna": LastMileProfile("environmental_edna", ("Occupancy uncertainty", "replicate concordance", "contamination source audit", "environmental covariate readiness"), ("mock community", "field/lab controls", "validated occupancy model")),
    "comparative_regulatory_genomics": LastMileProfile("comparative_regulatory_genomics", ("Regulatory gain/loss classification", "tissue match audit", "phylogenetic support readiness", "ancestral-state summary"), ("whole-genome alignment", "species/tissue-matched assays", "phylogenetic model")),
}


def _numeric(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def _wilson(successes: pd.Series, totals: pd.Series, z: float = 1.96) -> tuple[pd.Series, pd.Series]:
    totals = pd.to_numeric(totals, errors="coerce").replace(0, np.nan)
    p = pd.to_numeric(successes, errors="coerce") / totals
    denom = 1 + z**2 / totals
    center = (p + z**2 / (2 * totals)) / denom
    half = z * np.sqrt((p * (1 - p) / totals) + z**2 / (4 * totals**2)) / denom
    return (center - half).clip(0, 1), (center + half).clip(0, 1)


def _gwas(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    extras: dict[str, pd.DataFrame] = {}
    if {"variant", "beta", "se"}.issubset(frame.columns):
        rows = []
        for variant, group in frame.groupby("variant", dropna=False):
            beta = _numeric(group, "beta", np.nan)
            se = _numeric(group, "se", np.nan).replace(0, np.nan)
            valid = beta.notna() & se.notna()
            if not valid.any():
                continue
            weights = 1 / (se[valid] ** 2)
            pooled = float((weights * beta[valid]).sum() / weights.sum())
            pooled_se = float(np.sqrt(1 / weights.sum()))
            rows.append({"variant": variant, "studies": int(valid.sum()), "meta_beta": pooled, "meta_se": pooled_se, "z": pooled / pooled_se if pooled_se else np.nan})
        extras["fixed_effect_meta_analysis"] = pd.DataFrame(rows)
    if {"gene", "genotype"}.issubset(frame.columns):
        burden = frame.groupby("gene", as_index=False).agg(samples=("sample", "nunique") if "sample" in frame.columns else ("genotype", "size"), allele_burden=("genotype", lambda x: float(_numeric(pd.DataFrame({"genotype": x}), "genotype").sum())))
        extras["gene_burden_summary"] = burden
    if "ancestry" in frame.columns:
        numeric = next((column for column in ("priority_score", "prs", "score", "phenotype") if column in frame.columns), None)
        if numeric:
            extras["ancestry_transferability"] = frame.groupby("ancestry", as_index=False).agg(records=(numeric, "size"), mean_score=(numeric, lambda x: float(pd.to_numeric(x, errors="coerce").mean())), score_sd=(numeric, lambda x: float(pd.to_numeric(x, errors="coerce").std(ddof=0))))
    return extras


def _epigenomics(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    extras: dict[str, pd.DataFrame] = {}
    if {"ref_count", "alt_count"}.issubset(frame.columns):
        total = _numeric(frame, "ref_count") + _numeric(frame, "alt_count")
        out = frame.copy()
        out["alt_fraction"] = _numeric(out, "alt_count") / total.replace(0, np.nan)
        out["allelic_imbalance"] = (out["alt_fraction"] - 0.5).abs()
        extras["allele_specific_accessibility"] = out
    if {"region", "gene", "contact_score"}.issubset(frame.columns):
        links = frame.groupby(["region", "gene"], as_index=False).agg(contact_score=("contact_score", "mean"), samples=("sample", "nunique") if "sample" in frame.columns else ("contact_score", "size"))
        extras["contact_supported_links"] = links.sort_values("contact_score", ascending=False)
    if {"sample", "condition", "signal"}.issubset(frame.columns):
        replicate = frame.groupby(["condition", "sample"], as_index=False).agg(mean_signal=("signal", lambda x: float(pd.to_numeric(x, errors="coerce").mean())), regions=("region", "nunique") if "region" in frame.columns else ("signal", "size"))
        extras["replicate_concordance"] = replicate
    return extras


def _pgx(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = frame.copy()
    if "copy_number" in out.columns:
        cn = _numeric(out, "copy_number", 2)
        out["cnv_review"] = np.where(cn < 2, "Deletion/loss review", np.where(cn > 2, "Duplication/hybrid review", "Diploid"))
    if "phase_set" in out.columns or "haplotype" in out.columns:
        phase_col = "phase_set" if "phase_set" in out.columns else "haplotype"
        out["phasing_evidence"] = out[phase_col].notna() & out[phase_col].astype(str).ne("")
    return {"cnv_hybrid_phasing_review": out}


def _sv(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    extras: dict[str, pd.DataFrame] = {}
    if "baf" in frame.columns:
        out = frame.copy(); baf = _numeric(out, "baf", 0.5).clip(0, 1)
        out["baf_deviation"] = (baf - 0.5).abs()
        out["allelic_imbalance_flag"] = out["baf_deviation"] >= 0.2
        extras["baf_cnv_evidence"] = out
    af = next((c for c in ("allele_fraction", "vaf", "frequency") if c in frame.columns), None)
    if af:
        out = frame.copy(); values = _numeric(out, af).clip(0, 1)
        support = _numeric(out, "support", 1).clip(lower=1)
        out["mosaic_confidence"] = (1 - np.exp(-support / 10)) * (1 - (values - 0.25).abs().clip(0, 0.25) / 0.25)
        extras["mosaic_confidence"] = out
    return extras


def _splicing(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = frame.copy()
    event_text = out.get("event", pd.Series("", index=out.index)).astype(str).str.lower()
    out["cryptic_exon_candidate"] = event_text.str.contains("cryptic|novel|unannotated", regex=True)
    if "delta_psi" in out.columns:
        out["frame_disruption_risk"] = _numeric(out, "delta_psi").abs().clip(0, 1)
    elif "psi" in out.columns:
        out["frame_disruption_risk"] = (_numeric(out, "psi") - 0.5).abs() * 2
    if "domain" in out.columns:
        out["protein_domain_impact"] = out["domain"].notna() & out["domain"].astype(str).ne("")
    return {"cryptic_exon_and_protein_impact": out}


def _immune(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = frame.copy()
    chain = out.get("chain", pd.Series("", index=out.index)).astype(str)
    out["paired_chain_ready"] = chain.str.contains("TRA|TRB|IGH|IGK|IGL", regex=True)
    if "antigen_score" in out.columns:
        out["antigen_specificity_evidence"] = _numeric(out, "antigen_score").clip(0, 1)
    elif "antigen" in out.columns:
        out["antigen_specificity_evidence"] = out["antigen"].notna().astype(float)
    return {"antigen_and_paired_chain_review": out}


def _multiome(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if not {"cell", "modality", "value"}.issubset(frame.columns):
        return {}
    wide = frame.pivot_table(index="cell", columns="modality", values="value", aggfunc="sum", fill_value=0).reset_index()
    modalities = [column for column in wide.columns if column != "cell"]
    if modalities:
        ranks = wide[modalities].rank(pct=True)
        denominator = ranks.sum(axis=1).replace(0, np.nan)
        for modality in modalities:
            wide[f"weight_{modality}"] = ranks[modality] / denominator
        wide["wnn_balance"] = 1 - ranks.std(axis=1).fillna(0)
    return {"wnn_modality_weights": wide}


def _proteogenomics(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = frame.copy()
    score = _numeric(out, "spectrum_score", np.nan) if "spectrum_score" in out.columns else _numeric(out, "ms_support", 0)
    q = _numeric(out, "q_value", 1.0) if "q_value" in out.columns else pd.Series(1 - np.minimum(1, score), index=out.index)
    out["spectrum_evidence_tier"] = np.select([q <= 0.01, q <= 0.05, score > 0], ["Strong", "Moderate", "Supporting"], default="Predicted only")
    return {"spectrum_evidence_review": out}


def _grn(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if not {"tf", "target", "condition"}.issubset(frame.columns):
        return {}
    value = next((c for c in ("activity", "evidence", "expression", "priority_score") if c in frame.columns), None)
    if not value:
        return {}
    pivot = frame.pivot_table(index=["tf", "target"], columns="condition", values=value, aggfunc="mean", fill_value=0).reset_index()
    condition_cols = [c for c in pivot.columns if c not in {"tf", "target"}]
    if len(condition_cols) >= 2:
        pivot["rewiring_magnitude"] = (pd.to_numeric(pivot[condition_cols[-1]], errors="coerce") - pd.to_numeric(pivot[condition_cols[0]], errors="coerce")).abs()
    return {"network_rewiring": pivot}



def _federated(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if "source" not in frame.columns:
        return {}
    aggregations = {"records": ("source", "size")}
    if "case_id" in frame.columns:
        aggregations["cases"] = ("case_id", "nunique")
    if "phenotype_similarity" in frame.columns:
        aggregations["mean_phenotype_similarity"] = ("phenotype_similarity", lambda x: float(pd.to_numeric(x, errors="coerce").mean()))
    if "variant_match" in frame.columns:
        aggregations["mean_variant_match"] = ("variant_match", lambda x: float(pd.to_numeric(x, errors="coerce").mean()))
    availability = frame.groupby("source", as_index=False).agg(**aggregations)
    if "access_status" in frame.columns:
        access = frame.pivot_table(index="source", columns="access_status", values=frame.columns[0], aggfunc="size", fill_value=0).reset_index()
    else:
        access = pd.DataFrame()
    return {"federated_source_availability": availability, "consent_access_matrix": access}

def _viral(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    extras: dict[str, pd.DataFrame] = {}
    if {"subject", "position"}.issubset(frame.columns):
        value = next((c for c in ("depth", "support", "frequency") if c in frame.columns), None)
        if value:
            protocol = frame.groupby(["subject", "position"], as_index=False).agg(records=(value, "size"), mean_support=(value, lambda x: float(pd.to_numeric(x, errors="coerce").mean())))
            protocol["low_support_review"] = protocol["mean_support"] < float(protocol["mean_support"].median() * 0.2 if len(protocol) else 0)
            extras["amplicon_protocol_awareness"] = protocol
    if "amplicon" in frame.columns:
        value = next((c for c in ("depth", "support", "coverage") if c in frame.columns), None)
        if value:
            amplicon = frame.groupby("amplicon", as_index=False).agg(mean_depth=(value, lambda x: float(pd.to_numeric(x, errors="coerce").mean())), records=(value, "size"))
            threshold = float(amplicon["mean_depth"].median() * 0.2) if len(amplicon) else 0
            amplicon["dropout_risk"] = amplicon["mean_depth"] < threshold
            extras["amplicon_protocol_qc"] = amplicon
    return extras


def _annotation(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if not {"feature_id", "evidence"}.issubset(frame.columns):
        return {}
    out = frame.copy()
    evidence_map = {"protein": 1.0, "rna": 0.9, "orthology": 0.75, "ab_initio": 0.4}
    out["reconciliation_score"] = out["evidence"].astype(str).str.lower().map(evidence_map).fillna(0.25)
    out["curation_action"] = np.where(out["reconciliation_score"] >= 0.8, "Accept candidate", np.where(out["reconciliation_score"] >= 0.5, "Review evidence", "Manual curation required"))
    return {"evidence_weighted_reconciliation": out}


def _circular(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = frame.copy()
    cn = _numeric(out, "copy_number", 2)
    support = _numeric(out, "support", 1)
    event = out.get("event_type", pd.Series("", index=out.index)).astype(str).str.lower()
    out["ecdna_evidence_score"] = (0.45 * np.minimum(1, cn / 10) + 0.35 * np.minimum(1, support / 20) + 0.20 * event.str.contains("ecdna|circle").astype(float)).clip(0, 1)
    out["bfb_evidence_score"] = (0.55 * np.minimum(1, cn / 15) + 0.45 * event.str.contains("bfb|breakage|fold").astype(float)).clip(0, 1)
    out["topology_classification"] = np.where(out["ecdna_evidence_score"] > out["bfb_evidence_score"], "ecDNA-like", "BFB/linear-like")
    return {"ecdna_bfb_evidence": out}


def _edna(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if not {"site", "species"}.issubset(frame.columns):
        return {}
    detection = frame.get("detection", _numeric(frame, "reads") > 0).astype(bool)
    work = frame.assign(_detection=detection)
    out = work.groupby(["site", "species"], as_index=False).agg(samples=("_detection", "size"), detections=("_detection", "sum"))
    out["occupancy"] = out["detections"] / out["samples"].replace(0, np.nan)
    out["occupancy_lower"], out["occupancy_upper"] = _wilson(out["detections"], out["samples"])
    return {"occupancy_uncertainty": out}


def _comparative(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if not {"region", "species", "activity"}.issubset(frame.columns):
        return {}
    pivot = frame.pivot_table(index="region", columns="species", values="activity", aggfunc="mean", fill_value=0).reset_index()
    species = [c for c in pivot.columns if c != "region"]
    if species:
        active = (pivot[species] > 0).sum(axis=1)
        pivot["regulatory_state"] = np.select([active == len(species), active == 1, active == 0], ["Conserved active", "Lineage-specific gain/loss", "Inactive/unsupported"], default="Partially conserved")
        pivot["species_supported"] = active
    return {"regulatory_gain_loss": pivot}


def augment_bundle(input_frame: pd.DataFrame, module: Any, bundle: Any, parameters: dict[str, Any] | None = None) -> Any:
    key = module.key
    functions = {
        "population_gwas_peak": _gwas,
        "epigenomics_peak": _epigenomics,
        "pharmacogenomics_peak": _pgx,
        "structural_variant_peak": _sv,
        "rna_splicing_peak": _splicing,
        "immune_repertoire": _immune,
        "single_cell_multiome": _multiome,
        "proteogenomics_peak": _proteogenomics,
        "gene_regulatory_network": _grn,
        "federated_genomic_discovery": _federated,
        "viral_within_host": _viral,
        "genome_annotation": _annotation,
        "circular_dna_instability": _circular,
        "environmental_edna": _edna,
        "comparative_regulatory_genomics": _comparative,
    }
    extra_tables: dict[str, pd.DataFrame] = {}
    function = functions.get(key)
    if function:
        try:
            extra_tables = function(input_frame.copy())
        except Exception:
            extra_tables = {}
    extras = dict(bundle.extras)
    for name, table in extra_tables.items():
        if isinstance(table, pd.DataFrame):
            extras[f"last_mile_{name}"] = table
    summary = dict(bundle.summary)
    profile = LAST_MILE_PROFILES[key]
    summary["last_mile_features"] = list(profile.features)
    summary["specialist_confirmations"] = list(profile.specialist_confirmations)
    summary["last_mile_tables"] = sorted(f"last_mile_{name}" for name in extra_tables)
    metrics = dict(summary.get("metrics", {}))
    metrics["last_mile_tables"] = len(extra_tables)
    summary["metrics"] = metrics
    return bundle.__class__(result=bundle.result, summary=summary, extras=extras, quality=bundle.quality)


__all__ = ["LastMileProfile", "LAST_MILE_PROFILES", "augment_bundle"]
