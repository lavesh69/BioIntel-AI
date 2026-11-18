from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from html import escape
from typing import Iterable

from biointel.ui.style_catalog import FONTS, FontSpec, ThemeSpec


@dataclass(frozen=True)
class LightThemeSpec:
    background: str
    background_soft: str
    surface: str
    surface_strong: str
    sidebar_start: str
    sidebar_end: str
    text: str
    muted: str
    border: str


@dataclass(frozen=True)
class ThemeMeta:
    category: str
    best_for: tuple[str, ...]
    performance: str
    recommended_fonts: tuple[str, ...]
    layout_mode: str


@dataclass(frozen=True)
class TypographyPairing:
    name: str
    heading_font: str
    body_font: str
    data_font: str
    description: str


@dataclass(frozen=True)
class ChartProfile:
    grid_dash: str
    grid_alpha: float
    axis_width: int
    line_width: float
    marker_symbol: str
    marker_size: int
    legend_orientation: str
    legend_y: float
    hover_border: str
    plot_alpha: float


@dataclass(frozen=True)
class FontMetrics:
    heading_weight: int
    body_weight: int
    navigation_weight: int
    heading_tracking: str
    body_line_height: float
    table_scale: float


LIGHT_THEMES: dict[str, LightThemeSpec] = {
    "BioIntel Signature": LightThemeSpec("#F4FAFD", "#E7F3F9", "rgba(255,255,255,.96)", "#FFFFFF", "#F8FCFE", "#EAF5FA", "#10253C", "#5E7285", "rgba(34,211,238,.20)"),
    "Executive": LightThemeSpec("#F3F7FC", "#EAF1FA", "rgba(255,255,255,.95)", "#FFFFFF", "#F8FBFF", "#EDF4FC", "#0F2340", "#52657D", "rgba(26,71,126,.16)"),
    "Clinical": LightThemeSpec("#F1FAF8", "#E6F5F1", "rgba(253,255,254,.97)", "#FFFFFF", "#F6FCFA", "#E8F5F1", "#123B37", "#55706C", "rgba(15,118,110,.18)"),
    "Regulatory": LightThemeSpec("#F7F5EF", "#EFEADF", "rgba(255,254,250,.97)", "#FFFFFF", "#FBF9F4", "#EEE8DA", "#29271F", "#6D685A", "rgba(29,78,216,.16)"),
    "Aurora": LightThemeSpec("#F7F4FF", "#EEE9FF", "rgba(255,255,255,.88)", "#FFFFFF", "#FBF9FF", "#F0EAFF", "#2B1F4A", "#6A5D87", "rgba(139,92,246,.18)"),
    "Ocean": LightThemeSpec("#F0F9FF", "#E2F4FD", "rgba(252,255,255,.94)", "#FFFFFF", "#F7FCFF", "#E7F6FD", "#0E3855", "#527188", "rgba(14,165,233,.18)"),
    "Emerald": LightThemeSpec("#F1FBF5", "#E5F7EC", "rgba(253,255,254,.95)", "#FFFFFF", "#F7FDF9", "#E8F7EE", "#113D2A", "#557465", "rgba(16,185,129,.18)"),
    "Rose": LightThemeSpec("#FFF5F8", "#FCE8EF", "rgba(255,252,253,.94)", "#FFFFFF", "#FFF9FB", "#FCEAF1", "#4B1E31", "#806273", "rgba(244,63,94,.18)"),
    "Midnight Graphite": LightThemeSpec("#F0F2F6", "#E4E8EF", "rgba(250,251,253,.96)", "#FFFFFF", "#F6F7FA", "#E7EAF0", "#202938", "#647083", "rgba(51,65,85,.20)"),
    "Nordic Frost": LightThemeSpec("#F4FAFC", "#E9F3F7", "rgba(255,255,255,.96)", "#FFFFFF", "#F9FCFD", "#EDF6F8", "#173641", "#627780", "rgba(14,165,233,.15)"),
    "Solarized Lab": LightThemeSpec("#FCF8EE", "#F4EDDE", "rgba(255,253,247,.96)", "#FFFFFF", "#FFFCF6", "#F5EDDE", "#3D3424", "#756C5C", "rgba(180,114,8,.20)"),
    "Deep Space": LightThemeSpec("#F4F3FF", "#E9E7FA", "rgba(253,252,255,.95)", "#FFFFFF", "#F9F8FF", "#ECE9FC", "#28234C", "#676184", "rgba(99,102,241,.18)"),
    "BioMatrix": LightThemeSpec("#F0FAF2", "#E3F4E8", "rgba(251,255,252,.96)", "#FFFFFF", "#F7FDF8", "#E8F6EB", "#153A25", "#5C7665", "rgba(34,197,94,.18)"),
    "Royal Amethyst": LightThemeSpec("#FBF4FF", "#F1E7F8", "rgba(255,252,255,.92)", "#FFFFFF", "#FDF8FF", "#F2E9F8", "#412252", "#7A6287", "rgba(168,85,247,.18)"),
    "Ember Forge": LightThemeSpec("#FFF7F1", "#F8EBDD", "rgba(255,253,250,.97)", "#FFFFFF", "#FFF9F5", "#F8ECE1", "#4A2A18", "#806957", "rgba(194,65,12,.20)"),
    "Arctic Glass": LightThemeSpec("#F1FBFD", "#E4F5F8", "rgba(255,255,255,.68)", "rgba(255,255,255,.84)", "rgba(250,254,255,.82)", "rgba(232,247,250,.90)", "#123946", "#5B7880", "rgba(6,182,212,.19)"),
    "Sakura Research": LightThemeSpec("#FFF5FA", "#FBE7F1", "rgba(255,252,254,.94)", "#FFFFFF", "#FFF9FC", "#FCEAF3", "#4D2038", "#806678", "rgba(236,72,153,.18)"),
    "Monochrome Pro": LightThemeSpec("#F6F6F6", "#EAEAEA", "#FFFFFF", "#FFFFFF", "#FAFAFA", "#EDEDED", "#111111", "#5B5B5B", "rgba(17,17,17,.28)"),
    'Genomic Noir': LightThemeSpec('#EFFAF8','#E1F3F0','rgba(255,255,255,.97)','#FFFFFF','#F7FCFB','#E8F5F3','#123B38','#5B7471','rgba(0,122,108,.18)'),
    'Helix Quantum': LightThemeSpec('#F6F3FF','#EAE5FB','rgba(255,255,255,.96)','#FFFFFF','#FAF8FF','#EDE9FC','#2D2555','#6D658C','rgba(124,58,237,.18)'),
    'CRISPR Cyan': LightThemeSpec('#F0FBFC','#E2F5F6','rgba(255,255,255,.97)','#FFFFFF','#F8FDFD','#E9F7F8','#123D43','#5A767A','rgba(6,182,212,.18)'),
    'Proteome Platinum': LightThemeSpec('#F4F6F8','#E7EBEF','rgba(255,255,255,.97)','#FFFFFF','#FAFBFC','#EBEEF2','#202B38','#65717F','rgba(71,85,105,.18)'),
    'Cell Atlas': LightThemeSpec('#F4FBF9','#E7F5F1','rgba(255,255,255,.96)','#FFFFFF','#F9FDFC','#EAF7F3','#183E38','#657870','rgba(20,184,166,.17)'),
    'Neural Biotech': LightThemeSpec('#F2F6FF','#E5EDFC','rgba(255,255,255,.97)','#FFFFFF','#F8FAFF','#EAF0FD','#1F3158','#61708C','rgba(59,130,246,.18)'),
    'Quantum Enzyme': LightThemeSpec('#FFF9EC','#F5EEDB','rgba(255,254,250,.97)','#FFFFFF','#FFFCF5','#F7EFDF','#44351B','#7A6D57','rgba(180,120,8,.19)'),
    'Botanical Circuit': LightThemeSpec('#F1FAF3','#E3F3E7','rgba(254,255,254,.97)','#FFFFFF','#F8FDF9','#E8F6EB','#173A22','#607665','rgba(34,197,94,.18)'),
    'Clinical Sapphire': LightThemeSpec('#F1F6FD','#E4EDF9','rgba(255,255,255,.97)','#FFFFFF','#F8FBFF','#E8F0FA','#183458','#60738A','rgba(37,99,235,.17)'),
    'Molecular Carbon': LightThemeSpec('#F5F5F5','#E8E8E8','#FFFFFF','#FFFFFF','#FAFAFA','#ECECEC','#111417','#5D6267','rgba(17,20,23,.24)'),
    'Spatial Omics': LightThemeSpec('#FCF3FD','#F2E5F4','rgba(255,253,255,.96)','#FFFFFF','#FEF9FF','#F4EAF6','#48214D','#7C6680','rgba(192,38,211,.17)'),
    'BioLuminescence': LightThemeSpec('#EFFBF7','#E1F5EE','rgba(253,255,254,.96)','#FFFFFF','#F7FDFB','#E6F7F0','#123B2F','#5D776D','rgba(16,185,129,.18)'),
    'Pathway Gold': LightThemeSpec('#FCF8ED','#F3ECD8','rgba(255,254,250,.97)','#FFFFFF','#FFFCF6','#F5EEDC','#41361F','#756B58','rgba(165,120,10,.19)'),
    'Cryo-EM Frost': LightThemeSpec('#F3FAFD','#E7F3F8','rgba(255,255,255,.86)','rgba(255,255,255,.96)','#FAFDFF','#EDF7FA','#173743','#627983','rgba(56,189,248,.16)'),
    'Synthetic Biology': LightThemeSpec('#FFF4FA','#F7E6F2','rgba(255,253,255,.96)','#FFFFFF','#FFF9FC','#F9EAF4','#4A203D','#806779','rgba(236,72,153,.17)'),
}


