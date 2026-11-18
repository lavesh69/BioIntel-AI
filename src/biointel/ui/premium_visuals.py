from __future__ import annotations

import base64
import hashlib
import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import streamlit as st


@dataclass(frozen=True)
class HeroVisualSpec:
    icon: str
    motif: str
    workflow: tuple[str, ...]
    accent_label: str


# Small, dependency-free SVG library. All icons share a 24×24 viewBox, rounded
# strokes and currentColor so they inherit the active BioIntel palette.
_ICON_PATHS: dict[str, str] = {
    "dna": '<path d="M7 3c6 4 6 14 0 18M17 3c-6 4-6 14 0 18M8.6 6h6.8M7.4 10h9.2M7.4 14h9.2M8.6 18h6.8"/>',
    "protein": '<path d="M5 5c3-3 5 3 8 0s6 2 4 5-5 1-5 5 3 5 5 2M8 8l2 2m4-2 2 2M7 17h3"/>',
    "molecule": '<circle cx="6" cy="12" r="2.2"/><circle cx="16.5" cy="6.5" r="2.2"/><circle cx="18" cy="17" r="2.2"/><path d="m8 11 6.5-3.5M8 13l8 3M16.7 8.7l.8 6.1"/>',
    "microscope": '<path d="M9 3h5v3H9zM10 6v5a4 4 0 0 0 4 4h2M8 21h11M12 17a5 5 0 0 1-5-5V9M6 9h4M16 12h3v5h-3z"/>',
    "chromosome": '<path d="M8 3c0 4 8 4 8 9s-8 5-8 9M16 3c0 4-8 4-8 9s8 5 8 9M9.5 6.5h5M8.5 12h7M9.5 17.5h5"/>',
    "brain": '<path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-1 5 3 3 0 0 0 2 5 3 3 0 0 0 5 2V5A3 3 0 0 0 9 4Zm6 0a3 3 0 0 1 3 3 3 3 0 0 1 1 5 3 3 0 0 1-2 5 3 3 0 0 1-5 2V5a3 3 0 0 1 3-1Z"/><path d="M8 9h4m4 0h-4M8 14h4m4 0h-4"/>',
    "flask": '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3M8 15h8M7 18h10"/>',
    "database": '<ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v6c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 11v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>',
    "shield": '<path d="M12 3 5 6v5c0 4.6 2.8 8.1 7 10 4.2-1.9 7-5.4 7-10V6l-7-3Z"/><path d="m9 12 2 2 4-5"/>',
    "workflow": '<rect x="3" y="4" width="6" height="5" rx="1"/><rect x="15" y="4" width="6" height="5" rx="1"/><rect x="9" y="15" width="6" height="5" rx="1"/><path d="M9 6.5h6M6 9v3h6v3m6-6v3h-6"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="2"/><path d="m4 17 5-5 4 4 3-3 5 5"/>',
    "pathogen": '<circle cx="12" cy="12" r="5"/><path d="M12 2v5m0 10v5M2 12h5m10 0h5M5 5l3.5 3.5m7 7L19 19M19 5l-3.5 3.5m-7 7L5 19"/><circle cx="10" cy="11" r=".8"/><circle cx="14" cy="13" r=".8"/>',
    "report": '<path d="M6 3h9l3 3v15H6zM15 3v4h4M9 11h6M9 15h6M9 7h2"/>',
    "sequence": '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="10" cy="18" r="2"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.4 1A7 7 0 0 0 15 6l-.3-2.6h-4L10.4 6A7 7 0 0 0 8 7.1l-2.4-1-2 3.4 2 1.5a7 7 0 0 0 0 2l-2 1.5 2 3.4 2.4-1A7 7 0 0 0 10.4 18l.3 2.6h4L15 18a7 7 0 0 0 1.5-1.1l2.4 1 2-3.4-2-1.5c.1-.3.1-.7.1-1Z"/>',
    "home": '<path d="m3 11 9-8 9 8M5 10v11h14V10M9 21v-7h6v7"/>',
    "generic": '<path d="M12 2 4 6.5v9L12 22l8-4.5v-9L12 2Z"/><path d="m4 6.5 8 4.5 8-4.5M12 11v11"/>',
}


