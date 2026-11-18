from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

from ..paths import education_paths
from .base import ResearchPlatformError
from .compute import INITIAL_WORKFLOW_LIBRARY, ResearchCompute

UPLOAD_TYPES = [
    "fa",
    "fasta",
    "fq",
    "fastq",
    "bam",
    "cram",
    "sam",
    "vcf",
    "bcf",
    "gff",
    "gff3",
    "gtf",
    "bed",
    "csv",
    "tsv",
    "xlsx",
    "json",
    "h5",
    "hdf5",
    "h5ad",
    "mtx",
    "pdb",
    "cif",
    "mmcif",
    "mzml",
    "dcm",
]


@st.cache_resource
def _research_compute(root_text: str) -> ResearchCompute:
    root = Path(root_text)
    database, media = education_paths(root)
    return ResearchCompute(database, media)


def _stage_uploads(service: ResearchCompute, uploads) -> tuple[tempfile.TemporaryDirectory, list[Path]]:
    temporary = tempfile.TemporaryDirectory(prefix="biointel-p34-", dir=service.storage_root)
    paths = []
    for index, upload in enumerate(uploads):
        safe_name = Path(upload.name).name
        if not safe_name or safe_name in {".", ".."}:
            temporary.cleanup()
            raise ResearchPlatformError("An uploaded filename is unsafe.")
        target = Path(temporary.name) / f"{index:05d}-{safe_name}"
        with target.open("wb") as handle:
            while block := upload.read(1024 * 1024):
                handle.write(block)
        paths.append(target)
    return temporary, paths


