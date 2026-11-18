from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from biointel.synthetic import FAILURE_SCENARIOS
from biointel.synthetic.core import SYNTHETIC_WATERMARK, SyntheticGeneratedDataset

from .analysis import ScientificAnalysisPlatform
from .models import PlatformConflictError, PlatformValidationError, new_id, utc_now
from .storage import DiscoveryPlatformStore
from .synthetic_adapter import adapt_generated_dataset


class SyntheticPlatformBridge:
    """Keeps generated fixtures inside an explicit synthetic project boundary."""

    def __init__(
        self,
        store: DiscoveryPlatformStore,
        *,
        actor: str = "local_user",
        role: str = "Administrator",
    ):
        self.store = store
        self.actor = actor
        self.role = role

    def register_generated_dataset(
        self,
        *,
        project_id: str,
        dataset_id: str,
        generated: SyntheticGeneratedDataset,
    ) -> dict[str, Any]:
        project = self.store.row("projects", "project_id", project_id)
        dataset = self.store.row("datasets", "dataset_id", dataset_id)
        if project is None:
            raise KeyError(project_id)
        if dataset is None:
            raise KeyError(dataset_id)
        if dataset["project_id"] != project_id:
            raise PlatformConflictError("Dataset does not belong to the selected project")
        if not project["is_synthetic"] or not dataset["is_synthetic"]:
            raise PlatformConflictError(
                "Synthetic manifests can only be registered to synthetic projects and datasets"
            )
        if not generated.is_synthetic or generated.data_origin != "synthetic":
            raise PlatformValidationError("Generated dataset is missing synthetic origin metadata")
        manifest = generated.manifest.to_dict()
        parameters = {
            "config": generated.config.to_dict(),
            "manifest": manifest,
            "ground_truth": [row.to_dict() for row in generated.ground_truth],
            "expected_qc_findings": generated.expected_qc_findings,
            "expected_recommendations": generated.expected_recommendations,
            "tutorial_notes": generated.tutorial_notes,
        }
        output_hashes = {
            name: hashlib.sha256(
                (
                    table.to_csv(index=False).encode("utf-8")
                    if hasattr(table, "to_csv")
                    else json.dumps(table, sort_keys=True, default=str).encode("utf-8")
                )
            ).hexdigest()
            for name, table in generated.tables.items()
        }
        manifest_id = new_id("SYNMAN")
        self.store.insert(
            "synthetic_manifests",
            {
                "manifest_id": manifest_id,
                "project_id": project_id,
                "dataset_id": dataset_id,
                "generator": generated.manifest.generator_id,
                "generator_version": generated.manifest.generator_version,
                "random_seed": generated.config.seed,
                "parameters_json": parameters,
                "output_hashes_json": output_hashes,
                "notice": SYNTHETIC_WATERMARK,
                "created_at_utc": utc_now(),
            },
        )
        self.store.audit(
            "synthetic_manifest_registered", "synthetic_manifest", manifest_id,
            project_id=project_id, actor=self.actor, role=self.role,
            detail={
                "dataset_id": dataset_id,
                "module_id": generated.config.module_id,
                "scenario": generated.config.scenario,
                "seed": generated.config.seed,
            },
        )
        return self.store.row("synthetic_manifests", "manifest_id", manifest_id) or {}

    def run_generated_analysis(
        self,
        *,
        project_id: str,
        dataset_id: str,
        generated: SyntheticGeneratedDataset,
    ) -> dict[str, Any]:
        """Run an origin-labelled synthetic fixture through the production engine."""

        project = self.store.row("projects", "project_id", project_id)
        dataset = self.store.row("datasets", "dataset_id", dataset_id)
        if project is None:
            raise KeyError(project_id)
        if dataset is None:
            raise KeyError(dataset_id)
        if dataset["project_id"] != project_id:
            raise PlatformConflictError("Dataset does not belong to the selected project")
        if not project["is_synthetic"] or not dataset["is_synthetic"]:
            raise PlatformConflictError("Synthetic analysis requires a synthetic project boundary")
        prepared = adapt_generated_dataset(generated)
        analysis = ScientificAnalysisPlatform(self.store)
        try:
            run = analysis.run_and_persist(
                project_id=project_id,
                dataset_id=dataset_id,
                module_id=prepared.module_id,
                frame=prepared.frame,
                parameters=prepared.parameters,
                is_synthetic=True,
                seed=generated.config.seed,
            )
        except PlatformConflictError as exc:
            expected_failures = set(FAILURE_SCENARIOS.values())
            if generated.config.scenario not in expected_failures:
                raise
            failed = self.store.rows(
                "runs",
                filters={
                    "project_id": project_id,
                    "dataset_id": dataset_id,
                    "module_id": prepared.module_id,
                    "status": "Failed",
                },
                order_by="started_at_utc",
                limit=1,
            )
            return {
                "status": "Expected failure captured",
                "error": str(exc),
                "run": failed[0] if failed else None,
                "adapter_version": prepared.adapter_version,
                "source_tables": list(prepared.source_tables),
                "input_rows": len(prepared.frame),
            }
        return {
            "status": "Completed",
            "run": run,
            "adapter_version": prepared.adapter_version,
            "source_tables": list(prepared.source_tables),
            "input_rows": len(prepared.frame),
        }

    def project_status(self, project_id: str) -> dict[str, Any]:
        project = self.store.row("projects", "project_id", project_id)
        if project is None:
            raise KeyError(project_id)
        manifests = self.store.rows(
            "synthetic_manifests",
            filters={"project_id": project_id},
            order_by="created_at_utc",
            limit=5000,
        )
        with self.store.connect(read_only=True) as connection:
            contamination = {
                "synthetic_datasets_in_real_project": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM datasets WHERE project_id=? AND is_synthetic=1",
                        (project_id,),
                    ).fetchone()[0]
                )
                if not project["is_synthetic"] else 0,
                "synthetic_runs_in_real_project": int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM runs
                        WHERE project_id=? AND json_extract(provenance_json,'$.origin')='synthetic_demo_output'
                        """,
                        (project_id,),
                    ).fetchone()[0]
                )
                if not project["is_synthetic"] else 0,
            }
        return {
            "project_id": project_id,
            "is_synthetic": project["is_synthetic"],
            "notice": SYNTHETIC_WATERMARK if project["is_synthetic"] else "",
            "manifests": manifests,
            "contamination": contamination,
            "boundary_valid": not any(contamination.values()),
        }

    def reset_project(self, project_id: str, *, confirmation: str) -> dict[str, Any]:
        project = self.store.row("projects", "project_id", project_id)
        if project is None:
            raise KeyError(project_id)
        if not project["is_synthetic"]:
            raise PlatformConflictError("Reset is restricted to synthetic projects")
        if confirmation != project_id:
            raise PlatformValidationError("Reset requires the exact synthetic project ID")
        with self.store.transaction() as connection:
            counts = {}
            for table in (
                "validation_results", "recommendations", "experiments", "hypotheses",
                "evidence", "candidates", "artifacts", "runs", "datasets",
            ):
                cursor = connection.execute(
                    f"DELETE FROM {table} WHERE project_id=?", (project_id,)
                )
                counts[table] = int(cursor.rowcount)
        self.store.audit(
            "synthetic_project_reset", "project", project_id,
            project_id=project_id, actor=self.actor, role=self.role,
            detail={"deleted": counts},
        )
        return {"project_id": project_id, "reset": True, "deleted": counts}


__all__ = ["SyntheticPlatformBridge"]
