from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.genomics.codon_advanced import HOST_PRIMARY, optimize_protein_advanced
from biointel.genomics.codon_advanced import result_dict as codon_result_dict
from biointel.genomics.design_advanced import (
    NUCLEASES,
    base_editing_window,
    deletion_guide_pairs,
    design_primer_pairs_advanced,
    find_crispr_guides_advanced,
    in_silico_pcr,
    multiplex_compatibility,
    result_dict,
)
from biointel.sequence.parser import parse_sequences_text
from biointel.ui.scientific_visuals import render_generic_visual_explorer
from biointel.ui.components import (
    metric_cards,
    scientific_boundary_banner,
    smart_dataframe,
    smart_json,
)
from biointel.ui.performance import read_text_cached
from biointel.ui.theme import apply_theme, hero, insight_callout
from biointel.ui.workflow import analysis_run, render_methodology

DEMO = ROOT / "data" / "bioinformatics_demo"
st.set_page_config(page_title="Primer, CRISPR & Codon Studio · BioIntel AI", page_icon="🧫", layout="wide")
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("primer_codon", key_prefix="step116_58_Primer_CRISPR_Codon_Studio_primer_codon_1", expanded=False)
hero(
    "Primer, CRISPR & Codon Studio",
    "Thermodynamic primer screening, nuclease-aware CRISPR design with optional local off-target checks, and constraint-aware multi-candidate codon optimization.",
    eyebrow="BioIntel AI · Molecular Design",
    chips=["Nearest-neighbour Tm", "Multi-nuclease CRISPR", "Local off-targets", "CAI + GC windows"],
)
scientific_boundary_banner(
    source_kind="demo_reference",
    release_eligible=False,
    message="In-silico engineering support only. Confirm specificity against the intended reference build, validate oligos experimentally and review current nuclease/host guidance before laboratory use.",
)
render_methodology(
    method="Transparent local primer thermodynamics, IUPAC PAM matching, sequence-level off-target screening and synonymous-codon constraint optimization.",
    assumptions=["The supplied target/reference sequences and reaction chemistry reflect the planned assay."],
    limitations=["Local sequence scanning is not a substitute for a complete indexed genome search.", "Bundled host codon profiles are engineering defaults rather than certified organism-wide expression guarantees."],
    validation=["Confirm primers using Primer-BLAST/in-silico PCR.", "Confirm guide specificity with a current organism/genome-build reference and appropriate off-target software."],
)

template_pack = ROOT / "data" / "lab_templates" / "LAB_ANALYTICS_TEMPLATE_PACK.zip"
if template_pack.exists():
    st.download_button(
        "Download molecular-design and lab template pack",
        template_pack.read_bytes(),
        "LAB_ANALYTICS_TEMPLATE_PACK.zip",
        "application/zip",
        width="stretch",
        key="molecular_design_template_pack",
    )

dna_default = parse_sequences_text(read_text_cached(DEMO / "demo_dna_template.fasta"))[0].sequence
primer_tab, crispr_tab, codon_tab = st.tabs(["Primer design", "CRISPR guides", "Codon optimization"])

