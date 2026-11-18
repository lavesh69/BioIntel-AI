from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from biointel.education.phase32_35.base import PermissionDenied
from biointel.education.phase32_35.twin import BUILTIN_MODELS, DigitalTwinLab


@pytest.fixture()
def lab(tmp_path: Path) -> DigitalTwinLab:
    return DigitalTwinLab(tmp_path / "education.sqlite3", tmp_path / "media")


def project(lab: DigitalTwinLab, title: str = "Synthetic learning twin") -> dict:
    return lab.create_project(
        "tenant-a",
        "researcher-a",
        "institution-a",
        title=title,
        purpose="Controlled education and research simulation",
    )


def test_clinical_grade_is_disabled_and_patient_derived_requires_governance(
    lab: DigitalTwinLab,
):
    with pytest.raises(PermissionDenied, match="Clinical-Grade"):
        lab.create_project(
            "tenant-a",
            "researcher-a",
            "institution-a",
            title="Unsupported",
            purpose="Must fail",
            classification="Clinical-Grade Twin",
        )
    with pytest.raises(PermissionDenied, match="consent"):
        lab.create_project(
            "tenant-a",
            "researcher-a",
            "institution-a",
            title="Research twin",
            purpose="Research only",
            classification="Patient-Derived Research Twin",
            consent_status="unknown",
        )


def test_ingestion_validates_schema_identity_provenance_and_duplicates(lab: DigitalTwinLab):
    twin = project(lab)
    records = [
        {
            "variable_class": "phenotype",
            "variable_name": "glucose",
            "observed_at_utc": "2026-01-01T00:00:00+00:00",
            "value": 98.0,
            "unit": "mg/dL",
            "reference_low": 70,
            "reference_high": 140,
            "quality_score": 0.95,
        }
    ]
    first = lab.ingest_observations(
        twin["project_id"],
        "researcher-a",
        source_type="manual_phenotype",
        source_label="De-identified reference row",
        source_reference="local fixture",
        records=records,
        provenance={"source": "deterministic test"},
    )
    duplicate = lab.ingest_observations(
        twin["project_id"],
        "researcher-a",
        source_type="manual_phenotype",
        source_label="Duplicate",
        source_reference="local fixture",
        records=records,
        provenance={"source": "deterministic test"},
    )
    assert first["records"] == 1
    assert duplicate["duplicate"] is True
    with pytest.raises(PermissionDenied, match="identity"):
        lab.ingest_observations(
            twin["project_id"],
            "researcher-a",
            source_type="manual",
            source_label="Unsafe",
            source_reference="fixture",
            records=[{**records[0], "email": "person@example.invalid"}],
            provenance={},
        )


def test_synthetic_generator_is_seeded_labelled_and_separate(lab: DigitalTwinLab):
    first_project = project(lab, "First")
    second_project = project(lab, "Second")
    first = lab.generate_synthetic_profile(
        first_project["project_id"],
        "researcher-a",
        seed=1234,
        time_points=8,
    )
    second = lab.generate_synthetic_profile(
        second_project["project_id"],
        "researcher-a",
        seed=1234,
        time_points=8,
    )
    assert first["sha256"] == second["sha256"]
    assert first["synthetic"] is True
    assert first["records"] == 16


def test_temporal_simulation_uncertainty_sensitivity_replay_and_bundle(lab: DigitalTwinLab):
    twin = project(lab)
    model = lab.register_model(
        twin["project_id"],
        "researcher-a",
        model_key="glucose_regulation_v1",
    )
    scenario = lab.create_scenario(
        twin["project_id"],
        model["model_id"],
        "researcher-a",
        name="Synthetic intervention",
        time_steps=24,
        step_size=0.5,
        interventions=[
            {
                "time": 4.0,
                "target": "insulin_sensitivity",
                "mode": "multiply",
                "value": 1.2,
            }
        ],
        seed=99,
    )
    first = lab.run_scenario(scenario["scenario_id"], "researcher-a")
    replay = lab.run_scenario(
        scenario["scenario_id"],
        "researcher-a",
        replay_of=first.simulation_id,
    )
    assert first.sha256 == replay.sha256
    assert len(first.trajectory) == 25
    assert len(first.uncertainty) == 25
    assert first.sensitivity
    assert "NOT MEDICAL ADVICE OR A PRESCRIPTION" in first.warnings

    bundle = lab.export_result_bundle(first.simulation_id)
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        assert archive.testzip() is None
        limitations = archive.read("LIMITATIONS.txt").decode()
        assert "NON-CLINICAL" in limitations


