from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.decomposition import PCA
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.preprocessing import RobustScaler

from .assessment import bh_fdr
from .native_workflows import MAX_FEATURES, _check, _column, _metric, _numeric
from .native_integrity import parse_scientific_bool

DNA = set("ACGTN")
AA = set("ACDEFGHIKLMNPQRSTVWYBXZJUO")
HYDROPHOBIC = set("AILMFWVY")
BASIC = set("KRH")
ACIDIC = set("DE")


def _sequence_columns(frame: pd.DataFrame) -> tuple[str | None, str | None]:
    return _column(frame, "candidate", "candidate_id", "guide_id", "peptide_id", "sequence_id", "id"), _column(
        frame, "sequence", "guide", "peptide", "protein_sequence", "dna_sequence"
    )


def _crispr(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    ident, seq_col = _sequence_columns(frame)
    if not seq_col:
        _check(checks, "Guide sequence schema", "fail", "A guide/sequence column is required")
        return {}, ["Provide guide identifiers, guide sequence, nuclease/PAM and genome-build metadata."]
    out = []
    off_col = _column(frame, "off_target_hits", "offtargets", "near_matches")
    var_col = _column(frame, "variant_overlap", "population_variant_overlap")
    pam_col = _column(frame, "pam", "pam_sequence")
    for i, row in frame.iterrows():
        seq = re.sub(r"\s+", "", str(row[seq_col]).upper())
        gc = 100.0 * sum(c in "GC" for c in seq) / max(len(seq), 1)
        max_hom = max((len(m.group(0)) for m in re.finditer(r"(A+|C+|G+|T+)", seq)), default=0)
        off = pd.to_numeric(pd.Series([row[off_col]]), errors="coerce").iloc[0] if off_col else np.nan
        var = parse_scientific_bool(row[var_col], default=False) if var_col else False
        pam = str(row[pam_col]) if pam_col else ""
        valid = bool(seq) and set(seq) <= DNA and 17 <= len(seq) <= 30
        risk = int(not valid) + int(gc < 30 or gc > 70) + int(max_hom >= 5) + int(pd.notna(off) and off > 0) + int(var)
        out.append({"candidate": row[ident] if ident else i, "sequence": seq, "length": len(seq), "gc_percent": gc, "max_homopolymer": max_hom, "pam": pam, "off_target_hits": off, "population_variant_overlap": var, "risk_flags": risk, "status": "review" if risk else "pass"})
    table = pd.DataFrame(out)
    _check(checks, "Guide validity", "pass" if table["status"].ne("review").all() else "review", f"{int((table.status=='review').sum())} guides require review")
    _check(checks, "Genome-wide off-target evidence", "pass" if off_col else "review", off_col or "No off-target count column")
    _check(checks, "Population-variant overlap", "pass" if var_col else "review", var_col or "No population-variant overlap column")
    _metric(metrics, "guides", len(table), "guides")
    _metric(metrics, "guides_flagged", int((table.status == "review").sum()), "guides")
    return {"guide_safety_screen": table}, [
        "Use a genome-build-pinned aligner supporting mismatches and bulges before experimental selection.",
        "Confirm specificity with orthogonal off-target assays and population-variant-aware review.",
    ]


def _antibody(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    ident, seq_col = _sequence_columns(frame)
    if not seq_col:
        _check(checks, "Antibody sequence schema", "fail", "An amino-acid sequence column is required")
        return {}, ["Provide chain-paired antibody sequences and numbering metadata."]
    rows = []
    for i, row in frame.iterrows():
        seq = re.sub(r"\s+", "", str(row[seq_col]).upper())
        invalid = sorted(set(seq) - AA)
        liabilities = sum(seq.count(m) for m in ("NG", "NS", "DG", "DP", "DD", "W", "M"))
        glyco = len(re.findall(r"N[^P][ST]", seq))
        hydro = sum(c in HYDROPHOBIC for c in seq) / max(len(seq), 1)
        charge = sum(c in BASIC for c in seq) - sum(c in ACIDIC for c in seq)
        cys = seq.count("C")
        flags = int(bool(invalid)) + int(len(seq) < 80 or len(seq) > 1500) + int(cys % 2 == 1) + int(hydro > 0.45) + int(liabilities >= 4)
        rows.append({"candidate": row[ident] if ident else i, "length": len(seq), "invalid_residues": ",".join(invalid), "cysteines": cys, "net_charge_proxy": charge, "hydrophobic_fraction": hydro, "liability_motifs": liabilities, "n_glycosylation_motifs": glyco, "risk_flags": flags})
    table = pd.DataFrame(rows)
    _check(checks, "Sequence validity", "pass" if table.invalid_residues.eq("").all() else "fail", f"{int(table.invalid_residues.ne('').sum())} invalid sequences")
    _check(checks, "Developability liability screen", "review" if table.risk_flags.gt(0).any() else "pass", f"{int(table.risk_flags.gt(0).sum())} candidates flagged")
    _check(checks, "ANARCI/IgBLAST numbering evidence", "pass" if metadata.get("numbering_release") else "review", metadata.get("numbering_release", "Not supplied"))
    _metric(metrics, "antibody_candidates", len(table), "candidates")
    return {"antibody_developability": table.sort_values(["risk_flags", "liability_motifs"])}, [
        "Confirm chain pairing, IMGT numbering, CDR boundaries and germline assignment with ANARCI/IgBLAST.",
        "Computational liability flags require expression, aggregation, affinity and manufacturability assays.",
    ]


def _vaccine(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    ident, seq_col = _sequence_columns(frame)
    if not seq_col:
        _check(checks, "Peptide schema", "fail", "A peptide sequence column is required")
        return {}, ["Provide peptide, HLA allele, binding score/rank and safety annotations."]
    rank_col = _column(frame, "percentile_rank", "rank", "binding_rank")
    affinity_col = _column(frame, "affinity_nm", "ic50", "binding_affinity")
    conserv_col = _column(frame, "conservancy", "conservation")
    allergen_col = _column(frame, "allergen", "allergen_flag")
    toxin_col = _column(frame, "toxin", "toxin_flag")
    allele_col = _column(frame, "hla", "allele", "hla_allele")
    rows = []
    for i, row in frame.iterrows():
        seq = re.sub(r"\s+", "", str(row[seq_col]).upper())
        rank = pd.to_numeric(pd.Series([row[rank_col]]), errors="coerce").iloc[0] if rank_col else np.nan
        affinity = pd.to_numeric(pd.Series([row[affinity_col]]), errors="coerce").iloc[0] if affinity_col else np.nan
        conserv = pd.to_numeric(pd.Series([row[conserv_col]]), errors="coerce").iloc[0] if conserv_col else np.nan
        allergen = parse_scientific_bool(row[allergen_col], default=False) if allergen_col else False
        toxin = parse_scientific_bool(row[toxin_col], default=False) if toxin_col else False
        binder = bool((pd.notna(rank) and rank <= 2.0) or (pd.notna(affinity) and affinity <= 500))
        safe = not allergen and not toxin
        rows.append({"peptide": row[ident] if ident else i, "sequence": seq, "length": len(seq), "allele": row[allele_col] if allele_col else "", "rank": rank, "affinity_nm": affinity, "conservancy": conserv, "predicted_binder": binder, "safety_pass": safe, "candidate": bool(binder and safe and 8 <= len(seq) <= 30)})
    table = pd.DataFrame(rows)
    _check(checks, "HLA binding evidence", "pass" if rank_col or affinity_col else "review", rank_col or affinity_col or "Not supplied")
    _check(checks, "Safety annotation", "pass" if allergen_col and toxin_col else "review", "Allergen/toxin annotations" if allergen_col and toxin_col else "Incomplete")
    _check(checks, "Population coverage inputs", "pass" if allele_col and metadata.get("allele_frequency_release") else "review", metadata.get("allele_frequency_release", "Allele-frequency release missing"))
    _metric(metrics, "candidate_epitopes", int(table.candidate.sum()), "peptides")
    return {"epitope_candidates": table.sort_values(["candidate", "rank"], ascending=[False, True])}, [
        "Pin predictor and allele-frequency releases and assess host similarity, allergenicity and toxicity.",
        "Predicted epitopes require experimental immunogenicity and safety validation.",
    ]


def _long_read(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    length_col = _column(frame, "read_length", "length", "aligned_length", "contig_length")
    q_col = _column(frame, "qscore", "mean_qscore", "quality")
    cov_col = _column(frame, "coverage", "depth")
    if not length_col:
        _check(checks, "Long-read schema", "fail", "A read/contig length column is required")
        return {}, ["Provide read/contig length, quality and alignment/coverage summaries."]
    lengths = pd.to_numeric(frame[length_col], errors="coerce").dropna().clip(lower=0).sort_values(ascending=False)
    total = float(lengths.sum())
    n50 = float(lengths.iloc[np.searchsorted(lengths.cumsum().to_numpy(), total / 2, side="left")]) if len(lengths) and total > 0 else np.nan
    table = pd.DataFrame({"metric": ["reads_or_contigs", "total_bases", "N50", "median_length", "max_length"], "value": [len(lengths), total, n50, float(lengths.median()) if len(lengths) else np.nan, float(lengths.max()) if len(lengths) else np.nan]})
    _check(checks, "Read/contig lengths", "pass" if len(lengths) >= 10 else "review", f"{len(lengths)} records")
    if q_col:
        q = pd.to_numeric(frame[q_col], errors="coerce")
        _check(checks, "Read quality", "pass" if q.median() >= 10 else "review", f"median Q={q.median():.2f}")
        _metric(metrics, "median_qscore", float(q.median()), "Q")
    else:
        _check(checks, "Read quality", "review", "Quality column not supplied")
    _check(checks, "Coverage evidence", "pass" if cov_col else "review", cov_col or "Not supplied")
    _metric(metrics, "n50", n50, "bases")
    return {"long_read_summary": table}, [
        "Run platform-appropriate basecalling, adapter removal, assembly/alignment, polishing and contamination checks.",
        "Confirm assembly completeness and consensus accuracy with independent references or orthogonal data.",
    ]


def _isoform(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    tid = _column(frame, "transcript_id", "isoform", "transcript")
    gene = _column(frame, "gene_id", "gene")
    support = _column(frame, "junction_support", "read_support", "supporting_reads")
    abundance = _column(frame, "abundance", "tpm", "counts")
    full = _column(frame, "full_length", "is_full_length")
    novelty = _column(frame, "novelty", "class_code", "classification")
    if not tid:
        _check(checks, "Isoform schema", "fail", "Transcript/isoform identifier is required")
        return {}, ["Provide transcript identifiers, gene, junction/read support and annotation class."]
    table = frame[[c for c in (tid, gene, support, abundance, full, novelty) if c]].copy()
    if support:
        table["support_value"] = pd.to_numeric(table[support], errors="coerce")
        low = table.support_value.fillna(0) < 3
        _check(checks, "Read/junction support", "review" if low.any() else "pass", f"{int(low.sum())} isoforms with support <3")
    else:
        _check(checks, "Read/junction support", "review", "Not supplied")
    _check(checks, "Full-length evidence", "pass" if full else "review", full or "Not supplied")
    _check(checks, "Annotation/novelty class", "pass" if novelty else "review", novelty or "Not supplied")
    _metric(metrics, "isoforms", int(frame[tid].nunique(dropna=True)), "isoforms")
    if gene:
        _metric(metrics, "genes", int(frame[gene].nunique(dropna=True)), "genes")
    return {"isoform_evidence": table.head(100_000)}, [
        "Confirm splice junctions with strand-aware alignments and a pinned transcript annotation release.",
        "Novel isoforms require replicate support and orthogonal confirmation.",
    ]


def _single_cell(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    cell = _column(frame, "cell_id", "barcode", "cell")
    sample = _column(frame, "sample", "sample_id", "donor")
    batch = _column(frame, "batch", "batch_id")
    genes = _numeric(frame, exclude=[c for c in (cell, sample, batch) if c])
    if not genes:
        _check(checks, "Expression matrix", "fail", "No numeric expression features detected")
        return {}, ["Provide cells-by-features counts with cell, sample/donor and batch metadata."]
    matrix = frame[genes].apply(pd.to_numeric, errors="coerce").fillna(0).clip(lower=0)
    lib = matrix.sum(axis=1)
    detected = (matrix > 0).sum(axis=1)
    mt_genes = [g for g in genes if str(g).upper().startswith(("MT-", "MT_"))]
    mt = matrix[mt_genes].sum(axis=1) / lib.replace(0, np.nan) if mt_genes else pd.Series(np.nan, index=frame.index)
    qc = pd.DataFrame({"cell": frame[cell].astype(str) if cell else frame.index.astype(str), "library_size": lib, "detected_features": detected, "mitochondrial_fraction": mt})
    low = (lib <= lib.quantile(0.01)) | (detected <= detected.quantile(0.01))
    high_mt = mt.gt(float(metadata.get("max_mito_fraction", 0.2))).fillna(False)
    qc["qc_flag"] = low | high_mt
    _check(checks, "Cell QC", "review" if qc.qc_flag.any() else "pass", f"{int(qc.qc_flag.sum())} cells flagged")
    _check(checks, "Donor/sample metadata", "pass" if sample else "review", sample or "Not supplied")
    _check(checks, "Batch metadata", "pass" if batch else "review", batch or "Not supplied")
    components = min(5, len(genes), max(1, len(frame) - 1))
    transformed = np.log1p(matrix)
    scores = PCA(n_components=components, random_state=153).fit_transform(RobustScaler().fit_transform(transformed)) if len(frame) > 1 else np.zeros((len(frame), 1))
    embedding = pd.DataFrame(scores, columns=[f"PC{i+1}" for i in range(scores.shape[1])])
    embedding.insert(0, "cell", qc.cell.values)
    _metric(metrics, "cells", len(frame), "cells")
    _metric(metrics, "features", len(genes), "features")
    return {"cell_qc": qc, "robust_embedding": embedding}, [
        "Use donor-aware pseudobulk or mixed models; cells are not independent biological replicates.",
        "Review ambient RNA, doublets, batch effects, annotation uncertainty and out-of-distribution cells.",
    ]


def _epigenomics(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    chrom = _column(frame, "chrom", "chromosome")
    start = _column(frame, "start", "peak_start")
    end = _column(frame, "end", "peak_end")
    rep = _column(frame, "replicate", "replicate_id", "sample")
    qcol = _column(frame, "q_value", "qvalue", "fdr")
    signal = _column(frame, "signal", "score", "fold_enrichment", "frip")
    if not (chrom and start and end):
        _check(checks, "Peak schema", "fail", "chrom/start/end columns are required")
        return {}, ["Provide peak coordinates, replicate identifiers and signal/FDR values."]
    table = frame[[c for c in (chrom, start, end, rep, qcol, signal) if c]].copy()
    table["start_numeric"] = pd.to_numeric(table[start], errors="coerce")
    table["end_numeric"] = pd.to_numeric(table[end], errors="coerce")
    table["width"] = table.end_numeric - table.start_numeric
    invalid = table.width.le(0) | table.start_numeric.lt(0)
    _check(checks, "Peak coordinates", "fail" if invalid.any() else "pass", f"{int(invalid.sum())} invalid intervals")
    if qcol:
        q = pd.to_numeric(table[qcol], errors="coerce")
        _check(checks, "Peak FDR", "pass" if (q <= 0.05).mean() >= 0.5 else "review", f"{float((q<=0.05).mean()):.1%} peaks q<=0.05")
    else:
        _check(checks, "Peak FDR", "review", "FDR/q-value not supplied")
    if rep:
        table["peak_key"] = table[chrom].astype(str) + ":" + (table.start_numeric // 100).astype("Int64").astype(str) + "-" + (table.end_numeric // 100).astype("Int64").astype(str)
        reproducibility = table.groupby("peak_key")[rep].nunique().rename("replicates").reset_index()
        fraction = float((reproducibility.replicates >= 2).mean()) if len(reproducibility) else 0.0
        _check(checks, "Replicate reproducibility", "pass" if fraction >= 0.5 else "review", f"{fraction:.1%} rounded peaks in >=2 replicates")
    else:
        reproducibility = pd.DataFrame()
        _check(checks, "Replicate reproducibility", "review", "Replicate column not supplied")
    _metric(metrics, "peaks", len(table), "peaks")
    return {"peak_qc": table.head(100_000), "replicate_reproducibility": reproducibility.head(100_000)}, [
        "Use matched controls, replicate-aware peak calling and IDR/differential-accessibility methods.",
        "Pin genome build, aligner, peak caller and annotation releases; validate key loci orthogonally.",
    ]


def _genomic_variant(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    module = str(metadata.get("module_key", ""))
    variant = _column(frame, "variant_id", "variant", "id", "rsid")
    sample = _column(frame, "sample_id", "sample", "subject")
    genotype = _column(frame, "genotype", "gt")
    rows = []
    sample_qc = pd.DataFrame()
    ancestry_pca = pd.DataFrame()
    relatedness_flags = pd.DataFrame()
    if variant and sample and genotype:
        for vid, subset in frame.groupby(variant, dropna=False):
            gt = subset[genotype].astype(str).str.replace("|", "/", regex=False)
            called = gt.isin(["0/0", "0/1", "1/0", "1/1", "0", "1", "2"])
            dosage = gt.map({"0/0": 0, "0/1": 1, "1/0": 1, "1/1": 2, "0": 0, "1": 1, "2": 2})
            maf = float(min(dosage.mean() / 2, 1 - dosage.mean() / 2)) if dosage.notna().any() else np.nan
            n0 = int(gt.isin(["0/0", "0"]).sum())
            n1 = int(gt.isin(["0/1", "1/0", "1"]).sum())
            n2 = int(gt.isin(["1/1", "2"]).sum())
            n_called = n0 + n1 + n2
            alt_freq = (n1 + 2 * n2) / max(2 * n_called, 1)
            expected = np.array([(1-alt_freq)**2, 2*alt_freq*(1-alt_freq), alt_freq**2]) * n_called
            observed = np.array([n0, n1, n2], dtype=float)
            hwe_p = float(stats.chisquare(observed, expected).pvalue) if n_called > 0 and (expected > 0).all() else np.nan
            rows.append({"variant_id": vid, "samples": len(subset), "call_rate": float(called.mean()), "maf": maf, "hwe_p": hwe_p, "heterozygotes": n1, "alt_homozygotes": n2})
        table = pd.DataFrame(rows)
        dosage_long = frame[[sample, variant, genotype]].copy()
        dosage_long["_dosage"] = dosage_long[genotype].astype(str).str.replace("|", "/", regex=False).map({"0/0": 0.0, "0/1": 1.0, "1/0": 1.0, "1/1": 2.0, "0": 0.0, "1": 1.0, "2": 2.0})
        dosage_matrix = dosage_long.pivot_table(index=sample, columns=variant, values="_dosage", aggfunc="first")
        if not dosage_matrix.empty:
            sample_qc = pd.DataFrame({
                "sample_id": dosage_matrix.index.astype(str),
                "call_rate": dosage_matrix.notna().mean(axis=1).to_numpy(),
                "heterozygosity_fraction": dosage_matrix.eq(1).sum(axis=1).div(dosage_matrix.notna().sum(axis=1).replace(0, np.nan)).to_numpy(),
            })
            _check(checks, "Sample call rate", "pass" if sample_qc.call_rate.median() >= 0.95 else "review", f"median={sample_qc.call_rate.median():.1%}")
            bounded_matrix = dosage_matrix.iloc[:2_000, :10_000].copy()
            variant_means = bounded_matrix.mean(axis=0)
            imputed = bounded_matrix.fillna(variant_means)
            allele_frequency = (imputed.mean(axis=0) / 2).clip(1e-6, 1 - 1e-6)
            scale = np.sqrt(2 * allele_frequency * (1 - allele_frequency)).replace(0, np.nan)
            standardized = (imputed - 2 * allele_frequency) / scale
            standardized = standardized.replace([np.inf, -np.inf], np.nan).fillna(0.0)
            components = min(5, len(standardized), standardized.shape[1])
            if components >= 2 and float(standardized.var(axis=0, ddof=0).sum()) > 0:
                pca = PCA(n_components=components, random_state=153)
                coordinates = pca.fit_transform(standardized)
                ancestry_pca = pd.DataFrame(coordinates, columns=[f"PC{i+1}" for i in range(components)])
                ancestry_pca.insert(0, "sample_id", standardized.index.astype(str))
                variance_ratio = np.nan_to_num(pca.explained_variance_ratio_, nan=0.0, posinf=0.0, neginf=0.0)
                for i, variance in enumerate(variance_ratio, start=1):
                    ancestry_pca[f"PC{i}_variance_fraction"] = float(variance)
                _metric(metrics, "pca_variance_pc1_pc2", float(variance_ratio[:2].sum()), "fraction")
            elif components >= 2:
                _check(checks, "Ancestry PCA", "review", "Genotype matrix has zero variance; PCA was not estimated")
            if len(standardized) >= 2:
                sample_vectors = standardized.to_numpy(dtype=float)
                centered = sample_vectors - sample_vectors.mean(axis=1, keepdims=True)
                norms = np.linalg.norm(centered, axis=1)
                denominator = np.outer(norms, norms)
                numerator = centered @ centered.T
                related_matrix = np.divide(
                    numerator,
                    denominator,
                    out=np.full_like(numerator, np.nan, dtype=float),
                    where=denominator > 0,
                )
            else:
                related_matrix = np.empty((0, 0))
            rel_rows = []
            for i in range(len(standardized)):
                for j in range(i + 1, len(standardized)):
                    similarity = float(related_matrix[i, j]) if related_matrix.size else np.nan
                    if np.isfinite(similarity) and similarity >= 0.80:
                        rel_rows.append({"sample_a": str(standardized.index[i]), "sample_b": str(standardized.index[j]), "genotype_correlation": similarity, "review_threshold": 0.80})
                    if len(rel_rows) >= 10_000:
                        break
                if len(rel_rows) >= 10_000:
                    break
            relatedness_flags = pd.DataFrame(rel_rows)
            _check(checks, "Relatedness screen", "review" if not relatedness_flags.empty else "pass", f"{len(relatedness_flags)} high-correlation sample pairs")
        _check(checks, "Variant call rate", "pass" if table.call_rate.median() >= 0.95 else "review", f"median={table.call_rate.median():.1%}")
        _metric(metrics, "variants", len(table), "variants")
        _metric(metrics, "samples", int(frame[sample].nunique()), "samples")
    else:
        table = frame.copy()
        _check(checks, "Genotype-level schema", "review", "Variant/sample/genotype triplet not detected; using summary-table checks")
    if module == "pharmacogenomics":
        star = _column(frame, "star_allele", "diplotype", "allele_call")
        cn = _column(frame, "copy_number", "cn")
        phased = _column(frame, "phased", "phase_status")
        _check(checks, "Star-allele/diplotype calls", "pass" if star else "review", star or "Not supplied")
        _check(checks, "Copy-number evidence", "pass" if cn else "review", cn or "Not supplied")
        _check(checks, "Phasing evidence", "pass" if phased else "review", phased or "Not supplied")
    elif module == "structural_variant_repeat":
        svtype = _column(frame, "svtype", "sv_type", "type")
        support = _column(frame, "read_support", "supporting_reads", "split_reads")
        size = _column(frame, "svlen", "length", "repeat_size")
        _check(checks, "SV/repeat type", "pass" if svtype else "review", svtype or "Not supplied")
        _check(checks, "Read-level support", "pass" if support else "review", support or "Not supplied")
        _check(checks, "Event length/repeat size", "pass" if size else "review", size or "Not supplied")
    elif module == "population_gwas":
        pcs = [_column(frame, f"PC{i}", f"pc{i}") for i in range(1, 4)]
        phenotype = _column(frame, "phenotype", "case_control", "outcome")
        pca_available = any(pcs) or not ancestry_pca.empty
        _check(checks, "Population-structure covariates", "pass" if pca_available else "review", "Supplied or computed ancestry PCs" if pca_available else "PC covariates absent")
        _check(checks, "Phenotype", "pass" if phenotype else "review", phenotype or "Not supplied")
    build = metadata.get("genome_build") or _column(frame, "genome_build", "build")
    _check(checks, "Genome-build provenance", "pass" if build else "review", str(build or "Not supplied"))
    return {
        "variant_qc": table.head(100_000),
        "sample_qc": sample_qc,
        "ancestry_pca": ancestry_pca,
        "relatedness_flags": relatedness_flags,
    }, [
        "Use ancestry-aware sample QC, relatedness checks and a specialist caller/association model for confirmatory analysis.",
        "Clinical interpretation requires pinned allele/guideline releases and qualified human review.",
    ]


def _pathology(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    slide = _column(frame, "slide_id", "image_id", "well_id", "image")
    patient = _column(frame, "patient_id", "subject_id", "donor")
    truth = _column(frame, "ground_truth", "label", "truth")
    pred = _column(frame, "prediction", "predicted_label")
    tile = _column(frame, "tile_id", "object_id", "cell_id")
    if not slide:
        _check(checks, "Image/slide schema", "fail", "slide_id/image_id is required")
        return {}, ["Provide slide/image IDs, patient IDs, object/tile IDs and prediction/ground-truth fields."]
    summary = frame.groupby(slide).agg(records=(slide, "size")).reset_index()
    if patient:
        pcount = frame.groupby(slide)[patient].nunique().rename("patients").reset_index()
        summary = summary.merge(pcount, on=slide, how="left")
        leakage = frame.groupby(patient)[slide].nunique().gt(1).sum()
        _check(checks, "Patient/slide grouping", "review" if leakage else "pass", f"{int(leakage)} patients span multiple slides")
    else:
        _check(checks, "Patient metadata", "review", "Patient/donor ID not supplied")
    perf = pd.DataFrame()
    if truth and pred:
        y = frame[truth].astype(str); p = frame[pred].astype(str)
        labels = sorted(set(y) | set(p))
        cm = confusion_matrix(y, p, labels=labels)
        perf = pd.DataFrame(cm, index=[f"true:{x}" for x in labels], columns=[f"pred:{x}" for x in labels]).reset_index(names="label")
        acc = accuracy_score(y, p)
        _check(checks, "Ground-truth performance", "pass" if acc >= 0.8 else "review", f"accuracy={acc:.3f}")
        _metric(metrics, "accuracy", acc, "fraction")
    else:
        _check(checks, "Ground-truth performance", "review", "Truth/prediction columns not both supplied")
    _check(checks, "Tile/object granularity", "pass" if tile else "review", tile or "Not supplied")
    _metric(metrics, "slides_or_images", int(frame[slide].nunique()), "images")
    return {"image_summary": summary, "confusion_matrix": perf}, [
        "Split train/validation/test by patient and site, not by tile, to prevent leakage.",
        "Validate stain/scanner normalization and segmentation against representative pathologist-reviewed ground truth.",
    ]


def _target_decoy(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], *, proteogenomics: bool):
    score = _column(frame, "score", "search_score", "hyperscore", "xcorr")
    decoy = _column(frame, "decoy", "is_decoy", "target_decoy")
    ident = _column(frame, "psm_id", "spectrum_id", "feature", "glycopeptide", "peptide")
    if not (score and decoy):
        _check(checks, "Target-decoy schema", "fail", "Score and decoy fields are required")
        return {}, ["Provide PSM-level score, target/decoy flag and spectrum/peptide identifiers."]
    work = frame.copy()
    work["_score"] = pd.to_numeric(work[score], errors="coerce")
    work["_decoy"] = work[decoy].astype(str).str.lower().isin({"1", "true", "decoy", "d"})
    work = work.sort_values("_score", ascending=False)
    work["cum_decoy"] = work._decoy.cumsum()
    work["cum_target"] = (~work._decoy).cumsum()
    work["estimated_fdr"] = work.cum_decoy / work.cum_target.clip(lower=1)
    work["q_value"] = work.estimated_fdr[::-1].cummin()[::-1]
    accepted = (~work._decoy) & work.q_value.le(0.01)
    _check(checks, "Target-decoy FDR", "pass" if accepted.any() else "review", f"{int(accepted.sum())} target PSMs at q<=0.01")
    if proteogenomics:
        variant = _column(frame, "variant_id", "variant", "mutation")
        tumor = _column(frame, "tumor_specific", "tumour_specific")
        hla = _column(frame, "hla_affinity", "affinity_nm", "binding_rank")
        _check(checks, "Variant provenance", "pass" if variant else "review", variant or "Not supplied")
        _check(checks, "Tumour specificity", "pass" if tumor else "review", tumor or "Not supplied")
        _check(checks, "HLA evidence", "pass" if hla else "review", hla or "Not supplied")
    else:
        site = _column(frame, "site_probability", "localization_probability", "site_confidence")
        glycan = _column(frame, "glycan", "glycan_composition")
        _check(checks, "Site localization", "pass" if site else "review", site or "Not supplied")
        _check(checks, "Glycan annotation", "pass" if glycan else "review", glycan or "Not supplied")
    _metric(metrics, "accepted_psms_q01", int(accepted.sum()), "PSMs")
    cols = [c for c in (ident, score, decoy) if c] + ["estimated_fdr", "q_value"]
    return {"psm_fdr": work[cols].head(100_000)}, [
        "Inspect accepted spectra manually and pin search-engine, database and modification settings.",
        "Spectrum-level evidence requires orthogonal peptide/site or immune-function confirmation.",
    ]


def _glycomics(frame, checks, metrics, metadata):
    return _target_decoy(frame, checks, metrics, proteogenomics=False)


def _proteogenomics(frame, checks, metrics, metadata):
    return _target_decoy(frame, checks, metrics, proteogenomics=True)


def _amr(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]):
    isolate = _column(frame, "isolate_id", "sample_id", "sample")
    gene = _column(frame, "amr_gene", "gene", "marker")
    prediction = _column(frame, "predicted_resistant", "genotype_call", "prediction")
    phenotype = _column(frame, "phenotype_resistant", "phenotype", "ast_result")
    drug = _column(frame, "drug", "antibiotic")
    if not (isolate and gene):
        _check(checks, "AMR schema", "fail", "isolate/sample and AMR gene/marker are required")
        return {}, ["Provide isolate-level AMR calls, database release and AST phenotype where available."]
    prevalence = frame.groupby(gene)[isolate].nunique().rename("isolates").reset_index()
    prevalence["prevalence"] = prevalence.isolates / max(frame[isolate].nunique(), 1)
    concordance = pd.DataFrame()
    if prediction and phenotype:
        y = frame[phenotype].astype(str).str.lower().isin({"1", "true", "r", "resistant"})
        p = frame[prediction].astype(str).str.lower().isin({"1", "true", "r", "resistant"})
        acc = accuracy_score(y, p)
        concordance = pd.DataFrame([{"n": len(frame), "concordance": acc, "discordant": int((y != p).sum())}])
        _check(checks, "Genotype-phenotype concordance", "pass" if acc >= 0.9 else "review", f"concordance={acc:.3f}")
        _metric(metrics, "genotype_phenotype_concordance", acc, "fraction")
    else:
        _check(checks, "AST phenotype linkage", "review", "Prediction and phenotype fields not both supplied")
    _check(checks, "Antibiotic context", "pass" if drug else "review", drug or "Not supplied")
    _check(checks, "AMR database release", "pass" if metadata.get("amr_database_release") else "review", metadata.get("amr_database_release", "Not supplied"))
    return {"amr_prevalence": prevalence.sort_values("prevalence", ascending=False), "phenotype_concordance": concordance}, [
        "Pin CARD/ResFinder/AMRFinderPlus-style database and software releases and inspect coverage/identity thresholds.",
        "Confirm clinically actionable resistance using approved culture and susceptibility workflows.",
    ]


def specialist_demo(family: str, rng: np.random.Generator) -> pd.DataFrame | None:
    if family == "crispr-safety":
        return pd.DataFrame({"guide_id": ["g1", "g2", "g3"], "guide": ["GAGTCCGAGCAGAAGAAGAANGG", "AAAAAAAAAAAAAAAAAAAA", "CGTACGTACGTACGTACGTA"], "pam": ["NGG", "NGG", "NGG"], "off_target_hits": [0, 3, 0], "variant_overlap": [False, False, True]})
    if family == "antibody-engineering":
        return pd.DataFrame({"candidate_id": ["Ab1", "Ab2"], "sequence": ["EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEWVSAISGSGGSTYYADSVKGRFTISRDNSKNTLYLQMNSLRAEDTAVYYCAK", "QVQLVQSGAEVKKPGSSVKVSCKASGGTFSNGWVRQAPGQGLEWMGWINTYTGEPTYAADFKR"]})
    if family == "vaccine-design":
        return pd.DataFrame({"peptide_id": ["p1", "p2", "p3"], "peptide": ["SLYNTVATL", "LLFGYPVYV", "AAAAAAAAA"], "hla": ["HLA-A*02:01"] * 3, "percentile_rank": [0.4, 1.5, 8.0], "affinity_nm": [45, 220, 5000], "conservancy": [0.95, 0.8, 0.3], "allergen": [False, False, False], "toxin": [False, False, False]})
    if family == "long-read":
        return pd.DataFrame({"read_id": [f"r{i}" for i in range(30)], "read_length": rng.integers(2_000, 30_000, 30), "qscore": rng.normal(14, 2, 30), "coverage": rng.normal(30, 5, 30)})
    if family == "isoform-analysis":
        return pd.DataFrame({"transcript_id": [f"tx{i}" for i in range(12)], "gene_id": [f"g{i//3}" for i in range(12)], "junction_support": [2, 5, 8] * 4, "abundance": rng.uniform(1, 20, 12), "full_length": [True, True, False] * 4, "novelty": ["known", "novel", "known"] * 4})
    if family == "single-cell":
        n = 60
        return pd.DataFrame({"cell_id": [f"c{i}" for i in range(n)], "sample_id": [f"D{i//20}" for i in range(n)], "batch": ["B1"] * 30 + ["B2"] * 30, "G1": rng.poisson(5, n), "G2": rng.poisson(8, n), "MT-CO1": rng.poisson(1, n), "G3": rng.poisson(3, n)})
    if family == "epigenomics":
        rows = []
        for rep in ("R1", "R2"):
            for i in range(30):
                rows.append({"chrom": "chr1", "start": i * 1000, "end": i * 1000 + 250, "replicate": rep, "q_value": 0.01 if i < 25 else 0.2, "signal": float(rng.normal(10, 2))})
        return pd.DataFrame(rows)
    if family == "genomic-variant":
        rows = []
        for variant in ("v1", "v2", "v3"):
            for i in range(36):
                rows.append({"variant_id": variant, "sample_id": f"S{i}", "genotype": "0/0" if i < 18 else ("0/1" if i < 30 else "1/1"), "PC1": rng.normal(), "phenotype": int(i >= 18), "genome_build": "GRCh38"})
        return pd.DataFrame(rows)
    if family == "pathology-ai":
        rows = []
        for slide in range(8):
            for tile in range(12):
                truth = "positive" if tile % 3 == 0 else "negative"
                rows.append({"slide_id": f"SL{slide}", "patient_id": f"P{slide}", "tile_id": f"T{tile}", "ground_truth": truth, "prediction": truth, "area": float(rng.normal(100, 10))})
        return pd.DataFrame(rows)
    if family in {"glycomics", "proteogenomics"}:
        n = 80
        data = {"psm_id": [f"psm{i}" for i in range(n)], "score": np.linspace(100, 1, n), "decoy": [i % 20 == 0 for i in range(n)]}
        if family == "glycomics":
            data.update({"glycan": ["HexNAc2Hex5"] * n, "site_probability": rng.uniform(0.8, 1.0, n)})
        else:
            data.update({"variant_id": [f"v{i%5}" for i in range(n)], "tumor_specific": [True] * n, "hla_affinity": rng.uniform(20, 500, n)})
        return pd.DataFrame(data)
    if family == "amr-analysis":
        return pd.DataFrame({"isolate_id": [f"I{i}" for i in range(30)], "amr_gene": ["blaTEM" if i % 2 else "mecA" for i in range(30)], "drug": ["AMP" if i % 2 else "OXA" for i in range(30)], "predicted_resistant": [True] * 30, "phenotype_resistant": [i % 10 != 0 for i in range(30)]})
    return None
