from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Request
from pydantic import Field

from biointel.synthetic.core import (
    CLEAN_SCENARIOS,
    FAILURE_SCENARIOS,
    MODULE_SPECS,
    SYNTHETIC_WATERMARK,
    SyntheticGenerationConfig,
)
from biointel.synthetic.generators import SyntheticDatasetGenerator

from .advanced_analytics import (
    baseline_characteristics,
    build_cohort,
    imaging_quality_control,
    longitudinal_summary,
    missingness_analysis,
    propensity_support,
    random_effects_meta_analysis,
    spatial_neighborhood_analysis,
)
from .analysis import analysis_catalog
from .api_schemas import (
    CohortBody,
    LongitudinalBody,
    PropensityBody,
    SpatialBody,
    StrictModel,
    SyntheticGenerateBody,
)
from .api_shared import invoke, service_for
from .constants import (
    CANDIDATE_TYPES,
    EVIDENCE_TYPES,
    PROJECT_STAGES,
    WORKFLOW_TEMPLATES,
)
from .models import PlatformConflictError, ProjectCreate
from .reports import EXPORT_FORMATS, REPORT_SECTIONS

router = APIRouter()


class JobCreateBody(StrictModel):
    job_type: str = Field(min_length=1, max_length=200)
    project_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=50, ge=0, le=100)


