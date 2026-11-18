from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from statistics import mean
from typing import Callable

import pandas as pd

from .catalog import EvidenceRequirement
from .manifests import ManifestValidation, validate_manifest
from .metrics import (
    as_bool,
    balanced_accuracy,
    cohen_kappa,
    median_value,
    pearson,
    precision_recall,
    rmse,
    roc_auc,
    z_prime,
)


@dataclass(frozen=True)
class EvidenceValidation:
    module_key: str
    evidence_id: str
    manifest_passed: bool
    data_passed: bool
    qualified: bool
    record_count: int
    metrics: dict[str, float | int | str | bool]
    blockers: tuple[str, ...]
    path: str


def _read_csv(path: Path, required: tuple[str, ...]) -> tuple[pd.DataFrame, list[str]]:
    blockers: list[str] = []
    if not path.is_file():
        return pd.DataFrame(), [f"required data file is missing: {path.name}"]
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        return pd.DataFrame(), [f"cannot read {path.name}: {exc}"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        blockers.append(f"missing columns in {path.name}: {', '.join(missing)}")
    if frame.empty:
        blockers.append(f"{path.name} contains no records")
    return frame, blockers


def _numeric(frame: pd.DataFrame, columns: tuple[str, ...], blockers: list[str]) -> None:
    for column in columns:
        if column not in frame.columns:
            continue
        converted = pd.to_numeric(frame[column], errors="coerce")
        if converted.isna().any():
            blockers.append(f"column {column} contains missing or non-numeric values")
        frame[column] = converted


def _all_finite(frame: pd.DataFrame, columns: tuple[str, ...]) -> bool:
    for column in columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any() or not values.map(math.isfinite).all():
            return False
    return True


def _manifest_only(_: Path, __: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    return True, {"manifest_only": True}, []


def _phenotypic_instrument(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    columns = ("run_id", "field_flatness_pct", "focus_cv_pct", "illumination_cv_pct", "stage_error_um", "passed")
    blockers: list[str] = []
    _numeric(frame, columns[1:5], blockers)
    metrics = {
        "runs": len(frame),
        "max_field_flatness_pct": float(frame.field_flatness_pct.max()) if "field_flatness_pct" in frame else float("nan"),
        "max_focus_cv_pct": float(frame.focus_cv_pct.max()) if "focus_cv_pct" in frame else float("nan"),
        "max_illumination_cv_pct": float(frame.illumination_cv_pct.max()) if "illumination_cv_pct" in frame else float("nan"),
        "max_stage_error_um": float(frame.stage_error_um.max()) if "stage_error_um" in frame else float("nan"),
    }
    if len(frame) < 3:
        blockers.append("at least 3 real instrument runs are required")
    if not _all_finite(frame, columns[1:5]):
        blockers.append("instrument metrics must be finite")
    if metrics["max_field_flatness_pct"] > 10:
        blockers.append("field flatness variation exceeds 10%")
    if metrics["max_focus_cv_pct"] > 10:
        blockers.append("focus CV exceeds 10%")
    if metrics["max_illumination_cv_pct"] > 10:
        blockers.append("illumination CV exceeds 10%")
    if metrics["max_stage_error_um"] > 5:
        blockers.append("stage error exceeds 5 µm")
    if "passed" in frame and not frame.passed.map(as_bool).all():
        blockers.append("one or more instrument runs are not accepted")
    return not blockers, metrics, blockers


def _phenotypic_plates(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    numeric = ("positive_mean", "positive_sd", "negative_mean", "negative_sd", "replicate_corr", "edge_effect_pct")
    _numeric(frame, numeric, blockers)
    z_values = [
        z_prime(row.positive_mean, row.positive_sd, row.negative_mean, row.negative_sd)
        for row in frame.itertuples(index=False)
    ] if set(numeric).issubset(frame.columns) else []
    metrics = {
        "plates": int(frame.plate_id.nunique()) if "plate_id" in frame else len(frame),
        "min_z_prime": min(z_values) if z_values else float("nan"),
        "min_replicate_corr": float(frame.replicate_corr.min()) if "replicate_corr" in frame else float("nan"),
        "max_edge_effect_pct": float(frame.edge_effect_pct.max()) if "edge_effect_pct" in frame else float("nan"),
    }
    if metrics["plates"] < 3:
        blockers.append("at least 3 independent plates are required")
    if z_values and min(z_values) < 0.5:
        blockers.append("one or more plates have Z-prime below 0.5")
    if "replicate_corr" in frame and frame.replicate_corr.min() < 0.80:
        blockers.append("replicate correlation is below 0.80")
    if "edge_effect_pct" in frame and frame.edge_effect_pct.max() > 15:
        blockers.append("edge effect exceeds 15%")
    return not blockers, metrics, blockers


def _phenotypic_segmentation(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("dice", "iou", "object_f1"), blockers)
    metrics = {
        "images": int(frame.image_id.nunique()) if "image_id" in frame else len(frame),
        "mean_dice": float(frame.dice.mean()) if "dice" in frame else float("nan"),
        "mean_iou": float(frame.iou.mean()) if "iou" in frame else float("nan"),
        "mean_object_f1": float(frame.object_f1.mean()) if "object_f1" in frame else float("nan"),
    }
    if metrics["images"] < 20:
        blockers.append("at least 20 expert-labelled images are required")
    if metrics["mean_dice"] < 0.85:
        blockers.append("mean Dice is below 0.85")
    if metrics["mean_iou"] < 0.75:
        blockers.append("mean IoU is below 0.75")
    if metrics["mean_object_f1"] < 0.85:
        blockers.append("mean object F1 is below 0.85")
    if "reviewer_approved" in frame and not frame.reviewer_approved.map(as_bool).all():
        blockers.append("one or more ground-truth records lack expert approval")
    return not blockers, metrics, blockers


def _phenotypic_replicates(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("replicate_corr", "confirmed_hit_rate"), blockers)
    metrics = {
        "sites": int(frame.site_id.nunique()) if "site_id" in frame else 0,
        "batches": int(frame.batch_id.nunique()) if "batch_id" in frame else 0,
        "mean_replicate_corr": float(frame.replicate_corr.mean()) if "replicate_corr" in frame else float("nan"),
        "mean_confirmed_hit_rate": float(frame.confirmed_hit_rate.mean()) if "confirmed_hit_rate" in frame else float("nan"),
    }
    if metrics["sites"] < 2:
        blockers.append("at least 2 independent sites are required")
    if metrics["batches"] < 3:
        blockers.append("at least 3 biological batches are required")
    if metrics["mean_replicate_corr"] < 0.80:
        blockers.append("mean replicate correlation is below 0.80")
    if metrics["mean_confirmed_hit_rate"] < 0.70:
        blockers.append("confirmed-hit rate is below 0.70")
    return not blockers, metrics, blockers


def _phenotypic_orthogonal(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("primary_effect", "orthogonal_effect"), blockers)
    correlation = pearson(frame.primary_effect.tolist(), frame.orthogonal_effect.tolist()) if len(frame) >= 2 else float("nan")
    fraction = float(frame.confirmed.map(as_bool).mean()) if "confirmed" in frame and len(frame) else 0.0
    metrics = {"candidates": len(frame), "effect_correlation": correlation, "confirmed_fraction": fraction}
    if len(frame) < 10:
        blockers.append("at least 10 candidates are required")
    if not math.isfinite(correlation) or correlation < 0.70:
        blockers.append("primary-versus-orthogonal effect correlation is below 0.70")
    if fraction < 0.70:
        blockers.append("confirmed fraction is below 0.70")
    return not blockers, metrics, blockers


def _spatial_scanner(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    numeric = ("colour_delta_e", "focus_failure_pct", "tile_artifact_pct", "registration_error_um")
    _numeric(frame, numeric, blockers)
    metrics = {
        "runs": len(frame),
        "scanners": int(frame.scanner_id.nunique()) if "scanner_id" in frame else 0,
        "max_colour_delta_e": float(frame.colour_delta_e.max()) if "colour_delta_e" in frame else float("nan"),
        "max_focus_failure_pct": float(frame.focus_failure_pct.max()) if "focus_failure_pct" in frame else float("nan"),
        "max_tile_artifact_pct": float(frame.tile_artifact_pct.max()) if "tile_artifact_pct" in frame else float("nan"),
        "max_registration_error_um": float(frame.registration_error_um.max()) if "registration_error_um" in frame else float("nan"),
    }
    if len(frame) < 3:
        blockers.append("at least 3 scanner qualification runs are required")
    if metrics["max_colour_delta_e"] > 5:
        blockers.append("colour delta E exceeds 5")
    if metrics["max_focus_failure_pct"] > 2:
        blockers.append("focus failure exceeds 2%")
    if metrics["max_tile_artifact_pct"] > 2:
        blockers.append("tile artefacts exceed 2%")
    if metrics["max_registration_error_um"] > 10:
        blockers.append("registration error exceeds 10 µm")
    if "passed" in frame and not frame.passed.map(as_bool).all():
        blockers.append("one or more scanner runs are not accepted")
    return not blockers, metrics, blockers


def _spatial_drift(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("embedding_shift", "auc_drop", "calibration_error"), blockers)
    metrics = {
        "sites": int(frame.site_id.nunique()) if "site_id" in frame else 0,
        "scanners": int(frame.scanner_id.nunique()) if "scanner_id" in frame else 0,
        "stain_batches": int(frame.stain_batch.nunique()) if "stain_batch" in frame else 0,
        "max_embedding_shift": float(frame.embedding_shift.max()) if "embedding_shift" in frame else float("nan"),
        "max_auc_drop": float(frame.auc_drop.max()) if "auc_drop" in frame else float("nan"),
        "max_calibration_error": float(frame.calibration_error.max()) if "calibration_error" in frame else float("nan"),
    }
    if metrics["sites"] < 2:
        blockers.append("at least 2 sites are required")
    if metrics["stain_batches"] < 2:
        blockers.append("at least 2 stain batches are required")
    if metrics["max_embedding_shift"] > 0.20:
        blockers.append("embedding shift exceeds 0.20")
    if metrics["max_auc_drop"] > 0.05:
        blockers.append("AUC drop exceeds 0.05")
    if metrics["max_calibration_error"] > 0.05:
        blockers.append("calibration error exceeds 0.05")
    return not blockers, metrics, blockers


def _spatial_patient(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("prediction",), blockers)
    truth = frame.label.map(as_bool).tolist() if "label" in frame else []
    scores = frame.prediction.tolist() if "prediction" in frame else []
    predictions = [score >= 0.5 for score in scores]
    auc = roc_auc(truth, scores) if truth else float("nan")
    bacc = balanced_accuracy(truth, predictions) if truth else float("nan")
    metrics = {
        "patients": int(frame.patient_id.nunique()) if "patient_id" in frame else 0,
        "sites": int(frame.site_id.nunique()) if "site_id" in frame else 0,
        "roc_auc": auc,
        "balanced_accuracy": bacc,
    }
    if metrics["patients"] < 30:
        blockers.append("at least 30 unique external patients are required")
    if metrics["sites"] < 2:
        blockers.append("at least 2 independent sites are required")
    if not math.isfinite(auc) or auc < 0.80:
        blockers.append("ROC-AUC is below 0.80")
    if not math.isfinite(bacc) or bacc < 0.75:
        blockers.append("balanced accuracy is below 0.75")
    return not blockers, metrics, blockers


def _spatial_pathologists(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    reviewer1 = frame.reviewer1_label.astype(str).tolist() if "reviewer1_label" in frame else []
    reviewer2 = frame.reviewer2_label.astype(str).tolist() if "reviewer2_label" in frame else []
    model = frame.model_label.astype(str).tolist() if "model_label" in frame else []
    agreed_indices = [index for index, (a, b) in enumerate(zip(reviewer1, reviewer2)) if a == b]
    consensus_labels = [reviewer1[index] for index in agreed_indices]
    model_agreed = [model[index] for index in agreed_indices]
    inter = cohen_kappa(reviewer1, reviewer2) if reviewer1 else float("nan")
    model_kappa = cohen_kappa(consensus_labels, model_agreed) if consensus_labels else float("nan")
    metrics = {
        "cases": int(frame.case_id.nunique()) if "case_id" in frame else len(frame),
        "consensus_cases": len(agreed_indices),
        "inter_reviewer_kappa": inter,
        "model_consensus_kappa": model_kappa,
    }
    if metrics["cases"] < 30:
        blockers.append("at least 30 reviewed cases are required")
    if len(agreed_indices) < 20:
        blockers.append("at least 20 reviewer-consensus cases are required")
    if not math.isfinite(inter) or inter < 0.70:
        blockers.append("inter-reviewer kappa is below 0.70")
    if not math.isfinite(model_kappa) or model_kappa < 0.70:
        blockers.append("model-versus-consensus kappa is below 0.70")
    return not blockers, metrics, blockers


def _spatial_prospective(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("prediction",), blockers)
    truth = frame.label.map(as_bool).tolist() if "label" in frame else []
    predictions = [value >= 0.5 for value in frame.prediction.tolist()] if "prediction" in frame else []
    bacc = balanced_accuracy(truth, predictions) if truth else float("nan")
    metrics = {"cases": len(frame), "balanced_accuracy": bacc}
    if len(frame) < 30:
        blockers.append("at least 30 prospective cases are required")
    if "pre_specified_before_outcome" in frame and not frame.pre_specified_before_outcome.map(as_bool).all():
        blockers.append("all predictions and thresholds must be pre-specified before outcomes")
    if not math.isfinite(bacc) or bacc < 0.75:
        blockers.append("prospective balanced accuracy is below 0.75")
    return not blockers, metrics, blockers


def _protein_benchmark(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("metric_value", "threshold", "identity_to_train_max"), blockers)
    passed = (frame.metric_value >= frame.threshold) if {"metric_value", "threshold"}.issubset(frame.columns) else pd.Series(dtype=bool)
    metrics = {
        "benchmarks": int(frame.benchmark_id.nunique()) if "benchmark_id" in frame else len(frame),
        "all_metrics_passed": bool(passed.all()) if len(passed) else False,
        "max_identity_to_train": float(frame.identity_to_train_max.max()) if "identity_to_train_max" in frame else float("nan"),
    }
    if metrics["benchmarks"] < 2:
        blockers.append("at least 2 independent benchmarks are required")
    if not metrics["all_metrics_passed"]:
        blockers.append("one or more benchmark metrics fail the locked threshold")
    if metrics["max_identity_to_train"] > 0.70:
        blockers.append("benchmark identity to training exceeds 70%")
    if "independent" in frame and not frame.independent.map(as_bool).all():
        blockers.append("all benchmark rows must be independent")
    return not blockers, metrics, blockers


def _protein_novelty(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("max_identity_to_training", "max_kmer_jaccard"), blockers)
    metrics = {
        "sequences": int(frame.sequence_id.nunique()) if "sequence_id" in frame else len(frame),
        "max_identity_to_training": float(frame.max_identity_to_training.max()) if "max_identity_to_training" in frame else float("nan"),
        "max_kmer_jaccard": float(frame.max_kmer_jaccard.max()) if "max_kmer_jaccard" in frame else float("nan"),
    }
    if metrics["sequences"] < 20:
        blockers.append("at least 20 generated sequences are required")
    if metrics["max_identity_to_training"] > 0.70:
        blockers.append("sequence identity to training exceeds 70%")
    if metrics["max_kmer_jaccard"] > 0.60:
        blockers.append("k-mer Jaccard overlap exceeds 0.60")
    if "restricted_motif" in frame and frame.restricted_motif.map(as_bool).any():
        blockers.append("restricted motifs are present")
    if "duplicate" in frame and frame.duplicate.map(as_bool).any():
        blockers.append("duplicate sequences are present")
    return not blockers, metrics, blockers


def _protein_structure(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("plddt", "ptm"), blockers)
    passing = (frame.plddt >= 70) & (frame.ptm >= 0.50) if {"plddt", "ptm"}.issubset(frame.columns) else pd.Series(dtype=bool)
    fraction = float(passing.mean()) if len(passing) else 0.0
    confirmation = frame.independent_or_experimental.map(as_bool).sum() if "independent_or_experimental" in frame else 0
    metrics = {
        "sequences": int(frame.sequence_id.nunique()) if "sequence_id" in frame else len(frame),
        "confidence_pass_fraction": fraction,
        "independent_or_experimental_confirmations": int(confirmation),
    }
    if metrics["sequences"] < 10:
        blockers.append("at least 10 sequences require structure confirmation")
    if fraction < 0.80:
        blockers.append("fewer than 80% meet pLDDT/pTM thresholds")
    if confirmation < 1:
        blockers.append("at least one independent or experimental confirmation is required")
    return not blockers, metrics, blockers


def _protein_expression(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("expression_yield_mg_l", "soluble_fraction", "purity_pct"), blockers)
    pass_mask = (
        (frame.expression_yield_mg_l > 0)
        & (frame.soluble_fraction >= 0.50)
        & (frame.purity_pct >= 80)
        & frame.activity_confirmed.map(as_bool)
    ) if {"expression_yield_mg_l", "soluble_fraction", "purity_pct", "activity_confirmed"}.issubset(frame.columns) else pd.Series(dtype=bool)
    fraction = float(pass_mask.mean()) if len(pass_mask) else 0.0
    metrics = {"designs": int(frame.sequence_id.nunique()) if "sequence_id" in frame else len(frame), "wet_lab_success_fraction": fraction}
    if metrics["designs"] < 5:
        blockers.append("at least 5 wet-lab tested designs are required")
    if fraction < 0.60:
        blockers.append("fewer than 60% pass expression, solubility, purity and activity gates")
    return not blockers, metrics, blockers


def _ligand_docking(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("predicted_rmsd", "rank"), blockers)
    rmsds = frame.predicted_rmsd.tolist() if "predicted_rmsd" in frame else []
    top1 = ((frame["rank"] == 1) & (frame.predicted_rmsd <= 2.0)).mean() if {"rank", "predicted_rmsd"}.issubset(frame.columns) and len(frame) else 0.0
    metrics = {
        "complexes": int(frame.complex_id.nunique()) if "complex_id" in frame else len(frame),
        "median_pose_rmsd": median_value(rmsds),
        "top1_success_fraction": float(top1),
    }
    if metrics["complexes"] < 20:
        blockers.append("at least 20 redocking complexes are required")
    if metrics["median_pose_rmsd"] > 2.0:
        blockers.append("median pose RMSD exceeds 2 Å")
    if metrics["top1_success_fraction"] < 0.60:
        blockers.append("top-1 redocking success is below 0.60")
    return not blockers, metrics, blockers


def _ligand_binding(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("predicted_pkd", "experimental_pkd"), blockers)
    predicted = frame.predicted_pkd.tolist() if "predicted_pkd" in frame else []
    measured = frame.experimental_pkd.tolist() if "experimental_pkd" in frame else []
    corr = pearson(predicted, measured) if predicted else float("nan")
    error = rmse(predicted, measured) if predicted else float("nan")
    metrics = {"measurements": len(frame), "pearson": corr, "rmse_pkd": error}
    if len(frame) < 20:
        blockers.append("at least 20 experimental affinity measurements are required")
    if not math.isfinite(corr) or corr < 0.60:
        blockers.append("affinity Pearson correlation is below 0.60")
    if not math.isfinite(error) or error > 1.50:
        blockers.append("affinity RMSE exceeds 1.50 pK units")
    return not blockers, metrics, blockers


def _ligand_selectivity(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("panel_size",), blockers)
    compound_count = int(frame.compound_id.nunique()) if "compound_id" in frame else len(frame)
    min_panel = int(frame.panel_size.min()) if "panel_size" in frame and len(frame) else 0
    fraction = float(frame.selectivity_pass.map(as_bool).mean()) if "selectivity_pass" in frame and len(frame) else 0.0
    metrics = {"compounds": compound_count, "min_panel_size": min_panel, "selectivity_pass_fraction": fraction}
    if compound_count < 10:
        blockers.append("at least 10 compounds are required")
    if min_panel < 5:
        blockers.append("selectivity panel contains fewer than 5 targets")
    if fraction < 0.70:
        blockers.append("selectivity pass fraction is below 0.70")
    return not blockers, metrics, blockers


def _ligand_admet(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    gates = ("solubility_ok", "permeability_ok", "cytotoxicity_ok", "herg_ok", "metabolic_stability_ok")
    if all(column in frame for column in gates):
        passed = frame[list(gates)].apply(lambda row: all(as_bool(value) for value in row), axis=1)
        fraction = float(passed.mean())
    else:
        fraction = 0.0
    metrics = {"compounds": int(frame.compound_id.nunique()) if "compound_id" in frame else len(frame), "all_gate_pass_fraction": fraction}
    if metrics["compounds"] < 10:
        blockers.append("at least 10 compounds are required")
    if fraction < 0.60:
        blockers.append("fewer than 60% pass every mandatory ADMET gate")
    return not blockers, metrics, blockers


def _ligand_prospective(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    truth = frame.experimental_active.map(as_bool).tolist() if "experimental_active" in frame else []
    predicted = frame.predicted_active.map(as_bool).tolist() if "predicted_active" in frame else []
    precision, recall = precision_recall(truth, predicted) if truth else (0.0, 0.0)
    metrics = {"compounds": len(frame), "precision": precision, "recall": recall}
    if len(frame) < 20:
        blockers.append("at least 20 prospective compounds are required")
    if "planned_before_assay" in frame and not frame.planned_before_assay.map(as_bool).all():
        blockers.append("all predictions must be locked before assay execution")
    if precision < 0.60:
        blockers.append("prospective precision is below 0.60")
    if recall < 0.60:
        blockers.append("prospective recall is below 0.60")
    return not blockers, metrics, blockers


def _microbiome_mock(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    truth = frame.expected_present.map(as_bool).tolist() if "expected_present" in frame else []
    predicted = frame.called_present.map(as_bool).tolist() if "called_present" in frame else []
    precision, recall = precision_recall(truth, predicted) if truth else (0.0, 0.0)
    expected = frame.expected_abundance.tolist() if "expected_abundance" in frame else []
    estimated = frame.estimated_abundance.tolist() if "estimated_abundance" in frame else []
    corr = pearson(expected, estimated) if expected else float("nan")
    metrics = {"records": len(frame), "precision": precision, "recall": recall, "abundance_correlation": corr}
    if len(frame) < 10:
        blockers.append("mock-community evidence contains too few strain observations")
    if precision < 0.90:
        blockers.append("mock-community precision is below 0.90")
    if recall < 0.90:
        blockers.append("mock-community recall is below 0.90")
    if not math.isfinite(corr) or corr < 0.90:
        blockers.append("abundance correlation is below 0.90")
    return not blockers, metrics, blockers


def _microbiome_contamination(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("total_reads", "contaminant_reads"), blockers)
    negatives = frame[frame.control_type.astype(str).str.lower().isin({"negative", "blank", "extraction_blank"})] if "control_type" in frame else frame.iloc[0:0]
    fractions = (negatives.contaminant_reads / negatives.total_reads.replace(0, pd.NA)).fillna(1.0) if len(negatives) else pd.Series(dtype=float)
    flags = negatives.flagged.map(as_bool) if "flagged" in negatives else pd.Series([False] * len(negatives))
    critical_unflagged = int(((fractions > 0.01) & (~flags)).sum()) if len(fractions) else 0
    metrics = {"negative_controls": len(negatives), "critical_unflagged": critical_unflagged, "max_contaminant_fraction": float(fractions.max()) if len(fractions) else float("nan")}
    if len(negatives) < 5:
        blockers.append("at least 5 negative or extraction-blank controls are required")
    if critical_unflagged:
        blockers.append("critical contamination above 1% remains unflagged")
    return not blockers, metrics, blockers


def _microbiome_ground_truth(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("ani", "coverage"), blockers)
    truth = frame.expected_present.map(as_bool).tolist() if "expected_present" in frame else []
    predicted = frame.called_present.map(as_bool).tolist() if "called_present" in frame else []
    precision, recall = precision_recall(truth, predicted) if truth else (0.0, 0.0)
    called = frame[frame.called_present.map(as_bool)] if "called_present" in frame else frame.iloc[0:0]
    quality = bool(((called.ani >= 0.99) & (called.coverage >= 0.80)).all()) if len(called) else False
    ambiguous_called = int((called.ambiguous.map(as_bool)).sum()) if "ambiguous" in called else 0
    metrics = {"records": len(frame), "precision": precision, "recall": recall, "all_called_quality_pass": quality, "ambiguous_calls": ambiguous_called}
    if len(frame) < 10:
        blockers.append("strain ground-truth evidence contains too few records")
    if precision < 0.90:
        blockers.append("strain precision is below 0.90")
    if recall < 0.90:
        blockers.append("strain recall is below 0.90")
    if not quality:
        blockers.append("one or more called strains fail ANI or coverage thresholds")
    if ambiguous_called:
        blockers.append("ambiguous strain assignments were emitted instead of abstaining")
    return not blockers, metrics, blockers


def _microbiome_sites(_: Path, frame: pd.DataFrame) -> tuple[bool, dict[str, object], list[str]]:
    blockers: list[str] = []
    _numeric(frame, ("precision", "recall", "abundance_corr"), blockers)
    grouped = frame.groupby("site_id")[["precision", "recall", "abundance_corr"]].mean() if "site_id" in frame else pd.DataFrame()
    metrics = {
        "sites": len(grouped),
        "min_site_precision": float(grouped.precision.min()) if not grouped.empty else float("nan"),
        "min_site_recall": float(grouped.recall.min()) if not grouped.empty else float("nan"),
        "min_site_abundance_corr": float(grouped.abundance_corr.min()) if not grouped.empty else float("nan"),
    }
    if metrics["sites"] < 2:
        blockers.append("at least 2 independent sequencing sites are required")
    if not grouped.empty and (grouped < 0.85).any().any():
        blockers.append("one or more sites fall below 0.85 precision, recall or abundance correlation")
    return not blockers, metrics, blockers


VALIDATORS: dict[str, tuple[tuple[str, ...], Callable[[Path, pd.DataFrame], tuple[bool, dict[str, object], list[str]]]]] = {
    "manifest_only": ((), _manifest_only),
    "phenotypic_instrument": (("run_id", "field_flatness_pct", "focus_cv_pct", "illumination_cv_pct", "stage_error_um", "passed"), _phenotypic_instrument),
    "phenotypic_plates": (("plate_id", "positive_mean", "positive_sd", "negative_mean", "negative_sd", "replicate_corr", "edge_effect_pct"), _phenotypic_plates),
    "phenotypic_segmentation": (("image_id", "dice", "iou", "object_f1", "reviewer_approved"), _phenotypic_segmentation),
    "phenotypic_replicates": (("site_id", "batch_id", "replicate_corr", "confirmed_hit_rate"), _phenotypic_replicates),
    "phenotypic_orthogonal": (("candidate_id", "primary_effect", "orthogonal_effect", "confirmed"), _phenotypic_orthogonal),
    "spatial_scanner": (("scanner_id", "colour_delta_e", "focus_failure_pct", "tile_artifact_pct", "registration_error_um", "passed"), _spatial_scanner),
    "spatial_drift": (("site_id", "scanner_id", "stain_batch", "embedding_shift", "auc_drop", "calibration_error"), _spatial_drift),
    "spatial_patient": (("patient_id", "site_id", "prediction", "label"), _spatial_patient),
    "spatial_pathologists": (("case_id", "model_label", "reviewer1_label", "reviewer2_label"), _spatial_pathologists),
    "spatial_prospective": (("case_id", "prediction", "label", "pre_specified_before_outcome"), _spatial_prospective),
    "protein_benchmark": (("benchmark_id", "metric_name", "metric_value", "threshold", "independent", "identity_to_train_max"), _protein_benchmark),
    "protein_novelty": (("sequence_id", "sequence", "max_identity_to_training", "max_kmer_jaccard", "restricted_motif", "duplicate"), _protein_novelty),
    "protein_structure": (("sequence_id", "method", "plddt", "ptm", "independent_or_experimental"), _protein_structure),
    "protein_expression": (("sequence_id", "expression_yield_mg_l", "soluble_fraction", "purity_pct", "activity_confirmed"), _protein_expression),
    "ligand_docking": (("complex_id", "predicted_rmsd", "rank", "engine_version", "reference_pose"), _ligand_docking),
    "ligand_binding": (("compound_id", "target_id", "predicted_pkd", "experimental_pkd", "assay_type"), _ligand_binding),
    "ligand_selectivity": (("compound_id", "panel_size", "selectivity_pass"), _ligand_selectivity),
    "ligand_admet": (("compound_id", "solubility_ok", "permeability_ok", "cytotoxicity_ok", "herg_ok", "metabolic_stability_ok"), _ligand_admet),
    "ligand_prospective": (("compound_id", "predicted_active", "experimental_active", "planned_before_assay"), _ligand_prospective),
    "microbiome_mock": (("sample_id", "strain_id", "expected_present", "called_present", "expected_abundance", "estimated_abundance"), _microbiome_mock),
    "microbiome_contamination": (("sample_id", "control_type", "total_reads", "contaminant_reads", "flagged"), _microbiome_contamination),
    "microbiome_ground_truth": (("sample_id", "strain_id", "expected_present", "called_present", "ani", "coverage", "ambiguous"), _microbiome_ground_truth),
    "microbiome_sites": (("site_id", "sample_id", "precision", "recall", "abundance_corr"), _microbiome_sites),
}


def validate_evidence_folder(root: str | Path, module_key: str, requirement: EvidenceRequirement) -> EvidenceValidation:
    folder = Path(root).resolve() / "UserData" / "step181" / "evidence" / module_key / requirement.evidence_id
    manifest: ManifestValidation = validate_manifest(folder, module_key, requirement)
    blockers = list(manifest.blockers)
    frame = pd.DataFrame()
    data_passed = False
    metrics: dict[str, object] = {}
    if manifest.passed:
        required_columns, validator = VALIDATORS[requirement.validator]
        if requirement.data_file is None:
            data_passed, metrics, data_blockers = validator(folder, frame)
        else:
            frame, csv_blockers = _read_csv(folder / requirement.data_file, required_columns)
            blockers.extend(csv_blockers)
            if not csv_blockers:
                data_passed, metrics, data_blockers = validator(folder, frame)
            else:
                data_passed, metrics, data_blockers = False, {}, []
        blockers.extend(data_blockers)
    qualified = manifest.passed and data_passed and not blockers
    return EvidenceValidation(
        module_key=module_key,
        evidence_id=requirement.evidence_id,
        manifest_passed=manifest.passed,
        data_passed=data_passed,
        qualified=qualified,
        record_count=len(frame),
        metrics={str(key): value for key, value in metrics.items()},
        blockers=tuple(blockers),
        path=str(folder),
    )


__all__ = ["EvidenceValidation", "VALIDATORS", "validate_evidence_folder"]
