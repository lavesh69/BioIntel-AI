from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from .native_workflows import _check, _column, _metric, _numeric

AA = set("ACDEFGHIKLMNPQRSTVWYBXZJUO")
DNA = set("ACGTN")
HYDRO = set("AILMFWVY")


def _seq(frame: pd.DataFrame) -> tuple[str | None, str | None]:
    return _column(frame, "candidate", "candidate_id", "construct_id", "sequence_id", "id"), _column(
        frame, "sequence", "protein_sequence", "dna_sequence", "construct_sequence"
    )


def _gene_therapy(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    ident, seq_col = _seq(frame)
    if not seq_col:
        _check(checks, "Vector sequence schema", "fail", "A DNA vector/transgene sequence is required")
        return {}, ["Provide vector/transgene sequence, serotype, payload limits and safety evidence metadata."]
    serotype = _column(frame, "serotype", "capsid", "vector_type")
    nabs = _column(frame, "neutralizing_antibody_rate", "preexisting_immunity", "nab_rate")
    integration = _column(frame, "integration_risk", "integration_site_risk")
    rows = []
    limit = float(metadata.get("payload_limit_bp", 4700))
    for i, row in frame.iterrows():
        seq = re.sub(r"\s+", "", str(row[seq_col]).upper())
        gc = 100 * sum(c in "GC" for c in seq) / max(len(seq), 1)
        cpg = len(re.findall("CG", seq)) / max(len(seq), 1) * 1000
        max_hom = max((len(m.group(0)) for m in re.finditer(r"(A+|C+|G+|T+)", seq)), default=0)
        valid = bool(seq) and set(seq) <= DNA
        payload_ok = len(seq) <= limit
        flags = int(not valid) + int(not payload_ok) + int(gc < 30 or gc > 70) + int(max_hom >= 8)
        rows.append({"candidate": row[ident] if ident else i, "length_bp": len(seq), "payload_limit_bp": limit, "payload_pass": payload_ok, "gc_percent": gc, "cpg_per_kb": cpg, "max_homopolymer": max_hom, "sequence_valid": valid, "risk_flags": flags, "serotype": row[serotype] if serotype else "", "reported_immunity": row[nabs] if nabs else np.nan, "reported_integration_risk": row[integration] if integration else ""})
    table = pd.DataFrame(rows)
    _check(checks, "Payload capacity", "review" if (~table.payload_pass).any() else "pass", f"{int((~table.payload_pass).sum())} constructs exceed configured limit")
    _check(checks, "Serotype/capsid context", "pass" if serotype else "review", serotype or "Not supplied")
    _check(checks, "Pre-existing immunity evidence", "pass" if nabs else "review", nabs or "Not supplied")
    _check(checks, "Integration/biodistribution evidence", "pass" if integration else "review", integration or "Not supplied")
    _metric(metrics, "vector_candidates", len(table), "constructs")
    return {"vector_design_qc": table.sort_values(["risk_flags", "length_bp"])}, [
        "Confirm payload integrity, capsid identity, potency, biodistribution, shedding and integration-site risk experimentally.",
        "Manufacturing and clinical safety claims require qualified assays and regulatory review.",
    ]


def _cell_therapy(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    ident, seq_col = _seq(frame)
    antigen = _column(frame, "antigen", "target_antigen", "target")
    healthy = _column(frame, "healthy_tissue_expression", "off_tumor_expression", "off_tumour_expression")
    killing = _column(frame, "killing_percent", "cytotoxicity", "functional_killing")
    cytokine = _column(frame, "cytokine_release", "il6", "ifng")
    exhaustion = _column(frame, "exhaustion_score", "pd1", "tim3")
    if not (seq_col or antigen):
        _check(checks, "Cell-therapy construct schema", "fail", "Construct sequence and/or antigen target is required")
        return {}, ["Provide construct architecture, target antigen, healthy-tissue expression and functional assay results."]
    rows = []
    for i, row in frame.iterrows():
        seq = re.sub(r"\s+", "", str(row[seq_col]).upper()) if seq_col else ""
        invalid = sorted(set(seq) - AA) if seq else []
        hydro = sum(c in HYDRO for c in seq) / max(len(seq), 1) if seq else np.nan
        healthy_v = pd.to_numeric(pd.Series([row[healthy]]), errors="coerce").iloc[0] if healthy else np.nan
        killing_v = pd.to_numeric(pd.Series([row[killing]]), errors="coerce").iloc[0] if killing else np.nan
        exhaustion_v = pd.to_numeric(pd.Series([row[exhaustion]]), errors="coerce").iloc[0] if exhaustion else np.nan
        flags = int(bool(invalid)) + int(pd.notna(healthy_v) and healthy_v > float(metadata.get("max_healthy_expression", 0.1))) + int(pd.notna(killing_v) and killing_v < 50) + int(pd.notna(exhaustion_v) and exhaustion_v > 0.5)
        rows.append({"candidate": row[ident] if ident else i, "antigen": row[antigen] if antigen else "", "construct_length": len(seq), "invalid_residues": ",".join(invalid), "hydrophobic_fraction": hydro, "healthy_tissue_expression": healthy_v, "functional_killing": killing_v, "cytokine_release": row[cytokine] if cytokine else np.nan, "exhaustion_score": exhaustion_v, "risk_flags": flags})
    table = pd.DataFrame(rows)
    _check(checks, "Antigen definition", "pass" if antigen else "review", antigen or "Not supplied")
    _check(checks, "Healthy-tissue/off-tumour evidence", "pass" if healthy else "review", healthy or "Not supplied")
    _check(checks, "Functional killing evidence", "pass" if killing else "review", killing or "Not supplied")
    _check(checks, "Cytokine/exhaustion evidence", "pass" if cytokine and exhaustion else "review", "Detected" if cytokine and exhaustion else "Incomplete")
    _metric(metrics, "cell_therapy_candidates", len(table), "constructs")
    return {"cell_therapy_candidate_review": table.sort_values("risk_flags")}, [
        "Review antigen expression across healthy tissues and assess tonic signalling, exhaustion and cytokine-release risk.",
        "Confirm potency, specificity, persistence, manufacturing consistency and safety in qualified assays.",
    ]


def _protein_design(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    ident, seq_col = _seq(frame)
    confidence = _column(frame, "plddt", "confidence", "model_confidence")
    identity = _column(frame, "max_identity", "nearest_identity", "sequence_identity")
    expression = _column(frame, "expression_yield", "expression", "yield")
    activity = _column(frame, "activity", "measured_activity", "fitness")
    if not seq_col:
        _check(checks, "Protein sequence schema", "fail", "A protein sequence column is required")
        return {}, ["Provide designed protein sequences and model/experimental evidence fields."]
    rows = []
    for i, row in frame.iterrows():
        seq = re.sub(r"\s+", "", str(row[seq_col]).upper())
        invalid = sorted(set(seq) - AA)
        hydro = sum(c in HYDRO for c in seq) / max(len(seq), 1)
        low_complexity = max((len(m.group(0)) for m in re.finditer(r"(.)\1+", seq)), default=1)
        cys = seq.count("C")
        conf = pd.to_numeric(pd.Series([row[confidence]]), errors="coerce").iloc[0] if confidence else np.nan
        ident_v = pd.to_numeric(pd.Series([row[identity]]), errors="coerce").iloc[0] if identity else np.nan
        flags = int(bool(invalid)) + int(hydro > 0.5) + int(low_complexity >= 6) + int(cys % 2 == 1) + int(pd.notna(conf) and conf < 70)
        rows.append({"candidate": row[ident] if ident else i, "length": len(seq), "invalid_residues": ",".join(invalid), "hydrophobic_fraction": hydro, "max_repeat_run": low_complexity, "cysteines": cys, "model_confidence": conf, "nearest_identity": row[identity] if identity else np.nan, "expression_yield": row[expression] if expression else np.nan, "measured_activity": row[activity] if activity else np.nan, "risk_flags": flags})
    table = pd.DataFrame(rows)
    _check(checks, "Model confidence", "pass" if confidence else "review", confidence or "Not supplied")
    _check(checks, "Novelty/nearest-neighbour evidence", "pass" if identity else "review", identity or "Not supplied")
    _check(checks, "Expression/activity evidence", "pass" if expression and activity else "review", "Detected" if expression and activity else "Incomplete")
    _metric(metrics, "protein_design_candidates", len(table), "proteins")
    return {"protein_design_candidate_qc": table.sort_values(["risk_flags", "model_confidence"], ascending=[True, False])}, [
        "Record model weights, constraints, seeds, templates and nearest-neighbour analysis for every design.",
        "Predicted structure/confidence does not establish expression, stability, activity or safety.",
    ]


def _enzyme_design(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    ident, seq_col = _seq(frame)
    reaction = _column(frame, "reaction", "reaction_id", "ec_number")
    dg = _column(frame, "delta_g", "deltag", "reaction_dg")
    flux = _column(frame, "predicted_flux", "flux")
    kcat = _column(frame, "kcat", "turnover")
    km = _column(frame, "km", "michaelis_constant")
    if not (seq_col or reaction):
        _check(checks, "Enzyme design schema", "fail", "Sequence and/or reaction identifier is required")
        return {}, ["Provide enzyme sequence, target reaction and kinetic/thermodynamic evidence."]
    rows = []
    for i, row in frame.iterrows():
        seq = re.sub(r"\s+", "", str(row[seq_col]).upper()) if seq_col else ""
        dg_v = pd.to_numeric(pd.Series([row[dg]]), errors="coerce").iloc[0] if dg else np.nan
        flux_v = pd.to_numeric(pd.Series([row[flux]]), errors="coerce").iloc[0] if flux else np.nan
        kcat_v = pd.to_numeric(pd.Series([row[kcat]]), errors="coerce").iloc[0] if kcat else np.nan
        km_v = pd.to_numeric(pd.Series([row[km]]), errors="coerce").iloc[0] if km else np.nan
        efficiency = kcat_v / km_v if pd.notna(kcat_v) and pd.notna(km_v) and km_v > 0 else np.nan
        flags = int(seq and bool(set(seq) - AA)) + int(pd.notna(dg_v) and dg_v > 0) + int(pd.notna(flux_v) and flux_v <= 0)
        rows.append({"candidate": row[ident] if ident else i, "reaction": row[reaction] if reaction else "", "sequence_length": len(seq), "delta_g": dg_v, "predicted_flux": flux_v, "kcat": kcat_v, "km": km_v, "catalytic_efficiency": efficiency, "risk_flags": flags})
    table = pd.DataFrame(rows)
    _check(checks, "Reaction definition", "pass" if reaction else "review", reaction or "Not supplied")
    _check(checks, "Thermodynamic feasibility", "pass" if dg else "review", dg or "Not supplied")
    _check(checks, "Flux context", "pass" if flux else "review", flux or "Not supplied")
    _check(checks, "Kinetic evidence", "pass" if kcat and km else "review", "kcat/Km detected" if kcat and km else "Incomplete")
    _metric(metrics, "enzyme_candidates", len(table), "enzymes")
    return {"enzyme_pathway_feasibility": table.sort_values("risk_flags")}, [
        "Evaluate host context, cofactor balance, competing pathways, toxicity and metabolic burden.",
        "Confirm catalytic efficiency and pathway flux experimentally under relevant conditions.",
    ]


def _structural_protein(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    structure = _column(frame, "structure_id", "pdb_id", "model_id", "id")
    plddt = _column(frame, "plddt", "confidence")
    clash = _column(frame, "clashscore", "clashes")
    rama = _column(frame, "ramachandran_outliers", "rama_outliers")
    missing = _column(frame, "missing_residues", "missing_atoms")
    resolution = _column(frame, "resolution", "resolution_angstrom")
    if not structure:
        _check(checks, "Structure schema", "fail", "A structure/model identifier is required")
        return {}, ["Provide structure IDs and validation metrics from a qualified structure workflow."]
    table = frame[[c for c in (structure, plddt, clash, rama, missing, resolution) if c]].copy()
    numeric_map = {}
    for c in (plddt, clash, rama, missing, resolution):
        if c:
            numeric_map[c] = pd.to_numeric(table[c], errors="coerce")
    for c, vals in numeric_map.items():
        table[f"{c}_numeric"] = vals
    _check(checks, "Confidence metric", "pass" if plddt or resolution else "review", plddt or resolution or "Not supplied")
    _check(checks, "Clashscore", "pass" if clash else "review", clash or "Not supplied")
    _check(checks, "Ramachandran validation", "pass" if rama else "review", rama or "Not supplied")
    _check(checks, "Missing-residue/atom audit", "pass" if missing else "review", missing or "Not supplied")
    _metric(metrics, "structures", int(frame[structure].nunique()), "structures")
    return {"structure_validation": table.head(100_000)}, [
        "Repair/protonate structures with explicit methods and retain original coordinates and validation reports.",
        "Model confidence does not establish binding, dynamics or biological function.",
    ]


def _virology(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    sample = _column(frame, "sample_id", "isolate_id", "sequence_id", "sample")
    date = _column(frame, "collection_date", "date", "time")
    lineage = _column(frame, "lineage", "clade")
    mutations = _column(frame, "mutation_count", "mutations", "snp_distance")
    location = _column(frame, "location", "region", "country")
    if not sample:
        _check(checks, "Virology sequence schema", "fail", "Sample/isolate identifier is required")
        return {}, ["Provide isolate IDs, collection date, lineage, mutation/SNP metrics and location."]
    table = frame[[c for c in (sample, date, lineage, mutations, location) if c]].copy()
    if date:
        parsed = pd.to_datetime(table[date], errors="coerce", utc=True)
        _check(checks, "Collection dates", "review" if parsed.isna().any() else "pass", f"{int(parsed.isna().sum())} invalid dates")
    else:
        _check(checks, "Collection dates", "review", "Not supplied")
    _check(checks, "Lineage/clade annotation", "pass" if lineage else "review", lineage or "Not supplied")
    _check(checks, "Mutation/SNP evidence", "pass" if mutations else "review", mutations or "Not supplied")
    _check(checks, "Geographic metadata", "pass" if location else "review", location or "Not supplied")
    if lineage:
        summary = frame.groupby(lineage)[sample].nunique().rename("samples").reset_index().sort_values("samples", ascending=False)
    else:
        summary = pd.DataFrame()
    _metric(metrics, "viral_samples", int(frame[sample].nunique()), "samples")
    return {"lineage_summary": summary, "viral_evidence": table.head(100_000)}, [
        "Assess recombination, sampling bias, sequencing errors and within-host mixtures before evolutionary interpretation.",
        "Use time-resolved phylogenetics and epidemiological metadata for transmission claims.",
    ]


def _synthetic_biology(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    circuit = _column(frame, "circuit_id", "construct_id", "id")
    promoter = _column(frame, "promoter", "promoter_strength")
    rbs = _column(frame, "rbs", "rbs_strength")
    output = _column(frame, "output", "expression", "reporter")
    burden = _column(frame, "growth_burden", "burden", "growth_rate_change")
    leak = _column(frame, "leakiness", "basal_expression")
    if not circuit:
        _check(checks, "Circuit schema", "fail", "Circuit/construct identifier is required")
        return {}, ["Provide circuit IDs, part strengths, measured output and host-burden evidence."]
    table = frame[[c for c in (circuit, promoter, rbs, output, burden, leak) if c]].copy()
    _check(checks, "Promoter/RBS definition", "pass" if promoter and rbs else "review", "Detected" if promoter and rbs else "Incomplete")
    _check(checks, "Output/transfer function", "pass" if output else "review", output or "Not supplied")
    _check(checks, "Host burden", "pass" if burden else "review", burden or "Not supplied")
    _check(checks, "Leakiness", "pass" if leak else "review", leak or "Not supplied")
    numeric = _numeric(frame, exclude=[circuit])
    if len(numeric) >= 2:
        corr = frame[numeric].apply(pd.to_numeric, errors="coerce").corr().reset_index(names="feature")
    else:
        corr = pd.DataFrame()
    _metric(metrics, "circuits", int(frame[circuit].nunique()), "circuits")
    return {"circuit_evidence": table.head(100_000), "part_output_correlations": corr}, [
        "Model stochastic expression, host burden, growth feedback and context dependence before circuit selection.",
        "Confirm circuit behaviour, containment and biosafety experimentally in the intended host.",
    ]


def biodesign_demo(family: str, rng: np.random.Generator) -> pd.DataFrame | None:
    if family == "gene-therapy":
        return pd.DataFrame({"construct_id": ["V1", "V2"], "dna_sequence": ["ATG" + "GCC" * 300 + "TAA", "ATG" + "CGT" * 1200 + "TAA"], "serotype": ["AAV9", "AAV8"], "neutralizing_antibody_rate": [0.1, 0.25], "integration_risk": ["low", "review"]})
    if family == "cell-therapy":
        return pd.DataFrame({"construct_id": ["CAR1", "CAR2"], "protein_sequence": ["MKTIIALSYIFCLVFADYKDDDDK" * 4, "ACDEFGHIKLMNPQRSTVWY" * 5], "antigen": ["CD19", "BCMA"], "healthy_tissue_expression": [0.02, 0.08], "killing_percent": [78, 64], "cytokine_release": [0.2, 0.4], "exhaustion_score": [0.2, 0.35]})
    if family == "protein-design":
        return pd.DataFrame({"candidate_id": ["P1", "P2", "P3"], "protein_sequence": ["ACDEFGHIKLMNPQRSTVWY" * 5, "MKTIIALSYIFCLVFADYKDDDDK" * 4, "AAAAAAAACCCCCCCCGGGGGGGG"], "plddt": [88, 74, 45], "max_identity": [0.25, 0.45, 0.1], "expression_yield": [25, 12, 0.5], "activity": [1.2, 0.8, 0.1]})
    if family == "enzyme-design":
        return pd.DataFrame({"candidate_id": ["E1", "E2"], "protein_sequence": ["ACDEFGHIKLMNPQRSTVWY" * 4, "MKTIIALSYIFCLVFADYKDDDDK" * 3], "reaction_id": ["R1", "R2"], "delta_g": [-12.5, 3.2], "predicted_flux": [4.2, 0.0], "kcat": [20, 5], "km": [0.2, 1.5]})
    if family == "structural-protein":
        return pd.DataFrame({"structure_id": ["S1", "S2"], "plddt": [90, 65], "clashscore": [4.2, 18.5], "ramachandran_outliers": [0.2, 3.1], "missing_residues": [0, 12], "resolution": [2.0, 3.5]})
    if family == "virology-evolution":
        return pd.DataFrame({"sample_id": [f"V{i}" for i in range(20)], "collection_date": pd.date_range("2025-01-01", periods=20).astype(str), "lineage": ["L1"] * 12 + ["L2"] * 8, "mutation_count": rng.integers(2, 20, 20), "location": ["North"] * 10 + ["South"] * 10})
    if family == "synthetic-biology":
        return pd.DataFrame({"circuit_id": ["C1", "C2", "C3"], "promoter_strength": [0.2, 0.6, 0.9], "rbs_strength": [0.3, 0.7, 0.8], "expression": [10, 45, 70], "growth_burden": [0.05, 0.15, 0.35], "leakiness": [0.01, 0.04, 0.12]})
    return None
