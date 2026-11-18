# BioIntel AI UI Design Guide

## Design direction

The interface uses a midnight scientific-workspace aesthetic with:

- Deep navy backgrounds
- Glass-like surfaces
- Aurora purple, cyan and emerald accents
- Rounded 13–28 px corners
- Soft shadows
- Strong typographic hierarchy
- Low-noise data presentation

## Shared theme module

```text
src/biointel/ui/theme.py
```

Reusable helpers:

- `apply_theme()`
- `hero()`
- `section_title()`
- `feature_card()`
- `badge()`
- `empty_state()`
- `plotly_layout()`

## Appearance Studio

The user can choose among 17 complete UI themes, including 10 additional themes:

- Midnight Graphite
- Nordic Frost
- Solarized Lab
- Deep Space
- BioMatrix
- Royal Amethyst
- Ember Forge
- Arctic Glass
- Sakura Research
- Monochrome Pro

The studio also provides 11 text stacks: Inter plus 10 additional local-first fonts
(Aptos, Segoe UI, Arial, Verdana, Tahoma, Trebuchet MS, Georgia,
Times New Roman, Courier New and Century Gothic).

Themes control accents, app backgrounds, sidebar, surfaces, hero panels, glow and
Plotly colours. Font selection applies to interface text and Plotly charts. No remote
font CDN is required. Density, motion, contrast, appearance mode, text scale and
colour-vision chart palettes remain independently configurable.

Preferences are stored per local UI profile in
`reports/ui_profiles/<profile>/preferences.json`.

## Accessibility

- High contrast strengthens muted text and borders
- Reduced motion disables transitions and animations
- Controls preserve native Streamlit labels and keyboard behaviour
- Colour is not the only status indicator
- Mobile breakpoints reduce page padding and hero size

## Adding a new page

After `st.set_page_config`, call:

```python
from biointel.ui.theme import apply_theme
apply_theme()
```

For a premium page header:

```python
from biointel.ui.theme import hero

hero(
    "Clear page title",
    "One-sentence explanation.",
    eyebrow="Module name",
    chips=["Capability one", "Capability two"],
)
```

## Step 12 experience layer

### Persistent preferences

Theme, font, density, motion, contrast, favourites and recent pages are stored per profile in `reports/ui_profiles/<profile>/preferences.json`.

### Global Quick Dock

Every page exposes Command Center, Quick Start, Workflow Dashboard, Appearance Studio, favourites and recent tools in the sidebar.

### Command Center

The searchable catalog is defined in `src/biointel/ui/navigation.py`.

### Report Studio

Printable HTML is produced by `src/biointel/reports/workspace_report.py`.

## Step 13 professional visual layer

- Executive palette is the default professional theme
- Clinical palette supports a biomedical green/teal direction
- `executive_kpis()` renders board-style decision metrics
- `status_chips()` renders compact evidence indicators
- `timeline()` renders privacy-safe operational activity
- `professional_strip()` provides calm executive context

## Step 14 governance visual layer

- Regulatory palette combines controlled navy, gold and teal accents
- Governance Hub uses professional registers and evidence matrices
- Evidence Package Studio uses package KPIs and integrity summaries
- Release Readiness uses a transparent control matrix and lineage graph
- Governance alerts reuse critical/warning status semantics consistently

## Step 15 data-ready visual layer

- Data & Model Library centralises pack downloads and model metrics
- Training screens default to meaningful bundled datasets
- Predictor screens expose molecule and protein selectors
- Batch screens expose a one-click 250-row sample
- Synthetic-data warnings remain visually persistent
- Benchmark tables distinguish task, training pack and source row count

## Step 17 double-data visual layer

- Double Data ML separates pack-v4 metrics from overall champions
- 32,000-row downloads and templates are first-class actions
- Honest comparison copy explains why more data may not improve every metric

## Professional UI v2

- Responsive database card grid
- Command bars and insight callouts
- Density indicators and executive surfaces
- Intelligence-first Home and Command Center hierarchy
- Improved data tables, hover depth and mobile breakpoints
