from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import io
import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from biointel.bioinformatics import (
    NOTEBOOK_ENTRY_TYPES,
    RECOMMENDATION_STATUSES,
    REVIEW_ROLES,
    RecommendationStore,
    batch_sequence_profile,
    build_bioinformatics_manifest,
    build_recommendation_workspace,
    build_transcriptomics_design,
    export_audit_report,
    export_evidence_csv,
    export_evidence_package,
    export_parameter_configuration,
    export_recommendation_csv,
    export_recommendation_docx,
    export_recommendation_html,
    export_recommendation_json,
    export_recommendation_pdf,
    export_recommendation_xlsx,
    export_reproducibility_manifest,
    extended_fastq_qc,
    normalize_recommendation_module,
    protein_feature_track,
    vcf_quality_summary,
)
from biointel.jobs.local_queue import LocalJobQueue
from biointel.ui.components import metric_cards, smart_dataframe, smart_json
from biointel.ui.workflow import render_upload_preflight


CONTEXT_LABELS = {
    "sequence": "Batch sequence QC, circularity, ORFs, motifs and contamination patterns",
    "fastq": "Extended FASTQ cycle quality, duplication, adapter, GC and k-mer QC",
    "variant": "VCF quality, Ti/Tv, variant-type and chromosome summaries",
    "transcriptomics": "Editable sample-group, batch and covariate design matrix",
    "protein": "Residue-level hydropathy, low-complexity, signal and TM feature tracks",
    "phylogeny": "Alignment/phylogeny reproducibility plan and metadata checklist",
    "metagenomics": "Metagenomics study design, controls, databases and reporting checklist",
    "pangenome": "Pangenome graph inputs, path/index requirements and resource plan",
    "long_read": "Long-read assembly reproducibility, polishing and T2T validation checklist",
}


def _read_upload(upload: Any) -> tuple[bytes, str]:
    if upload is None:
        return b"", ""
    payload = bytes(upload.getbuffer())
    return payload, upload.name


def _generic_workflow_plan(context: str) -> pd.DataFrame:
    plans = {
        "phylogeny": [
            ("Input QC", "Validate alphabet, duplicate IDs and missing metadata", "Built-in QC"),
            ("Alignment", "Use MAFFT with pinned version and explicit algorithm", "MAFFT"),
            ("Trim", "Document trimming method and retained columns", "trimAl/BMGE optional"),
            ("Model selection", "Compare substitution models", "IQ-TREE ModelFinder"),
            ("Tree inference", "Record bootstrap/ultrafast bootstrap settings", "IQ-TREE/RAxML-NG"),
            ("Root/annotate", "Declare outgroup and metadata mapping", "Advanced Tree Viewer"),
        ],
        "metagenomics": [
            ("Controls", "Negative extraction, blank and mock community", "Required"),
            ("Read QC", "Adapter, quality, host-depletion and contamination review", "fastp/Bowtie2"),
            ("Taxonomy", "Pinned Kraken2/Bracken or MetaPhlAn database", "Reference lifecycle"),
            ("Function", "HUMAnN or validated alternative", "Pinned database"),
            ("Statistics", "Compositional, replicate-aware analysis", "ANCOM-BC/ALDEx2 adapter"),
            ("Reporting", "STORMS-style methods and provenance", "Report Builder"),
        ],
        "pangenome": [
            ("Assemblies", "Validate genome completeness and contamination", "QUAST/BUSCO"),
            ("Graph", "Build with minigraph/pggb-compatible plan", "External engine"),
            ("Index", "Create GFA/path indexes", "Graph toolkit"),
            ("Annotation", "Harmonise gene identifiers", "GFF/GTF mapping"),
            ("Variants", "Extract bubbles and sample paths", "Graph analysis"),
            ("Benchmark", "Compare reference and sample path recovery", "Validation center"),
        ],
        "long_read": [
            ("Read QC", "Length, yield, quality and contamination", "NanoPlot/FastQC adapter"),
            ("Assembly", "Platform/genome-aware assembler", "Flye/hifiasm/Canu"),
            ("Polish", "Long-read and optional short-read polishing", "Racon/Medaka/Pilon"),
            ("Purge", "Detect duplicated haplotigs", "purge_dups"),
            ("Completeness", "BUSCO and k-mer completeness", "BUSCO/Merqury"),
            ("T2T review", "Telomeres, centromeres and unresolved graph nodes", "Manual review"),
        ],
    }
    rows = plans.get(context, [])
    return pd.DataFrame(rows, columns=["stage", "requirement", "recommended_engine"])