def _normalise(*parts: str | None) -> str:
    return " ".join(str(part or "") for part in parts).lower()


def icon_name_for(*, page_key: str | None = None, category: str | None = None, title: str | None = None, hint: str | None = None) -> str:
    text = _normalise(page_key, category, title, hint)
    rules: tuple[tuple[tuple[str, ...], str], ...] = (
        (("home", "quick start", "studio", "command center"), "home"),
        (("protein", "peptide", "antibody", "proteom", "enzyme"), "protein"),
        (("drug", "smiles", "chembl", "admet", "compound", "molecule", "docking"), "molecule"),
        (("microscop", "image", "spatial", "organoid", "cytometry", "high content"), "microscope"),
        (("chromosome", "variant", "genome", "gwas", "crispr", "pangenome", "long read", "assembly"), "chromosome"),
        (("sequence", "fasta", "fastq", "alignment", "phylogen"), "dna"),
        (("pathogen", "virus", "microbio", "outbreak", "one health", "metagenom"), "pathogen"),
        (("model", "machine learning", "ai lab", "autolab", "explainable", "causal", "biomarker"), "brain"),
        (("lab", "assay", "qpcr", "elisa", "bioprocess", "fermentation", "synthetic biology"), "flask"),
        (("database", "data", "dataset", "reference", "warehouse", "provider", "lakehouse"), "database"),
        (("governance", "evidence", "validation", "quality", "release", "security", "privacy", "assurance"), "shield"),
        (("workflow", "pipeline", "job", "operation", "execution", "project"), "workflow"),
        (("document", "report", "citation", "publication", "ocr"), "report"),
        (("appearance", "theme", "setting", "preference"), "settings"),
    )
    for needles, icon in rules:
        if any(needle in text for needle in needles):
            return icon
    return "generic"


def svg_icon_html(
    icon_name: str | None = None,
    *,
    page_key: str | None = None,
    category: str | None = None,
    title: str | None = None,
    hint: str | None = None,
    size: int = 24,
    css_class: str = "bio-svg-icon",
    label: str | None = None,
) -> str:
    resolved = icon_name if icon_name in _ICON_PATHS else icon_name_for(page_key=page_key, category=category, title=title, hint=hint)
    safe_label = html.escape(label or title or resolved.replace("_", " ").title())
    path = _ICON_PATHS.get(resolved, _ICON_PATHS["generic"])
    return (
        f'<svg class="{html.escape(css_class)}" width="{int(size)}" height="{int(size)}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="{safe_label}">'
        f'<title>{safe_label}</title>{path}</svg>'
    )


def _hero_spec(page_key: str | None, category: str | None, title: str | None) -> HeroVisualSpec:
    text = _normalise(page_key, category, title)
    icon = icon_name_for(page_key=page_key, category=category, title=title)
    motif = "molecular"
    workflow = ("Upload", "Validate", "Configure", "Analyse", "Review", "Export")
    accent = "Scientific workspace"
    if any(k in text for k in ("sequence", "genome", "variant", "crispr", "long read", "pangenome")):
        motif, accent = "helix", "Genomic intelligence"
    elif any(k in text for k in ("protein", "structure", "docking", "antibody", "enzyme")):
        motif, accent = "protein", "Structure & design"
        workflow = ("Input", "Prepare", "Design", "Validate", "Rank", "Export")
    elif any(k in text for k in ("microscop", "image", "spatial", "organoid", "cytometry")):
        motif, accent = "cells", "Imaging & spatial biology"
        workflow = ("Import", "Correct", "Segment", "Quantify", "Review", "Export")
    elif any(k in text for k in ("model", "ai", "autolab", "training", "evaluation")):
        motif, accent = "network", "AI model lifecycle"
        workflow = ("Register", "Prepare", "Train", "Validate", "Assure", "Release")
    elif any(k in text for k in ("lab", "assay", "bioprocess", "fermentation")):
        motif, accent = "assay", "Laboratory analytics"
        workflow = ("Import", "Map", "QC", "Analyse", "Approve", "Report")
    elif any(k in text for k in ("evidence", "governance", "validation", "release", "quality")):
        motif, accent = "evidence", "Evidence & governance"
        workflow = ("Collect", "Verify", "Review", "Resolve", "Approve", "Package")
    elif any(k in text for k in ("document", "citation", "report", "ocr")):
        motif, accent = "document", "Scientific knowledge"
        workflow = ("Import", "Extract", "Index", "Review", "Link", "Publish")
    elif any(k in text for k in ("data", "database", "reference", "warehouse")):
        motif, accent = "data", "Data & lineage"
        workflow = ("Register", "Validate", "Curate", "Version", "Link", "Release")
    return HeroVisualSpec(icon=icon, motif=motif, workflow=workflow, accent_label=accent)


