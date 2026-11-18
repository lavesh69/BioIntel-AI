from __future__ import annotations

import platform
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel import __version__
from biointel.data.coverage_packs import (
    load_coverage_manifest,
    verify_coverage_integrity,
)
from biointel.data.data_packs import data_library_summary, verify_data_pack_integrity
from biointel.intelligence.data_intelligence import all_database_health
from biointel.production_enablement_v217 import (
    readiness_table_rows as production_readiness_rows,
    scan_production_enablement,
)
from biointel.release_readiness_v216 import readiness_table_rows, scan_release_readiness
from biointel.ui.theme import apply_theme, badge, executive_kpis, hero, section_title


def _package_version(distribution: str) -> str:
    try:
        return package_version(distribution)
    except PackageNotFoundError:
        return "Not installed"

st.set_page_config(page_title="Project Status · BioIntel AI", page_icon="✅", layout="wide")
apply_theme()
library = data_library_summary(ROOT)
integrity = verify_data_pack_integrity(ROOT)
benchmark = library["benchmark"]
coverage = load_coverage_manifest(ROOT)
coverage_integrity = verify_coverage_integrity(ROOT)
database_health = all_database_health(ROOT)
release_readiness = scan_release_readiness(ROOT, deep_hashes=False)
production_readiness = scan_production_enablement(ROOT)

hero(
    "A professional local research platform with verified scientific database systems.",
    (
        "Review quality-hardened scientific workflows, lineage, runtime health and local evidence boundaries using live package and database counts."
    ),
    eyebrow="Project status · Quality-Hardened Scientific Data & UI Overhaul",
    chips=[
        f"{database_health['database_count']} databases",
        f"{len(list((ROOT / 'models').glob('*.joblib')))} model artifacts",
        "Step216 readiness",
        f"Step217 · {production_readiness['internal_controls_ready']}/{production_readiness['capability_count']} controls",
        "offline starter kits",
    ],
)
badge(
    (
        "● Quality-Hardened scientific data and interface overhaul ready"
        if integrity["valid"]
        else "● Data integrity requires attention"
    ),
    "success" if integrity["valid"] else "danger",
)

executive_kpis(
    [
        (
            "Step216 readiness",
            "Pass" if release_readiness["passed"] else "Review",
            f"{release_readiness['score_percent']}% checks",
        ),
        (
            "Step217 controls",
            f"{production_readiness['internal_controls_ready']}/{production_readiness['capability_count']}",
            f"{len(production_readiness['p0_blockers'])} P0 evidence blockers",
        ),
        ("App version", __version__, "Connected Research Edition"),
        (
            "Database systems",
            str(database_health["database_count"]),
            f"{database_health['total_rows']:,} indexed rows",
        ),
        (
            "Model artifacts",
            str(len(list((ROOT / "models").glob("*.joblib")))),
            "Classification and regression",
        ),
        (
            "Benchmark leader",
            str(
                benchmark.get("best_models", {}).get("classification", {}).get("model_name", "N/A")
            ),
            "Overall held-out ROC-AUC winner",
        ),
    ]
)

section_title("Step216 release readiness", "OK")
with st.container(horizontal=True):
    st.metric(
        "Readiness",
        "Pass" if release_readiness["passed"] else "Review",
        f"{release_readiness['checks_passed']}/{release_readiness['checks_total']} checks",
        border=True,
    )
    st.metric(
        "Physical release",
        f"Step{release_readiness['physical_release_step']}",
        release_readiness["physical_package_generation"],
        border=True,
    )
    st.metric(
        "Readiness layer",
        f"Step{release_readiness['release_step']}",
        release_readiness["package_generation"],
        border=True,
    )
    st.metric(
        "Blockers",
        len(release_readiness["blockers"]),
        "target-machine review" if release_readiness["blockers"] else "none",
        border=True,
    )

if release_readiness["passed"]:
    st.success("Step216 software readiness checks passed in quick mode.")
else:
    st.warning("Step216 found release-readiness items that need review before packaging.")

st.caption(release_readiness["claim_boundary"])
st.dataframe(
    pd.DataFrame(readiness_table_rows(release_readiness)),
    width="stretch",
    hide_index=True,
    column_config={
        "Check": st.column_config.TextColumn("Check", pinned=True),
        "Status": st.column_config.TextColumn("Status"),
        "Severity": st.column_config.TextColumn("Severity"),
        "Detail": st.column_config.TextColumn("Detail", width="large"),
    },
)