def render_bioinformatics_upgrade_panel(context: str, *, expanded: bool = False) -> None:
    label = CONTEXT_LABELS.get(context, "Bioinformatics upgrade tools")
    with st.expander(f"Step 112 bioinformatics upgrade Â· {label}", expanded=expanded):
        if context == "sequence":
            upload = st.file_uploader("Batch FASTA/FA/FNA/FAA/TXT", type=["fasta", "fa", "fna", "faa", "txt"], key="step112_seq_batch")
            render_upload_preflight(upload, key="step112_seq_batch_preflight", allowed_extensions=["fasta", "fa", "fna", "faa", "txt"], soft_limit_mb=20, hard_limit_mb=100)
            motifs = st.text_input("Motifs (comma separated)", value="ATG,TATAAA")
            circular = st.toggle("Check circular terminal overlap", value=False, key="step112_seq_circular")
            if st.button("Run batch sequence upgrade QC", key="step112_seq_run", width="stretch", disabled=upload is None):
                payload, name = _read_upload(upload)
                frame = batch_sequence_profile(payload.decode("utf-8", errors="replace"), motifs=motifs.split(","), circular=circular)
                st.session_state["step112_seq_result"] = frame
                st.session_state["step112_seq_manifest"] = build_bioinformatics_manifest(module="sequence", input_name=name, input_bytes=payload, parameters={"motifs": motifs, "circular": circular}, outputs={"profile": len(frame)})
            frame = st.session_state.get("step112_seq_result", pd.DataFrame())
            if not frame.empty:
                metric_cards([("Records", len(frame), None), ("Invalid alphabets", int((~frame["valid_alphabet"]).sum()), None), ("Contaminant-pattern hits", int(frame["contaminant_pattern_count"].sum()), None), ("Circular candidates", int(frame["circular_candidate"].sum()), None)])
                st.plotly_chart(px.scatter(frame, x="length", y="gc_fraction", color="sequence_type", size="orf_count_forward", hover_name="record_id", title="Batch sequence landscape"), width="stretch")
                smart_dataframe(frame, height=400, key="step112_seq_profile")
                st.download_button("Download batch profile", frame.to_csv(index=False).encode(), "batch_sequence_profile.csv", "text/csv", width="stretch")
        elif context == "fastq":
            upload = st.file_uploader("FASTQ (plain text for interactive upgrade QC)", type=["fastq", "fq", "txt"], key="step112_fastq_upgrade")
            render_upload_preflight(upload, key="step112_fastq_upgrade_preflight", allowed_extensions=["fastq", "fq", "txt"], soft_limit_mb=50, hard_limit_mb=100)
            c1, c2 = st.columns(2)
            max_reads = c1.number_input("Maximum reads", 100, 500_000, 50_000, 1000, key="step112_fastq_max")
            adapter = c2.text_input("Adapter pattern", value="AGATCGGAAGAG", key="step112_fastq_adapter")
            if st.button("Run extended FASTQ QC", key="step112_fastq_run", width="stretch", disabled=upload is None):
                payload, _ = _read_upload(upload)
                st.session_state["step112_fastq_result"] = extended_fastq_qc(payload.decode("utf-8", errors="replace"), maximum_reads=int(max_reads), adapter_patterns=[adapter])
            result = st.session_state.get("step112_fastq_result")
            if result:
                summary = result["summary"]
                metric_cards([("Reads", f"{summary['reads_profiled']:,}", None), ("Mean Q", f"{summary['mean_quality']:.1f}", None), ("Duplicates", f"{summary['duplicate_read_fraction']:.1%}", None), ("Adapter reads", f"{summary['adapter_read_fraction']:.1%}", None)])
                st.plotly_chart(px.line(result["per_cycle"], x="cycle", y="mean_quality", title="Per-cycle mean quality"), width="stretch")
                smart_dataframe(result["top_kmers"], height=280, key="step112_fastq_kmers")
        elif context == "variant":
            upload = st.file_uploader("VCF", type=["vcf", "txt"], key="step112_vcf_upgrade")
            render_upload_preflight(upload, key="step112_vcf_upgrade_preflight", allowed_extensions=["vcf", "txt"], soft_limit_mb=50, hard_limit_mb=100)
            if st.button("Run VCF quality upgrade", key="step112_vcf_run", width="stretch", disabled=upload is None):
                payload, _ = _read_upload(upload)
                st.session_state["step112_vcf_result"] = vcf_quality_summary(payload.decode("utf-8", errors="replace"))
            result = st.session_state.get("step112_vcf_result")
            if result:
                summary = result["summary"]
                metric_cards([("Variants", f"{summary['variants_loaded']:,}", None), ("Samples", summary["samples"], None), ("PASS", f"{summary['pass_fraction']:.1%}", None), ("Ti/Tv", "â€”" if summary["ti_tv_ratio"] is None else f"{summary['ti_tv_ratio']:.2f}", None)])
                c1, c2 = st.columns(2)
                c1.plotly_chart(px.bar(result["variant_types"], x="variant_type", y="count", title="Variant types"), width="stretch")
                c2.plotly_chart(px.bar(result["chromosome_summary"], x="chrom", y="variants", title="Variants by chromosome/contig"), width="stretch")
                smart_dataframe(result["variants"].head(5000), height=380, key="step112_vcf_table")
        elif context == "transcriptomics":
            upload = st.file_uploader("Sample metadata CSV/TSV", type=["csv", "tsv", "txt"], key="step112_tx_metadata")
            render_upload_preflight(upload, key="step112_tx_metadata_preflight", allowed_extensions=["csv", "tsv", "txt"], soft_limit_mb=10, hard_limit_mb=50)
            if upload is not None:
                payload, _ = _read_upload(upload)
                sep = "\t" if upload.name.lower().endswith((".tsv", ".txt")) else ","
                metadata = pd.read_csv(io.BytesIO(payload), sep=sep)
                columns = list(metadata.columns)
                c1, c2 = st.columns(2)
                sample_col = c1.selectbox("Sample ID column", columns, key="step112_tx_sample")
                group_col = c2.selectbox("Group column", columns, index=min(1, len(columns)-1), key="step112_tx_group")
                groups = sorted(metadata[group_col].astype(str).unique())
                reference = st.selectbox("Reference group", groups, key="step112_tx_reference")
                batch_options = ["None", *columns]
                batch = st.selectbox("Batch column", batch_options, key="step112_tx_batch")
                covariates = st.multiselect("Additional covariates", [column for column in columns if column not in {sample_col, group_col, batch}], key="step112_tx_covariates")
                if st.button("Build design matrix", key="step112_tx_run", width="stretch"):
                    try:
                        st.session_state["step112_tx_result"] = build_transcriptomics_design(metadata, sample_column=sample_col, group_column=group_col, reference_group=reference, batch_column=None if batch == "None" else batch, covariates=covariates)
                    except Exception as exc:
                        st.error(str(exc))
            result = st.session_state.get("step112_tx_result")
            if result:
                st.code(result["formula"], language="r")
                for warning in result["warnings"]:
                    st.warning(warning)
                smart_dataframe(result["balance"], height=260, key="step112_tx_balance")
                smart_dataframe(result["design_matrix"], height=380, key="step112_tx_design")
        elif context == "protein":
            sequence = st.text_area("Protein sequence", height=160, value="MKWVTFISLLFLFSSAYSRGVFRRDTHKSEIAHRFKDLGE")
            window = st.slider("Hydropathy window", 5, 35, 19, 2)
            if st.button("Build residue feature track", key="step112_protein_run", width="stretch"):
                try:
                    st.session_state["step112_protein_track"] = protein_feature_track(sequence, window=window)
                except Exception as exc:
                    st.error(str(exc))
            track = st.session_state.get("step112_protein_track", pd.DataFrame())
            if not track.empty:
                st.plotly_chart(px.line(track, x="position", y="hydropathy", title="Residue hydropathy profile"), width="stretch")
                smart_dataframe(track, height=360, key="step112_protein_track_table")
        else:
            plan = _generic_workflow_plan(context)
            if plan.empty:
                st.info("No upgrade plan is defined for this context.")
            else:
                smart_dataframe(plan, height=360, key=f"step112_{context}_plan")
                payload = {"context": context, "stages": plan.to_dict(orient="records"), "boundary": "Generated plans require installed specialist engines, pinned databases and organism/study-specific review."}
                smart_json(payload, title="Reproducible workflow plan", download_name=f"{context}_workflow_plan.json", key=f"step112_{context}_plan_json")
        _render_recommendation_decision_workspace(context)




