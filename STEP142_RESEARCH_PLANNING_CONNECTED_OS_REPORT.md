# BioIntel AI Step 142 — Research Planning Connected Operating System

## Scope

Step 142 upgrades the Step 141 Research Planning suite from independent specialist tools into a connected planning operating system.

- Research Planning pages: **20**
- Existing specialist modules augmented: **18**
- New orchestration modules: **2**
- Existing Step 141 scientific visuals preserved: **128**
- Advanced feature assignments: **220**
- Advanced visual specifications: **119**
- Module-specific critical consistency checks: **73**
- Standards-readiness requirements: **25**

## New modules

1. **Research Planning Command Center** — unified readiness, blockers, actions, standards matrix and digital-thread health.
2. **Research Budget & Participant Burden Studio** — participant time/travel/procedure burden, probabilistic costs and site capacity.

## Shared planning operating system

### Unified Research Digital Thread

- Protocol, objective, endpoint, estimand, sample-size, visit, biospecimen, CRF, analysis, risk, budget and preregistration entities.
- Cross-module traceability links.
- Orphan-entity detection.
- Downstream impact traversal.
- Immutable audit events.

### Standards-readiness validator

Local, non-certifying readiness profiles for:

- SPIRIT-style protocol content
- ICH E6(R3)-style quality by design
- ICH E9(R1)-style estimands and sensitivity analyses
- CDISC PRM/CDASH/SDTM/ADaM readiness
- FHIR/eSource variable mapping

### Estimand Builder

- Treatment condition
- Population
- Variable/endpoint
- Intercurrent events and strategies
- Population summary
- Estimator
- Sensitivity analyses
- Objective-to-estimator trace visual

### Scenario and amendment intelligence

- Optimistic, base, conservative and stress Monte Carlo scenarios.
- Recruitment, dropout, missingness, assay failure, cost and timeline uncertainty.
- Protocol amendment comparison.
- Affected-module identification.
- Revalidation requirement and change checksum.

### Interoperability

- CDASH-style variable mapping.
- SDTM-domain and ADaM-dataset readiness.
- FHIR Questionnaire export.
- ODM-style XML export.
- Define-XML readiness checks.

### Collaboration and assumptions

- Assumption source, owner, confidence and sensitivity bounds.
- Open/resolved discussion threads.
- Comments and mentions.
- Proposed changes with accept/reject decisions.
- Conflict-of-interest field.

### Scientific verification

- Cross-module consistency audit.
- Independent sample-size calculation comparison.
- Formula panel.
- Python, R and SAS-compatible verification script skeletons.
- Boundary-condition matrix.

### Participant burden and budget

- Visit, travel, questionnaire, blood-volume, digital-access and discomfort burden.
- Probabilistic budget simulation with uncertainty and contingency.
- Site workload utilization and overload detection.

## Reliability and optimization

- SQLite writes use the managed BioIntel connection contract.
- Foreign keys, busy timeouts and connection cleanup are enforced.
- Monte Carlo iterations are bounded.
- Planning inputs are bounded by the existing 250,000-row analysis and 5,000-row visualization guards.
- Errors are isolated to the affected panel.
- Existing reproducibility ZIPs now include advanced planning contracts and standards requirements.
- All new pages use direct source bootstrapping and the shared visual suite.

## Verification completed

- Distinct selected tests: **138 passed, 0 failures**
- Python compilation: **1,066/1,066 passed**
- SQLite databases: **40/40 healthy**
- Database rows inspected: **108,493**
- Foreign-key violations: **0**
- Managed SQLite connection audit: **passed**
- Page bootstrap audit: **passed**
- Research Planning navigation pages: **20**, missing pages **0**
- Release source files before packaging: **4,188**

## Honest boundary

The standards layer is a local readiness and traceability implementation. It does not claim regulatory approval, ethical approval, CDISC certification, successful trial conduct or statistical validity for every real protocol. Live Streamlit browser automation and physical Windows qualification could not be executed in the current Linux build interpreter; target-machine launchers are included for local verification.
