from __future__ import annotations

from biointel.runtime_paths import runtime_database_path, runtime_report_path

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd

from biointel.assets.research_assets import (
    search_assets,
    seed_asset_store,
)
from biointel.assurance import build_final_assurance
from biointel.chemistry.common_compounds import (
    load_common_compound_directory,
    search_common_compounds,
)
from biointel.data.coverage_packs import (
    load_coverage_manifest,
    register_coverage_datasets,
    seed_demo_workspace,
    verify_coverage_integrity,
    write_coverage_packs,
)
from biointel.data.data_packs import (
    data_library_summary,
    register_bundled_data_packs,
    write_data_packs,
)
from biointel.data.dataset_registry import (
    list_datasets,
    register_dataset,
)
from biointel.database.migrations import (
    optimize_existing_registries,
)
from biointel.dti.batch_pipeline import run_chunked_batch_prediction
from biointel.dti.predictor import (
    batch_predict_dti,
    predict_dti_pair,
)
from biointel.governance.governance_registry import (
    create_decision,
    create_milestone,
    governance_portfolio_summary,
    project_governance_snapshot,
    upsert_gate,
)
from biointel.governance.reproducibility import (
    build_project_evidence_package,
    build_project_manifest,
    inspect_project_evidence_package,
    project_readiness,
)
from biointel.integrations.cache import ExternalResponseCache
from biointel.integrations.chembl_dataset import (
    ChEMBLActivityQuery,
    build_chembl_activity_dataset,
)
from biointel.integrations.http_client import (
    DEFAULT_CACHE_DIRECTORY,
    DEFAULT_CACHE_TTL_SECONDS,
)
from biointel.intelligence.data_intelligence import (
    all_database_health,
    optimize_all_databases,
    universal_search,
)
from biointel.intelligence.knowledge_warehouse import (
    search_knowledge,
    seed_knowledge_warehouse,
)
from biointel.internet.connectivity import (
    check_internet_services,
    internet_configuration,
)
from biointel.internet.download_registry import (
    download_summary,
    list_downloads,
)
from biointel.internet.downloader import download_public_file
from biointel.internet.network_policy import internet_policy_from_environment
from biointel.internet.pubchem import fetch_pubchem_compound_by_name
from biointel.internet.rcsb import download_rcsb_structure, fetch_rcsb_entry
from biointel.observability.analytics_store import (
    analytics_summary,
    seed_analytics_store,
)
from biointel.operations.activity_center import activity_export
from biointel.operations.executive_summary import build_executive_summary
from biointel.portfolio.project_exchange import (
    import_project_bundle,
    project_bundle_json,
)
from biointel.portfolio.project_registry import (
    create_project,
    get_project,
    list_projects,
    update_project,
)
from biointel.reports.release_bundle import (
    build_model_release_bundle,
)
from biointel.reports.workspace_report import (
    build_workspace_report_data,
    build_workspace_report_html,
)
from biointel.sequence.dna_analysis import nucleotide_statistics
from biointel.sequence.parser import parse_sequence_text
from biointel.sequence.protein_analysis import protein_statistics
from biointel.sequence.validators import (
    SequenceType,
    detect_sequence_type,
    validate_for_type,
)
from biointel.training.experiment_registry import (
    register_experiment,
)
from biointel.training.external_validation import (
    evaluate_external_dataset,
)
from biointel.training.model_artifact import (
    load_model_artifact,
    save_model_artifact,
)
from biointel.training.model_catalog import (
    sync_model_catalog,
    update_model_catalog,
)
from biointel.training.trainers import (
    TrainingConfig,
    train_dti_model,
)
from biointel.ui.navigation import search_pages
from biointel.utils.audit_log import verify_audit_chain
from biointel.utils.diagnostics import (
    diagnostic_summary,
    run_diagnostics,
)
from biointel.utils.workspace_backup import (
    create_workspace_backup,
    inspect_workspace_backup,
    restore_workspace_backup,
)


def _root() -> Path:
    for candidate in (
        Path.cwd(),
        Path(__file__).resolve().parents[2],
    ):
        if (candidate / "models").exists() and (candidate / "config").exists():
            return candidate
    return Path.cwd()