def _scene_svg(motif: str, title: str) -> str:
    safe = html.escape(title)
    # A compact vector scene with CSS-animated groups. It is decorative, uses no
    # remote assets and remains legible when motion is disabled.
    common = (
        '<defs><linearGradient id="pv-g" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="var(--bio-primary)"/><stop offset=".52" stop-color="var(--bio-secondary)"/>'
        '<stop offset="1" stop-color="var(--bio-accent)"/></linearGradient>'
        '<filter id="pv-glow"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>'
    )
    if motif == "helix":
        body = (
            '<g class="pv-orbit" fill="none" stroke="url(#pv-g)" stroke-width="3" filter="url(#pv-glow)">'
            '<path d="M36 18c82 30 82 82 0 112s-82 82 0 112"/>'
            '<path d="M154 18c-82 30-82 82 0 112s82 82 0 112"/></g>'
            '<g class="pv-pulse" stroke="currentColor" opacity=".55">'
            + ''.join(f'<path d="M{52 + (i%2)*18} {42+i*25}h{70-(i%2)*36}"/>' for i in range(8)) + '</g>'
        )
    elif motif == "protein":
        body = (
            '<path class="pv-orbit" d="M20 170C55 20 115 245 165 62S238 220 275 90" fill="none" stroke="url(#pv-g)" stroke-width="16" stroke-linecap="round" filter="url(#pv-glow)"/>'
            '<path class="pv-drift" d="M28 190C88 72 132 230 195 84S253 195 282 132" fill="none" stroke="currentColor" stroke-width="2" opacity=".38"/>'
        )
    elif motif == "cells":
        body = '<g class="pv-drift" fill="none" stroke="url(#pv-g)" filter="url(#pv-glow)">' + ''.join(
            f'<circle cx="{35+(i%4)*68}" cy="{42+(i//4)*72}" r="{15+(i%3)*5}"/><circle cx="{35+(i%4)*68}" cy="{42+(i//4)*72}" r="4" fill="currentColor"/>'
            for i in range(12)
        ) + '</g>'
    elif motif == "network":
        nodes = [(35,50),(100,25),(165,70),(240,35),(275,120),(205,175),(125,140),(45,195)]
        links = [(0,1),(1,2),(2,3),(3,4),(4,5),(5,6),(6,7),(7,0),(1,6),(2,5)]
        body = '<g class="pv-pulse" stroke="url(#pv-g)" stroke-width="2">' + ''.join(
            f'<path d="M{nodes[a][0]} {nodes[a][1]}L{nodes[b][0]} {nodes[b][1]}"/>' for a,b in links
        ) + '</g><g fill="var(--bio-surface-strong)" stroke="currentColor" stroke-width="2">' + ''.join(
            f'<circle cx="{x}" cy="{y}" r="8"/>' for x,y in nodes
        ) + '</g>'
    elif motif == "assay":
        body = (
            '<g class="pv-drift" stroke="url(#pv-g)" fill="none" stroke-width="3">'
            '<path d="M40 25h42M51 25v70l-32 95a18 18 0 0 0 17 24h62a18 18 0 0 0 17-24L72 95V25"/>'
            '<path d="M29 154h76"/><path d="M146 68h130M146 108h112M146 148h130M146 188h96"/>'
            '</g><g class="pv-bubbles" fill="currentColor" opacity=".55"><circle cx="55" cy="175" r="5"/><circle cx="77" cy="186" r="7"/><circle cx="64" cy="147" r="4"/></g>'
        )
    elif motif == "evidence":
        body = (
            '<path d="M75 20 18 46v62c0 58 31 101 86 125 55-24 86-67 86-125V46L133 20" fill="none" stroke="url(#pv-g)" stroke-width="5"/>'
            '<path class="pv-pulse" d="m58 116 29 29 62-79" fill="none" stroke="currentColor" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>'
            '<g class="pv-drift" stroke="currentColor" opacity=".35"><path d="M210 55h66M210 95h52M210 135h70M210 175h44"/></g>'
        )
    elif motif == "data":
        body = (
            '<g class="pv-orbit" fill="none" stroke="url(#pv-g)" stroke-width="4">'
            '<ellipse cx="115" cy="42" rx="78" ry="28"/><path d="M37 42v122c0 16 35 29 78 29s78-13 78-29V42"/>'
            '<path d="M37 83c0 16 35 29 78 29s78-13 78-29M37 123c0 16 35 29 78 29s78-13 78-29"/>'
            '</g><g class="pv-drift" stroke="currentColor" opacity=".38"><path d="M220 65h60M220 105h43M220 145h68M220 185h51"/></g>'
        )
    elif motif == "document":
        body = (
            '<path d="M55 20h118l48 48v165H55zM173 20v52h50" fill="none" stroke="url(#pv-g)" stroke-width="5"/>'
            '<g class="pv-pulse" stroke="currentColor" opacity=".5"><path d="M85 102h105M85 137h105M85 172h78M85 207h92"/></g>'
        )
    else:
        body = (
            '<g class="pv-orbit" fill="none" stroke="url(#pv-g)" stroke-width="3"><circle cx="145" cy="125" r="68"/><ellipse cx="145" cy="125" rx="125" ry="42" transform="rotate(28 145 125)"/><ellipse cx="145" cy="125" rx="125" ry="42" transform="rotate(-28 145 125)"/></g>'
            '<circle class="pv-pulse" cx="145" cy="125" r="10" fill="currentColor"/>'
        )
    return (
        f'<svg class="bio-hero-scene bio-hero-scene-{html.escape(motif)}" viewBox="0 0 300 250" role="img" aria-label="Decorative scientific artwork for {safe}">'
        f'<title>{safe} scientific motif</title>{common}{body}</svg>'
    )


