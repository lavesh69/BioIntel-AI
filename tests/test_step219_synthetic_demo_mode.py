from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from pypdf import PdfReader

from biointel.bioinformatics.recommendation_exports import (
    export_audit_report,
    export_evidence_package,
    export_parameter_configuration,
    export_recommendation_docx,
    export_recommendation_pdf_full,
    export_recommendation_xlsx,
)
from biointel.bioinformatics.recommendation_store import RecommendationStore
from biointel.bioinformatics.recommendations import (
    build_recommendation_workspace,
    export_evidence_csv,
    export_recommendation_csv,
    export_recommendation_html,
    export_recommendation_json,
    export_reproducibility_manifest,
)
from biointel.synthetic.cli import main as synthetic_cli_main
from biointel.synthetic.core import (
    CLEAN_SCENARIOS,
    FAILURE_SCENARIOS,
    MODULE_SPECS,
    SYNTHETIC_BANNER_TEXT,
    SYNTHETIC_WATERMARK,
    SyntheticGenerationConfig,
    SyntheticSafetyError,
    enforce_evidence_assignment,
    enforce_origin_transition,
    enforce_project_merge,
)
from biointel.synthetic.exports import build_synthetic_dataset_package
from biointel.synthetic.generators import generate_synthetic_dataset
from biointel.synthetic.service import SyntheticWorkspaceService


def _config(
    module: str = "differential_expression",
    scenario: str = "balanced_clean_design",
    *,
    seed: int = 42,
    samples: int = 16,
    features: int = 32,
    **overrides,
) -> SyntheticGenerationConfig:
    return SyntheticGenerationConfig(
        module,
        scenario,
        sample_count=samples,
        feature_count=features,
        seed=seed,
        **overrides,
    )


def _dataset_signature(dataset) -> dict[str, str]:
    return {
        name: frame.to_csv(index=False, float_format="%.12g")
        for name, frame in sorted(dataset.tables.items())
    }


