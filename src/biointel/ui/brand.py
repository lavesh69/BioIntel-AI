from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class BrandIdentity:
    """Single source of truth for the BioIntel AI product identity."""

    name: str = "BioIntel AI"
    compact_name: str = "BioIntel"
    descriptor: str = "Scientific Intelligence for Life Sciences"
    tagline: str = "Biology, Engineered into Intelligence."
    trust_line: str = "Traceable science. Defensible decisions."
    founder: str = "Lavesh Dobriyal"
    edition: str = "Professional Research Platform"
    primary: str = "#22D3EE"
    secondary: str = "#3B82F6"
    accent: str = "#8B5CF6"
    success: str = "#22C55E"
    warning: str = "#F59E0B"
    critical: str = "#EF4444"
    uncertainty: str = "#94A3B8"
    background: str = "#07111F"
    surface: str = "#111C30"
    text: str = "#F8FAFC"
    muted: str = "#9DB6C8"


BRAND = BrandIdentity()


@dataclass(frozen=True)
class BrandDomain:
    key: str
    label: str
    description: str
    icon: str


PRODUCT_FAMILIES: tuple[BrandDomain, ...] = (
    BrandDomain("genomics", "BioIntel Genomics", "Sequence, genome, variant and pathogen intelligence.", "dna"),
    BrandDomain("discovery", "BioIntel Discovery", "Target, compound, structure and developability workflows.", "molecule"),
    BrandDomain("lab", "BioIntel Lab", "Assay, instrument, wet-lab and process analytics.", "flask"),
    BrandDomain("omics", "BioIntel Omics", "Transcriptomic, proteomic, single-cell and multi-omics analysis.", "layers"),
    BrandDomain("models", "BioIntel Models", "Training, evaluation, validation and lifecycle governance.", "model"),
    BrandDomain("evidence", "BioIntel Evidence", "Provenance, evidence review, release gates and reporting.", "shield"),
    BrandDomain("operations", "BioIntel Operations", "Projects, workflows, reliability, storage and deployment.", "workflow"),
)


COMPACT_MODULE_NAMES: dict[str, str] = {
    "pangenome_graph": "Pangenome Graph Studio",
    "long_read_assembly": "Long-Read Assembly Studio",
    "protein_design_lab": "Protein Design Lab",
    "crispr_perturbseq": "CRISPR & Perturb-seq Lab",
    "pathogen_outbreak": "Outbreak Genomics Center",
    "synthetic_biology_designer": "Genetic Circuit Studio",
    "rare_disease_board": "Rare Disease Review Board",
    "knowledge_graph_copilot": "Biomedical Evidence Copilot",
    "multiomics_biomarker": "Biomarker Discovery Studio",
    "visual_workflow_builder": "Workflow Builder",
    "innovation_modules_hub": "Innovation Hub",
}


_ALGORITHM_NAMES = {
    "extra_trees": "ExtraTrees",
    "random_forest": "Random Forest",
    "logistic_regression": "Logistic Regression",
    "sgd_logistic": "SGD Logistic",
    "ridge": "Ridge",
    "elastic_net": "Elastic Net",
    "sgd": "SGD Regressor",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "catboost": "CatBoost",
    "gradient_boosting": "Gradient Boosting",
}


@dataclass(frozen=True)
class ModelBrand:
    display_name: str
    compact_name: str
    tier_code: str
    tier_label: str
    evidence_label: str
    status_tone: str
    quality_label: str


def branded_page_title(title: str) -> str:
    from biointel.ui.public_branding import brand_public_text

    clean = str(brand_public_text(title)).strip()
    if not clean:
        return BRAND.name
    if BRAND.name.lower() in clean.lower():
        return clean
    return f"{clean} · {BRAND.name}"


def compact_module_name(page_key: str | None, fallback: str) -> str:
    from biointel.ui.public_branding import brand_public_text

    if page_key and page_key in COMPACT_MODULE_NAMES:
        return str(brand_public_text(COMPACT_MODULE_NAMES[page_key]))
    return str(brand_public_text(fallback))


def product_family_for_category(category: str) -> str:
    normalized = str(category or "").strip().lower()
    if normalized in {"bioinformatics", "sequence"}:
        return "BioIntel Genomics"
    if normalized in {"discovery", "chemistry"}:
        return "BioIntel Discovery"
    if normalized == "lab analytics":
        return "BioIntel Lab"
    if normalized in {"ai lab", "modelling", "modeling"}:
        return "BioIntel Models"
    if normalized in {"governance", "data & governance"}:
        return "BioIntel Evidence"
    if normalized in {"data", "documents", "intelligence"}:
        return "BioIntel Omics"
    return "BioIntel Operations"


