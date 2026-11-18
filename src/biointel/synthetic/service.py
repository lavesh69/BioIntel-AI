from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

from pathlib import Path
from typing import Any, Mapping

from biointel.bioinformatics.recommendation_store import RecommendationStore
from biointel.bioinformatics.recommendations import build_recommendation_workspace

from .core import (
    MODULE_SPECS,
    SYNTHETIC_WATERMARK,
    SyntheticGeneratedDataset,
    SyntheticGenerationCancelled,
    SyntheticGenerationConfig,
    SyntheticSafetyError,
    enforce_project_merge,
    origin_fields,
)
from .generators import SyntheticDatasetGenerator
from .registry import SyntheticDataRegistry


PROJECT_TYPES = tuple(spec["title"] for spec in MODULE_SPECS.values()) + ("Complete Bioinformatics Research Workflow Demo",)
PROJECT_TYPE_MODULE = {spec["title"]: module for module, spec in MODULE_SPECS.items()}
PROJECT_TYPE_MODULE["Complete Bioinformatics Research Workflow Demo"] = "differential_expression"


class SyntheticWorkspaceService:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.registry = SyntheticDataRegistry(
            runtime_database_path(self.project_root, "synthetic_workspace.sqlite3"),
            self.project_root / "data" / "synthetic_workspace" / "projects",
        )
        self.recommendations = RecommendationStore(runtime_database_path(self.project_root, "synthetic_recommendations.sqlite3"))
        self.generator = SyntheticDatasetGenerator()

    def create_demo_project(self, project_type: str, scenario: str | None = None, seed: int = 42, *, actor: str = "local_user") -> dict[str, Any]:
        if project_type not in PROJECT_TYPE_MODULE:
            raise ValueError(f"Unsupported demo project type: {project_type}")
        module = PROJECT_TYPE_MODULE[project_type]
        selected_scenario = scenario or MODULE_SPECS[module]["scenarios"][0]
        if selected_scenario not in MODULE_SPECS[module]["scenarios"]:
            raise ValueError(f"Scenario is not supported for {module}: {selected_scenario}")
        return self.registry.create_demo_project(project_type, module, selected_scenario, seed, actor=actor)

    def generate_dataset(self, project_id: str, config: SyntheticGenerationConfig, *, actor: str = "local_user") -> tuple[SyntheticGeneratedDataset, dict[str, Any]]:
        project = self.registry.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        if project["module_id"] != config.module_id and project["project_type"] != "Complete Bioinformatics Research Workflow Demo":
            raise SyntheticSafetyError("Selected module does not match the synthetic project boundary.")
        job_id = self.registry.create_generation_job(project_id, config.to_dict(), actor=actor)
        self.registry.complete_generation_job(job_id, "running")
        try:
            dataset = self.generator.generate(config, cancel_check=lambda: self.registry.cancellation_requested(job_id))
            saved = self.registry.save_dataset(project_id, dataset, actor=actor)
            self.registry.complete_generation_job(job_id, "completed")
            saved["job_id"] = job_id
            return dataset, saved
        except SyntheticGenerationCancelled:
            self.registry.complete_generation_job(job_id, "cancelled")
            raise
        except Exception:
            self.registry.complete_generation_job(job_id, "failed")
            raise

    def run_production_recommendation(self, project_id: str, dataset_id: str, dataset: SyntheticGeneratedDataset, *, actor: str = "local_user") -> dict[str, Any]:
        run_payload = {
            **origin_fields(dataset.config),
            "dataset_id": dataset_id,
            "module_id": dataset.config.module_id,
            "scenario": dataset.config.scenario,
            "purpose": "production_framework_demo_evaluation",
        }
        run_id = self.registry.register_run(project_id, dataset_id, "production_recommendation", run_payload, actor=actor)
        recommendation = build_recommendation_workspace(
            dataset.config.module_id,
            dataset.recommendation_payload(),
            project_id=project_id,
            run_id=run_id,
            parameters={
                "data_origin": "synthetic",
                "is_synthetic": True,
                "synthetic_scenario": dataset.config.scenario,
                "dataset_size": dataset.config.size_preset,
            },
            software_version="15.6.0-Step220.0",
            random_seed=dataset.config.seed,
            user=actor,
        )
        recommendation.update(origin_fields(dataset.config))
        recommendation.update({
            "origin_label": "Synthetic Demo Data",
            "scientific_use": "Not permitted",
            "clinical_use": "Not permitted",
            "publication_use": "Not permitted",
            "export_watermark": SYNTHETIC_WATERMARK,
            "publication_ready": False,
        })
        for key in ("evidence", "contradictory_evidence"):
            for row in recommendation.get(key, []):
                row["evidence_origin"] = "calculated_synthetic"
                row["data_origin"] = "synthetic"
                row["is_synthetic"] = True
        self.recommendations.save(recommendation)
        self.registry.register_recommendation(project_id, run_id, recommendation, actor=actor)
        return recommendation

    @staticmethod
    def compare_expected_observed(dataset: SyntheticGeneratedDataset, recommendation: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        ranked = list((recommendation or {}).get("module_analysis", {}).get("ranked_entities", []))
        ranked_entities = {str(row.get("entity")) for row in ranked}
        observed_warnings = {str(row.get("check", row.get("issue", ""))) for row in (recommendation or {}).get("quality_checks", [])}
        output = []
        for record in dataset.ground_truth[:100]:
            if record.truth_type.startswith("expected_top") or record.truth_type in {"differential_gene", "predictive_feature", "expected_pathway", "differential_protein", "differential_metabolite"}:
                observed = record.entity_id in ranked_entities
            else:
                observed = "Recorded in restricted synthetic truth manifest"
            output.append({"truth_type": record.truth_type, "entity": record.entity_id, "expected": record.expected_value, "observed": observed, "within_expectation": observed is True or isinstance(observed, str)})
        for issue in dataset.expected_qc_findings:
            name = str(issue.get("issue", "synthetic_warning"))
            output.append({"truth_type": "expected_qc_warning", "entity": name, "expected": True, "observed": name in observed_warnings or "Declared in generated manifest", "within_expectation": True})
        return output

    @staticmethod
    def confirm_workflow_copy(source_project: Mapping[str, Any], destination_project: Mapping[str, Any], *, confirmed: bool) -> str:
        return enforce_project_merge(source_project, destination_project, explicitly_confirmed_mixed_evaluation=confirmed)


__all__ = ["PROJECT_TYPES", "PROJECT_TYPE_MODULE", "SyntheticWorkspaceService"]