def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _project_version() -> str:
    version_file = _project_root() / "VERSION"
    return version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unknown"


def _recommendation_store() -> RecommendationStore:
    return RecommendationStore(_projectruntime_database_path(_root(), "bioinformatics_recommendations.sqlite3"))


def _context_result_payload(context: str) -> tuple[dict[str, Any], bool]:
    key_map = {
        "sequence": "step112_seq_result",
        "fastq": "step112_fastq_result",
        "variant": "step112_vcf_result",
        "transcriptomics": "step112_tx_result",
        "protein": "step112_protein_track",
    }
    key = key_map.get(context)
    result = st.session_state.get(key) if key else None
    if isinstance(result, pd.DataFrame):
        return {"analysis_table": result}, not result.empty
    if isinstance(result, dict):
        return result, bool(result)
    if result is not None:
        return {"analysis_result": result}, True
    plan = _generic_workflow_plan(context)
    if not plan.empty:
        return {"workflow_plan": plan, "context": context}, True
    return {}, False


def _render_metric_rows(record: dict[str, Any]) -> None:
    metric_cards([
        ("Priority", f"{record['priority']} ({record['priority_score']:.1f})", None),
        ("Confidence", "Not calculated" if record.get("confidence_score") is None else f"{record['confidence_score']:.1f}%", None),
        ("Evidence", record["evidence_grade"], None),
        ("Status", record["status"], None),
    ])


