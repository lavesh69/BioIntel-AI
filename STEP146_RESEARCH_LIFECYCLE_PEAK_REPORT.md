# BioIntel AI Step 146 — Research Lifecycle Peak

## Scope

Step 146 extends the Step 145 stable application from research planning into the complete research lifecycle. The existing 20 Research Planning modules remain available and now include a lifecycle-and-governance readiness panel. Four new specialist modules cover participant protection, FAIR data management, interim monitoring and research dissemination.

## New modules

1. Research Ethics, Consent & Participant Protection Studio
2. Research Data Management & FAIR Planning Studio
3. Data Monitoring, Interim Review & Safety Studio
4. Publication, Dissemination & Knowledge Translation Studio

The Research Planning catalogue now contains 24 modules.

## Ethics, consent and participant protection

- Consent-element readiness and evidence coverage
- Privacy-sensitive item detection
- Vulnerable-population safeguard review
- Risk-weighted unresolved requirement ranking
- Missing owner and evidence-reference detection
- High-risk blocker escalation
- Domain and population readiness summaries
- Persistent review decisions and immutable plan versions

## Research data management and FAIR planning

- Findable, Accessible, Interoperable and Reusable scoring
- Stable identifier and metadata-standard coverage
- Repository, licence and access-state planning
- Retention and data-steward ownership checks
- Backup-copy and encryption controls
- Preferred scientific-format readiness
- Asset and data-type summaries
- Complete reproducibility bundle

## Interim monitoring and safety

- Serious, unresolved and reportable event review
- Optional enrolled-arm population denominators
- Arm event-rate comparisons and confidence intervals
- Prespecified serious-event review threshold
- Severity and relatedness controlled-term checks
- Cumulative event timelines
- Immediate review and arm-level signal queues
- Clear boundary that the module does not make medical or study-stopping decisions

## Publication, dissemination and knowledge translation

- Publication and stakeholder-output inventory
- Audience and channel coverage
- Open-access, lay-summary, data-statement and code-availability planning
- Accessibility review tracking
- Overdue output detection
- Open-science and readiness scoring
- Publication/dissemination timeline
- Structured review, versioning and audit export

## Cross-module lifecycle integration

Every existing Research Planning module now includes an end-to-end lifecycle panel covering:

- Scientific question
- Protocol and design
- Participant protection
- Data management
- Statistical analysis
- Operational feasibility
- Interim monitoring
- Reproducibility
- Dissemination

The Planning Command Center expands from eight to twelve readiness dimensions when lifecycle scores are supplied. Ethics, FAIR data, monitoring and dissemination scores below the configured threshold become actionable blockers.

## Digital thread

New lifecycle plan node types are supported:

- Ethics plan
- Data-management plan
- Monitoring plan
- Publication plan

Completed lifecycle analyses can create deterministic digital-thread nodes and link to an existing protocol node. Digital-thread failures are isolated and cannot invalidate a completed specialist analysis.

## Optimization and safety

- 100 MB interactive lifecycle upload limit
- 2,000-row browser editing limit; larger tables remain read-only while full bounded analysis continues
- 100,000-row engine limits
- Fifteen-minute bounded in-process result cache with maximum entry count
- Deterministic hashes for inputs, tables, manifests and export bundles
- Duplicate identifier blocking
- Invalid date, probability, retention, backup and controlled-term checks
- Panel-level and digital-thread failure isolation
- Stable recovery identifiers
- Existing Step 145 startup, database, cache, job and diagnostic hardening preserved

## Visuals

Each new module includes three specialist data-linked visualizations and the five-view Research Planning visual suite. Existing modules gain a lifecycle readiness radar and gap table.

## Completed verification

- 152 selected scientific, research-planning, stability and regression tests passed
- 46 Step 141–146 Research Planning tests passed
- 8 Step 146 focused tests passed
- 1,090 Python files passed source compilation
- 228/228 registered navigation entries point to existing files
- 24 Research Planning modules registered
- 40/40 SQLite databases passed quick integrity checks
- 108,493 database rows inspected
- 0 foreign-key violations

## Environment boundary

Live Streamlit browser automation was not executed because Streamlit and its compatible Linux runtime dependencies are not installed in the build environment. Physical Windows 10/11 installation, display scaling, antivirus, sleep/resume and external service testing require target-machine execution. Ethics approval, legal compliance, monitoring-committee decisions and publication acceptance cannot be generated or certified by software.