THEME_META: dict[str, ThemeMeta] = {
    "BioIntel Signature": ThemeMeta("Brand", ("Official product experience", "Store screenshots", "Scientific reports"), "Balanced", ("Inter", "Aptos", "Segoe UI"), "signature"),
    "Executive": ThemeMeta("Professional", ("Daily work", "Executive dashboards"), "Balanced", ("Inter", "Aptos", "Segoe UI"), "executive"),
    "Clinical": ThemeMeta("Clinical", ("Laboratory review", "Large tables"), "Fast", ("Verdana", "Segoe UI", "Arial"), "minimal"),
    "Regulatory": ThemeMeta("Professional", ("Governance", "Audit review"), "Fast", ("Aptos", "Georgia", "Segoe UI"), "ledger"),
    "Aurora": ThemeMeta("Creative", ("Exploration", "Presentations"), "Balanced", ("Inter", "Trebuchet MS", "Century Gothic"), "fluid"),
    "Ocean": ThemeMeta("Professional", ("Data analysis", "Long sessions"), "Balanced", ("Inter", "Verdana", "Segoe UI"), "layered"),
    "Emerald": ThemeMeta("Scientific", ("Biotechnology", "Assay analytics"), "Balanced", ("Inter", "Tahoma", "Trebuchet MS"), "organic"),
    "Rose": ThemeMeta("Creative", ("Presentations", "Soft professional UI"), "Balanced", ("Century Gothic", "Trebuchet MS", "Inter"), "atelier"),
    "Midnight Graphite": ThemeMeta("Professional", ("Low-light work", "Operations"), "Fast", ("Segoe UI", "Aptos", "Tahoma"), "executive"),
    "Nordic Frost": ThemeMeta("Minimal", ("Large tables", "Focused review"), "Fast", ("Inter", "Verdana", "Arial"), "minimal"),
    "Solarized Lab": ThemeMeta("Editorial", ("Scientific reports", "Reading"), "Fast", ("Georgia", "Aptos", "Times New Roman"), "editorial"),
    "Deep Space": ThemeMeta("Technology", ("AI/ML", "Discovery workflows"), "Balanced", ("Inter", "Century Gothic", "Segoe UI"), "tech"),
    "BioMatrix": ThemeMeta("Technology", ("Bioinformatics", "Technical monitoring"), "Balanced", ("Tahoma", "Courier New", "Segoe UI"), "terminal"),
    "Royal Amethyst": ThemeMeta("Glass", ("Presentations", "Premium dashboards"), "Effects-heavy", ("Century Gothic", "Inter", "Trebuchet MS"), "glass"),
    "Ember Forge": ThemeMeta("Technology", ("Operations", "Process analytics"), "Fast", ("Aptos", "Segoe UI", "Tahoma"), "industrial"),
    "Arctic Glass": ThemeMeta("Glass", ("Modern dashboards", "Presentations"), "Effects-heavy", ("Inter", "Century Gothic", "Segoe UI"), "glass"),
    "Sakura Research": ThemeMeta("Creative", ("Research planning", "Soft professional UI"), "Balanced", ("Trebuchet MS", "Century Gothic", "Inter"), "studio"),
    "Monochrome Pro": ThemeMeta("High contrast", ("Print review", "Accessibility"), "Fast", ("Arial", "Georgia", "Courier New"), "brutalist"),
    'Genomic Noir': ThemeMeta('Scientific',('Genomics', 'Long analytical sessions'),'Fast',('Inter', 'Aptos', 'Segoe UI'),'ledger'),
    'Helix Quantum': ThemeMeta('Technology',('AI bioinformatics', 'Advanced modelling'),'Balanced',('Century Gothic', 'Inter', 'Segoe UI'),'tech'),
    'CRISPR Cyan': ThemeMeta('Scientific',('CRISPR design', 'Sequence analysis'),'Fast',('Inter', 'Verdana', 'Segoe UI'),'minimal'),
    'Proteome Platinum': ThemeMeta('Professional',('Proteomics', 'Executive review'),'Fast',('Aptos', 'Segoe UI', 'Arial'),'executive'),
    'Cell Atlas': ThemeMeta('Scientific',('Single-cell', 'Cell atlas review'),'Fast',('Inter', 'Trebuchet MS', 'Verdana'),'organic'),
    'Neural Biotech': ThemeMeta('Technology',('ML workflows', 'DTI prediction'),'Balanced',('Inter', 'Century Gothic', 'Segoe UI'),'tech'),
    'Quantum Enzyme': ThemeMeta('Scientific',('Enzyme kinetics', 'Assay analytics'),'Fast',('Georgia', 'Aptos', 'Inter'),'editorial'),
    'Botanical Circuit': ThemeMeta('Scientific',('Plant biology', 'Synthetic circuits'),'Fast',('Trebuchet MS', 'Inter', 'Tahoma'),'organic'),
    'Clinical Sapphire': ThemeMeta('Clinical',('Clinical review', 'Validated tables'),'Fast',('Segoe UI', 'Verdana', 'Aptos'),'minimal'),
    'Molecular Carbon': ThemeMeta('High contrast',('Low-light work', 'Molecular modelling'),'Fast',('Arial', 'Segoe UI', 'Courier New'),'brutalist'),
    'Spatial Omics': ThemeMeta('Scientific',('Spatial transcriptomics', 'Tissue mapping'),'Balanced',('Inter', 'Century Gothic', 'Trebuchet MS'),'studio'),
    'BioLuminescence': ThemeMeta('Technology',('Marine biology', 'Live monitoring'),'Balanced',('Inter', 'Tahoma', 'Courier New'),'terminal'),
    'Pathway Gold': ThemeMeta('Editorial',('Pathways', 'Scientific reporting'),'Fast',('Georgia', 'Aptos', 'Times New Roman'),'editorial'),
    'Cryo-EM Frost': ThemeMeta('Glass',('Structural biology', 'Cryo-EM review'),'Balanced',('Inter', 'Segoe UI', 'Century Gothic'),'glass'),
    'Synthetic Biology': ThemeMeta('Creative',('Synthetic biology', 'Design workflows'),'Balanced',('Century Gothic', 'Inter', 'Trebuchet MS'),'atelier'),
}


