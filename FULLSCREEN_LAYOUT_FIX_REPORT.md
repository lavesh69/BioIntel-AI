# Full-Screen Layout Fix Report

Release: `15.6.0-Step220.0-WINDOWS-V20.3`
Validation date: `2026-07-23`
Runtime validated: Streamlit `1.58.0`

## Scope

The responsive shell fix applies globally through `apply_theme()` and therefore covers the home page and every registered Streamlit module. No scientific workflow, dataset, model, page, navigation item, dark/light preference, or sidebar function was removed.

## Root causes

1. Several historical theme layers fixed the sidebar at `286px`, `260px`, or `244px`.
2. Main content had repeated `1440px`, `1480px`, and `1560px` maximum-width caps.
3. The Discovery Lab page injected a separate mobile shell using `100vw`, `left: 0`, and forced sidebar hiding.
4. The sidebar collapse control inherited the wrong icon font from a legacy sidebar button rule.
5. Zero-height theme injection elements still consumed vertical flex gaps, creating excessive space above the first visible header.
6. Nested Streamlit column rows compressed search, status, and action controls into character-wide mobile columns.
7. Plotly, dataframe, and canvas surfaces needed a resize notification after sidebar transitions.

## Implemented architecture

The authoritative shell rules now live in:

`src/biointel/ui/responsive_layout.css`

The stylesheet is loaded after all palette, aesthetic, workbench, density, and premium visual layers. It uses stable Streamlit semantic selectors and attributes:

- `[data-testid="stAppViewContainer"]`
- `[data-testid="stSidebar"][aria-expanded="true|false"]`
- `[data-testid="stMain"]`
- `[data-testid="stHeader"]`
- `[data-testid="stMainBlockContainer"]`
- `[data-testid="stHorizontalBlock"]`
- `[data-testid="stColumn"]`

No generated Emotion class is used as a selector.

The global variables are:

- `--bio-sidebar-expanded-width`
- `--bio-sidebar-current-width`
- `--bio-page-gutter`
- `--bio-workspace-max-width`
- `--bio-app-header-height`
- `--bio-workspace-top-gutter`
- `--bio-layout-transition`

Expanded desktop sidebars remain in normal flex flow. Collapsed sidebars become an exact zero-width flex item with no border or shadow. Mobile expanded sidebars use a fixed overlay, leaving the main workspace at full viewport width.

## Responsive data surfaces

Plotly, Vega-Lite, dataframe, data editor, table, form, uploader, canvas, and shared BioIntel workspace wrappers now receive explicit `width: 100%`, bounded `max-width`, and `min-width: 0` rules.

A Streamlit Components v2 observer watches sidebar attributes and main-wrapper width. It dispatches resize notifications after state changes and explicitly asks Plotly to resize its graph divs. The observer is zero-height and removed from visual layout flow.

## Measured results

| Viewport | Expanded sidebar | Expanded main | Collapsed sidebar | Collapsed main | Horizontal overflow |
|---:|---:|---:|---:|---:|---:|
| 2560 | 260 | 2300 | 0 | 2560 | 0 |
| 1920 | 260 | 1660 | 0 | 1920 | 0 |
| 1440 | 260 | 1180 | 0 | 1440 | 0 |
| 1366 | 260 | 1106.4 | 0 | 1366.4 | 0 |
| 1024 | 244 | 780 | 0 | 1024 | 0 |
| 768 | 244 | 524 | 0 | 768 | 0 |
| 390 | 272 overlay | 390.4 | 0 | 390.4 | 0 |

All measurements are CSS pixels captured from the running Streamlit `1.58.0` DOM.

Workflow Dashboard data-surface measurements at 1440px:

| Surface | Sidebar expanded | Sidebar collapsed | Growth |
|---|---:|---:|---:|
| Plotly wrapper | 1049 | 1309 | 260 |
| Plotly graph | 1033 | 1293 | 260 |
| Dataframe | 1117.8 | 1377.8 | 260 |
| Dataframe canvas | 1116 | 1376 | 260 |

## Mobile shell correction

At 390px:

- Search control: `356px`
- Status controls: two columns at `173.6px` each
- Pin/Navigate/Help: three columns at `112.8px` each
- Brand starts at `y=72px`, below the 60px application header
- Discovery Lab heading: `356px` wide
- Horizontal overflow: `0`

## Verification

- Python syntax compilation passed for all modified Python files.
- 11 direct regression assertions passed across the new layout tests and existing desktop/overflow suites.
- Full `pytest` execution was not available because `pytest` is not installed in the packaged application environment.
- Live browser QA passed on Command Center, Workflow Dashboard, and Discovery Lab Platform.
- Dark and light appearance modes both retained the responsive shell; dark mode was restored after testing.
- No Streamlit exception appeared on the corrected pages.

## Removed code

Only the conflicting page-local mobile CSS block in `pages/270_Discovery_Lab_Platform.py` was removed. No feature implementation, scientific data, model, report, page, or navigation entry was removed.
