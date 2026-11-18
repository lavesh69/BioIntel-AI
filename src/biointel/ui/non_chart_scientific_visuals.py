from __future__ import annotations

import hashlib
import html
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw


@dataclass(frozen=True)
class NonChartVisualSpec:
    key: str
    title: str
    icon: str
    description: str
    modules: tuple[str, ...]
    interaction: str


NON_CHART_VISUAL_CATALOG: dict[str, NonChartVisualSpec] = {
    "genome_track": NonChartVisualSpec(
        "genome_track", "Interactive Genome Track Canvas", "🧬",
        "Inspect gene models, variants, peaks, coverage, splice junctions and selected intervals without reducing them to summary charts.",
        ("Variant Workbench", "GWAS", "Epigenomics", "CRISPR", "RNA Splicing", "Cancer Genomics", "Structural Variants"),
        "Coordinate selection, track visibility, feature details and interval export",
    ),
    "molecular_scene": NonChartVisualSpec(
        "molecular_scene", "Molecular Structure Scene", "🧩",
        "Review chains, ligands, residues, contacts, pockets and mutations in an offline structure-inspection canvas.",
        ("Structural Bioinformatics", "Docking", "Antibody Engineering", "Protein Design", "Immunoinformatics", "Enzyme Engineering"),
        "Chain/residue selection, contact inspection, scene presets and snapshot-ready state",
    ),
    "microscopy_editor": NonChartVisualSpec(
        "microscopy_editor", "Microscopy Mask Overlay Editor", "🔬",
        "Review raw channels, segmentation masks, object labels and correction candidates on the image itself.",
        ("Bioimage & Microscopy", "Organoid Analytics", "High-Content Screening", "Spatial Biology"),
        "Threshold, mask opacity, object selection, false-positive review and corrected-mask export",
    ),
    "pathology_canvas": NonChartVisualSpec(
        "pathology_canvas", "Whole-Slide Pathology Canvas", "🧫",
        "Navigate tissue regions, spatial overlays, ROI annotations and review status using a bounded offline canvas.",
        ("Spatial Omics", "Digital Pathology", "Cancer Genomics", "Clinical Biomarkers"),
        "ROI selection, layer opacity, stain comparison, region labelling and annotation review",
    ),
    "flow_gating_canvas": NonChartVisualSpec(
        "flow_gating_canvas", "Flow-Cytometry Gating Canvas", "🧪",
        "Inspect events, define review gates, view parent-child populations and record gating decisions.",
        ("Flow Cytometry", "Immunology", "Cell Phenotyping"),
        "Gate bounds, transform mode, population selection, control overlay and gate-state persistence",
    ),
    "plate_map_editor": NonChartVisualSpec(
        "plate_map_editor", "Interactive Plate Map Editor", "🧬",
        "Assign standards, controls, samples and replicate groups on common laboratory plate formats.",
        ("qPCR", "ELISA", "Wet-Lab Biotechnology", "High-Content Screening", "Experimental Design"),
        "Well assignment, role filters, edge-effect review, replicate selection and template export",
    ),
    "mass_spectrum_inspector": NonChartVisualSpec(
        "mass_spectrum_inspector", "Spectrum & Chromatogram Evidence Inspector", "⚗️",
        "Review peak identities, fragments, integration windows, isotope/adduct evidence and acceptance status.",
        ("Metabolomics", "Proteomics", "Glycomics", "Lipidomics", "Proteogenomics"),
        "Peak selection, fragment evidence, integration status, confidence review and acceptance queue",
    ),
    "sequence_feature_track": NonChartVisualSpec(
        "sequence_feature_track", "Sequence Feature Track", "🧬",
        "Inspect domains, exons, motifs, PTMs, transmembrane regions, disorder, active sites and mutations along a sequence.",
        ("Sequence Analyzer", "Protein Annotation", "CRISPR", "RNA Isoforms", "Protein Design", "Antibody Engineering"),
        "Feature-lane toggles, interval selection, residue/base detail and annotation export",
    ),
    "pedigree_canvas": NonChartVisualSpec(
        "pedigree_canvas", "Pedigree & Segregation Canvas", "👪",
        "Review family structure, affected state, genotype inheritance, carrier status and segregation conflicts.",
        ("Rare Disease", "Family Genetics", "Pharmacogenomics"),
        "Proband selection, genotype layer, phenotype labels and segregation review",
    ),
    "phylogeny_canvas": NonChartVisualSpec(
        "phylogeny_canvas", "Interactive Phylogeny Canvas", "🌳",
        "Explore clades, branch support, metadata rings, root choice and sample search without relying on a static chart.",
        ("Alignment & Phylogeny", "Pathogen Outbreak", "Virology", "One Health", "Metagenomics"),
        "Clade collapse, root selection, metadata colouring, sample search and review notes",
    ),
    "outbreak_map_canvas": NonChartVisualSpec(
        "outbreak_map_canvas", "Geographic Outbreak Review Map", "🗺️",
        "Inspect sample locations, clusters, hosts, dates, AMR alerts and transmission hypotheses on a local map canvas.",
        ("Pathogen Outbreak", "One Health", "Environmental Genomics", "Wastewater Surveillance"),
        "Time window, cluster filter, location selection, transmission review and snapshot export",
    ),
    "pangenome_canvas": NonChartVisualSpec(
        "pangenome_canvas", "Pangenome Variation-Graph Canvas", "🕸️",
        "Inspect sequence nodes, reference/sample paths, bubbles, core/accessory regions and selected graph intervals.",
        ("Pangenome & Variation Graph Studio",),
        "Path selection, node details, graph focus, bubble review and GFA-ready export state",
    ),
    "single_cell_canvas": NonChartVisualSpec(
        "single_cell_canvas", "Single-Cell Selection Canvas", "🔭",
        "Explore cell clusters, batches, conditions, marker states and selected-cell metadata in a rasterized local canvas.",
        ("Single-Cell Heterogeneity", "Cell Atlas", "Trajectory Analysis", "Perturb-seq"),
        "Cluster filter, marker overlay, cell selection, metadata inspection and selected-cell export",
    ),
    "multiomics_canvas": NonChartVisualSpec(
        "multiomics_canvas", "Multi-Omics Relationship Canvas", "🔗",
        "Trace genes, proteins, metabolites and pathways through a column-based evidence and relationship workspace.",
        ("Omics Integration", "Biomarker Discovery", "Proteogenomics"),
        "Entity selection, evidence path, concordance review and cross-omics handoff",
    ),
    "bioprocess_board": NonChartVisualSpec(
        "bioprocess_board", "Live Bioprocess Control Board", "🏭",
        "Review reactor state, sensor health, process phase, alarms, feed events and operator decisions in one control-board layout.",
        ("Bioprocess", "Fermentation", "Instrument Monitoring"),
        "Reactor selection, phase state, alarm acknowledgement, sensor review and operator annotation",
    ),
}


MODULE_NON_CHART_CONTEXTS: dict[str, dict[str, Any]] = {
    "fastq": {
        "title": "FASTQ decision workspace",
        "items": ("Read-quality traffic lights", "Adapter contamination map", "Paired-end sync state", "File-health checklist", "Before/after trim preview", "QC decision card"),
    },
    "variant": {
        "title": "Variant evidence workspace",
        "items": ("Chromosome ideogram", "Consequence badges", "Genotype inspector", "Evidence drawer", "Variant review queue", "ClinVar-style source cards"),
    },
    "transcriptomics": {
        "title": "Transcriptomics design workspace",
        "items": ("Editable sample-group board", "Design-matrix editor", "Contrast builder", "Metadata cards", "Gene detail drawer", "Analysis readiness checklist"),
    },
    "crispr": {
        "title": "CRISPR design workspace",
        "items": ("Guide location track", "Editing window", "Guide alignment", "Off-target mismatch rows", "Amplicon preview", "Validation-primer placement"),
    },
    "admet": {
        "title": "ADMET decision workspace",
        "items": ("Molecule depiction", "Endpoint traffic-light matrix", "Risk badges", "Liability cards", "Applicability-domain indicator", "Recommended modification panel"),
    },
    "antibody": {
        "title": "Antibody engineering workspace",
        "items": ("Heavy/light chain schematic", "CDR ribbon", "Mutation-marked sequence", "Liability badges", "Humanization comparison", "Interface evidence panel"),
    },
    "rare_disease": {
        "title": "Rare-disease interpretation workspace",
        "items": ("Patient phenotype cards", "HPO hierarchy", "Variant evidence matrix", "ACMG checklist", "Reanalysis timeline", "Family segregation review"),
    },
    "clinical_biomarker": {
        "title": "Clinical biomarker review workspace",
        "items": ("CONSORT flow", "Patient swimmer timeline", "Visit timeline", "Adverse-event matrix", "Eligibility board", "Reviewer decision panel"),
    },
    "reference_db": {
        "title": "Reference lifecycle workspace",
        "items": ("Version cards", "Dependency map", "Download-state timeline", "Checksum badge", "Active/pinned/rollback state", "Licence acknowledgement"),
    },
    "background_jobs": {
        "title": "Background execution workspace",
        "items": ("Queue kanban", "Per-stage stepper", "Worker cards", "Resource meters", "Retry history", "Diagnostic drawer", "Artifact cards"),
    },
    "workflow": {
        "title": "Workflow execution workspace",
        "items": ("Drag-and-drop node canvas", "Typed ports", "Live node state", "Failed-node trace", "Step detail drawer", "Dataset flow", "Checkpoint markers"),
    },
    "dataset_registry": {
        "title": "Dataset governance workspace",
        "items": ("Dataset lineage", "Version cards", "Schema comparison", "Quality matrix", "Physical/logical asset view", "Licence and evidence badges"),
    },
    "model_registry": {
        "title": "Model lifecycle workspace",
        "items": ("Lifecycle stepper", "Version comparison cards", "Approval timeline", "Dataset lineage", "Model-card preview", "Deployment status board"),
    },
}


