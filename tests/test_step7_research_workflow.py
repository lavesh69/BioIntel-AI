from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd

from biointel.cli import main as cli_main
from biointel.integrations.chembl_dataset import ChEMBLActivityQuery, build_chembl_activity_dataset
from biointel.integrations.http_client import HttpResponse
from biointel.reports.release_bundle import build_model_release_bundle
from biointel.sequence.batch_analysis import summarize_fasta_text
from biointel.training.external_validation import evaluate_external_dataset
from biointel.training.model_artifact import load_model_artifact, save_model_artifact
from biointel.training.trainers import TrainingConfig, train_dti_model
from biointel.training.uncertainty import (
    classification_prediction_set,
    fit_classification_conformal,
    fit_regression_conformal,
    regression_prediction_interval,
)
from biointel.utils.audit_log import append_audit_event, read_audit_events

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data/examples/synthetic_dti_demo.csv"


def trained(task="classification"):
    return train_dti_model(
        pd.read_csv(DEMO),
        TrainingConfig(
            task_type=task,
            model_name="random_forest" if task == "classification" else "ridge",
            fingerprint_bits=64,
            n_estimators=20,
            bootstrap_iterations=20,
            conformal_alpha=0.1,
            synthetic_demo=True,
        ),
    )


def test_conformal_classification():
    c = fit_classification_conformal(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9]), 0.1)
    assert classification_prediction_set(0.95, c) == [1]


def test_conformal_regression():
    c = fit_regression_conformal(np.array([1.0, 2.0, 3.0]), np.array([1.1, 1.9, 3.2]), 0.2)
    lo, hi = regression_prediction_interval(2.5, c)
    assert lo < 2.5 < hi


def test_batch_summary():
    s = summarize_fasta_text(">dna\nATGCGCTAA\n>protein\nMKWVTFISLLFLFSSAYSR\n")
    assert len(s) == 2 and set(s.detected_type) == {"DNA", "Protein"}


def test_audit_hash(tmp_path):
    p = tmp_path / "a.jsonl"
    append_audit_event(p, "x", "ok", {"canonical_smiles": "CCO", "protein_sequence": "ACDE"})
    assert "CCO" not in p.read_text() and read_audit_events(p)


def test_external_validation():
    r = evaluate_external_dataset(trained().artifact, pd.read_csv(DEMO).head(20))
    assert "accuracy" in r.metrics and "status" in r.drift


def test_release_bundle(tmp_path):
    tr = trained("regression")
    saved = save_model_artifact(tr.artifact, tmp_path / "m.joblib")
    with zipfile.ZipFile(BytesIO(build_model_release_bundle(tr.artifact, saved))) as z:
        assert "MANIFEST_SHA256.json" in z.namelist()


def test_cli(capsys):
    assert cli_main(["sequence-analyze", "--text", "ATGCGCTAA", "--sequence-type", "DNA"]) == 0
    assert json.loads(capsys.readouterr().out)["analysis"]["length"] == 9


def test_artifact_v7(tmp_path):
    tr = trained()
    saved = save_model_artifact(tr.artifact, tmp_path / "m.joblib")
    assert load_model_artifact(saved).metadata.artifact_version == "7.0.0"


def test_chembl_builder_mock():
    def transport(url, timeout, headers):
        if "target/" in url:
            return HttpResponse(
                200,
                json.dumps({"target_components": [{"accession": "P12345"}]}).encode(),
                "application/json",
            )
        if "uniprot" in url:
            return HttpResponse(200, b">x\nACDEFGHIKLMNPQRSTVWY\n", "text/plain")
        return HttpResponse(
            200,
            json.dumps(
                {
                    "activities": [
                        {
                            "activity_id": 1,
                            "molecule_chembl_id": "CHEMBL25",
                            "canonical_smiles": "CCO",
                            "standard_value": "100",
                            "standard_units": "nM",
                            "standard_relation": "=",
                            "pchembl_value": "7.0",
                        }
                    ],
                    "page_meta": {"next": None},
                }
            ).encode(),
            "application/json",
        )

    r = build_chembl_activity_dataset(
        ChEMBLActivityQuery("CHEMBL204", task_type="classification", max_records=10),
        transport=transport,
    )
    assert len(r.dataset) == 1 and r.dataset.iloc[0]["label"] == 1
