from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.genomics.assembly import assembly_metrics, metrics_dict
from biointel.genomics.fastq import (
    DEFAULT_ADAPTERS,
    decode_fastq_bytes,
    detect_phred_offset,
    fastq_qc,
    fastq_text,
    paired_end_qc,
    parse_fastq,
    read_level_metrics,
    trim_fastq_advanced,
    trim_paired_fastq,
)
from biointel.sequence.parser import parse_sequences_text
from biointel.ui.components import (
    metric_cards,
    result_summary,
    scientific_boundary_banner,
    smart_dataframe,
)
from biointel.ui.performance import read_text_cached
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.workflow import (  # noqa: E402
    analysis_run,
    read_uploaded_text,
    render_methodology,
    render_upload_preflight,
)

DEMO = ROOT / "data" / "bioinformatics_demo"
st.set_page_config(page_title="FASTQ & Genome QC · BioIntel AI", page_icon="🧬", layout="wide")
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("fastq_qc", key_prefix="step116_56_FASTQ_Genomics_QC_fastq_qc_1", expanded=False)
hero(
    "FASTQ & Genome Quality Control",
    "Analyse plain or gzip-compressed single/paired FASTQ reads, validate pair synchronization, inspect per-cycle quality, and export synchronized trimmed reads.",
    eyebrow="Quality-Hardened · Production Genomics Workbench",
    chips=[
        "FASTQ.gz",
        "Paired-end QC",
        "Per-cycle diagnostics",
        "Synchronized trimming",
        "N50/L50",
    ],
)
scientific_boundary_banner(source_kind="demo_reference", release_eligible=False)

render_methodology(
    method="Streaming-style FASTQ quality summaries, adapter/quality trimming and assembly contiguity statistics.",
    assumptions=[
        "Phred encoding and read layout match the selected settings.",
        "Sampled reads represent the complete library.",
    ],
    limitations=[
        "Interactive QC is not a replacement for FastQC/MultiQC or validated production trimming.",
        "Very large libraries should use the batch workflow.",
    ],
    validation=[
        "Inspect per-cycle quality and adapter profiles in an external validated tool.",
        "Retain original FASTQ checksums and paired-end synchronization evidence.",
    ],
)

fastq_tab, assembly_tab = st.tabs(["FASTQ quality", "Assembly metrics"])


def _demo_bytes(filename: str) -> bytes:
    return (DEMO / filename).read_bytes()