_STATUS_CLASS = {
    "pass": "nc-pass",
    "ready": "nc-pass",
    "active": "nc-pass",
    "review": "nc-review",
    "warning": "nc-review",
    "pending": "nc-review",
    "blocked": "nc-fail",
    "fail": "nc-fail",
    "inactive": "nc-muted",
    "met": "nc-pass",
    "not met": "nc-muted",
    "consistent": "nc-pass",
    "complete": "nc-pass",
    "none": "nc-pass",
}


def _safe(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _inject_css() -> None:
    """Inject non-chart canvas CSS on every Streamlit rerun.

    Streamlit preserves ``st.session_state`` while rebuilding the page DOM. A
    session-level "CSS loaded" flag therefore caused later reruns or module
    navigation to omit this stylesheet, leaving feature lanes and KPI cards as
    concatenated plain text. The stylesheet is intentionally emitted on every
    render so each page owns the styles required by its canvases.
    """
    st.markdown(
        """
<style id="biointel-non-chart-scientific-visuals-v2">
.nc-shell,.nc-shell *{box-sizing:border-box}
.nc-shell{display:block!important;width:100%;min-width:0;overflow:hidden;border:1px solid rgba(120,150,190,.28);border-radius:18px;background:linear-gradient(145deg,rgba(12,24,45,.94),rgba(8,16,31,.96));padding:18px;margin:8px 0 14px;box-shadow:0 10px 30px rgba(0,0,0,.18)}
.nc-title{display:block!important;font-size:1.02rem;font-weight:800;letter-spacing:.01em;margin-bottom:4px;color:#f5f8ff;overflow-wrap:anywhere}.nc-sub{display:block!important;font-size:.82rem;color:#aebbd3;margin-bottom:12px;overflow-wrap:anywhere}
.nc-grid{display:grid!important;width:100%;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:10px;margin-top:12px;align-items:stretch}.nc-card{display:block!important;min-width:0;height:100%;overflow:hidden;overflow-wrap:anywhere;border:1px solid rgba(115,150,195,.28);border-radius:14px;background:rgba(20,35,60,.72);padding:12px;min-height:72px}
.nc-card b{display:block!important;color:#f5f8ff;font-size:.86rem;margin-bottom:5px;overflow-wrap:anywhere}.nc-card span{display:block!important;color:#aebbd3;font-size:.76rem;line-height:1.35;overflow-wrap:anywhere}.nc-kpi{font-size:1.22rem!important;font-weight:800;color:#71e0d5!important}
.nc-badge{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:4px 9px;font-size:.72rem;font-weight:700;margin:2px 4px 2px 0;border:1px solid rgba(255,255,255,.13)}
.nc-pass{background:rgba(28,180,135,.16);color:#75ebc4}.nc-review{background:rgba(244,176,55,.16);color:#ffd176}.nc-fail{background:rgba(235,90,100,.16);color:#ff9aa2}.nc-muted{background:rgba(125,140,165,.14);color:#b8c2d6}
.nc-stepper{display:flex;gap:8px;align-items:flex-start;overflow-x:auto;padding:4px 0 8px}.nc-step{min-width:115px;position:relative;border:1px solid rgba(120,150,190,.25);border-radius:12px;padding:10px;background:rgba(18,32,55,.65)}.nc-step:after{content:'›';position:absolute;right:-9px;top:20px;color:#7f91ad;font-size:1.3rem}.nc-step:last-child:after{display:none}.nc-step small{display:block;color:#8da0be}.nc-step strong{font-size:.78rem;color:#eef4ff}
.nc-matrix{width:100%;border-collapse:separate;border-spacing:4px}.nc-matrix td,.nc-matrix th{padding:7px 9px;border-radius:8px;font-size:.74rem;text-align:left}.nc-matrix th{color:#9fb0c9}.nc-matrix td{background:rgba(24,42,70,.72);color:#dce5f4}
.nc-lane{display:block!important;position:relative;width:100%;height:34px;min-height:34px;border-radius:10px;background:rgba(25,42,68,.78);margin:8px 0;overflow:hidden}.nc-seg{display:block!important;position:absolute;top:8px;height:18px;border-radius:6px;background:linear-gradient(90deg,#32c8c6,#4b83f3);font-size:.62rem;color:white;padding:2px 5px;white-space:nowrap;overflow:hidden}.nc-seg.alt{background:linear-gradient(90deg,#a86bf0,#f06595)}.nc-seg.warn{background:linear-gradient(90deg,#e4973f,#e86868)}
.nc-code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;background:#08111f;border:1px solid rgba(120,150,190,.25);padding:12px;border-radius:12px;color:#dce9ff;overflow:auto;font-size:.74rem;line-height:1.55}
.nc-progress{height:9px;background:rgba(90,110,145,.25);border-radius:99px;overflow:hidden}.nc-progress>i{display:block;height:100%;background:linear-gradient(90deg,#42d7c8,#5a7cf4);border-radius:99px}
.nc-well-grid{display:grid;gap:3px;overflow:auto}.nc-well{aspect-ratio:1;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.52rem;border:1px solid rgba(255,255,255,.16);color:#e7efff;min-width:18px}.nc-well.sample{background:#315b96}.nc-well.control{background:#8e5ec7}.nc-well.standard{background:#2e9b78}.nc-well.blank{background:#4a566c}.nc-well.review{box-shadow:0 0 0 2px #f4b642 inset}
.nc-kanban{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:10px;overflow:auto}.nc-col{background:rgba(15,28,48,.68);border:1px solid rgba(120,150,190,.22);border-radius:13px;padding:10px}.nc-col h5{margin:0 0 8px;color:#dce6f7}.nc-ticket{background:rgba(32,52,82,.82);border-radius:10px;padding:9px;margin:7px 0;color:#e9f1ff;font-size:.72rem}.nc-ticket small{display:block;color:#9dafc7;margin-top:4px}
.nc-svg{width:100%;height:auto;border-radius:14px;background:#091525;border:1px solid rgba(120,150,190,.25)}
.nc-callout{border-left:4px solid #42d7c8;background:rgba(20,40,66,.72);border-radius:0 12px 12px 0;padding:11px 13px;color:#dce7f7;font-size:.8rem;margin:8px 0}
@media(max-width:760px){.nc-kanban{grid-template-columns:repeat(4,210px)}.nc-grid{grid-template-columns:1fr 1fr}.nc-shell{padding:13px}}
</style>
""",
        unsafe_allow_html=True,
    )


def status_badges(items: Iterable[tuple[str, str]]) -> str:
    parts = []
    for label, status in items:
        cls = _STATUS_CLASS.get(str(status).lower(), "nc-muted")
        parts.append(f'<span class="nc-badge {cls}">{_safe(label)} · {_safe(status)}</span>')
    return "".join(parts)


def workflow_stepper(steps: Iterable[tuple[str, str]]) -> str:
    return '<div class="nc-stepper">' + "".join(
        f'<div class="nc-step"><small>{index:02d}</small><strong>{_safe(label)}</strong><div>{status_badges(((status, status),))}</div></div>'
        for index, (label, status) in enumerate(steps, 1)
    ) + "</div>"


def readiness_matrix(rows: Iterable[tuple[str, str, str]]) -> str:
    body = "".join(
        f'<tr><td>{_safe(label)}</td><td>{status_badges(((status, status),))}</td><td>{_safe(action)}</td></tr>'
        for label, status, action in rows
    )
    return f'<table class="nc-matrix"><thead><tr><th>Check</th><th>Status</th><th>Action</th></tr></thead><tbody>{body}</tbody></table>'


def _svg_wrap(content: str, *, viewbox: str = "0 0 900 420", label: str = "Interactive scientific canvas") -> str:
    return f'<svg class="nc-svg" viewBox="{viewbox}" role="img" aria-label="{_safe(label)}" xmlns="http://www.w3.org/2000/svg"><title>{_safe(label)}</title>{content}</svg>'


def _cards(cards: Iterable[tuple[str, str]], *, kpi: bool = False) -> str:
    cls = " nc-kpi" if kpi else ""
    return '<div class="nc-grid">' + "".join(
        f'<div class="nc-card"><b>{_safe(title)}</b><span class="{cls.strip()}">{_safe(text)}</span></div>'
        for title, text in cards
    ) + "</div>"


def _lane(label: str, segments: Iterable[tuple[float, float, str, str]]) -> str:
    segs = "".join(
        f'<span class="nc-seg {_safe(kind)}" style="left:{max(0,min(100,start)):.2f}%;width:{max(1,min(100-start,width)):.2f}%">{_safe(text)}</span>'
        for start, width, text, kind in segments
    )
    return f'<div style="color:#aebbd3;font-size:.72rem;margin-top:7px">{_safe(label)}</div><div class="nc-lane">{segs}</div>'


def _render_genome_track(prefix: str) -> None:
    region = st.text_input("Genomic interval", value="chr7:55,086,000-55,116,000", key=f"{prefix}_interval")
    tracks = st.multiselect("Visible tracks", ["Gene model", "Variants", "Coverage", "Peaks", "Splice junctions"], default=["Gene model", "Variants", "Coverage"], key=f"{prefix}_tracks")
    selected = st.selectbox("Selected feature", ["EGFR exon 18", "Variant rs121434568", "Enhancer peak P4", "Splice junction J2"], key=f"{prefix}_feature")
    lanes = []
    if "Gene model" in tracks:
        lanes.append(_lane("Gene model", [(6, 18, "EGFR exon 18", ""), (28, 12, "exon 19", ""), (47, 15, "exon 20", "alt"), (68, 20, "exon 21", "")]))
    if "Variants" in tracks:
        lanes.append(_lane("Variants", [(15, 2, "V1", "warn"), (36, 2, "V2", "alt"), (55, 2, "V3", "warn"), (79, 2, "V4", "")]))
    if "Coverage" in tracks:
        lanes.append(_lane("Coverage", [(2, 8, "42×", ""), (11, 16, "71×", ""), (29, 20, "55×", "alt"), (51, 42, "63×", "")]))
    if "Peaks" in tracks:
        lanes.append(_lane("Peaks", [(12, 13, "P1", "alt"), (44, 8, "P2", "warn"), (72, 17, "P3", "alt")]))
    if "Splice junctions" in tracks:
        lanes.append(_lane("Junctions", [(20, 22, "J1", ""), (50, 28, "J2", "alt")]))
    st.markdown(f'<div class="nc-shell"><div class="nc-title">{_safe(region)}</div><div class="nc-sub">Coordinate-aware local track canvas · selected: {_safe(selected)}</div>{"".join(lanes)}{_cards((("Selected evidence", selected),("Reference build", "GRCh38"),("Tracks visible", str(len(tracks))),("Export", "BED/VCF interval bundle")), kpi=False)}</div>', unsafe_allow_html=True)


@lru_cache(maxsize=128)
def _molecular_svg(chain: str, residue: int) -> str:
    rng = np.random.default_rng(115 + residue)
    points = []
    x, y = 110.0, 210.0
    for index in range(55):
        x += float(rng.normal(11, 5)); y += float(rng.normal(0, 22))
        x = max(55, min(840, x)); y = max(55, min(365, y))
        points.append((x, y))
    path = " ".join(("M" if i == 0 else "L") + f" {px:.1f} {py:.1f}" for i, (px, py) in enumerate(points))
    atoms = "".join(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{7 if i==residue%55 else 3.5}" fill="{"#ffca62" if i==residue%55 else "#50c8d4"}" opacity=".88"><title>{chain}{i+1}</title></circle>' for i,(px,py) in enumerate(points))
    ligand = '<polygon points="520,180 545,195 538,224 510,230 493,205" fill="#ef6f9a" stroke="#ffd3e1" stroke-width="2"><title>Ligand LIG</title></polygon>'
    return _svg_wrap(f'<path d="{path}" fill="none" stroke="#6b8cff" stroke-width="4" opacity=".65"/>{atoms}{ligand}<text x="28" y="34" fill="#dbe8ff" font-size="18">Chain {chain} · residue {residue}</text>')


def _render_molecular_scene(prefix: str) -> None:
    c1, c2, c3 = st.columns(3)
    chain = c1.selectbox("Chain", ["A", "B", "L"], key=f"{prefix}_chain")
    residue = c2.slider("Residue", 1, 420, 145, key=f"{prefix}_residue")
    representation = c3.selectbox("Scene preset", ["Cartoon + ligand", "Pocket review", "Mutation review", "Contact review"], key=f"{prefix}_preset")
    st.markdown(f'<div class="nc-shell"><div class="nc-title">Offline molecular scene</div><div class="nc-sub">{_safe(representation)} · selected {chain}{residue}</div>{_molecular_svg(chain,residue)}{_cards((("Selected residue",f"{chain}{residue}"),("Neighbour contacts","8 residues"),("Ligand distance","3.2 Å"),("Mutation status","Review required")))}</div>', unsafe_allow_html=True)


@lru_cache(maxsize=32)
def _synthetic_micro_image(seed: int, threshold: float, opacity: float, pathology: bool = False) -> Image.Image:
    rng = np.random.default_rng(seed)
    h, w = (520, 840)
    base = np.zeros((h, w, 3), dtype=np.uint8)
    if pathology:
        base[:] = [38, 20, 45]
        image = Image.fromarray(base)
        draw = ImageDraw.Draw(image, "RGBA")
        for _ in range(230):
            cx, cy = int(rng.integers(0, w)), int(rng.integers(0, h))
            rx, ry = int(rng.integers(6, 40)), int(rng.integers(5, 28))
            color = tuple(int(v) for v in rng.choice([[180,85,145],[105,120,185],[205,120,135],[130,75,155]])) + (110,)
            draw.ellipse((cx-rx,cy-ry,cx+rx,cy+ry), fill=color)
        for idx in range(5):
            x1,y1 = int(rng.integers(40,w-180)), int(rng.integers(40,h-160))
            draw.rounded_rectangle((x1,y1,x1+int(rng.integers(80,180)),y1+int(rng.integers(60,150))), radius=16, outline=(65,230,205,220), width=4)
            draw.text((x1+8,y1+8),f"ROI {idx+1}",fill=(220,255,250,255))
        return image
    image = Image.new("RGB", (w, h), (5, 16, 31))
    draw = ImageDraw.Draw(image, "RGBA")
    objects = []
    for idx in range(135):
        cx, cy = int(rng.integers(15, w-15)), int(rng.integers(15, h-15))
        r = int(rng.integers(5, 15))
        intensity = float(rng.uniform(0.25, 1.0))
        draw.ellipse((cx-r,cy-r,cx+r,cy+r), fill=(35, int(120+110*intensity), 210, 160))
        if intensity >= threshold:
            objects.append((cx,cy,r,idx))
    overlay = Image.new("RGBA", image.size, (0,0,0,0))
    od = ImageDraw.Draw(overlay, "RGBA")
    alpha = int(255*opacity)
    for cx,cy,r,idx in objects:
        od.ellipse((cx-r-2,cy-r-2,cx+r+2,cy+r+2), outline=(255,205,75,alpha), width=2)
        if idx % 11 == 0:
            od.text((cx+r+2,cy-r),str(idx+1),fill=(255,240,190,alpha))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _render_microscopy_editor(prefix: str) -> None:
    c1, c2, c3 = st.columns(3)
    threshold = c1.slider("Mask threshold", 0.20, 0.90, 0.58, 0.01, key=f"{prefix}_threshold")
    opacity = c2.slider("Mask opacity", 0.10, 1.00, 0.75, 0.05, key=f"{prefix}_opacity")
    channel = c3.selectbox("Channel", ["Composite", "Nuclei", "Cytoplasm", "Marker"], key=f"{prefix}_channel")
    image = _synthetic_micro_image(115, threshold, opacity)
    st.image(image, caption=f"{channel} · segmentation overlay · bounded preview", width="stretch")
    selected = st.multiselect("Objects marked for correction", [f"Object {i}" for i in range(1, 13)], key=f"{prefix}_objects")
    st.markdown(f'<div class="nc-shell">{_cards((("Detected objects",str(int(80+threshold*70))),("Selected corrections",str(len(selected))),("Channel",channel),("Export state","Mask + audit JSON")),kpi=True)}{readiness_matrix((("Image bounds","Pass","No action"),("Mask continuity","Review","Inspect edge objects"),("Scale calibration","Pending","Enter µm/pixel"),("Correction audit","Pass","Changes tracked")))}</div>', unsafe_allow_html=True)


def _render_pathology_canvas(prefix: str) -> None:
    c1,c2,c3 = st.columns(3)
    opacity = c1.slider("Spatial overlay opacity",0.0,1.0,.55,.05,key=f"{prefix}_opacity")
    stain = c2.selectbox("Stain/layer",["H&E","Expression","Cell density","Segmentation"],key=f"{prefix}_stain")
    roi = c3.selectbox("Active ROI",["ROI 1","ROI 2","ROI 3","ROI 4","ROI 5"],key=f"{prefix}_roi")
    image = _synthetic_micro_image(116, .5, opacity, pathology=True)
    st.image(image, caption=f"Bounded pathology canvas · {stain} · {roi}", width="stretch")
    st.markdown(f'<div class="nc-shell">{_cards((("Canvas mode","Tiled preview"),("Active layer",stain),("Selected region",roi),("Native WSI","OpenSlide adapter required")))}{workflow_stepper((("Load slide","pass"),("Register layers","pass"),("Draw ROI","active"),("Review cells","pending"),("Export region","pending")))}</div>', unsafe_allow_html=True)


@lru_cache(maxsize=64)
def _flow_canvas_image(seed: int, x_gate: float, y_gate: float) -> tuple[Image.Image, float]:
    rng = np.random.default_rng(seed)
    w,h = 760,520
    image = Image.new("RGB",(w,h),(7,18,34)); draw = ImageDraw.Draw(image,"RGBA")
    pts=[]
    for _ in range(2500):
        group=int(rng.choice([0,1,2],p=[.55,.3,.15]))
        centers=[(.35,.4),(.66,.66),(.72,.3)]
        sx,sy=centers[group]
        x=float(np.clip(rng.normal(sx,.09),.02,.98)); y=float(np.clip(rng.normal(sy,.09),.02,.98))
        pts.append((x,y)); draw.ellipse((x*w-1,y*h-1,x*w+1,y*h+1),fill=(80,185,230,70))
    gx=int(x_gate*w); gy=int(y_gate*h)
    draw.rectangle((gx,gy,w,h),outline=(255,195,70,255),width=4)
    inside=sum(1 for x,y in pts if x>=x_gate and y>=y_gate)/len(pts)
    return image,inside


def _render_flow_gating(prefix: str) -> None:
    c1,c2,c3=st.columns(3)
    xg=c1.slider("FSC gate",0.05,.95,.55,.01,key=f"{prefix}_xg")
    yg=c2.slider("SSC gate",0.05,.95,.45,.01,key=f"{prefix}_yg")
    transform=c3.selectbox("Transform",["Linear","Logicle","Biexponential"],key=f"{prefix}_transform")
    image,inside=_flow_canvas_image(117,xg,yg)
    st.image(image,caption=f"Event canvas · gate population {inside:.1%} · {transform}",width="stretch")
    st.markdown(f'<div class="nc-shell">{_cards((("Parent population","All events"),("Gate population",f"{inside:.1%}"),("Transform",transform),("Control overlay","FMO available")),kpi=False)}{workflow_stepper((("Compensation","pass"),("Transform","pass"),("Parent gate","active"),("Child gates","pending"),("Export template","pending")))}</div>',unsafe_allow_html=True)


def _plate_grid(rows: int, cols: int, selected_role: str) -> str:
    row_labels=[chr(65+i) for i in range(rows)]
    cells=[]
    for r,row in enumerate(row_labels):
        for c in range(1,cols+1):
            role="blank" if c==1 else "standard" if c in {2,3} else "control" if c in {cols-1,cols} else "sample"
            review=" review" if (r in {0,rows-1} and c%5==0) else ""
            cells.append(f'<div class="nc-well {role}{review}" title="{row}{c} · {role}">{row}{c}</div>')
    return f'<div class="nc-well-grid" style="grid-template-columns:repeat({cols},minmax(18px,1fr))">{"".join(cells)}</div>'


def _render_plate_map(prefix: str) -> None:
    c1,c2,c3=st.columns(3)
    fmt=c1.selectbox("Plate",["96 wells","384 wells"],key=f"{prefix}_plate")
    role=c2.selectbox("Assignment brush",["Sample","Standard","Control","Blank"],key=f"{prefix}_role")
    replicate=c3.selectbox("Replicate group",["R1","R2","R3","None"],key=f"{prefix}_rep")
    rows,cols=(8,12) if fmt.startswith("96") else (16,24)
    grid=_plate_grid(rows,cols,role)
    st.markdown(f'<div class="nc-shell"><div class="nc-title">{fmt} layout</div><div class="nc-sub">Brush: {_safe(role)} · replicate: {_safe(replicate)}</div>{grid}{status_badges((("Edge review","review"),("Controls distributed","pass"),("Replicate adjacency","pass"),("Missing wells","pass")))}</div>',unsafe_allow_html=True)


def _render_mass_spectrum(prefix: str) -> None:
    rng=np.random.default_rng(118)
    peaks=pd.DataFrame({"mz":np.sort(rng.uniform(80,950,34)),"intensity":rng.uniform(.05,1.0,34),"annotation":[f"frag{i+1}" for i in range(34)]})
    selected=st.selectbox("Selected peak",peaks["annotation"].tolist(),key=f"{prefix}_peak")
    row=peaks.loc[peaks["annotation"]==selected].iloc[0]
    sticks="".join(f'<line x1="{70+(r.mz-80)/870*760:.1f}" y1="360" x2="{70+(r.mz-80)/870*760:.1f}" y2="{360-r.intensity*270:.1f}" stroke="{"#ffcc6a" if r.annotation==selected else "#5b8ef0"}" stroke-width="{5 if r.annotation==selected else 2}"><title>{r.annotation} · m/z {r.mz:.3f}</title></line>' for r in peaks.itertuples())
    svg=_svg_wrap(f'<line x1="60" y1="360" x2="850" y2="360" stroke="#657792"/>{sticks}<text x="34" y="30" fill="#dce8ff" font-size="18">MS/MS fragment evidence</text>')
    evidence=pd.DataFrame({"Evidence":["Mass error","Isotope fit","Library match","Blank ratio","QC CV"],"Value":["2.1 ppm","0.94","0.89","8.2×","7.1%"],"Status":["Pass","Pass","Review","Pass","Pass"]})
    st.markdown(f'<div class="nc-shell">{svg}{_cards((("Peak",selected),("m/z",f"{row.mz:.4f}"),("Relative intensity",f"{row.intensity:.2f}"),("Decision","Review fragmentation")),kpi=False)}</div>',unsafe_allow_html=True)
    st.dataframe(evidence,hide_index=True,width="stretch")


def _render_sequence_track(prefix: str) -> None:
    length=st.slider("Sequence length",120,1800,620,10,key=f"{prefix}_length")
    selection=st.slider("Selected interval",1,length,(135,min(length,225)),key=f"{prefix}_interval")
    lanes=[
        _lane("Domains",[(5,22,"Kinase domain",""),(42,18,"Regulatory","alt"),(71,20,"Interaction","" )]),
        _lane("Topology",[(2,7,"Signal","warn"),(32,4,"TM1","alt"),(62,4,"TM2","alt")]),
        _lane("Variants",[(18,2,"V1","warn"),(53,2,"V2","warn"),(84,2,"V3","alt")]),
        _lane("PTMs",[(25,3,"P",""),(47,3,"Ub","alt"),(74,3,"Ac","warn")]),
    ]
    st.markdown(f'<div class="nc-shell"><div class="nc-title">Residue/base feature track · 1–{length}</div><div class="nc-sub">Selected {selection[0]}–{selection[1]}</div>{"".join(lanes)}{_cards((("Selection length",str(selection[1]-selection[0]+1)),("Active features","12"),("Conservation","High"),("Export","BED/GFF/feature JSON")))}</div>',unsafe_allow_html=True)


def _render_pedigree(prefix: str) -> None:
    layer=st.selectbox("Pedigree layer",["Affected status","Genotype","Carrier state","Phenotype burden"],key=f"{prefix}_layer")
    proband=st.selectbox("Proband",["III-2","III-1"],key=f"{prefix}_proband")
    nodes=[("I-1",130,70,"M","0/1",False),("I-2",250,70,"F","0/0",False),("II-1",190,190,"F","0/1",False),("II-2",520,190,"M","0/1",False),("III-1",300,330,"F","0/0",False),("III-2",430,330,"M","1/1",True)]
    edges=[((130,70),(190,190)),((250,70),(190,190)),((190,190),(300,330)),((520,190),(300,330)),((190,190),(430,330)),((520,190),(430,330))]
    content="".join(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="#6c7f9c" stroke-width="3"/>' for a,b in edges)
    for ident,x,y,sex,geno,affected in nodes:
        shape=f'<rect x="{x-18}" y="{y-18}" width="36" height="36" rx="4"' if sex=="M" else f'<circle cx="{x}" cy="{y}" r="18"'
        end="/>"
        content+=f'{shape} fill="{"#f06b7f" if affected else "#172a48"}" stroke="{"#ffd166" if ident==proband else "#dce8ff"}" stroke-width="4"{end}<text x="{x}" y="{y+42}" text-anchor="middle" fill="#dce8ff" font-size="13">{ident} · {geno}</text>'
    svg=_svg_wrap(content,"0 0 700 420")
    st.markdown(f'<div class="nc-shell"><div class="nc-title">Pedigree and segregation · {_safe(layer)}</div><div class="nc-sub">Proband: {_safe(proband)}</div>{svg}{readiness_matrix((("Family structure","Pass","No action"),("Genotype completeness","Pass","No action"),("Segregation","Review","Inspect III-2"),("Phenotype coverage","Pending","Add HPO terms")))}</div>',unsafe_allow_html=True)


def _render_phylogeny(prefix: str) -> None:
    layout=st.selectbox("Tree layout",["Rectangular","Radial","Time scaled"],key=f"{prefix}_layout")
    root=st.selectbox("Root/outgroup",["Auto","Sample A","Sample H"],key=f"{prefix}_root")
    search=st.text_input("Find sample",value="Sample F",key=f"{prefix}_search")
    # deterministic rectangular dendrogram SVG
    ys=[55,95,145,185,245,285,335,375]
    content='<text x="28" y="30" fill="#dce8ff" font-size="18">Phylogenetic review tree</text>'
    for idx,y in enumerate(ys):
        content+=f'<line x1="640" y1="{y}" x2="820" y2="{y}" stroke="#5a8af0" stroke-width="3"/><text x="830" y="{y+5}" fill="{"#ffd166" if search.lower().endswith(chr(97+idx)) else "#dce8ff"}" font-size="13">Sample {chr(65+idx)}</text>'
    for x,y1,y2 in [(540,55,95),(540,145,185),(540,245,285),(540,335,375),(400,75,165),(400,265,355),(260,120,310)]:
        content+=f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" stroke="#8292ab" stroke-width="3"/><line x1="{x}" y1="{(y1+y2)/2}" x2="{x+140}" y2="{(y1+y2)/2}" stroke="#8292ab" stroke-width="3"/>'
    svg=_svg_wrap(content)
    st.markdown(f'<div class="nc-shell"><div class="nc-title">{_safe(layout)} tree · root {_safe(root)}</div><div class="nc-sub">Search highlight: {_safe(search)}</div>{svg}{status_badges((("Bootstrap metadata","pass"),("Date metadata","review"),("Outgroup","active"),("Recombination screen","pending")))}</div>',unsafe_allow_html=True)


def _render_outbreak_map(prefix: str) -> None:
    cluster=st.multiselect("Clusters",["C1","C2","C3","C4"],default=["C1","C2","C3","C4"],key=f"{prefix}_clusters")
    day=st.slider("Timeline day",1,120,72,key=f"{prefix}_day")
    host=st.selectbox("Host/source",["All","Human","Animal","Wastewater"],key=f"{prefix}_host")
    points=[(150,145,"C1"),(250,210,"C2"),(365,120,"C1"),(470,260,"C3"),(610,170,"C4"),(720,280,"C2"),(530,95,"C3")]
    colors={"C1":"#4bd2c7","C2":"#6b8df5","C3":"#ea6fa7","C4":"#f0b85a"}
    content='<path d="M80,90 C180,35 275,75 340,55 C445,25 530,85 620,72 C720,60 815,125 810,220 C800,320 700,370 610,345 C515,320 430,380 335,342 C245,310 130,335 82,250 C55,205 50,135 80,90 Z" fill="#142946" stroke="#58739d" stroke-width="3"/>'
    for x,y,c in points:
        if c in cluster:
            content+=f'<circle cx="{x}" cy="{y}" r="15" fill="{colors[c]}" opacity=".9"><title>{c} · day {day}</title></circle>'
    for a,b in zip(points[:-1],points[1:]):
        if a[2] in cluster and b[2] in cluster:
            content+=f'<path d="M {a[0]} {a[1]} Q {(a[0]+b[0])/2} {min(a[1],b[1])-55} {b[0]} {b[1]}" fill="none" stroke="#d6e4ff" stroke-width="2" opacity=".35"/>'
    svg=_svg_wrap(content,"0 0 900 420")
    st.markdown(f'<div class="nc-shell"><div class="nc-title">Outbreak review map · day {day}</div><div class="nc-sub">Source filter: {_safe(host)} · clusters: {_safe(", ".join(cluster) or "none")}</div>{svg}{_cards((("Locations","7"),("Active clusters",str(len(cluster))),("AMR alerts","2 review"),("Transmission links","6 hypotheses")))}</div>',unsafe_allow_html=True)


def _render_pangenome(prefix: str) -> None:
    path=st.selectbox("Highlighted path",["Reference","Sample A","Sample B","Sample C"],key=f"{prefix}_path")
    focus=st.selectbox("Graph focus",["Core path","Bubble 12","Accessory island 4","SV path 7"],key=f"{prefix}_focus")
    nodes=[]
    for i in range(18):
        x=70+i*44; y=210+45*math.sin(i*.8)
        nodes.append((x,y))
    content=""
    for i,(x,y) in enumerate(nodes[:-1]):
        nx,ny=nodes[i+1]; content+=f'<line x1="{x}" y1="{y}" x2="{nx}" y2="{ny}" stroke="#5b83ef" stroke-width="5"/>'
    for i,(x,y) in enumerate(nodes):
        content+=f'<circle cx="{x}" cy="{y}" r="{12 if i in {6,7,8} else 8}" fill="{"#f1b34d" if i in {6,7,8} else "#43c9c2"}"/><text x="{x}" y="{y-16}" text-anchor="middle" fill="#aebbd3" font-size="10">n{i+1}</text>'
    content+='<path d="M 334 165 Q 385 75 430 166" fill="none" stroke="#e16fa2" stroke-width="5"/><path d="M 555 170 Q 610 320 675 173" fill="none" stroke="#a96bea" stroke-width="5"/>'
    svg=_svg_wrap(content)
    st.markdown(f'<div class="nc-shell"><div class="nc-title">Pangenome graph · {_safe(path)}</div><div class="nc-sub">Focus: {_safe(focus)}</div>{svg}{status_badges((("Graph integrity","pass"),("Reference path","active"),("Bubble review","review"),("Annotation coverage","pending")))}</div>',unsafe_allow_html=True)


@lru_cache(maxsize=64)
def _single_cell_image(seed: int, cluster: str, marker: str) -> tuple[Image.Image,int]:
    rng=np.random.default_rng(seed); w,h=780,520
    image=Image.new("RGB",(w,h),(6,17,32)); draw=ImageDraw.Draw(image,"RGBA")
    centers={"C1":(220,190),"C2":(510,180),"C3":(340,365),"C4":(620,360)}
    colors={"C1":(60,205,195,150),"C2":(100,135,245,150),"C3":(225,100,155,150),"C4":(238,178,75,150)}
    selected_count=0
    for name,(cx,cy) in centers.items():
        for _ in range(420):
            x=int(rng.normal(cx,65)); y=int(rng.normal(cy,48))
            if 0<x<w and 0<y<h:
                alpha=230 if cluster in {"All",name} else 35
                c=(*colors[name][:3],alpha)
                r=3 if marker=="None" else int(2+rng.uniform(0,3))
                draw.ellipse((x-r,y-r,x+r,y+r),fill=c)
                if cluster in {"All",name}: selected_count+=1
    return image,selected_count


def _render_single_cell(prefix: str) -> None:
    c1,c2,c3=st.columns(3)
    cluster=c1.selectbox("Cluster",["All","C1","C2","C3","C4"],key=f"{prefix}_cluster")
    marker=c2.selectbox("Marker overlay",["None","CD3D","MS4A1","LYZ","MKI67"],key=f"{prefix}_marker")
    condition=c3.selectbox("Condition",["All","Control","Treated"],key=f"{prefix}_condition")
    image,count=_single_cell_image(121,cluster,marker)
    st.image(image,caption=f"Rasterized cell selection canvas · {count:,} visible cells",width="stretch")
    st.markdown(f'<div class="nc-shell">{_cards((("Visible cells",f"{count:,}"),("Cluster",cluster),("Marker",marker),("Condition",condition)),kpi=True)}{readiness_matrix((("Cell metadata","Pass","No action"),("Batch labels","Pass","No action"),("Doublet calls","Review","Inspect C4"),("Reference labels","Pending","Choose atlas")))}</div>',unsafe_allow_html=True)


def _render_multiomics(prefix: str) -> None:
    focus=st.selectbox("Focus entity",["EGFR","TP53","BRCA1","IL6"],key=f"{prefix}_entity")
    evidence=st.multiselect("Evidence layers",["Transcript","Protein","Metabolite","Pathway","Phenotype"],default=["Transcript","Protein","Metabolite","Pathway"],key=f"{prefix}_layers")
    cols=[("Gene",[focus,"MYC","STAT3"]),("Protein",[f"{focus} protein","AKT1","MAPK1"]),("Metabolite",["Lactate","ATP","Glutamine"]),("Pathway",["RTK signalling","Cell cycle","Glycolysis"])]
    x_positions=[120,330,540,750]
    content=''
    for x,(label,items) in zip(x_positions,cols):
        content+=f'<text x="{x}" y="45" text-anchor="middle" fill="#cfe0fa" font-size="16">{label}</text>'
        for j,item in enumerate(items):
            y=105+j*105
            content+=f'<rect x="{x-70}" y="{y-25}" width="140" height="50" rx="14" fill="#173354" stroke="#5d87c9"/><text x="{x}" y="{y+5}" text-anchor="middle" fill="#edf5ff" font-size="12">{_safe(item)}</text>'
    for a,b in zip(x_positions[:-1],x_positions[1:]):
        for j in range(3):
            content+=f'<path d="M {a+70} {105+j*105} C {a+120} {105+j*105} {b-120} {105+((j+1)%3)*105} {b-70} {105+((j+1)%3)*105}" fill="none" stroke="#47c9bd" stroke-width="3" opacity=".55"/>'
    svg=_svg_wrap(content,"0 0 900 420")
    st.markdown(f'<div class="nc-shell"><div class="nc-title">Cross-omics evidence path · {_safe(focus)}</div><div class="nc-sub">Layers: {_safe(", ".join(evidence))}</div>{svg}{_cards((("Concordant links","7"),("Conflicting links","2 review"),("Evidence sources","4 layers"),("Export","Relationship manifest")))}</div>',unsafe_allow_html=True)


@lru_cache(maxsize=16)
def _reactor_svg(phase: str, alarm: bool) -> str:
    fill="#e77272" if alarm else "#45d1c0"
    return _svg_wrap(f'''
<rect x="300" y="85" width="300" height="270" rx="60" fill="#102b49" stroke="#8da7ca" stroke-width="6"/>
<path d="M 325 255 Q 450 180 575 255 L 575 330 L 325 330 Z" fill="{fill}" opacity=".65"/>
<line x1="450" y1="40" x2="450" y2="190" stroke="#b7c8df" stroke-width="10"/><path d="M 400 190 L 500 190 M 415 215 L 485 215" stroke="#b7c8df" stroke-width="8"/>
<rect x="665" y="105" width="170" height="245" rx="20" fill="#132942" stroke="#526f98"/>
<text x="750" y="145" text-anchor="middle" fill="#dce8ff" font-size="18">{_safe(phase)}</text>
<text x="750" y="195" text-anchor="middle" fill="#8fe5d3" font-size="16">pH 7.08</text>
<text x="750" y="235" text-anchor="middle" fill="#8fe5d3" font-size="16">DO 38%</text>
<text x="750" y="275" text-anchor="middle" fill="#8fe5d3" font-size="16">36.9 °C</text>
<text x="750" y="315" text-anchor="middle" fill="{fill}" font-size="15">{"ALARM" if alarm else "STABLE"}</text>
''')


def _render_bioprocess(prefix: str) -> None:
    c1,c2,c3=st.columns(3)
    reactor=c1.selectbox("Reactor",["BR-01","BR-02","BR-03"],key=f"{prefix}_reactor")
    phase=c2.selectbox("Process phase",["Inoculation","Growth","Feed","Production","Harvest"],index=2,key=f"{prefix}_phase")
    alarm=c3.toggle("Simulate alarm",value=False,key=f"{prefix}_alarm")
    st.markdown(f'<div class="nc-shell"><div class="nc-title">{_safe(reactor)} control board</div><div class="nc-sub">Phase {_safe(phase)} · operator-reviewed local dashboard</div>{_reactor_svg(phase,alarm)}{_cards((("Agitation","420 rpm"),("Feed rate","1.8 L/h"),("OUR","82 mmol/L/h"),("Endpoint ETA","6 h 20 m")),kpi=True)}{status_badges((("pH loop","pass"),("DO loop","review" if alarm else "pass"),("Temperature","pass"),("Sensor health","pass")))}</div>',unsafe_allow_html=True)


_RENDERERS: dict[str, Callable[[str], None]] = {
    "genome_track": _render_genome_track,
    "molecular_scene": _render_molecular_scene,
    "microscopy_editor": _render_microscopy_editor,
    "pathology_canvas": _render_pathology_canvas,
    "flow_gating_canvas": _render_flow_gating,
    "plate_map_editor": _render_plate_map,
    "mass_spectrum_inspector": _render_mass_spectrum,
    "sequence_feature_track": _render_sequence_track,
    "pedigree_canvas": _render_pedigree,
    "phylogeny_canvas": _render_phylogeny,
    "outbreak_map_canvas": _render_outbreak_map,
    "pangenome_canvas": _render_pangenome,
    "single_cell_canvas": _render_single_cell,
    "multiomics_canvas": _render_multiomics,
    "bioprocess_board": _render_bioprocess,
}


def render_non_chart_visual(key: str, *, key_prefix: str | None = None, expanded: bool = False, heading: bool = True) -> None:
    if key not in NON_CHART_VISUAL_CATALOG:
        st.error(f"Unknown non-chart scientific visual: {key}")
        return
    _inject_css()
    spec=NON_CHART_VISUAL_CATALOG[key]
    prefix=key_prefix or f"nc_{key}"
    if heading:
        st.markdown(f"#### {spec.icon} {spec.title}")
        st.caption(spec.description)
    open_state=st.toggle("Open interactive non-chart workspace",value=expanded,key=f"{prefix}_open")
    if not open_state:
        st.markdown(f'<div class="nc-shell">{_cards((("Connected modules",str(len(spec.modules))),("Interaction",spec.interaction),("Rendering","Lazy / selected only"),("Evidence boundary","Review support")))}</div>',unsafe_allow_html=True)
        return
    try:
        _RENDERERS[key](prefix)
        with st.expander("Review note and export visual state", expanded=False):
            note = st.text_area("Reviewer note", key=f"{prefix}_review_note", placeholder="Record the selected interval, object, gate, ROI or scientific concern.")
            manifest = {
                "schema": "biointel.non-chart-visual-state.v1",
                "version": "15.6.0",
                "visual_key": key,
                "visual_title": spec.title,
                "connected_modules": list(spec.modules),
                "interaction": spec.interaction,
                "review_note": note,
                "evidence_boundary": "Scientific review support; specialist validation remains required where applicable.",
            }
            st.download_button(
                "Download visual state manifest",
                data=json.dumps(manifest, indent=2, ensure_ascii=False),
                file_name=f"biointel_{key}_visual_state.json",
                mime="application/json",
                key=f"{prefix}_state_download",
            )
    except Exception as exc:
        error_id=hashlib.sha256(f"{key}:{type(exc).__name__}:{exc}".encode("utf-8",errors="ignore")).hexdigest()[:12].upper()
        st.error(f"The workspace could not render safely. Error ID: NC-{error_id}")
        with st.expander("Diagnostic details"):
            st.code(f"viewer={key}\nerror={type(exc).__name__}: {exc}")


def _generic_module_panel(context: str, prefix: str) -> None:
    config=MODULE_NON_CHART_CONTEXTS[context]
    st.markdown(f'<div class="nc-shell"><div class="nc-title">{_safe(config["title"])}</div><div class="nc-sub">Decision-oriented module visuals; no decorative graph dependency.</div>{_cards(tuple((item,"Available in this workspace") for item in config["items"]))}{workflow_stepper((("Input","pass"),("Validate","pass"),("Configure","active"),("Review","pending"),("Approve/export","pending")))}</div>',unsafe_allow_html=True)


def _fastq_panel(prefix: str) -> None:
    st.markdown(f'<div class="nc-shell"><div class="nc-title">FASTQ quality decision board</div>{status_badges((("Read quality","pass"),("Adapters","review"),("Paired-end sync","pass"),("Contamination","review")))}{readiness_matrix((("FASTQ structure","Pass","No action"),("Median Q score","Pass","No action"),("Adapter burden","Review","Trim 3′ adapters"),("K-mer contamination","Review","Inspect top sequences"),("Paired reads","Pass","No action")))}{_cards((("Before trimming","12.4M reads · Q30 87%"),("After trimming","11.9M reads · Q30 94%"),("Decision","Proceed after adapter trim"),("Export","QC manifest + failure rows")))}</div>',unsafe_allow_html=True)


def _variant_panel(prefix: str) -> None:
    ideogram=''.join(f'<rect x="{25+i*35}" y="70" width="24" height="{220-(i%4)*20}" rx="10" fill="#1d3d63" stroke="#5576a4"/><circle cx="{37+i*35}" cy="{110+(i*27)%140}" r="5" fill="{"#ef6d7e" if i%5==0 else "#51cfc3"}"/>' for i in range(23))
    svg=_svg_wrap(f'<text x="28" y="35" fill="#dce8ff" font-size="18">Chromosome review ideogram</text>{ideogram}',"0 0 900 340")
    st.markdown(f'<div class="nc-shell">{svg}{status_badges((("Pathogenic","2"),("Likely pathogenic","5"),("VUS","18"),("Benign","64")))}{readiness_matrix((("Genome build","Pass","GRCh38"),("Reference alleles","Pass","No action"),("Genotype quality","Review","6 low-GQ calls"),("Evidence sources","Pass","ClinVar snapshot"),("Reviewer queue","Pending","25 records")))}</div>',unsafe_allow_html=True)


def _transcriptomics_panel(prefix: str) -> None:
    samples=pd.DataFrame({"sample":["CTRL_1","CTRL_2","TRT_1","TRT_2"],"group":["Control","Control","Treatment","Treatment"],"batch":["B1","B2","B1","B2"],"include":[True,True,True,True]})
    edited=st.data_editor(samples,hide_index=True,width="stretch",key=f"{prefix}_design")
    groups=edited["group"].astype(str).unique().tolist() if not edited.empty else []
    c1,c2=st.columns(2)
    reference=c1.selectbox("Reference group",groups or ["Control"],key=f"{prefix}_ref")
    contrast=c2.selectbox("Contrast",[f"{g} vs {reference}" for g in groups if g!=reference] or ["Treatment vs Control"],key=f"{prefix}_contrast")
    included = int(edited["include"].sum()) if "include" in edited else len(edited)
    cards = _cards((("Design formula", "~ batch + group"), ("Reference", reference), ("Contrast", contrast), ("Samples included", str(included))))
    matrix = readiness_matrix((("Group assignment", "Pass", "No action"), ("Batch balance", "Pass", "No action"), ("Replicates", "Pass", "2 per group"), ("Covariates", "Review", "Add sex/age if relevant"), ("Contrast", "Pass", contrast)))
    st.markdown(f'<div class="nc-shell">{cards}{matrix}</div>', unsafe_allow_html=True)


def _crispr_panel(prefix: str) -> None:
    guide="GACTGACCTGAGGCTACGTT"
    target="GACTGACCTGAGGCTACGCT"
    marks=''.join('|' if a==b else '×' for a,b in zip(guide,target))
    editing=''.join('<span style="background:#e8b64a;color:#111;padding:2px 1px">'+c+'</span>' if 4<=i<=8 else c for i,c in enumerate(guide))
    st.markdown(f'<div class="nc-shell"><div class="nc-title">Guide, editing window and amplicon review</div><div class="nc-code">Guide&nbsp;&nbsp; {guide}<br>Target&nbsp; {target}<br>Match&nbsp;&nbsp; {marks}<br><br>Editing window&nbsp; {editing}</div>{_lane("Amplicon",[(8,16,"Forward primer",""),(37,24,"Editing region","warn"),(76,16,"Reverse primer","alt")])}{readiness_matrix((("PAM compatibility","Pass","NGG"),("On-target score","Pass","0.81"),("Off-target burden","Review","3 candidates"),("Population variants","Pending","Upload VCF"),("Validation primers","Pass","Amplicon 428 bp")))}</div>',unsafe_allow_html=True)


def _admet_panel(prefix: str) -> None:
    endpoints=[("Absorption","Ready","High"),("Solubility","Review","Moderate"),("CYP risk","Blocked","CYP3A4 alert"),("hERG","Review","Rule-based"),("Ames","Pending","Qualified model absent"),("DILI","Pending","Qualified model absent")]
    body=''.join(f'<tr><td>{_safe(a)}</td><td>{status_badges(((b,b),))}</td><td>{_safe(c)}</td></tr>' for a,b,c in endpoints)
    molecule=_svg_wrap('<g stroke="#cfe1ff" stroke-width="5" fill="none"><polygon points="220,100 300,145 300,235 220,280 140,235 140,145"/><polygon points="380,145 460,100 540,145 540,235 460,280 380,235"/><line x1="300" y1="145" x2="380" y2="145"/><line x1="300" y1="235" x2="380" y2="235"/></g><text x="340" y="340" text-anchor="middle" fill="#8fe5d3" font-size="20">Standardized candidate structure</text>',"0 0 700 390")
    st.markdown(f'<div class="nc-shell">{molecule}<table class="nc-matrix"><thead><tr><th>Endpoint</th><th>Status</th><th>Interpretation</th></tr></thead><tbody>{body}</tbody></table>{_cards((("Applicability domain","Inside · 0.82"),("Critical liabilities","1"),("Modifiable risks","2"),("Recommendation","Reduce lipophilicity")))}</div>',unsafe_allow_html=True)


def _antibody_panel(prefix: str) -> None:
    heavy=_lane("Heavy chain",[(5,20,"FR1",""),(25,10,"CDR-H1","warn"),(36,18,"FR2",""),(56,10,"CDR-H2","warn"),(67,16,"FR3",""),(84,10,"CDR-H3","warn")])
    light=_lane("Light chain",[(5,22,"FR1",""),(29,9,"CDR-L1","alt"),(40,20,"FR2",""),(63,9,"CDR-L2","alt"),(74,20,"FR3/CDR-L3","alt")])
    st.markdown(f'<div class="nc-shell"><div class="nc-title">Antibody chain and CDR review</div>{heavy}{light}{status_badges((("Humanness","pass"),("Aggregation","review"),("Deamidation","review"),("Unpaired cysteine","pass")))}{readiness_matrix((("Chain pairing","Pass","No action"),("CDR numbering","Pass","IMGT-style"),("Humanization","Review","2 framework positions"),("Developability","Review","Hydrophobic patch"),("Interface evidence","Pending","Load antigen structure")))}</div>',unsafe_allow_html=True)


def _rare_disease_panel(prefix: str) -> None:
    criteria=[("PVS1","Very strong","Met"),("PS2","Strong","Review"),("PM2","Moderate","Met"),("PP3","Supporting","Met"),("BS1","Strong benign","Not met")]
    body=''.join(f'<tr><td>{a}</td><td>{b}</td><td>{status_badges(((c,c),))}</td></tr>' for a,b,c in criteria)
    st.markdown(f'<div class="nc-shell"><div class="nc-title">Rare-disease evidence and phenotype board</div>{_cards((("Proband","III-2"),("Phenotypes","Seizures · DD · Hypotonia"),("Top gene","SCN2A"),("Candidate variant","c.4763T>C")))}<table class="nc-matrix"><thead><tr><th>ACMG</th><th>Strength</th><th>Status</th></tr></thead><tbody>{body}</tbody></table>{workflow_stepper((("Initial review","pass"),("Family segregation","review"),("Functional evidence","pending"),("Multidisciplinary review","pending"),("Reanalysis","pending")))}</div>',unsafe_allow_html=True)


def _clinical_panel(prefix: str) -> None:
    consort=_svg_wrap('<rect x="80" y="35" width="220" height="55" rx="12" fill="#173553"/><text x="190" y="68" text-anchor="middle" fill="#eef5ff">Screened n=420</text><path d="M190 90 L190 145" stroke="#80a0c8" stroke-width="3"/><rect x="80" y="145" width="220" height="55" rx="12" fill="#173553"/><text x="190" y="178" text-anchor="middle" fill="#eef5ff">Eligible n=286</text><path d="M300 172 L470 172" stroke="#80a0c8"/><rect x="470" y="145" width="220" height="55" rx="12" fill="#3c2638"/><text x="580" y="178" text-anchor="middle" fill="#ffd5de">Excluded n=134</text><path d="M190 200 L190 255" stroke="#80a0c8" stroke-width="3"/><rect x="80" y="255" width="220" height="55" rx="12" fill="#173553"/><text x="190" y="288" text-anchor="middle" fill="#eef5ff">Analysed n=268</text><path d="M190 310 L190 365" stroke="#80a0c8" stroke-width="3"/><rect x="80" y="365" width="220" height="55" rx="12" fill="#1e4b43"/><text x="190" y="398" text-anchor="middle" fill="#d9fff3">External validation n=112</text>',"0 0 760 450")
    st.markdown(f'<div class="nc-shell"><div class="nc-title">Cohort flow and reviewer decision</div>{consort}{readiness_matrix((("Primary endpoint","Pass","Locked"),("Missing outcome","Review","6.3%"),("Treatment interaction","Review","Subgroup analysis"),("External cohort","Pass","112 participants"),("Clinical utility","Pending","Prospective evaluation")))}</div>',unsafe_allow_html=True)


def _reference_panel(prefix: str) -> None:
    st.markdown(f'<div class="nc-shell"><div class="nc-title">Reference database lifecycle board</div>{_cards((("ClinVar","2026-06 · active"),("Ensembl","Release 114 · pinned"),("gnomAD","v4.1 · verified"),("HPO","2026-05 · update ready")))}{workflow_stepper((("Plan","pass"),("Licence","pass"),("Download","pass"),("Verify","pass"),("Index","review"),("Activate","active")))}{readiness_matrix((("SHA-256","Pass","Verified"),("Disk space","Pass","142 GB free"),("Tool compatibility","Review","VEP cache mismatch"),("Rollback point","Pass","1 previous version"),("Licence acknowledgement","Pass","Recorded")))}</div>',unsafe_allow_html=True)


def _jobs_panel(prefix: str) -> None:
    cols={"Queued":[("J-204","Kraken profile"),("J-207","VEP annotation")],"Running":[("J-199","Cellpose batch")],"Review":[("J-188","GWAS PCA")],"Completed":[("J-174","FASTQ QC"),("J-175","Assembly stats")]}
    html_cols=''.join(f'<div class="nc-col"><h5>{name}</h5>'+''.join(f'<div class="nc-ticket"><b>{jid}</b> · {job}<small>{"worker-02" if name=="Running" else "local queue"}</small></div>' for jid,job in jobs)+'</div>' for name,jobs in cols.items())
    st.markdown(f'<div class="nc-shell"><div class="nc-title">Persistent background execution board</div><div class="nc-kanban">{html_cols}</div>{_cards((("Workers online","2/2"),("CPU reserved","8 cores"),("RAM reserved","18 GB"),("Retry budget","3 attempts")),kpi=True)}{workflow_stepper((("Preflight","pass"),("Stage input","pass"),("Execute","active"),("Verify output","pending"),("Register artifacts","pending")))}</div>',unsafe_allow_html=True)


def _workflow_panel(prefix: str) -> None:
    svg=_svg_wrap('<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#65d4c9"/></marker></defs><rect x="45" y="170" width="150" height="70" rx="14" fill="#173553"/><text x="120" y="210" text-anchor="middle" fill="#eef5ff">Upload + QC</text><rect x="270" y="70" width="165" height="70" rx="14" fill="#173553"/><text x="352" y="110" text-anchor="middle" fill="#eef5ff">Align / quantify</text><rect x="270" y="270" width="165" height="70" rx="14" fill="#442d49"/><text x="352" y="310" text-anchor="middle" fill="#ffd9ed">Failure branch</text><rect x="520" y="170" width="165" height="70" rx="14" fill="#1d4c44"/><text x="602" y="210" text-anchor="middle" fill="#e5fff7">Analyse</text><rect x="745" y="170" width="120" height="70" rx="14" fill="#173553"/><text x="805" y="210" text-anchor="middle" fill="#eef5ff">Report</text><path d="M195 205 L270 105" stroke="#65d4c9" stroke-width="4" marker-end="url(#arrow)"/><path d="M195 205 L270 305" stroke="#e3749f" stroke-width="4" marker-end="url(#arrow)"/><path d="M435 105 L520 205" stroke="#65d4c9" stroke-width="4" marker-end="url(#arrow)"/><path d="M685 205 L745 205" stroke="#65d4c9" stroke-width="4" marker-end="url(#arrow)"/>')
    st.markdown(f'<div class="nc-shell"><div class="nc-title">Typed workflow execution canvas</div>{svg}{status_badges((("Schema compatibility","pass"),("Critical path","active"),("Checkpoint","pass"),("Failure recovery","review")))}{_cards((("Nodes","5"),("Cached nodes","2"),("Estimated runtime","42 min"),("Peak RAM","11.8 GB")))}</div>',unsafe_allow_html=True)


def _dataset_panel(prefix: str) -> None:
    st.markdown(f'<div class="nc-shell"><div class="nc-title">Dataset lineage and governance board</div>{_cards((("Physical asset","RNAseq_counts_v3.parquet"),("Logical version","Cohort-A · release 3"),("Parent version","release 2"),("SHA-256","6d1f…9ba2")))}{workflow_stepper((("Raw asset","pass"),("Curated table","pass"),("QC release","pass"),("Analysis snapshot","active"),("Archive","pending")))}{readiness_matrix((("Schema","Pass","42 fields"),("Missingness","Review","3 fields >10%"),("Sample metadata","Pass","126/126"),("Licence","Pass","Research use"),("Scientific release","Review","External evidence pending")))}</div>',unsafe_allow_html=True)


def _model_panel(prefix: str) -> None:
    st.markdown(f'<div class="nc-shell"><div class="nc-title">Model lifecycle and approval board</div>{workflow_stepper((("Draft","pass"),("Training","pass"),("Internal validation","pass"),("External validation","review"),("Approval","pending"),("Deployment","pending")))}{_cards((("Candidate","model-11.5.2"),("Training snapshot","ds-2026-0711"),("Calibration","0.93 coverage"),("Deployment","Not approved")))}{readiness_matrix((("Leakage audit","Pass","No action"),("Subgroup metrics","Review","2 weak cohorts"),("External validation","Review","Complete cohort B"),("Model card","Pass","Generated"),("Approval signature","Pending","Assign reviewer")))}</div>',unsafe_allow_html=True)


_CONTEXT_RENDERERS: dict[str, Callable[[str], None]] = {
    "fastq": _fastq_panel,
    "variant": _variant_panel,
    "transcriptomics": _transcriptomics_panel,
    "crispr": _crispr_panel,
    "admet": _admet_panel,
    "antibody": _antibody_panel,
    "rare_disease": _rare_disease_panel,
    "clinical_biomarker": _clinical_panel,
    "reference_db": _reference_panel,
    "background_jobs": _jobs_panel,
    "workflow": _workflow_panel,
    "dataset_registry": _dataset_panel,
    "model_registry": _model_panel,
}


def render_module_non_chart_panel(context: str, *, key_prefix: str | None = None, expanded: bool = False) -> None:
    if context not in MODULE_NON_CHART_CONTEXTS:
        st.error(f"Unknown module non-chart context: {context}")
        return
    _inject_css()
    prefix=key_prefix or f"module_nc_{context}"
    config=MODULE_NON_CHART_CONTEXTS[context]
    st.divider()
    st.markdown(f"#### 🧭 {config['title']}")
    st.caption("Interactive scientific status, editors, tracks, matrices and review panels beyond conventional charts.")
    if not st.toggle("Open module-specific non-chart workspace",value=expanded,key=f"{prefix}_open"):
        st.markdown(f'<div class="nc-shell">{_cards(tuple((item,"Available on demand") for item in config["items"]))}</div>',unsafe_allow_html=True)
        return
    renderer=_CONTEXT_RENDERERS.get(context)
    try:
        if renderer is not None:
            renderer(prefix)
        else:
            _generic_module_panel(context, prefix)
        with st.expander("Review note and export workspace state", expanded=False):
            note = st.text_area("Reviewer note", key=f"{prefix}_review_note", placeholder="Record the decision, blocker or required follow-up.")
            manifest = {
                "schema": "biointel.module-non-chart-state.v1",
                "version": "15.6.0",
                "context": context,
                "title": config["title"],
                "available_components": list(config["items"]),
                "review_note": note,
            }
            st.download_button(
                "Download workspace state",
                data=json.dumps(manifest, indent=2, ensure_ascii=False),
                file_name=f"biointel_{context}_workspace_state.json",
                mime="application/json",
                key=f"{prefix}_state_download",
            )
    except Exception as exc:
        error_id=hashlib.sha256(f"{context}:{type(exc).__name__}:{exc}".encode()).hexdigest()[:12].upper()
        st.error(f"The module workspace could not render safely. Error ID: NCM-{error_id}")
        with st.expander("Diagnostic details"):
            st.code(f"context={context}\nerror={type(exc).__name__}: {exc}")


def render_non_chart_visual_hub() -> None:
    _inject_css()
    st.markdown("### Advanced non-chart scientific visual catalogue")
    st.caption("Fifteen optimized canvases, editors, tracks, maps, boards and relationship workspaces. Heavy views render only after selection.")
    query=st.text_input("Search non-chart visuals",placeholder="genome, plate, pedigree, microscopy, bioprocess…",key="nc_hub_search")
    options=list(NON_CHART_VISUAL_CATALOG.values())
    if query.strip():
        token=query.lower().strip()
        options=[spec for spec in options if token in (spec.title+" "+spec.description+" "+" ".join(spec.modules)).lower()]
    st.markdown(_cards(tuple((spec.title,", ".join(spec.modules[:3])) for spec in options)),unsafe_allow_html=True)
    if not options:
        st.info("No non-chart visual matches the current search.")
        return
    selected=st.selectbox("Open visual workspace",[spec.key for spec in options],format_func=lambda key:NON_CHART_VISUAL_CATALOG[key].title,key="nc_hub_choice")
    render_non_chart_visual(selected,key_prefix=f"nc_hub_{selected}",expanded=True,heading=True)


__all__ = [
    "MODULE_NON_CHART_CONTEXTS",
    "NON_CHART_VISUAL_CATALOG",
    "NonChartVisualSpec",
    "readiness_matrix",
    "render_module_non_chart_panel",
    "render_non_chart_visual",
    "render_non_chart_visual_hub",
    "status_badges",
    "workflow_stepper",
]