def workflow_ribbon_html(steps: Sequence[str], *, active_index: int = 0) -> str:
    active = max(0, min(int(active_index), len(steps) - 1)) if steps else 0
    rendered: list[str] = []
    for index, step in enumerate(steps):
        state = "complete" if index < active else "active" if index == active else "pending"
        marker = "✓" if state == "complete" else str(index + 1)
        rendered.append(
            f'<div class="bio-workflow-step bio-workflow-{state}" role="listitem" aria-current="step"'
            f' data-workflow-state="{state}"><span class="bio-workflow-marker">{marker}</span>'
            f'<span class="bio-workflow-label">{html.escape(str(step))}</span></div>'
        )
    return '<div class="bio-workflow-ribbon" role="list" aria-label="Scientific workflow">' + "".join(rendered) + "</div>"


def premium_hero_inner_html(
    *,
    page_key: str | None,
    category: str | None,
    title: str,
    subtitle: str,
    eyebrow: str,
    chips: Iterable[str] | None,
    active_stage: int = 0,
) -> str:
    spec = _hero_spec(page_key, category, title)
    chip_html = ""
    if chips:
        chip_html = '<div class="bio-chip-row bio-hero-chips">' + "".join(
            f'<span class="bio-chip">{html.escape(str(chip))}</span>' for chip in chips
        ) + "</div>"
    icon = svg_icon_html(spec.icon, title=title, size=30, css_class="bio-svg-icon bio-hero-icon-svg")
    ribbon = workflow_ribbon_html(spec.workflow, active_index=active_stage)
    scene = _scene_svg(spec.motif, title)
    # Keep this fragment continuous. An empty optional chip row inside indented
    # multiline HTML makes Streamlit Markdown treat the following SVG as code.
    return (
        '<div class="bio-hero-content">'
        '<div class="bio-hero-copy">'
        f'<span class="bio-eyebrow"><span class="bio-hero-icon-wrap">{icon}</span>{html.escape(eyebrow)}</span>'
        f'<div class="bio-hero-domain">{html.escape(spec.accent_label)}</div>'
        f'<div class="bio-hero-title"><span class="bio-gradient-text">{html.escape(title)}</span></div>'
        f'<div class="bio-hero-subtitle">{html.escape(subtitle)}</div>'
        f"{chip_html}"
        "</div>"
        f'<div class="bio-hero-art" aria-hidden="true">{scene}</div>'
        "</div>"
        f"{ribbon}"
    )