def algorithm_display_name(raw: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(raw).strip().lower()).strip("_")
    if normalized in _ALGORITHM_NAMES:
        return _ALGORITHM_NAMES[normalized]
    return (
        " ".join(
            part.upper() if part in {"sgd", "svm", "cnn", "gnn"} else part.title()
            for part in normalized.split("_")
            if part
        )
        or "Model"
    )


def model_tier(metadata: Any, audit: Mapping[str, Any] | None = None) -> tuple[str, str, str, str]:
    audit = audit or {}
    synthetic = bool(getattr(metadata, "synthetic_demo", False))
    release_eligible = bool(audit.get("release_eligible", False))
    external = bool(audit.get("external_validation_present", False))
    robust = bool(audit.get("robust_split_passed", False))

    if synthetic:
        return "D", "Demonstration", "Synthetic benchmark only", "warning"
    if release_eligible and external:
        return "A", "Independent validation", "Externally validated and release eligible", "success"
    if external or (release_eligible and robust):
        return "B", "External evidence", "Independent external evidence available", "success"
    return "C", "Public-data research", "Retrospective research evidence", "info"


def branded_model_identity(
    model_path: str | Path,
    metadata: Any,
    audit: Mapping[str, Any] | None = None,
) -> ModelBrand:
    audit = audit or {}
    algorithm = algorithm_display_name(getattr(metadata, "model_name", Path(model_path).stem))
    task = str(getattr(metadata, "task_type", "model")).strip().title()
    version = str(getattr(metadata, "model_version", "local")).strip()
    tier_code, tier_label, evidence_label, tone = model_tier(metadata, audit)
    quality = float(audit.get("score", 0.0) or 0.0)
    compact = f"{algorithm} v{version}"
    return ModelBrand(
        display_name=f"{BRAND.compact_name} DTI {algorithm} · v{version} · Tier {tier_code}",
        compact_name=compact,
        tier_code=tier_code,
        tier_label=tier_label,
        evidence_label=evidence_label,
        status_tone=tone,
        quality_label=f"{quality:.0f}/100 · {task}",
    )