with fastq_tab:
    with st.form("fastq_analysis_form"):
        source_col, option_col = st.columns([1.3, 1])
        with source_col:
            mode = st.radio("Library layout", ["Single-end", "Paired-end"], horizontal=True)
            r1_upload = st.file_uploader(
                "FASTQ / FASTQ.gz" if mode == "Single-end" else "R1 FASTQ / FASTQ.gz",
                type=["fastq", "fq", "gz"],
                key="step33_fastq_r1",
            )
            r1_upload_profile = render_upload_preflight(
                r1_upload,
                key="fastq_r1",
                allowed_extensions=["fastq", "fq", "gz"],
                soft_limit_mb=50,
                hard_limit_mb=500,
            )
            r2_upload = None
            if mode == "Paired-end":
                r2_upload = st.file_uploader(
                    "R2 FASTQ / FASTQ.gz",
                    type=["fastq", "fq", "gz"],
                    key="step33_fastq_r2",
                )
                r2_upload_profile = render_upload_preflight(
                    r2_upload,
                    key="fastq_r2",
                    allowed_extensions=["fastq", "fq", "gz"],
                    soft_limit_mb=50,
                    hard_limit_mb=500,
                )
            use_demo = st.toggle(
                "Use built-in reference reads when no upload is provided", value=True
            )
        with option_col:
            preview_limit = st.number_input(
                "Maximum reads per mate", 1_000, 1_000_000, 50_000, 1_000
            )
            adapter_name = st.selectbox("Adapter profile", ["Custom", *DEFAULT_ADAPTERS])
            adapter_default = (
                "AGATCGGAAGAG" if adapter_name == "Custom" else DEFAULT_ADAPTERS[adapter_name]
            )
            adapter = st.text_input("Adapter sequence", adapter_default).strip().upper()
            analyse = st.form_submit_button("Analyse reads", type="primary", width="stretch")

    if analyse or "step33_fastq_result" not in st.session_state:
        try:
            if r1_upload is not None:
                r1_text = decode_fastq_bytes(r1_upload.getvalue(), filename=r1_upload.name)
            elif use_demo:
                r1_text = decode_fastq_bytes(
                    _demo_bytes(
                        "demo_reads_R1.fastq" if mode == "Paired-end" else "demo_reads.fastq"
                    ),
                    filename="demo.fastq",
                )
            else:
                raise ValueError("Upload FASTQ data or enable the built-in reference dataset.")
            r1_records = parse_fastq(r1_text, max_records=int(preview_limit))
            encoding = detect_phred_offset(r1_records)
            if mode == "Paired-end":
                if r2_upload is not None:
                    r2_text = decode_fastq_bytes(r2_upload.getvalue(), filename=r2_upload.name)
                elif use_demo:
                    r2_text = decode_fastq_bytes(
                        _demo_bytes("demo_reads_R2.fastq"), filename="demo_R2.fastq"
                    )
                else:
                    raise ValueError("Paired-end mode requires an R2 FASTQ file.")
                r2_records = parse_fastq(r2_text, max_records=int(preview_limit))
                paired = paired_end_qc(r1_records, r2_records)
                st.session_state["step33_fastq_result"] = {
                    "mode": mode,
                    "r1_text": r1_text,
                    "r2_text": r2_text,
                    "r1_qc": asdict(paired.r1),
                    "r2_qc": asdict(paired.r2),
                    "pair_qc": asdict(paired),
                    "adapter": adapter,
                    "limit": int(preview_limit),
                    "encoding": encoding,
                }
            else:
                qc = fastq_qc(r1_records)
                st.session_state["step33_fastq_result"] = {
                    "mode": mode,
                    "r1_text": r1_text,
                    "r1_qc": asdict(qc),
                    "adapter": adapter,
                    "limit": int(preview_limit),
                    "encoding": encoding,
                }
        except (OSError, ValueError) as exc:
            st.error(str(exc))

    payload = st.session_state.get("step33_fastq_result")
    if payload:
        r1_qc = payload["r1_qc"]
        pair_payload = payload.get("pair_qc")
        metric_cards(
            [
                (
                    "Reads / pairs",
                    f"{pair_payload['pairs']:,}" if pair_payload else f"{r1_qc['reads']:,}",
                    "Analysed library records",
                ),
                ("R1 bases", f"{r1_qc['bases']:,}", "Total R1 analysed bases"),
                ("R1 mean quality", f"Q{r1_qc['mean_quality']:.1f}", "Mean Phred score"),
                ("R1 Q30", f"{r1_qc['q30_percent']:.1f}%", "Bases with Phred ≥ 30"),
                ("R1 GC", f"{r1_qc['mean_gc_percent']:.1f}%", "Mean GC percentage"),
                (
                    "Pair sync",
                    f"{pair_payload['synchronized_pairs']:,}" if pair_payload else "N/A",
                    "Matching paired identifiers",
                ),
            ]
        )

        r1_cycle = pd.DataFrame(
            {
                "Cycle": range(1, len(r1_qc["per_cycle_quality"]) + 1),
                "Mean quality": r1_qc["per_cycle_quality"],
                "GC percent": r1_qc["per_cycle_gc_percent"],
                "Mate": "R1",
            }
        )
        cycles = [r1_cycle]
        if payload.get("r2_qc"):
            r2_qc = payload["r2_qc"]
            cycles.append(
                pd.DataFrame(
                    {
                        "Cycle": range(1, len(r2_qc["per_cycle_quality"]) + 1),
                        "Mean quality": r2_qc["per_cycle_quality"],
                        "GC percent": r2_qc["per_cycle_gc_percent"],
                        "Mate": "R2",
                    }
                )
            )
        cycle_frame = pd.concat(cycles, ignore_index=True)
        charts = st.columns(2)
        charts[0].plotly_chart(
            px.line(
                cycle_frame,
                x="Cycle",
                y="Mean quality",
                color="Mate",
                title="Per-cycle mean quality",
            ),
            width="stretch",
        )
        charts[1].plotly_chart(
            px.line(
                cycle_frame,
                x="Cycle",
                y="GC percent",
                color="Mate",
                title="Per-cycle GC percentage",
            ),
            width="stretch",
        )

        quality_hist = pd.DataFrame(
            [
                {"Phred": int(score), "Bases": count}
                for score, count in r1_qc["quality_histogram"].items()
            ]
        )
        length_hist = pd.DataFrame(
            [
                {"Length": int(length), "Reads": count}
                for length, count in r1_qc["length_histogram"].items()
            ]
        )
        charts = st.columns(2)
        charts[0].plotly_chart(
            px.bar(quality_hist, x="Phred", y="Bases", title="R1 base-quality distribution"),
            width="stretch",
        )
        charts[1].plotly_chart(
            px.bar(length_hist, x="Length", y="Reads", title="R1 read-length distribution"),
            width="stretch",
        )

        adapters = pd.DataFrame(
            [
                {"Adapter": name, "Reads detected": count}
                for name, count in r1_qc["adapter_hits"].items()
            ]
        )
        overrepresented = pd.DataFrame(r1_qc["overrepresented_sequences"])
        detail_tabs = st.tabs(
            [
                "Adapter detection",
                "Overrepresented sequences",
                "Read-level diagnostics",
                "Pair validation",
                "QC report",
            ]
        )
        with detail_tabs[0]:
            smart_dataframe(adapters, height=250)
        with detail_tabs[1]:
            if overrepresented.empty:
                st.success("No duplicated sequence exceeded the reporting threshold.")
            else:
                smart_dataframe(overrepresented, height=350)
        with detail_tabs[2]:
            records_for_metrics = parse_fastq(payload["r1_text"], max_records=int(payload["limit"]))
            read_metrics = read_level_metrics(
                records_for_metrics, offset=int(payload.get("encoding", {}).get("offset", 33))
            )
            smart_dataframe(read_metrics, height=420)
            st.plotly_chart(
                px.scatter(
                    read_metrics,
                    x="gc_percent",
                    y="mean_quality",
                    color="expected_errors",
                    hover_name="read_id",
                    title="Read-level GC, quality and expected errors",
                ),
                width="stretch",
            )
            st.download_button(
                "Download read-level QC",
                read_metrics.to_csv(index=False),
                "fastq_read_level_qc.csv",
                "text/csv",
                width="stretch",
            )
        with detail_tabs[3]:
            if pair_payload:
                result_summary(
                    {
                        key: pair_payload[key]
                        for key in [
                            "pairs",
                            "synchronized_pairs",
                            "mismatched_identifiers",
                            "orphan_r1",
                            "orphan_r2",
                        ]
                    },
                    title="Paired-end synchronization",
                )
                for warning in pair_payload.get("warnings", []):
                    st.warning(warning)
            else:
                st.info("Select Paired-end mode to validate R1/R2 identifiers and orphan reads.")
        with detail_tabs[4]:
            result_summary(
                {
                    key: value
                    for key, value in r1_qc.items()
                    if key
                    not in {
                        "per_cycle_quality",
                        "per_cycle_gc_percent",
                        "quality_histogram",
                        "length_histogram",
                        "overrepresented_sequences",
                    }
                },
                title="R1 QC summary",
            )
            result_summary(payload.get("encoding", {}), title="Quality encoding audit")

        with st.form("fastq_trim_form"):
            section_title("Synchronized quality and adapter trimming", "✂️")
            cols = st.columns(5)
            minimum_quality = cols[0].slider("Minimum terminal Phred", 0, 40, 20)
            minimum_length = cols[1].number_input("Minimum retained length", 10, 500, 30)
            trim_adapter = cols[2].toggle("Trim selected adapter", value=True)
            window_quality = cols[3].slider("4-base window quality", 0, 40, 20)
            max_errors = cols[4].number_input("Maximum expected errors", 0.1, 20.0, 2.0, 0.1)
            poly_x = st.toggle("Trim terminal poly-X/poly-G runs", value=True)
            trim_now = st.form_submit_button("Run trimming", type="primary", width="stretch")
        if trim_now:
            try:
                r1_records = parse_fastq(payload["r1_text"], max_records=int(payload["limit"]))
                settings = {
                    "adapter": payload["adapter"] if trim_adapter else None,
                    "minimum_quality": int(minimum_quality),
                    "minimum_length": int(minimum_length),
                }
                with analysis_run("Trimming and validating FASTQ reads"):
                    if payload["mode"] == "Paired-end":
                        r2_records = parse_fastq(
                            payload["r2_text"], max_records=int(payload["limit"])
                        )
                        trimmed_r1, trimmed_r2, summary = trim_paired_fastq(
                            r1_records, r2_records, **settings
                        )
                        downloads = st.columns(2)
                        downloads[0].download_button(
                            "Download trimmed R1",
                            fastq_text(trimmed_r1),
                            "trimmed_R1.fastq",
                            "text/plain",
                            width="stretch",
                        )
                        downloads[1].download_button(
                            "Download trimmed R2",
                            fastq_text(trimmed_r2),
                            "trimmed_R2.fastq",
                            "text/plain",
                            width="stretch",
                        )
                    else:
                        trimmed_r1, summary, trim_audit = trim_fastq_advanced(
                            r1_records,
                            adapter=payload["adapter"] if trim_adapter else None,
                            minimum_quality=int(minimum_quality),
                            minimum_length=int(minimum_length),
                            minimum_mean_window_quality=float(window_quality),
                            maximum_expected_errors=float(max_errors),
                            trim_poly_x=bool(poly_x),
                            offset=int(payload.get("encoding", {}).get("offset", 33)),
                        )
                        st.download_button(
                            "Download trimmed FASTQ",
                            fastq_text(trimmed_r1),
                            "trimmed.fastq",
                            "text/plain",
                            width="stretch",
                        )
                        st.download_button(
                            "Download trimming audit",
                            pd.DataFrame(trim_audit).to_csv(index=False),
                            "fastq_trimming_audit.csv",
                            "text/csv",
                            width="stretch",
                        )
                result_summary(summary, title="Trimming summary")
                st.toast("FASTQ trimming completed", icon="✅")
            except ValueError as exc:
                st.error(str(exc))