def _safe_svg(svg: str) -> str:
    value = str(svg or "").strip()
    if not value.startswith("<svg") or "<script" in value.lower() or "onload=" in value.lower():
        raise ValueError("Before/after artwork must be a safe inline SVG without scripts or event handlers.")
    return value


def comparison_state_svg(
    *,
    title: str,
    label: str,
    after: bool,
    motif: str = "generic",
) -> str:
    safe_title = html.escape(title)
    safe_label = html.escape(label)
    primary = "#5eead4" if after else "#64748b"
    secondary = "#60a5fa" if after else "#94a3b8"
    bg = "#071927" if after else "#111827"
    grid_opacity = ".18" if after else ".10"
    blocks = "".join(
        f'<rect x="{36+(i%4)*118}" y="{70+(i//4)*82}" width="88" height="50" rx="12" fill="{primary}" opacity="{.18 + (i%3)*.08}" stroke="{secondary}"/>'
        for i in range(8)
    )
    marks = "".join(
        f'<circle cx="{66+(i%5)*92}" cy="{292-(i%3)*24}" r="{5+(i%3)*2}" fill="{primary}" opacity=".85"/>'
        for i in range(10)
    )
    return f'''<svg viewBox="0 0 520 340" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{safe_label}">
      <defs><pattern id="grid-{int(after)}" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="{secondary}" opacity="{grid_opacity}"/></pattern></defs>
      <rect width="520" height="340" rx="22" fill="{bg}"/><rect width="520" height="340" rx="22" fill="url(#grid-{int(after)})"/>
      <text x="30" y="38" fill="#e5f3ff" font-family="system-ui,sans-serif" font-size="20" font-weight="700">{safe_title}</text>
      <text x="30" y="60" fill="{secondary}" font-family="system-ui,sans-serif" font-size="12">{safe_label} · {html.escape(motif)}</text>
      {blocks}{marks}
      <path d="M42 275 C110 {230 if after else 262}, 185 {252 if after else 280}, 250 {195 if after else 268} S390 {160 if after else 250}, 478 {112 if after else 235}" fill="none" stroke="{primary}" stroke-width="5" stroke-linecap="round"/>
      <rect x="30" y="308" width="{430 if after else 250}" height="8" rx="4" fill="{primary}" opacity=".9"/>
    </svg>'''


