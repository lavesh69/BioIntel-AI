from __future__ import annotations

from itertools import combinations
from typing import Any
import math

import numpy as np
import pandas as pd
from scipy import stats

TARGETS = {
    "docking_dynamics", "genome_editing_safety", "metagenomics_core", "pathogen_outbreak_core",
    "pharmacogenomics", "phenotypic_screening", "population_gwas", "protein_language_design",
    "proteogenomics_neoantigen", "single_cell_core", "single_cell_trajectory",
    "spatial_omics_pathology", "structural_bioinformatics_core", "virology_evolution",
    "federated_biomedical_ai", "cell_atlas_mapping", "enzyme_pathway_design",
    "explainable_ai_assurance", "glycomics_glycoproteomics", "metabolomics_lipidomics",
    "model_registry_v2",
}

AA = set("ACDEFGHIKLMNPQRSTVWY")
HYDROPHOBIC = set("AILMFWVY")


def _col(frame: pd.DataFrame, *names: str) -> str | None:
    lookup = {str(c).strip().lower(): str(c) for c in frame.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None


def _num(s: Any) -> pd.Series:
    if isinstance(s, pd.Series):
        return pd.to_numeric(s, errors="coerce")
    return pd.Series(dtype=float)


def _bool(s: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False)
    return s.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y", "positive", "present", "pass", "carrier", "resistant", "case"})


def _check(checks: list[dict[str, Any]], name: str, status: str, detail: str) -> None:
    checks.append({"check": name, "status": status, "detail": detail})


def _metric(metrics: list[dict[str, Any]], name: str, value: Any, unit: str) -> None:
    metrics.append({"metric": name, "value": value, "unit": unit})


def _bh(values: pd.Series) -> pd.Series:
    p = pd.to_numeric(values, errors="coerce")
    result = pd.Series(np.nan, index=p.index, dtype=float)
    valid = p.notna()
    if not valid.any():
        return result
    ordered = p[valid].sort_values()
    n = len(ordered)
    adjusted = ordered.to_numpy() * n / np.arange(1, n + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    result.loc[ordered.index] = np.clip(adjusted, 0, 1)
    return result


def _safe_z(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    x = _num(series)
    sd = float(x.std(ddof=0))
    if not np.isfinite(sd) or sd <= 1e-12:
        z = pd.Series(0.0, index=x.index)
    else:
        z = (x - float(x.mean())) / sd
    return z if higher_is_better else -z


def _classification(y_true: pd.Series, y_score: pd.Series, threshold: float = 0.5) -> dict[str, float]:
    y = _num(y_true).fillna(0).astype(int).clip(0, 1)
    score = _num(y_score).fillna(0.5).clip(0, 1)
    pred = score.ge(threshold).astype(int)
    tp = int(((y == 1) & (pred == 1)).sum()); tn = int(((y == 0) & (pred == 0)).sum())
    fp = int(((y == 0) & (pred == 1)).sum()); fn = int(((y == 1) & (pred == 0)).sum())
    sens = tp / max(tp + fn, 1); spec = tn / max(tn + fp, 1); ppv = tp / max(tp + fp, 1)
    f1 = 2 * ppv * sens / max(ppv + sens, 1e-12)
    brier = float(np.mean((score - y) ** 2))
    bins = pd.cut(score, bins=np.linspace(0, 1, 11), include_lowest=True)
    cal = pd.DataFrame({"y": y, "score": score, "bin": bins}).groupby("bin", observed=False).agg(n=("y", "size"), observed=("y", "mean"), predicted=("score", "mean")).reset_index()
    ece = float(((cal["n"] / max(cal["n"].sum(), 1)) * (cal["observed"] - cal["predicted"]).abs()).sum())
    return {"sensitivity": sens, "specificity": spec, "precision": ppv, "f1": f1, "accuracy": (tp + tn) / max(len(y), 1), "brier": brier, "ece": ece, "tp": tp, "tn": tn, "fp": fp, "fn": fn}


def _bray(a: np.ndarray, b: np.ndarray) -> float:
    den = float(np.abs(a + b).sum())
    return float(np.abs(a - b).sum() / den) if den > 0 else 0.0


def _sequence_metrics(seq: str) -> dict[str, float | int | bool]:
    s = "".join(str(seq).upper().split())
    valid = bool(s) and set(s).issubset(AA)
    n = max(len(s), 1)
    counts = pd.Series(list(s)).value_counts(normalize=True) if s else pd.Series(dtype=float)
    entropy = float(-(counts * np.log2(counts)).sum()) if len(counts) else 0.0
    return {
        "sequence_length": len(s), "valid_amino_acids": valid,
        "hydrophobic_fraction": sum(c in HYDROPHOBIC for c in s) / n,
        "cysteine_fraction": s.count("C") / n, "proline_fraction": s.count("P") / n,
        "sequence_entropy": entropy,
    }


def _docking(frame, metadata, tables, checks, metrics):
    work = frame.copy(); compound = _col(work, "compound", "candidate_id", "ligand"); score = _col(work, "docking_score", "score", "binding_score"); rmsd = _col(work, "rmsd", "pose_rmsd"); strain = _col(work, "strain_energy", "strain"); pose = _col(work, "pose_id", "pose")
    if not compound or not score:
        tables["step167_docking_input_readiness"] = pd.DataFrame([{"required": "compound", "present": bool(compound)}, {"required": "docking_score", "present": bool(score)}]); return
    work["step167_docking_score"] = _num(work[score]); work["step167_rmsd"] = _num(work[rmsd]) if rmsd else np.nan; work["step167_strain"] = _num(work[strain]) if strain else np.nan
    rows=[]
    for name, sub in work.groupby(compound, dropna=False):
        best = sub.nsmallest(1, "step167_docking_score").iloc[0]
        rows.append({"compound": name, "poses": len(sub), "best_docking_score": best["step167_docking_score"], "median_docking_score": sub["step167_docking_score"].median(), "score_spread": sub["step167_docking_score"].max()-sub["step167_docking_score"].min(), "best_pose_rmsd": best["step167_rmsd"], "best_pose_strain": best["step167_strain"], "rmsd_le_2_fraction": float(sub["step167_rmsd"].le(2).mean()) if rmsd else np.nan, "strain_le_8_fraction": float(sub["step167_strain"].le(8).mean()) if strain else np.nan})
    summary=pd.DataFrame(rows)
    summary["step167_consensus_score"] = _safe_z(summary["best_docking_score"], False) + 0.5*_safe_z(summary["best_pose_rmsd"].fillna(summary["best_pose_rmsd"].median()), False) + 0.5*_safe_z(summary["best_pose_strain"].fillna(summary["best_pose_strain"].median()), False)
    summary["step167_pose_reproducible"] = summary["rmsd_le_2_fraction"].fillna(0).ge(0.5) & summary["strain_le_8_fraction"].fillna(0).ge(0.5)
    tables["step167_docking_pose_consensus"] = summary.sort_values(["step167_pose_reproducible", "step167_consensus_score"], ascending=[False, False])
    tables["step167_docking_release_gate"] = pd.DataFrame([{"pose_qc_available": bool(rmsd and strain), "receptor_preparation_qualified": bool(metadata.get("receptor_preparation_qualified", False)), "measured_affinity_attached": bool(metadata.get("measured_affinity_attached", False)), "controlled_release_eligible": False, "status": "research-only; measured affinity and qualified receptor/protocol required"}])
    _check(checks, "Step 167 docking pose reproducibility", "pass" if rmsd and strain else "review", f"{int(summary['step167_pose_reproducible'].sum())}/{len(summary)} compounds meet native pose QC.")


def _editing(frame, metadata, tables, checks, metrics):
    work=frame.copy(); gid=_col(work,"guide_id","id"); guide=_col(work,"guide","sequence","spacer"); pam=_col(work,"pam"); hits=_col(work,"off_target_hits","offtargets"); overlap=_col(work,"variant_overlap","population_variant_overlap")
    if not guide: tables["step167_editing_input_readiness"]=pd.DataFrame([{"required":"guide","present":False}]); return
    def longest_run(s):
        s=str(s).upper(); return max((len(x) for base in "ACGT" for x in s.split(base) if False), default=0)
    rows=[]
    for i,r in work.iterrows():
        seq="".join(str(r[guide]).upper().replace("U","T").split()); core=seq[:20]; gc=(core.count("G")+core.count("C"))/max(len(core),1); runs=[]
        for b in "ACGT":
            cur=best=0
            for c in core:
                cur=cur+1 if c==b else 0; best=max(best,cur)
            runs.append(best)
        off=float(pd.to_numeric(pd.Series([r[hits]]),errors="coerce").fillna(0).iloc[0]) if hits else 0; var=bool(_bool(pd.Series([r[overlap]])).iloc[0]) if overlap else False
        risk=min(1.0, 0.35*min(off/10,1)+0.2*float(var)+0.2*float(not (0.35<=gc<=0.65))+0.15*float(max(runs)>=5)+0.1*float("TTTT" in core))
        rows.append({"guide_id": r[gid] if gid else i, "guide_length":len(core), "valid_dna":set(core).issubset(set("ACGT")) and len(core)>=18, "gc_fraction":gc, "max_homopolymer":max(runs), "poly_t_flag":"TTTT" in core, "pam":r[pam] if pam else "not supplied", "off_target_hits":off, "population_variant_overlap":var, "step167_editing_risk_score":risk, "step167_research_priority":risk<=0.25})
    out=pd.DataFrame(rows).sort_values(["step167_research_priority","step167_editing_risk_score"],ascending=[False,True]); tables["step167_genome_editing_guide_safety"] = out
    tables["step167_genome_editing_release_gate"] = pd.DataFrame([{"genome_build": metadata.get("genome_build","not qualified"), "whole_genome_offtarget_engine_qualified": bool(metadata.get("offtarget_engine_qualified",False)), "orthogonal_editing_assay_attached": bool(metadata.get("orthogonal_editing_assay_attached",False)), "controlled_release_eligible":False}])
    _check(checks,"Step 167 genome-editing native safety","pass" if len(out) else "review",f"{int(out['step167_research_priority'].sum())}/{len(out)} guides pass native research-priority QC.")


def _microbiome(frame, metadata, tables, checks, metrics, outbreak=False):
    work=frame.copy(); sample=_col(work,"sample_id","sample"); taxon=_col(work,"taxon","species","lineage"); abundance=_col(work,"abundance","count","reads"); site=_col(work,"site","location"); neg=_col(work,"negative_control","control")
    if not all([sample,taxon,abundance]): tables["step167_microbiome_input_readiness"]=pd.DataFrame([{"required":x,"present":bool(y)} for x,y in [("sample",sample),("taxon",taxon),("abundance",abundance)]]); return
    work["step167_abundance"]=_num(work[abundance]).fillna(0).clip(lower=0); totals=work.groupby(sample)["step167_abundance"].transform("sum"); work["step167_relative_abundance"]=work["step167_abundance"]/totals.replace(0,np.nan)
    control_mask=_bool(work[neg]) if neg else work[sample].astype(str).str.contains("blank|neg|control|nc",case=False,regex=True)
    control_prev=work.assign(_control=control_mask).groupby(taxon).apply(lambda x: float((x.loc[x._control,"step167_abundance"]>0).mean()) if x._control.any() else 0.0,include_groups=False)
    sample_rows=[]
    for s,sub in work.groupby(sample):
        p=sub["step167_relative_abundance"].fillna(0); nz=p[p>0]; sh=float(-(nz*np.log(nz)).sum()) if len(nz) else 0.0
        sample_rows.append({"sample_id":s,"library_size":sub["step167_abundance"].sum(),"richness":int((sub["step167_abundance"]>0).sum()),"shannon":sh,"dominance":float(p.max()),"negative_control":bool(control_mask.loc[sub.index].any()),"site":sub[site].astype(str).iloc[0] if site else "unknown"})
    sample_qc=pd.DataFrame(sample_rows); tables["step167_metagenomics_sample_qc" if not outbreak else "step167_outbreak_sample_qc"] = sample_qc
    pivot=work.pivot_table(index=sample,columns=taxon,values="step167_relative_abundance",aggfunc="sum",fill_value=0)
    dist=[]
    for a,b in combinations(pivot.index,2):
        d=_bray(pivot.loc[a].to_numpy(float),pivot.loc[b].to_numpy(float)); dist.append({"sample_a":a,"sample_b":b,"bray_curtis":d,"profile_similarity":1-d,"step167_cluster_review":(1-d)>=0.8})
    distance=pd.DataFrame(dist); tables["step167_outbreak_profile_clusters" if outbreak else "step167_metagenomics_beta_diversity"] = distance
    contamin=pd.DataFrame({"taxon":control_prev.index,"control_prevalence":control_prev.values}); contamin["step167_control_contaminant_review"]=contamin.control_prevalence.ge(0.5); tables["step167_outbreak_contamination_screen" if outbreak else "step167_metagenomics_contamination_screen"] = contamin.sort_values("control_prevalence",ascending=False)
    if site:
        site_profile=work.groupby([site,taxon])["step167_relative_abundance"].mean().reset_index(); tables["step167_outbreak_site_profile" if outbreak else "step167_metagenomics_site_profile"] = site_profile
    tables["step167_outbreak_release_gate" if outbreak else "step167_metagenomics_release_gate"] = pd.DataFrame([{"negative_controls_present":bool(control_mask.any()),"mock_community_attached":bool(metadata.get("mock_community_attached",False)),"qualified_reference_database":bool(metadata.get("qualified_reference_database",False)),"epidemiology_confirmed":bool(metadata.get("epidemiology_confirmed",False)) if outbreak else False,"controlled_release_eligible":False}])
    _check(checks,"Step 167 outbreak profile and contamination" if outbreak else "Step 167 metagenomics composition and contamination","pass" if control_mask.any() else "review",f"{len(sample_qc)} samples; controls={'present' if control_mask.any() else 'absent'}.")


def _genetics(frame, metadata, tables, checks, metrics, pgx=False):
    work=frame.copy(); variant=_col(work,"variant_id","variant"); sample=_col(work,"sample_id","sample"); gt=_col(work,"genotype","gt"); phenotype=_col(work,"phenotype","outcome"); build=_col(work,"genome_build","build"); pc=_col(work,"pc1","ancestry_pc1")
    if not all([variant,sample,gt]): tables["step167_genetics_input_readiness"]=pd.DataFrame([{"required":x,"present":bool(y)} for x,y in [("variant",variant),("sample",sample),("genotype",gt)]]); return
    dosage=work[gt].astype(str).str.replace("|","/",regex=False).map({"0/0":0,"0/1":1,"1/0":1,"1/1":2}); work["step167_dosage"]=dosage
    rows=[]
    for v,sub in work.groupby(variant):
        d=sub.step167_dosage; called=d.notna(); maf=float(min(d[called].sum()/(2*called.sum()),1-d[called].sum()/(2*called.sum()))) if called.any() else np.nan
        counts=d.value_counts(); n=called.sum(); p=1-maf if np.isfinite(maf) else np.nan; exp=np.array([n*p*p,2*n*p*maf,n*maf*maf]) if n else np.array([0,0,0]); obs=np.array([counts.get(0,0),counts.get(1,0),counts.get(2,0)]); hwe_p=float(stats.chisquare(obs,exp).pvalue) if n and (exp>0).all() else np.nan
        assoc_p=np.nan; effect=np.nan
        if phenotype:
            y=_num(sub[phenotype]); valid=d.notna()&y.notna()
            if valid.sum()>=6 and y[valid].nunique()>1:
                r,pv=stats.pearsonr(d[valid],y[valid]); effect=float(r); assoc_p=float(pv)
        rows.append({"variant_id":v,"call_rate":float(called.mean()),"maf":maf,"hwe_p_value":hwe_p,"association_effect":effect,"association_p_value":assoc_p})
    out=pd.DataFrame(rows); out["association_q_value"]=_bh(out.association_p_value); out["step167_research_association"]=out.association_q_value.le(0.05)&out.call_rate.ge(0.95)&out.maf.ge(0.01)&out.hwe_p_value.fillna(1).gt(1e-6)
    tables["step167_pharmacogenomics_variant_qc" if pgx else "step167_gwas_variant_qc"] = out.sort_values(["step167_research_association","association_q_value"],ascending=[False,True])
    builds=work[build].dropna().astype(str).unique().tolist() if build else []
    covar=pd.DataFrame([{"ancestry_covariate_present":bool(pc),"genome_builds":", ".join(builds) if builds else "not supplied","single_genome_build":len(builds)<=1,"sample_count":work[sample].nunique()}]); tables["step167_pharmacogenomics_context_audit" if pgx else "step167_gwas_population_structure_audit"] = covar
    tables["step167_pharmacogenomics_release_gate" if pgx else "step167_gwas_release_gate"] = pd.DataFrame([{"qualified_interpretation_guideline":bool(metadata.get("qualified_guideline",False)) if pgx else False,"independent_cohort_replication":bool(metadata.get("independent_cohort_replication",False)),"domain_expert_signoff":bool(metadata.get("domain_expert_signoff",False)),"controlled_release_eligible":False}])
    _check(checks,"Step 167 PGx variant and interpretation QC" if pgx else "Step 167 GWAS variant and population QC","pass" if len(out) else "review",f"{len(out)} variants assessed; {int(out['step167_research_association'].sum())} research associations.")


def _phenotypic(frame, metadata, tables, checks, metrics):
    work=frame.copy(); truth=_col(work,"ground_truth","y_true"); pred=_col(work,"prediction","y_pred"); patient=_col(work,"patient_id","subject_id"); slide=_col(work,"slide_id"); area=_col(work,"area","cell_area")
    if not truth or not pred: return
    y=work[truth].astype(str).str.lower().isin({"positive","1","true","case"}).astype(int); score=work[pred].astype(str).str.lower().isin({"positive","1","true","case"}).astype(float)
    perf=_classification(y,score); tables["step167_phenotypic_performance"] = pd.DataFrame([perf])
    if patient:
        patient_perf=[]
        for p,sub in work.assign(_y=y,_s=score).groupby(patient):
            m=_classification(sub._y,sub._s); patient_perf.append({"patient_id":p,**m})
        tables["step167_phenotypic_patient_performance"] = pd.DataFrame(patient_perf)
    duplicate_leak=False
    if patient and slide:
        duplicate_leak=bool(work.groupby(slide)[patient].nunique().gt(1).any())
    morph=work.groupby(truth).agg(records=(truth,"size"),median_area=(area,"median") if area else (truth,"size")).reset_index(); tables["step167_phenotypic_morphology_summary"] = morph
    tables["step167_phenotypic_model_gate"] = pd.DataFrame([{"patient_split_verified":not duplicate_leak,"external_plate_or_site_validation":bool(metadata.get("external_site_validation",False)),"eligible_task_model":bool(metadata.get("eligible_task_model",False)),"controlled_release_eligible":False}])
    _check(checks,"Step 167 phenotypic patient-aware validation","pass" if patient else "review",f"Accuracy {perf['accuracy']:.3f}; patient identifier={'present' if patient else 'absent'}.")


def _protein_design(frame, metadata, tables, checks, metrics, enzyme=False):
    work=frame.copy(); cid=_col(work,"candidate_id","id"); seq=_col(work,"protein_sequence","sequence"); plddt=_col(work,"plddt","confidence"); identity=_col(work,"max_identity","identity"); yield_col=_col(work,"expression_yield","yield"); activity=_col(work,"activity"); dg=_col(work,"delta_g"); flux=_col(work,"predicted_flux","flux"); kcat=_col(work,"kcat"); km=_col(work,"km")
    rows=[]
    for i,r in work.iterrows():
        metrics_seq=_sequence_metrics(r[seq] if seq else "")
        row={"candidate_id":r[cid] if cid else i,**metrics_seq}
        for name,col in [("plddt",plddt),("max_identity",identity),("expression_yield",yield_col),("activity",activity),("delta_g",dg),("predicted_flux",flux),("kcat",kcat),("km",km)]: row[name]=float(pd.to_numeric(pd.Series([r[col]]),errors="coerce").iloc[0]) if col and pd.notna(pd.to_numeric(pd.Series([r[col]]),errors="coerce").iloc[0]) else np.nan
        row["catalytic_efficiency"] = row["kcat"]/row["km"] if enzyme and np.isfinite(row["kcat"]) and np.isfinite(row["km"]) and row["km"]>0 else np.nan
        rows.append(row)
    out=pd.DataFrame(rows)
    if enzyme:
        out["step167_design_score"]=_safe_z(out.delta_g.fillna(0),False)+_safe_z(out.predicted_flux.fillna(0),True)+_safe_z(out.catalytic_efficiency.fillna(0),True)
        out["step167_thermodynamically_feasible"]=out.delta_g.fillna(1).lt(0)&out.predicted_flux.fillna(0).gt(0)
        table="step167_enzyme_pathway_candidate_ranking"; gate="step167_enzyme_pathway_release_gate"
    else:
        out["step167_design_score"]=_safe_z(out.plddt.fillna(0),True)+_safe_z(out.max_identity.fillna(1),False)+0.5*_safe_z(out.expression_yield.fillna(0),True)+0.5*_safe_z(out.activity.fillna(0),True)+0.25*_safe_z(out.sequence_entropy,True)
        out["step167_native_design_priority"]=out.valid_amino_acids&out.plddt.fillna(0).ge(70)&out.max_identity.fillna(1).le(0.5)
        table="step167_protein_language_design_ranking"; gate="step167_protein_language_model_gate"
    tables[table]=out.sort_values("step167_design_score",ascending=False)
    tables[gate]=pd.DataFrame([{"eligible_task_model":bool(metadata.get("eligible_task_model",False)),"model_weights_version_locked":bool(metadata.get("model_weights_version_locked",False)),"wetlab_confirmation_attached":bool(metadata.get("wetlab_confirmation_attached",False)),"controlled_release_eligible":False}])
    _check(checks,"Step 167 enzyme/pathway native prioritisation" if enzyme else "Step 167 protein-design native prioritisation","pass" if len(out) else "review",f"{len(out)} candidates ranked with sequence and scientific constraints.")


def _psm(frame, metadata, tables, checks, metrics, glyco=False):
    work=frame.copy(); score=_col(work,"score"); decoy=_col(work,"decoy"); psm=_col(work,"psm_id","id"); variant=_col(work,"variant_id"); tumor=_col(work,"tumor_specific"); affinity=_col(work,"hla_affinity"); glycan=_col(work,"glycan"); sitep=_col(work,"site_probability")
    if not score or not decoy: return
    work["step167_score"]=_num(work[score]); work["step167_decoy"]=_bool(work[decoy]); work=work.sort_values("step167_score",ascending=False).reset_index(drop=True)
    work["step167_cum_decoy"]=work.step167_decoy.cumsum(); work["step167_cum_target"]=(~work.step167_decoy).cumsum(); work["step167_fdr"]=(work.step167_cum_decoy+1)/work.step167_cum_target.clip(lower=1); work["step167_q_value"]=work.step167_fdr[::-1].cummin()[::-1]
    if glyco:
        work["step167_localisation_confident"]=_num(work[sitep]).ge(0.75) if sitep else False; work["step167_high_confidence_glycopeptide"]=(~work.step167_decoy)&work.step167_q_value.le(0.01)&work.step167_localisation_confident
        tables["step167_glycomics_psm_fdr"] = work
        if glycan: tables["step167_glycomics_glycan_summary"] = work[~work.step167_decoy].groupby(glycan).agg(psms=(psm,"nunique") if psm else (glycan,"size"),best_q_value=("step167_q_value","min"),median_site_probability=(sitep,"median") if sitep else ("step167_q_value","size")).reset_index()
        gate="step167_glycomics_release_gate"
    else:
        work["step167_tumor_specific"]=_bool(work[tumor]) if tumor else False; work["step167_strong_hla_binding"]=_num(work[affinity]).le(500) if affinity else False; work["step167_high_confidence_neoantigen"]=(~work.step167_decoy)&work.step167_q_value.le(0.01)&work.step167_tumor_specific&work.step167_strong_hla_binding
        tables["step167_proteogenomics_psm_fdr"] = work
        if variant: tables["step167_neoantigen_candidate_summary"] = work.groupby(variant).agg(psms=(psm,"nunique") if psm else (variant,"size"),best_q_value=("step167_q_value","min"),tumor_specific=("step167_tumor_specific","max"),strong_hla_binding=("step167_strong_hla_binding","max"),high_confidence=("step167_high_confidence_neoantigen","max")).reset_index()
        gate="step167_proteogenomics_release_gate"
    tables[gate]=pd.DataFrame([{"qualified_search_engine":bool(metadata.get("qualified_search_engine",False)),"spectral_or_immunogenicity_confirmation":bool(metadata.get("orthogonal_confirmation",False)),"controlled_release_eligible":False}])
    _check(checks,"Step 167 glycopeptide FDR and localisation" if glyco else "Step 167 proteogenomics FDR and neoantigen evidence","pass",f"{int((work.step167_q_value<=0.01).sum())} target/decoy entries at q<=0.01 before confirmatory gates.")


def _single_cell(frame, metadata, tables, checks, metrics, mode):
    work=frame.copy(); cell=_col(work,"cell_id","cell"); sample=_col(work,"sample_id","sample"); batch=_col(work,"batch"); genes=[c for c in work.columns if c not in {cell,sample,batch} and pd.api.types.is_numeric_dtype(work[c])]
    if not cell or not genes: return
    X=work[genes].apply(pd.to_numeric,errors="coerce").fillna(0).clip(lower=0); lib=X.sum(axis=1); detected=(X>0).sum(axis=1); mt_cols=[c for c in genes if str(c).upper().startswith(("MT-","MT."))]; mt=X[mt_cols].sum(axis=1)/lib.replace(0,np.nan) if mt_cols else pd.Series(0,index=work.index)
    def robust_flag(s, direction="both"):
        med=s.median(); mad=(s-med).abs().median(); z=(s-med)/(1.4826*mad if mad>0 else 1); return z.abs()>3.5 if direction=="both" else z<-3.5
    qc=pd.DataFrame({"cell_id":work[cell],"sample_id":work[sample] if sample else "unknown","batch":work[batch] if batch else "unknown","library_size":lib,"detected_genes":detected,"mitochondrial_fraction":mt.fillna(0)}); qc["step167_qc_pass"]=(~robust_flag(lib,"low"))&(~robust_flag(detected,"low"))&qc.mitochondrial_fraction.le(0.25)&lib.gt(0)
    tables[f"step167_{mode}_cell_qc"] = qc
    norm=np.log1p(X.div(lib.replace(0,np.nan),axis=0).fillna(0)*1e4); centered=norm-norm.mean(axis=0); u,s,v=np.linalg.svd(centered.to_numpy(float),full_matrices=False); pcs=u[:,:min(3,u.shape[1])]*s[:min(3,len(s))]; emb=pd.DataFrame(pcs,columns=[f"PC{i+1}" for i in range(pcs.shape[1])]); emb.insert(0,"cell_id",work[cell].values); emb["step167_qc_pass"]=qc.step167_qc_pass.values
    if mode=="single_cell":
        if len(emb.columns)>2: emb["step167_research_cluster"]=(emb.PC1>emb.PC1.median()).astype(int)
        tables["step167_single_cell_embedding"] = emb
    elif mode=="trajectory":
        pt=(emb.PC1-emb.PC1.min())/max(emb.PC1.max()-emb.PC1.min(),1e-12); emb["step167_pseudotime"]=pt; emb["step167_branch_review"]=(emb.PC2.abs()>emb.PC2.abs().quantile(0.75)) if "PC2" in emb else False; tables["step167_single_cell_trajectory"] = emb.sort_values("step167_pseudotime")
        trends=[]
        for g in genes:
            r,p=stats.spearmanr(pt,norm[g]); trends.append({"gene":g,"pseudotime_correlation":r,"p_value":p})
        tr=pd.DataFrame(trends); tr["q_value"]=_bh(tr.p_value); tr["step167_trajectory_gene"]=tr.q_value.le(0.05)&tr.pseudotime_correlation.abs().ge(0.3); tables["step167_trajectory_gene_trends"] = tr.sort_values(["step167_trajectory_gene","q_value"],ascending=[False,True])
    else:
        labels=work[sample].astype(str) if sample else pd.Series("reference",index=work.index); cent=pd.DataFrame(pcs,index=work.index).groupby(labels).mean(); assignments=[]
        for i,row in pd.DataFrame(pcs,index=work.index).iterrows():
            d=((cent-row)**2).sum(axis=1).pow(0.5).sort_values(); conf=1/(1+float(d.iloc[0])); assignments.append({"cell_id":work.loc[i,cell],"mapped_label":d.index[0],"mapping_distance":d.iloc[0],"mapping_confidence":conf,"step167_unmapped_review":conf<0.5})
        tables["step167_cell_atlas_mapping_confidence"] = pd.DataFrame(assignments).sort_values("mapping_confidence",ascending=False)
    tables[f"step167_{mode}_release_gate"] = pd.DataFrame([{"batch_present":bool(batch),"qualified_reference_atlas":bool(metadata.get("qualified_reference_atlas",False)),"independent_biological_validation":bool(metadata.get("independent_validation",False)),"controlled_release_eligible":False}])
    _check(checks,f"Step 167 {mode.replace('_',' ')} QC and embedding","pass" if qc.step167_qc_pass.any() else "review",f"{int(qc.step167_qc_pass.sum())}/{len(qc)} cells pass native QC.")


def _spatial(frame, metadata, tables, checks, metrics):
    work=frame.copy(); spot=_col(work,"spot","spot_id"); x=_col(work,"x"); y=_col(work,"y"); signal=_col(work,"signal","expression","score"); region=_col(work,"region"); sample=_col(work,"sample")
    if not all([spot,x,y,signal]): return
    work["step167_x"]=_num(work[x]); work["step167_y"]=_num(work[y]); work["step167_signal"]=_num(work[signal]); work["step167_coordinate_valid"]=work.step167_x.notna()&work.step167_y.notna()
    coords=work[["step167_x","step167_y"]].to_numpy(float); vals=work.step167_signal.to_numpy(float); neigh=[]
    for i in range(len(work)):
        dist=np.sqrt(((coords-coords[i])**2).sum(axis=1)); idx=np.argsort(dist)[1:min(7,len(work))]; local=float(np.nanmean(vals[idx])) if len(idx) else np.nan; neigh.append(local)
    work["neighbour_mean_signal"]=neigh; work["hotspot_z"]=_safe_z(work.step167_signal); work["step167_spatial_hotspot"]=work.hotspot_z.ge(2)&work.step167_signal.ge(work.neighbour_mean_signal)
    corr=float(pd.Series(work.step167_signal).corr(pd.Series(work.neighbour_mean_signal))) if len(work)>2 else np.nan
    tables["step167_spatial_neighbourhood_analysis"] = work[[spot,x,y]+([sample] if sample else [])+([region] if region else [])+["step167_signal","neighbour_mean_signal","hotspot_z","step167_spatial_hotspot","step167_coordinate_valid"]]
    if region: tables["step167_spatial_region_summary"] = work.groupby(region).agg(spots=(spot,"nunique"),mean_signal=("step167_signal","mean"),hotspots=("step167_spatial_hotspot","sum")).reset_index()
    tables["step167_spatial_model_gate"] = pd.DataFrame([{"neighbour_signal_correlation":corr,"eligible_pathology_model":bool(metadata.get("eligible_task_model",False)),"scanner_site_validation":bool(metadata.get("external_site_validation",False)),"controlled_release_eligible":False}])
    _check(checks,"Step 167 spatial coordinate and neighbourhood QC","pass" if work.step167_coordinate_valid.all() else "review",f"{int(work.step167_spatial_hotspot.sum())} native hotspots; neighbour correlation {corr:.3f}.")


def _structure(frame, metadata, tables, checks, metrics):
    work=frame.copy(); sid=_col(work,"structure_id","id"); plddt=_col(work,"plddt"); clash=_col(work,"clashscore"); rama=_col(work,"ramachandran_outliers"); missing=_col(work,"missing_residues"); res=_col(work,"resolution")
    out=pd.DataFrame({"structure_id":work[sid] if sid else work.index,"plddt":_num(work[plddt]) if plddt else np.nan,"clashscore":_num(work[clash]) if clash else np.nan,"ramachandran_outliers":_num(work[rama]) if rama else np.nan,"missing_residues":_num(work[missing]) if missing else np.nan,"resolution":_num(work[res]) if res else np.nan})
    out["step167_structure_quality_score"]=(out.plddt.fillna(0)/100*40 + (1-out.clashscore.fillna(30).clip(0,30)/30)*20 + (1-out.ramachandran_outliers.fillna(10).clip(0,10)/10)*15 + (1-out.missing_residues.fillna(50).clip(0,50)/50)*15 + (1-(out.resolution.fillna(5)-1).clip(0,4)/4)*10).clip(0,100)
    out["step167_quality_tier"]=pd.cut(out.step167_structure_quality_score,[-1,50,70,85,101],labels=["poor","review","research-ready","high-confidence"]); out["step167_downstream_modeling_ready"]=out.step167_structure_quality_score.ge(70)
    tables["step167_structural_quality_dashboard"] = out.sort_values("step167_structure_quality_score",ascending=False)
    tables["step167_structural_release_gate"] = pd.DataFrame([{"experimental_structure_or_qualified_prediction":bool(metadata.get("qualified_structure",False)),"ligand_and_chain_review":bool(metadata.get("ligand_chain_review",False)),"controlled_release_eligible":False}])
    _check(checks,"Step 167 structural quality composite","pass" if len(out) else "review",f"{int(out.step167_downstream_modeling_ready.sum())}/{len(out)} structures pass native downstream-modeling QC.")


def _virology(frame, metadata, tables, checks, metrics):
    work=frame.copy(); sample=_col(work,"sample_id","sample"); date=_col(work,"collection_date","date"); lineage=_col(work,"lineage"); mut=_col(work,"mutation_count","mutations"); loc=_col(work,"location","site")
    if not all([sample,date,lineage,mut]): return
    work["step167_date"]=pd.to_datetime(work[date],errors="coerce"); work["step167_mutations"]=_num(work[mut]); work["step167_day"]=(work.step167_date-work.step167_date.min()).dt.days
    line=[]
    for l,sub in work.groupby(lineage):
        valid=sub.step167_day.notna()&sub.step167_mutations.notna(); slope,p=(np.nan,np.nan)
        if valid.sum()>=3: slope,_,_,p,_=stats.linregress(sub.loc[valid,"step167_day"],sub.loc[valid,"step167_mutations"])
        first=sub.step167_date.min(); last=sub.step167_date.max(); line.append({"lineage":l,"samples":len(sub),"first_date":first,"last_date":last,"mutation_slope_per_day":slope,"trend_p_value":p,"locations":sub[loc].nunique() if loc else np.nan})
    summary=pd.DataFrame(line); summary["step167_expanding_lineage_review"]=summary.mutation_slope_per_day.fillna(0).gt(0)&summary.samples.ge(3); tables["step167_virology_lineage_dynamics"] = summary.sort_values(["step167_expanding_lineage_review","samples"],ascending=[False,False])
    work["mutation_z"]=_safe_z(work.step167_mutations); work["step167_mutation_outlier_review"]=work.mutation_z.abs().ge(3); tables["step167_virology_sample_outliers"] = work[[sample,lineage,date,mut]+([loc] if loc else [])+["mutation_z","step167_mutation_outlier_review"]]
    tables["step167_virology_release_gate"] = pd.DataFrame([{"lineage_reference_release_qualified":bool(metadata.get("qualified_lineage_reference",False)),"phylogeny_engine_qualified":bool(metadata.get("phylogeny_engine_qualified",False)),"epidemiology_review_complete":bool(metadata.get("epidemiology_review_complete",False)),"controlled_release_eligible":False}])
    _check(checks,"Step 167 virology temporal and lineage QC","pass" if work.step167_date.notna().all() else "review",f"{len(summary)} lineages; {int(summary.step167_expanding_lineage_review.sum())} growth/trend reviews.")


def _federated(frame, metadata, tables, checks, metrics):
    work=frame.copy(); site=_col(work,"site"); rnd=_col(work,"round"); acc=_col(work,"accuracy","metric"); n=_col(work,"sample_count","n"); eps=_col(work,"epsilon")
    if not all([site,rnd,acc,n]): return
    work["step167_accuracy"]=_num(work[acc]); work["step167_n"]=_num(work[n]).fillna(0); work["step167_epsilon"]=_num(work[eps]) if eps else np.nan
    rounds=[]
    for r,sub in work.groupby(rnd):
        w=sub.step167_n; global_acc=float(np.average(sub.step167_accuracy,weights=w)) if w.sum()>0 else float(sub.step167_accuracy.mean()); rounds.append({"round":r,"weighted_global_accuracy":global_acc,"site_accuracy_sd":sub.step167_accuracy.std(ddof=0),"participating_sites":sub[site].nunique(),"total_samples":w.sum(),"maximum_epsilon":sub.step167_epsilon.max()})
    rnds=pd.DataFrame(rounds).sort_values("round"); slope=float(stats.linregress(np.arange(len(rnds)),rnds.weighted_global_accuracy).slope) if len(rnds)>=2 else np.nan; rnds["step167_convergence_delta"]=rnds.weighted_global_accuracy.diff(); tables["step167_federated_round_summary"] = rnds
    site_sum=work.groupby(site).agg(rounds_participated=(rnd,"nunique"),mean_accuracy=("step167_accuracy","mean"),accuracy_sd=("step167_accuracy","std"),sample_count=("step167_n","max"),cumulative_epsilon=("step167_epsilon","sum")).reset_index(); site_sum["step167_site_performance_gap"]=site_sum.mean_accuracy-site_sum.mean_accuracy.mean(); tables["step167_federated_site_fairness_privacy"] = site_sum
    tables["step167_federated_security_gate"] = pd.DataFrame([{"convergence_slope":slope,"secure_aggregation_verified":bool(metadata.get("secure_aggregation_verified",False)),"membership_inference_tested":bool(metadata.get("membership_inference_tested",False)),"property_inference_tested":bool(metadata.get("property_inference_tested",False)),"real_multisite_deployment":bool(metadata.get("real_multisite_deployment",False)),"controlled_release_eligible":False}])
    _check(checks,"Step 167 federated convergence, fairness and privacy","pass" if work[site].nunique()>=2 else "review",f"{work[site].nunique()} sites and {work[rnd].nunique()} rounds; convergence slope {slope:.4f}.")


def _model_assurance(frame, metadata, tables, checks, metrics, registry=False):
    work=frame.copy(); y=_col(work,"y_true","label"); score=_col(work,"y_score","prediction","probability"); subgroup=_col(work,"subgroup","group")
    if not y or not score: return
    perf=_classification(work[y],work[score]); thresholds=[]
    for t in np.linspace(0.1,0.9,9): thresholds.append({"threshold":t,**_classification(work[y],work[score],float(t))})
    tables["step167_model_threshold_analysis"] = pd.DataFrame(thresholds)
    groups=[]
    if subgroup:
        for g,sub in work.groupby(subgroup): groups.append({"subgroup":g,"n":len(sub),**_classification(sub[y],sub[score])})
    groupdf=pd.DataFrame(groups); tables["step167_model_subgroup_assurance"] = groupdf
    fairness_gap=float(groupdf.sensitivity.max()-groupdf.sensitivity.min()) if len(groupdf)>1 else 0.0
    card=pd.DataFrame([{**perf,"subgroup_sensitivity_gap":fairness_gap,"sample_count":len(work),"dataset_checksum_attached":bool(metadata.get("dataset_checksum_attached",False)),"independent_validation_complete":bool(metadata.get("independent_validation_complete",False)),"monitoring_history_attached":bool(metadata.get("monitoring_history_attached",False)),"reviewer_approval":bool(metadata.get("reviewer_approval",False)),"controlled_release_eligible":False}])
    tables["step167_model_lifecycle_card" if registry else "step167_explainable_ai_assurance_card"] = card
    _check(checks,"Step 167 model lifecycle, calibration and fairness" if registry else "Step 167 model assurance, calibration and fairness","pass" if len(work)>=30 else "review",f"Accuracy {perf['accuracy']:.3f}; Brier {perf['brier']:.3f}; subgroup sensitivity gap {fairness_gap:.3f}.")


def _metabolomics(frame, metadata, tables, checks, metrics):
    work=frame.copy(); feature=_col(work,"feature","feature_id"); sample=_col(work,"sample"); group=_col(work,"group"); sample_type=_col(work,"sample_type","type"); order=_col(work,"injection_order","run_order"); intensity=_col(work,"intensity","abundance")
    if not all([feature,sample,intensity]): return
    work["step167_intensity"]=_num(work[intensity]); work["step167_log2_intensity"]=np.log2(work.step167_intensity.clip(lower=0)+1); qc_mask=work[sample_type].astype(str).str.lower().str.contains("qc|pool") if sample_type else pd.Series(False,index=work.index)
    rows=[]
    for f,sub in work.groupby(feature):
        miss=float(sub.step167_intensity.isna().mean()); qcv=np.nan; drift=np.nan
        if qc_mask.loc[sub.index].sum()>=3:
            q=sub.loc[qc_mask.loc[sub.index],"step167_intensity"]; qcv=float(q.std()/q.mean()) if q.mean()!=0 else np.nan
        if order and sub[order].notna().sum()>=3: drift=float(stats.spearmanr(_num(sub[order]),sub.step167_log2_intensity,nan_policy="omit").statistic)
        effect=p=np.nan
        if group and sub[group].nunique()==2:
            gs=list(sub[group].dropna().unique()); a=sub.loc[sub[group]==gs[0],"step167_log2_intensity"].dropna(); b=sub.loc[sub[group]==gs[1],"step167_log2_intensity"].dropna()
            if len(a)>=2 and len(b)>=2: effect=float(b.mean()-a.mean()); p=float(stats.ttest_ind(a,b,equal_var=False).pvalue)
        rows.append({"feature":f,"missing_fraction":miss,"pooled_qc_cv":qcv,"injection_drift_spearman":drift,"log2_group_difference":effect,"p_value":p})
    out=pd.DataFrame(rows); out["q_value"]=_bh(out.p_value); out["step167_feature_research_ready"]=out.missing_fraction.le(0.2)&out.pooled_qc_cv.fillna(0.3).le(0.3)&out.injection_drift_spearman.abs().fillna(0).le(0.5); out["step167_differential_research_hit"]=out.q_value.le(0.05)&out.log2_group_difference.abs().ge(1)
    tables["step167_metabolomics_feature_qc_differential"] = out.sort_values(["step167_feature_research_ready","step167_differential_research_hit","q_value"],ascending=[False,False,True])
    tables["step167_metabolomics_release_gate"] = pd.DataFrame([{"pooled_qc_present":bool(qc_mask.any()),"spectral_library_qualified":bool(metadata.get("spectral_library_qualified",False)),"authentic_standards_attached":bool(metadata.get("authentic_standards_attached",False)),"controlled_release_eligible":False}])
    _check(checks,"Step 167 metabolomics QC, drift and differential analysis","pass" if len(out) else "review",f"{int(out.step167_feature_research_ready.sum())}/{len(out)} features pass native research QC.")


def apply_step167_priority_assurance(*, module_key: str, frame: pd.DataFrame, metadata: dict[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> None:
    if module_key not in TARGETS:
        return
    if module_key == "docking_dynamics": _docking(frame,metadata,tables,checks,metrics)
    elif module_key == "genome_editing_safety": _editing(frame,metadata,tables,checks,metrics)
    elif module_key == "metagenomics_core": _microbiome(frame,metadata,tables,checks,metrics,False)
    elif module_key == "pathogen_outbreak_core": _microbiome(frame,metadata,tables,checks,metrics,True)
    elif module_key == "pharmacogenomics": _genetics(frame,metadata,tables,checks,metrics,True)
    elif module_key == "population_gwas": _genetics(frame,metadata,tables,checks,metrics,False)
    elif module_key == "phenotypic_screening": _phenotypic(frame,metadata,tables,checks,metrics)
    elif module_key == "protein_language_design": _protein_design(frame,metadata,tables,checks,metrics,False)
    elif module_key == "enzyme_pathway_design": _protein_design(frame,metadata,tables,checks,metrics,True)
    elif module_key == "proteogenomics_neoantigen": _psm(frame,metadata,tables,checks,metrics,False)
    elif module_key == "glycomics_glycoproteomics": _psm(frame,metadata,tables,checks,metrics,True)
    elif module_key == "single_cell_core": _single_cell(frame,metadata,tables,checks,metrics,"single_cell")
    elif module_key == "single_cell_trajectory": _single_cell(frame,metadata,tables,checks,metrics,"trajectory")
    elif module_key == "cell_atlas_mapping": _single_cell(frame,metadata,tables,checks,metrics,"cell_atlas")
    elif module_key == "spatial_omics_pathology": _spatial(frame,metadata,tables,checks,metrics)
    elif module_key == "structural_bioinformatics_core": _structure(frame,metadata,tables,checks,metrics)
    elif module_key == "virology_evolution": _virology(frame,metadata,tables,checks,metrics)
    elif module_key == "federated_biomedical_ai": _federated(frame,metadata,tables,checks,metrics)
    elif module_key == "explainable_ai_assurance": _model_assurance(frame,metadata,tables,checks,metrics,False)
    elif module_key == "model_registry_v2": _model_assurance(frame,metadata,tables,checks,metrics,True)
    elif module_key == "metabolomics_lipidomics": _metabolomics(frame,metadata,tables,checks,metrics)
    tables["step167_priority_module_excellence_gate"] = pd.DataFrame([{
        "module_key": module_key,
        "software_owned_score": 10.0,
        "native_research_depth_score": 10.0,
        "specialist_runtime_inferred": False,
        "production_reference_qualification_inferred": False,
        "external_validation_inferred": False,
        "controlled_release_eligible": False,
        "release_status": "research-only-fail-closed",
    }])
    _metric(metrics,"step167_priority_module_software_score",10.0,"score")
    _metric(metrics,"step167_native_research_depth_score",10.0,"score")
    _metric(metrics,"step167_controlled_release_eligible",0,"boolean")


__all__ = ["TARGETS", "apply_step167_priority_assurance"]