with primer_tab:
    with st.form("primer_design_advanced_form"):
        sequence = st.text_area("DNA template", dna_default, height=190)
        row1 = st.columns(5)
        assay_mode = row1[0].selectbox("Assay mode", ["standard_pcr", "qpcr", "target_region"])
        minimum_product = row1[1].number_input("Minimum product (bp)", 40, 5_000, 100)
        maximum_product = row1[2].number_input("Maximum product (bp)", 50, 10_000, 500)
        minimum_length = row1[3].number_input("Minimum primer length", 15, 35, 18)
        maximum_length = row1[4].number_input("Maximum primer length", 16, 40, 24)
        row2 = st.columns(5)
        minimum_tm = row2[0].number_input("Minimum Tm °C", 40.0, 80.0, 57.0, 0.5)
        maximum_tm = row2[1].number_input("Maximum Tm °C", 40.0, 85.0, 63.0, 0.5)
        minimum_gc = row2[2].number_input("Minimum GC %", 10.0, 90.0, 35.0, 1.0)
        maximum_gc = row2[3].number_input("Maximum GC %", 10.0, 90.0, 65.0, 1.0)
        maximum_pairs = row2[4].number_input("Maximum pairs", 5, 500, 100)
        row3 = st.columns(5)
        sodium = row3[0].number_input("Na⁺ (mM)", 0.0, 500.0, 50.0, 5.0)
        magnesium = row3[1].number_input("Mg²⁺ (mM)", 0.0, 20.0, 1.5, 0.1)
        dntp = row3[2].number_input("dNTP (mM)", 0.0, 10.0, 0.2, 0.1)
        primer_nm = row3[3].number_input("Primer concentration (nM)", 10.0, 5_000.0, 250.0, 10.0)
        search_mode = row3[4].selectbox(
            "Search thoroughness",
            ["balanced", "fast", "exhaustive"],
            help="Balanced is recommended. Exhaustive evaluates every viable oligo length and can take longer on large templates.",
        )
        use_target = st.toggle(
            "Require the amplicon to flank a target interval",
            value=assay_mode == "target_region",
        )
        maximum_target_start = max(len(sequence) - 1, 0)
        maximum_target_end = max(len(sequence), 1)
        # Clamp widget-backed values before the widgets are instantiated. This avoids
        # StreamlitAPIException when a user replaces a long template with a shorter one.
        stored_start = int(st.session_state.get("primer_target_start", min(50, maximum_target_start)))
        stored_start = min(max(stored_start, 0), maximum_target_start)
        st.session_state["primer_target_start"] = stored_start
        stored_end = int(st.session_state.get("primer_target_end", min(max(100, stored_start + 1), maximum_target_end)))
        stored_end = min(max(stored_end, stored_start + 1), maximum_target_end)
        if stored_end <= stored_start:
            stored_start = max(0, maximum_target_end - 1)
            stored_end = maximum_target_end
            st.session_state["primer_target_start"] = stored_start
        st.session_state["primer_target_end"] = stored_end
        target_cols = st.columns(2)
        target_start = target_cols[0].number_input(
            "Target start (0-based)",
            0,
            maximum_target_start,
            disabled=not use_target,
            key="primer_target_start",
        )
        target_end = target_cols[1].number_input(
            "Target end (exclusive)",
            1,
            maximum_target_end,
            disabled=not use_target,
            key="primer_target_end",
        )
        reference_panel = st.text_area(
            "Optional reference-panel FASTA for exact in-silico PCR",
            "",
            height=100,
            help="Use compact reference/transcript panels here. Genome-wide mismatch-tolerant specificity still requires Primer-BLAST or an indexed aligner.",
        )
        circular_references = st.toggle("Treat reference-panel sequences as circular", value=False, disabled=not bool(reference_panel.strip()))
        run = st.form_submit_button("Design thermodynamic primer pairs", type="primary", width="stretch")
    if len(sequence) > 5_000:
        st.warning(
            "Large template detected. Use Fast or Balanced search for interactive work; "
            "genome-scale specificity still requires Primer-BLAST or an indexed aligner."
        )
    if run:
        try:
            with analysis_run(
                "Screening primers, thermodynamics and pair compatibility", expanded=True
            ) as run_state:
                pairs = design_primer_pairs_advanced(
                    sequence,
                    minimum_product=int(minimum_product),
                    maximum_product=int(maximum_product),
                    minimum_length=int(minimum_length),
                    maximum_length=int(maximum_length),
                    minimum_tm=float(minimum_tm),
                    maximum_tm=float(maximum_tm),
                    minimum_gc=float(minimum_gc),
                    maximum_gc=float(maximum_gc),
                    target_start=int(target_start) if use_target else None,
                    target_end=int(target_end) if use_target else None,
                    assay_mode=assay_mode,
                    sodium_millimolar=float(sodium),
                    magnesium_millimolar=float(magnesium),
                    dntp_millimolar=float(dntp),
                    primer_nanomolar=float(primer_nm),
                    maximum_pairs=int(maximum_pairs),
                    search_mode=search_mode,
                    progress_callback=lambda label, progress: run_state.stage(
                        label, progress=progress
                    ),
                )
                run_state.stage(
                    f"Prepared {len(pairs):,} ranked primer pairs", progress=1.0
                )
            data = pd.DataFrame(
                [
                    {
                        "forward": pair.forward.sequence,
                        "reverse": pair.reverse.sequence,
                        "forward_start": pair.forward.start,
                        "reverse_start": pair.reverse.start,
                        "product_size": pair.product_size,
                        "forward_tm": pair.forward.tm_celsius,
                        "reverse_tm": pair.reverse.tm_celsius,
                        "tm_difference": pair.tm_difference,
                        "forward_gc": pair.forward.gc_percent,
                        "reverse_gc": pair.reverse.gc_percent,
                        "forward_3p_complementarity": pair.forward.three_prime_complementarity,
                        "reverse_3p_complementarity": pair.reverse.three_prime_complementarity,
                        "heterodimer_proxy": pair.heterodimer_proxy,
                        "score": pair.score,
                        "warnings": "; ".join(pair.warnings),
                    }
                    for pair in pairs
                ]
            )
            metric_cards([
                ("Candidate pairs", len(data), None),
                ("Clean pairs", int(data["warnings"].eq("").sum()) if not data.empty else 0, None),
                ("Best score", f"{data['score'].max():.1f}" if not data.empty else "—", None),
                ("Assay mode", assay_mode.replace("_", " ").title(), None),
            ])
            smart_dataframe(data, height=520)
            if not data.empty:
                st.plotly_chart(px.scatter(data, x="product_size", y="score", color="heterodimer_proxy", hover_data=["forward", "reverse", "warnings"], title="Primer-pair design space"), width="stretch")
                render_generic_visual_explorer(
                    data,
                    key="primer_design_visuals",
                    heading="Primer design visual analytics",
                )
                st.download_button("Download primer pairs", data.to_csv(index=False), "primer_pairs_thermodynamic.csv", "text/csv", width="stretch")
                compatibility = pd.DataFrame(multiplex_compatibility(pairs[: min(20, len(pairs))]))
                if not compatibility.empty:
                    with st.expander("Multiplex compatibility audit", expanded=False):
                        smart_dataframe(compatibility, height=320)
                        st.download_button("Download multiplex compatibility", compatibility.to_csv(index=False), "primer_multiplex_compatibility.csv", "text/csv", width="stretch")
                if reference_panel.strip():
                    references = [record.sequence for record in parse_sequences_text(reference_panel)]
                    products = pd.DataFrame(in_silico_pcr(pairs[: min(50, len(pairs))], references, circular=bool(circular_references)))
                    with st.expander("Exact local in-silico PCR products", expanded=True):
                        if products.empty:
                            st.warning("No exact amplicons were found in the supplied reference panel.")
                        else:
                            product_counts = products.groupby("pair_index").size().rename("predicted_products").reset_index()
                            smart_dataframe(product_counts, height=220)
                            smart_dataframe(products.drop(columns=["product_sequence"]), height=360)
                            st.download_button("Download in-silico PCR products", products.to_csv(index=False), "in_silico_pcr_products.csv", "text/csv", width="stretch")
        except Exception as exc:
            st.error(f"Primer design could not run: {exc}")