def render_before_after_comparison(
    *,
    before_svg: str,
    after_svg: str,
    key: str,
    before_label: str = "Before",
    after_label: str = "After",
    height: int = 390,
    caption: str | None = None,
) -> None:
    """Render a dependency-free draggable before/after scientific comparison.

    The component is fully local, keyboard accessible and uses inline SVG only.
    It intentionally does not persist hidden scientific state; callers should
    export underlying data separately.
    """
    before = _safe_svg(before_svg)
    after = _safe_svg(after_svg)
    uid = "pv-" + hashlib.sha256(str(key).encode("utf-8")).hexdigest()[:12]
    safe_before = html.escape(before_label)
    safe_after = html.escape(after_label)
    component = f"""
<!doctype html><html><head><meta charset="utf-8"><style>
:root{{--primary:#5eead4;--secondary:#60a5fa;--surface:rgba(7,17,31,.94);--text:#edf7ff;--muted:#9fb1c7}}
*{{box-sizing:border-box}}body{{margin:0;background:transparent;color:var(--text);font-family:Inter,Segoe UI,system-ui,sans-serif}}
.ba-card{{position:relative;overflow:hidden;border:1px solid rgba(125,211,252,.25);border-radius:22px;background:var(--surface);box-shadow:0 18px 54px rgba(2,6,23,.28);isolation:isolate}}
.ba-stage{{position:relative;aspect-ratio:520/340;min-height:260px;overflow:hidden;background:#07111f}}
.ba-stage svg{{display:block;width:100%;height:100%}}.ba-before,.ba-after{{position:absolute;inset:0}}
.ba-after{{clip-path:inset(0 0 0 50%)}}
.ba-divider{{position:absolute;top:0;bottom:0;left:50%;width:2px;background:rgba(255,255,255,.9);transform:translateX(-1px);box-shadow:0 0 18px rgba(94,234,212,.8);pointer-events:none}}
.ba-handle{{position:absolute;left:50%;top:50%;width:44px;height:44px;border-radius:50%;display:grid;place-items:center;transform:translate(-50%,-50%);background:linear-gradient(135deg,var(--primary),var(--secondary));color:#04111b;font-weight:900;box-shadow:0 8px 24px rgba(0,0,0,.35);pointer-events:none}}
.ba-label{{position:absolute;top:14px;padding:7px 11px;border-radius:999px;background:rgba(3,8,18,.76);backdrop-filter:blur(10px);font-size:12px;font-weight:700;border:1px solid rgba(255,255,255,.16)}}
.ba-label.left{{left:14px}}.ba-label.right{{right:14px}}.ba-controls{{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;padding:12px 16px;background:rgba(4,12,23,.86)}}
.ba-controls span{{font-size:12px;color:var(--muted);font-weight:700}}input[type=range]{{width:100%;accent-color:var(--primary)}}
.ba-note{{padding:0 16px 13px;color:var(--muted);font-size:11px}}
@media (prefers-reduced-motion:no-preference){{.ba-after,.ba-divider,.ba-handle{{transition:clip-path .08s linear,left .08s linear}}}}
</style></head><body>
<div class="ba-card" id="{uid}"><div class="ba-stage">
  <div class="ba-before">{before}</div><div class="ba-after">{after}</div>
  <div class="ba-divider"></div><div class="ba-handle" aria-hidden="true">↔</div>
  <div class="ba-label left">{safe_before}</div><div class="ba-label right">{safe_after}</div>
</div><div class="ba-controls"><span>{safe_before}</span><input aria-label="Before and after comparison position" type="range" min="0" max="100" value="50"><span>{safe_after}</span></div>
{f'<div class="ba-note">{html.escape(caption)}</div>' if caption else ''}</div>
<script>
(()=>{{const root=document.getElementById('{uid}'), slider=root.querySelector('input'), after=root.querySelector('.ba-after'), divider=root.querySelector('.ba-divider'), handle=root.querySelector('.ba-handle');
const update=()=>{{const v=Number(slider.value);after.style.clipPath=`inset(0 0 0 ${{v}}%)`;divider.style.left=`${{v}}%`;handle.style.left=`${{v}}%`;}};slider.addEventListener('input',update);update();}})();
</script></body></html>
"""
    st.iframe(component, width="stretch", height=int(height), tab_index=0)


def set_workflow_stage(stage: int, *, page_key: str | None = None) -> None:
    resolved = page_key or "global"
    st.session_state[f"_bio_workflow_stage_{resolved}"] = max(0, int(stage))


def premium_theme_names() -> tuple[str, ...]:
    return (
        "Genomic Aurora",
        "Midnight Laboratory",
        "Clinical White",
        "Molecular Glass",
        "Cyber Biotech",
        "Oceanic Research",
        "Cellular Green",
        "Protein Violet",
        "Minimal Scientific",
        "High-Contrast Research",
        "Lavender Genome",
        "Rose Quartz Laboratory",
        "Emerald Muse",
        "Bronze Anatomy",
        "Obsidian Engineering",
        "Ink & Blueprint",
        "Solar Helix",
        "Black Diamond",
        "Crimson Genome",
        "Electric Lime",
        "Velvet Neon",
        "Copper Eclipse",
    )
