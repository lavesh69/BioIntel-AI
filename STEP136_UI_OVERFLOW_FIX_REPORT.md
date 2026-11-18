# BioIntel AI Step 136 — UI Overflow and Scientific Content Visibility Fix

## Fixed issues

1. **Oversized circular question-mark panels removed**
   - The four tall `st.metric` columns shown for Rows, Columns, Missing cells and Duplicates were replaced with one compact import-summary strip.
   - Imported records and readiness information now remain above the fold.

2. **Giant heading-link/chain icon fixed**
   - The reactive scientific browser was using `st.html` with generic `svg`, `button` and `table` CSS selectors.
   - That CSS could leak into the Streamlit page and resize heading anchor icons and metric help icons.
   - The browser visual is now isolated in an iframe.
   - Defensive CSS size limits were added for heading-link and metric SVG icons.

3. **Imported data is visible by default**
   - “Preview imported records” is now expanded automatically in both scientific renderer generations.
   - The preview no longer remains hidden behind a collapsed panel after import.

4. **Home/module shell ratio corrected**
   - The desktop shell ratio was rebalanced so Status, Timeline, Alerts and View receive sufficient width.
   - Action-control proportions were adjusted.
   - Popover labels are forced to remain horizontal with ellipsis protection instead of wrapping one character per line.

5. **Motion/overflow safeguards**
   - Heading and metric SVGs have bounded dimensions and animation/transform protection.
   - The compact summary is responsive and wraps cleanly at smaller widths.

## Verification

- Modified Python files compiled successfully.
- Full project Python compilation completed successfully.
- New UI overflow regression tests: **4/4 passed**.
- SQLite integrity checks: **36/36 databases healthy**.
- Existing browser-runtime tests requiring Streamlit were not executed in this build environment because Streamlit is not installed here.