TYPOGRAPHY_PAIRINGS: dict[str, TypographyPairing] = {
    "Modern Professional": TypographyPairing("Modern Professional", "Inter", "Inter", "Segoe UI", "Neutral modern pairing for everyday scientific work."),
    "Clinical Readable": TypographyPairing("Clinical Readable", "Trebuchet MS", "Verdana", "Tahoma", "Highly readable clinical and laboratory pairing."),
    "Scientific Editorial": TypographyPairing("Scientific Editorial", "Georgia", "Aptos", "Courier New", "Editorial headings with efficient body and fixed-width data."),
    "Technical Console": TypographyPairing("Technical Console", "Segoe UI", "Tahoma", "Courier New", "Dense technical controls with monospaced data output."),
    "Executive Report": TypographyPairing("Executive Report", "Century Gothic", "Aptos", "Segoe UI", "Geometric headings with document-oriented body text."),
    "Classic Academic": TypographyPairing("Classic Academic", "Times New Roman", "Georgia", "Courier New", "Traditional academic report pairing."),
    "Custom": TypographyPairing("Custom", "Inter", "Inter", "Inter", "Choose heading, body and data fonts independently."),
}


CHART_PROFILES: dict[str, ChartProfile] = {
    "BioIntel Signature": ChartProfile("solid", .10, 1, 2.45, "circle", 8, "h", 1.12, "#22D3EE", .012),
    "Executive": ChartProfile("solid", .13, 1, 2.4, "circle", 8, "h", 1.12, "#2563EB", .018),
    "Clinical": ChartProfile("dot", .11, 1, 2.1, "circle-open", 8, "h", 1.12, "#0F766E", .0),
    "Regulatory": ChartProfile("dash", .15, 1, 2.3, "square", 8, "h", 1.12, "#1D4ED8", .01),
    "Aurora": ChartProfile("dot", .08, 1, 2.6, "diamond", 9, "h", 1.12, "#8B5CF6", .02),
    "Ocean": ChartProfile("solid", .11, 1, 2.5, "circle", 8, "h", 1.12, "#0284C7", .015),
    "Emerald": ChartProfile("dot", .10, 1, 2.5, "hexagon", 9, "h", 1.12, "#059669", .012),
    "Rose": ChartProfile("dot", .08, 1, 2.5, "diamond", 9, "h", 1.12, "#E11D48", .018),
    "Midnight Graphite": ChartProfile("dash", .18, 1, 2.3, "square", 8, "v", 1.0, "#818CF8", .08),
    "Nordic Frost": ChartProfile("dot", .09, 1, 2.1, "circle-open", 8, "h", 1.12, "#0284C7", 0),
    "Solarized Lab": ChartProfile("dash", .12, 1, 2.2, "triangle-up", 8, "h", 1.12, "#B45309", .01),
    "Deep Space": ChartProfile("dashdot", .22, 1, 2.8, "diamond", 9, "v", 1.0, "#6366F1", .10),
    "BioMatrix": ChartProfile("dot", .23, 1, 2.3, "square", 8, "v", 1.0, "#22C55E", .08),
    "Royal Amethyst": ChartProfile("dot", .09, 1, 2.7, "diamond", 9, "h", 1.12, "#A855F7", .025),
    "Ember Forge": ChartProfile("dash", .20, 2, 2.8, "square", 9, "v", 1.0, "#F97316", .06),
    "Arctic Glass": ChartProfile("dot", .07, 1, 2.4, "circle-open", 8, "h", 1.12, "#06B6D4", .015),
    "Sakura Research": ChartProfile("dot", .08, 1, 2.5, "diamond", 9, "h", 1.12, "#EC4899", .018),
    "Monochrome Pro": ChartProfile("solid", .20, 2, 2.6, "square-open", 8, "h", 1.12, "#111111", 0),
    'Genomic Noir': ChartProfile('dash',0.141,1,2.45,'hexagon',8,'h',1.13,'#00C2A8',0.011),
    'Helix Quantum': ChartProfile('dashdot',0.171,1,2.72,'diamond',9,'v',1.01,'#7C3AED',0.071),
    'CRISPR Cyan': ChartProfile('dot',0.101,1,2.18,'circle-open',8,'h',1.14,'#06B6D4',0.001),
    'Proteome Platinum': ChartProfile('solid',0.161,1,2.34,'square-open',8,'h',1.15,'#64748B',0.031),
    'Cell Atlas': ChartProfile('dot',0.111,1,2.52,'hexagon2',9,'h',1.16,'#14B8A6',0.013),
    'Neural Biotech': ChartProfile('dashdot',0.181,1,2.76,'diamond-open',9,'v',1.02,'#3B82F6',0.081),
    'Quantum Enzyme': ChartProfile('dash',0.131,1,2.27,'triangle-up',8,'h',1.17,'#D97706',0.012),
    'Botanical Circuit': ChartProfile('dot',0.121,1,2.48,'hexagon',9,'h',1.18,'#16A34A',0.014),
    'Clinical Sapphire': ChartProfile('solid',0.091,1,2.16,'circle',8,'h',1.19,'#2563EB',0.002),
    'Molecular Carbon': ChartProfile('solid',0.211,2,2.61,'square',8,'v',1.03,'#E2E8F0',0.041),
    'Spatial Omics': ChartProfile('dot',0.081,1,2.58,'diamond',9,'h',1.2,'#D946EF',0.019),
    'BioLuminescence': ChartProfile('dashdot',0.191,1,2.42,'star',9,'v',1.04,'#10B981',0.061),
    'Pathway Gold': ChartProfile('dash',0.151,1,2.31,'triangle-right',8,'h',1.21,'#D4A017',0.016),
    'Cryo-EM Frost': ChartProfile('dot',0.071,1,2.39,'circle-open',8,'h',1.22,'#38BDF8',0.017),
    'Synthetic Biology': ChartProfile('dot',0.086,1,2.57,'diamond-wide',9,'h',1.23,'#EC4899',0.021),
}


