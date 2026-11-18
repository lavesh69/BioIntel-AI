from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from biointel.discovery_platform.api import router as discovery_router
from biointel.discovery_platform.api_shared import shared_store
from biointel.discovery_platform.constants import PROJECT_STAGES
from biointel.discovery_platform.models import (
    PlatformConflictError,
    PlatformPermissionError,
    PlatformValidationError,
    ProjectCreate,
)
from biointel.discovery_platform.reports import EXPORT_FORMATS
from biointel.discovery_platform.security import redact_mapping, safe_local_path
from biointel.discovery_platform.service import DiscoveryPlatformService
from biointel.discovery_platform.storage import SCHEMA_VERSION
from biointel.discovery_platform.workflow import validate_dag
from biointel.synthetic import (
    CLEAN_SCENARIOS,
    FAILURE_SCENARIOS,
    MODULE_SPECS,
    SyntheticDatasetGenerator,
    SyntheticGenerationConfig,
)


class Step220DiscoveryPlatformTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="biointel_step220_tests_")
        self.root = Path(self.temporary.name)
        self.service = DiscoveryPlatformService(
            self.root / "platform.sqlite3", self.root / "artifacts"
        )

    def tearDown(self) -> None:
        shared_store.cache_clear()
        self.temporary.cleanup()

    def create_project(self, *, synthetic: bool = False) -> dict:
        return self.service.create_project(
            ProjectCreate(
                title="Step220 verification project",
                research_question="Does the integrated platform preserve scientific provenance?",
                scientific_objective="Verify connected lifecycle and analysis behavior.",
                owner="test_operator",
                data_origin=(
                    "synthetic_demo_output"
                    if synthetic
                    else "user_entered_interpretation"
                ),
                is_synthetic=synthetic,
            )
        )

    def create_dataset(self, project: dict, module: str = "statistical_analysis") -> dict:
        synthetic = bool(project["is_synthetic"])
        return self.service.register_dataset(
            project["project_id"],
            name=f"Dataset {module}",
            assay_type=module,
            sample_count=24,
            feature_count=40,
            data_origin=(
                "synthetic_demo_output" if synthetic else "imported_external_result"
            ),
            provenance={"origin": "test", "module": module},
            is_synthetic=synthetic,
        )

    def test_schema_lifecycle_integrity_and_audit_chain(self) -> None:
        project = self.create_project()
        self.assertEqual(len(PROJECT_STAGES), 19)
        self.assertEqual(project["current_stage"], PROJECT_STAGES[0])
        advanced = self.service.advance_stage(project["project_id"])
        self.assertEqual(advanced["current_stage"], PROJECT_STAGES[1])
        with self.assertRaises(PlatformConflictError):
            self.service.advance_stage(project["project_id"])
        self.service.set_stage_gate(
            project["project_id"], PROJECT_STAGES[1], criteria=("research_question",), status="Approved"
        )
        advanced_again = self.service.advance_stage(project["project_id"])
        self.assertEqual(advanced_again["current_stage"], PROJECT_STAGES[2])
        integrity = self.service.store.integrity()
        self.assertTrue(integrity["healthy"])
        self.assertEqual(integrity["schema_version"], SCHEMA_VERSION)
        self.assertTrue(self.service.store.verify_audit_chain()["valid"])

    def test_ingestion_duplicate_corruption_and_unicode_windows_path(self) -> None:
        project = self.create_project()
        dataset = self.create_dataset(project)
        folder = self.root / "Path With Spaces" / "Unicode_\u0394"
        folder.mkdir(parents=True)
        source = folder / "measurements.csv"
        source.write_text("sample_id,value\nS1,1.0\nS2,2.0\n", encoding="utf-8")
        first = self.service.ingestion.ingest(
            dataset["dataset_id"], source, required_columns=("sample_id", "value")
        )
        duplicate = self.service.ingestion.ingest(dataset["dataset_id"], source)
        self.assertEqual(first["format"], "CSV")
        self.assertEqual(duplicate["status"], "Duplicate")
        corrupt = folder / "corrupt.zip"
        corrupt.write_bytes(b"not a valid zip archive")
        with self.assertRaises(PlatformValidationError):
            self.service.ingestion.ingest(dataset["dataset_id"], corrupt)
        self.assertTrue(safe_local_path(folder, "nested", "result.csv").is_relative_to(folder))
        with self.assertRaises(PlatformValidationError):
            safe_local_path(folder, "..", "outside.txt")

    def test_workflow_authentication_redaction_and_permissions(self) -> None:
        valid = validate_dag(
            ({"key": "ingest"}, {"key": "analyze"}, {"key": "report"}),
            (
                {"source": "ingest", "target": "analyze"},
                {"source": "analyze", "target": "report"},
            ),
        )
        self.assertEqual(valid["topological_order"], ["ingest", "analyze", "report"])
        with self.assertRaises(PlatformValidationError):
            validate_dag(
                ({"key": "a"}, {"key": "b"}),
                (
                    {"source": "a", "target": "b"},
                    {"source": "b", "target": "a"},
                ),
            )
        user = self.service.authentication.create_user(
            username="step220.user",
            password="Strong-Step220-Password9!",
            display_name="Step220 User",
            role="Bioinformatician",
        )
        session = self.service.authentication.authenticate(
            user["username"], "Strong-Step220-Password9!", client={"token": "hidden"}
        )
        validated = self.service.authentication.validate_session(session["session_token"])
        self.assertEqual(validated["user_id"], user["user_id"])
        self.assertTrue(self.service.authentication.logout(session["session_token"]))
        with self.assertRaises(PlatformPermissionError):
            self.service.authentication.validate_session(session["session_token"])
        self.assertEqual(
            redact_mapping({"password": "x", "nested": {"api_key": "y"}}),
            {"password": "[REDACTED]", "nested": {"api_key": "[REDACTED]"}},
        )

    def test_all_synthetic_scenarios_use_production_analysis(self) -> None:
        project = self.create_project(synthetic=True)
        observed = []
        for category, scenarios in (("clean", CLEAN_SCENARIOS), ("failure", FAILURE_SCENARIOS)):
            for index, (module, scenario) in enumerate(scenarios.items(), start=1):
                config = SyntheticGenerationConfig(
                    module_id=module,
                    scenario=scenario,
                    size_preset="small",
                    seed=22000 + index,
                )
                generated = SyntheticDatasetGenerator().generate(config)
                samples, features = config.dimensions
                dataset = self.service.register_dataset(
                    project["project_id"],
                    name=f"{category}-{module}",
                    assay_type=module,
                    sample_count=samples,
                    feature_count=features,
                    file_formats=("in-memory synthetic tables",),
                    data_origin="synthetic_demo_output",
                    provenance={"origin": "synthetic_demo_output", "seed": config.seed},
                    is_synthetic=True,
                )
                manifest = self.service.synthetic.register_generated_dataset(
                    project_id=project["project_id"],
                    dataset_id=dataset["dataset_id"],
                    generated=generated,
                )
                result = self.service.synthetic.run_generated_analysis(
                    project_id=project["project_id"],
                    dataset_id=dataset["dataset_id"],
                    generated=generated,
                )
                self.assertEqual(manifest["generator_version"], generated.manifest.generator_version)
                self.assertIn(result["status"], {"Completed", "Expected failure captured"})
                self.assertGreater(result["input_rows"], 0)
                observed.append((category, module, result["status"]))
        self.assertEqual(len(MODULE_SPECS), 18)
        self.assertEqual(len(observed), 36)
        self.assertEqual(self.service.store.table_counts()["runs"], 36)
        self.assertTrue(self.service.synthetic.project_status(project["project_id"])["boundary_valid"])

    def test_reports_and_model_comparison(self) -> None:
        project = self.create_project()
        dataset = self.create_dataset(project)
        first_path = self.root / "model one.bin"
        second_path = self.root / "model two.bin"
        first_path.write_bytes(b"model-one")
        second_path.write_bytes(b"model-two")
        first = self.service.register_model(
            name="Classifier",
            version="1.0",
            task="classification",
            owner="test_operator",
            artifact_path=first_path,
            project_id=project["project_id"],
            training_dataset_id=dataset["dataset_id"],
            performance={"auc": 0.81},
        )
        second = self.service.register_model(
            name="Classifier",
            version="2.0",
            task="classification",
            owner="test_operator",
            artifact_path=second_path,
            project_id=project["project_id"],
            training_dataset_id=dataset["dataset_id"],
            performance={"auc": 0.87},
        )
        comparison = self.service.compare_models(first["model_id"], second["model_id"])
        self.assertIn("performance", comparison["differences"])
        report = self.service.reports.create_report(
            project["project_id"], title="Step220 integrated report"
        )
        for output_format in EXPORT_FORMATS:
            content, filename, media_type = self.service.reports.render(
                report["report_id"], output_format
            )
            self.assertGreater(len(content), 20, output_format)
            self.assertTrue(filename)
            self.assertTrue(media_type)

    def test_fastapi_catalog_synthetic_route_and_typed_error(self) -> None:
        os.environ["BIOINTEL_USER_DATA"] = str(self.root / "api user data")
        shared_store.cache_clear()
        app = FastAPI()
        app.include_router(discovery_router)
        client = TestClient(app)
        catalog = client.get("/v1/research-platform/catalog")
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(len(catalog.json()["analysis_modules"]), 18)
        generated = client.post(
            "/v1/research-platform/synthetic/generate",
            json={
                "module_id": "sequencing_quality",
                "scenario": CLEAN_SCENARIOS["sequencing_quality"],
                "size_preset": "small",
                "seed": 220,
                "project_title": "API synthetic verification",
            },
        )
        self.assertEqual(generated.status_code, 201, generated.text)
        payload = generated.json()
        self.assertEqual(payload["production_analysis"]["status"], "Completed")
        missing = client.get("/v1/research-platform/projects/PRJ-DOES-NOT-EXIST")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"]["error"]["code"], "not_found")


if __name__ == "__main__":
    unittest.main(verbosity=2)
