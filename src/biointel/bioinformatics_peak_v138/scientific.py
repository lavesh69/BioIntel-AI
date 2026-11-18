from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from .catalog import BioinformaticsPeakModule, MODULE_BY_KEY


@dataclass
class AnalysisBundle:
    result: pd.DataFrame
    summary: dict[str, Any]
    extras: dict[str, pd.DataFrame]
    quality: pd.DataFrame


def _seed(key: str) -> int:
    return int(sha256(key.encode("utf-8")).hexdigest()[:8], 16)


def _rng(key: str) -> np.random.Generator:
    return np.random.default_rng(_seed(key))


def _num(series: pd.Series, fill: float | None = None) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce")
    return out.fillna(fill) if fill is not None else out


def _safe_welch(a: pd.Series, b: pd.Series) -> float:
    aa = _num(a).replace([np.inf, -np.inf], np.nan).dropna().to_numpy(float)
    bb = _num(b).replace([np.inf, -np.inf], np.nan).dropna().to_numpy(float)
    if len(aa) < 2 or len(bb) < 2:
        return float("nan")
    return float(stats.ttest_ind(aa, bb, equal_var=False, nan_policy="omit").pvalue)


def _bh(values: pd.Series) -> pd.Series:
    p = _num(values).to_numpy(float)
    out = np.full(len(p), np.nan)
    valid = np.isfinite(p)
    if not valid.any():
        return pd.Series(out, index=values.index)
    pv = p[valid]
    order = np.argsort(pv)
    ranked = pv[order]
    adjusted = ranked * len(ranked) / np.arange(1, len(ranked) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    restored = np.empty_like(adjusted)
    restored[order] = np.clip(adjusted, 0, 1)
    out[np.where(valid)[0]] = restored
    return pd.Series(out, index=values.index)


def _entropy(values: pd.Series) -> float:
    arr = _num(values, 0).clip(lower=0).to_numpy(float)
    total = arr.sum()
    if total <= 0:
        return 0.0
    p = arr[arr > 0] / total
    return float(-(p * np.log(p)).sum())


def _zscore(series: pd.Series) -> pd.Series:
    values = _num(series)
    sd = float(values.std(ddof=0))
    if not np.isfinite(sd) or sd <= 0:
        return pd.Series(np.zeros(len(values)), index=series.index)
    return (values - values.mean()) / sd


def _rank01(series: pd.Series, *, ascending: bool = True) -> pd.Series:
    values = _num(series)
    if values.notna().sum() == 0:
        return pd.Series(np.zeros(len(values)), index=series.index)
    return values.rank(pct=True, ascending=ascending).fillna(0.0)


def _pca(frame: pd.DataFrame, n_components: int = 2) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=[f"PC{i+1}" for i in range(n_components)])
    matrix = frame.apply(pd.to_numeric, errors="coerce").fillna(frame.apply(pd.to_numeric, errors="coerce").mean()).fillna(0.0)
    matrix = matrix - matrix.mean(axis=0)
    scale = matrix.std(axis=0, ddof=0).replace(0, 1)
    matrix = matrix / scale
    try:
        u, s, _ = np.linalg.svd(matrix.to_numpy(float), full_matrices=False)
        coords = u[:, :n_components] * s[:n_components]
    except np.linalg.LinAlgError:
        coords = np.zeros((len(matrix), n_components))
    columns = [f"PC{i+1}" for i in range(n_components)]
    if coords.shape[1] < n_components:
        coords = np.pad(coords, ((0, 0), (0, n_components - coords.shape[1])))
    return pd.DataFrame(coords[:, :n_components], index=frame.index, columns=columns)


def validate_frame(data: pd.DataFrame, module: BioinformaticsPeakModule | str) -> dict[str, Any]:
    if isinstance(module, str):
        module = MODULE_BY_KEY[module]
    duplicate_columns = list(data.columns[data.columns.duplicated()].astype(str))
    missing_required = [column for column in module.required_columns if column not in data.columns]
    infinite_cells = 0
    constant_columns: list[str] = []
    for index, column in enumerate(data.columns):
        series = data.iloc[:, index]
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().any():
            infinite_cells += int(np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).sum())
        if series.nunique(dropna=True) <= 1:
            constant_columns.append(str(column))
    missing_cells = int(data.isna().sum().sum())
    duplicate_rows = int(data.duplicated().sum()) if not data.empty else 0
    warnings: list[str] = []
    if data.empty:
        warnings.append("No records are available.")
    if missing_required:
        warnings.append("Required fields are missing: " + ", ".join(missing_required))
    if duplicate_columns:
        warnings.append("Duplicate columns must be renamed before analysis.")
    if infinite_cells:
        warnings.append(f"{infinite_cells:,} infinite values will be converted to missing values.")
    if duplicate_rows:
        warnings.append(f"{duplicate_rows:,} duplicate rows were detected.")
    if len(data) > 250_000:
        warnings.append("Interactive analysis is bounded to 250,000 rows; use background execution for larger data.")
    return {
        "valid": not data.empty and not missing_required and not duplicate_columns,
        "rows": int(len(data)),
        "columns": int(len(data.columns)),
        "missing_required": missing_required,
        "duplicate_columns": duplicate_columns,
        "missing_cells": missing_cells,
        "infinite_cells": infinite_cells,
        "duplicate_rows": duplicate_rows,
        "constant_columns": constant_columns,
        "warnings": warnings,
    }


def _clean(data: pd.DataFrame, module: BioinformaticsPeakModule) -> pd.DataFrame:
    frame = data.copy()
    frame = frame.loc[:, ~frame.columns.duplicated()].copy()
    frame.replace([np.inf, -np.inf], np.nan, inplace=True)
    if len(frame) > 250_000:
        frame = frame.sample(250_000, random_state=_seed(module.key)).sort_index()
    for column in module.required_columns:
        if column not in frame.columns:
            frame[column] = np.nan
    return frame


