from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .native_integrity import parse_scientific_bool

_AA = set("ACDEFGHIKLMNPQRSTVWY")
_DNA = set("ACGTN")


def _column(frame: pd.DataFrame, *names: str) -> str | None:
    direct = {str(column).lower(): str(column) for column in frame.columns}
    normalized = {re.sub(r"[^a-z0-9]", "", str(column).lower()): str(column) for column in frame.columns}
    for name in names:
        if name.lower() in direct:
            return direct[name.lower()]
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        if key in normalized:
            return normalized[key]
    return None


def _check(rows: list[dict[str, Any]], name: str, status: str, detail: str) -> None:
    rows.append({"check": name, "status": status, "detail": str(detail)})


def _metric(rows: list[dict[str, Any]], name: str, value: Any, unit: str = "") -> None:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        value = None
    rows.append({"metric": name, "value": value, "unit": unit})


def _sequence(value: Any, alphabet: set[str]) -> str:
    text = re.sub(r"\s+", "", str(value or "").upper())
    return "".join(character for character in text if character in alphabet)


def _longest_hydrophobic_run(sequence: str) -> int:
    hydrophobic = set("AVILMFWY")
    longest = current = 0
    for residue in sequence:
        current = current + 1 if residue in hydrophobic else 0
        longest = max(longest, current)
    return longest


def _motif_count(sequence: str, motifs: Sequence[str]) -> int:
    return sum(sequence.count(motif) for motif in motifs)


