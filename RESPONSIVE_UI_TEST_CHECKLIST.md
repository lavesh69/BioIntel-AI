# Responsive UI Test Checklist

Release: `15.6.0-Step220.0-WINDOWS-V20.3`
Runtime: Streamlit `1.58.0`
Status: PASS

## Global shell

- [x] Global page configuration remains `layout="wide"`.
- [x] Responsive CSS loads after every visual and density layer.
- [x] Stable `data-testid` and `aria-expanded` selectors are used.
- [x] No generated Emotion class is used by the new layout source.
- [x] Expanded sidebar remains usable and visually intact.
- [x] Collapse button is visible, clickable, and uses the Material icon font.
- [x] Collapsed sidebar width, flex basis, border, and shadow are zero.
- [x] Main area and header grow to the released sidebar width.
- [x] No hard-coded left margin or duplicate sidebar subtraction remains.
- [x] Main block has no unintended desktop maximum-width cap.
- [x] Page gutter and header clearance use centralized variables.

## Viewport matrix

- [x] 2560px expanded and collapsed
- [x] 1920px expanded and collapsed
- [x] 1440px expanded and collapsed
- [x] 1366px expanded and collapsed
- [x] 1024px expanded and collapsed
- [x] 768px expanded and collapsed
- [x] 390px expanded and collapsed
- [x] Zero document-level horizontal overflow at every tested size/state

## Mobile and tablet

- [x] Collapsed main workspace remains full viewport width.
- [x] Expanded sidebar becomes a fixed overlay and does not shrink main content.
- [x] Brand content starts below the fixed application header.
- [x] Search control uses full available width.
- [x] Status controls reflow to two usable columns.
- [x] Pin, Navigate, and Help controls remain readable and clickable.
- [x] Breadcrumb text wraps without forcing horizontal scrolling.
- [x] No character-wide or vertical button labels remain.
- [x] Discovery Lab Platform no longer hides its shell with page-local CSS.

## Data and visual surfaces

- [x] Plotly wrapper resizes after sidebar toggle.
- [x] Plotly graph div resizes after sidebar toggle.
- [x] Dataframe wrapper resizes after sidebar toggle.
- [x] Dataframe canvas resizes after sidebar toggle.
- [x] Forms and uploaders are bounded to workspace width.
- [x] Tabs and columns have `min-width: 0`.
- [x] Charts and tables do not retain a 260px dead band after collapse.
- [x] Resize observer is mounted once per page and has zero visual height.

## Appearance and functionality

- [x] Dark mode shell verified.
- [x] Light mode shell verified.
- [x] Dark mode restored after test.
- [x] Sidebar navigation preserved.
- [x] Global search popover preserved.
- [x] Status, alerts, view, pin, navigation, and help controls preserved.
- [x] No application exception on Command Center.
- [x] No application exception on Workflow Dashboard.
- [x] No application exception on Discovery Lab Platform.

## Source regression checks

- [x] Modified Python files compile.
- [x] New layout regression assertions pass.
- [x] Existing overflow regression assertions pass.
- [x] Existing desktop UI assertions pass.
- [x] `100vw` is absent from the authoritative responsive shell.
- [x] Negative-margin layout hacks are absent.
- [x] Page-local Discovery shell selectors are absent.

## Re-run procedure

1. Start the app with Streamlit `1.58.0`.
2. Open Command Center and Workflow Dashboard.
3. Test each viewport listed above.
4. Toggle the sidebar in both directions.
5. Confirm sidebar and main bounding rectangles.
6. Confirm `document.documentElement.scrollWidth - innerWidth` equals zero.
7. Confirm Plotly, dataframe, and canvas widths change with the main workspace.
8. Open Discovery Lab Platform and repeat mobile expanded/collapsed checks.
9. Switch between dark and light appearance modes.
10. Run `tests/test_fullscreen_responsive_layout.py` in a test environment with `pytest`.
