from __future__ import annotations

import hashlib
import json
from pathlib import Path

import streamlit as st

from ..paths import education_paths
from .base import ResearchPlatformError
from .discovery import DiscoveryEcosystem


@st.cache_resource
def _discovery_ecosystem(root_text: str) -> DiscoveryEcosystem:
    root = Path(root_text)
    database, media = education_paths(root)
    return DiscoveryEcosystem(database, media)


def render_discovery_ecosystem(root: str | Path) -> None:
    service = _discovery_ecosystem(str(Path(root).resolve()))
    st.title("Scientific Discovery Agent Ecosystem")
    st.caption(
        "Controlled local agents organize registered evidence, draft hypotheses and plans, "
        "and preserve provenance for human review."
    )
    st.warning(
        "Research assistance only. This system does not autonomously discover, prove novelty, "
        "validate clinical use, diagnose, recommend treatment, or guarantee correctness."
    )
    tenant_id = st.text_input("Institution or tenant ID", value="local-institution")
    researcher_id = st.text_input("Researcher ID", value="local-researcher")

    project_tab, evidence_tab, agent_tab, review_tab = st.tabs(
        ["Workspace", "Evidence", "Scientific agent", "Graph & evaluation"]
    )
    projects = service.compute.projects(tenant_id)
    workspaces = service.workspaces(tenant_id)

    with project_tab:
        with st.form("phase35_project"):
            title = st.text_input("Research workspace title", value="Evidence-grounded study")
            question = st.text_area(
                "Research question",
                value="What evidence and testable mechanisms should be reviewed?",
            )
            create = st.form_submit_button("Create linked research and discovery workspace")
        if create:
            try:
                project = service.compute.create_project(
                    tenant_id,
                    researcher_id,
                    tenant_id,
                    title=title,
                    hypothesis="No hypothesis adopted until evidence and human review are complete.",
                    objectives=[question],
                )
                workspace = service.create_workspace(
                    project["project_id"],
                    researcher_id,
                    title=title,
                )
                st.session_state["phase35_workspace_id"] = workspace["workspace_id"]
                st.success(f"Workspace created: {workspace['workspace_id']}")
                st.rerun()
            except ResearchPlatformError as exc:
                st.error(str(exc))
        if projects and not workspaces:
            project_id = st.selectbox(
                "Existing Phase 34 research project",
                [row["project_id"] for row in projects],
            )
            if st.button("Bind selected project", width="stretch"):
                try:
                    service.create_workspace(project_id, researcher_id)
                    st.rerun()
                except ResearchPlatformError as exc:
                    st.error(str(exc))
        st.dataframe(workspaces, width="stretch", hide_index=True)

    workspace_id = st.selectbox(
        "Active discovery workspace",
        [row["workspace_id"] for row in workspaces],
        index=0 if workspaces else None,
        placeholder="Create or bind a research project",
        key="phase35_workspace",
    )
    sources = service.evidence_sources(workspace_id) if workspace_id else []

    with evidence_tab:
        with st.form("phase35_evidence"):
            evidence_title = st.text_input("Source title")
            citation = st.text_input("Citation or local source reference")
            abstract = st.text_area("Evidence abstract or summary")
            methodology = st.text_area("Methodology")
            limitations = st.text_area("Limitations")
            identifier = st.text_input("Persistent identifier (optional)")
            save_evidence = st.form_submit_button("Register local evidence record")
        if save_evidence:
            try:
                source = service.register_evidence(
                    workspace_id,
                    researcher_id,
                    source_type="registered_research_source",
                    title=evidence_title,
                    citation=citation,
                    abstract_text=abstract,
                    methodology_text=methodology,
                    limitations_text=limitations,
                    persistent_identifier=identifier,
                    retraction_status="not_checked",
                )
                st.success(f"Evidence registered: {source['source_id']}")
                st.rerun()
            except ResearchPlatformError as exc:
                st.error(str(exc))
        st.dataframe(
            [
                {
                    "source_id": row["source_id"],
                    "title": row["title"],
                    "citation": row["citation"],
                    "retraction_status": row["retraction_status"],
                    "existence_status": row["existence_status"],
                }
                for row in sources
            ],
            width="stretch",
            hide_index=True,
        )

    registry = service.agent_registry()
    with agent_tab:
        agent_key = st.selectbox(
            "Scientific agent",
            [row["agent_key"] for row in registry],
            format_func=lambda key: next(
                row["name"] for row in registry if row["agent_key"] == key
            ),
        )
        agent_question = st.text_area(
            "Task question or objective",
            value="Synthesize the registered evidence and state uncertainty.",
        )
        selected_evidence = st.multiselect(
            "Registered evidence",
            [row["source_id"] for row in sources],
            default=[row["source_id"] for row in sources[:5]],
        )
        if st.button(
            "Run controlled local draft",
            width="stretch",
            disabled=not bool(workspace_id),
        ):
            payload = {
                "question": agent_question,
                "topic": agent_question,
                "claims": [agent_question] if agent_key == "scientific_reviewer" else [],
            }
            digest = hashlib.sha256(
                json.dumps(
                    [workspace_id, agent_key, payload, selected_evidence],
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            try:
                task = service.create_agent_task(
                    workspace_id,
                    researcher_id,
                    agent_key=agent_key,
                    task_input=payload,
                    evidence_ids=selected_evidence,
                    idempotency_key=f"ui:{digest}",
                )
                if task["state"] == "planned":
                    task = service.execute_agent_task(task["task_id"])
                st.session_state["phase35_task_id"] = task["task_id"]
                st.success(f"Draft state: {task['state']}; human review remains required.")
            except ResearchPlatformError as exc:
                st.error(str(exc))
        task_id = st.session_state.get("phase35_task_id")
        if task_id:
            task = service.task(task_id)
            st.json(json.loads(task["output_json"]) if task["output_json"] != "{}" else task)

    with review_tab:
        if workspace_id:
            graph = service.claim_evidence_graph(workspace_id)
            first, second, third = st.columns(3)
            first.metric("Claims", graph["claim_count"])
            second.metric("Unsupported", graph["unsupported_claim_count"])
            third.metric("Graph edges", len(graph["edges"]))
            st.dataframe(graph["nodes"], width="stretch", hide_index=True)
            with st.expander("Evidence graph edges"):
                st.dataframe(graph["edges"], width="stretch", hide_index=True)
            if st.button("Run deterministic evaluation suite", width="stretch"):
                evaluation = service.run_evaluation_suite(workspace_id, researcher_id)
                st.session_state["phase35_evaluation"] = evaluation
            evaluation = st.session_state.get("phase35_evaluation")
            if evaluation:
                st.json(evaluation)
                st.download_button(
                    "Export evaluation result",
                    data=json.dumps(evaluation, indent=2),
                    file_name="biointel-scientific-agent-evaluation.json",
                    mime="application/json",
                    width="stretch",
                )
