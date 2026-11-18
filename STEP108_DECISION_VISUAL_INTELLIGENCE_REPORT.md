# BioIntel AI Step 108 — Decision Visual Intelligence

## Release summary

- Version: **11.0.0**
- Phase 1 modules upgraded: **8**
- Phase 2 modules upgraded: **6**
- Total upgraded modules: **14**
- Decision-focused visual views: **70**
- Visual choices per module: **5**

Step 108 extends the scientific visual workbench with decision-oriented validation, evidence, lineage, governance, release, provider and reference-database views. The design uses lazy rendering: all five visual choices remain available, but only the selected view is constructed at a time.

## Phase 1 — Validation and decision intelligence

### Clinical Validation

- Clinical evidence pyramid
- Validation cohort flow
- Endpoint forest plot
- Quality-risk matrix
- Validation record coverage

### External Validation

- External performance summary
- Feature-drift ranking
- Calibration or agreement
- Error and confidence distribution
- Validation data-quality funnel

### Benchmark Leakage

- Leakage overlap profile
- Leakage-risk matrix
- Unique-entity retention
- Release decision gauge
- Train and test composition

### Dti Validation

- Implementation versus evidence
- Evidence-gap heatmap
- Qualification status composition
- Capability gap ranking
- Validation milestone funnel

### Data Readiness

- Metadata versus scientific readiness
- Dataset readiness matrix
- Readiness blocker profile
- Dataset lineage coverage
- Provider data coverage

### Model Evaluation

- Model metric comparison
- Validation-to-test agreement
- Generalisation delta heatmap
- Data support versus performance
- Model provenance composition

### Experiment Registry

- Experiment performance leaderboard
- Cross-validation stability
- Hyperparameter search landscape
- Runtime versus performance
- Validation requirement status

### Dataset Registry

- Logical versus physical datasets
- Dataset lineage network
- Schema and QC coverage
- Storage and format composition
- Readiness issue matrix

## Phase 2 — Evidence, governance and infrastructure intelligence

### Knowledge Graph

- Evidence-confidence distribution
- Relationship type composition
- Citation coverage by relation
- Conflict and research-gap profile
- Entity-type connectivity

### Evidence Package

- Package readiness profile
- Evidence file composition
- Claim-to-artifact coverage
- Integrity and completeness matrix
- Package blocker ranking

### Governance

- Governance control matrix
- Project risk heatmap
- Open findings trend
- Approval and review timeline
- Compliance coverage profile

### Release Gate

- Release gate waterfall
- Blocker severity profile
- Validation evidence matrix
- Readiness scorecard
- Required versus available evidence

### Provider Integration

- Provider connection health
- Provider latency and availability
- Query and record activity
- Failure-type distribution
- Provider coverage matrix

### Reference Manager

- Reference storage profile
- Release and version timeline
- Reference integrity matrix
- Asset lifecycle events
- Compatibility and activation status

## Performance and reliability design

- One selected visual renders at a time; hidden alternatives do not construct Plotly figures.
- SQLite-backed visual queries use a 60-second cache keyed by database modification time.
- Visual builders return safe empty states when a registry, table or optional field is unavailable.
- Every chart card includes scientific interpretation, method context, underlying-data preview and CSV export.
- Large tables are bounded before chart construction to prevent browser and memory overload.
- Existing 1 GB upload transport limit and background-safe staging remain unchanged.

## Verification completed

- **70/70** visual builders passed direct data-level construction tests.
- **14/14** upgraded Streamlit pages passed isolated default-load runtime tests.
- **70/70** selector options were verified across those pages.
- **23/23** Step 105–108 targeted regression tests passed.
- **7/7** application self-tests passed in build-runtime mode.
- Python compilation passed for source, pages, scripts and tests.
- Ruff was unavailable in the build environment, so no lint-pass claim is made.

## Scientific boundary

These views improve interpretation of existing data, evidence and operational records. They do not manufacture independent clinical validation, regulatory approval, provider releases, wet-lab confirmation or external scientific evidence.