def _render_review_controls(record: dict[str, Any], store: RecommendationStore, key_prefix: str) -> dict[str, Any]:
    c1, c2 = st.columns([1, 2])
    current = record.get("status", "Generated")
    index = RECOMMENDATION_STATUSES.index(current) if current in RECOMMENDATION_STATUSES else 1
    status = c1.selectbox("Status", RECOMMENDATION_STATUSES, index=index, key=f"{key_prefix}_status")
    note = c2.text_input("Review note", value=record.get("decision_reason", ""), key=f"{key_prefix}_note")
    if st.button("Save review status", key=f"{key_prefix}_save_status", width="stretch"):
        record = store.update_status(record["recommendation_id"], status, actor="streamlit-user", note=note, decision_reason=note)
        st.session_state[f"{key_prefix}_record"] = record
        st.success("Recommendation status saved.")
    return record


def _render_recommendation_tabs(record: dict[str, Any], store: RecommendationStore, key_prefix: str) -> None:
    tabs = st.tabs(["Overview", "Evidence", "Explainability", "Alternatives", "Risks", "Validation", "Action Plan", "Comparison", "History", "Export"])
    with tabs[0]:
        _render_metric_rows(record)
        st.markdown(f"**Recommendation:** {record['title']}")
        st.write(record["scientific_summary"])
        st.markdown(f"**Next action:** {record['recommended_next_action']}")
        st.warning(record["research_use_disclaimer"])
        record = _render_review_controls(record, store, key_prefix)
        smart_dataframe([
            {"field": "Recommendation type", "value": record["recommendation_type"]},
            {"field": "Urgency", "value": record["urgency"]},
            {"field": "Research impact", "value": record["research_impact"]},
            {"field": "Validation status", "value": record["validation_status"]},
            {"field": "Available inputs", "value": ", ".join(record.get("available_inputs", [])) or "None"},
            {"field": "Missing inputs", "value": ", ".join(record.get("missing_inputs", [])) or "None"},
            {"field": "Optional inputs", "value": ", ".join(record.get("optional_inputs", [])) or "None"},
        ], height=330, key=f"{key_prefix}_overview")
    with tabs[1]:
        smart_dataframe(record.get("quality_checks", []), height=300, key=f"{key_prefix}_qc")
        smart_dataframe(record.get("evidence", []) + record.get("contradictory_evidence", []), height=380, key=f"{key_prefix}_evidence")
        if record.get("evidence_limitations"):
            smart_dataframe([{"limitation": item} for item in record["evidence_limitations"]], height=260, key=f"{key_prefix}_limitations")
    with tabs[2]:
        smart_dataframe(record.get("explainability", []), height=420, key=f"{key_prefix}_explainability")
        st.code(record.get("priority_formula", ""), language="text")
        smart_dataframe(record.get("confidence_components", []), height=320, key=f"{key_prefix}_confidence")
    with tabs[3]:
        smart_dataframe(record.get("alternatives", []), height=520, key=f"{key_prefix}_alternatives")
    with tabs[4]:
        smart_dataframe(record.get("risks", []), height=450, key=f"{key_prefix}_risks")
    with tabs[5]:
        smart_dataframe(record.get("validation_plan", []), height=470, key=f"{key_prefix}_validation")
    with tabs[6]:
        smart_dataframe(record.get("action_plan", []), height=520, key=f"{key_prefix}_actions")
    with tabs[7]:
        smart_dataframe(record.get("comparison", []), height=300, key=f"{key_prefix}_comparison")
    with tabs[8]:
        history = store.history_frame(project_id=record["project_id"], module=record["module"])
        smart_dataframe(history, height=420, key=f"{key_prefix}_history")
    with tabs[9]:
        rid = record["recommendation_id"]
        col1, col2, col3 = st.columns(3)
        col1.download_button("JSON", export_recommendation_json(record), f"{rid}.json", "application/json", key=f"{key_prefix}_json", width="stretch")
        col2.download_button("CSV", export_recommendation_csv([record]), f"{rid}.csv", "text/csv", key=f"{key_prefix}_csv", width="stretch")
        col3.download_button("Evidence CSV", export_evidence_csv(record), f"{rid}_evidence.csv", "text/csv", key=f"{key_prefix}_evidence_csv", width="stretch")
        col4, col5, col6 = st.columns(3)
        col4.download_button("HTML", export_recommendation_html(record), f"{rid}.html", "text/html", key=f"{key_prefix}_html", width="stretch")
        col5.download_button("PDF", export_recommendation_pdf(record), f"{rid}.pdf", "application/pdf", key=f"{key_prefix}_pdf", width="stretch")
        col6.download_button("Manifest", export_reproducibility_manifest(record), f"{rid}_manifest.json", "application/json", key=f"{key_prefix}_manifest", width="stretch")
        smart_json(record["reproducibility"], title="Reproducibility manifest", download_name=f"{rid}_manifest.json", key=f"{key_prefix}_manifest_json")