def _print(payload: object) -> None:
    print(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


def _read(
    text: str | None,
    file: str | None,
) -> str:
    if text:
        return text
    if file:
        return Path(file).read_text(encoding="utf-8")
    raise ValueError("Provide text or input file.")


def _model(name: str):
    root = _root()
    return load_model_artifact(
        root / "models" / Path(name).name,
        trusted_root=root / "models",
    )


def sequence_cmd(args: argparse.Namespace) -> None:
    parsed = parse_sequence_text(_read(args.text, args.input_file))
    detection = detect_sequence_type(parsed.sequence)
    selected = (
        detection.detected_type
        if args.sequence_type == "auto"
        else SequenceType(args.sequence_type)
    )
    if selected not in {
        SequenceType.DNA,
        SequenceType.RNA,
        SequenceType.PROTEIN,
    }:
        raise ValueError("Ambiguous sequence type; specify it explicitly.")
    if validate_for_type(parsed.sequence, selected):
        raise ValueError("Invalid sequence symbols.")

    result = (
        nucleotide_statistics(
            parsed.sequence,
            is_rna=selected == SequenceType.RNA,
        )
        if selected in {SequenceType.DNA, SequenceType.RNA}
        else protein_statistics(parsed.sequence)
    )
    payload = {
        "header": parsed.header,
        "sequence_type": selected.value,
        "analysis": result,
    }
    if args.output:
        Path(args.output).write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
    else:
        _print(payload)


def train_cmd(args: argparse.Namespace) -> None:
    root = _root()
    dataframe = pd.read_csv(args.csv)
    config = TrainingConfig(
        task_type=args.task,
        model_name=args.model,
        split_strategy=args.split,
        fingerprint_bits=args.fingerprint_bits,
        dataset_name=args.dataset_name,
        model_version=args.model_version,
        conformal_alpha=args.conformal_alpha,
    )
    result = train_dti_model(dataframe, config)
    saved = save_model_artifact(
        result.artifact,
        root / "models" / Path(args.output).name,
    )
    register_experiment(
        runtime_database_path(root, "experiments.sqlite3"),
        result.artifact,
        saved.name,
    )
    _print(
        {
            "saved_model": str(saved),
            "experiment_id": (result.artifact.metadata.experiment_id),
            "metrics": result.metrics,
        }
    )


def predict_cmd(args: argparse.Namespace) -> None:
    parsed = parse_sequence_text(_read(args.protein, args.protein_file))
    _print(
        asdict(
            predict_dti_pair(
                _model(args.model),
                args.smiles,
                parsed.sequence,
            )
        )
    )


def batch_cmd(args: argparse.Namespace) -> None:
    output = batch_predict_dti(
        _model(args.model),
        pd.read_csv(args.csv),
        max_rows=args.max_rows,
    )
    output.to_csv(args.output, index=False)
    _print(
        {
            "output": args.output,
            "rows": len(output),
        }
    )


def external_cmd(args: argparse.Namespace) -> None:
    result = evaluate_external_dataset(
        _model(args.model),
        pd.read_csv(args.csv),
    )
    payload = {
        "metrics": result.metrics,
        "conformal_diagnostics": (result.conformal_diagnostics),
        "drift": result.drift,
        "dataset_sha256": result.dataset_sha256,
    }
    Path(args.output).write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    result.predictions.to_csv(
        Path(args.output).with_suffix(".predictions.csv"),
        index=False,
    )
    _print(payload)


def chembl_cmd(args: argparse.Namespace) -> None:
    result = build_chembl_activity_dataset(
        ChEMBLActivityQuery(
            target_chembl_id=args.target,
            activity_type=args.activity_type,
            task_type=args.task,
            classification_threshold_nm=args.threshold_nm,
            max_records=args.max_records,
        )
    )
    result.dataset.to_csv(args.output, index=False)
    result.rejected.to_csv(
        Path(args.output).with_suffix(".rejected.csv"),
        index=False,
    )
    _print(result.metadata)


def status_cmd(_: argparse.Namespace) -> None:
    root = _root()
    rows = []
    for path in sorted((root / "models").glob("*.joblib")):
        try:
            artifact = load_model_artifact(
                path,
                trusted_root=root / "models",
            )
            rows.append(
                {
                    "filename": path.name,
                    "artifact_version": (artifact.metadata.artifact_version),
                    "task_type": (artifact.metadata.task_type),
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "filename": path.name,
                    "error": str(exc),
                }
            )
    _print({"models": rows})


def bundle_cmd(args: argparse.Namespace) -> None:
    root = _root()
    path = root / "models" / Path(args.model).name
    artifact = load_model_artifact(
        path,
        trusted_root=root / "models",
    )
    Path(args.output).write_bytes(build_model_release_bundle(artifact, path))
    _print({"bundle": args.output})


def workspace_backup_cmd(
    args: argparse.Namespace,
) -> None:
    content = create_workspace_backup(
        _root(),
        include_demo_models=args.include_demo_models,
        include_cache=args.include_cache,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    summary = inspect_workspace_backup(content)
    _print(
        {
            "output": str(output),
            "file_count": summary.file_count,
            "total_bytes": summary.total_bytes,
            "created_at_utc": summary.created_at_utc,
        }
    )


def workspace_restore_cmd(
    args: argparse.Namespace,
) -> None:
    backup = Path(args.backup).read_bytes()
    result = restore_workspace_backup(
        _root(),
        backup,
        overwrite=args.overwrite,
        allow_demo_models=args.allow_demo_models,
    )
    _print(result)


def diagnose_cmd(_: argparse.Namespace) -> None:
    checks = run_diagnostics(_root())
    _print(
        {
            "summary": diagnostic_summary(checks),
            "checks": [check.to_dict() for check in checks],
        }
    )


def cache_status_cmd(_: argparse.Namespace) -> None:
    cache = ExternalResponseCache(DEFAULT_CACHE_DIRECTORY)
    _print(
        {
            "entries": len(cache.list_entries()),
            "size_bytes": cache.total_size_bytes(),
            "ttl_seconds": DEFAULT_CACHE_TTL_SECONDS,
        }
    )


def cache_clear_cmd(args: argparse.Namespace) -> None:
    cache = ExternalResponseCache(DEFAULT_CACHE_DIRECTORY)
    removed = cache.clear() if args.all else cache.remove_expired(DEFAULT_CACHE_TTL_SECONDS)
    _print(
        {
            "removed": removed,
            "mode": "all" if args.all else "expired",
        }
    )


def dataset_register_cmd(args: argparse.Namespace) -> None:
    dataframe = pd.read_csv(args.csv)
    record = register_dataset(
        runtime_database_path(_root(), "datasets.sqlite3"),
        dataframe,
        dataset_name=args.name,
        dataset_version=args.version,
        task_type=args.task,
        source_description=args.source,
        activity_type=args.activity_type,
        parent_sha256=args.parent_sha256,
        notes=args.notes,
    )
    _print(asdict(record))


def dataset_list_cmd(_: argparse.Namespace) -> None:
    records = list_datasets(runtime_database_path(_root(), "datasets.sqlite3"))
    _print({"datasets": [asdict(record) for record in records]})


def model_catalog_cmd(_: argparse.Namespace) -> None:
    entries = sync_model_catalog(_root() / "models")
    _print({"models": [asdict(entry) for entry in entries]})


def model_lifecycle_cmd(args: argparse.Namespace) -> None:
    entry = update_model_catalog(
        _root() / "models",
        args.model,
        state=args.state,
        is_default=True if args.default else None,
        notes=args.notes,
    )
    _print(asdict(entry))


def chunked_batch_cmd(args: argparse.Namespace) -> None:
    dataframe = pd.read_csv(args.csv)
    output, summary = run_chunked_batch_prediction(
        _model(args.model),
        dataframe,
        chunk_size=args.chunk_size,
        max_rows=args.max_rows,
        checkpoint_path=args.checkpoint,
        resume=not args.no_resume,
    )
    output.to_csv(args.output, index=False)
    _print(
        {
            "output": args.output,
            "summary": asdict(summary),
        }
    )


def workspace_report_cmd(args: argparse.Namespace) -> None:
    report = build_workspace_report_data(
        _root(),
        title=args.title,
        notes=args.notes,
    )
    html_content = build_workspace_report_html(report)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_content, encoding="utf-8")
    json_path = output.with_suffix(".json")
    json_path.write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )
    _print(
        {
            "html_report": str(output),
            "json_report": str(json_path),
            "datasets": report["workflow_status"]["datasets"]["total"],
            "models": report["workflow_status"]["models"]["total"],
            "experiments": report["workflow_status"]["experiments"]["total"],
        }
    )