section_title("Step217 production enablement", ":material/fact_check:")
with st.container(horizontal=True):
    st.metric(
        "Internal controls",
        f"{production_readiness['internal_controls_ready']}/{production_readiness['capability_count']}",
        "installed",
        border=True,
    )
    st.metric(
        "Release eligible",
        f"{production_readiness['release_eligible_capabilities']}/{production_readiness['capability_count']}",
        "external evidence gated",
        border=True,
    )
    st.metric(
        "Qualified engines",
        f"{production_readiness['engine_inventory']['qualified_on_target']}/{production_readiness['engine_inventory']['registered']}",
        "target machine",
        border=True,
    )
    st.metric(
        "Qualified models",
        production_readiness["model_inventory"]["qualified_candidates"],
        "independent candidates",
        border=True,
    )

if production_readiness["p0_blockers"]:
    st.warning(
        "Step217 P0 evidence blockers: " + ", ".join(production_readiness["p0_blockers"]),
        icon=":material/warning:",
    )
else:
    st.success("Step217 P0 release gates are satisfied.", icon=":material/check_circle:")

st.caption(production_readiness["claim_boundary"])
st.dataframe(
    pd.DataFrame(production_readiness_rows(production_readiness)),
    width="stretch",
    hide_index=True,
    column_config={
        "Priority": st.column_config.TextColumn("Priority", pinned=True),
        "Capability": st.column_config.TextColumn("Capability", width="large"),
        "Control": st.column_config.TextColumn("Control"),
        "Evidence": st.column_config.TextColumn("Evidence"),
        "Release eligible": st.column_config.CheckboxColumn("Release eligible"),
        "Detail": st.column_config.TextColumn("Detail", width="large"),
    },
)
section_title("Quality-Hardened scientific data and interface overhaul", "📄")
st.markdown(
    """
- 20,000-read FASTQ reference cohort, paired-end files and assembly N50/L50 metrics
- 5,000-variant cohort plus 2,000-gene GFF/GTF annotation reference
- Primer, CRISPR guide and codon-optimization screening tools
- 5,000-gene × 24-sample transcriptomics normalization, differential-expression screening and PCA
- 200-protein family panel, 1,000-feature proteomics matrix and 12 PDB ligand-contact structures
- ADMET/drug-likeness, pathway enrichment and multi-omics integration
- Plate-scale qPCR/ELISA, replicate enzyme kinetics and 241-point bioprocess time series
- 300-taxa × 40-sample microbiome, ANI proxy and 50-sequence phylogeny
- Ten Step 93 innovation workbenches plus advanced native Windows + WSL toolchain manager for BLAST+, MAFFT, HMMER, MMseqs2, minimap2, samtools, bcftools, FastQC, fastp, MultiQC, Bowtie 2, Kraken 2, Bracken, MetaPhlAn, HUMAnN, FastANI, Mash, Prokka, Bakta, AMRFinderPlus, IQ-TREE, VEP, SnpEff, Primer3 and Vina
- Dataset files, samples, QC metrics, column dictionary and cross-dataset lineage
- Research Knowledge Warehouse with searchable scientific entities
- Analytics & Observability Warehouse with 15,000 run events
- Research Assets database with indexed project assets
- Eleven total SQLite systems including job queue and persistent feature cache
- Universal cross-database search
- Secure RCSB PDB and public HTTPS research downloads
- Database health, optimize, backup and JSON export
- 16-format document extraction with reviewed OCR and six downloadable output formats
- Full-text search, scientific entities, cited Q&A and document comparison
- Dataset/Evidence Registry document bridge and soft-delete history controls
- Premium database cards, insight surfaces and responsive UI
- Existing 160,000-row DTI and 23-model suite retained
- No-login local operation retained
"""
)

section_title("5X model results", "🧠")
ranking = pd.DataFrame(benchmark.get("ranking", []))
five_x = ranking[ranking.get("training_pack", pd.Series(dtype=str)) == "five_x_ultra"]
st.dataframe(five_x, width="stretch", hide_index=True)

section_title("Runtime versions", "◈")
versions = pd.DataFrame(
    [
        {"Component": "BioIntel AI", "Version": __version__},
        {"Component": "Python", "Version": platform.python_version()},
        {"Component": "Streamlit", "Version": st.__version__},
        {"Component": "FastAPI", "Version": _package_version("fastapi")},
        {"Component": "BioIntel Sequence Intelligence", "Version": _package_version("biopython")},
        {"Component": "BioIntel Molecular Intelligence", "Version": _package_version("rdkit")},
        {"Component": "BioIntel Predictive Analytics", "Version": _package_version("scikit-learn")},
    ]
)
st.dataframe(versions, width="stretch", hide_index=True)

section_title("Release pulse", "◎")
columns = st.columns(5)
columns[0].metric("Access", "No login")
columns[1].metric("Entry points", 106)
columns[2].metric("Scientific modules", "14 core areas")
columns[3].metric("Application", __version__)
columns[4].metric(
    "Databases", f"{database_health['healthy_count']}/{database_health['database_count']} healthy"
)

st.info(
    "Coverage and seeded workspace records are demonstration content. "
    "Replace them with independently reviewed real evidence for research use."
)

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
