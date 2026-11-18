# BioIntel AI Step 143 — Research Planning Feature Density Peak

## Scope

Step 143 increases feature and visual depth across all **20 Research Planning pages** while preserving the Step 141 and Step 142 workflows.

- Step 143 peak feature contracts: **716**
- Step 143 signature visual contracts: **160**
- Module-specific validation checks: **80**
- Existing Step 141 scientific visuals preserved: **128**
- Step 142 advanced feature assignments preserved: **220**
- Product version preserved: **13.2.0**

## Deep specialist workspaces

1. **Research Planning Command Center** — multi-study portfolio readiness, weighted policies, critical blockers and cross-study comparison.
2. **Research Budget & Participant Burden** — exchange rates, inflation, monthly cash flow, contingency, cost drivers and subgroup burden equity.
3. **Study Protocol Designer** — schedule-of-activities matrix, participant journey and amendment redline.
4. **Data Collection & CRF Designer** — variable uniqueness, skip-logic dependency cycles, missing dependencies and automated rule test cases.
5. **Cohort Eligibility Builder** — safe computable eligibility rules, attrition funnel and site feasibility.
6. **Endpoint Strategy** — endpoint priority, burden/value balance and composite endpoint contribution.
7. **Randomization & Allocation** — minimization allocation, deterministic seed, entropy and stratum imbalance audit.
8. **Statistical Analysis Plan** — TFL shell generation and dataset → model → output lineage.
9. **Biostatistics Studio** — outcome/design/model compatibility and assumption sensitivity.
10. **Synthetic Cohort Lab** — correlated synthetic participants, MNAR-like missingness, site heterogeneity and privacy-utility comparison.

## Shared linked visual system

Every Research Planning module receives:

- Objective → endpoint → estimand → variable → model → output trace.
- Effect-size, sample-size, budget and duration sensitivity.
- Complete/consistent/reviewed/locked/evidence-backed/export-ready heatmap.
- Field-level change-impact propagation.
- Feature-density inventory and implementation status.
- Validation checklist and machine-readable peak feature manifest.

## Stability and optimization

- Deterministic random seeds for simulation and allocation.
- Bounded cohort sizes, budget horizons and numerical ranges.
- Duplicate participant, study, variable and analysis-ID rejection.
- Invalid rule operators and missing source columns blocked before analysis.
- CRF dependency-cycle detection.
- Safe handling of invalid schedule, budget and composite endpoint inputs.
- Individual panels fail independently with stable recovery IDs.
- Profile and allocation SHA-256 digests.
- Existing row and visual rendering guards preserved.

## Verification completed

- Distinct completed selected tests: **146 passed, 0 failures**
- Step 143 focused tests: **9 passed**
- Step 141–143 Research Planning tests: **26 passed**
- Python compilation: **1,069/1,069 passed**
- SQLite databases: **40/40 healthy**
- Database rows inspected: **108,493**
- Foreign-key violations: **0**
- Research Planning pages: **20**, missing pages **0**

## Environment boundary

Live Streamlit browser interaction and physical clean-Windows qualification were not available in the current Linux interpreter. Three legacy UI test files that directly import Streamlit could not be collected here and are not counted as passes. Windows qualification launchers are included in the package.

## Scientific boundary

The new calculators, simulations and readiness checks are research-planning decision support. They do not independently establish statistical validity, ethical approval, regulatory compliance, clinical suitability or successful study execution.