def tool_catalog_cmd(args: argparse.Namespace) -> None:
    pages = search_pages(
        query=args.query or "",
        category=args.category,
    )
    _print(
        {
            "tools": [
                {
                    "key": page.key,
                    "path": page.path,
                    "title": page.title,
                    "icon": page.icon,
                    "category": page.category,
                    "description": page.description,
                }
                for page in pages
            ]
        }
    )


def project_create_cmd(args: argparse.Namespace) -> None:
    record = create_project(
        runtime_database_path(_root(), "projects.sqlite3"),
        project_code=args.code,
        name=args.name,
        status=args.status,
        priority=args.priority,
        objective=args.objective,
        owner_label=args.owner,
        tags=args.tags,
        target_date=args.target_date,
        dataset_sha256=args.dataset_sha256,
        model_filename=args.model,
        notes=args.notes,
    )
    _print(asdict(record))


def project_list_cmd(_: argparse.Namespace) -> None:
    records = list_projects(runtime_database_path(_root(), "projects.sqlite3"))
    _print({"projects": [asdict(record) for record in records]})


def project_update_cmd(args: argparse.Namespace) -> None:
    registry = runtime_database_path(_root(), "projects.sqlite3")
    current = get_project(registry, args.project_id)
    if current is None:
        raise ValueError("Project not found")
    changes = {
        key: value
        for key, value in {
            "status": args.status,
            "priority": args.priority,
            "owner_label": args.owner,
            "target_date": args.target_date,
            "dataset_sha256": args.dataset_sha256,
            "model_filename": args.model,
            "notes": args.notes,
        }.items()
        if value is not None
    }
    updated = update_project(
        registry,
        args.project_id,
        **changes,
    )
    _print(asdict(updated))


def executive_summary_cmd(args: argparse.Namespace) -> None:
    payload = build_executive_summary(_root())
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
    _print(payload)


def activity_export_cmd(args: argparse.Namespace) -> None:
    payload = activity_export(_root())
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
    _print(payload)