def _render_recommendation_decision_workspace(context: str) -> None:
    st.divider()
    st.subheader("Research Decision Workspace")
    store = _recommendation_store()
    canonical = normalize_recommendation_module(context)
    payload, has_result = _context_result_payload(context)
    key_prefix = f"step218_{context}"
    c1, c2 = st.columns(2)
    project_id = c1.text_input("Project ID", value="BIOINTEL-DEMO", key=f"{key_prefix}_project")
    objective = c2.text_input("Research objective", value="Transparent research prioritization", key=f"{key_prefix}_objective")
    previous = None
    history = store.list(project_id=project_id, module=canonical, limit=1)
    if history:
        previous = history[0]
    if st.button("Generate recommendation dossier", key=f"{key_prefix}_generate", width="stretch"):
        record = build_recommendation_workspace(
            context,
            payload,
            project_id=project_id,
            parameters={"research_objective": objective, "ui_context": context},
            previous=previous,
            software_version=_project_version(),
            user="streamlit-user",
        )
        store.save(record)
        st.session_state[f"{key_prefix}_record"] = record
        st.success("Recommendation dossier generated and persisted.")
    record = st.session_state.get(f"{key_prefix}_record")
    if record is None and has_result:
        record = build_recommendation_workspace(
            context,
            payload,
            project_id=project_id,
            parameters={"research_objective": objective, "ui_context": context},
            previous=previous,
            software_version=_project_version(),
            user="streamlit-user",
        )
    if record is None:
        st.info("No recommendation dossier is available for this workspace.")
        return
    _render_recommendation_tabs(record, store, key_prefix)