# Step 124 premium theme metadata. Values remain one-to-one so the existing
# catalogue integrity checks continue to detect accidental duplicates.
LIGHT_THEMES.update({
    "Genomic Aurora": LightThemeSpec("#F7F4FF", "#EDE8FD", "rgba(255,255,255,.90)", "#FFFFFF", "#FBFAFF", "#F0ECFF", "#291D4D", "#6B5F89", "rgba(124,58,237,.19)"),
    "Midnight Laboratory": LightThemeSpec("#F2F7FA", "#E5EFF4", "rgba(255,255,255,.96)", "#FFFFFF", "#F8FBFD", "#EAF3F7", "#173444", "#617680", "rgba(56,189,248,.17)"),
    "Clinical White": LightThemeSpec("#F8FCFC", "#EAF6F5", "rgba(255,255,255,.98)", "#FFFFFF", "#FBFEFE", "#EDF8F7", "#12333A", "#5A7278", "rgba(15,118,110,.16)"),
    "Molecular Glass": LightThemeSpec("#F1FAFC", "#E3F3F7", "rgba(255,255,255,.72)", "rgba(255,255,255,.88)", "rgba(249,254,255,.86)", "rgba(232,247,250,.91)", "#153A47", "#5D7A84", "rgba(6,182,212,.20)"),
    "Cyber Biotech": LightThemeSpec("#F0FBF7", "#DFF6EC", "rgba(253,255,254,.96)", "#FFFFFF", "#F7FDFB", "#E5F8F0", "#103A2F", "#59766B", "rgba(0,155,101,.20)"),
    "Oceanic Research": LightThemeSpec("#EFF9FD", "#E0F1F8", "rgba(253,255,255,.95)", "#FFFFFF", "#F7FCFE", "#E7F5FA", "#123C55", "#587487", "rgba(2,132,199,.18)"),
    "Cellular Green": LightThemeSpec("#F1FAF3", "#E2F4E7", "rgba(254,255,254,.96)", "#FFFFFF", "#F8FDF9", "#E8F7EC", "#153C24", "#5E7565", "rgba(22,163,74,.18)"),
    "Protein Violet": LightThemeSpec("#F9F4FF", "#EEE6FA", "rgba(255,253,255,.95)", "#FFFFFF", "#FCF9FF", "#F1EAFB", "#38204E", "#756184", "rgba(139,92,246,.19)"),
    "Minimal Scientific": LightThemeSpec("#FAFBFD", "#EEF2F7", "rgba(255,255,255,.99)", "#FFFFFF", "#FCFDFF", "#F1F5F9", "#172033", "#64748B", "rgba(37,99,235,.14)"),
    "High-Contrast Research": LightThemeSpec("#FFFFFF", "#EFEFEF", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#EAEAEA", "#000000", "#333333", "rgba(0,0,0,.42)"),
})

THEME_META.update({
    "Genomic Aurora": ThemeMeta("Glass", ("Genomics", "Presentation dashboards"), "Effects-heavy", ("Inter", "Century Gothic", "Segoe UI"), "glass"),
    "Midnight Laboratory": ThemeMeta("Professional", ("Low-light laboratory work", "Instrumentation"), "Balanced", ("Segoe UI", "Inter", "Tahoma"), "executive"),
    "Clinical White": ThemeMeta("Clinical", ("Clinical review", "Large validated tables"), "Fast", ("Segoe UI", "Verdana", "Aptos"), "minimal"),
    "Molecular Glass": ThemeMeta("Glass", ("Molecular modelling", "Presentations"), "Effects-heavy", ("Inter", "Century Gothic", "Segoe UI"), "glass"),
    "Cyber Biotech": ThemeMeta("Technology", ("Bioinformatics", "Live workflow monitoring"), "Balanced", ("Inter", "Courier New", "Segoe UI"), "terminal"),
    "Oceanic Research": ThemeMeta("Scientific", ("Long analysis sessions", "Data exploration"), "Balanced", ("Inter", "Verdana", "Segoe UI"), "layered"),
    "Cellular Green": ThemeMeta("Scientific", ("Cell biology", "Assay analytics"), "Balanced", ("Inter", "Trebuchet MS", "Tahoma"), "organic"),
    "Protein Violet": ThemeMeta("Scientific", ("Protein design", "Structural biology"), "Balanced", ("Inter", "Century Gothic", "Segoe UI"), "studio"),
    "Minimal Scientific": ThemeMeta("Minimal", ("Publication review", "Dense scientific tables"), "Fast", ("Aptos", "Segoe UI", "Arial"), "minimal"),
    "High-Contrast Research": ThemeMeta("High contrast", ("Accessibility", "Print and projection"), "Fast", ("Arial", "Verdana", "Courier New"), "brutalist"),
})

CHART_PROFILES.update({
    "Genomic Aurora": ChartProfile("dot", .083, 1, 2.63, "diamond", 9, "h", 1.241, "#7C3AED", .023),
    "Midnight Laboratory": ChartProfile("dash", .173, 1, 2.37, "square", 8, "v", 1.051, "#38BDF8", .073),
    "Clinical White": ChartProfile("solid", .091, 1, 2.13, "circle-open", 8, "h", 1.251, "#0F766E", .003),
    "Molecular Glass": ChartProfile("dot", .071, 1, 2.49, "hexagon", 9, "h", 1.261, "#06B6D4", .027),
    "Cyber Biotech": ChartProfile("dashdot", .213, 1, 2.71, "star", 9, "v", 1.061, "#00B67A", .083),
    "Oceanic Research": ChartProfile("solid", .121, 1, 2.53, "circle", 8, "h", 1.271, "#0284C7", .017),
    "Cellular Green": ChartProfile("dot", .113, 1, 2.47, "hexagon2", 9, "h", 1.281, "#16A34A", .014),
    "Protein Violet": ChartProfile("dashdot", .095, 1, 2.67, "diamond-open", 9, "h", 1.291, "#8B5CF6", .029),
    "Minimal Scientific": ChartProfile("solid", .101, 1, 2.08, "circle", 7, "h", 1.301, "#2563EB", .001),
    "High-Contrast Research": ChartProfile("dash", .251, 2, 2.83, "square-open", 10, "v", 1.071, "#000000", .001),
})


# Step 126 light appearances, discovery metadata and chart identities.
LIGHT_THEMES.update({
    "Lavender Genome": LightThemeSpec("#F8F5FF", "#EEE9FB", "rgba(255,255,255,.91)", "#FFFFFF", "#FCFAFF", "#F1ECFC", "#30244D", "#71678B", "rgba(167,139,250,.20)"),
    "Rose Quartz Laboratory": LightThemeSpec("#FFF7FA", "#F8E9EF", "rgba(255,254,255,.94)", "#FFFFFF", "#FFFBFD", "#FAEDF2", "#472B38", "#806775", "rgba(231,167,196,.22)"),
    "Emerald Muse": LightThemeSpec("#F2FBF7", "#E5F6EE", "rgba(254,255,254,.95)", "#FFFFFF", "#F9FDFB", "#E9F8F1", "#153B2E", "#5D776B", "rgba(95,209,161,.20)"),
    "Bronze Anatomy": LightThemeSpec("#FCF7EF", "#F2E9DB", "rgba(255,254,250,.96)", "#FFFFFF", "#FFFBF5", "#F5ECDF", "#3E2D1E", "#776856", "rgba(185,133,78,.22)"),
    "Obsidian Engineering": LightThemeSpec("#F2F5F8", "#E5EBF1", "rgba(255,255,255,.97)", "#FFFFFF", "#F8FAFC", "#E9EEF4", "#182536", "#627184", "rgba(59,130,246,.19)"),
    "Ink & Blueprint": LightThemeSpec("#F0F7FD", "#E2EEF9", "rgba(254,255,255,.96)", "#FFFFFF", "#F8FBFF", "#E8F3FB", "#173652", "#60768A", "rgba(40,120,200,.20)"),
})

THEME_META.update({
    "Lavender Genome": ThemeMeta("Aesthetic", ("Genomics", "Gentle long-session analysis", "Presentations"), "Balanced", ("Century Gothic", "Inter", "Trebuchet MS"), "studio"),
    "Rose Quartz Laboratory": ThemeMeta("Aesthetic", ("Clinical research", "Molecular biology", "Presentation dashboards"), "Balanced", ("Trebuchet MS", "Century Gothic", "Inter"), "glass"),
    "Emerald Muse": ThemeMeta("Aesthetic", ("Biotechnology", "Cell biology", "Evidence review"), "Balanced", ("Inter", "Georgia", "Trebuchet MS"), "organic"),
    "Bronze Anatomy": ThemeMeta("Art", ("Structural biology", "Anatomy", "Scientific storytelling"), "Balanced", ("Georgia", "Aptos", "Inter"), "editorial"),
    "Obsidian Engineering": ThemeMeta("Art", ("Operations", "Bioinformatics", "Low-light engineering"), "Fast", ("Segoe UI", "Aptos", "Tahoma"), "tech"),
    "Ink & Blueprint": ThemeMeta("Art", ("Workflow design", "Genomics", "Technical review"), "Balanced", ("Aptos", "Courier New", "Segoe UI"), "ledger"),
})

CHART_PROFILES.update({
    "Lavender Genome": ChartProfile("dot", .086, 1, 2.58, "diamond", 9, "h", 1.241, "#A78BFA", .024),
    "Rose Quartz Laboratory": ChartProfile("dot", .075, 1, 2.45, "circle", 9, "h", 1.251, "#E7A7C4", .019),
    "Emerald Muse": ChartProfile("dashdot", .102, 1, 2.46, "hexagon", 9, "h", 1.261, "#5FD1A1", .018),
    "Bronze Anatomy": ChartProfile("dash", .145, 1, 2.34, "triangle-up", 8, "h", 1.271, "#B9854E", .018),
    "Obsidian Engineering": ChartProfile("solid", .188, 2, 2.62, "square", 8, "v", 1.061, "#3B82F6", .050),
    "Ink & Blueprint": ChartProfile("dash", .160, 1, 2.48, "square-open", 8, "h", 1.281, "#2878C8", .035),
})


# Step 148 dedicated light appearances, discovery metadata and chart identities.
LIGHT_THEMES.update({
    "Cyber 3D Bio-Matrix": LightThemeSpec("#F0FCFD", "#E2FAF6", "rgba(255,255,255,.94)", "#FFFFFF", "#F7FEFE", "#E6FBF7", "#0C3A42", "#5A7C82", "rgba(6,182,212,.22)"),
    "Royal 3D Biotech": LightThemeSpec("#F5F3FF", "#EBE5FF", "rgba(255,255,255,.94)", "#FFFFFF", "#FAF8FF", "#EEE8FF", "#2E1A47", "#6D5C87", "rgba(168,85,247,.22)"),
    "Solar Helix": LightThemeSpec("#FFFBE8", "#FFF2B8", "rgba(255,255,252,.97)", "#FFFFFF", "#FFFDF4", "#FFF5C9", "#342A00", "#756A42", "rgba(176,133,0,.24)"),
    "Black Diamond": LightThemeSpec("#F4F5F7", "#E5E8EC", "rgba(255,255,255,.98)", "#FFFFFF", "#FAFBFC", "#E9EDF1", "#0A0B0D", "#5C626C", "rgba(0,0,0,.32)"),
    "Crimson Genome": LightThemeSpec("#FFF4F5", "#FCE2E6", "rgba(255,253,253,.97)", "#FFFFFF", "#FFF9FA", "#FDE8EB", "#4B111A", "#84616A", "rgba(190,18,60,.22)"),
    "Electric Lime": LightThemeSpec("#F8FFE8", "#ECF9C9", "rgba(254,255,251,.97)", "#FFFFFF", "#FBFFF3", "#EFFAD5", "#263600", "#68764A", "rgba(101,140,0,.23)"),
    "Velvet Neon": LightThemeSpec("#FFF3FC", "#F5E2F3", "rgba(255,253,255,.95)", "#FFFFFF", "#FFF9FE", "#F8E8F6", "#4A1644", "#80667E", "rgba(210,20,170,.21)"),
    "Copper Eclipse": LightThemeSpec("#FFF7F1", "#F5E8DE", "rgba(255,254,252,.97)", "#FFFFFF", "#FFFAF6", "#F8ECE3", "#43281B", "#7A695D", "rgba(173,83,40,.22)"),
})

THEME_META.update({
    "Cyber 3D Bio-Matrix": ThemeMeta("Glass", ("Interactive 3D Matrix", "Bioinformatics", "Holographic dashboards"), "Effects-heavy", ("Inter", "Century Gothic", "Segoe UI"), "glass"),
    "Royal 3D Biotech": ThemeMeta("Glass", ("Executive discovery", "Proteomics", "3D Modelling"), "Effects-heavy", ("Century Gothic", "Inter", "Segoe UI"), "glass"),
    "Solar Helix": ThemeMeta("Bold", ("Executive dashboards", "Presentation screens", "High-energy monitoring"), "Balanced", ("Century Gothic", "Inter", "Segoe UI"), "solar"),
    "Black Diamond": ThemeMeta("Luxury", ("Low-light analysis", "Executive review", "Molecular modelling"), "Fast", ("Aptos", "Segoe UI", "Arial"), "faceted"),
    "Crimson Genome": ThemeMeta("Bold", ("Genomics", "Safety monitoring", "Critical review"), "Balanced", ("Inter", "Aptos", "Segoe UI"), "pulse"),
    "Electric Lime": ThemeMeta("Neon", ("Bioinformatics", "Live workflows", "Technical operations"), "Balanced", ("Tahoma", "Courier New", "Segoe UI"), "circuit"),
    "Velvet Neon": ThemeMeta("Luxury", ("Presentations", "AI discovery", "Creative scientific review"), "Effects-heavy", ("Century Gothic", "Inter", "Trebuchet MS"), "velvet"),
    "Copper Eclipse": ThemeMeta("Art", ("Structural biology", "Research storytelling", "Scientific reports"), "Balanced", ("Georgia", "Aptos", "Inter"), "eclipse"),
})

CHART_PROFILES.update({
    "Cyber 3D Bio-Matrix": ChartProfile("dot", .071, 1, 2.65, "diamond", 9, "h", 1.25, "#06B6D4", .03),
    "Royal 3D Biotech": ChartProfile("solid", .085, 1, 2.60, "star", 9, "h", 1.25, "#A855F7", .03),
    "Solar Helix": ChartProfile("dash", .126, 1, 2.66, "triangle-up", 9, "h", 1.311, "#D6A900", .022),
    "Black Diamond": ChartProfile("solid", .224, 2, 2.58, "diamond-open", 8, "v", 1.081, "#F8FAFC", .046),
    "Crimson Genome": ChartProfile("dashdot", .154, 1, 2.73, "diamond", 9, "h", 1.321, "#EF233C", .034),
    "Electric Lime": ChartProfile("dot", .193, 1, 2.69, "star", 10, "v", 1.091, "#78B800", .068),
    "Velvet Neon": ChartProfile("dashdot", .088, 1, 2.77, "hexagon2", 9, "h", 1.331, "#D61FB3", .029),
    "Copper Eclipse": ChartProfile("dash", .137, 1, 2.41, "triangle-right", 8, "h", 1.341, "#B85E32", .025),
})



FONT_METRICS: dict[str, FontMetrics] = {
    "Inter": FontMetrics(700, 400, 600, "-.025em", 1.55, 1.0),
    "Aptos": FontMetrics(700, 400, 600, "-.018em", 1.55, 1.0),
    "Segoe UI": FontMetrics(700, 400, 600, "-.018em", 1.52, 1.0),
    "Arial": FontMetrics(700, 400, 600, "-.012em", 1.50, .98),
    "Verdana": FontMetrics(700, 400, 600, "-.010em", 1.58, .94),
    "Tahoma": FontMetrics(700, 400, 600, "-.012em", 1.50, .96),
    "Trebuchet MS": FontMetrics(700, 400, 600, "-.020em", 1.56, .98),
    "Georgia": FontMetrics(700, 400, 600, "-.012em", 1.62, 1.0),
    "Times New Roman": FontMetrics(700, 400, 600, "0em", 1.58, 1.02),
    "Courier New": FontMetrics(700, 400, 700, "-.025em", 1.48, .90),
    "Century Gothic": FontMetrics(700, 400, 600, "-.035em", 1.55, .92),
}


def light_theme_for(theme_name: str) -> LightThemeSpec:
    return LIGHT_THEMES.get(theme_name, LIGHT_THEMES["Executive"])


def theme_meta_for(theme_name: str) -> ThemeMeta:
    return THEME_META.get(theme_name, THEME_META["Executive"])


def chart_profile_for(theme_name: str) -> ChartProfile:
    return CHART_PROFILES.get(theme_name, CHART_PROFILES["Executive"])


def font_metrics_for(font_name: str) -> FontMetrics:
    return FONT_METRICS.get(font_name, FONT_METRICS["Inter"])


def layout_archetype_css(theme_name: str) -> str:
    """Return compositional desktop rules for the theme's layout archetype."""

    mode = theme_meta_for(theme_name).layout_mode
    rules = {
        "minimal": """
          .bio-hero{max-width:1040px;margin-left:auto!important;margin-right:auto!important;box-shadow:none!important}
          .bio-card,.bio-kpi,.bio-db-card,[data-testid='stMetric']{box-shadow:none!important}
          .bio-board,.bio-db-grid{grid-auto-flow:row dense}
        """,
        "glass": """
          .bio-hero{transform:translateY(-4px)}
          .bio-board>*,.bio-db-grid>*{transform:translateZ(0)}
          .bio-board>*:nth-child(even),.bio-db-grid>*:nth-child(even){margin-top:14px}
        """,
        "tech": """
          .main .block-container{border-left:1px solid color-mix(in srgb,var(--bio-primary) 18%,transparent);border-right:1px solid color-mix(in srgb,var(--bio-primary) 10%,transparent)}
          .bio-hero{display:grid!important;grid-template-columns:minmax(0,1fr) 120px!important;align-items:center!important}
          .bio-hero:after{grid-column:2;justify-self:end}
        """,
        "terminal": """
          .bio-shell-bar,.bio-workspace-context,.bio-command-bar{border-style:dashed!important}
          .bio-card-title,.bio-section-label,.bio-eyebrow{text-transform:uppercase;letter-spacing:.07em!important}
          [data-testid='stDataFrame'],pre,code{font-variant-ligatures:none}
        """,
        "editorial": """
          .bio-hero{max-width:1180px;border-left:7px solid var(--bio-primary)!important;box-shadow:none!important}
          .bio-hero-title{max-width:820px;line-height:1.02!important}.bio-hero-subtitle{max-width:760px}
          .bio-section-label{border-bottom:1px solid var(--bio-border);padding-bottom:.45rem}
        """,
        "ledger": """
          .bio-card,.bio-kpi,.bio-db-card,[data-testid='stMetric']{border-left-width:4px!important}
          .bio-section-label{text-transform:uppercase;letter-spacing:.09em!important}
        """,
        "industrial": """
          .bio-board,.bio-db-grid{gap:.55rem!important}.bio-card,.bio-kpi,.bio-db-card{border-bottom-width:4px!important}
          .bio-hero{min-height:210px;display:flex!important;flex-direction:column!important;justify-content:flex-end!important}
        """,
        "brutalist": """
          .bio-board,.bio-db-grid{gap:0!important}.bio-card,.bio-kpi,.bio-db-card{margin:-1px 0 0 -1px!important}
          .bio-hero{display:grid!important;grid-template-columns:1fr minmax(220px,.35fr)!important}
        """,
        "fluid": """
          .bio-hero{min-height:230px;display:flex!important;flex-direction:column!important;justify-content:center!important}
          .bio-board>*:nth-child(3n+2){transform:translateY(10px)}
        """,
        "atelier": """
          .bio-hero{max-width:1240px;margin-inline:auto!important}.bio-board{grid-auto-flow:row dense}
          .bio-board>*:first-child{grid-column:span 2}
        """,
        "studio": """
          .bio-hero{max-width:1260px;margin-inline:auto!important}.bio-section-label{display:inline-flex;width:auto!important}
          .bio-board>*:nth-child(4n+1){border-top-width:3px!important}
        """,
        "organic": """
          .bio-hero{border-radius:32px 12px 32px 12px!important}.bio-board>*:nth-child(odd){border-radius:24px 10px 24px 10px!important}
        """,
        "layered": """
          .bio-hero{box-shadow:0 10px 0 color-mix(in srgb,var(--bio-primary) 10%,transparent),var(--bio-exp-shadow)!important}
          .bio-board>*:nth-child(even){transform:translateY(6px)}
        """,
        "executive": """
          .bio-kpi-grid,[data-testid='stHorizontalBlock']:has([data-testid='stMetric']){position:relative;z-index:2}
          .bio-card,.bio-kpi,.bio-db-card{border-left-width:3px!important}
        """,
    }
    return rules.get(mode, rules["executive"])


def pairing_for(name: str) -> TypographyPairing:
    return TYPOGRAPHY_PAIRINGS.get(name, TYPOGRAPHY_PAIRINGS["Modern Professional"])


def _hex_rgb(value: str) -> tuple[float, float, float]:
    cleaned = value.strip().lstrip("#")
    if len(cleaned) == 3:
        cleaned = "".join(ch * 2 for ch in cleaned)
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", cleaned):
        raise ValueError(f"Unsupported colour: {value}")
    return tuple(int(cleaned[index:index + 2], 16) / 255 for index in (0, 2, 4))


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4


def luminance(value: str) -> float:
    red, green, blue = _hex_rgb(value)
    return .2126 * _linear(red) + .7152 * _linear(green) + .0722 * _linear(blue)


def contrast_ratio(first: str, second: str) -> float:
    a, b = sorted((luminance(first), luminance(second)), reverse=True)
    return (a + .05) / (b + .05)


def accessible_foreground(*backgrounds: str) -> str:
    candidates = ("#FFFFFF", "#07111F")
    return max(candidates, key=lambda candidate: min(contrast_ratio(candidate, bg) for bg in backgrounds))


def _blend(first: str, second: str, fraction: float) -> str:
    first_rgb = _hex_rgb(first)
    second_rgb = _hex_rgb(second)
    channels = [
        round((left * (1 - fraction) + right * fraction) * 255)
        for left, right in zip(first_rgb, second_rgb, strict=True)
    ]
    return "#" + "".join(f"{channel:02X}" for channel in channels)


def accessible_button_palette(theme: ThemeSpec) -> tuple[str, str, str]:
    """Return foreground and adjusted gradient stops meeting WCAG AA text contrast."""

    options: list[tuple[float, str, str, str]] = []
    for foreground, target in (("#FFFFFF", "#000000"), ("#07111F", "#FFFFFF")):
        adjusted: list[str] = []
        total_shift = 0.0
        for original in (theme.primary, theme.secondary):
            selected = original
            selected_shift = 0.0
            for step in range(21):
                fraction = step / 20
                candidate = _blend(original, target, fraction)
                if contrast_ratio(foreground, candidate) >= 4.5:
                    selected = candidate
                    selected_shift = fraction
                    break
            adjusted.append(selected)
            total_shift += selected_shift
        options.append((total_shift, foreground, adjusted[0], adjusted[1]))
    _, foreground, start, end = min(options, key=lambda item: item[0])
    return foreground, start, end


def theme_button_foreground(theme: ThemeSpec) -> str:
    return accessible_button_palette(theme)[0]


def font_candidates(font: FontSpec) -> tuple[str, ...]:
    values: list[str] = []
    for raw in font.css_stack.split(","):
        candidate = raw.strip().strip('"\'')
        if candidate and candidate.lower() not in {"sans-serif", "serif", "monospace", "system-ui", "ui-sans-serif"}:
            values.append(candidate)
    return tuple(dict.fromkeys(values))


def font_detection_html(font_names: Iterable[str]) -> str:
    payload = []
    for name in font_names:
        spec = FONTS[name]
        payload.append({"name": name, "candidates": font_candidates(spec), "stack": spec.css_stack})
    data = json.dumps(payload)
    return f"""
    <!doctype html><html><head><meta charset='utf-8'><style>
      body{{margin:0;background:transparent;color:#dbeafe;font-family:system-ui,sans-serif}}
      .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(225px,1fr));gap:8px}}
      .card{{border:1px solid rgba(148,163,184,.22);border-radius:12px;padding:10px;background:rgba(15,23,42,.58)}}
      .name{{font-weight:800;font-size:13px}} .status{{font-size:11px;margin-top:5px;line-height:1.45;color:#94a3b8}}
      .ok{{color:#86efac}} .fallback{{color:#fde68a}}
    </style></head><body><div id='grid' class='grid'></div><script>
      const fonts={data};
      const generics=['monospace','serif','sans-serif'];
      function available(name){{
        if(document.fonts && document.fonts.check) return document.fonts.check('16px "'+name.replaceAll('"','')+'"');
        return true;
      }}
      const grid=document.getElementById('grid');
      fonts.forEach(f=>{{
        const hit=f.candidates.find(available);
        const actual=hit || (f.stack.includes('serif')&&!f.stack.includes('sans-serif')?'serif':f.stack.includes('monospace')?'monospace':'system sans-serif');
        const exact=hit===f.candidates[0];
        const card=document.createElement('div'); card.className='card'; card.style.fontFamily=f.stack;
        card.innerHTML=`<div class='name'>${{f.name}} · Aa 0123 α β Δ μ Å</div><div class='status ${{exact?'ok':'fallback'}}'>${{exact?'Primary font available':'Fallback active'}}<br>Rendered candidate: ${{actual}}</div>`;
        grid.appendChild(card);
      }});
    </script></body></html>
    """


def mini_theme_preview_html(theme: ThemeSpec, *, appearance: str = "Dark") -> str:
    meta = theme_meta_for(theme.name)
    light = light_theme_for(theme.name)
    if appearance == "Light":
        bg, surface, text, muted, border = light.background, light.surface, light.text, light.muted, light.border
    else:
        bg, surface, text, muted, border = theme.bg_mid, theme.surface_strong, theme.text, theme.muted, "rgba(148,163,184,.20)"
    button_text = theme_button_foreground(theme)
    _, button_start, button_end = accessible_button_palette(theme)
    best = " · ".join(meta.best_for)
    return f"""
    <div class='bio-mini-theme' style='--m-bg:{bg};--m-surface:{surface};--m-text:{text};--m-muted:{muted};--m-border:{border};--m-primary:{theme.primary};--m-secondary:{theme.secondary};'>
      <div class='bio-mini-sidebar'><span></span><span></span><span class='active'></span><span></span></div>
      <div class='bio-mini-main'>
        <div class='bio-mini-hero'><b>{escape(theme.name)}</b><small>{escape(meta.layout_mode)} · {escape(meta.performance)}</small></div>
        <div class='bio-mini-kpis'><i></i><i></i><i></i></div>
        <div class='bio-mini-row'><div class='bio-mini-chart'></div><div class='bio-mini-table'><em></em><em></em><em></em></div></div>
        <button style='color:{button_text};background:linear-gradient(90deg,{button_start},{button_end})'>Run analysis</button>
        <p>{escape(best)}</p>
      </div>
    </div>
    """


@lru_cache(maxsize=256)
def theme_variable_override_css(
    theme: ThemeSpec,
    *,
    heading_font: FontSpec,
    body_font: FontSpec,
    data_font: FontSpec,
    appearance_mode: str,
    reduce_effects: bool,
) -> str:
    light = light_theme_for(theme.name)
    button_foreground, button_start, button_end = accessible_button_palette(theme)
    heading_metrics = font_metrics_for(heading_font.name)
    body_metrics = font_metrics_for(body_font.name)
    data_metrics = font_metrics_for(data_font.name)
    dark_vars = f"""
      --bio-primary:{theme.primary};--bio-secondary:{theme.secondary};--bio-accent:{theme.accent};
      --bio-glow:{theme.glow};--bio-bg:{theme.bg_start};--bio-bg-soft:{theme.bg_soft};
      --bio-surface:{theme.surface};--bio-surface-strong:{theme.surface_strong};
      --bio-text:{theme.text};--bio-muted:{theme.muted};--bio-border:rgba(148,163,184,.16);
    """
    light_vars = f"""
      --bio-bg:{light.background};--bio-bg-soft:{light.background_soft};--bio-surface:{light.surface};
      --bio-surface-strong:{light.surface_strong};--bio-text:{light.text};--bio-muted:{light.muted};--bio-border:{light.border};
    """
    font_vars = f"""
      --bio-heading-font:{heading_font.css_stack};--bio-body-font:{body_font.css_stack};
      --bio-data-font:{data_font.css_stack};--bio-font-family:{body_font.css_stack};
      --bio-button-foreground:{button_foreground};--bio-button-start:{button_start};--bio-button-end:{button_end};
      --bio-heading-weight:{heading_metrics.heading_weight};--bio-body-weight:{body_metrics.body_weight};
      --bio-navigation-weight:{body_metrics.navigation_weight};--bio-heading-tracking:{heading_metrics.heading_tracking};
      --bio-body-line-height:{body_metrics.body_line_height};--bio-table-scale:{data_metrics.table_scale};
    """
    appearance = light_vars if appearance_mode == "Light" else ""
    system = f"@media(prefers-color-scheme:light){{:root{{{light_vars}}}}}" if appearance_mode == "System" else ""
    effects = """
      .stApp,[data-testid='stAppViewContainer']{background-attachment:scroll!important}
      .bio-card,.bio-kpi,.bio-db-card,.bio-hero,[data-testid='stMetric'],[data-testid='stPlotlyChart'],div[data-testid='stForm'],[data-testid='stSidebar']{backdrop-filter:none!important;-webkit-backdrop-filter:none!important;box-shadow:0 8px 22px rgba(15,23,42,.12)!important}
      .bio-card:hover,.bio-kpi:hover,.bio-db-card:hover,[data-testid='stMetric']:hover{transform:none!important}
    """ if reduce_effects else ""
    return f"""
    <style id='biointel-appearance-engine-v67'>
      :root{{{dark_vars}{font_vars}{appearance}}}
      {system}
      html,body,[class*='css'],.stMarkdown,label,button,input,textarea,select{{font-family:var(--bio-body-font)!important;font-weight:var(--bio-body-weight);line-height:var(--bio-body-line-height)}}
      h1,h2,h3,h4,h5,h6,.bio-hero-title,.bio-card-title,.bio-section-label,.bio-shell-title{{font-family:var(--bio-heading-font)!important;font-weight:var(--bio-heading-weight)!important;letter-spacing:var(--bio-heading-tracking)!important}}
      code,pre,kbd,samp,.bio-kpi-value,.bio-db-value,[data-testid='stMetricValue'],[data-testid='stDataFrame']{{font-family:var(--bio-data-font)!important}}
      [data-testid='stSidebar'] [data-testid='stPageLink'] a,[data-baseweb='tab'],button{{font-weight:var(--bio-navigation-weight)!important}}
      [data-testid='stDataFrame'],[data-testid='stTable']{{font-size:calc(.78rem * var(--bio-table-scale))!important}}
      .bio-theme-meta-v67,.bio-theme-copy-v67,.bio-font-meta-v67,.bio-caption,[data-testid='stCaptionContainer']{{font-size:clamp(12px,.68rem,15px)!important}}
      [data-testid='stButton'] button,[data-testid='stDownloadButton'] button,[data-testid='stFormSubmitButton'] button{{font-size:clamp(14px,.76rem,16px)!important;min-height:44px!important}}
      [data-testid='stButton'] button[kind='primary'],[data-testid='stFormSubmitButton'] button[kind='primary']{{color:var(--bio-button-foreground)!important;background:linear-gradient(105deg,var(--bio-button-start),var(--bio-button-end))!important}}
      {effects}
    </style>
    """
