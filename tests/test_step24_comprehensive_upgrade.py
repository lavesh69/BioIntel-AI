from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from biointel.api.middleware import (
    OptionalApiKeyMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from biointel.data.curation import (
    curate_activity_dataset,
    normalize_activity_value,
    standardize_compound,
)
from biointel.dti.batch_pipeline import run_chunked_batch_prediction
from biointel.dti.checkpoints import BatchCheckpointStore
from biointel.dti.feature_cache import FeatureCache
from biointel.dti.predictor import batch_predict_dti
from biointel.jobs.local_queue import LocalJobQueue
from biointel.training.model_artifact import load_model_artifact
from biointel.training.release_gate import evaluate_release_gate
from biointel.training.scientific_splits import (
    cold_drug_target_split_indices,
    sequence_cluster_split_indices,
    temporal_split_indices,
)

ROOT = Path(__file__).resolve().parents[1]
SEQUENCE = "ACDEFGHIKLMNPQRSTVWY"


def test_activity_and_compound_standardization() -> None:
    activity = normalize_activity_value(10, "nM")
    assert activity.molar_value == 1e-8
    assert activity.p_activity == 8.0
    compound = standardize_compound("CC(=O)O.[Na+]")
    assert compound.canonical_smiles == "CC(=O)O"
    assert compound.fragment_count == 2
    assert compound.inchikey


def test_curator_aggregates_duplicates_and_keeps_unknown_censoring() -> None:
    source = pd.DataFrame(
        [
            {
                "canonical_smiles": "CCO",
                "protein_sequence": SEQUENCE,
                "standard_value": 10,
                "standard_units": "nM",
                "standard_relation": "=",
                "activity_type": "Ki",
            },
            {
                "canonical_smiles": "CCO.[Na+]",
                "protein_sequence": SEQUENCE,
                "standard_value": 20,
                "standard_units": "nM",
                "standard_relation": "=",
                "activity_type": "Ki",
            },
            {
                "canonical_smiles": "CCN",
                "protein_sequence": SEQUENCE,
                "standard_value": 100,
                "standard_units": "uM",
                "standard_relation": ">",
                "activity_type": "Ki",
            },
        ]
    )
    curated, errors, summary = curate_activity_dataset(source)
    assert errors.empty
    assert len(curated) == 2
    assert summary.duplicate_groups == 1
    assert summary.inactive_rows == 1
    assert curated["assay_quality_score"].between(0, 1).all()


def _demo_artifact():
    return load_model_artifact(
        ROOT / "models" / "demo_classification_model.joblib",
        trusted_root=ROOT / "models",
    )


def test_vectorized_prediction_uses_persistent_cache(tmp_path: Path) -> None:
    artifact = _demo_artifact()
    cache_path = tmp_path / "feature_cache.sqlite3"
    dataframe = pd.DataFrame(
        [
            {"sample_id": "a", "canonical_smiles": "CCO", "protein_sequence": SEQUENCE},
            {"sample_id": "b", "canonical_smiles": "CCO", "protein_sequence": SEQUENCE},
        ]
    )
    first = batch_predict_dti(
        artifact,
        dataframe,
        max_rows=10,
        n_jobs=2,
        feature_cache_path=cache_path,
    )
    second = batch_predict_dti(
        artifact,
        dataframe,
        max_rows=10,
        n_jobs=2,
        feature_cache_path=cache_path,
    )
    assert first["error"].eq("").all()
    assert first["prediction"].tolist() == second["prediction"].tolist()
    stats = FeatureCache(cache_path).stats()
    assert stats.entries == 2
    assert stats.total_hits >= 2


def test_transactional_checkpoint_resume(tmp_path: Path) -> None:
    artifact = _demo_artifact()
    checkpoint = tmp_path / "batch.sqlite3"
    cache = tmp_path / "features.sqlite3"
    dataframe = pd.DataFrame(
        [
            {"sample_id": f"s{i}", "canonical_smiles": "CCO", "protein_sequence": SEQUENCE}
            for i in range(5)
        ]
    )
    first, first_summary = run_chunked_batch_prediction(
        artifact,
        dataframe,
        chunk_size=2,
        checkpoint_path=checkpoint,
        feature_cache_path=cache,
        n_jobs=2,
    )
    second, second_summary = run_chunked_batch_prediction(
        artifact,
        dataframe,
        chunk_size=2,
        checkpoint_path=checkpoint,
        feature_cache_path=cache,
        n_jobs=2,
        resume=True,
    )
    assert len(first) == 5
    assert len(second) == 5
    assert first_summary.checkpoint_format == "sqlite"
    assert second_summary.resumed_rows == 5
    assert len(BatchCheckpointStore(checkpoint).load()) == 5


def test_scientific_split_strategies() -> None:
    rows = []
    for drug_index in range(12):
        for target_index in range(8):
            rows.append(
                {
                    "drug_id": f"d{drug_index}",
                    "target_id": f"t{target_index}",
                    "protein_sequence": ("A" * (10 + target_index)) + ("C" * target_index),
                    "publication_date": f"202{drug_index % 5}-01-{(target_index % 9) + 1:02d}",
                }
            )
    dataframe = pd.DataFrame(rows)
    temporal = temporal_split_indices(dataframe, "publication_date")
    assert temporal.summary["chronological_order_preserved"] is True
    cold = cold_drug_target_split_indices(dataframe)
    assert cold.summary["drug_overlap"] is False
    assert cold.summary["target_overlap"] is False
    clustered = sequence_cluster_split_indices(
        dataframe,
        identity_threshold=0.95,
    )
    assert clustered.summary["cluster_overlap"] is False


def test_release_gate_blocks_synthetic_and_accepts_valid_real_model() -> None:
    synthetic = SimpleNamespace(synthetic_demo=True, task_type="classification")
    blocked = evaluate_release_gate(metadata=synthetic)
    assert blocked.passed is False
    assert blocked.blockers

    real = SimpleNamespace(synthetic_demo=False, task_type="classification", dataset_sha256="real-dataset-hash")
    passed = evaluate_release_gate(
        metadata=real,
        external_validation={
            "valid_rows": 200,
            "input_rows": 205,
            "metrics": {"roc_auc": 0.82, "balanced_accuracy": 0.74},
            "drift": {"status": "low"},
        },
        split_summary={"group_overlap": False},
        evidence_manifest={
            "dataset_sha256": "real-dataset-hash",
            "license_coverage": 1.0,
            "review_coverage": 1.0,
            "mean_quality": 0.8,
            "source_count": 1,
            "publication_coverage": 1.0,
        },
    )
    assert passed.passed is True


def test_persistent_job_queue_cancel_retry_and_complete(tmp_path: Path) -> None:
    queue = LocalJobQueue(tmp_path / "jobs.sqlite3")
    submitted = queue.submit("batch_prediction", {"rows": 10})
    claimed = queue.claim_next()
    assert claimed is not None and claimed.job_id == submitted.job_id
    failed = queue.fail(claimed.job_id, "temporary", retry=False)
    assert failed.status == "failed"
    retried = queue.retry(failed.job_id)
    assert retried.status == "queued"
    claimed_again = queue.claim_next()
    completed = queue.complete(claimed_again.job_id, {"ok": True})
    assert completed.status == "completed"


def test_optional_api_key_rate_limit_and_security_headers() -> None:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=2)
    app.add_middleware(OptionalApiKeyMiddleware, api_key="secret")

    @app.get("/private")
    def private():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/private").status_code == 401
    response = client.get("/private", headers={"X-API-Key": "secret"})
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-BioIntel-Access"] == "api-key"
    second = client.get("/private", headers={"X-API-Key": "secret"})
    assert second.status_code == 200
    limited = client.get("/private", headers={"X-API-Key": "secret"})
    assert limited.status_code == 429