with crispr_tab:
    with st.form("crispr_advanced_form"):
        sequence = st.text_area("DNA target", dna_default, height=180, key="crispr_sequence")
        row1 = st.columns(4)
        nuclease = row1[0].selectbox("Nuclease", list(NUCLEASES))
        minimum_gc = row1[1].slider("Minimum guide GC %", 0, 100, 35)
        maximum_gc = row1[2].slider("Maximum guide GC %", 0, 100, 70)
        maximum_results = row1[3].number_input("Maximum results", 10, 1_000, 150)
        reference_text = st.text_area(
            "Optional local reference FASTA/sequences for off-target screening",
            "",
            height=120,
            help="Paste one or more FASTA records. For whole-genome work use a specialist indexed aligner; this local scan is designed for compact reference panels.",
        )
        mismatch_limit = st.slider("Maximum off-target mismatches", 0, 5, 3, disabled=not bool(reference_text.strip()))
        edit_cols = st.columns(4)
        editing_mode = edit_cols[0].selectbox("Editing workflow", ["Nuclease knockout", "CBE base editing", "ABE base editing", "Paired-guide deletion"])
        window_start = edit_cols[1].number_input("Editor window start", 1, 20, 4, disabled="base editing" not in editing_mode.lower())
        window_end = edit_cols[2].number_input("Editor window end", 1, 20, 8, disabled="base editing" not in editing_mode.lower())
        deletion_start = edit_cols[3].number_input("Deletion target start", 0, max(len(sequence) - 1, 0), min(50, max(len(sequence) - 1, 0)), disabled=editing_mode != "Paired-guide deletion")
        deletion_end = st.number_input("Deletion target end", 1, max(len(sequence), 1), min(max(100, int(deletion_start) + 1), max(len(sequence), 1)), disabled=editing_mode != "Paired-guide deletion")
        run = st.form_submit_button("Find and rank guide candidates", type="primary", width="stretch")
    if run:
        try:
            references = [record.sequence for record in parse_sequences_text(reference_text)] if reference_text.strip() else None
            with analysis_run("Scanning PAMs and ranking guide efficiency/specificity"):
                guides = pd.DataFrame([result_dict(guide) for guide in find_crispr_guides_advanced(sequence, nuclease=nuclease, reference_sequences=references, maximum_mismatches=int(mismatch_limit))])
            if not guides.empty:
                guides = guides[(guides["gc_percent"] >= minimum_gc) & (guides["gc_percent"] <= maximum_gc)].head(int(maximum_results)).copy()
                guides["risk_flags"] = guides["risk_flags"].map(lambda values: "; ".join(values) if isinstance(values, (list, tuple)) else str(values))
            smart_dataframe(guides, height=540)
            if not guides.empty:
                metric_cards([
                    ("Guides", len(guides), None),
                    ("Median efficiency", f"{guides['efficiency_score'].median():.1f}", None),
                    ("Risk-free", int(guides["risk_flags"].eq("").sum()), None),
                    ("Nuclease", nuclease, NUCLEASES[nuclease]["pam"]),
                ])
                color = "specificity_score" if guides["specificity_score"].notna().any() else "strand"
                st.plotly_chart(px.scatter(guides, x="start", y="efficiency_score", color=color, hover_data=["guide", "pam", "cut_site", "risk_flags"], title="Guide locations and scores"), width="stretch")
                render_generic_visual_explorer(
                    guides,
                    key="crispr_guide_visuals",
                    heading="CRISPR guide visual analytics",
                )
            st.download_button("Download guide candidates", guides.to_csv(index=False), "crispr_guides_advanced.csv", "text/csv", width="stretch")
            raw_guides = find_crispr_guides_advanced(sequence, nuclease=nuclease, reference_sequences=references, maximum_mismatches=int(mismatch_limit))
            if editing_mode in {"CBE base editing", "ABE base editing"} and raw_guides:
                editor = "CBE" if editing_mode.startswith("CBE") else "ABE"
                editing = pd.DataFrame([
                    {**base_editing_window(guide, editor=editor, window_start=int(window_start), window_end=int(window_end)), "start": guide.start, "strand": guide.strand, "efficiency_score": guide.efficiency_score}
                    for guide in raw_guides[: int(maximum_results)]
                ])
                editing["editable_positions"] = editing["editable_positions"].map(lambda values: ", ".join(map(str, values)))
                with st.expander(f"{editor} editing-window audit", expanded=True):
                    smart_dataframe(editing, height=360)
                    st.download_button("Download base-editing audit", editing.to_csv(index=False), "crispr_base_editing_audit.csv", "text/csv", width="stretch")
            elif editing_mode == "Paired-guide deletion" and raw_guides:
                deletion_pairs = pd.DataFrame(deletion_guide_pairs(raw_guides, target_start=int(deletion_start), target_end=int(deletion_end)))
                with st.expander("Paired-guide deletion designs", expanded=True):
                    if deletion_pairs.empty:
                        st.warning("No guide pairs flank the requested interval within the current search window.")
                    else:
                        smart_dataframe(deletion_pairs, height=420)
                        st.download_button("Download deletion guide pairs", deletion_pairs.to_csv(index=False), "crispr_deletion_guide_pairs.csv", "text/csv", width="stretch")
        except Exception as exc:
            st.error(f"CRISPR guide design could not run: {exc}")

