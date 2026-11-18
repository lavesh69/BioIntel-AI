from __future__ import annotations

import hashlib
import math
import re
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.calibration import calibration_curve
from sklearn.decomposition import PCA
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
)
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import RobustScaler

from .assessment import bh_fdr
from .native_workflows import MAX_FEATURES, RANDOM_SEED, _check, _column, _metric, _numeric, _robust_z

def _pharmacovigilance(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    drug = _column(frame, "drug", "product", "medication", "active_ingredient")
    event = _column(frame, "event", "adverse_event", "reaction", "preferred_term")
    report = _column(frame, "report_id", "case_id", "id")
    if not (drug and event):
        _check(checks, "Drug-event schema", "fail", "Drug and event columns are required")
        return {}, ["Provide deduplicated report-level drug and event records."]
    work = frame[[drug, event] + ([report] if report else [])].dropna(subset=[drug, event]).copy()
    if report:
        work = work.drop_duplicates([report, drug, event])
    else:
        work = work.drop_duplicates()
    total = len(work)
    drug_counts = work[drug].value_counts()
    event_counts = work[event].value_counts()
    pair_counts = work.groupby([drug, event]).size().rename("a").reset_index()
    rows: list[dict[str, Any]] = []
    for item in pair_counts.itertuples(index=False):
        a = int(item.a)
        b = int(drug_counts[item[0]] - a)
        c = int(event_counts[item[1]] - a)
        d = int(total - a - b - c)
        if min(a, b, c, d) < 0:
            continue
        aa, bb, cc, dd = [value + 0.5 for value in (a, b, c, d)]
        ror = (aa * dd) / (bb * cc)
        se = math.sqrt(1 / aa + 1 / bb + 1 / cc + 1 / dd)
        log_ror = math.log(ror)
        low, high = math.exp(log_ror - 1.96 * se), math.exp(log_ror + 1.96 * se)
        prr = (aa / (aa + bb)) / (cc / (cc + dd))
        chi_square = (total * (a * d - b * c) ** 2 / max((a + b) * (c + d) * (a + c) * (b + d), 1)) if total else np.nan
        # Transparent normal-prior shrinkage proxy; deliberately not labelled MGPS/EBGM.
        prior_variance = float(metadata.get("log_ror_prior_variance", 0.25) or 0.25)
        shrinkage = prior_variance / (prior_variance + se * se)
        shrunk_log_ror = shrinkage * log_ror
        shrunk_ror_proxy = math.exp(shrunk_log_ror)
        rows.append({"drug": item[0], "event": item[1], "reports": a, "ror": ror, "ror_ci_low": low, "ror_ci_high": high, "prr": prr, "chi_square": chi_square, "shrunk_ror_proxy": shrunk_ror_proxy, "shrinkage_weight": shrinkage, "signal_flag": bool(a >= 3 and low > 1.0 and prr >= 2.0 and chi_square >= 4.0)})
    signals = pd.DataFrame(rows).sort_values(["signal_flag", "ror_ci_low", "reports"], ascending=[False, False, False]) if rows else pd.DataFrame()
    signal_count = int(signals["signal_flag"].sum()) if not signals.empty else 0
    duplicate_count = int(frame.duplicated([c for c in (report, drug, event) if c]).sum()) if report else int(frame.duplicated([drug, event]).sum())
    coding_version = metadata.get("coding_dictionary_version") or _column(frame, "meddra_version", "coding_version", "dictionary_version")
    exposure = _column(frame, "exposure", "patient_exposure", "prescriptions", "person_time")
    _check(checks, "Disproportionality calculation", "pass" if not signals.empty else "review", f"{len(signals):,} drug-event pairs")
    _check(checks, "Signal review", "review" if signal_count else "pass", f"{signal_count} statistical signals")
    _check(checks, "Duplicate-case audit", "review" if duplicate_count else "pass", f"{duplicate_count} duplicate source records")
    _check(checks, "Coding dictionary version", "pass" if coding_version else "review", str(coding_version or "Not supplied"))
    _check(checks, "Exposure denominator", "pass" if exposure else "review", exposure or "Not supplied; incidence cannot be estimated")
    _metric(metrics, "deduplicated_records", total, "records")
    _metric(metrics, "statistical_signals", signal_count, "drug-event pairs")
    return {"disproportionality_signals": signals.head(50_000)}, [
        "Spontaneous-report disproportionality does not estimate incidence or prove causality.",
        "Review duplicates, indication, co-medication, exposure denominator, coding version and clinical narratives. The shrinkage field is a transparent proxy, not MGPS/EBGM.",
    ]


def _privacy(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    configured = metadata.get("quasi_identifiers", [])
    quasi = [str(c) for c in configured if str(c) in frame.columns]
    if not quasi:
        candidates = [str(c) for c in frame.columns if frame[c].nunique(dropna=False) <= max(100, len(frame) // 4) and frame[c].nunique(dropna=False) > 1]
        quasi = candidates[:5]
    sensitive = str(metadata.get("sensitive_attribute", ""))
    if sensitive not in frame.columns:
        sensitive = _column(frame, "sensitive", "diagnosis", "outcome", "disease") or ""
    if not quasi:
        _check(checks, "Quasi-identifier selection", "fail", "No quasi-identifiers configured or inferred")
        return {}, ["Specify quasi-identifiers and the sensitive attribute in evidence metadata."]
    groups = frame.groupby(quasi, dropna=False).size().rename("equivalence_class_size").reset_index()
    k_min = int(groups["equivalence_class_size"].min()) if not groups.empty else 0
    unique_fraction = float((groups["equivalence_class_size"] == 1).sum() / max(len(groups), 1))
    _check(checks, "k-anonymity", "pass" if k_min >= 5 else "review", f"minimum k={k_min}")
    _metric(metrics, "minimum_k", k_min, "records")
    _metric(metrics, "unique_equivalence_class_fraction", unique_fraction, "fraction")
    diversity = pd.DataFrame()
    if sensitive:
        diversity = frame.groupby(quasi, dropna=False)[sensitive].nunique(dropna=False).rename("l_diversity").reset_index()
        l_min = int(diversity["l_diversity"].min()) if not diversity.empty else 0
        _check(checks, "l-diversity", "pass" if l_min >= 2 else "review", f"minimum l={l_min}")
        _metric(metrics, "minimum_l", l_min, "categories")
    else:
        _check(checks, "Sensitive attribute", "review", "Not configured")
    return {"equivalence_classes": groups.sort_values("equivalence_class_size").head(50_000), "diversity": diversity.sort_values("l_diversity").head(50_000) if not diversity.empty else diversity}, [
        "k-anonymity and l-diversity are incomplete privacy guarantees; test linkage and membership-inference risk.",
        "Apply the approved privacy policy and data-use agreement before sharing any derived dataset.",
    ]


def _bioprocess(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    time_col = _column(frame, "time", "timestamp", "elapsed_time", "process_time")
    batch = _column(frame, "batch", "batch_id", "reactor", "run")
    numeric = _numeric(frame, exclude=[c for c in (time_col,) if c])
    if not numeric:
        _check(checks, "Sensor schema", "fail", "No numeric sensor columns detected")
        return {}, ["Provide time-ordered sensor data and a batch/run identifier."]
    if time_col:
        time_values = pd.to_numeric(frame[time_col], errors="coerce")
        monotonic_failures = 0
        if batch:
            for _, subset in frame.assign(_time=time_values).groupby(batch):
                monotonic_failures += int((subset["_time"].diff().dropna() < 0).any())
        else:
            monotonic_failures = int((time_values.diff().dropna() < 0).any())
        _check(checks, "Time ordering", "review" if monotonic_failures else "pass", f"{monotonic_failures} batches/runs out of order")
    else:
        _check(checks, "Time ordering", "review", "Time column not detected")
    rows: list[dict[str, Any]] = []
    flags: list[pd.DataFrame] = []
    for column in numeric[:30]:
        values = pd.to_numeric(frame[column], errors="coerce")
        center = values.median()
        mad = (values - center).abs().median()
        sigma = 1.4826 * mad
        lower, upper = center - 3 * sigma, center + 3 * sigma
        out = (values < lower) | (values > upper)
        rows.append({"sensor": column, "median": float(center), "robust_sigma": float(sigma), "lower_control_limit": float(lower), "upper_control_limit": float(upper), "out_of_control": int(out.sum())})
        if out.any():
            subset = frame.loc[out, [c for c in (batch, time_col, column) if c]].copy()
            subset["sensor"] = column
            flags.append(subset.head(100))
    control = pd.DataFrame(rows)
    total_flags = int(control["out_of_control"].sum()) if not control.empty else 0
    _check(checks, "Robust control limits", "review" if total_flags else "pass", f"{total_flags} out-of-control values")
    _metric(metrics, "sensors", len(control), "sensors")
    _metric(metrics, "out_of_control_values", total_flags, "values")
    if batch:
        _metric(metrics, "batches", int(frame[batch].nunique(dropna=True)), "batches")
    return {"sensor_control_limits": control, "out_of_control_records": pd.concat(flags, ignore_index=True).head(5_000) if flags else pd.DataFrame()}, [
        "Interpret control limits by process phase and batch; do not combine incompatible operating regimes.",
        "Confirm mass balance, calibration, sensor maintenance and approved quality-system requirements.",
    ]


def _federated(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    site = _column(frame, "site", "site_id", "client")
    round_col = _column(frame, "round", "round_id", "iteration")
    metric_col = _column(frame, "metric", "score", "accuracy", "auc", "loss")
    n_col = _column(frame, "n", "samples", "sample_count", "weight")
    epsilon = _column(frame, "epsilon", "privacy_epsilon")
    if not (site and round_col and metric_col):
        _check(checks, "Federated round schema", "fail", "Site, round and metric/loss columns are required")
        return {}, ["Provide one record per site and round with sample weight and performance metric."]
    work = frame.copy()
    work["_metric"] = pd.to_numeric(work[metric_col], errors="coerce")
    work["_weight"] = pd.to_numeric(work[n_col], errors="coerce").fillna(1.0) if n_col else 1.0
    aggregated_rows: list[dict[str, Any]] = []
    for round_value, subset in work.groupby(round_col, sort=True):
        valid = subset["_metric"].notna() & subset["_weight"].gt(0)
        if not valid.any():
            continue
        mean = float(np.average(subset.loc[valid, "_metric"], weights=subset.loc[valid, "_weight"]))
        aggregated_rows.append({"round": round_value, "weighted_metric": mean, "participating_sites": int(subset.loc[valid, site].nunique()), "total_weight": float(subset.loc[valid, "_weight"].sum()), "site_std": float(subset.loc[valid, "_metric"].std(ddof=1))})
    aggregate = pd.DataFrame(aggregated_rows)
    site_summary = work.groupby(site)["_metric"].agg(["count", "mean", "std", "min", "max"]).reset_index()
    min_participation = int(aggregate["participating_sites"].min()) if not aggregate.empty else 0
    site_count = int(work[site].nunique())
    _check(checks, "Site participation", "review" if min_participation < site_count else "pass", f"minimum {min_participation}/{site_count} sites per round")
    _metric(metrics, "sites", site_count, "sites")
    _metric(metrics, "rounds", int(work[round_col].nunique()), "rounds")
    if epsilon:
        eps = pd.to_numeric(work[epsilon], errors="coerce")
        _metric(metrics, "maximum_reported_epsilon", float(eps.max()), "epsilon")
        _check(checks, "Privacy budget", "review" if eps.isna().any() else "pass", f"max epsilon={eps.max():.4g}")
    else:
        _check(checks, "Privacy budget", "review", "No epsilon/privacy-budget field detected")
    return {"round_aggregation": aggregate, "site_summary": site_summary}, [
        "A local weighted-average audit is not secure aggregation; use authenticated clients, threat modelling and privacy accounting.",
        "Validate the locked federated model independently across sites and clinically relevant subgroups.",
    ]


def _structural(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    compound = _column(frame, "compound", "ligand", "molecule", "candidate", "id")
    smiles = _column(frame, "smiles", "canonical_smiles", "structure")
    pose = _column(frame, "pose", "pose_id", "conformer")
    score = _column(frame, "docking_score", "score", "binding_energy", "affinity")
    rmsd = _column(frame, "rmsd", "pose_rmsd")
    strain = _column(frame, "strain", "strain_energy")
    descriptor_rows: list[dict[str, Any]] = []
    invalid_smiles = 0
    if smiles:
        try:
            from rdkit import Chem
            from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors

            for index, value in frame[smiles].items():
                molecule = Chem.MolFromSmiles(str(value))
                if molecule is None:
                    invalid_smiles += 1
                    continue
                mw = float(Descriptors.MolWt(molecule))
                logp = float(Crippen.MolLogP(molecule))
                hbd = int(Lipinski.NumHDonors(molecule))
                hba = int(Lipinski.NumHAcceptors(molecule))
                tpsa = float(rdMolDescriptors.CalcTPSA(molecule))
                rotors = int(Lipinski.NumRotatableBonds(molecule))
                violations = int(mw > 500) + int(logp > 5) + int(hbd > 5) + int(hba > 10)
                descriptor_rows.append(
                    {
                        "row_index": str(index),
                        "compound": str(frame.loc[index, compound]) if compound else str(index),
                        "canonical_smiles": Chem.MolToSmiles(molecule, canonical=True),
                        "molecular_weight": mw,
                        "logp": logp,
                        "hbd": hbd,
                        "hba": hba,
                        "tpsa": tpsa,
                        "rotatable_bonds": rotors,
                        "lipinski_violations": violations,
                    }
                )
        except Exception as exc:
            _check(checks, "RDKit descriptor engine", "review", f"Unavailable or failed: {type(exc).__name__}")
    descriptors = pd.DataFrame(descriptor_rows)
    if smiles:
        _check(checks, "SMILES parsing", "review" if invalid_smiles else "pass", f"{invalid_smiles} invalid structures")
        _metric(metrics, "valid_structures", len(descriptors), "molecules")
        if not descriptors.empty:
            violations = int((descriptors["lipinski_violations"] > 0).sum())
            _check(checks, "Rule-of-five triage", "review" if violations else "pass", f"{violations} molecules with ≥1 violation")
    else:
        _check(checks, "Chemical structure input", "review", "No SMILES column detected")
    score_table = pd.DataFrame()
    selected = [column for column in (compound, pose, score, rmsd, strain) if column]
    if selected:
        score_table = frame[selected].copy()
        if score:
            score_values = pd.to_numeric(score_table[score], errors="coerce")
            score_table["score_robust_z"] = _robust_z(score_values)
            _check(checks, "Score completeness", "review" if score_values.isna().any() else "pass", f"{int(score_values.isna().sum())} missing scores")
            _metric(metrics, "median_score", float(score_values.median()), "score units")
        if rmsd:
            rmsd_values = pd.to_numeric(score_table[rmsd], errors="coerce")
            poor = rmsd_values > 2.0
            _check(checks, "Pose RMSD", "review" if poor.any() else "pass", f"{int(poor.sum())} poses >2 Å/units")
        if compound and pose:
            duplicate = score_table.astype({compound: str, pose: str}).duplicated([compound, pose], keep=False)
            _check(checks, "Ligand-pose identity", "review" if duplicate.any() else "pass", f"{int(duplicate.sum())} duplicate pose keys")
    if descriptors.empty and score_table.empty:
        _check(checks, "Structural/ligand schema", "fail", "No structure or score columns detected")
    return {"molecular_descriptors": descriptors.head(100_000), "pose_score_qc": score_table.head(100_000)}, [
        "Descriptor and pose-score triage does not perform docking, dynamics or measured-affinity validation.",
        "Record receptor/ligand preparation, protonation, grid, seed, engine version, positive controls and experimental affinity.",
    ]


def _causal(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    instrument = _column(frame, "instrument", "variant", "snp", "rsid")
    bx = _column(frame, "beta_exposure", "beta_x", "exposure_beta")
    by = _column(frame, "beta_outcome", "beta_y", "outcome_beta")
    se_y = _column(frame, "se_outcome", "se_y", "outcome_se")
    se_x = _column(frame, "se_exposure", "se_x", "exposure_se")
    if not (bx and by and se_y):
        _check(checks, "Instrument-effect schema", "fail", "beta_exposure, beta_outcome and se_outcome are required")
        return {}, ["Provide harmonized instrument effects and standard errors."]
    work = frame[[column for column in (instrument, bx, by, se_y, se_x) if column]].copy()
    work["beta_exposure"] = pd.to_numeric(work[bx], errors="coerce")
    work["beta_outcome"] = pd.to_numeric(work[by], errors="coerce")
    work["se_outcome"] = pd.to_numeric(work[se_y], errors="coerce")
    valid = work["beta_exposure"].notna() & work["beta_outcome"].notna() & work["se_outcome"].gt(0) & work["beta_exposure"].abs().gt(1e-12)
    work = work.loc[valid].copy()
    if work.empty:
        _check(checks, "Instrument-effect schema", "fail", "No valid instruments")
        return {}, ["Check harmonization, effect alleles and standard errors."]
    work["wald_ratio"] = work["beta_outcome"] / work["beta_exposure"]
    work["wald_se"] = work["se_outcome"] / work["beta_exposure"].abs()
    work["weight"] = 1.0 / work["wald_se"].pow(2)
    ivw = float(np.average(work["wald_ratio"], weights=work["weight"]))
    ivw_se = float(math.sqrt(1.0 / work["weight"].sum()))
    z_value = ivw / ivw_se if ivw_se > 0 else np.nan
    p_value = float(2 * stats.norm.sf(abs(z_value))) if np.isfinite(z_value) else np.nan
    q = float(np.sum(work["weight"] * (work["wald_ratio"] - ivw) ** 2))
    q_p = float(stats.chi2.sf(q, max(len(work) - 1, 1)))
    summary = pd.DataFrame(
        [
            {
                "instruments": len(work),
                "ivw_estimate": ivw,
                "ivw_se": ivw_se,
                "z": z_value,
                "p_value": p_value,
                "cochran_q": q,
                "heterogeneity_p": q_p,
            }
        ]
    )
    _check(checks, "Instrument count", "pass" if len(work) >= 3 else "review", f"{len(work)} valid instruments")
    _check(checks, "Heterogeneity", "review" if q_p < 0.05 else "pass", f"Q p={q_p:.4g}")
    if se_x:
        work["se_exposure"] = pd.to_numeric(work[se_x], errors="coerce")
        work["f_statistic"] = (work["beta_exposure"] / work["se_exposure"]).pow(2)
        weak = work["f_statistic"] < 10
        _check(checks, "Instrument strength", "review" if weak.any() else "pass", f"{int(weak.sum())} instruments F<10")
    else:
        _check(checks, "Instrument strength", "review", "Exposure standard errors not detected")
    _metric(metrics, "ivw_estimate", ivw, "effect units")
    _metric(metrics, "ivw_p_value", p_value, "p-value")
    return {"instrument_estimates": work.head(100_000), "causal_summary": summary}, [
        "Association-based causal estimates depend on exclusion restriction, exchangeability and instrument-relevance assumptions.",
        "Review harmonization, pleiotropy, weak instruments, heterogeneity, directionality and independent sensitivity analyses.",
    ]


def _network(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    source = _column(frame, "source", "source_id", "node_a", "from", "subject")
    target = _column(frame, "target", "target_id", "node_b", "to", "object")
    score = _column(frame, "score", "confidence", "weight")
    evidence = _column(frame, "evidence", "evidence_id", "citation", "reference")
    relation = _column(frame, "relation", "edge_type", "predicate", "interaction")
    if not (source and target):
        _check(checks, "Edge-list schema", "fail", "Source and target columns are required")
        return {}, ["Provide an edge list with source, target and evidence/provenance fields."]
    edges = frame[[column for column in (source, target, relation, score, evidence) if column]].dropna(subset=[source, target]).copy()
    duplicate = edges.astype({source: str, target: str}).duplicated([source, target] + ([relation] if relation else []), keep=False)
    self_loops = edges[source].astype(str).eq(edges[target].astype(str))
    _check(checks, "Duplicate edges", "review" if duplicate.any() else "pass", f"{int(duplicate.sum())} duplicate edge rows")
    _check(checks, "Self loops", "review" if self_loops.any() else "pass", f"{int(self_loops.sum())} self loops")
    nodes = sorted(set(edges[source].astype(str)) | set(edges[target].astype(str)))
    parent = {node: node for node in nodes}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    degree: dict[str, int] = {node: 0 for node in nodes}
    for a, b in zip(edges[source].astype(str), edges[target].astype(str)):
        union(a, b)
        degree[a] += 1
        degree[b] += 1
    component_map = {node: find(node) for node in nodes}
    component_sizes = pd.Series(component_map).value_counts()
    node_table = pd.DataFrame(
        {
            "node": nodes,
            "degree": [degree[node] for node in nodes],
            "component": [component_map[node] for node in nodes],
            "component_size": [int(component_sizes[component_map[node]]) for node in nodes],
        }
    ).sort_values(["degree", "component_size"], ascending=False)
    if evidence:
        coverage = float(edges[evidence].notna().mean())
        _check(checks, "Edge evidence coverage", "pass" if coverage >= 0.95 else "review", f"coverage={coverage:.1%}")
        _metric(metrics, "edge_evidence_coverage", coverage, "fraction")
    else:
        _check(checks, "Edge evidence coverage", "review", "Evidence/citation column not detected")
    _metric(metrics, "nodes", len(nodes), "nodes")
    _metric(metrics, "edges", len(edges), "edges")
    _metric(metrics, "connected_components", int(component_sizes.size), "components")
    return {"node_centrality": node_table.head(100_000), "edge_audit": edges.head(100_000)}, [
        "Network topology and confidence scores do not establish causal or physical interaction.",
        "Pin ontology/reference releases, retain edge-level evidence and review contradictory or duplicated assertions.",
    ]


def _sequence(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    sequence = _column(frame, "sequence", "seq", "guide", "guide_rna", "peptide", "protein_sequence", "heavy_sequence", "dna_sequence")
    if not sequence:
        _check(checks, "Sequence column", "fail", "No sequence-like column detected")
        return {}, ["Provide a sequence/guide/peptide/protein sequence column."]
    seqs = frame[sequence].fillna("").astype(str).str.upper().str.replace(r"\s+", "", regex=True)
    rows: list[dict[str, Any]] = []
    for index, seq in seqs.items():
        dna_fraction = sum(base in "ACGTUN" for base in seq) / max(len(seq), 1)
        is_nucleic = dna_fraction >= 0.90
        alphabet = set("ACGTUNRYKMSWBDHV-") if is_nucleic else set("ACDEFGHIKLMNPQRSTVWYBXZJUO*-")
        invalid = sorted(set(seq) - alphabet)
        if is_nucleic:
            canonical = re.sub(r"[^ACGT]", "", seq)
            gc = (canonical.count("G") + canonical.count("C")) / max(len(canonical), 1)
            homopolymer = max((len(match.group(0)) for match in re.finditer(r"(.)\1+", canonical)), default=1)
            liability = int(gc < 0.25 or gc > 0.75) + int(homopolymer >= 8) + int("GGGG" in canonical)
            hydrophobic = np.nan
            charge = np.nan
        else:
            canonical = re.sub(r"[^ACDEFGHIKLMNPQRSTVWY]", "", seq)
            gc = np.nan
            homopolymer = max((len(match.group(0)) for match in re.finditer(r"(.)\1+", canonical)), default=1)
            hydrophobic = sum(canonical.count(aa) for aa in "AILMFWVY") / max(len(canonical), 1)
            charge = (canonical.count("K") + canonical.count("R") + 0.1 * canonical.count("H")) - (canonical.count("D") + canonical.count("E"))
            motifs = ("NG", "NS", "DG", "DP", "DD", "DS", "NT", "NN", "PP")
            liability = sum(canonical.count(motif) for motif in motifs) + canonical.count("M") + canonical.count("W") + int(hydrophobic > 0.55)
        rows.append({"row_index": str(index), "sequence_length": len(seq), "sequence_type": "nucleic" if is_nucleic else "protein", "invalid_characters": "".join(invalid), "gc_fraction": gc, "max_homopolymer": homopolymer, "hydrophobic_fraction": hydrophobic, "net_charge_proxy": charge, "liability_score": int(liability), "sequence_sha256": hashlib.sha256(seq.encode()).hexdigest()})
    audit = pd.DataFrame(rows)
    invalid_count = int(audit["invalid_characters"].astype(bool).sum())
    duplicate_count = int(audit["sequence_sha256"].duplicated(keep=False).sum())
    high_liability = int((audit["liability_score"] >= 4).sum())
    _check(checks, "Sequence alphabet", "review" if invalid_count else "pass", f"{invalid_count} sequences with invalid characters")
    _check(checks, "Sequence duplication", "review" if duplicate_count else "pass", f"{duplicate_count} duplicate sequence rows")
    _check(checks, "Sequence liability screen", "review" if high_liability else "pass", f"{high_liability} high-liability candidates")
    _metric(metrics, "sequences", len(audit), "sequences")
    _metric(metrics, "median_sequence_length", float(audit["sequence_length"].median()), "residues/bases")
    return {"sequence_audit": audit.head(100_000)}, [
        "Built-in composition/liability screening is a transparent prioritisation aid, not a structure, specificity, efficacy or safety assay.",
        "Use specialist reference databases and independent experimental validation before release decisions.",
    ]


def _multiomics(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    sample = _column(frame, "sample", "sample_id", "cell", "cell_id", "subject")
    batch = _column(frame, "batch", "batch_id", "site", "platform")
    group = _column(frame, "group", "condition", "phenotype", "cell_type")
    numeric = _numeric(frame)
    if len(numeric) < 2:
        _check(checks, "Numeric feature matrix", "fail", "At least two numeric features are required")
        return {}, ["Provide a sample-by-feature table with metadata columns."]
    matrix = frame[numeric[:MAX_FEATURES]].apply(pd.to_numeric, errors="coerce")
    missing = matrix.isna().mean().sort_values(ascending=False).rename_axis("feature").reset_index(name="missing_fraction")
    retained = [column for column in matrix.columns if matrix[column].notna().mean() >= 0.80 and matrix[column].nunique(dropna=True) > 1]
    _check(checks, "Feature missingness", "review" if (missing["missing_fraction"] > 0.20).any() else "pass", f"{int((missing['missing_fraction'] > 0.20).sum())} features >20% missing")
    pca_table = pd.DataFrame()
    loadings = pd.DataFrame()
    if len(retained) >= 2 and len(matrix) >= 4:
        imputed = matrix[retained].fillna(matrix[retained].median())
        scaled = RobustScaler().fit_transform(imputed)
        components = min(10, len(retained), len(imputed) - 1)
        model = PCA(n_components=components, random_state=RANDOM_SEED)
        scores = model.fit_transform(scaled)
        pca_table = pd.DataFrame(scores, columns=[f"PC{i+1}" for i in range(components)], index=frame.index)
        for col in (sample, batch, group):
            if col:
                pca_table[col] = frame.loc[pca_table.index, col].astype(str)
        loadings = pd.DataFrame(model.components_.T, index=retained, columns=[f"PC{i+1}" for i in range(components)]).rename_axis("feature").reset_index()
        _metric(metrics, "pc1_explained_variance", float(model.explained_variance_ratio_[0]), "fraction")
        _metric(metrics, "pc1_pc2_explained_variance", float(model.explained_variance_ratio_[:2].sum()), "fraction")
        _check(checks, "Robust PCA", "pass", f"{components} components from {len(retained)} retained features")
    else:
        _check(checks, "Robust PCA", "review", "Insufficient complete/variable features")
    if sample:
        _metric(metrics, "samples_or_cells", int(frame[sample].nunique(dropna=True)), "entities")
    if batch:
        _metric(metrics, "batches", int(frame[batch].nunique(dropna=True)), "batches")
        _check(checks, "Batch metadata", "pass", batch)
    else:
        _check(checks, "Batch metadata", "review", "No batch/platform/site column detected")
    return {"feature_missingness": missing, "pca_scores": pca_table.head(50_000), "pca_loadings": loadings}, [
        "Inspect PCA and missingness before correction; retain raw values and avoid removing biological signal.",
        "Use biological replicates and sample/subject-level inference rather than treating cells/features as independent replicates.",
    ]


def _model_assurance(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    truth = _column(frame, "y_true", "truth", "actual", "label", "outcome")
    score = _column(frame, "y_score", "probability", "score", "prediction_probability", "predicted_risk")
    prediction = _column(frame, "prediction", "y_pred", "predicted")
    subgroup = _column(frame, "subgroup", "group", "sex", "site", "ancestry")
    if not truth or not (score or prediction):
        _check(checks, "Prediction schema", "fail", "Truth and score/prediction columns are required")
        return {}, ["Provide held-out truth and prediction records; include subgroup/site fields where applicable."]
    y_raw = frame[truth]
    y_numeric = pd.to_numeric(y_raw, errors="coerce")
    binary = set(y_numeric.dropna().unique()).issubset({0, 1}) and y_numeric.notna().sum() >= 5
    summary_rows: list[dict[str, Any]] = []
    calibration = pd.DataFrame()
    if binary and score:
        y = y_numeric
        s = pd.to_numeric(frame[score], errors="coerce")
        valid = y.notna() & s.notna()
        y, s = y[valid].astype(int), s[valid].clip(0, 1)
        auc = roc_auc_score(y, s) if y.nunique() == 2 else np.nan
        brier = brier_score_loss(y, s)
        predicted = (s >= float(metadata.get("threshold", 0.5))).astype(int)
        summary_rows.append({"metric": "roc_auc", "value": auc})
        summary_rows.append({"metric": "brier_score", "value": brier})
        summary_rows.append({"metric": "balanced_accuracy", "value": balanced_accuracy_score(y, predicted)})
        fraction_positive, mean_predicted = calibration_curve(y, s, n_bins=min(10, max(3, len(y) // 20)), strategy="quantile")
        calibration = pd.DataFrame({"mean_predicted": mean_predicted, "observed_fraction": fraction_positive})
        _metric(metrics, "roc_auc", auc, "fraction")
        _metric(metrics, "brier_score", brier, "score")
        _check(checks, "Discrimination", "pass" if np.isfinite(auc) and auc >= 0.70 else "review", f"AUC={auc:.3f}" if np.isfinite(auc) else "Not estimable")
        _check(checks, "Calibration", "pass" if brier <= 0.20 else "review", f"Brier={brier:.3f}")
    else:
        y = pd.to_numeric(frame[truth], errors="coerce")
        p_col = score or prediction
        p = pd.to_numeric(frame[p_col], errors="coerce")
        valid = y.notna() & p.notna()
        mae = mean_absolute_error(y[valid], p[valid]) if valid.any() else np.nan
        rmse = math.sqrt(mean_squared_error(y[valid], p[valid])) if valid.any() else np.nan
        summary_rows.extend([{"metric": "mae", "value": mae}, {"metric": "rmse", "value": rmse}])
        _metric(metrics, "mae", mae, "outcome units")
        _metric(metrics, "rmse", rmse, "outcome units")
        _check(checks, "Regression performance", "pass" if valid.sum() >= 20 else "review", f"{int(valid.sum())} evaluable records")
    subgroup_table = pd.DataFrame()
    if subgroup:
        rows: list[dict[str, Any]] = []
        for value, subset in frame.groupby(subgroup, dropna=False):
            if len(subset) < 5:
                rows.append({"subgroup": str(value), "n": len(subset), "status": "small"})
                continue
            if binary and score:
                yy = pd.to_numeric(subset[truth], errors="coerce")
                ss = pd.to_numeric(subset[score], errors="coerce")
                valid = yy.notna() & ss.notna()
                auc_value = roc_auc_score(yy[valid], ss[valid]) if valid.sum() >= 5 and yy[valid].nunique() == 2 else np.nan
                rows.append({"subgroup": str(value), "n": int(valid.sum()), "auc": auc_value, "brier": brier_score_loss(yy[valid], ss[valid].clip(0, 1)) if valid.any() else np.nan, "status": "review"})
            else:
                rows.append({"subgroup": str(value), "n": len(subset), "status": "review"})
        subgroup_table = pd.DataFrame(rows)
        small = int((subgroup_table["n"] < 20).sum()) if not subgroup_table.empty else 0
        _check(checks, "Subgroup assurance", "review" if small else "pass", f"{small} subgroups with n<20")
    else:
        _check(checks, "Subgroup assurance", "review", "No subgroup/site column detected")
    return {"performance": pd.DataFrame(summary_rows), "calibration": calibration, "subgroup_performance": subgroup_table}, [
        "Evaluate only on a locked held-out cohort and inspect calibration, subgroups, site drift and OOD behaviour.",
        "Explanations and correlations describe model behaviour; they do not establish biological causality or clinical utility.",
    ]


def _trial(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    subject = _column(frame, "subject", "subject_id", "sample", "participant", "id")
    arm = _column(frame, "arm", "group", "treatment", "condition")
    outcome = _column(frame, "outcome", "response", "value", "endpoint")
    if not (arm and outcome):
        _check(checks, "Trial/cohort schema", "fail", "Arm/group and outcome columns are required")
        return {}, ["Provide one record per subject with arm assignment and outcome."]
    work = frame.copy()
    if subject:
        duplicates = work[subject].astype(str).duplicated(keep=False)
        _check(checks, "Subject uniqueness", "review" if duplicates.any() else "pass", f"{int(duplicates.sum())} duplicate subject rows")
    counts = work[arm].astype(str).value_counts().rename_axis("arm").reset_index(name="n")
    imbalance = counts["n"].max() / max(counts["n"].min(), 1) if len(counts) else np.nan
    _check(checks, "Arm balance", "pass" if np.isfinite(imbalance) and imbalance <= 1.25 else "review", f"max/min ratio={imbalance:.3f}" if np.isfinite(imbalance) else "Not estimable")
    _metric(metrics, "arms", len(counts), "arms")
    _metric(metrics, "participants", len(work), "records")
    outcome_numeric = pd.to_numeric(work[outcome], errors="coerce")
    effect_table = pd.DataFrame()
    if work[arm].nunique() == 2 and outcome_numeric.notna().mean() >= 0.80:
        labels = list(work[arm].dropna().unique())
        a = outcome_numeric[work[arm] == labels[0]].dropna()
        b = outcome_numeric[work[arm] == labels[1]].dropna()
        test = stats.ttest_ind(a, b, equal_var=False, nan_policy="omit") if min(len(a), len(b)) >= 2 else None
        pooled = math.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / max(len(a) + len(b) - 2, 1)) if min(len(a), len(b)) >= 2 else np.nan
        effect = (b.mean() - a.mean()) / pooled if np.isfinite(pooled) and pooled > 0 else np.nan
        effect_table = pd.DataFrame([{"arm_a": labels[0], "arm_b": labels[1], "n_a": len(a), "n_b": len(b), "mean_a": float(a.mean()), "mean_b": float(b.mean()), "difference": float(b.mean() - a.mean()), "standardized_effect": effect, "p_value": float(test.pvalue) if test else np.nan}])
        _check(checks, "Exploratory arm comparison", "pass" if test else "review", f"p={test.pvalue:.4g}" if test else "Insufficient records")
    else:
        _check(checks, "Exploratory arm comparison", "review", "Exactly two arms with numeric outcome not detected")
    return {"arm_balance": counts, "effect_estimate": effect_table}, [
        "Prespecify sample-size assumptions, endpoints, missing-data handling, randomization and multiplicity controls.",
        "Exploratory effect estimates are not a substitute for a locked statistical analysis plan or independent review.",
    ]


def _surveillance(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    sample = _column(frame, "sample", "sample_id", "isolate", "isolate_id")
    feature = _column(frame, "taxon", "organism", "pathogen", "feature", "gene", "amr_gene", "strain")
    value = _column(frame, "abundance", "count", "reads", "relative_abundance", "coverage", "call")
    source = _column(frame, "source", "site", "location", "environment")
    if not (sample and feature):
        _check(checks, "Surveillance schema", "fail", "Sample/isolate and feature/taxon columns are required")
        return {}, ["Provide sample/isolate-level taxon, AMR or feature observations."]
    work = frame.copy()
    if value:
        work["_value"] = pd.to_numeric(work[value], errors="coerce").fillna(0.0)
    else:
        work["_value"] = 1.0
    prevalence = work.groupby(feature).agg(samples=(sample, "nunique"), total_signal=("_value", "sum"), median_signal=("_value", "median")).reset_index()
    total_samples = int(work[sample].nunique())
    prevalence["prevalence"] = prevalence["samples"] / max(total_samples, 1)
    duplicates = int(work.astype({sample: str, feature: str}).duplicated([sample, feature]).sum())
    _check(checks, "Sample-feature uniqueness", "review" if duplicates else "pass", f"{duplicates} duplicate pairs")
    _metric(metrics, "samples_or_isolates", total_samples, "samples")
    _metric(metrics, "features_or_taxa", int(work[feature].nunique()), "features")
    if source:
        _metric(metrics, "sources_or_sites", int(work[source].nunique()), "sites")
    else:
        _check(checks, "Source/site metadata", "review", "Not detected")
    negative = _column(frame, "negative_control", "is_negative_control", "control_type")
    _check(checks, "Negative-control metadata", "pass" if negative else "review", negative or "Not detected")
    return {"prevalence": prevalence.sort_values(["prevalence", "total_signal"], ascending=False).head(100_000)}, [
        "Pin taxonomy/AMR database releases and retain negative-control, extraction-batch and sequencing-run metadata.",
        "Confirm actionable findings using independent culture, susceptibility or public-health workflows.",
    ]


def _platform(frame: pd.DataFrame, checks: list[dict[str, Any]], metrics: list[dict[str, Any]], metadata: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    hash_col = _column(frame, "sha256", "checksum", "input_hash", "artifact_hash")
    version = _column(frame, "version", "release", "software_version", "reference_version")
    status = _column(frame, "status", "state", "result")
    created = _column(frame, "created_at", "timestamp", "time")
    coverage_rows = []
    for label, column in (("checksum", hash_col), ("version", version), ("status", status), ("timestamp", created)):
        fraction = float(frame[column].notna().mean()) if column else 0.0
        coverage_rows.append({"field": label, "column": column or "", "coverage": fraction})
        _check(checks, f"{label.title()} provenance", "pass" if fraction >= 0.95 else "review", f"coverage={fraction:.1%}")
    if hash_col:
        valid_hash = frame[hash_col].astype(str).str.fullmatch(r"[0-9a-fA-F]{64}", na=False)
        _check(checks, "SHA-256 syntax", "pass" if valid_hash.all() else "review", f"{int((~valid_hash).sum())} invalid hashes")
    if status:
        _metric(metrics, "distinct_statuses", int(frame[status].nunique(dropna=True)), "statuses")
    return {"governance_coverage": pd.DataFrame(coverage_rows)}, [
        "A local provenance record is not an externally timestamped or regulated audit trail.",
        "Use signed releases, least-privilege access, independent review and recovery testing for production deployment.",
    ]