with assembly_tab:
    with st.form("assembly_qc_form"):
        upload = st.file_uploader(
            "Assembly FASTA", type=["fa", "fasta", "fna"], key="step33_assembly"
        )
        assembly_upload_profile = render_upload_preflight(
            upload,
            key="assembly_fasta",
            allowed_extensions=["fa", "fasta", "fna"],
            soft_limit_mb=30,
            hard_limit_mb=200,
        )
        calculate = st.form_submit_button(
            "Calculate assembly metrics", type="primary", width="stretch"
        )
    if calculate or "step33_assembly_result" not in st.session_state:
        try:
            text = (
                read_uploaded_text(upload)
                if upload
                else read_text_cached(DEMO / "demo_assembly.fasta")
            )
            records = parse_sequences_text(text, max_records=100_000)
            metrics = assembly_metrics([record.sequence for record in records])
            st.session_state["step33_assembly_result"] = {
                "payload": metrics_dict(metrics),
                "lengths": [
                    {
                        "Contig": record.header or f"contig_{index + 1}",
                        "Length": len(record.sequence),
                    }
                    for index, record in enumerate(records)
                ],
            }
        except ValueError as exc:
            st.error(str(exc))
    assembly_result = st.session_state.get("step33_assembly_result")
    if assembly_result:
        payload = assembly_result["payload"]
        metric_cards(
            [
                ("Contigs", f"{payload['sequences']:,}", None),
                ("Total bases", f"{payload['total_bases']:,}", None),
                ("N50", f"{payload['n50']:,}", None),
                ("L50", f"{payload['l50']:,}", None),
                ("GC", f"{payload['gc_percent']:.2f}%", None),
                ("Ambiguous", f"{payload['ambiguous_percent']:.3f}%", None),
            ]
        )
        lengths = pd.DataFrame(assembly_result["lengths"])
        charts = st.columns(2)
        charts[0].plotly_chart(
            px.histogram(lengths, x="Length", nbins=40, title="Contig length distribution"),
            width="stretch",
        )
        ranked = lengths.sort_values("Length", ascending=False).assign(
            Rank=lambda data: range(1, len(data) + 1)
        )
        charts[1].plotly_chart(
            px.line(ranked, x="Rank", y="Length", title="Ranked contig lengths"), width="stretch"
        )
        result_summary(payload, title="Assembly summary")
        st.download_button(
            "Download assembly metrics",
            pd.DataFrame([payload]).to_csv(index=False),
            "assembly_metrics.csv",
            "text/csv",
            width="stretch",
        )


# Step 112 shared bioinformatics feature upgrades
from biointel.ui.bioinformatics_upgrades import render_bioinformatics_upgrade_panel
render_bioinformatics_upgrade_panel("fastq", expanded=False)

# Step 115 module-specific non-chart workspace: fastq
from biointel.ui.non_chart_scientific_visuals import render_module_non_chart_panel as _render_step115_module_non_chart
_render_step115_module_non_chart("fastq", key_prefix="step115_56_FASTQ_Genomics_QC_fastq", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_FASTQ_QC
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('fastq_qc', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='fastq_genomics_qc', title='FASTQ & Genome QC', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='fastq_genomics_qc', title='FASTQ & Genome QC', category='Bioinformatics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