def test_builtin_models_compute_real_stored_trajectories_and_compare(lab: DigitalTwinLab):
    twin = project(lab)
    simulation_ids = []
    for model_key in BUILTIN_MODELS:
        model = lab.register_model(twin["project_id"], "researcher-a", model_key=model_key)
        scenario = lab.create_scenario(
            twin["project_id"],
            model["model_id"],
            "researcher-a",
            name=model_key,
            time_steps=8,
            step_size=0.25,
        )
        result = lab.run_scenario(scenario["scenario_id"], "researcher-a")
        assert result.trajectory[-1] != result.trajectory[0]
        simulation_ids.append(result.simulation_id)
    comparison = lab.compare_simulations(simulation_ids)
    assert comparison["computed"] is True
    assert len(comparison["simulations"]) == len(BUILTIN_MODELS)


def test_imported_model_is_stored_but_not_mislabelled_as_executable(lab: DigitalTwinLab):
    twin = project(lab)
    model = lab.register_model(
        twin["project_id"],
        "researcher-a",
        model_key="sbml-import-fixture",
        model_name="Imported definition",
        model_type="imported_definition",
        definition={"format": "SBML", "version": "fixture"},
    )
    assert model["executable"] == 0
    scenario = lab.create_scenario(
        twin["project_id"],
        model["model_id"],
        "researcher-a",
        name="Stored only",
    )
    with pytest.raises(PermissionDenied, match="approved adapter"):
        lab.run_scenario(scenario["scenario_id"], "researcher-a")


def test_validation_never_auto_promotes_to_clinical_and_integrations_require_review(
    lab: DigitalTwinLab,
):
    twin = project(lab)
    model = lab.register_model(
        twin["project_id"],
        "researcher-a",
        model_key="inflammation_response_v1",
    )
    with pytest.raises(PermissionDenied, match="Clinical Validation"):
        lab.record_validation(
            model["model_id"],
            "reviewer-a",
            category="Clinical Validation",
            benchmark_reference="none",
            expected_output={},
            observed_output={},
            calibration={},
            sensitivity={},
            uncertainty={},
            reproducibility_seed=1,
            limitations="Not clinical",
            approved=True,
        )
    validated = lab.record_validation(
        model["model_id"],
        "reviewer-a",
        category="Synthetic Benchmark Validation",
        benchmark_reference="deterministic fixture",
        expected_output={"bounded": True},
        observed_output={"bounded": True},
        calibration={"status": "fixture pass"},
        sensitivity={"status": "computed"},
        uncertainty={"status": "computed"},
        reproducibility_seed=42,
        limitations="Synthetic only",
        approved=True,
    )
    assert validated["approved"] is True
    assert lab.model(model["model_id"])["validation_status"] == "Synthetic Benchmark Validation"
    link = lab.link_integration(
        twin["project_id"],
        "researcher-a",
        target_module="science_pulse",
        target_object_id="collection-1",
        purpose="Attach evidence collection",
        payload={"reference": "collection-1"},
    )
    assert link["state"] == "review_required"


def test_phase33_api_and_streamlit_surfaces(
    lab: DigitalTwinLab,
    monkeypatch,
    tmp_path: Path,
):
    from biointel.education.phase32_35 import twin_api

    monkeypatch.setattr(twin_api, "_LAB", lab)
    app = FastAPI()
    app.include_router(twin_api.router)
    client = TestClient(app)
    assert client.get("/phase33/capabilities").json()["clinical_grade_supported"] is False
    created = client.post(
        "/phase33/projects",
        json={
            "tenant_id": "tenant-a",
            "owner_id": "researcher-a",
            "institution_id": "institution-a",
            "title": "API synthetic twin",
            "purpose": "Education",
        },
    )
    assert created.status_code == 201

    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path / "streamlit-user-data"))
    page = Path(__file__).resolve().parents[1] / "pages" / "349_Biomedical_Digital_Twin_Lab.py"
    rendered = AppTest.from_file(str(page), default_timeout=60).run(timeout=60)
    assert not rendered.exception
