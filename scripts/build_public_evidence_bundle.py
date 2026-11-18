from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "real_scientific_pack" / "cancer" / "uci_wdbc_real.csv"
OUT = ROOT / "data" / "external_scientific_evidence"
MODEL = ROOT / "models" / "public_wdbc_reproducible_benchmark.joblib"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(SOURCE)
    feature_columns = [
        column
        for column in data.columns
        if column not in {"sample_id", "target", "diagnosis_label"}
    ]
    train, holdout = train_test_split(
        data,
        test_size=0.22,
        random_state=8600,
        stratify=data["target"],
    )
    pipeline = Pipeline(
        [
            ("scale", StandardScaler()),
            ("model", LogisticRegression(max_iter=4000, random_state=8600)),
        ]
    )
    pipeline.fit(train[feature_columns], train["target"])
    probability = pipeline.predict_proba(holdout[feature_columns])[:, 1]
    prediction = pipeline.predict(holdout[feature_columns])
    holdout_path = OUT / "uci_wdbc_untouched_holdout.csv"
    predictions_path = OUT / "uci_wdbc_holdout_predictions.csv"
    report_path = OUT / "uci_wdbc_benchmark_report.json"
    model_card_path = OUT / "PUBLIC_BENCHMARK_MODEL_CARD.md"
    readme_path = OUT / "README.md"
    holdout.sort_values("sample_id").to_csv(holdout_path, index=False)
    pd.DataFrame(
        {
            "sample_id": holdout["sample_id"].values,
            "observed_target": holdout["target"].values,
            "predicted_target": prediction,
            "positive_probability": probability,
        }
    ).sort_values("sample_id").to_csv(predictions_path, index=False)
    joblib.dump(pipeline, MODEL, compress=0)
    report = {
        "schema": "biointel.public-benchmark.v1",
        "dataset": "UCI Wisconsin Diagnostic Breast Cancer",
        "dataset_sha256": sha256(SOURCE),
        "model_sha256": sha256(MODEL),
        "feature_columns": feature_columns,
        "train_rows": len(train),
        "holdout_rows": len(holdout),
        "split": {"method": "stratified untouched holdout", "random_state": 8600},
        "metrics": {
            "holdout_roc_auc": float(roc_auc_score(holdout["target"], probability)),
            "holdout_balanced_accuracy": float(
                balanced_accuracy_score(holdout["target"], prediction)
            ),
            "confusion_matrix": confusion_matrix(holdout["target"], prediction).tolist(),
        },
        "clinical_use": False,
        "scope": "Reproducible public-data software benchmark; not a clinical diagnostic validation.",
        "limitations": [
            "Retrospective public dataset",
            "No prospective BioIntel-specific clinical study",
            "No regulatory authorization",
        ],
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    model_card_path.write_text(
        "# Public WDBC Reproducible Benchmark\n\n"
        "A deterministic logistic-regression software benchmark trained on a versioned public dataset. "
        "The untouched holdout, predictions, metrics, model bytes and checksums are bundled. "
        "This artifact is **not** approved for clinical diagnosis, patient care or regulatory use.\n",
        encoding="utf-8",
    )
    readme_path.write_text(
        "# External Scientific Evidence Bundle\n\n"
        "Contains checksum-bound public reference evidence and one reproducible real-data benchmark. "
        "Public evidence is reported separately from BioIntel-specific independent clinical/pharma validation.\n",
        encoding="utf-8",
    )
    artifacts = [
        SOURCE,
        ROOT / "data" / "real_scientific_pack" / "catalog.json",
        ROOT / "data" / "real_scientific_pack" / "manifests" / "verified_public_reference_catalog.csv",
        MODEL,
        holdout_path,
        predictions_path,
        report_path,
        model_card_path,
        readme_path,
    ]
    catalog = json.loads((ROOT / "data" / "real_scientific_pack" / "catalog.json").read_text())
    for dataset in catalog.get("datasets", [])[:8]:
        entries = dataset.get("file_metadata", [])
        if entries:
            candidate = ROOT / entries[0]["path"]
            if candidate.is_file() and candidate not in artifacts:
                artifacts.append(candidate)
    manifest = {
        "schema": "biointel.public-evidence-bundle.v1",
        "claim_boundary": "Public reference evidence does not establish BioIntel clinical efficacy, regulatory authorization or prospective validation.",
        "artifacts": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in artifacts
        ],
    }
    manifest_path = OUT / "evidence_bundle_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], sort_keys=True))


if __name__ == "__main__":
    main()
