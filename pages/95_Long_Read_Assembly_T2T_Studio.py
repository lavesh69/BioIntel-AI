from __future__ import annotations

import shlex
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.innovation.engines import assembly_plan, demo_fastq
from biointel.innovation.advanced_engines import (
    assembly_command_plan, contig_qc_advanced, long_read_qc_metrics, parse_fastq_advanced,
)
from biointel.tools.runtime import all_tool_status, resolve_tool, run_tool_audited
from biointel.innovation.excellence_ui import render_long_read_excellence
from biointel.innovation.professional_ui import render_long_read_professional
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title
from biointel.ui.workflow import render_upload_preflight

st.set_page_config(page_title="Long-Read Assembly & T2T Studio · BioIntel AI", page_icon="🧵", layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('long_read_core', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'long_read_core', expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("long_read", key_prefix="step116_95_Long_Read_Assembly_T2T_Studio_long_read_1", expanded=False)
hero(
    "Long-Read Assembly & T2T Studio Pro",
    "Profile ONT/PacBio reads, estimate coverage, generate executable assembly plans and audit contigs with L50, auN, circularity and telomere-end signals.",
    eyebrow="Step 99 · Executable long-read genomics upgrade",
    chips=["FASTQ.GZ", "Q20 yield", "N50/N90", "auN/L50", "Audited execution", "Artifact manifests"],
)
scientific_boundary_banner(source_kind="demo_reference", release_eligible=False, message="BioIntel audits inputs and generates reproducible commands. Publication-grade assembly still requires organism-appropriate databases, contamination controls, validated tool versions and manual graph review.")

read_tab, plan_tab, contig_tab, execution_tab = st.tabs(["1 · Read QC", "2 · Assembly design", "3 · Contig/T2T review", "4 · Execution preflight"])
with read_tab:
    cols = st.columns(3)
    source = cols[0].radio("Read source", ["Deterministic demo", "Upload FASTQ/FASTQ.GZ"], horizontal=False)
    genome_size = cols[1].number_input("Expected genome size (Mb)", 0.01, 100000.0, 5.0, 0.5)
    max_reads = cols[2].number_input("Maximum reads to profile", 100, 500000, 20000, 1000)
    upload = st.file_uploader("Long-read FASTQ", type=["fastq", "fq", "gz"], disabled=source == "Deterministic demo")
    render_upload_preflight(
        upload, key="long_read_fastq", allowed_extensions=["fastq", "fq", "gz"],
        soft_limit_mb=250, hard_limit_mb=2048,
    )
    try:
        raw = upload.getvalue() if upload else demo_fastq(300).encode()
        reads = parse_fastq_advanced(raw, upload.name if upload else "demo.fastq", int(max_reads))
        metrics = long_read_qc_metrics(reads, float(genome_size))
    except Exception as exc:
        st.error(f"FASTQ QC failed: {exc}")
        st.stop()
    metric_cards([
        ("Reads", f"{metrics['reads']:,}", None), ("Yield", f"{metrics['bases'] / 1e6:.2f} Mb", None),
        ("N50", f"{metrics['n50']:,} bp", None), ("N90", f"{metrics['n90']:,} bp", None),
        ("Mean Q", f"{metrics['mean_q']:.1f}", None), ("Q20 base fraction", f"{metrics['q20_base_fraction']:.1%}", None),
        ("Estimated coverage", f"{metrics['estimated_coverage']:.1f}×", None), ("QC grade", metrics["qc_grade"], None),
    ])
    c1, c2, c3 = st.columns(3)
    with c1:
        st.plotly_chart(px.histogram(reads, x="length", nbins=55, title="Read-length distribution"), width="stretch")
    with c2:
        st.plotly_chart(px.scatter(reads, x="length", y="mean_q", color="gc", opacity=0.65, title="Length–quality landscape"), width="stretch")
    with c3:
        quality_summary = pd.DataFrame({"metric": ["Q10", "Q20", "Q30"], "fraction": [reads["q10_fraction"].mean(), reads["q20_fraction"].mean(), reads["q30_fraction"].mean()]})
        st.plotly_chart(px.bar(quality_summary, x="metric", y="fraction", range_y=[0, 1], title="Per-read base quality fractions"), width="stretch")
    smart_dataframe(reads.head(5000), height=380, key="long_read_qc_advanced")
    st.download_button("Export read QC table", reads.to_csv(index=False).encode(), "long_read_qc.csv", "text/csv")

with plan_tab:
    cols = st.columns(4)
    platform = cols[0].selectbox("Platform", ["Oxford Nanopore", "PacBio HiFi", "PacBio CLR"])
    genome_type = cols[1].selectbox("Genome type", ["Bacterial/microbial", "Fungal", "Plant", "Human/animal", "Metagenome"])
    coverage = cols[2].number_input("Estimated coverage ×", 1.0, 500.0, 45.0, 1.0)
    hybrid = cols[3].toggle("Hybrid short-read polish", value=False)
    recommendation = assembly_plan(platform, genome_type, float(coverage), hybrid)
    commands = assembly_command_plan(platform, genome_type, "reads.fastq.gz", "assembly_output", 8, "short_reads.bam" if hybrid else None)
    section_title("Scientific workflow recommendation", "🧬")
    smart_dataframe(recommendation, height=330, key="assembly_recommendation")
    section_title("Reproducible command plan", "⌘")
    smart_dataframe(commands, height=360, key="assembly_commands")
    st.download_button("Download command plan", commands.to_csv(index=False).encode(), "long_read_command_plan.csv", "text/csv")
    insight_callout("Execution safety", "Commands are generated but not launched automatically. Review paths, genome mode, read chemistry and resource limits before running specialist tools.", tone="warning")

with contig_tab:
    source = st.radio("Assembly source", ["Demo contigs", "Paste/upload FASTA"], horizontal=True, key="contig_source")
    upload_fasta = st.file_uploader("Assembly FASTA", type=["fa", "fasta", "fna", "txt"], disabled=source == "Demo contigs")
    render_upload_preflight(
        upload_fasta, key="assembly_fasta", allowed_extensions=["fa", "fasta", "fna", "txt"],
        soft_limit_mb=100, hard_limit_mb=500,
    )
    default_fasta = ">chromosome_candidate\n" + "ACGT" * 7000 + "TTAGGG" * 18 + "\n>circular_plasmid\n" + "GGCATC" * 800 + ("GGCATC" * 5)
    fasta_text = upload_fasta.getvalue().decode("utf-8", errors="replace") if upload_fasta else default_fasta
    try:
        contigs, summary = contig_qc_advanced(fasta_text)
    except Exception as exc:
        st.error(f"Contig audit failed: {exc}")
        st.stop()
    metric_cards([
        ("Contigs", summary["contigs"], None), ("Assembly span", f"{summary['total_bp']:,} bp", None),
        ("N50 / L50", f"{summary['n50']:,} / {summary['l50']}", None), ("auN", f"{summary['auN']:,.0f}", None),
        ("Largest", f"{summary['largest']:,} bp", None), ("Circular candidates", summary["circular_candidates"], None),
        ("Two-end telomere signal", summary["telomere_complete_candidates"], None), ("N per 100 kb", f"{summary['n_per_100kb']:.1f}", None),
    ])
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(px.bar(contigs.head(50), x="contig", y="length", color="gc", title="Contig length and GC"), width="stretch")
    with c2:
        st.plotly_chart(px.scatter(contigs, x="length", y="n_per_100kb", color="circular_candidate", size="terminal_overlap_bp", title="Ambiguity and circularity review"), width="stretch")
    smart_dataframe(contigs, height=430, key="contig_qc_advanced")
    st.download_button("Export contig audit", contigs.to_csv(index=False).encode(), "contig_t2t_audit.csv", "text/csv")

with execution_tab:
    status = pd.DataFrame(all_tool_status(include_versions=False))
    wanted = ["fastqc", "fastp", "minimap2", "samtools", "bcftools", "flye", "hifiasm", "canu", "quast", "busco"]
    selected = status[status["executable"].isin(wanted)].copy() if not status.empty else status
    available = int(selected["available"].sum()) if not selected.empty else 0
    metric_cards([("Required/optional tools", len(selected), None), ("Detected", available, None), ("Missing", len(selected) - available, None), ("Execution readiness", f"{available / max(1, len(selected)):.0%}", None)])
    smart_dataframe(selected, height=500, key="long_read_tool_preflight")
    smart_json({"required_tools": wanted, "tools_home": str(status["path_or_command"].iloc[0]) if not status.empty and "path_or_command" in status else "See Advanced Tools Manager"}, key="long_read_preflight_json")
    section_title("Audited specialist-tool execution", "▶")
    exec_cols = st.columns([1, 2, 2])
    selected_tool = exec_cols[0].selectbox("Tool", ["fastqc", "fastp", "flye", "hifiasm", "canu", "quast", "busco"], key="long_read_exec_tool")
    input_path = exec_cols[1].text_input("Input path", "", help="Use a local path accessible to the selected native or WSL tool.", key="long_read_exec_input")
    run_directory = exec_cols[2].text_input("Evidence directory", str(ROOT / "workspace" / "tool_runs" / "long_read"), key="long_read_exec_dir")
    default_arguments = {
        "fastqc": '"{input}" --outdir "{run_dir}"',
        "fastp": '-i "{input}" -o "{run_dir}/clean.fastq.gz" --json "{run_dir}/fastp.json" --html "{run_dir}/fastp.html"',
        "flye": '--nano-hq "{input}" --out-dir "{run_dir}/flye" --threads 8',
        "hifiasm": '-o "{run_dir}/hifiasm" -t 8 "{input}"',
        "canu": '-p assembly -d "{run_dir}/canu" genomeSize=5m -nanopore "{input}"',
        "quast": '"{input}" -o "{run_dir}/quast"',
        "busco": '-i "{input}" -o busco_result -m genome --out_path "{run_dir}"',
    }
    template = default_arguments[selected_tool].format(input=input_path or "INPUT_FILE", run_dir=run_directory.replace("\\", "/"))
    arguments_text = st.text_area("Arguments", template, height=110, key=f"long_read_arguments_{selected_tool}")
    resolution = resolve_tool(selected_tool)
    if resolution.available:
        st.success(f"{selected_tool} detected via {resolution.backend}: {resolution.executable}")
    else:
        st.warning(f"{selected_tool} is not installed. Use Advanced Bioinformatics Tools before execution.")
    confirm = st.checkbox("I reviewed the command, paths, chemistry and resource requirements", key="long_read_exec_confirm")
    if st.button("Run selected tool with audit evidence", type="primary", disabled=not (resolution.available and input_path.strip() and confirm), width="stretch"):
        try:
            arguments = shlex.split(arguments_text, posix=False)
            with st.spinner(f"Running {selected_tool} and capturing command evidence..."):
                result = run_tool_audited(
                    selected_tool,
                    arguments,
                    run_directory=run_directory,
                    cwd=Path(input_path).expanduser().parent if Path(input_path).expanduser().parent.exists() else None,
                    timeout_seconds=24 * 60 * 60,
                )
            st.success(f"{selected_tool} completed in {result.duration_seconds:.1f} seconds.")
            smart_json(result.to_dict(), key="long_read_audited_execution_result")
        except Exception as exc:
            st.error(f"Tool execution failed: {exc}")
    insight_callout("Full pipeline boundary", "Step 99 can launch detected specialist tools and records the command, executable identity, binary hash where available, exit code, stdout and stderr. A T2T claim still requires real reads, appropriate references, contamination control and expert review.", tone="info")

# Step 99 module excellence layer
render_long_read_excellence(reads, metrics, contigs, summary)

# Step 100 professional integration and optimization layer
render_long_read_professional(reads, metrics, contigs)


# Step 112 shared bioinformatics feature upgrades
from biointel.ui.bioinformatics_upgrades import render_bioinformatics_upgrade_panel
render_bioinformatics_upgrade_panel("long_read", expanded=False)

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("long_read_core", None, key_prefix="step114_long_read_core", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_LONG_READ
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('long_read', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='long_read_assembly', title='Long-Read Assembly & T2T Studio', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='long_read_assembly', title='Long-Read Assembly & T2T Studio', category='Bioinformatics')

# STEP176_TARGET_MODULE_OPERATIONAL_EXCELLENCE
from biointel.target_modules_v176.ui import render_target_module_upgrade as _render_step176_target_module_upgrade
_render_step176_target_module_upgrade('long_read_core', expanded=False)

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("long_read_core", expanded=False)

# Step 184 advanced deterministic demo assurance
from biointel.demo_assurance_v184.ui import render_step184_demo_assurance as _render_step184_demo_assurance
_render_step184_demo_assurance("long_read_core", expanded=False)

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('long_read_core', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('long_read_core', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('long_read_core', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('long_read_core', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('long_read_core', expanded=False)