def milestone_create_cmd(args: argparse.Namespace) -> None:
    record = create_milestone(
        runtime_database_path(_root(), "projects.sqlite3"),
        args.project_id,
        title=args.title,
        status=args.status,
        due_date=args.due_date,
        owner_label=args.owner,
        acceptance_criteria=args.acceptance,
        evidence_reference=args.evidence,
        notes=args.notes,
    )
    _print(asdict(record))


def decision_record_cmd(args: argparse.Namespace) -> None:
    record = create_decision(
        runtime_database_path(_root(), "projects.sqlite3"),
        args.project_id,
        title=args.title,
        decision=args.decision,
        status=args.status,
        decision_date=args.decision_date,
        context=args.context,
        rationale=args.rationale,
        alternatives=args.alternatives,
        impact=args.impact,
        approver_label=args.approver,
        evidence_reference=args.evidence,
    )
    _print(asdict(record))


def gate_set_cmd(args: argparse.Namespace) -> None:
    record = upsert_gate(
        runtime_database_path(_root(), "projects.sqlite3"),
        args.project_id,
        gate_name=args.gate,
        status=args.status,
        reviewer_label=args.reviewer,
        conditions=args.conditions,
        evidence_reference=args.evidence,
        decision_date=args.decision_date,
    )
    _print(asdict(record))


def governance_summary_cmd(args: argparse.Namespace) -> None:
    registry = runtime_database_path(_root(), "projects.sqlite3")
    payload = (
        project_governance_snapshot(
            registry,
            args.project_id,
        )
        if args.project_id
        else governance_portfolio_summary(registry)
    )
    _print(payload)


def project_readiness_cmd(args: argparse.Namespace) -> None:
    payload = project_readiness(
        _root(),
        args.project_id,
    )
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
    _print(payload)