def _antibody(frame: pd.DataFrame, metadata: Mapping[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    identifier = _column(frame, "candidate_id", "antibody_id", "construct_id", "id")
    sequence_col = _column(frame, "sequence", "protein_sequence", "amino_acid_sequence", "aa_sequence")
    chain_col = _column(frame, "chain", "chain_type", "heavy_light")
    pair_col = _column(frame, "pair_id", "molecule_id", "antibody_pair")
    if not sequence_col:
        _check(checks, "Antibody sequence evidence", "fail", "Amino-acid sequence column is required")
        return
    rows = []
    for index, row in frame.iterrows():
        raw = re.sub(r"\s+", "", str(row[sequence_col] or "").upper())
        sequence = _sequence(raw, _AA)
        invalid = sorted(set(raw) - _AA)
        inferred_chain = "unknown"
        if sequence.startswith(("EVQL", "QVQL", "DVQL", "QVEL", "VH")) or len(sequence) >= 105:
            inferred_chain = "heavy-like"
        elif sequence.startswith(("DIQMT", "EIVLT", "QSVLT", "DIVMT", "VL")) or 80 <= len(sequence) < 105:
            inferred_chain = "light-like"
        cys_count = sequence.count("C")
        liabilities = {
            "deamidation": _motif_count(sequence, ("NG", "NS", "NT", "QG")),
            "isomerization": _motif_count(sequence, ("DG", "DS")),
            "oxidation": sequence.count("M") + sequence.count("W"),
            "glycosylation": len(re.findall(r"N[^P][ST]", sequence)),
            "cleavage": _motif_count(sequence, ("DP", "TS", "HS")),
        }
        hydrophobic_run = _longest_hydrophobic_run(sequence)
        risk_score = (
            min(30, 5 * liabilities["deamidation"])
            + min(20, 5 * liabilities["isomerization"])
            + min(15, 2 * liabilities["oxidation"])
            + min(15, 5 * liabilities["glycosylation"])
            + (20 if hydrophobic_run >= 8 else 10 if hydrophobic_run >= 6 else 0)
            + (20 if invalid else 0)
            + (10 if cys_count % 2 else 0)
        )
        rows.append({
            "candidate_id": str(row[identifier]) if identifier else str(index),
            "declared_chain": str(row[chain_col]) if chain_col else "",
            "inferred_chain": inferred_chain,
            "pair_id": str(row[pair_col]) if pair_col else "",
            "length_aa": len(sequence),
            "invalid_residues": ",".join(invalid),
            "cysteines": cys_count,
            "unpaired_cysteine_warning": bool(cys_count % 2),
            "longest_hydrophobic_run": hydrophobic_run,
            **{f"{key}_motifs": value for key, value in liabilities.items()},
            "sequence_liability_risk": min(100, risk_score),
            "sequence_sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
        })
    audit = pd.DataFrame(rows)
    tables["antibody_sequence_liability_audit"] = audit
    invalid_count = int(audit.invalid_residues.astype(bool).sum())
    high_risk = int((audit.sequence_liability_risk >= 40).sum())
    _check(checks, "Antibody alphabet and integrity", "fail" if invalid_count else "pass", f"{invalid_count}/{len(audit)} sequences contain unsupported residues")
    _check(checks, "Sequence developability liabilities", "review" if high_risk else "pass", f"{high_risk}/{len(audit)} candidates have sequence-liability risk ≥40")
    if pair_col or chain_col:
        pairing_key = pair_col or identifier
        pairing = frame.assign(_chain=(frame[chain_col].astype(str).str.lower() if chain_col else audit.inferred_chain)).groupby(pairing_key, dropna=False)["_chain"].agg(lambda values: sorted(set(values))).reset_index(name="chains")
        pairing["heavy_present"] = pairing.chains.apply(lambda values: any("heavy" in value or value in {"h", "hc"} for value in values))
        pairing["light_present"] = pairing.chains.apply(lambda values: any("light" in value or value in {"l", "lc", "kappa", "lambda"} for value in values))
        pairing["paired"] = pairing.heavy_present & pairing.light_present
        tables["antibody_chain_pairing_audit"] = pairing
        _check(checks, "Heavy/light chain pairing", "review" if (~pairing.paired).any() else "pass", f"{int(pairing.paired.sum())}/{len(pairing)} pairs contain heavy and light evidence")
    else:
        _check(checks, "Heavy/light chain pairing", "review", "No chain or pair identifiers supplied")
    _metric(metrics, "antibody_candidates_audited", len(audit), "candidates")


def _vaccine(frame: pd.DataFrame, metadata: Mapping[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    peptide_col = _column(frame, "peptide", "epitope", "sequence")
    hla_col = _column(frame, "hla", "allele", "mhc_allele")
    rank_col = _column(frame, "percentile_rank", "rank", "el_rank")
    affinity_col = _column(frame, "affinity_nm", "ic50", "binding_affinity")
    conservancy_col = _column(frame, "conservancy", "coverage_fraction")
    allergen_col = _column(frame, "allergen", "is_allergen")
    toxin_col = _column(frame, "toxin", "is_toxin")
    frequency_col = _column(frame, "population_frequency", "allele_frequency", "hla_frequency")
    host_similarity_col = _column(frame, "host_similarity", "human_identity", "self_similarity")
    if not peptide_col:
        _check(checks, "Vaccine peptide evidence", "fail", "Peptide sequence column is required")
        return
    work = frame.copy()
    work["peptide_clean"] = work[peptide_col].map(lambda value: _sequence(value, _AA))
    work["peptide_length"] = work.peptide_clean.str.len()
    if rank_col:
        work["binding_rank_numeric"] = pd.to_numeric(work[rank_col], errors="coerce")
    else:
        work["binding_rank_numeric"] = np.nan
    if affinity_col:
        work["affinity_nm_numeric"] = pd.to_numeric(work[affinity_col], errors="coerce")
    else:
        work["affinity_nm_numeric"] = np.nan
    work["strong_binder"] = work.binding_rank_numeric.le(0.5) | work.affinity_nm_numeric.le(50)
    work["weak_or_better_binder"] = work.binding_rank_numeric.le(2.0) | work.affinity_nm_numeric.le(500)
    work["allergen_flag"] = work[allergen_col].map(parse_scientific_bool) if allergen_col else False
    work["toxin_flag"] = work[toxin_col].map(parse_scientific_bool) if toxin_col else False
    if conservancy_col:
        work["conservancy_numeric"] = pd.to_numeric(work[conservancy_col], errors="coerce").clip(0, 1)
    else:
        work["conservancy_numeric"] = np.nan
    if host_similarity_col:
        work["host_similarity_numeric"] = pd.to_numeric(work[host_similarity_col], errors="coerce").clip(0, 1)
    else:
        host_reference = {_sequence(value, _AA) for value in metadata.get("host_reference_peptides", [])}
        work["host_similarity_numeric"] = work.peptide_clean.map(lambda peptide: 1.0 if peptide in host_reference and peptide else 0.0)
    frequency_map = metadata.get("hla_frequencies", {})
    if frequency_col:
        work["hla_frequency"] = pd.to_numeric(work[frequency_col], errors="coerce").clip(0, 1)
    elif isinstance(frequency_map, Mapping) and hla_col:
        work["hla_frequency"] = work[hla_col].astype(str).map({str(key): float(value) for key, value in frequency_map.items()}).clip(0, 1)
    else:
        work["hla_frequency"] = np.nan
    work["safety_pass"] = ~(work.allergen_flag | work.toxin_flag | work.host_similarity_numeric.ge(0.8))
    work["candidate_score"] = (
        35 * work.strong_binder.astype(float)
        + 15 * work.weak_or_better_binder.astype(float)
        + 25 * work.conservancy_numeric.fillna(0.5)
        + 15 * work.hla_frequency.fillna(0.0)
        + 10 * work.safety_pass.astype(float)
    ).clip(0, 100)
    tables["vaccine_candidate_prioritization"] = work
    unsafe = int((~work.safety_pass).sum())
    _check(checks, "Vaccine safety flags", "fail" if unsafe else "pass", f"{unsafe}/{len(work)} candidates have allergen, toxin or high host-similarity flags")
    if hla_col:
        allele_summary = work.groupby(hla_col, dropna=False).agg(candidates=(peptide_col, "count"), strong_binders=("strong_binder", "sum"), safe_candidates=("safety_pass", "sum"), maximum_frequency=("hla_frequency", "max")).reset_index()
        tables["hla_coverage_summary"] = allele_summary
        frequencies = allele_summary.loc[allele_summary.strong_binders.gt(0), "maximum_frequency"].dropna().clip(0, 1)
        estimated_coverage = float(1 - np.prod(1 - frequencies)) if len(frequencies) else np.nan
        _metric(metrics, "estimated_hla_population_coverage", estimated_coverage, "fraction")
        _check(checks, "HLA population-frequency evidence", "pass" if frequencies.notna().any() else "review", f"Frequency evidence available for {int(frequencies.notna().sum())} binding alleles")
    else:
        _check(checks, "HLA allele coverage", "review", "HLA allele column not supplied")
    _metric(metrics, "safe_strong_binders", int((work.safety_pass & work.strong_binder).sum()), "peptides")


def _pharmacogenomics(frame: pd.DataFrame, metadata: Mapping[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    gene = _column(frame, "gene", "pharmacogene")
    sample = _column(frame, "sample_id", "sample", "subject")
    variant = _column(frame, "variant_id", "variant", "rsid")
    genotype = _column(frame, "genotype", "gt")
    diplotype = _column(frame, "diplotype", "star_alleles", "star_allele")
    phenotype = _column(frame, "metabolizer_status", "phenotype_call", "predicted_phenotype")
    cn = _column(frame, "copy_number", "cn", "gene_copy_number")
    phase = _column(frame, "phased", "phase_status", "haplotype_phased")
    guideline = _column(frame, "guideline_version", "cpic_version", "dpwg_version")
    genome_build = _column(frame, "genome_build", "build", "assembly")
    fields = {"gene": gene, "sample": sample, "variant": variant, "genotype": genotype, "diplotype": diplotype, "phenotype": phenotype, "copy_number": cn, "phase": phase, "guideline": guideline, "genome_build": genome_build}
    rows = []
    for label, column in fields.items():
        present = bool(column)
        completeness = float(frame[column].notna().mean()) if column else 0.0
        rows.append({"evidence_field": label, "column": column or "", "present": present, "completeness": completeness})
    audit = pd.DataFrame(rows)
    tables["pharmacogenomics_evidence_completeness"] = audit
    required_present = all(fields[key] for key in ("sample", "variant", "genotype", "genome_build"))
    _check(checks, "Core PGx variant evidence", "pass" if required_present else "fail", f"Core fields present={required_present}")
    _check(checks, "Star-allele/diplotype evidence", "pass" if diplotype else "review", diplotype or "Not supplied; variant genotypes alone do not establish a star-allele diplotype")
    _check(checks, "Copy-number evidence", "pass" if cn else "review", cn or "Not supplied; required for complex pharmacogenes such as CYP2D6")
    if phase:
        phased_fraction = float(frame[phase].map(parse_scientific_bool).mean())
        _check(checks, "Read-backed/phased evidence", "pass" if phased_fraction >= 0.95 else "review", f"{phased_fraction:.1%} rows marked phased")
    else:
        _check(checks, "Read-backed/phased evidence", "review", "Phase status not supplied")
    if guideline:
        versions = sorted(frame[guideline].dropna().astype(str).unique())
        _check(checks, "Guideline version pinning", "pass" if versions else "review", ", ".join(versions[:5]) or "No guideline release supplied")
    else:
        _check(checks, "Guideline version pinning", "review", "No CPIC/DPWG guideline release supplied")
    if diplotype and phenotype:
        consistency = frame[[diplotype, phenotype]].dropna().copy()
        consistency["call_pair"] = consistency[diplotype].astype(str) + " → " + consistency[phenotype].astype(str)
        pair_counts = consistency.call_pair.value_counts().rename_axis("diplotype_phenotype_pair").reset_index(name="records")
        tables["diplotype_phenotype_consistency"] = pair_counts
    _metric(metrics, "pgx_evidence_fields_present", int(audit.present.sum()), "of 10")


def _structural_variant(frame: pd.DataFrame, metadata: Mapping[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    variant = _column(frame, "variant_id", "sv_id", "id")
    chrom = _column(frame, "chrom", "chromosome")
    start = _column(frame, "start", "pos", "position", "breakpoint_1")
    end = _column(frame, "end", "stop", "breakpoint_2")
    svtype = _column(frame, "svtype", "sv_type", "type")
    split = _column(frame, "split_reads", "split_read_support", "sr")
    pair = _column(frame, "paired_reads", "discordant_pairs", "pe")
    depth = _column(frame, "depth_support", "read_depth_support", "rd")
    caller = _column(frame, "caller", "calling_tool")
    sample = _column(frame, "sample_id", "sample")
    repeat_count = _column(frame, "repeat_count", "allele_repeat_count", "repeat_size")
    repeat_threshold = _column(frame, "pathogenic_threshold", "repeat_threshold")
    if not (variant or (chrom and start)):
        _check(checks, "Structural-variant evidence", "review", "Provide variant IDs or breakpoint coordinates for read-support audit")
        return
    columns = [column for column in (variant, sample, chrom, start, end, svtype, split, pair, depth, caller, repeat_count, repeat_threshold) if column]
    audit = frame[columns].copy()
    support_cols = []
    for name, column in (("split_read_support", split), ("paired_read_support", pair), ("depth_support", depth)):
        if column:
            audit[name] = pd.to_numeric(audit[column], errors="coerce")
            support_cols.append(name)
    if support_cols:
        audit["total_read_support"] = audit[support_cols].fillna(0).sum(axis=1)
        audit["support_tier"] = pd.cut(audit.total_read_support, [-np.inf, 2, 5, 10, np.inf], labels=["insufficient", "low", "moderate", "strong"])
        insufficient = int(audit.total_read_support.lt(float(metadata.get("minimum_sv_read_support", 5))).sum())
        _check(checks, "Read-backed breakpoint evidence", "review" if insufficient else "pass", f"{insufficient}/{len(audit)} records below minimum support")
    else:
        audit["total_read_support"] = np.nan
        audit["support_tier"] = "not supplied"
        _check(checks, "Read-backed breakpoint evidence", "review", "No split-read, paired-read or depth-support columns supplied")
    if caller:
        consensus_keys = [column for column in (sample, variant, chrom, start, end) if column]
        consensus = audit.groupby(consensus_keys, dropna=False)[caller].nunique().rename("independent_callers").reset_index()
        tables["structural_variant_caller_consensus"] = consensus
        _check(checks, "Independent caller consensus", "pass" if (consensus.independent_callers >= 2).any() else "review", f"{int((consensus.independent_callers>=2).sum())}/{len(consensus)} variants supported by ≥2 callers")
    else:
        _check(checks, "Independent caller consensus", "review", "Caller provenance not supplied")
    if repeat_count:
        audit["repeat_count_numeric"] = pd.to_numeric(audit[repeat_count], errors="coerce")
        if repeat_threshold:
            audit["repeat_threshold_numeric"] = pd.to_numeric(audit[repeat_threshold], errors="coerce")
            audit["above_pathogenic_threshold"] = audit.repeat_count_numeric >= audit.repeat_threshold_numeric
        else:
            audit["above_pathogenic_threshold"] = pd.NA
            _check(checks, "Repeat catalogue threshold", "review", "Repeat pathogenic threshold not supplied")
    tables["structural_variant_evidence_audit"] = audit
    _metric(metrics, "sv_records_audited", len(audit), "records")


def _gene_therapy(frame: pd.DataFrame, metadata: Mapping[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    identifier = _column(frame, "construct_id", "vector_id", "candidate_id", "id")
    sequence_col = _column(frame, "dna_sequence", "sequence", "payload_sequence")
    serotype = _column(frame, "serotype", "capsid")
    nab = _column(frame, "neutralizing_antibody_rate", "preexisting_immunity", "nab_rate")
    integration = _column(frame, "integration_risk", "integration_score")
    if not sequence_col:
        _check(checks, "Vector sequence evidence", "fail", "DNA payload/vector sequence is required")
        return
    packaging_limits = {"AAV": 4700, "LENTI": 9000, "LV": 9000, "ADENO": 36000}
    rows = []
    for index, row in frame.iterrows():
        raw = re.sub(r"\s+", "", str(row[sequence_col] or "").upper())
        sequence = _sequence(raw, _DNA)
        label = str(row[serotype]).upper() if serotype else str(metadata.get("vector_type", "AAV")).upper()
        vector_family = next((key for key in packaging_limits if key in label), "AAV")
        limit = int(metadata.get("packaging_limit_bp", packaging_limits[vector_family]))
        length = len(sequence)
        gc = (sequence.count("G") + sequence.count("C")) / max(length, 1)
        cpg = sum(1 for position in range(max(0, length - 1)) if sequence[position:position + 2] == "CG")
        longest_homopolymer = max((len(match.group(0)) for match in re.finditer(r"A+|C+|G+|T+", sequence)), default=0)
        restriction_hits = {motif: sequence.count(motif) for motif in metadata.get("restricted_motifs", ["GAATTC", "AAGCTT", "GGATCC"])}
        nab_value = float(pd.to_numeric(pd.Series([row[nab] if nab else np.nan]), errors="coerce").iloc[0]) if nab else np.nan
        integration_value = str(row[integration]).lower() if integration else "not supplied"
        risk = (
            (35 if length > limit else 15 if length > 0.95 * limit else 0)
            + (15 if gc < 0.30 or gc > 0.70 else 0)
            + (15 if cpg / max(length / 1000, 1e-9) > 20 else 0)
            + (15 if longest_homopolymer >= 10 else 0)
            + (10 if sum(restriction_hits.values()) else 0)
            + (10 if pd.notna(nab_value) and nab_value > 0.2 else 0)
        )
        rows.append({
            "construct_id": str(row[identifier]) if identifier else str(index),
            "vector_family": vector_family,
            "sequence_length_bp": length,
            "packaging_limit_bp": limit,
            "packaging_margin_bp": limit - length,
            "within_packaging_limit": length <= limit,
            "gc_fraction": gc,
            "cpg_per_kb": cpg / max(length / 1000, 1e-9),
            "longest_homopolymer": longest_homopolymer,
            "restricted_motif_hits": sum(restriction_hits.values()),
            "neutralizing_antibody_rate": nab_value,
            "declared_integration_risk": integration_value,
            "vector_sequence_risk": min(100, risk),
            "sequence_sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
        })
    audit = pd.DataFrame(rows)
    tables["gene_therapy_vector_risk_audit"] = audit
    over_capacity = int((~audit.within_packaging_limit).sum())
    _check(checks, "Vector packaging capacity", "fail" if over_capacity else "pass", f"{over_capacity}/{len(audit)} constructs exceed declared vector capacity")
    high_risk = int((audit.vector_sequence_risk >= 40).sum())
    _check(checks, "Vector sequence and immunity risk", "review" if high_risk else "pass", f"{high_risk}/{len(audit)} constructs have risk ≥40")
    _metric(metrics, "vector_constructs_audited", len(audit), "constructs")


def _cell_therapy(frame: pd.DataFrame, metadata: Mapping[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    identifier = _column(frame, "construct_id", "candidate_id", "id")
    antigen = _column(frame, "antigen", "target")
    healthy = _column(frame, "healthy_tissue_expression", "normal_tissue_expression", "off_tumor_expression")
    killing = _column(frame, "killing_percent", "cytotoxicity", "target_killing")
    cytokine = _column(frame, "cytokine_release", "crs_score", "cytokine_score")
    exhaustion = _column(frame, "exhaustion_score", "exhaustion", "dysfunction_score")
    persistence = _column(frame, "persistence_score", "persistence")
    if not identifier:
        identifier = frame.index.name if frame.index.name in frame.columns else None
    work = frame.copy()
    for output, column in (("healthy_expression", healthy), ("killing", killing), ("cytokine", cytokine), ("exhaustion", exhaustion), ("persistence", persistence)):
        work[output] = pd.to_numeric(work[column], errors="coerce") if column else np.nan
    if work.killing.dropna().median() > 1:
        work.killing = work.killing / 100.0
    thresholds = {
        "max_healthy_expression": float(metadata.get("max_healthy_tissue_expression", 0.05)),
        "min_killing": float(metadata.get("minimum_killing_fraction", 0.70)),
        "max_cytokine": float(metadata.get("maximum_cytokine_score", 0.30)),
        "max_exhaustion": float(metadata.get("maximum_exhaustion_score", 0.30)),
    }
    work["off_tumour_pass"] = work.healthy_expression.le(thresholds["max_healthy_expression"])
    work["potency_pass"] = work.killing.ge(thresholds["min_killing"])
    work["cytokine_pass"] = work.cytokine.le(thresholds["max_cytokine"])
    work["exhaustion_pass"] = work.exhaustion.le(thresholds["max_exhaustion"])
    work["overall_preclinical_gate"] = work[["off_tumour_pass", "potency_pass", "cytokine_pass", "exhaustion_pass"]].fillna(False).all(axis=1)
    work["benefit_risk_score"] = (
        35 * work.killing.fillna(0).clip(0, 1)
        + 20 * (1 - work.healthy_expression.fillna(1).clip(0, 1))
        + 15 * (1 - work.cytokine.fillna(1).clip(0, 1))
        + 15 * (1 - work.exhaustion.fillna(1).clip(0, 1))
        + 15 * work.persistence.fillna(0.5).clip(0, 1)
    ).clip(0, 100)
    keep = [column for column in (identifier, antigen) if column] + ["healthy_expression", "killing", "cytokine", "exhaustion", "persistence", "off_tumour_pass", "potency_pass", "cytokine_pass", "exhaustion_pass", "overall_preclinical_gate", "benefit_risk_score"]
    tables["cell_therapy_benefit_risk_audit"] = work[keep]
    failed = int((~work.overall_preclinical_gate).sum())
    _check(checks, "CAR-T preclinical benefit-risk gate", "review" if failed else "pass", f"{failed}/{len(work)} constructs fail one or more configurable preclinical gates")
    _check(checks, "Healthy-tissue expression evidence", "pass" if healthy else "review", healthy or "No healthy-tissue expression field supplied")
    _metric(metrics, "cell_therapy_candidates_passing_gate", int(work.overall_preclinical_gate.sum()), "constructs")


def _structural_chemistry(frame: pd.DataFrame, metadata: Mapping[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    compound = _column(frame, "compound", "ligand", "candidate", "compound_id")
    pose = _column(frame, "pose_id", "pose", "rank")
    score = _column(frame, "docking_score", "binding_score", "vina_score")
    rmsd = _column(frame, "rmsd", "pose_rmsd", "redocking_rmsd")
    strain = _column(frame, "strain_energy", "ligand_strain", "strain")
    replicate = _column(frame, "replicate", "run", "seed")
    time = _column(frame, "time", "time_ns", "frame_time")
    energy = _column(frame, "potential_energy", "energy", "total_energy")
    if score and compound:
        work = frame[[column for column in (compound, pose, score, rmsd, strain, replicate) if column]].copy()
        work["score_numeric"] = pd.to_numeric(work[score], errors="coerce")
        work["rmsd_numeric"] = pd.to_numeric(work[rmsd], errors="coerce") if rmsd else np.nan
        work["strain_numeric"] = pd.to_numeric(work[strain], errors="coerce") if strain else np.nan
        grouped = work.groupby(compound, dropna=False).agg(
            poses=(score, "count"),
            best_docking_score=("score_numeric", "min"),
            median_docking_score=("score_numeric", "median"),
            docking_score_sd=("score_numeric", "std"),
            median_rmsd=("rmsd_numeric", "median"),
            median_strain=("strain_numeric", "median"),
        ).reset_index()
        grouped["pose_reproducibility_pass"] = grouped.poses.ge(2) & grouped.docking_score_sd.fillna(np.inf).le(float(metadata.get("maximum_pose_score_sd", 1.5)))
        grouped["redocking_pass"] = grouped.median_rmsd.le(float(metadata.get("maximum_redocking_rmsd", 2.0)))
        grouped["strain_pass"] = grouped.median_strain.le(float(metadata.get("maximum_strain_energy", 8.0)))
        grouped["consensus_pose_gate"] = grouped[["pose_reproducibility_pass", "redocking_pass", "strain_pass"]].fillna(False).all(axis=1)
        tables["docking_pose_consensus_audit"] = grouped
        _check(checks, "Docking pose consensus", "review" if (~grouped.consensus_pose_gate).any() else "pass", f"{int(grouped.consensus_pose_gate.sum())}/{len(grouped)} compounds pass pose consistency, redocking and strain gates")
    if time and (rmsd or energy):
        trajectory = frame[[column for column in (compound, replicate, time, rmsd, energy) if column]].copy()
        trajectory["time_numeric"] = pd.to_numeric(trajectory[time], errors="coerce")
        if rmsd:
            trajectory["rmsd_numeric"] = pd.to_numeric(trajectory[rmsd], errors="coerce")
        if energy:
            trajectory["energy_numeric"] = pd.to_numeric(trajectory[energy], errors="coerce")
        keys = [column for column in (compound, replicate) if column]
        if not keys:
            keys = [lambda _: "trajectory"]
        rows = []
        grouped_iterator = trajectory.groupby([column for column in (compound, replicate) if column], dropna=False) if any((compound, replicate)) else [("trajectory", trajectory)]
        for key, subset in grouped_iterator:
            subset = subset.sort_values("time_numeric")
            tail = subset.iloc[max(0, len(subset) // 2):]
            record = {"trajectory": str(key), "frames": len(subset), "time_span": float(subset.time_numeric.max() - subset.time_numeric.min()) if len(subset) else np.nan}
            if rmsd and len(tail) >= 3:
                slope = np.polyfit(tail.time_numeric, tail.rmsd_numeric, 1)[0]
                record.update({"tail_rmsd_mean": tail.rmsd_numeric.mean(), "tail_rmsd_sd": tail.rmsd_numeric.std(ddof=1), "tail_rmsd_slope": slope, "rmsd_converged": abs(slope) <= float(metadata.get("maximum_rmsd_slope", 0.02))})
            if energy and len(tail) >= 3:
                slope = np.polyfit(tail.time_numeric, tail.energy_numeric, 1)[0]
                record.update({"tail_energy_mean": tail.energy_numeric.mean(), "tail_energy_sd": tail.energy_numeric.std(ddof=1), "tail_energy_slope": slope, "energy_converged": abs(slope) <= float(metadata.get("maximum_energy_slope", 0.1))})
            rows.append(record)
        convergence = pd.DataFrame(rows)
        tables["molecular_dynamics_convergence_audit"] = convergence
        pass_columns = [column for column in ("rmsd_converged", "energy_converged") if column in convergence]
        if pass_columns:
            converged = convergence[pass_columns].fillna(False).all(axis=1)
            _check(checks, "Molecular-dynamics convergence", "review" if (~converged).any() else "pass", f"{int(converged.sum())}/{len(convergence)} trajectories meet tail-stability gates")
    else:
        _check(checks, "Molecular-dynamics convergence", "review", "Trajectory time with RMSD/energy not supplied")


def apply_step156_translational(
    *,
    module_key: str,
    family: str,
    frame: pd.DataFrame,
    metadata: dict[str, Any],
    tables: dict[str, pd.DataFrame],
    checks: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> None:
    if family == "antibody-engineering":
        _antibody(frame, metadata, tables, checks, metrics)
    elif family == "vaccine-design":
        _vaccine(frame, metadata, tables, checks, metrics)
    elif module_key == "pharmacogenomics":
        _pharmacogenomics(frame, metadata, tables, checks, metrics)
    elif module_key == "structural_variant_repeat":
        _structural_variant(frame, metadata, tables, checks, metrics)
    elif family == "gene-therapy":
        _gene_therapy(frame, metadata, tables, checks, metrics)
    elif family == "cell-therapy":
        _cell_therapy(frame, metadata, tables, checks, metrics)
    elif family == "structural-chemistry":
        _structural_chemistry(frame, metadata, tables, checks, metrics)


__all__ = ["apply_step156_translational"]
