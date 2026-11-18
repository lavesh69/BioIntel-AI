from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.dti.feature_combiner import FeatureSchema
from biointel.integrations.chembl import (
    fetch_chembl_molecule,
    fetch_chembl_target,
)
from biointel.integrations.http_client import HttpResponse
from biointel.integrations.uniprot import fetch_uniprot_fasta
from biointel.provenance import (
    create_dataset_manifest,
    stable_dataframe_sha256,
)
from biointel.reports.model_card import build_model_card_markdown
from biointel.training.evaluation import (
    bootstrap_classification_intervals,
    bootstrap_regression_intervals,
)
from biointel.training.experiment_registry import (
    delete_experiment,
    list_experiments,
    register_experiment,
)
from biointel.training.model_artifact import (
    ARTIFACT_VERSION,
    ModelArtifact,
    ModelMetadata,
)


def test_dataframe_hash_is_stable_and_sensitive() -> None:
    first = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    second = first.copy()
    assert stable_dataframe_sha256(first) == stable_dataframe_sha256(second)
    second.loc[1, "b"] = "z"
    assert stable_dataframe_sha256(first) != stable_dataframe_sha256(second)


def test_dataset_manifest_does_not_embed_rows() -> None:
    dataframe = pd.DataFrame(
        {
            "canonical_smiles": ["CCO"],
            "protein_sequence": ["ACDE"],
            "label": [1],
        }
    )
    manifest = create_dataset_manifest(
        dataframe,
        "demo",
        "1.0",
        source_description="unit test",
    )
    assert manifest.row_count == 1
    assert len(manifest.sha256) == 64
    assert not hasattr(manifest, "rows")


def test_uniprot_connector_with_injected_transport() -> None:
    def transport(url: str, timeout: float, headers: dict[str, str]) -> HttpResponse:
        assert "rest.uniprot.org" in url
        assert timeout > 0
        assert "User-Agent" in headers
        return HttpResponse(
            200,
            b">sp|P69905|HBA_HUMAN Hemoglobin subunit alpha\nMVLSPADKTN\n",
            "text/plain",
        )

    record = fetch_uniprot_fasta("P69905", transport=transport)
    assert record.accession == "P69905"
    assert record.sequence == "MVLSPADKTN"


def test_chembl_connectors_with_injected_transport() -> None:
    molecule_payload = {
        "molecule_chembl_id": "CHEMBL25",
        "pref_name": "ASPIRIN",
        "molecule_type": "Small molecule",
        "max_phase": 4,
        "molecule_structures": {"canonical_smiles": "CC(=O)OC1=CC=CC=C1C(=O)O"},
    }
    target_payload = {
        "target_chembl_id": "CHEMBL204",
        "pref_name": "Epidermal growth factor receptor",
        "target_type": "SINGLE PROTEIN",
        "organism": "Homo sapiens",
    }

    def transport(url: str, timeout: float, headers: dict[str, str]) -> HttpResponse:
        payload = target_payload if "/target/" in url else molecule_payload
        return HttpResponse(
            200,
            json.dumps(payload).encode("utf-8"),
            "application/json",
        )

    molecule = fetch_chembl_molecule("CHEMBL25", transport=transport)
    target = fetch_chembl_target("CHEMBL204", transport=transport)
    assert molecule.preferred_name == "ASPIRIN"
    assert molecule.canonical_smiles
    assert target.target_type == "SINGLE PROTEIN"


def test_bootstrap_intervals_return_bounds() -> None:
    y_true = np.array([0, 0, 0, 1, 1, 1, 0, 1])
    probabilities = np.array([0.1, 0.2, 0.4, 0.6, 0.8, 0.9, 0.3, 0.7])
    classification = bootstrap_classification_intervals(
        y_true,
        probabilities,
        threshold=0.5,
        iterations=50,
    )
    assert classification["accuracy"] is not None
    assert classification["accuracy"]["lower_95"] <= classification["accuracy"]["upper_95"]

    regression = bootstrap_regression_intervals(
        np.arange(8, dtype=float),
        np.arange(8, dtype=float) + 0.1,
        iterations=50,
    )
    assert regression["rmse"] is not None


def _artifact() -> ModelArtifact:
    metadata = ModelMetadata(
        artifact_version=ARTIFACT_VERSION,
        experiment_id="exp-test-001",
        model_version="1.0.0",
        model_name="unit_test",
        task_type="classification",
        trained_at_utc="2026-07-04T00:00:00+00:00",
        dataset_name="unit",
        dataset_version="1.0",
        dataset_sha256="a" * 64,
        split_strategy="random_pair",
        threshold_strategy="fixed",
        calibration_method="none",
        decision_threshold=0.5,
        positive_class_name="interaction_positive",
        activity_type=None,
        synthetic_demo=True,
        train_rows=10,
        validation_rows=4,
        test_rows=4,
        metrics={"accuracy": 0.5},
        validation_metrics={"accuracy": 0.5},
        confidence_intervals={
            "accuracy": {
                "lower_95": 0.2,
                "upper_95": 0.8,
                "bootstrap_samples": 50,
            }
        },
        data_quality_summary={"valid_after_cleaning": 18},
        training_config={"random_seed": 42},
        software_versions={"python": "3.11"},
    )
    schema = FeatureSchema(
        schema_version="2.0.0",
        feature_count=1,
        feature_hash="hash",
        fingerprint_radius=2,
        fingerprint_bits=1,
        use_chirality=True,
        include_dipeptides=False,
        drug_feature_count=1,
        protein_feature_count=0,
    )
    return ModelArtifact(
        estimator=object(),
        feature_schema=schema,
        feature_names=("feature",),
        metadata=metadata,
        applicability_statistics={},
    )


def test_model_card_and_experiment_registry(tmp_path: Path) -> None:
    artifact = _artifact()
    card = build_model_card_markdown(artifact)
    assert "exp-test-001" in card
    assert "Dataset SHA-256" in card

    registry = tmp_path / "experiments.sqlite3"
    register_experiment(registry, artifact, "model.joblib")
    records = list_experiments(registry)
    assert records[0]["experiment_id"] == "exp-test-001"
    assert delete_experiment(registry, "exp-test-001")
    assert list_experiments(registry) == []


def test_api_health_and_sequence_analysis() -> None:
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    response = client.post(
        "/sequence/analyze",
        json={
            "sequence": ">dna\nATGCGCTAA",
            "sequence_type": "DNA",
        },
    )
    assert response.status_code == 200
    assert response.json()["analysis"]["length"] == 9


def test_api_rejects_model_path_traversal() -> None:
    client = TestClient(app)
    response = client.post(
        "/dti/predict",
        json={
            "model_filename": "../outside.joblib",
            "canonical_smiles": "CCO",
            "protein_sequence": "ACDEFGHIK",
        },
    )
    assert response.status_code == 400
