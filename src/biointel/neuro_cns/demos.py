from __future__ import annotations

import numpy as np
import pandas as pd


DEMO_SMILES = {
    "Caffeine": "Cn1cnc2n(C)c(=O)n(C)c(=O)c12",
    "Dopamine": "NCCc1ccc(O)c(O)c1",
    "Diazepam": "CN1C(=O)CN=C(c2ccccc2)c2cc(Cl)ccc21",
    "Mannitol": "OCC(O)C(O)C(O)C(O)CO",
}

DEMO_PROTEIN_SEQUENCE = (
    "MKTIIALSYIFCLVFADYKDDDDK" + "A" * 20 + "VVVVVVVVVVVVVVVVVVV" + "G" * 15
    + "TVGYG" + "L" * 25 + "VVVVVVVVVVVVVVVVVVV" + "A" * 30
)

DEMO_GPCR_SEQUENCE = (
    "M" * 20 + "LAVVAVVAFVVLWAP" + "A" * 25 + "DRY" + "L" * 30
    + "VVVVVILILVV" + "A" * 35 + "CWLP" + "L" * 35 + "NPVIY" + "V" * 30
)

DEMO_AGGREGATION_SEQUENCE = "MDVFMKGLSKAKEGVVAAAEKTKQGVAEAAGKTKEGVLYVGSKTKEGVVHGVTTVA" * 2


def binding_profile() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"target_id": "DRD2", "binding_score": 0.86},
            {"target_id": "HTR2A", "binding_score": 0.61},
            {"target_id": "SCN1A", "binding_score": 0.42},
            {"target_id": "EGFR", "binding_score": 0.75},
        ]
    )


def variants() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"chrom": "2", "position": 166848200, "ref": "C", "alt": "T", "gene": "SCN1A", "consequence": "missense_variant", "clinvar": "likely pathogenic", "af": 0.000001, "inheritance": "de novo", "zygosity": "heterozygous", "hpo_match": 0.88},
            {"chrom": "17", "position": 44039700, "ref": "G", "alt": "A", "gene": "MAPT", "consequence": "missense_variant", "clinvar": "uncertain significance", "af": 0.0002, "inheritance": "dominant", "zygosity": "heterozygous", "hpo_match": 0.62},
            {"chrom": "1", "position": 100100, "ref": "A", "alt": "G", "gene": "GENE1", "consequence": "synonymous_variant", "clinvar": "benign", "af": 0.12, "inheritance": "unknown", "zygosity": "heterozygous", "hpo_match": 0.05},
        ]
    )


def omics(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 48
    group = np.array(["control"] * (n // 2) + ["disease"] * (n // 2))
    return pd.DataFrame(
        {
            "group": group,
            "SNCA_expression": np.r_[rng.normal(0.0, 1.0, n // 2), rng.normal(1.2, 1.0, n // 2)],
            "TREM2_expression": np.r_[rng.normal(0.0, 1.0, n // 2), rng.normal(0.8, 1.0, n // 2)],
            "C3_protein": np.r_[rng.normal(0.0, 1.0, n // 2), rng.normal(0.6, 1.1, n // 2)],
            "neutral_feature": rng.normal(0.0, 1.0, n),
            "metabolite_X": np.r_[rng.normal(0.0, 1.0, n // 2), rng.normal(-0.9, 1.0, n // 2)],
        }
    )


def eeg(sample_rate: float = 256.0, seconds: float = 8.0, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    time = np.arange(0, seconds, 1.0 / sample_rate)
    return pd.DataFrame(
        {
            "time": time,
            "Fz": np.sin(2 * np.pi * 10 * time) + 0.25 * rng.normal(size=len(time)),
            "Cz": 0.8 * np.sin(2 * np.pi * 6 * time) + 0.25 * rng.normal(size=len(time)),
            "Pz": 1.1 * np.sin(2 * np.pi * 20 * time) + 0.25 * rng.normal(size=len(time)),
        }
    )


def roi_timeseries(seed: int = 13) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 180
    common = rng.normal(size=n)
    return pd.DataFrame(
        {
            "time": np.arange(n),
            "hippocampus": 0.75 * common + 0.45 * rng.normal(size=n),
            "prefrontal_cortex": 0.65 * common + 0.55 * rng.normal(size=n),
            "striatum": -0.35 * common + 0.75 * rng.normal(size=n),
            "thalamus": 0.25 * common + 0.75 * rng.normal(size=n),
        }
    )


def trials() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trial_id": "DEMO-001", "title": "Alpha-synuclein programme", "phase": "Phase 2", "status": "Recruiting", "indication": "Parkinson disease", "compound": "Compound A", "target": "SNCA", "endpoint": "Motor score change", "failure_reason": ""},
            {"trial_id": "DEMO-002", "title": "Microglial modulation", "phase": "Phase 1", "status": "Completed", "indication": "Alzheimer disease", "compound": "Compound B", "target": "TREM2", "endpoint": "Safety and biomarker response", "failure_reason": ""},
            {"trial_id": "DEMO-003", "title": "Ion-channel programme", "phase": "Phase 2", "status": "Terminated", "indication": "Epilepsy", "compound": "Compound C", "target": "SCN1A", "endpoint": "Seizure frequency", "failure_reason": "Insufficient efficacy"},
        ]
    )


def cohort(seed: int = 17) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for cluster, center in enumerate(((0.0, 0.2, 0.1), (2.4, 2.1, -0.5), (-1.8, 1.4, 2.2)), 1):
        for index in range(18):
            rows.append(
                {
                    "sample_id": f"C{cluster}_{index + 1:02d}",
                    "inflammation_score": rng.normal(center[0], 0.45),
                    "neurodegeneration_marker": rng.normal(center[1], 0.5),
                    "imaging_burden": rng.normal(center[2], 0.4),
                    "cognitive_score": rng.normal(0.0 - center[1], 0.55),
                }
            )
    return pd.DataFrame(rows)