def evidence_manifest_cmd(args: argparse.Namespace) -> None:
    payload = build_project_manifest(
        _root(),
        args.project_id,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _print(
        {
            "output": str(output),
            "readiness": payload["readiness"]["percent"],
        }
    )


def evidence_package_cmd(args: argparse.Namespace) -> None:
    content = build_project_evidence_package(
        _root(),
        args.project_id,
        include_model_files=args.include_model_files,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    summary = inspect_project_evidence_package(content)
    _print(
        {
            "output": str(output),
            "project_code": summary.project_code,
            "readiness_score": summary.readiness_score,
            "file_count": summary.file_count,
            "total_bytes": summary.total_bytes,
            "included_model_files": summary.included_model_files,
        }
    )


def project_export_cmd(args: argparse.Namespace) -> None:
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        project_bundle_json(
            runtime_database_path(_root(), "projects.sqlite3"),
            args.project_id,
        ),
        encoding="utf-8",
    )
    _print({"output": str(output)})


def project_import_cmd(args: argparse.Namespace) -> None:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    record = import_project_bundle(
        runtime_database_path(_root(), "projects.sqlite3"),
        payload,
        project_code=args.code,
        name_suffix=args.name_suffix,
    )
    _print(asdict(record))


def audit_verify_cmd(args: argparse.Namespace) -> None:
    payload = verify_audit_chain(runtime_report_path(_root(), "audit.jsonl"))
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
    _print(payload)


def data_pack_status_cmd(_: argparse.Namespace) -> None:
    _print(data_library_summary(_root()))


def data_pack_register_cmd(_: argparse.Namespace) -> None:
    records = register_bundled_data_packs(_root())
    _print(
        {
            "registered_count": len(records),
            "datasets": records,
        }
    )


def data_pack_generate_cmd(_: argparse.Namespace) -> None:
    records = write_data_packs(_root())
    _print(
        {
            "generated_count": len(records),
            "packs": [asdict(record) for record in records],
        }
    )


def double_ml_status_cmd(_: argparse.Namespace) -> None:
    summary = data_library_summary(_root())
    benchmark = summary["benchmark"]
    _print(
        {
            "data_pack_version": benchmark.get("data_pack_version"),
            "double_ultra_rows": 32000,
            "double_models": [
                row
                for row in benchmark.get("ranking", [])
                if row.get("training_pack") == "double_ultra"
            ],
            "overall_best_models": benchmark.get("best_models", {}),
        }
    )


def five_x_ml_status_cmd(_: argparse.Namespace) -> None:
    summary = data_library_summary(_root())
    benchmark = summary["benchmark"]
    _print(
        {
            "data_pack_version": benchmark.get("data_pack_version"),
            "five_x_rows": 160000,
            "unique_compounds": 1000,
            "unique_targets": 160,
            "five_x_models": [
                row
                for row in benchmark.get("ranking", [])
                if row.get("training_pack") == "five_x_ultra"
            ],
            "overall_best_models": benchmark.get(
                "best_models",
                {},
            ),
        }
    )


def coverage_status_cmd(_: argparse.Namespace) -> None:
    _print(
        {
            "manifest": load_coverage_manifest(_root()),
            "integrity": verify_coverage_integrity(_root()),
        }
    )


def coverage_generate_cmd(_: argparse.Namespace) -> None:
    assets = write_coverage_packs(_root())
    records = register_coverage_datasets(_root())
    _print(
        {
            "generated_assets": len(assets),
            "registered_datasets": len(records),
            "integrity": verify_coverage_integrity(_root()),
        }
    )


def demo_workspace_seed_cmd(args: argparse.Namespace) -> None:
    _print(
        seed_demo_workspace(
            _root(),
            replace_existing_demo=not args.keep_existing_demo,
        )
    )



def final_assurance_cmd(args: argparse.Namespace) -> None:
    report = build_final_assurance(_root())
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    _print(report)

def database_status_cmd(_: argparse.Namespace) -> None:
    _print(all_database_health(_root()))


def database_seed_cmd(_: argparse.Namespace) -> None:
    root = _root()
    existing = optimize_existing_registries(root)
    knowledge = seed_knowledge_warehouse(root)
    analytics = seed_analytics_store(root)
    assets = seed_asset_store(root)
    _print(
        {
            "existing_registries": existing,
            "knowledge": asdict(knowledge),
            "analytics": asdict(analytics),
            "assets": asdict(assets),
            "health": all_database_health(root),
        }
    )


def database_optimize_cmd(
    args: argparse.Namespace,
) -> None:
    _print(
        optimize_all_databases(
            _root(),
            vacuum=args.vacuum,
        )
    )


def intelligence_search_cmd(
    args: argparse.Namespace,
) -> None:
    _print(
        universal_search(
            _root(),
            args.query,
            limit_per_source=args.limit,
        )
    )


def knowledge_search_cmd(
    args: argparse.Namespace,
) -> None:
    root = _root()
    _print(
        {
            "results": search_knowledge(
                runtime_database_path(root, "knowledge.sqlite3"),
                args.query,
                entity_type=args.entity_type,
                status=args.status,
                limit=args.limit,
            )
        }
    )


def analytics_overview_cmd(
    args: argparse.Namespace,
) -> None:
    _print(
        asdict(
            analytics_summary(
                runtime_database_path(_root(), "analytics.sqlite3"),
                days=args.days,
            )
        )
    )


def asset_search_cmd(
    args: argparse.Namespace,
) -> None:
    _print(
        {
            "results": search_assets(
                runtime_database_path(_root(), "assets.sqlite3"),
                args.query,
                asset_type=args.asset_type,
                favourites_only=args.favourites_only,
                limit=args.limit,
            )
        }
    )


def internet_status_cmd(_: argparse.Namespace) -> None:
    _print(
        {
            "configuration": internet_configuration(),
            "downloads": download_summary(runtime_database_path(_root(), "internet_downloads.sqlite3")),
        }
    )


def internet_check_cmd(_: argparse.Namespace) -> None:
    _print(check_internet_services(policy=internet_policy_from_environment()))


def internet_download_list_cmd(args: argparse.Namespace) -> None:
    records = list_downloads(
        runtime_database_path(_root(), "internet_downloads.sqlite3"),
        provider=args.provider,
        limit=args.limit,
    )
    _print({"records": [asdict(record) for record in records]})


def pdb_fetch_cmd(args: argparse.Namespace) -> None:
    policy = internet_policy_from_environment()
    if args.metadata_only:
        _print(asdict(fetch_rcsb_entry(args.pdb_id, policy=policy)))
        return
    result, record = download_rcsb_structure(
        args.pdb_id,
        args.format,
        project_root=_root(),
        policy=policy,
    )
    payload = asdict(result)
    payload["path"] = str(result.path)
    _print({"download": payload, "registry": asdict(record)})


def pubchem_lookup_cmd(args: argparse.Namespace) -> None:
    _print(
        asdict(
            fetch_pubchem_compound_by_name(
                args.name,
                policy=internet_policy_from_environment(),
            )
        )
    )


def common_compound_search_cmd(args: argparse.Namespace) -> None:
    directory = load_common_compound_directory(_root())
    results = search_common_compounds(
        directory,
        args.query,
        name_type=args.name_type,
        limit=args.limit,
    )
    _print(
        {
            "directory_rows": len(directory),
            "results": results.to_dict(orient="records"),
        }
    )


def public_url_download_cmd(args: argparse.Namespace) -> None:
    policy = replace(
        internet_policy_from_environment(),
        official_hosts_only=args.official_hosts_only,
    )
    result, record = download_public_file(
        args.url,
        _root() / "data" / "internet_downloads" / "public_https",
        project_root=_root(),
        registry_path=runtime_database_path(_root(), "internet_downloads.sqlite3"),
        provider=args.provider,
        resource_id=None,
        preferred_filename=args.filename,
        policy=policy,
        max_bytes=args.max_mb * 1024 * 1024,
        notes="CLI-requested public HTTPS research download.",
    )
    payload = asdict(result)
    payload["path"] = str(result.path)
    _print({"download": payload, "registry": asdict(record)})

def research_platform_cmd(args: argparse.Namespace) -> None:
    from biointel.discovery_platform.cli import main as platform_main

    status = platform_main(args.platform_args)
    if status:
        raise ValueError("Research-platform command failed; see the structured error above.")



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="biointel")
    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    command = sub.add_parser("sequence-analyze")
    command.add_argument("--text")
    command.add_argument("--input-file")
    command.add_argument(
        "--sequence-type",
        choices=["auto", "DNA", "RNA", "Protein"],
        default="auto",
    )
    command.add_argument("--output")
    command.set_defaults(func=sequence_cmd)

    command = sub.add_parser("train")
    command.add_argument("--csv", required=True)
    command.add_argument(
        "--task",
        choices=["classification", "regression"],
        required=True,
    )
    command.add_argument(
        "--model",
        default="random_forest",
    )
    command.add_argument(
        "--split",
        default="random_pair",
    )
    command.add_argument(
        "--fingerprint-bits",
        type=int,
        default=256,
    )
    command.add_argument(
        "--dataset-name",
        default="cli_dataset",
    )
    command.add_argument(
        "--model-version",
        default="1.0.0",
    )
    command.add_argument(
        "--conformal-alpha",
        type=float,
        default=0.1,
    )
    command.add_argument("--output", required=True)
    command.set_defaults(func=train_cmd)

    command = sub.add_parser("predict")
    command.add_argument("--model", required=True)
    command.add_argument("--smiles", required=True)
    command.add_argument("--protein")
    command.add_argument("--protein-file")
    command.set_defaults(func=predict_cmd)

    command = sub.add_parser("batch-predict")
    command.add_argument("--model", required=True)
    command.add_argument("--csv", required=True)
    command.add_argument("--output", required=True)
    command.add_argument(
        "--max-rows",
        type=int,
        default=1000,
    )
    command.set_defaults(func=batch_cmd)

    command = sub.add_parser("external-validate")
    command.add_argument("--model", required=True)
    command.add_argument("--csv", required=True)
    command.add_argument("--output", required=True)
    command.set_defaults(func=external_cmd)

    command = sub.add_parser("chembl-build")
    command.add_argument("--target", required=True)
    command.add_argument(
        "--activity-type",
        default="IC50",
    )
    command.add_argument(
        "--task",
        default="regression",
    )
    command.add_argument(
        "--threshold-nm",
        type=float,
        default=1000,
    )
    command.add_argument(
        "--max-records",
        type=int,
        default=1000,
    )
    command.add_argument("--output", required=True)
    command.set_defaults(func=chembl_cmd)

    command = sub.add_parser("model-status")
    command.set_defaults(func=status_cmd)

    command = sub.add_parser("release-bundle")
    command.add_argument("--model", required=True)
    command.add_argument("--output", required=True)
    command.set_defaults(func=bundle_cmd)

    command = sub.add_parser("workspace-backup")
    command.add_argument("--output", required=True)
    command.add_argument(
        "--include-demo-models",
        action="store_true",
    )
    command.add_argument(
        "--include-cache",
        action="store_true",
    )
    command.set_defaults(func=workspace_backup_cmd)

    command = sub.add_parser("workspace-restore")
    command.add_argument("--backup", required=True)
    command.add_argument(
        "--overwrite",
        action="store_true",
    )
    command.add_argument(
        "--allow-demo-models",
        action="store_true",
    )
    command.set_defaults(func=workspace_restore_cmd)

    command = sub.add_parser("diagnose")
    command.set_defaults(func=diagnose_cmd)

    command = sub.add_parser("cache-status")
    command.set_defaults(func=cache_status_cmd)

    command = sub.add_parser("cache-clear")
    command.add_argument(
        "--all",
        action="store_true",
        help=("Clear every cache entry instead of only " "expired entries."),
    )
    command.set_defaults(func=cache_clear_cmd)

    command = sub.add_parser("dataset-register")
    command.add_argument("--csv", required=True)
    command.add_argument("--name", required=True)
    command.add_argument("--version", default="1.0")
    command.add_argument(
        "--task",
        choices=["classification", "regression", "unlabelled"],
        default="unlabelled",
    )
    command.add_argument("--source", default="CLI CSV registration")
    command.add_argument("--activity-type")
    command.add_argument("--parent-sha256")
    command.add_argument("--notes", default="")
    command.set_defaults(func=dataset_register_cmd)

    command = sub.add_parser("dataset-list")
    command.set_defaults(func=dataset_list_cmd)

    command = sub.add_parser("model-catalog")
    command.set_defaults(func=model_catalog_cmd)

    command = sub.add_parser("model-lifecycle")
    command.add_argument("--model", required=True)
    command.add_argument(
        "--state",
        choices=["candidate", "active", "archived"],
        required=True,
    )
    command.add_argument("--default", action="store_true")
    command.add_argument("--notes")
    command.set_defaults(func=model_lifecycle_cmd)

    command = sub.add_parser("chunked-batch-predict")
    command.add_argument("--model", required=True)
    command.add_argument("--csv", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--checkpoint")
    command.add_argument("--chunk-size", type=int, default=100)
    command.add_argument("--max-rows", type=int, default=10000)
    command.add_argument("--no-resume", action="store_true")
    command.set_defaults(func=chunked_batch_cmd)

    command = sub.add_parser("workspace-report")
    command.add_argument(
        "--title",
        default="BioIntel AI Research Workspace Report",
    )
    command.add_argument("--notes", default="")
    command.add_argument("--output", required=True)
    command.set_defaults(func=workspace_report_cmd)

    command = sub.add_parser("tool-catalog")
    command.add_argument("--query")
    command.add_argument("--category")
    command.set_defaults(func=tool_catalog_cmd)

    command = sub.add_parser("project-create")
    command.add_argument("--code", required=True)
    command.add_argument("--name", required=True)
    command.add_argument(
        "--status",
        choices=[
            "Planning",
            "Active",
            "Validation",
            "Paused",
            "Completed",
            "Archived",
        ],
        default="Planning",
    )
    command.add_argument(
        "--priority",
        choices=["Low", "Medium", "High", "Critical"],
        default="Medium",
    )
    command.add_argument("--objective", default="")
    command.add_argument("--owner", default="")
    command.add_argument("--tags", default="")
    command.add_argument("--target-date")
    command.add_argument("--dataset-sha256")
    command.add_argument("--model")
    command.add_argument("--notes", default="")
    command.set_defaults(func=project_create_cmd)

    command = sub.add_parser("project-list")
    command.set_defaults(func=project_list_cmd)

    command = sub.add_parser("project-update")
    command.add_argument("--project-id", required=True)
    command.add_argument(
        "--status",
        choices=[
            "Planning",
            "Active",
            "Validation",
            "Paused",
            "Completed",
            "Archived",
        ],
    )
    command.add_argument(
        "--priority",
        choices=["Low", "Medium", "High", "Critical"],
    )
    command.add_argument("--owner")
    command.add_argument("--target-date")
    command.add_argument("--dataset-sha256")
    command.add_argument("--model")
    command.add_argument("--notes")
    command.set_defaults(func=project_update_cmd)

    command = sub.add_parser("executive-summary")
    command.add_argument("--output")
    command.set_defaults(func=executive_summary_cmd)

    command = sub.add_parser("activity-export")
    command.add_argument("--output")
    command.set_defaults(func=activity_export_cmd)

    command = sub.add_parser("milestone-create")
    command.add_argument("--project-id", required=True)
    command.add_argument("--title", required=True)
    command.add_argument(
        "--status",
        choices=[
            "Planned",
            "In Progress",
            "Blocked",
            "Completed",
            "Cancelled",
        ],
        default="Planned",
    )
    command.add_argument("--due-date")
    command.add_argument("--owner", default="")
    command.add_argument("--acceptance", default="")
    command.add_argument("--evidence", default="")
    command.add_argument("--notes", default="")
    command.set_defaults(func=milestone_create_cmd)

    command = sub.add_parser("decision-record")
    command.add_argument("--project-id", required=True)
    command.add_argument("--title", required=True)
    command.add_argument("--decision", required=True)
    command.add_argument(
        "--status",
        choices=[
            "Proposed",
            "Approved",
            "Superseded",
            "Reversed",
        ],
        default="Approved",
    )
    command.add_argument("--decision-date")
    command.add_argument("--context", default="")
    command.add_argument("--rationale", default="")
    command.add_argument("--alternatives", default="")
    command.add_argument("--impact", default="")
    command.add_argument("--approver", default="")
    command.add_argument("--evidence", default="")
    command.set_defaults(func=decision_record_cmd)

    command = sub.add_parser("gate-set")
    command.add_argument("--project-id", required=True)
    command.add_argument("--gate", required=True)
    command.add_argument(
        "--status",
        choices=[
            "Pending",
            "Conditional",
            "Approved",
            "Rejected",
        ],
        default="Pending",
    )
    command.add_argument("--reviewer", default="")
    command.add_argument("--conditions", default="")
    command.add_argument("--evidence", default="")
    command.add_argument("--decision-date")
    command.set_defaults(func=gate_set_cmd)

    command = sub.add_parser("governance-summary")
    command.add_argument("--project-id")
    command.set_defaults(func=governance_summary_cmd)

    command = sub.add_parser("project-readiness")
    command.add_argument("--project-id", required=True)
    command.add_argument("--output")
    command.set_defaults(func=project_readiness_cmd)

    command = sub.add_parser("evidence-manifest")
    command.add_argument("--project-id", required=True)
    command.add_argument("--output", required=True)
    command.set_defaults(func=evidence_manifest_cmd)

    command = sub.add_parser("evidence-package")
    command.add_argument("--project-id", required=True)
    command.add_argument("--output", required=True)
    command.add_argument(
        "--include-model-files",
        action="store_true",
    )
    command.set_defaults(func=evidence_package_cmd)

    command = sub.add_parser("project-export")
    command.add_argument("--project-id", required=True)
    command.add_argument("--output", required=True)
    command.set_defaults(func=project_export_cmd)

    command = sub.add_parser("project-import")
    command.add_argument("--input", required=True)
    command.add_argument("--code", required=True)
    command.add_argument("--name-suffix", default="(Imported)")
    command.set_defaults(func=project_import_cmd)

    command = sub.add_parser("audit-verify")
    command.add_argument("--output")
    command.set_defaults(func=audit_verify_cmd)

    command = sub.add_parser("data-pack-status")
    command.set_defaults(func=data_pack_status_cmd)

    command = sub.add_parser("data-pack-register")
    command.set_defaults(func=data_pack_register_cmd)

    command = sub.add_parser("data-pack-generate")
    command.set_defaults(func=data_pack_generate_cmd)

    command = sub.add_parser("double-ml-status")
    command.set_defaults(func=double_ml_status_cmd)
    command = sub.add_parser("five-x-ml-status")
    command.set_defaults(func=five_x_ml_status_cmd)

    command = sub.add_parser("coverage-status")
    command.set_defaults(func=coverage_status_cmd)

    command = sub.add_parser("coverage-generate")
    command.set_defaults(func=coverage_generate_cmd)

    command = sub.add_parser("demo-workspace-seed")
    command.add_argument(
        "--keep-existing-demo",
        action="store_true",
    )
    command.set_defaults(func=demo_workspace_seed_cmd)


    command = sub.add_parser("final-assurance")
    command.add_argument("--output")
    command.set_defaults(func=final_assurance_cmd)

    command = sub.add_parser("database-status")
    command.set_defaults(func=database_status_cmd)

    command = sub.add_parser("database-seed")
    command.set_defaults(func=database_seed_cmd)

    command = sub.add_parser("database-optimize")
    command.add_argument(
        "--vacuum",
        action="store_true",
    )
    command.set_defaults(func=database_optimize_cmd)

    command = sub.add_parser("intelligence-search")
    command.add_argument("query")
    command.add_argument(
        "--limit",
        type=int,
        default=25,
    )
    command.set_defaults(func=intelligence_search_cmd)

    command = sub.add_parser("knowledge-search")
    command.add_argument("query")
    command.add_argument(
        "--entity-type",
        default="all",
    )
    command.add_argument(
        "--status",
        default="all",
    )
    command.add_argument(
        "--limit",
        type=int,
        default=100,
    )
    command.set_defaults(func=knowledge_search_cmd)

    command = sub.add_parser("analytics-overview")
    command.add_argument(
        "--days",
        type=int,
        default=180,
    )
    command.set_defaults(func=analytics_overview_cmd)

    command = sub.add_parser("asset-search")
    command.add_argument("query")
    command.add_argument(
        "--asset-type",
        default="all",
    )
    command.add_argument(
        "--favourites-only",
        action="store_true",
    )
    command.add_argument(
        "--limit",
        type=int,
        default=100,
    )
    command.set_defaults(func=asset_search_cmd)

    command = sub.add_parser("internet-status")
    command.set_defaults(func=internet_status_cmd)

    command = sub.add_parser("internet-check")
    command.set_defaults(func=internet_check_cmd)

    command = sub.add_parser("internet-download-list")
    command.add_argument("--provider", default="all")
    command.add_argument("--limit", type=int, default=100)
    command.set_defaults(func=internet_download_list_cmd)

    command = sub.add_parser("pdb-fetch")
    command.add_argument("pdb_id")
    command.add_argument(
        "--format",
        choices=["cif", "pdb", "cif.gz", "pdb.gz"],
        default="cif",
    )
    command.add_argument("--metadata-only", action="store_true")
    command.set_defaults(func=pdb_fetch_cmd)

    command = sub.add_parser("pubchem-lookup")
    command.add_argument("name")
    command.set_defaults(func=pubchem_lookup_cmd)

    command = sub.add_parser("common-compound-search")
    command.add_argument("query")
    command.add_argument(
        "--name-type",
        choices=[
            "all",
            "curated_common_name",
            "registry_screening_name",
            "reference_registry_name",
        ],
        default="all",
    )
    command.add_argument("--limit", type=int, default=100)
    command.set_defaults(func=common_compound_search_cmd)

    command = sub.add_parser("public-url-download")
    command.add_argument("url")
    command.add_argument("--provider", default="Public HTTPS")
    command.add_argument("--filename")
    command.add_argument("--official-hosts-only", action="store_true")
    command.add_argument("--max-mb", type=int, default=100)
    command.set_defaults(func=public_url_download_cmd)
    command = sub.add_parser("research-platform", add_help=False)
    command.add_argument("platform_args", nargs=argparse.REMAINDER)
    command.set_defaults(func=research_platform_cmd)


    return parser


def main(
    argv: list[str] | None = None,
) -> int:
    effective_argv = list(argv) if argv is not None else sys.argv[1:]
    if effective_argv and effective_argv[0] == "research-platform":
        from biointel.discovery_platform.cli import main as platform_main

        return platform_main(effective_argv[1:])
    try:
        args = build_parser().parse_args(effective_argv)
        args.func(args)
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"error": str(exc)},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