def _office_xml_text(content: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return "\n".join(
            archive.read(name).decode("utf-8", errors="ignore")
            for name in archive.namelist()
            if name.endswith(".xml")
        )


def _synthetic_recommendation(tmp_path: Path):
    service = SyntheticWorkspaceService(tmp_path)
    project = service.create_demo_project(
        MODULE_SPECS["differential_expression"]["title"],
        "strong_biological_signal",
        seed=123,
        actor="pytest",
    )
    dataset, saved = service.generate_dataset(
        project["project_id"],
        _config("differential_expression", "strong_biological_signal", seed=123),
        actor="pytest",
    )
    recommendation = service.run_production_recommendation(
        project["project_id"], saved["dataset_id"], dataset, actor="pytest"
    )
    return service, project, dataset, saved, recommendation


def test_seed_reproducibility_and_variation() -> None:
    first = generate_synthetic_dataset(_config(seed=991))
    second = generate_synthetic_dataset(_config(seed=991))
    changed = generate_synthetic_dataset(_config(seed=992))
    assert _dataset_signature(first) == _dataset_signature(second)
    assert [item.to_dict() for item in first.ground_truth] == [
        item.to_dict() for item in second.ground_truth
    ]
    assert _dataset_signature(first) != _dataset_signature(changed)


def test_all_18_modules_have_clean_and_failure_generators() -> None:
    assert len(MODULE_SPECS) == 18
    assert set(CLEAN_SCENARIOS) == set(MODULE_SPECS)
    assert set(FAILURE_SCENARIOS) == set(MODULE_SPECS)
    for module in MODULE_SPECS:
        clean = generate_synthetic_dataset(
            _config(module, CLEAN_SCENARIOS[module], seed=100)
        )
        failure = generate_synthetic_dataset(
            _config(module, FAILURE_SCENARIOS[module], seed=101)
        )
        assert clean.tables and clean.ground_truth
        assert failure.tables and failure.ground_truth
        assert failure.expected_qc_findings, module
        for frame in (*clean.tables.values(), *failure.tables.values()):
            assert frame["data_origin"].eq("synthetic").all()
            assert frame["is_synthetic"].astype(bool).all()


def test_ground_truth_and_known_signal_recovery() -> None:
    dataset = generate_synthetic_dataset(
        _config(
            "differential_expression",
            "strong_biological_signal",
            seed=7,
            samples=30,
            features=80,
            effect_size=2.5,
            noise_level=0.1,
        )
    )
    truth = {
        record.entity_id
        for record in dataset.ground_truth
        if record.truth_type == "differential_gene"
    }
    results = dataset.tables["differential_expression_results.csv"]
    recovered = set(
        results.loc[
            results["is_known_signal"].astype(bool) & (results["fdr_bh"] <= 0.05),
            "gene",
        ].astype(str)
    )
    assert truth
    assert len(truth & recovered) / len(truth) >= 0.8
    assert all(record.hidden_by_default for record in dataset.ground_truth)


def test_manifest_package_is_complete_unique_and_watermarked() -> None:
    dataset = generate_synthetic_dataset(_config(seed=44))
    content = build_synthetic_dataset_package(dataset)
    required = {
        "synthetic_manifest.json",
        "README_SYNTHETIC_DATA.md",
        "generation_parameters.json",
        "expected_ground_truth.json",
        "expected_qc_findings.json",
        "expected_recommendations.json",
    }
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert required.issubset(names)
        manifest = json.loads(archive.read("synthetic_manifest.json"))
        assert manifest["data_origin"] == "synthetic"
        assert manifest["is_synthetic"] is True
        assert manifest["seed"] == 44
        assert manifest["file_hashes"]
        assert SYNTHETIC_BANNER_TEXT in archive.read("README_SYNTHETIC_DATA.md").decode()
        csv_names = [name for name in names if name.endswith(".csv")]
        assert csv_names
        assert all(SYNTHETIC_WATERMARK in archive.read(name).decode("utf-8") for name in csv_names)


def test_production_recommendation_preserves_origin_and_evidence(tmp_path: Path) -> None:
    service, project, dataset, saved, recommendation = _synthetic_recommendation(tmp_path)
    assert recommendation["data_origin"] == "synthetic"
    assert recommendation["is_synthetic"] is True
    assert recommendation["synthetic_seed"] == dataset.config.seed
    assert recommendation["synthetic_scenario"] == dataset.config.scenario
    assert recommendation["scientific_use"] == "Not permitted"
    assert recommendation["clinical_use"] == "Not permitted"
    assert recommendation["publication_use"] == "Not permitted"
    assert recommendation["publication_ready"] is False
    assert recommendation["multi_model_consensus"]
    assert recommendation["what_if_analysis"]
    for row in recommendation["evidence"] + recommendation["contradictory_evidence"]:
        assert row["evidence_origin"] == "calculated_synthetic"
        assert row["data_origin"] == "synthetic"
        assert row["is_synthetic"] is True
    assert service.registry.audit_events(project["project_id"])
    assert Path(saved["package_path"]).is_file()


def test_all_recommendation_exports_have_visible_synthetic_notice(tmp_path: Path) -> None:
    _, _, _, _, recommendation = _synthetic_recommendation(tmp_path)
    plain_exports = (
        export_recommendation_json(recommendation),
        export_recommendation_csv([recommendation]),
        export_evidence_csv(recommendation),
        export_recommendation_html(recommendation),
        export_reproducibility_manifest(recommendation),
        export_parameter_configuration(recommendation),
        export_audit_report(recommendation),
    )
    assert all(SYNTHETIC_WATERMARK.encode() in content for content in plain_exports)

    assert SYNTHETIC_WATERMARK in _office_xml_text(export_recommendation_docx(recommendation))
    assert SYNTHETIC_WATERMARK in _office_xml_text(export_recommendation_xlsx(recommendation))
    pdf = export_recommendation_pdf_full(recommendation)
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    assert SYNTHETIC_WATERMARK in pdf_text

    evidence_zip = export_evidence_package(recommendation)
    with zipfile.ZipFile(io.BytesIO(evidence_zip)) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert "SYNTHETIC_NOTICE.txt" in names
        assert SYNTHETIC_WATERMARK in archive.read("SYNTHETIC_NOTICE.txt").decode()


def test_contamination_guards_block_real_project_promotion(tmp_path: Path) -> None:
    real = build_recommendation_workspace(
        "differential_expression",
        {"analysis_status": "complete", "qc_status": "pass", "rows": [{"value": 1.0}]},
        project_id="REAL-PROJECT",
    )
    synthetic_evidence = {
        "evidence_origin": "external_verified",
        "data_origin": "synthetic",
        "is_synthetic": True,
    }
    with pytest.raises(SyntheticSafetyError):
        enforce_evidence_assignment(synthetic_evidence, real)
    with pytest.raises(SyntheticSafetyError):
        enforce_project_merge(
            {"data_origin": "synthetic", "is_synthetic": True},
            {"data_origin": "real", "is_synthetic": False},
        )
    assert enforce_project_merge(
        {"data_origin": "synthetic", "is_synthetic": True},
        {"data_origin": "real", "is_synthetic": False},
        explicitly_confirmed_mixed_evaluation=True,
    ) == "Mixed-Origin Evaluation"
    with pytest.raises(SyntheticSafetyError):
        enforce_origin_transition(
            {"data_origin": "synthetic", "is_synthetic": True}, "real"
        )

    store = RecommendationStore(tmp_path / "real_recommendations.sqlite3")
    store.save(real)
    with pytest.raises(SyntheticSafetyError):
        store.save_validation_result(
            real["recommendation_id"],
            "Synthetic demo validation",
            "Validated",
            "Synthetic result",
            acceptance_criteria="Demo-only criterion",
            actor="pytest",
            evidence=[{"data_origin": "synthetic", "is_synthetic": True, "evidence_origin": "demo_fixture"}],
        )


def test_synthetic_validation_cannot_become_scientific_validation(tmp_path: Path) -> None:
    service, _, _, _, recommendation = _synthetic_recommendation(tmp_path)
    validation_id = service.recommendations.save_validation_result(
        recommendation["recommendation_id"],
        "Demo recovery check",
        "Validated",
        "Expected synthetic signal recovered",
        acceptance_criteria="Synthetic fixture tolerance",
        actor="pytest",
        evidence=[{"evidence_origin": "calculated_synthetic", "data_origin": "synthetic", "is_synthetic": True}],
    )
    validation = next(
        item
        for item in service.recommendations.validations(recommendation["recommendation_id"])
        if item["validation_id"] == validation_id
    )
    assert validation["status"] == "Synthetic Demo Passed - not scientifically validated"
    assert validation["evidence"][0]["evidence_origin"] == "demo_fixture"


def test_demo_reset_is_scoped_to_synthetic_project(tmp_path: Path) -> None:
    service, project, _, saved, _ = _synthetic_recommendation(tmp_path)
    package_path = Path(saved["package_path"])
    other = tmp_path / "real_project_marker.txt"
    other.write_text("must remain", encoding="utf-8")
    assert package_path.is_file()
    reset = service.registry.reset_project(project["project_id"], actor="pytest")
    assert reset["reset_count"] == 1
    assert not package_path.exists()
    assert service.registry.list_datasets(project["project_id"]) == []
    assert other.read_text(encoding="utf-8") == "must remain"


def test_large_preset_warns_and_generates_in_chunks() -> None:
    config = SyntheticGenerationConfig(
        "differential_expression",
        "balanced_clean_design",
        size_preset="large",
        seed=5,
    )
    assert config.memory_warning and "Large preset" in config.memory_warning
    dataset = generate_synthetic_dataset(config)
    matrix = dataset.tables["count_matrix.csv"]
    assert matrix.shape[0] == 500
    assert len([column for column in matrix.columns if column.startswith("SYNG-")]) == 5000


def test_no_fake_citations_pii_or_clinical_claims() -> None:
    forbidden_columns = {"patient_name", "email", "phone", "address", "mrn", "medical_record_number"}
    identifier_pattern = re.compile(r"\bPMID\s*[:#]?\s*\d{5,}\b|\b10\.\d{4,9}/\S+|\bNCT\d{8}\b", re.I)
    for module in MODULE_SPECS:
        dataset = generate_synthetic_dataset(_config(module, CLEAN_SCENARIOS[module], seed=88))
        for frame in dataset.tables.values():
            assert not forbidden_columns.intersection({str(column).lower() for column in frame.columns})
            text = frame.astype(str).to_csv(index=False)
            assert identifier_pattern.search(text) is None
            assert "patient name" not in text.lower()
            assert "clinically validated" not in text.lower()


def test_cli_and_controlled_api(tmp_path: Path, capsys, monkeypatch) -> None:
    output = tmp_path / "cli"
    assert synthetic_cli_main([
        "generate",
        "--module", "differential_expression",
        "--scenario", "balanced_clean_design",
        "--samples", "12",
        "--features", "24",
        "--seed", "219",
        "--output", str(output),
    ]) == 0
    cli_result = json.loads(capsys.readouterr().out)
    generated = Path(cli_result["output"])
    assert cli_result["data_origin"] == "synthetic"
    assert (generated / "synthetic_manifest.json").is_file()

    from biointel.api import main as api_main
    from biointel.api.schemas import SyntheticDatasetRequest

    assert any(getattr(route, "path", "") == "/api/v1/synthetic-datasets" for route in api_main.app.routes)
    monkeypatch.setattr(api_main, "ROOT", tmp_path / "api")
    request = SyntheticDatasetRequest(
        demo_mode=True,
        module_id="differential_expression",
        scenario="balanced_clean_design",
        sample_count=12,
        feature_count=24,
        seed=220,
    )
    response = api_main.create_synthetic_dataset(request)
    assert response["data_origin"] == "synthetic"
    assert response["manifest"]["seed"] == 220
    assert response["package_sha256"]
    assert all(len(table["preview"]) <= 20 for table in response["tables"].values())
    service = SyntheticWorkspaceService(tmp_path / "api")
    assert service.registry.audit_events(response["project_id"])


def test_bundled_fixture_catalog_contains_baseline_and_failure() -> None:
    project_root = Path(__file__).resolve().parents[1]
    catalog = json.loads(
        (project_root / "data" / "synthetic_demo_fixtures" / "catalog.json").read_text(encoding="utf-8")
    )
    assert catalog["module_count"] == 18
    assert catalog["fixture_count"] == 36
    grouped: dict[str, set[str]] = {}
    for record in catalog["records"]:
        grouped.setdefault(record["module_id"], set()).add(record["variant"])
        fixture = project_root / record["relative_path"]
        assert fixture.is_file()
        with zipfile.ZipFile(fixture) as archive:
            assert archive.testzip() is None
    assert all(variants == {"baseline", "failure"} for variants in grouped.values())