def branded_model_label_from_sidecar(
    model_path: str | Path,
    audit: Mapping[str, Any] | None = None,
) -> str:
    path = Path(model_path)
    payload: dict[str, Any] = {}
    sidecar = path.with_suffix(".json")
    if sidecar.is_file():
        try:
            import json

            loaded = json.loads(sidecar.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except (OSError, json.JSONDecodeError):
            payload = {}

    class _MetadataView:
        model_name = str(payload.get("model_name") or path.stem)
        model_version = str(payload.get("model_version") or "local")
        task_type = str(payload.get("task_type") or "model")
        synthetic_demo = bool(payload.get("synthetic_demo", False))

    identity = branded_model_identity(path, _MetadataView(), audit)
    return f"{identity.display_name} · {identity.quality_label}"


def _logo_palette(variant: str) -> tuple[str, str, str, str, str]:
    value = str(variant or "full").strip().lower()
    if value == "white":
        return "#FFFFFF", "#FFFFFF", "#FFFFFF", "#FFFFFF", "transparent"
    if value == "dark":
        return "#07111F", "#07111F", "#07111F", "#07111F", "transparent"
    if value in {"mono", "monochrome"}:
        return BRAND.text, BRAND.text, BRAND.text, BRAND.text, "transparent"
    return BRAND.primary, BRAND.secondary, BRAND.accent, BRAND.text, BRAND.background


def brand_mark_svg(
    *,
    size: int = 42,
    title: str = "BioIntel AI",
    variant: str = "full",
    simplified: bool = False,
) -> str:
    """Return a compact, deterministic SVG mark without repaint-heavy glow filters."""

    safe_title = html.escape(title)
    primary, secondary, accent, line, panel = _logo_palette(variant)
    crossbars = (
        '<path d="M22 20H42"/><path d="M19 28H45"/><path d="M19 36H45"/><path d="M22 44H42"/>'
        if not simplified
        else '<path d="M20 24H44"/><path d="M20 40H44"/>'
    )
    panel_fill = panel if panel != "transparent" else "none"
    return f"""
    <svg class="bio-brand-svg" width="{int(size)}" height="{int(size)}" viewBox="0 0 64 64" role="img" aria-label="{safe_title} logo" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="biointel-brand-gradient" x1="8" y1="8" x2="56" y2="56" gradientUnits="userSpaceOnUse">
          <stop stop-color="{primary}"/><stop offset=".54" stop-color="{secondary}"/><stop offset="1" stop-color="{accent}"/>
        </linearGradient>
      </defs>
      <rect x="3" y="3" width="58" height="58" rx="16" fill="{panel_fill}" stroke="url(#biointel-brand-gradient)" stroke-width="2"/>
      <path d="M19 12C42 18 42 46 19 52" fill="none" stroke="url(#biointel-brand-gradient)" stroke-width="4.25" stroke-linecap="round"/>
      <path d="M45 12C22 18 22 46 45 52" fill="none" stroke="url(#biointel-brand-gradient)" stroke-width="4.25" stroke-linecap="round"/>
      <g stroke="{line}" stroke-opacity=".78" stroke-width="1.8" stroke-linecap="round">{crossbars}</g>
      <circle cx="19" cy="12" r="2.7" fill="{primary}"/><circle cx="45" cy="12" r="2.7" fill="{accent}"/>
      <circle cx="19" cy="52" r="2.7" fill="{accent}"/><circle cx="45" cy="52" r="2.7" fill="{primary}"/>
    </svg>
    """.strip()


def brand_header_html(version: str) -> str:
    """Compact shell lockup: identity, tagline and trust—not developer credits."""

    return f"""
    <header class="bio-top-brand-v83 bio-brand-system-v136" aria-label="{html.escape(BRAND.name)} brand">
      <div class="bio-top-brand-main">
        <span class="bio-top-brand-mark">{brand_mark_svg(size=40)}</span>
        <div class="bio-brand-wordmark">
          <strong>{html.escape(BRAND.name)}</strong>
          <small>{html.escape(BRAND.descriptor)}</small>
        </div>
      </div>
      <div class="bio-top-brand-center">
        <div class="bio-top-brand-motto">{html.escape(BRAND.tagline)}</div>
        <div class="bio-top-brand-trust">{html.escape(BRAND.trust_line)}</div>
      </div>
      <div class="bio-top-brand-meta">
        <span>{html.escape(BRAND.edition)} · v{html.escape(version)}</span>
        <small><i aria-hidden="true"></i> Evidence-aware workspace</small>
      </div>
    </header>
    """.strip()


def sidebar_brand_html(version: str) -> str:
    return f"""
    <div class="bio-brand bio-brand-system-v136">
      <div class="bio-brand-mark">{brand_mark_svg(size=48)}</div>
      <div class="bio-brand-copy">
        <div class="bio-brand-title">{html.escape(BRAND.name)}</div>
        <div class="bio-brand-subtitle">{html.escape(BRAND.descriptor)}</div>
        <div class="bio-brand-tagline-mini">{html.escape(BRAND.tagline)}</div>
        <div class="bio-edition-pill">{html.escape(BRAND.edition)} · v{html.escape(version)}</div>
      </div>
    </div>
    """.strip()


def home_founder_credit_html() -> str:
    """Return a compact founder attribution intended only for the Home hero."""

    return f"""
    <div class="bio-home-founder-credit" role="note" aria-label="BioIntel AI founder attribution">
      <span>Created &amp; Developed by</span>
      <strong>{html.escape(BRAND.founder)}</strong>
    </div>
    """.strip()


def brand_trust_strip_html(
    *,
    evidence: str = "Reference",
    confidence: str = "Context dependent",
    dataset_status: str = "Verified when checksum-backed",
    model_status: str = "Research use",
    reviewed: str = "See provenance record",
) -> str:
    fields = (
        ("Evidence level", evidence),
        ("Confidence", confidence),
        ("Dataset status", dataset_status),
        ("Model status", model_status),
        ("Last reviewed", reviewed),
    )
    cells = "".join(
        f'<span><small>{html.escape(label)}</small><b>{html.escape(value)}</b></span>'
        for label, value in fields
    )
    return f'<div class="bio-brand-trust-strip" role="note" aria-label="Scientific trust status">{cells}</div>'


def about_brand_html(version: str) -> str:
    return f"""
    <div class="bio-about-brand">
      <div class="bio-about-lockup">{brand_mark_svg(size=36)}<div><strong>{html.escape(BRAND.name)}</strong><span>{html.escape(BRAND.tagline)}</span></div></div>
      <p>{html.escape(BRAND.descriptor)}. Created and developed by <strong>{html.escape(BRAND.founder)}</strong>.</p>
      <small>{html.escape(BRAND.edition)} · Version {html.escape(version)}</small>
    </div>
    """.strip()
