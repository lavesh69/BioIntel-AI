from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    roc_auc_score,
)
from sklearn.model_selection import RepeatedStratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.scientific.evidence_lake import ScientificEvidenceLake


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    dataset_path = ROOT / "data" / "public_reference" / "uci_breast_cancer_wisconsin_diagnostic.csv"
    frame = pd.read_csv(dataset_path)
    features = [
        column
        for column in frame.columns
        if column not in {"sample_id", "target", "diagnosis_label"}
    ]
    X = frame[features]
    y = frame["target"].astype(int)
    pipeline = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", LogisticRegression(max_iter=4000, class_weight="balanced", random_state=42)),
        ]
    )
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=3, random_state=42)
    scoring = {"roc_auc": "roc_auc", "balanced_accuracy": "balanced_accuracy", "f1": "f1"}
    cv_result = cross_validate(
        pipeline, X, y, cv=cv, scoring=scoring, n_jobs=1, return_train_score=False
    )
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, stratify=y, random_state=1729
    )
    pipeline.fit(X_train, y_train)
    probabilities = pipeline.predict_proba(X_test)[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    fraction_positive, mean_predicted = calibration_curve(
        y_test, probabilities, n_bins=10, strategy="quantile"
    )
    ece = float(np.average(np.abs(fraction_positive - mean_predicted)))
    metrics = {
        "holdout_roc_auc": float(roc_auc_score(y_test, probabilities)),
        "holdout_balanced_accuracy": float(balanced_accuracy_score(y_test, predictions)),
        "holdout_f1": float(f1_score(y_test, predictions)),
        "holdout_brier": float(brier_score_loss(y_test, probabilities)),
        "holdout_log_loss": float(log_loss(y_test, probabilities)),
        "holdout_ece": ece,
        "cv_roc_auc_mean": float(np.mean(cv_result["test_roc_auc"])),
        "cv_roc_auc_std": float(np.std(cv_result["test_roc_auc"], ddof=1)),
        "cv_balanced_accuracy_mean": float(np.mean(cv_result["test_balanced_accuracy"])),
        "cv_f1_mean": float(np.mean(cv_result["test_f1"])),
    }
    out_dir = ROOT / "reports" / "step38"
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = ROOT / "models" / "step38_uci_wdbc_logistic.joblib"
    joblib.dump(pipeline, model_path)
    dataset_hash = file_sha(dataset_path)
    model_hash = file_sha(model_path)
    report = {
        "study_id": "GEN-UCI-WDBC-REPEATED-CV-2026",
        "dataset": "UCI Breast Cancer Wisconsin Diagnostic",
        "dataset_doi": "10.24432/C5DW2B",
        "licence": "CC BY 4.0",
        "dataset_sha256": dataset_hash,
        "model_sha256": model_hash,
        "rows": len(frame),
        "features": len(features),
        "protocol": "Repeated stratified 5-fold CV x3 plus untouched stratified 20% holdout",
        "metrics": metrics,
        "completed_at": datetime.now(UTC).isoformat(),
        "limitations": [
            "Single public dataset",
            "Not an external DTI benchmark",
            "No prospective outcomes",
        ],
    }
    report_path = out_dir / "uci_wdbc_real_benchmark.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    lake = ScientificEvidenceLake(ROOT / "reports" / "scientific_evidence.sqlite3")
    lake.register_validation_study(
        study_id=report["study_id"],
        study_type="benchmark",
        protocol={
            "name": report["protocol"],
            "preregistered_at": "2026-07-05T00:00:00Z",
            "random_seed": 1729,
        },
        dataset_sha256=dataset_hash,
        model_sha256=model_hash,
        status="reviewed",
        metrics=metrics,
        evidence={
            "report_path": str(report_path.relative_to(ROOT)),
            "dataset_doi": report["dataset_doi"],
        },
        completed_at=report["completed_at"],
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
