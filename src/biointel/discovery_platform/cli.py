from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from biointel.synthetic.core import (
    CLEAN_SCENARIOS,
    MODULE_SPECS,
    SYNTHETIC_WATERMARK,
    SyntheticGenerationConfig,
)
from biointel.synthetic.generators import SyntheticDatasetGenerator

from .analysis import analysis_catalog
from .constants import CANDIDATE_TYPES, EVIDENCE_TYPES, PROJECT_STAGES, ROLES, WORKFLOW_TEMPLATES
from .models import ProjectCreate
from .reports import EXPORT_FORMATS
from .service import DiscoveryPlatformService


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def _mapping(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    if value.startswith("@"):
        payload = Path(value[1:]).read_text(encoding="utf-8")
    else:
        payload = value
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    return parsed


def _frame(path: str) -> pd.DataFrame:
    source = Path(path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    suffix = source.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(source)
    if suffix in {".tsv", ".txt"}:
        return pd.read_csv(source, sep="	")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(source)
    if suffix == ".json":
        return pd.read_json(source)
    if suffix == ".jsonl":
        return pd.read_json(source, lines=True)
    if suffix == ".parquet":
        return pd.read_parquet(source)
    raise ValueError(f"Unsupported tabular input format: {suffix}")


def _service(args: argparse.Namespace) -> DiscoveryPlatformService:
    return DiscoveryPlatformService(
        database_path=args.database,
        artifact_root=args.artifacts,
        actor=args.actor,
        role=args.role,
    )


def _run(args: argparse.Namespace) -> Any:
    service = _service(args)
    command = args.platform_command
    if command == "catalog":
        return {
            "project_stages": PROJECT_STAGES,
            "analysis_modules": analysis_catalog(),
            "synthetic_modules": MODULE_SPECS,
            "synthetic_notice": SYNTHETIC_WATERMARK,
        }
    if command == "project-create":
        synthetic = bool(args.synthetic)
        return service.create_project(
            ProjectCreate(
                title=args.title,
                research_question=args.question,
                scientific_objective=args.objective,
                disease_context=args.disease_context,
                organism=args.organism,
                assay_types=tuple(args.assay_type),
                principal_investigator=args.principal_investigator,
                owner=args.owner,
                data_origin=(
                    "synthetic_demo_output"
                    if synthetic else "user_entered_interpretation"
                ),
                is_synthetic=synthetic,
            )
        )
    if command == "project-list":
        return service.list_projects(
            limit=args.limit,
            offset=args.offset,
            stage=args.stage,
        )
    if command == "project-show":
        return service.get_project(args.project_id)
    if command == "dataset-add":
        project = service.get_project(args.project_id)
        synthetic = bool(project["is_synthetic"])
        return service.register_dataset(
            args.project_id,
            name=args.name,
            assay_type=args.assay_type,
            omics_type=args.omics_type,
            organism=args.organism,
            reference_build=args.reference_build,
            data_origin=(
                "synthetic_demo_output"
                if synthetic else "imported_external_result"
            ),
            is_synthetic=synthetic,
            provenance={
                "origin": (
                    "synthetic_demo_output"
                    if synthetic else "imported_external_result"
                )
            },
        )
    if command == "dataset-list":
        return service.list_datasets(
            args.project_id,
            limit=args.limit,
            offset=args.offset,
        )
    if command == "samples-add":
        sample_frame = _frame(args.input).astype(object)
        rows = sample_frame.where(
            pd.notna(sample_frame), None
        ).to_dict(orient="records")
        return service.add_samples(args.dataset_id, rows)
    if command == "ingest":
        return service.ingestion.ingest(
            args.dataset_id,
            args.file,
            required_columns=args.required_column,
            allow_cross_dataset_duplicate=args.allow_duplicate,
        )
    if command == "workflow-template":
        return service.workflows.create_template(
            args.template,
            project_id=args.project_id,
            created_by=service.actor,
        )
    if command == "workflow-list":
        return service.workflows.list_workflows(
            project_id=args.project_id,
            limit=args.limit,
        )
    if command == "run":
        project = service.get_project(args.project_id)
        return service.analysis.run_and_persist(
            project_id=args.project_id,
            module_id=args.module,
            frame=_frame(args.input),
            parameters=_mapping(args.parameters),
            dataset_id=args.dataset_id,
            is_synthetic=bool(project["is_synthetic"]),
            seed=args.seed,
        )
    if command == "run-show":
        return service.execution.run_snapshot(args.run_id)
    if command == "run-verify":
        return service.reproducibility.verify(args.run_id)
    if command == "candidate-add":
        project = service.get_project(args.project_id)
        return service.create_candidate(
            args.project_id,
            candidate_type=args.candidate_type,
            identity=args.identity,
            data_source=args.data_source,
            scores=_mapping(args.scores),
            confidence=args.confidence,
            origin=(
                "synthetic_demo_output"
                if project["is_synthetic"] else "real_calculation"
            ),
        )
    if command == "candidate-list":
        return service.list_candidates(
            args.project_id,
            candidate_type=args.candidate_type,
            lifecycle_state=args.state,
            limit=args.limit,
            offset=args.offset,
        )
    if command == "candidate-rank":
        return service.rank_candidates(args.project_id, _mapping(args.weights))
    if command == "evidence-add":
        project = service.get_project(args.project_id)
        synthetic = bool(project["is_synthetic"])
        return service.add_evidence(
            args.project_id,
            source=args.source,
            title=args.title,
            evidence_type=("Synthetic fixture" if synthetic else args.evidence_type),
            identifier=args.identifier,
            pmid=("" if synthetic else args.pmid),
            doi=("" if synthetic else args.doi),
            verification_state=args.verification,
            origin=(
                "synthetic_demo_output"
                if synthetic else "imported_external_result"
            ),
        )
    if command == "evidence-list":
        return service.list_evidence(
            args.project_id,
            evidence_type=args.evidence_type,
            limit=args.limit,
            offset=args.offset,
        )
    if command == "hypothesis-add":
        project = service.get_project(args.project_id)
        return service.create_hypothesis(
            args.project_id,
            statement=args.statement,
            null_hypothesis=args.null_hypothesis,
            supporting_observations=args.support,
            falsification_criteria=args.falsification,
            origin=(
                "synthetic_demo_output"
                if project["is_synthetic"] else "hypothesis"
            ),
        )
    if command == "report-create":
        return service.reports.create_report(
            args.project_id,
            title=args.title,
            selected_sections=args.section or None,
        )
    if command == "report-export":
        return service.reports.export(
            args.report_id,
            args.format,
            destination=args.output,
        )
    if command == "synthetic-generate":
        config = SyntheticGenerationConfig(
            module_id=args.module,
            scenario=args.scenario or CLEAN_SCENARIOS[args.module],
            size_preset=args.size,
            seed=args.seed,
        )
        generated = SyntheticDatasetGenerator().generate(config)
        project = service.create_project(
            ProjectCreate(
                title=args.title,
                research_question="Can this synthetic scenario exercise the workflow?",
                scientific_objective="Deterministic demonstration and failure testing",
                owner=service.actor,
                data_origin="synthetic_demo_output",
                is_synthetic=True,
            )
        )
        samples, features = config.dimensions
        dataset = service.register_dataset(
            project["project_id"],
            name=f"{args.module} - {config.scenario}",
            assay_type=args.module,
            sample_count=samples,
            feature_count=features,
            data_origin="synthetic_demo_output",
            is_synthetic=True,
            provenance={"origin": "synthetic_demo_output", "seed": args.seed},
        )
        manifest = service.synthetic.register_generated_dataset(
            project_id=project["project_id"],
            dataset_id=dataset["dataset_id"],
            generated=generated,
        )
        return {
            "project": project,
            "dataset": dataset,
            "manifest": manifest,
            "notice": SYNTHETIC_WATERMARK,
        }
    if command == "health":
        return service.health.snapshot()
    if command == "dependencies":
        return service.health.dependency_health(refresh=args.refresh)
    if command == "backup":
        return service.health.backup_database(args.output)
    if command == "audit-verify":
        return service.store.verify_audit_chain()
    raise ValueError(f"Unsupported research-platform command: {command}")


def _paging(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="biointel research-platform",
        description="Local-first BioIntel discovery lab lifecycle, analysis, and evidence CLI.",
    )
    parser.add_argument("--database")
    parser.add_argument("--artifacts")
    parser.add_argument("--actor", default="local_user")
    parser.add_argument("--role", choices=ROLES, default="Administrator")
    sub = parser.add_subparsers(dest="platform_command", required=True)

    sub.add_parser("catalog")

    command = sub.add_parser("project-create")
    command.add_argument("--title", required=True)
    command.add_argument("--question", required=True)
    command.add_argument("--objective", required=True)
    command.add_argument("--owner", default="local_user")
    command.add_argument("--disease-context", default="")
    command.add_argument("--organism", default="")
    command.add_argument("--assay-type", action="append", default=[])
    command.add_argument("--principal-investigator", default="")
    command.add_argument("--synthetic", action="store_true")

    command = sub.add_parser("project-list")
    _paging(command)
    command.add_argument("--stage", choices=PROJECT_STAGES)

    command = sub.add_parser("project-show")
    command.add_argument("project_id")

    command = sub.add_parser("dataset-add")
    command.add_argument("project_id")
    command.add_argument("--name", required=True)
    command.add_argument("--assay-type", default="")
    command.add_argument("--omics-type", default="")
    command.add_argument("--organism", default="")
    command.add_argument("--reference-build", default="")

    command = sub.add_parser("dataset-list")
    command.add_argument("project_id")
    _paging(command)

    command = sub.add_parser("samples-add")
    command.add_argument("dataset_id")
    command.add_argument("--input", required=True)

    command = sub.add_parser("ingest")
    command.add_argument("dataset_id")
    command.add_argument("--file", required=True)
    command.add_argument("--required-column", action="append", default=[])
    command.add_argument("--allow-duplicate", action="store_true")

    command = sub.add_parser("workflow-template")
    command.add_argument("project_id")
    command.add_argument("--template", choices=tuple(WORKFLOW_TEMPLATES), required=True)

    command = sub.add_parser("workflow-list")
    command.add_argument("--project-id")
    command.add_argument("--limit", type=int, default=200)

    command = sub.add_parser("run")
    command.add_argument("project_id")
    command.add_argument("--module", choices=tuple(MODULE_SPECS), required=True)
    command.add_argument("--input", required=True)
    command.add_argument("--parameters")
    command.add_argument("--dataset-id")
    command.add_argument("--seed", type=int)

    command = sub.add_parser("run-show")
    command.add_argument("run_id")

    command = sub.add_parser("run-verify")
    command.add_argument("run_id")

    command = sub.add_parser("candidate-add")
    command.add_argument("project_id")
    command.add_argument("--candidate-type", choices=CANDIDATE_TYPES, required=True)
    command.add_argument("--identity", required=True)
    command.add_argument("--data-source", required=True)
    command.add_argument("--scores", default="{}")
    command.add_argument("--confidence", type=float)

    command = sub.add_parser("candidate-list")
    command.add_argument("project_id")
    command.add_argument("--candidate-type", choices=CANDIDATE_TYPES)
    command.add_argument("--state")
    _paging(command)

    command = sub.add_parser("candidate-rank")
    command.add_argument("project_id")
    command.add_argument("--weights", required=True)

    command = sub.add_parser("evidence-add")
    command.add_argument("project_id")
    command.add_argument("--source", required=True)
    command.add_argument("--title", required=True)
    command.add_argument("--evidence-type", choices=EVIDENCE_TYPES, required=True)
    command.add_argument("--identifier", default="")
    command.add_argument("--pmid", default="")
    command.add_argument("--doi", default="")
    command.add_argument("--verification", default="Unverified")

    command = sub.add_parser("evidence-list")
    command.add_argument("project_id")
    command.add_argument("--evidence-type", choices=EVIDENCE_TYPES)
    _paging(command)

    command = sub.add_parser("hypothesis-add")
    command.add_argument("project_id")
    command.add_argument("--statement", required=True)
    command.add_argument("--null-hypothesis", required=True)
    command.add_argument("--support", action="append", required=True)
    command.add_argument("--falsification", action="append", required=True)

    command = sub.add_parser("report-create")
    command.add_argument("project_id")
    command.add_argument("--title", required=True)
    command.add_argument("--section", action="append")

    command = sub.add_parser("report-export")
    command.add_argument("report_id")
    command.add_argument("--format", choices=EXPORT_FORMATS, required=True)
    command.add_argument("--output", required=True)

    command = sub.add_parser("synthetic-generate")
    command.add_argument("--module", choices=tuple(MODULE_SPECS), required=True)
    command.add_argument("--scenario")
    command.add_argument("--size", choices=("small", "medium", "large"), default="small")
    command.add_argument("--seed", type=int, default=42)
    command.add_argument("--title", default="Synthetic discovery lab")

    sub.add_parser("health")

    command = sub.add_parser("dependencies")
    command.add_argument("--refresh", action="store_true")

    command = sub.add_parser("backup")
    command.add_argument("--output", required=True)

    sub.add_parser("audit-verify")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    service: DiscoveryPlatformService | None = None,
) -> int:
    try:
        args = build_parser().parse_args(list(argv) if argv is not None else None)
        if service is not None:
            args.database = str(service.store.database_path)
            args.artifacts = str(service.store.artifact_root)
            args.actor = service.actor
            args.role = service.role
        _print(_run(args))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                        "partial_results_usable": False,
                    }
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
