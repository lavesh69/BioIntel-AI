# BioIntel Education Phase 2 Accessibility Report

## Implemented controls

- Native Streamlit semantic controls, labels, buttons, dialogs, forms, tables and navigation are used.
- Material icons are paired with visible text; status is not communicated by color alone.
- Each chart includes a text alternative describing point count, total and peak.
- Metric explanations expose calculation provenance and limitations.
- Empty states use a heading plus actionable explanation.
- Reduced-motion preference is persisted in session state and avoids adding motion-only experiences.
- Dense information is split into selectable views and no more than four metric columns.
- Presentation Mode preserves the synthetic disclosure as a visible warning.

## Remaining qualification

A formal WCAG 2.2 AA audit with keyboard-only, screen-reader and contrast tooling was not performed in this constrained run. Native Streamlit semantics reduce risk but do not substitute for assistive-technology testing in the deployment environment.