def render_research_compute(root: str | Path) -> None:
    service = _research_compute(str(Path(root).resolve()))
    st.title("BioIntel Research Compute")
    st.caption(
        "Local-first, controlled bioinformatics workflows with checksums, checkpoints, "
        "reproducibility bundles, and human review."
    )
    st.warning(
        "Research support only. Outputs are not diagnostic interpretations, clinical advice, "
        "verified novelty, or guaranteed scientific conclusions."
    )

    tenant_id = st.text_input("Institution or tenant ID", value="local-institution")
    user_id = st.text_input("Researcher ID", value="local-researcher")
    projects = service.projects(tenant_id)
    create_tab, data_tab, workflow_tab, run_tab = st.tabs(
        ["Project", "Dataset", "Workflow", "Run & results"]
    )

    with create_tab:
        with st.form("phase34_project"):
            title = st.text_input("Project title", value="Local genomics quality-control study")
            hypothesis = st.text_area(
                "Hypothesis",
                value="Sequence quality metrics are adequate for a downstream research workflow.",
            )
            create = st.form_submit_button("Create research project")
        if create:
            try:
                project = service.create_project(
                    tenant_id,
                    user_id,
                    tenant_id,
                    title=title,
                    hypothesis=hypothesis,
                    objectives=["Validate input identity", "Record reproducible quality metrics"],
                )
                st.session_state["phase34_project_id"] = project["project_id"]
                st.success(f"Project created: {project['project_id']}")
                st.rerun()
            except ResearchPlatformError as exc:
                st.error(str(exc))
        st.dataframe(projects, width="stretch", hide_index=True)

    project_options = [row["project_id"] for row in projects]
    selected_project = st.selectbox(
        "Active research project",
        project_options,
        index=0 if project_options else None,
        placeholder="Create a project first",
        key="phase34_selected_project",
    )

    with data_tab:
        uploads = st.file_uploader(
            "Research data files",
            type=UPLOAD_TYPES,
            accept_multiple_files=True,
            help="Files are inspected in bounded chunks, checksummed, then copied to local storage.",
        )
        dataset_title = st.text_input("Dataset title", value="Research input dataset")
        if st.button(
            "Register checksummed dataset",
            width="stretch",
            disabled=not bool(selected_project and uploads),
        ):
            temporary = None
            try:
                temporary, paths = _stage_uploads(service, uploads)
                dataset = service.register_dataset(
                    selected_project,
                    user_id,
                    title=dataset_title,
                    source_paths=paths,
                    source="Local Streamlit upload",
                    licence="User-declared research data",
                    consent_status="User-declared; governance review required where applicable",
                    access_level="private",
                )
                st.session_state["phase34_dataset_id"] = dataset["dataset_id"]
                st.success(
                    f"Dataset registered as {dataset['format']} with "
                    f"{len(dataset['files'])} verified file(s)."
                )
            except (OSError, ResearchPlatformError) as exc:
                st.error(str(exc))
            finally:
                if temporary is not None:
                    temporary.cleanup()
        if selected_project:
            st.dataframe(
                service.datasets(selected_project),
                width="stretch",
                hide_index=True,
            )

    executable_workflows = {
        key: value
        for key, value in INITIAL_WORKFLOW_LIBRARY.items()
        if value["status"] == "native_executable"
    }
    with workflow_tab:
        workflow_key = st.selectbox("Controlled workflow template", sorted(executable_workflows))
        definition = executable_workflows[workflow_key]
        st.json(definition)
        admin_acknowledgement = st.checkbox(
            "I am authorized to approve this workflow for this local institution",
            key="phase34_admin_ack",
        )
        if st.button(
            "Create and approve versioned workflow",
            width="stretch",
            disabled=not bool(selected_project and admin_acknowledgement),
        ):
            try:
                workflow = service.define_workflow(
                    selected_project,
                    user_id,
                    name=workflow_key,
                    domain=definition["domain"],
                    version="1.0.0",
                    steps=definition["steps"],
                    approve=True,
                    approver_role="institution_administrator",
                )
                st.session_state["phase34_workflow_id"] = workflow["workflow_id"]
                st.success(f"Approved workflow created: {workflow['workflow_id']}")
            except ResearchPlatformError as exc:
                st.error(str(exc))
        if selected_project:
            st.dataframe(
                service.workflows(selected_project),
                width="stretch",
                hide_index=True,
            )

    with run_tab:
        datasets = service.datasets(selected_project) if selected_project else []
        workflows = service.workflows(selected_project, approved_only=True) if selected_project else []
        dataset_id = st.selectbox(
            "Dataset",
            [row["dataset_id"] for row in datasets],
            index=0 if datasets else None,
            placeholder="Register a dataset",
        )
        workflow_id = st.selectbox(
            "Approved workflow",
            [row["workflow_id"] for row in workflows],
            index=0 if workflows else None,
            placeholder="Create an approved workflow",
        )
        seed = st.number_input("Reproducibility seed", value=42, step=1)
        if st.button(
            "Queue and execute locally",
            width="stretch",
            disabled=not bool(selected_project and dataset_id and workflow_id),
        ):
            try:
                submitted = service.submit_run(
                    selected_project,
                    workflow_id,
                    dataset_id,
                    user_id,
                    idempotency_key=f"ui:{selected_project}:{workflow_id}:{dataset_id}:{seed}",
                    seed=int(seed),
                )
                completed = service.execute_run(submitted["run_id"])
                st.session_state["phase34_run_id"] = completed["run_id"]
                st.success(f"Run state: {completed['state']}")
            except ResearchPlatformError as exc:
                st.error(str(exc))

        run_rows = service.runs(selected_project) if selected_project else []
        st.dataframe(run_rows, width="stretch", hide_index=True)
        run_ids = [row["run_id"] for row in run_rows]
        chosen_run = st.selectbox(
            "Result run",
            run_ids,
            index=0 if run_ids else None,
            placeholder="No run available",
        )
        if chosen_run:
            explorer = service.result_explorer(chosen_run)
            first, second, third = st.columns(3)
            first.metric("State", explorer["run"]["state"])
            second.metric(
                "Completed steps",
                f"{explorer['quality_metrics']['completed_steps']}/"
                f"{explorer['quality_metrics']['total_steps']}",
            )
            third.metric("Verified artifacts", explorer["quality_metrics"]["verified_artifacts"])
            st.dataframe(explorer["artifacts"], width="stretch", hide_index=True)
            with st.expander("Provenance, logs, and warnings"):
                st.json(
                    {
                        "steps": explorer["steps"],
                        "warnings": explorer["warnings"],
                        "claim_boundary": explorer["claim_boundary"],
                    }
                )
            st.download_button(
                "Export reproducibility bundle",
                data=service.export_run_bundle(chosen_run),
                file_name=f"biointel-compute-{chosen_run}.zip",
                mime="application/zip",
                width="stretch",
            )
            st.download_button(
                "Export result summary",
                data=json.dumps(explorer, indent=2, default=str),
                file_name=f"biointel-compute-{chosen_run}.json",
                mime="application/json",
                width="stretch",
            )