class InstrumentCreateBody(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    instrument_type: str = Field(min_length=1, max_length=200)
    manufacturer: str = Field(default="", max_length=200)
    model: str = Field(default="", max_length=200)
    serial_number: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=300)
    status: str = "Available"
    owner: str = Field(default="", max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/catalog")
def catalog() -> dict[str, Any]:
    return {
        "project_stages": list(PROJECT_STAGES),
        "candidate_types": list(CANDIDATE_TYPES),
        "evidence_types": list(EVIDENCE_TYPES),
        "workflow_templates": {
            key: list(value) for key, value in WORKFLOW_TEMPLATES.items()
        },
        "analysis_modules": analysis_catalog(),
        "report_sections": list(REPORT_SECTIONS),
        "export_formats": list(EXPORT_FORMATS),
        "synthetic_notice": SYNTHETIC_WATERMARK,
    }


@router.get("/synthetic/catalog")
def synthetic_catalog() -> dict[str, Any]:
    return {
        "modules": MODULE_SPECS,
        "clean_scenarios": CLEAN_SCENARIOS,
        "failure_scenarios": FAILURE_SCENARIOS,
        "notice": SYNTHETIC_WATERMARK,
    }


@router.post("/synthetic/generate", status_code=201)
def generate_synthetic(
    request: Request,
    body: SyntheticGenerateBody,
) -> dict[str, Any]:
    service = service_for(request)

    def generate() -> dict[str, Any]:
        config = SyntheticGenerationConfig(
            module_id=body.module_id,
            scenario=body.scenario,
            size_preset=body.size_preset,
            seed=body.seed,
        )
        generated = SyntheticDatasetGenerator().generate(config)
        if body.project_id:
            project_item = service.get_project(body.project_id)
            if not project_item["is_synthetic"]:
                raise PlatformConflictError(
                    "Synthetic data cannot be added to a real project"
                )
        else:
            project_item = service.create_project(
                ProjectCreate(
                    title=body.project_title,
                    research_question=(
                        "Can this synthetic scenario exercise the configured workflow?"
                    ),
                    scientific_objective=(
                        "Training, demonstration, and deterministic failure testing"
                    ),
                    owner=service.actor,
                    data_origin="synthetic_demo_output",
                    is_synthetic=True,
                )
            )
        sample_count, feature_count = config.dimensions
        dataset = service.register_dataset(
            project_item["project_id"],
            name=f"{body.module_id} - {body.scenario}",
            description=SYNTHETIC_WATERMARK,
            assay_type=body.module_id,
            sample_count=sample_count,
            feature_count=feature_count,
            file_formats=("in-memory synthetic tables",),
            data_origin="synthetic_demo_output",
            is_synthetic=True,
            provenance={
                "origin": "synthetic_demo_output",
                "seed": body.seed,
                "scenario": body.scenario,
            },
        )
        manifest = service.synthetic.register_generated_dataset(
            project_id=project_item["project_id"],
            dataset_id=dataset["dataset_id"],
            generated=generated,
        )
        analysis_run = service.synthetic.run_generated_analysis(
            project_id=project_item["project_id"],
            dataset_id=dataset["dataset_id"],
            generated=generated,
        )
        previews = {}
        for name, table in generated.tables.items():
            if isinstance(table, pd.DataFrame):
                preview = table.head(20).astype(object)
                previews[name] = preview.where(pd.notna(preview), None).to_dict(
                    orient="records"
                )
            else:
                previews[name] = table
        return {
            "project": project_item,
            "dataset": dataset,
            "manifest": manifest,
            "production_analysis": analysis_run,
            "preview": previews,
            "expected_qc_findings": generated.expected_qc_findings,
            "expected_recommendations": generated.expected_recommendations,
            "notice": SYNTHETIC_WATERMARK,
        }

    return invoke(generate)


@router.get("/system/health")
def system_health(request: Request) -> dict[str, Any]:
    return invoke(service_for(request).health.snapshot)


@router.get("/system/dependencies")
def dependencies(request: Request, refresh: bool = False) -> dict[str, Any]:
    items = invoke(
        service_for(request).health.dependency_health,
        refresh=refresh,
    )
    return {"items": items, "count": len(items), "refreshed": refresh}


@router.get("/operations/queues")
def operation_queues(request: Request) -> dict[str, Any]:
    return invoke(service_for(request).lab_operations.queue_snapshot)


@router.post("/operations/jobs", status_code=201)
def create_job(request: Request, body: JobCreateBody) -> dict[str, Any]:
    return invoke(
        service_for(request).create_job,
        **body.model_dump(),
    )


@router.post("/operations/jobs/{job_id}/cancel")
def cancel_job(request: Request, job_id: str) -> dict[str, Any]:
    return invoke(service_for(request).cancel_job, job_id)


@router.post("/operations/jobs/{job_id}/retry")
def retry_job(request: Request, job_id: str) -> dict[str, Any]:
    return invoke(service_for(request).lab_operations.retry_job, job_id)


@router.post("/operations/instruments", status_code=201)
def register_instrument(
    request: Request,
    body: InstrumentCreateBody,
) -> dict[str, Any]:
    return invoke(
        service_for(request).lab_operations.register_instrument,
        **body.model_dump(),
    )


@router.post("/analytics/cohort")
def cohort_analytics(body: CohortBody) -> dict[str, Any]:
    frame = pd.DataFrame(body.rows)
    cohort = invoke(build_cohort, frame, body.criteria)
    output = {
        "cohort": cohort,
        "missingness": invoke(missingness_analysis, frame),
    }
    if body.group_column:
        output["baseline"] = invoke(
            baseline_characteristics,
            frame,
            group_column=body.group_column,
        )
    return output


@router.post("/analytics/propensity")
def propensity_analytics(body: PropensityBody) -> dict[str, Any]:
    return invoke(
        propensity_support,
        pd.DataFrame(body.rows),
        treatment_column=body.treatment_column,
        covariates=body.covariates,
        seed=body.seed,
    )


@router.post("/analytics/longitudinal")
def longitudinal_analytics(body: LongitudinalBody) -> dict[str, Any]:
    return invoke(
        longitudinal_summary,
        pd.DataFrame(body.rows),
        subject_column=body.subject_column,
        time_column=body.time_column,
        value_column=body.value_column,
        group_column=body.group_column,
    )


@router.post("/analytics/meta-analysis")
def meta_analytics(body: CohortBody) -> dict[str, Any]:
    return invoke(
        random_effects_meta_analysis,
        pd.DataFrame(body.rows),
    )


@router.post("/analytics/imaging-qc")
def imaging_analytics(body: CohortBody) -> dict[str, Any]:
    return invoke(imaging_quality_control, pd.DataFrame(body.rows))


@router.post("/analytics/spatial-neighborhood")
def spatial_analytics(body: SpatialBody) -> dict[str, Any]:
    return invoke(
        spatial_neighborhood_analysis,
        pd.DataFrame(body.rows),
        x_column=body.x_column,
        y_column=body.y_column,
        cell_id_column=body.cell_id_column,
        cell_type_column=body.cell_type_column,
        radius=body.radius,
        maximum_edges=body.maximum_edges,
    )