with codon_tab:
    with st.form("codon_advanced_form"):
        protein = st.text_area("Protein sequence", "MKWVTFISLLFLFSSAYSRGVFRRDTHKSEIAHRFKDLGE", height=150)
        row1 = st.columns(4)
        host = row1[0].selectbox("Expression host", sorted(HOST_PRIMARY))
        candidates = row1[1].slider("Candidate sequences", 1, 20, 5)
        target_gc = row1[2].slider("Target GC %", 25.0, 75.0, 50.0, 1.0)
        random_seed = row1[3].number_input("Reproducibility seed", 1, 999_999, 42)
        row2 = st.columns(3)
        minimum_window_gc = row2[0].slider("Minimum 60-bp window GC %", 10.0, 60.0, 30.0, 1.0)
        maximum_window_gc = row2[1].slider("Maximum 60-bp window GC %", 40.0, 90.0, 70.0, 1.0)
        include_stop = row2[2].toggle("Append host stop codon", value=False)
        avoid_sites = st.multiselect("Avoid restriction/synthesis motifs", ["GAATTC", "GGATCC", "AAGCTT", "GGTCTC", "CGTCTC", "AAAAAA", "TTTTTT", "AATAAA"], default=["GAATTC", "GGATCC", "GGTCTC", "CGTCTC"])
        custom_motifs = st.text_input("Additional motifs to avoid (comma separated)", "")
        run = st.form_submit_button("Generate optimized candidates", type="primary", width="stretch")
    if run:
        try:
            motifs = avoid_sites + [motif.strip().upper() for motif in custom_motifs.split(",") if motif.strip()]
            with analysis_run("Optimizing synonymous codons and synthesis constraints"):
                results = optimize_protein_advanced(
                    protein,
                    host=host,
                    avoid_motifs=motifs,
                    target_gc_percent=float(target_gc),
                    minimum_window_gc=float(minimum_window_gc),
                    maximum_window_gc=float(maximum_window_gc),
                    candidates=int(candidates),
                    random_seed=int(random_seed),
                    append_stop=include_stop,
                )
            summary = pd.DataFrame([codon_result_dict(result) for result in results])
            summary["removed_motifs"] = summary["removed_motifs"].map(lambda values: "; ".join(values))
            summary["unresolved_motifs"] = summary["unresolved_motifs"].map(lambda values: "; ".join(values))
            codon_display = summary.drop(columns=["optimized_dna", "protein_sequence"])
            smart_dataframe(codon_display, height=360)
            render_generic_visual_explorer(
                codon_display,
                key="codon_optimization_visuals",
                heading="Codon optimisation visual analytics",
            )
            best = results[0]
            metric_cards([
                ("Best CAI proxy", f"{best.cai_proxy:.3f}", None),
                ("Overall GC", f"{best.gc_percent:.1f}%", None),
                ("Window GC", f"{best.minimum_window_gc:.1f}–{best.maximum_window_gc:.1f}%", None),
                ("Unresolved motifs", len(best.unresolved_motifs), None),
            ])
            st.code(best.optimized_dna, language="text")
            insight_callout("Host profile boundary", best.profile_notice, "warning")
            fasta = "\n".join(f">optimized_{host}_candidate_{result.candidate_index}\n{result.optimized_dna}" for result in results) + "\n"
            st.download_button("Download all optimized FASTA candidates", fasta, "optimized_dna_candidates.fasta", "text/plain", width="stretch")
            smart_json(codon_result_dict(best), title="Best-candidate method card", download_name="codon_optimization_method_card.json", key="codon_advanced_method")
        except Exception as exc:
            st.error(f"Codon optimization could not run: {exc}")

# Step 115 non-chart visual: sequence_feature_track
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("sequence_feature_track", key_prefix="step115_58_Primer_CRISPR_Codon_Studio_sequence_feature_track", expanded=False)

# Step 115 module-specific non-chart workspace: crispr
from biointel.ui.non_chart_scientific_visuals import render_module_non_chart_panel as _render_step115_module_non_chart
_render_step115_module_non_chart("crispr", key_prefix="step115_58_Primer_CRISPR_Codon_Studio_crispr", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_PRIMER_CRISPR_CODON
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('primer_crispr_codon', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='primer_crispr_codon', title='Primer, CRISPR & Codon Studio', category='Lab Analytics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='primer_crispr_codon', title='Primer, CRISPR & Codon Studio', category='Lab Analytics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