def demo_frame(module: BioinformaticsPeakModule | str, n: int = 240) -> pd.DataFrame:
    if isinstance(module, str):
        module = MODULE_BY_KEY[module]
    rng = _rng(module.key)
    key = module.key

    if key == "population_gwas_peak":
        samples = [f"S{i+1:04d}" for i in range(max(48, n // 4))]
        phenotype = {sample: int(rng.binomial(1, 0.45)) for sample in samples}
        ancestry = {sample: rng.choice(["EUR", "SAS", "AFR"], p=[0.45, 0.35, 0.20]) for sample in samples}
        rows = []
        for i in range(max(60, n // 2)):
            maf = rng.uniform(0.03, 0.48)
            causal = i % 23 == 0
            for sample in samples:
                p = np.clip(maf + 0.10 * causal * phenotype[sample], 0.01, 0.49)
                rows.append({"sample": sample, "variant": f"rs{100000+i}", "chrom": str(1 + i % 12), "position": 100000 + i * 25000, "genotype": int(rng.binomial(2, p)), "phenotype": phenotype[sample], "ancestry": ancestry[sample], "age": rng.normal(52, 11), "sex": rng.choice(["F", "M"])})
        return pd.DataFrame(rows)

    if key == "epigenomics_peak":
        rows = []
        for sample_i in range(20):
            condition = "Treatment" if sample_i >= 10 else "Control"
            for region_i in range(max(60, n // 3)):
                shift = 1.0 if condition == "Treatment" and region_i % 17 == 0 else 0.0
                start = 100000 + region_i * 5000
                rows.append({"sample": f"EPI-{sample_i+1:03d}", "region": f"peak_{region_i+1:04d}", "condition": condition, "signal": max(0.0, rng.lognormal(2.0 + shift, 0.35)), "chrom": f"chr{1+region_i%8}", "start": start, "end": start + int(rng.integers(150, 1200)), "motif": rng.choice(["CTCF", "AP1", "GATA", "ETS", "None"]), "gene": f"GENE{1+region_i%40:03d}", "methylation": np.clip(rng.beta(2, 5) - 0.12 * shift, 0, 1)})
        return pd.DataFrame(rows)

    if key == "pharmacogenomics_peak":
        genes = ["CYP2D6", "CYP2C19", "CYP2C9", "SLCO1B1", "TPMT", "DPYD"]
        drugs = ["codeine", "clopidogrel", "warfarin", "simvastatin", "thiopurine", "fluoropyrimidine"]
        rows = []
        for sample_i in range(max(30, n // 5)):
            for idx, gene in enumerate(genes):
                allele = rng.choice(["*1", "*2", "*3", "*4", "*17"], p=[0.45, 0.2, 0.12, 0.13, 0.1])
                level = rng.choice(["High", "Moderate", "Low"], p=[0.35, 0.45, 0.2])
                rows.append({"sample": f"PGX-{sample_i+1:03d}", "gene": gene, "variant": f"{gene}:var{rng.integers(1,20)}", "drug": drugs[idx], "allele": allele, "evidence_level": level, "copy_number": int(rng.choice([1,2,2,2,3])), "population_frequency": rng.uniform(0.001, 0.45), "guideline_source": rng.choice(["CPIC-like reference", "DPWG-like reference", "Review needed"])})
        return pd.DataFrame(rows)

    if key in {"structural_variant_peak", "circular_dna_instability"}:
        event_types = ["DEL", "DUP", "INV", "BND", "STR", "MEI"] if key == "structural_variant_peak" else ["ecDNA", "circle", "MEI", "amplicon", "complex_rearrangement"]
        rows = []
        for i in range(n):
            start = int(rng.integers(10000, 150_000_000)); size = int(rng.lognormal(9.5, 1.4))
            row = {"sample": f"SV-{i%24+1:03d}", "event_id": f"EV-{i+1:05d}", "chrom": str(1+i%22), "start": start, "end": start+size, "event_type": rng.choice(event_types), "support": int(rng.integers(1, 80)), "quality": rng.uniform(5, 99), "gene": rng.choice(["MYC", "EGFR", "TP53", "BRCA1", "INTERGENIC"]), "allele_fraction": np.clip(rng.beta(2, 6), 0, 1), "copy_number": float(np.clip(rng.normal(3.0, 2.0), 0, 20)), "caller": rng.choice(["caller_a", "caller_b", "caller_c"])}
            rows.append(row)
        return pd.DataFrame(rows)

    if key == "rna_splicing_peak":
        rows = []
        events = ["exon_skip", "intron_retention", "alt_donor", "alt_acceptor", "mutually_exclusive"]
        for sample_i in range(24):
            group = "Case" if sample_i >= 12 else "Control"
            for event_i in range(max(45, n // 4)):
                base = rng.beta(4, 4)
                shift = 0.25 if group == "Case" and event_i % 13 == 0 else 0
                rows.append({"sample": f"RNA-{sample_i+1:03d}", "gene": f"GENE{1+event_i%30:03d}", "transcript": f"TX{1+event_i%30:03d}.{1+event_i%3}", "event": f"EVT{event_i+1:04d}:{rng.choice(events)}", "group": group, "psi": np.clip(base+shift+rng.normal(0,0.05),0,1), "junction_support": int(rng.integers(2,150)), "variant": rng.choice(["None", f"splice_var_{event_i%8}"])})
        return pd.DataFrame(rows)

    if key == "immune_repertoire":
        rows = []
        for sample_i in range(20):
            group = "Responder" if sample_i >= 10 else "Non-responder"
            for clone_i in range(max(40, n // 5)):
                count = int(rng.lognormal(2.0 + (1.0 if group == "Responder" and clone_i % 19 == 0 else 0), 0.8))
                rows.append({"sample": f"AIRR-{sample_i+1:03d}", "clonotype": f"CLONE-{clone_i+1:05d}", "chain": rng.choice(["TRA", "TRB", "IGH", "IGK"]), "v_gene": rng.choice(["TRBV5-1", "TRBV7-2", "IGHV3-23", "IGHV4-34"]), "j_gene": rng.choice(["TRBJ1-1", "TRBJ2-7", "IGHJ4", "IGHJ6"]), "cdr3": "C" + "A"*int(rng.integers(8,18)) + "F", "count": count, "group": group, "time": rng.choice([0,7,28])})
        return pd.DataFrame(rows)

    if key == "single_cell_multiome":
        rows = []
        modalities = ["RNA", "ATAC", "ADT"]
        features = {"RNA":["CD3D","MS4A1","LYZ","COL1A1"],"ATAC":["peak_CD3D","peak_MS4A1","peak_LYZ","peak_COL1A1"],"ADT":["CD3","CD19","CD14","CD90"]}
        for cell_i in range(max(120, n)):
            cluster = rng.choice(["T cell","B cell","Myeloid","Fibroblast"])
            sample = f"SC-{1+cell_i%8:02d}"; batch = rng.choice(["B1","B2"])
            for modality in modalities:
                for feature in features[modality]:
                    marker_match = cluster.split()[0].upper() in feature.upper() or (cluster=="Myeloid" and "LYZ" in feature)
                    value = max(0.0, rng.gamma(2.0 + 4.0*marker_match, 1.0))
                    rows.append({"cell": f"CELL-{cell_i+1:05d}", "sample": sample, "cluster": cluster, "modality": modality, "feature": feature, "value": value, "batch": batch})
        return pd.DataFrame(rows)

    if key == "proteogenomics_peak":
        rows = []
        for i in range(n):
            binding = np.clip(rng.beta(2, 5), 0, 1)
            rows.append({"sample": f"TUM-{i%18+1:03d}", "variant": f"chr{1+i%12}:{100000+i*113}:A>G", "gene": f"GENE{1+i%45:03d}", "peptide": "A" + "L"*(8+i%3), "hla": rng.choice(["HLA-A*02:01","HLA-A*03:01","HLA-B*07:02"]), "binding_score": binding, "expression": rng.lognormal(2.0,0.8), "ms_support": int(rng.binomial(1,0.28)), "clonality": np.clip(rng.beta(4,2),0,1), "normal_tissue_risk": np.clip(rng.beta(2,7),0,1)})
        return pd.DataFrame(rows)

    if key == "gene_regulatory_network":
        rows = []
        tfs = ["STAT1","GATA3","MYC","TP53","CEBPA","FOXP3"]
        for sample_i in range(18):
            condition = "Stimulated" if sample_i >= 9 else "Baseline"
            for edge_i in range(max(60, n // 3)):
                tf = tfs[edge_i%len(tfs)]; target = f"GENE{1+edge_i%50:03d}"
                shift = 0.35 if condition=="Stimulated" and tf in {"STAT1","MYC"} else 0
                rows.append({"sample": f"GRN-{sample_i+1:03d}", "condition": condition, "tf": tf, "target": target, "activity": rng.normal(0.2+shift,0.25), "evidence": np.clip(rng.beta(4,2),0,1), "expression": rng.lognormal(2.0+shift,0.4), "motif_score": np.clip(rng.beta(3,3),0,1)})
        return pd.DataFrame(rows)

    if key == "federated_genomic_discovery":
        rows = []
        sources = ["Local registry","Beacon-A","Phenopacket-B","Consortium-C"]
        for i in range(n):
            rows.append({"case_id": f"CASE-{i+1:05d}", "source": rng.choice(sources), "phenotype": rng.choice(["seizure","ataxia","cardiomyopathy","developmental delay"]), "gene": rng.choice(["SCN1A","CACNA1A","MYH7","MECP2","Unknown"]), "variant": f"var-{rng.integers(1,100)}", "phenotype_similarity": np.clip(rng.beta(5,2),0,1), "variant_match": np.clip(rng.beta(3,3),0,1), "access_status": rng.choice(["Open metadata","Controlled","Request required"], p=[0.35,0.45,0.2]), "consent_scope": rng.choice(["Disease-specific","Broad research","Unknown"])})
        return pd.DataFrame(rows)

    if key == "viral_within_host":
        rows = []
        for subject_i in range(18):
            lineage = rng.choice(["L1","L2","L3"])
            for time in [0,3,7,14,28]:
                for pos_i in range(max(15, n // 16)):
                    base = rng.beta(1.5,12)
                    slope = 0.025*time if pos_i%17==0 else 0
                    rows.append({"sample": f"V-{subject_i+1:03d}-T{time}", "subject": f"V-{subject_i+1:03d}", "time": time, "chrom": "viral_genome", "position": 100+pos_i*37, "ref": "A", "alt": rng.choice(["C","G","T"]), "frequency": np.clip(base+slope+rng.normal(0,0.01),0,1), "lineage": lineage, "depth": int(rng.integers(50,5000)), "recombination_flag": bool(rng.random()<0.03)})
        return pd.DataFrame(rows)

    if key == "genome_annotation":
        rows = []
        for i in range(n):
            start = 1000+i*5000; feature_type=rng.choice(["gene","mRNA","CDS","exon","ncRNA"])
            rows.append({"genome": rng.choice(["assembly_v1","assembly_v2"]), "feature_id": f"FEAT-{i+1:05d}", "chrom": f"chr{1+i%8}", "start": start, "end": start+int(rng.integers(150,10000)), "strand": rng.choice(["+","-"]), "feature_type": feature_type, "evidence": rng.choice(["protein","RNA","ab_initio","orthology"]), "ortholog_group": f"OG{1+i%70:04d}", "completeness": np.clip(rng.beta(5,2),0,1)})
        return pd.DataFrame(rows)

    if key == "environmental_edna":
        rows = []
        species = ["Species_A","Species_B","Species_C","Invasive_X","Pathogen_Y"]
        for sample_i in range(max(36,n//4)):
            site = f"SITE-{1+sample_i%9:02d}"; date = pd.Timestamp("2026-01-01") + pd.Timedelta(days=sample_i*7)
            control = "negative_control" if sample_i%18==0 else "sample"
            for sp in species:
                effect = 20 if sp=="Invasive_X" and site in {"SITE-07","SITE-08"} else 1
                reads = int(rng.poisson(8*effect if control=="sample" else 1))
                rows.append({"sample": f"EDNA-{sample_i+1:03d}", "site": site, "date": date, "species": sp, "reads": reads, "control_type": control, "reference_confidence": np.clip(rng.beta(5,2),0,1), "replicate": 1+sample_i%3})
        return pd.DataFrame(rows)

    if key == "comparative_regulatory_genomics":
        rows = []
        species = ["human","mouse","rat","macaque"]
        for region_i in range(max(70,n//3)):
            for sp in species:
                start=100000+region_i*2500
                rows.append({"species":sp,"region":f"REG-{region_i+1:04d}","ortholog_group":f"ROG-{region_i+1:04d}","motif":rng.choice(["CTCF","AP1","GATA","ETS"]),"conservation":np.clip(rng.normal(0.75 if sp in {"human","macaque"} else 0.6,0.15),0,1),"activity":max(0,rng.lognormal(1.2+(0.4 if region_i%19==0 and sp=="human" else 0),0.4)),"chrom":f"chr{1+region_i%6}","start":start,"end":start+int(rng.integers(200,1500)),"tissue":rng.choice(["brain","liver","blood"])} )
        return pd.DataFrame(rows)

    raise KeyError(key)


def analyse_module(data: pd.DataFrame, module: BioinformaticsPeakModule | str, threshold: float = 0.7, parameters: dict[str, Any] | None = None) -> AnalysisBundle:
    if isinstance(module, str):
        module = MODULE_BY_KEY[module]
    validation = validate_frame(data, module)
    if not validation["valid"]:
        raise ValueError("; ".join(validation["warnings"]) or "Input did not pass validation.")
    frame = _clean(data, module)
    key = module.key
    extras: dict[str, pd.DataFrame] = {}
    metrics: dict[str, Any] = {}

    if key == "population_gwas_peak":
        frame["genotype"] = _num(frame["genotype"])
        frame["phenotype"] = _num(frame["phenotype"])
        rows=[]
        for (variant, chrom, position), group in frame.groupby(["variant","chrom","position"], dropna=False):
            a=group.loc[group["phenotype"]<=0.5,"genotype"]; b=group.loc[group["phenotype"]>0.5,"genotype"]
            p=_safe_welch(a,b); beta=float(_num(b).mean()-_num(a).mean())
            rows.append({"variant":variant,"chrom":str(chrom),"position":float(position),"samples":group["sample"].nunique(),"call_rate":float(group["genotype"].notna().mean()),"maf":float(_num(group["genotype"]).mean()/2),"beta":beta,"p_value":p})
        result=pd.DataFrame(rows); result["q_value"]=_bh(result["p_value"]); result["minus_log10_p"]=-np.log10(result["p_value"].clip(lower=1e-300)); result["priority_score"]=_rank01(result["minus_log10_p"])*result["call_rate"].clip(0,1)
        geno=frame.pivot_table(index="sample",columns="variant",values="genotype",aggfunc="first")
        pcs=_pca(geno,2).reset_index().rename(columns={"index":"sample"}); meta=frame.groupby("sample",as_index=False).agg(phenotype=("phenotype","first"), ancestry=("ancestry","first") if "ancestry" in frame.columns else ("phenotype",lambda _:"Unknown")); pcs=pcs.merge(meta,on="sample",how="left")
        top=result.nlargest(min(25,len(result)),"priority_score")["variant"].tolist(); weights=result.set_index("variant")["beta"]
        prs=(geno.reindex(columns=top).mul(weights.reindex(top),axis=1).sum(axis=1,min_count=1)).rename("prs_score").reset_index(); prs=prs.merge(meta,on="sample",how="left")
        expected=np.arange(1,len(result)+1)/(len(result)+1); observed=np.sort(result["p_value"].fillna(1).clip(1e-300,1)); qq=pd.DataFrame({"expected":-np.log10(expected),"observed":-np.log10(observed)})
        extras.update({"ancestry_pca":pcs,"prs_scores":prs,"qq":qq,"genotype_matrix":geno.reset_index()})
        metrics={"variants":len(result),"samples":frame["sample"].nunique(),"fdr_hits":int((result["q_value"]<=0.05).sum()),"median_call_rate":float(result["call_rate"].median())}

    elif key == "epigenomics_peak":
        frame["signal"]=_num(frame["signal"]); groups=frame["condition"].astype(str).dropna().unique().tolist(); rows=[]
        for (region,chrom,start,end),g in frame.groupby(["region","chrom","start","end"],dropna=False):
            a=g.loc[g["condition"].astype(str)==groups[0],"signal"] if groups else pd.Series(dtype=float); b=g.loc[g["condition"].astype(str)==groups[-1],"signal"] if len(groups)>1 else pd.Series(dtype=float)
            rows.append({"region":region,"chrom":chrom,"start":start,"end":end,"gene":g.get("gene",pd.Series(["Unknown"])).iloc[0],"motif":g.get("motif",pd.Series(["None"])).iloc[0],"mean_signal":float(g["signal"].mean()),"log2_fold_change":float(np.log2((_num(b).mean()+1e-6)/(_num(a).mean()+1e-6))) if len(groups)>1 else 0.0,"p_value":_safe_welch(a,b),"methylation":float(_num(g.get("methylation",pd.Series(np.nan,index=g.index))).mean())})
        result=pd.DataFrame(rows); result["q_value"]=_bh(result["p_value"]); result["minus_log10_q"]=-np.log10(result["q_value"].clip(lower=1e-300)); result["priority_score"]=_rank01(result["log2_fold_change"].abs())*(1-result["q_value"].fillna(1))
        peak_matrix=frame.pivot_table(index="region",columns="sample",values="signal",aggfunc="mean").reset_index(); motif=result.groupby("motif",as_index=False).agg(regions=("region","count"),mean_effect=("log2_fold_change","mean"),mean_priority=("priority_score","mean")); gene=result.groupby("gene",as_index=False).agg(regions=("region","count"),max_priority=("priority_score","max"),mean_effect=("log2_fold_change","mean"))
        extras.update({"peak_matrix":peak_matrix,"motif_activity":motif,"peak_gene_links":gene})
        metrics={"regions":len(result),"samples":frame["sample"].nunique(),"fdr_regions":int((result["q_value"]<=0.05).sum()),"motifs":result["motif"].nunique()}

    elif key == "pharmacogenomics_peak":
        levels={"High":1.0,"Moderate":0.65,"Low":0.3}; result=frame.copy(); result["evidence_score"]=result["evidence_level"].astype(str).map(levels).fillna(0.2); result["frequency_score"]=(1-_num(result.get("population_frequency",pd.Series(0.5,index=result.index)),0.5)).clip(0,1); result["copy_number_review"]=_num(result.get("copy_number",pd.Series(2,index=result.index)),2).ne(2); result["priority_score"]=0.65*result["evidence_score"]+0.25*result["frequency_score"]+0.10*result["copy_number_review"].astype(float); result["review_status"]=np.select([result["evidence_score"]>=0.9,result["evidence_score"]>=0.6],["High-evidence review","Moderate-evidence review"],default="Evidence limited")
        gene_drug=result.pivot_table(index="gene",columns="drug",values="priority_score",aggfunc="max",fill_value=0).reset_index(); phenotype=result.groupby(["sample","gene"],as_index=False).agg(alleles=("allele",lambda x:"/".join(sorted(set(map(str,x))))),max_evidence=("evidence_score","max"),copy_number=("copy_number","max") if "copy_number" in result.columns else ("priority_score",lambda _:2)); phenotype["phenotype"] = np.where(phenotype["copy_number"]>2,"Possible increased function",np.where(phenotype["alleles"].str.contains(r"\*2|\*3|\*4",regex=True),"Possible reduced function","Reference-like/uncertain"))
        conflicts=result.groupby(["sample","drug"],as_index=False).agg(distinct_levels=("evidence_level","nunique"),records=("variant","count")); conflicts["conflict_flag"]=conflicts["distinct_levels"]>1
        extras.update({"drug_gene_matrix":gene_drug,"phenotypes":phenotype,"conflicts":conflicts})
        metrics={"samples":result["sample"].nunique(),"drug_gene_records":len(result),"high_evidence":int((result["evidence_score"]>=0.9).sum()),"conflicts":int(conflicts["conflict_flag"].sum())}

    elif key in {"structural_variant_peak","circular_dna_instability"}:
        result=frame.copy(); result["size_bp"]=(_num(result["end"])-_num(result["start"])).abs().clip(lower=1); result["support_score"]=_rank01(result["support"]); result["quality_score"]=_rank01(result.get("quality",pd.Series(50,index=result.index))); result["gene_impact"]=np.where(result.get("gene",pd.Series("INTERGENIC",index=result.index)).astype(str).str.upper().eq("INTERGENIC"),0.25,1.0); result["mosaic_score"]=(1-(_num(result.get("allele_fraction",pd.Series(0.5,index=result.index)),0.5)-0.25).abs()/0.25).clip(0,1); result["copy_score"]=_rank01(result.get("copy_number",pd.Series(2,index=result.index))); result["priority_score"]=0.3*result["support_score"]+0.2*result["quality_score"]+0.2*result["gene_impact"]+0.15*result["mosaic_score"]+0.15*result["copy_score"]; result["low_confidence"]=_num(result["support"])<3; result=result.sort_values(["low_confidence","priority_score"],ascending=[True,False])
        caller=result.pivot_table(index="event_type",columns="caller",values="event_id",aggfunc="count",fill_value=0).reset_index() if "caller" in result.columns else pd.DataFrame(); chrom=result.groupby("chrom",as_index=False).agg(events=("event_id","count"),median_size=("size_bp","median"),mean_priority=("priority_score","mean")); gene=result.groupby("gene",as_index=False).agg(events=("event_id","count"),max_priority=("priority_score","max")) if "gene" in result.columns else pd.DataFrame()
        extras.update({"caller_concordance":caller,"chromosome_summary":chrom,"gene_impact":gene})
        metrics={"events":len(result),"samples":result["sample"].nunique(),"low_confidence":int(result["low_confidence"].sum()),"high_priority":int((result["priority_score"]>=threshold).sum())}

    elif key == "rna_splicing_peak":
        frame["psi"]=_num(frame["psi"]); groups=frame["group"].astype(str).unique().tolist(); rows=[]
        for (event,gene,transcript),g in frame.groupby(["event","gene","transcript"],dropna=False):
            a=g.loc[g["group"].astype(str)==groups[0],"psi"] if groups else pd.Series(dtype=float); b=g.loc[g["group"].astype(str)==groups[-1],"psi"] if len(groups)>1 else pd.Series(dtype=float)
            rows.append({"event":event,"gene":gene,"transcript":transcript,"samples":g["sample"].nunique(),"mean_psi":float(g["psi"].mean()),"delta_psi":float(_num(b).mean()-_num(a).mean()) if len(groups)>1 else 0.0,"p_value":_safe_welch(a,b),"junction_support":float(_num(g["junction_support"]).median()),"variant":g.get("variant",pd.Series(["None"])).iloc[0]})
        result=pd.DataFrame(rows); result["q_value"]=_bh(result["p_value"]); result["supported"]=result["junction_support"]>=5; result["priority_score"]=result["delta_psi"].abs()*(1-result["q_value"].fillna(1))*result["supported"].astype(float)
        psi=frame.pivot_table(index="event",columns="sample",values="psi",aggfunc="mean").reset_index(); gene=result.groupby("gene",as_index=False).agg(events=("event","count"),max_delta=("delta_psi",lambda x:float(np.max(np.abs(x)))),max_priority=("priority_score","max")); types=result.assign(event_type=result["event"].astype(str).str.split(":").str[-1]).groupby("event_type",as_index=False).agg(events=("event","count"),mean_delta=("delta_psi","mean"))
        extras.update({"psi_matrix":psi,"gene_summary":gene,"event_types":types})
        metrics={"events":len(result),"genes":result["gene"].nunique(),"fdr_events":int((result["q_value"]<=0.05).sum()),"supported":int(result["supported"].sum())}

    elif key == "immune_repertoire":
        result=frame.copy(); result["count"]=_num(result["count"],0).clip(lower=0); totals=result.groupby("sample")["count"].transform("sum").replace(0,np.nan); result["frequency"]=result["count"]/totals; result["expanded"]=result["frequency"]>=result.groupby("sample")["frequency"].transform(lambda x:x.quantile(0.95)); result["priority_score"]=_rank01(result["frequency"])+0.15*result["expanded"].astype(float)
        diversity=result.groupby("sample").apply(lambda g:pd.Series({"shannon":_entropy(g["count"]),"richness":g["clonotype"].nunique(),"expanded_clones":int(g["expanded"].sum()),"group":g.get("group",pd.Series(["Unknown"])).iloc[0]}),include_groups=False).reset_index(); vj=result.pivot_table(index="v_gene",columns="j_gene",values="count",aggfunc="sum",fill_value=0).reset_index(); longitudinal=result.groupby(["clonotype","time"],as_index=False).agg(count=("count","sum"),samples=("sample","nunique")) if "time" in result.columns else pd.DataFrame()
        extras.update({"diversity":diversity,"vj_usage":vj,"longitudinal":longitudinal})
        metrics={"samples":result["sample"].nunique(),"clonotypes":result["clonotype"].nunique(),"expanded_records":int(result["expanded"].sum()),"chains":result["chain"].nunique()}

    elif key == "single_cell_multiome":
        frame["value"]=_num(frame["value"],0).clip(lower=0); cell_mod=frame.groupby(["cell","sample","cluster","batch","modality"],as_index=False).agg(total=("value","sum"),features=("feature","nunique")); wide=cell_mod.pivot_table(index=["cell","sample","cluster","batch"],columns="modality",values="total",fill_value=0).reset_index(); numeric=wide.select_dtypes(include=[np.number]); pcs=_pca(numeric,2); wide["UMAP1"]=pcs["PC1"].to_numpy(); wide["UMAP2"]=pcs["PC2"].to_numpy(); modalities=[c for c in ["RNA","ATAC","ADT"] if c in wide.columns]; wide["modality_agreement"]=wide[modalities].rank(pct=True).std(axis=1).rsub(1).clip(0,1) if modalities else 0.0; wide["priority_score"]=wide["modality_agreement"]
        result=wide; links=frame.groupby(["cluster","modality","feature"],as_index=False).agg(mean_value=("value","mean"),cells=("cell","nunique")); tf=links[links["modality"].eq("ATAC")].copy(); tf["tf_activity"]=_rank01(tf["mean_value"]); composition=result.groupby(["sample","cluster"],as_index=False).agg(cells=("cell","count"),mean_agreement=("modality_agreement","mean")); batch=result.groupby(["batch","cluster"],as_index=False).agg(cells=("cell","count"))
        extras.update({"feature_links":links,"tf_activity":tf,"cluster_composition":composition,"batch_mixing":batch})
        metrics={"cells":result["cell"].nunique(),"clusters":result["cluster"].nunique(),"modalities":len(modalities),"low_agreement":int((result["modality_agreement"]<0.5).sum())}

    elif key == "proteogenomics_peak":
        result=frame.copy(); result["binding_score"]=_num(result["binding_score"],0).clip(0,1); result["expression_score"]=_rank01(result["expression"]); result["ms_score"]=_num(result["ms_support"],0).clip(0,1); result["clonality_score"]=_num(result.get("clonality",pd.Series(0.5,index=result.index)),0.5).clip(0,1); result["safety_score"]=(1-_num(result.get("normal_tissue_risk",pd.Series(0.5,index=result.index)),0.5)).clip(0,1); result["priority_score"]=0.25*(1-result["binding_score"])+0.2*result["expression_score"]+0.2*result["ms_score"]+0.2*result["clonality_score"]+0.15*result["safety_score"]
        hla=result.pivot_table(index="peptide",columns="hla",values="priority_score",aggfunc="max",fill_value=0).reset_index(); evidence=result.groupby(["gene","variant"],as_index=False).agg(peptides=("peptide","nunique"),max_priority=("priority_score","max"),ms_supported=("ms_support","sum"),mean_expression=("expression","mean")); panel=result.sort_values("priority_score",ascending=False).drop_duplicates(["gene","hla"]).head(25)
        extras.update({"hla_matrix":hla,"evidence_matrix":evidence,"vaccine_panel":panel})
        metrics={"candidates":len(result),"samples":result["sample"].nunique(),"ms_supported":int((_num(result["ms_support"])>0).sum()),"high_priority":int((result["priority_score"]>=threshold).sum())}

    elif key == "gene_regulatory_network":
        frame["activity"]=_num(frame["activity"]); groups=frame["condition"].astype(str).unique().tolist(); rows=[]
        for (tf,target),g in frame.groupby(["tf","target"]):
            a=g.loc[g["condition"].astype(str)==groups[0],"activity"] if groups else pd.Series(dtype=float); b=g.loc[g["condition"].astype(str)==groups[-1],"activity"] if len(groups)>1 else pd.Series(dtype=float)
            rows.append({"tf":tf,"target":target,"mean_activity":float(g["activity"].mean()),"delta_activity":float(_num(b).mean()-_num(a).mean()) if len(groups)>1 else 0,"p_value":_safe_welch(a,b),"evidence":float(_num(g["evidence"]).mean()),"expression":float(_num(g["expression"]).mean()),"motif_score":float(_num(g.get("motif_score",pd.Series(0.5,index=g.index)),0.5).mean())})
        result=pd.DataFrame(rows); result["q_value"]=_bh(result["p_value"]); result["priority_score"]=(0.35*_rank01(result["delta_activity"].abs())+0.3*result["evidence"].clip(0,1)+0.2*_rank01(result["expression"])+0.15*result["motif_score"].clip(0,1)); regulon=result.groupby("tf",as_index=False).agg(targets=("target","nunique"),mean_activity=("mean_activity","mean"),delta_activity=("delta_activity","mean"),max_priority=("priority_score","max"),evidence=("evidence","mean")); matrix=frame.pivot_table(index="tf",columns="sample",values="activity",aggfunc="mean").reset_index()
        extras.update({"regulons":regulon,"activity_matrix":matrix,"top_edges":result.nlargest(100,"priority_score")})
        metrics={"edges":len(result),"tfs":result["tf"].nunique(),"targets":result["target"].nunique(),"high_confidence_edges":int((result["priority_score"]>=threshold).sum())}

    elif key == "federated_genomic_discovery":
        result=frame.copy(); result["phenotype_similarity"]=_num(result["phenotype_similarity"],0).clip(0,1); result["variant_match"]=_num(result["variant_match"],0).clip(0,1); access_score=result["access_status"].astype(str).map({"Open metadata":1.0,"Controlled":0.65,"Request required":0.4}).fillna(0.25); result["priority_score"]=0.55*result["phenotype_similarity"]+0.35*result["variant_match"]+0.10*access_score; result["access_review_required"]=~result["access_status"].astype(str).eq("Open metadata")
        sources=result.groupby("source",as_index=False).agg(cases=("case_id","nunique"),mean_match=("priority_score","mean"),controlled=("access_review_required","sum")); phen=result.pivot_table(index="phenotype",columns="source",values="priority_score",aggfunc="max",fill_value=0).reset_index(); provenance=result[["case_id","source","access_status","consent_scope"]].drop_duplicates()
        extras.update({"source_coverage":sources,"phenotype_matrix":phen,"query_provenance":provenance})
        metrics={"cases":result["case_id"].nunique(),"sources":result["source"].nunique(),"high_matches":int((result["priority_score"]>=threshold).sum()),"access_reviews":int(result["access_review_required"].sum())}

    elif key == "viral_within_host":
        result=frame.copy(); result["frequency"]=_num(result["frequency"],0).clip(0,1); result["minor_variant"]=result["frequency"].between(0.02,0.5); result["depth_pass"]=_num(result.get("depth",pd.Series(0,index=result.index)),0)>=100; rows=[]
        for (subject,position,alt),g in result.groupby(["subject","position","alt"]):
            clean=g[["time","frequency"]].dropna().sort_values("time"); slope=float(np.polyfit(clean["time"],clean["frequency"],1)[0]) if len(clean)>=2 and clean["time"].nunique()>=2 else 0.0
            rows.append({"subject":subject,"position":position,"alt":alt,"lineage":g["lineage"].iloc[0],"max_frequency":float(g["frequency"].max()),"frequency_slope":slope,"timepoints":g["time"].nunique(),"recombination_flag":bool(g.get("recombination_flag",pd.Series(False,index=g.index)).any()),"depth_pass_rate":float(g["depth_pass"].mean())})
        trajectories=pd.DataFrame(rows); trajectories["priority_score"]=0.45*_rank01(trajectories["max_frequency"])+0.35*_rank01(trajectories["frequency_slope"].abs())+0.2*trajectories["depth_pass_rate"]; result=result.merge(trajectories[["subject","position","alt","priority_score"]],on=["subject","position","alt"],how="left")
        lineage=result.groupby(["lineage","position","alt"],as_index=False).agg(mean_frequency=("frequency","mean"),subjects=("subject","nunique")); subject=result.groupby("subject",as_index=False).agg(variants=("position","nunique"),minor_variants=("minor_variant","sum"),lineage=("lineage","first"),recombination_flags=("recombination_flag","sum"))
        extras.update({"trajectories":trajectories,"lineage_markers":lineage,"subject_summary":subject})
        metrics={"subjects":result["subject"].nunique(),"variants":result[["position","alt"]].drop_duplicates().shape[0],"minor_records":int(result["minor_variant"].sum()),"recombination_flags":int(result.get("recombination_flag",pd.Series(False,index=result.index)).sum())}

    elif key == "genome_annotation":
        result=frame.copy(); result["length_bp"]=(_num(result["end"])-_num(result["start"])).abs().clip(lower=1); evidence_score=result["evidence"].astype(str).map({"protein":1.0,"RNA":0.9,"orthology":0.75,"ab_initio":0.4}).fillna(0.3); result["evidence_score"]=evidence_score; result["completeness"]=_num(result.get("completeness",pd.Series(0.5,index=result.index)),0.5).clip(0,1); result["priority_score"]=0.55*result["evidence_score"]+0.45*result["completeness"]
        versions=result.pivot_table(index="feature_id",columns="genome",values="priority_score",aggfunc="max",fill_value=0).reset_index(); orth=result.groupby(["ortholog_group","genome"],as_index=False).agg(features=("feature_id","nunique"),mean_completeness=("completeness","mean")); chrom=result.groupby(["genome","chrom"],as_index=False).agg(features=("feature_id","count"),total_bp=("length_bp","sum"),mean_priority=("priority_score","mean")); review=result.loc[(result["priority_score"]<0.55)|(result["length_bp"]<50)].copy()
        extras.update({"version_diff":versions,"orthology":orth,"chromosome_summary":chrom,"review_queue":review})
        metrics={"features":len(result),"genomes":result["genome"].nunique(),"ortholog_groups":result["ortholog_group"].nunique(),"review_required":len(review)}

    elif key == "environmental_edna":
        result=frame.copy(); result["reads"]=_num(result["reads"],0).clip(lower=0); negatives=result.loc[result["control_type"].astype(str).str.contains("negative",case=False,na=False)].groupby("species")["reads"].max(); result["background_reads"]=result["species"].map(negatives).fillna(0); result["adjusted_reads"]=(result["reads"]-result["background_reads"]).clip(lower=0); result["detection"]=result["adjusted_reads"]>=3; result["confidence_score"]=_num(result["reference_confidence"],0).clip(0,1)*np.where(result["detection"],1.0,0.25); result["priority_score"]=_rank01(result["adjusted_reads"])*result["confidence_score"]
        sample_summary=result.groupby(["sample","site","date"],as_index=False).agg(species_detected=("detection","sum"),total_reads=("adjusted_reads","sum"),shannon=("adjusted_reads",_entropy)); occupancy=result.groupby(["site","species"],as_index=False).agg(samples=("sample","nunique"),detections=("detection","sum"),mean_reads=("adjusted_reads","mean"),mean_confidence=("confidence_score","mean")); occupancy["occupancy"]=occupancy["detections"]/occupancy["samples"].replace(0,np.nan); contamination=result.loc[result["control_type"].astype(str).str.contains("negative",case=False,na=False)].copy()
        extras.update({"sample_summary":sample_summary,"occupancy":occupancy,"contamination":contamination})
        metrics={"samples":result["sample"].nunique(),"sites":result["site"].nunique(),"species":result["species"].nunique(),"detections":int(result["detection"].sum())}

    elif key == "comparative_regulatory_genomics":
        result=frame.copy(); result["conservation"]=_num(result["conservation"],0).clip(0,1); result["activity"]=_num(result["activity"],0).clip(lower=0); result["activity_norm"]=_rank01(result["activity"]); result["priority_score"]=0.55*result["conservation"]+0.45*result["activity_norm"]
        motif=result.pivot_table(index="motif",columns="species",values="activity",aggfunc="mean",fill_value=0).reset_index(); orth=result.pivot_table(index="ortholog_group",columns="species",values="conservation",aggfunc="mean",fill_value=0).reset_index(); synteny=result.groupby(["species","chrom"],as_index=False).agg(regions=("region","nunique"),mean_conservation=("conservation","mean"),mean_activity=("activity","mean")); species=result.groupby("species",as_index=False).agg(regions=("region","nunique"),mean_conservation=("conservation","mean"),mean_activity=("activity","mean"),motifs=("motif","nunique"))
        extras.update({"motif_turnover":motif,"ortholog_matrix":orth,"synteny":synteny,"species_summary":species})
        metrics={"regions":result["region"].nunique(),"species":result["species"].nunique(),"motifs":result["motif"].nunique(),"high_priority":int((result["priority_score"]>=threshold).sum())}

    else:
        raise KeyError(key)

    result=result.replace([np.inf,-np.inf],np.nan)
    if "priority_score" in result.columns:
        result=result.sort_values("priority_score",ascending=False,na_position="last")
    quality_rows=[
        {"check":"Required fields","status":"Pass" if not validation["missing_required"] else "Block","value":len(validation["missing_required"]),"detail":", ".join(validation["missing_required"]) or "All required fields present"},
        {"check":"Duplicate columns","status":"Pass" if not validation["duplicate_columns"] else "Block","value":len(validation["duplicate_columns"]),"detail":", ".join(validation["duplicate_columns"]) or "No duplicate columns"},
        {"check":"Missing cells","status":"Review" if validation["missing_cells"] else "Pass","value":validation["missing_cells"],"detail":"Missing values are retained and shown in evidence"},
        {"check":"Duplicate rows","status":"Review" if validation["duplicate_rows"] else "Pass","value":validation["duplicate_rows"],"detail":"Duplicates are not silently removed"},
        {"check":"Scientific boundary","status":"Research use","value":0,"detail":module.boundary},
    ]
    quality=pd.DataFrame(quality_rows)
    summary={"schema":"biointel.bioinformatics_peak.v138","module":key,"title":module.title,"input_records":len(frame),"result_records":len(result),"threshold":threshold,"metrics":metrics,"quality":validation,"visual_count":len(module.visuals),"scientific_boundary":module.boundary,"handoffs":list(module.handoffs)}
    base = AnalysisBundle(result=result, summary=summary, extras=extras, quality=quality)
    from .deep_science import enhance_bundle
    from .last_mile import augment_bundle
    enhanced = enhance_bundle(frame, module, base, parameters)
    return augment_bundle(frame, module, enhanced, parameters)
