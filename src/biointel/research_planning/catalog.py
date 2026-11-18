from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisualSpec:
    key: str
    title: str
    source: str
    kind: str
    x: str | None = None
    y: str | None = None
    color: str | None = None
    size: str | None = None
    description: str = ""


@dataclass(frozen=True)
class PlanningModule:
    key: str
    page_number: int
    title: str
    icon: str
    summary: str
    purpose: str
    required_columns: tuple[str, ...]
    accepted_inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    workflow: tuple[str, ...]
    features: tuple[str, ...]
    visuals: tuple[VisualSpec, ...]
    handoffs: tuple[str, ...]
    boundary: str
    keywords: tuple[str, ...]


def _v(key: str, title: str, source: str, kind: str, x: str | None = None, y: str | None = None,
       color: str | None = None, size: str | None = None, description: str = "") -> VisualSpec:
    return VisualSpec(key, title, source, kind, x, y, color, size, description)


PLANNING_MODULES: tuple[PlanningModule, ...] = (
    PlanningModule(
        "study_protocol_designer", 205, "Study Protocol Designer", "📋",
        "Build a complete, reviewable research protocol from objectives through visits, endpoints, deviations and amendments.",
        "Turn a research question into a structured protocol with explicit objectives, populations, procedures, responsibilities, completeness checks and versioned exports.",
        ("section", "owner", "status", "completeness", "risk", "due_day"),
        ("CSV/TSV protocol section table", "Excel protocol tracker", "BioIntel starter template"),
        ("protocol completeness report", "participant journey", "visit schedule", "risk register", "versioned protocol manifest"),
        ("Define the research question and objectives", "Specify population, endpoints and procedures", "Assign owners and review completeness", "Lock and export the protocol package"),
        ("Research question builder", "Primary and secondary objectives", "Inclusion and exclusion criteria", "Endpoint definitions", "Visit and sampling schedule", "Control and blinding plan", "Deviation handling", "Amendment history", "Protocol completeness scoring", "DOCX/PDF-ready structured manifest"),
        (
            _v("protocol_completion", "Protocol completeness by section", "primary", "bar", "section", "completeness", "status"),
            _v("protocol_risk", "Section risk and readiness", "primary", "scatter", "completeness", "risk", "status", "due_day"),
            _v("protocol_timeline", "Protocol development timeline", "timeline", "timeline", "start_day", "end_day", "owner"),
            _v("protocol_status", "Review status distribution", "primary", "donut", "status"),
            _v("protocol_heatmap", "Section × requirement readiness", "matrix", "heatmap", "requirement", "section"),
            _v("protocol_owner", "Owner workload", "primary", "bar", "owner", "due_day", "status"),
            _v("protocol_funnel", "Protocol readiness funnel", "funnel", "funnel", "stage", "records"),
            _v("protocol_radar", "Protocol quality dimensions", "quality", "radar", "dimension", "score"),
        ),
        ("Biostatistics, Power & Experimental Design Studio", "Statistical Analysis Plan Studio", "Pre-Registration & Reproducibility Studio"),
        "The generated protocol is a planning aid and requires discipline-specific, ethical, legal and statistical review before use in a real study.",
        ("protocol", "study design", "objectives", "visits", "inclusion", "exclusion", "amendment"),
    ),
    PlanningModule(
        "sample_size_power_studio", 206, "Sample Size & Statistical Power Studio", "📈",
        "Calculate transparent sample-size scenarios across continuous, binary, survival, repeated-measures and clustered designs.",
        "Compare assumptions, multiplicity, dropout, allocation and precision targets with simulation-backed sensitivity analysis.",
        ("scenario", "design", "effect_size", "alpha", "power", "dropout", "allocation_ratio"),
        ("CSV/TSV scenario table", "Excel design assumptions", "BioIntel starter template"),
        ("sample-size table", "power curves", "sensitivity grid", "assumption warnings", "reproducible calculation manifest"),
        ("Choose outcome and design family", "Enter justified assumptions", "Compare sensitivity and simulation", "Export the locked sample-size rationale"),
        ("Continuous, binary, count and survival outcomes", "Superiority, non-inferiority and equivalence", "Paired and unpaired designs", "Cluster and repeated-measures designs", "Dropout inflation", "Multiplicity adjustment", "Precision-based sample size", "Simulation-based power", "Scenario comparison", "Assumption provenance"),
        (
            _v("power_curve", "Power curve across sample sizes", "sensitivity", "line", "total_sample_size", "achieved_power", "scenario"),
            _v("sample_size", "Required recruitment by scenario", "primary", "bar", "scenario", "total_sample_size", "design"),
            _v("effect_heatmap", "Effect size × power sensitivity", "grid", "heatmap", "target_power", "effect_size"),
            _v("dropout", "Dropout impact on recruitment", "dropout", "line", "dropout", "total_sample_size", "scenario"),
            _v("allocation", "Allocation ratio sensitivity", "allocation", "line", "allocation_ratio", "total_sample_size", "scenario"),
            _v("precision", "Precision versus sample size", "precision", "line", "sample_size", "ci_half_width", "scenario"),
            _v("scenario_parallel", "Assumption trade-off landscape", "primary", "parallel", color="design"),
            _v("assumption_radar", "Scenario assumption quality", "quality", "radar", "dimension", "score"),
        ),
        ("Study Protocol Designer", "Clinical Trial Design Studio", "Statistical Analysis Plan Studio"),
        "Planning calculations depend on assumptions. Confirmatory or regulated studies require a qualified statistician and protocol-specific methods.",
        ("sample size", "power", "effect size", "dropout", "noninferiority", "equivalence", "cluster trial"),
    ),
    PlanningModule(
        "clinical_trial_design_studio", 207, "Clinical Trial Design Studio", "🏥",
        "Design phase-aware clinical trials with arms, cohorts, interim decisions, endpoints, recruitment and safety monitoring.",
        "Stress-test parallel, crossover, factorial, dose-escalation and adaptive trial structures before protocol finalisation.",
        ("cohort", "arm", "participants", "start_day", "end_day", "response_rate", "dropout_rate"),
        ("CSV/TSV cohort plan", "Excel trial schema", "BioIntel starter template"),
        ("trial schema", "cohort flow", "recruitment forecast", "interim decision plan", "site and milestone summary"),
        ("Select phase and trial architecture", "Define arms, cohorts and endpoints", "Model recruitment, dropout and interim rules", "Export the trial design package"),
        ("Phase I–IV templates", "Parallel, crossover and factorial design", "Dose escalation", "Adaptive design", "Randomisation and stratification", "Interim analysis", "Stopping boundaries", "Endpoint hierarchy", "Safety monitoring", "Site and country planning", "Recruitment assumptions", "Trial milestones"),
        (
            _v("trial_schema", "Trial arm and cohort schema", "primary", "sunburst", "arm", "cohort", "participants"),
            _v("recruitment", "Recruitment forecast", "recruitment", "line", "month", "cumulative_enrolled", "arm"),
            _v("cohort_flow", "Participant flow", "funnel", "funnel", "stage", "participants"),
            _v("dose_ladder", "Dose-escalation ladder", "primary", "bar", "cohort", "participants", "arm"),
            _v("interim", "Interim decision boundaries", "interim", "line", "information_fraction", "boundary", "decision"),
            _v("dropout", "Expected dropout by arm", "primary", "bar", "arm", "dropout_rate", "cohort"),
            _v("timeline", "Trial milestone timeline", "timeline", "timeline", "start_day", "end_day", "arm"),
            _v("trial_radar", "Trial design readiness", "quality", "radar", "dimension", "score"),
        ),
        ("Sample Size & Statistical Power Studio", "Randomization, Blinding & Allocation Studio", "Synthetic Cohort & Trial Simulation Lab"),
        "This module supports research planning only. Trial design requires ethics, regulatory, clinical, statistical and operational review.",
        ("clinical trial", "phase", "dose escalation", "adaptive", "interim", "recruitment", "cohort"),
    ),
    PlanningModule(
        "experimental_design_doe", 208, "Experimental Design & DoE Workbench", "🧪",
        "Create and analyse factorial, response-surface, screening and optimal experimental designs for laboratory and process studies.",
        "Explore factor effects, interactions, confounding, design efficiency and response surfaces with reproducible randomisation.",
        ("run", "factor_a", "factor_b", "factor_c", "response"),
        ("CSV/TSV design matrix", "Excel DoE run sheet", "BioIntel starter template"),
        ("design matrix", "effect estimates", "interaction table", "response surface", "optimisation candidates"),
        ("Define factors and levels", "Generate or import the design", "Fit effects and inspect diagnostics", "Export the randomised run sheet and analysis manifest"),
        ("Full and fractional factorial designs", "Response-surface methodology", "Central composite design", "Box–Behnken design", "Screening designs", "Blocking and randomisation", "Replicate allocation", "Confounding analysis", "Design efficiency", "Optimal design", "Interaction estimation", "Response optimisation"),
        (
            _v("design_matrix", "Design matrix", "primary", "heatmap", "factor", "run"),
            _v("effects", "Standardised factor effects", "effects", "bar", "term", "effect", "sign"),
            _v("pareto", "Pareto chart of effects", "effects", "bar", "term", "abs_effect", "sign"),
            _v("interaction", "Factor interaction map", "interaction", "heatmap", "factor_2", "factor_1"),
            _v("surface", "Response surface", "surface", "contour", "factor_a", "factor_b"),
            _v("predicted", "Observed versus predicted response", "predictions", "scatter", "predicted", "observed", "run"),
            _v("residuals", "Residual diagnostics", "predictions", "scatter", "predicted", "residual", "run"),
            _v("design_radar", "Design quality dimensions", "quality", "radar", "dimension", "score"),
        ),
        ("Biostatistics, Power & Experimental Design Studio", "Sampling & Biospecimen Planning Studio", "Research Timeline, Milestones & Dependencies Studio"),
        "DoE outputs are exploratory unless factor ranges, measurement systems, model assumptions and confirmatory runs are prospectively justified.",
        ("doe", "factorial", "response surface", "box behnken", "central composite", "screening design"),
    ),
    PlanningModule(
        "randomization_blinding_allocation", 209, "Randomization, Blinding & Allocation Studio", "🔀",
        "Generate reproducible allocation schedules with strata, variable blocks, concealment and balance diagnostics.",
        "Plan simple, block, stratified, cluster and unequal allocation while separating concealed treatment codes from operational schedules.",
        ("participant_id", "stratum", "site", "arm", "sequence"),
        ("CSV/TSV participant list", "Excel eligibility list", "BioIntel starter template"),
        ("allocation schedule", "concealment manifest", "balance diagnostics", "unblinding file", "audit report"),
        ("Import eligible participants", "Select allocation and blinding rules", "Generate and audit the schedule", "Lock concealed and operational exports separately"),
        ("Simple randomisation", "Variable block randomisation", "Stratified randomisation", "Cluster allocation", "Unequal ratios", "Concealed allocation", "Secure seed generation", "Emergency unblinding", "Re-randomisation controls", "Treatment-code generation", "Balance audit", "Immutable manifest"),
        (
            _v("arm_balance", "Allocation balance by arm", "primary", "bar", "arm", "participants", "site"),
            _v("strata", "Stratum × arm balance", "matrix", "heatmap", "arm", "stratum"),
            _v("sites", "Site × arm balance", "site_matrix", "heatmap", "arm", "site"),
            _v("sequence", "Allocation sequence", "sequence", "scatter", "sequence", "arm", "stratum"),
            _v("blocks", "Block-size distribution", "blocks", "bar", "block_size", "blocks", "site"),
            _v("imbalance", "Cumulative allocation imbalance", "imbalance", "line", "sequence", "imbalance", "stratum"),
            _v("concealment", "Blinding and concealment status", "quality", "bar", "dimension", "score"),
            _v("allocation_radar", "Allocation quality dimensions", "quality", "radar", "dimension", "score"),
        ),
        ("Clinical Trial Design Studio", "Cohort Definition & Eligibility Builder", "Pre-Registration & Reproducibility Studio"),
        "Production randomisation requires independent control, secure seed and code handling, documented concealment and approved emergency-unblinding procedures.",
        ("randomization", "allocation", "blinding", "stratified", "blocks", "concealment"),
    ),
    PlanningModule(
        "cohort_eligibility_builder", 210, "Cohort Definition & Eligibility Builder", "👥",
        "Define reproducible eligibility rules, estimate feasible cohorts and explain every inclusion or exclusion decision.",
        "Combine demographic, clinical, laboratory, genomic and temporal rules with overlap, missingness and feasibility diagnostics.",
        ("participant_id", "age", "sex", "biomarker", "diagnosis", "eligible", "exclusion_reason"),
        ("CSV/TSV candidate cohort", "Excel screening log", "BioIntel starter template"),
        ("eligible cohort", "screen-failure reasons", "rule impact table", "overlap analysis", "versioned cohort definition"),
        ("Import candidate participants", "Define and order eligibility rules", "Inspect exclusions and missingness", "Lock and export the cohort definition"),
        ("Inclusion and exclusion rule builder", "Demographic criteria", "Disease and phenotype definitions", "Laboratory thresholds", "Medication criteria", "Genomic biomarkers", "Time-window rules", "Missing-data policy", "Cohort overlap detection", "Feasibility estimate", "Rule version history", "Record-level explanation"),
        (
            _v("cohort_funnel", "Eligibility funnel", "funnel", "funnel", "stage", "participants"),
            _v("exclusions", "Exclusion reasons", "exclusions", "bar", "exclusion_reason", "participants"),
            _v("age", "Age distribution by eligibility", "primary", "histogram", "age", color="eligible"),
            _v("biomarker", "Biomarker distribution", "primary", "box", "eligible", "biomarker", "diagnosis"),
            _v("rule_impact", "Rule impact", "rules", "waterfall", "rule", "removed"),
            _v("missingness", "Eligibility data missingness", "missingness", "heatmap", "field", "group"),
            _v("overlap", "Eligibility overlap", "overlap", "upset", "rule", "participants"),
            _v("cohort_radar", "Cohort definition quality", "quality", "radar", "dimension", "score"),
        ),
        ("Clinical Trial Design Studio", "Research Feasibility & Recruitment Planner", "Synthetic Cohort & Trial Simulation Lab"),
        "Eligibility estimates depend on the quality and representativeness of the source cohort and do not replace clinical adjudication.",
        ("cohort", "eligibility", "inclusion", "exclusion", "screening", "feasibility"),
    ),
    PlanningModule(
        "endpoint_outcome_strategy", 211, "Endpoint & Outcome Strategy Studio", "🎯",
        "Prioritise primary, secondary and exploratory endpoints with burden, validity, missingness and multiplicity controls.",
        "Build a transparent endpoint hierarchy and measurement plan aligned to the study question and estimand.",
        ("endpoint", "type", "priority", "measurement_burden", "sensitivity", "specificity", "missingness_risk"),
        ("CSV/TSV endpoint inventory", "Excel outcome strategy", "BioIntel starter template"),
        ("endpoint hierarchy", "measurement schedule", "burden analysis", "multiplicity plan", "adjudication workflow"),
        ("List candidate outcomes", "Score validity, burden and missingness", "Define hierarchy and multiplicity", "Export the locked endpoint strategy"),
        ("Primary, secondary and exploratory endpoints", "Composite endpoints", "Surrogate endpoint review", "Measurement frequency", "Endpoint hierarchy", "Minimal clinically important difference", "Responder definitions", "Competing risks", "Missing endpoint strategy", "Multiplicity control", "Endpoint adjudication", "Estimand alignment"),
        (
            _v("endpoint_priority", "Endpoint priority ranking", "primary", "bar", "endpoint", "priority_score", "type"),
            _v("burden_validity", "Measurement burden versus validity", "primary", "scatter", "measurement_burden", "validity_score", "type", "priority_score"),
            _v("hierarchy", "Endpoint hierarchy", "hierarchy", "sunburst", "type", "endpoint", "priority_score"),
            _v("missingness", "Missingness risk", "primary", "bar", "endpoint", "missingness_risk", "type"),
            _v("correlation", "Endpoint correlation plan", "matrix", "heatmap", "endpoint_2", "endpoint_1"),
            _v("timeline", "Outcome measurement schedule", "timeline", "timeline", "start_day", "end_day", "endpoint"),
            _v("decision", "Endpoint decision matrix", "decision", "heatmap", "criterion", "endpoint"),
            _v("endpoint_radar", "Endpoint strategy readiness", "quality", "radar", "dimension", "score"),
        ),
        ("Study Protocol Designer", "Biomarker Study Planning Studio", "Statistical Analysis Plan Studio"),
        "Endpoint selection must be justified by clinical or scientific relevance, measurement validity and a prespecified analysis strategy.",
        ("endpoint", "outcome", "estimand", "composite", "surrogate", "multiplicity", "adjudication"),
    ),
    PlanningModule(
        "biomarker_study_planning", 212, "Biomarker Study Planning Studio", "🧬",
        "Plan diagnostic, prognostic and predictive biomarker studies from discovery through independent validation.",
        "Align cohorts, assays, cut-offs, pre-analytics, calibration and validation evidence before model or assay development begins.",
        ("biomarker", "stage", "evidence", "assay_readiness", "validation_status", "effect_size"),
        ("CSV/TSV biomarker inventory", "Excel evidence tracker", "BioIntel starter template"),
        ("biomarker development funnel", "evidence maturity", "cohort split plan", "cut-off sensitivity", "validation roadmap"),
        ("Define intended biomarker use", "Review evidence and assay readiness", "Plan discovery and validation cohorts", "Lock the analysis and validation roadmap"),
        ("Diagnostic, prognostic and predictive modes", "Discovery and validation cohorts", "Cut-off strategy", "Pre-analytical variables", "Assay requirements", "Batch-effect planning", "Internal and external validation", "Calibration planning", "Subgroup analysis", "Assay qualification", "Locked analysis plan", "Evidence maturity"),
        (
            _v("development_funnel", "Biomarker development funnel", "funnel", "funnel", "stage", "biomarkers"),
            _v("maturity", "Evidence maturity by biomarker", "primary", "bar", "biomarker", "maturity_score", "stage"),
            _v("assay_evidence", "Assay readiness versus evidence", "primary", "scatter", "assay_readiness", "evidence", "validation_status", "effect_size"),
            _v("cohort_split", "Discovery and validation cohort split", "cohort", "donut", "cohort"),
            _v("cutoff", "Cut-off sensitivity", "cutoff", "line", "threshold", "performance", "metric"),
            _v("validation", "Validation status matrix", "matrix", "heatmap", "validation_stage", "biomarker"),
            _v("timeline", "Biomarker validation roadmap", "timeline", "timeline", "start_day", "end_day", "stage"),
            _v("biomarker_radar", "Biomarker plan readiness", "quality", "radar", "dimension", "score"),
        ),
        ("Endpoint & Outcome Strategy Studio", "Clinical Trial Biomarker & Patient Stratification Studio", "Statistical Analysis Plan Studio"),
        "A planning score does not establish biomarker validity. Independent analytical and clinical validation remain required.",
        ("biomarker", "diagnostic", "prognostic", "predictive", "cutoff", "validation cohort", "assay"),
    ),
    PlanningModule(
        "sampling_biospecimen_planning", 213, "Sampling & Biospecimen Planning Studio", "🧫",
        "Plan collection, aliquoting, storage, shipping and retention for biospecimen-intensive studies.",
        "Calculate sample volumes, aliquot counts, storage demand and collection schedules while exposing pre-analytical risks.",
        ("sample_type", "visit", "participants", "volume_ml", "aliquots", "storage_temp", "failure_rate"),
        ("CSV/TSV sampling plan", "Excel biospecimen schedule", "BioIntel starter template"),
        ("sampling calendar", "volume and aliquot forecast", "storage capacity plan", "shipping plan", "failure contingency"),
        ("Define specimen types and visits", "Estimate volume and aliquots", "Assign storage and shipping conditions", "Export the biospecimen operations package"),
        ("Sample type selection", "Collection time points", "Aliquot planning", "Storage conditions", "Freeze–thaw limits", "Shipping plan", "Sample-volume estimation", "Batch and plate allocation", "Chain of custody", "Retention schedule", "Biobank capacity", "Failure contingency"),
        (
            _v("sampling_calendar", "Sampling calendar", "timeline", "timeline", "start_day", "end_day", "sample_type"),
            _v("volume", "Total volume by specimen", "primary", "bar", "sample_type", "total_volume_ml", "visit"),
            _v("aliquots", "Aliquot demand", "primary", "bar", "sample_type", "total_aliquots", "storage_temp"),
            _v("storage", "Storage capacity by temperature", "storage", "treemap", "storage_temp", "sample_type", "total_aliquots"),
            _v("failure", "Expected sample loss", "primary", "bar", "sample_type", "expected_failures", "visit"),
            _v("journey", "Biospecimen journey", "journey", "sankey", "from", "to", "samples"),
            _v("plate", "Plate and batch allocation", "matrix", "heatmap", "batch", "sample_type"),
            _v("biospecimen_radar", "Biospecimen plan readiness", "quality", "radar", "dimension", "score"),
        ),
        ("Data Collection & CRF Designer", "Lab Instrument Import Center", "Research Timeline, Milestones & Dependencies Studio"),
        "Volume and storage calculations must be checked against assay-specific requirements, local SOPs, biosafety and biobank constraints.",
        ("biospecimen", "sample collection", "aliquot", "storage", "shipping", "biobank", "chain of custody"),
    ),
    PlanningModule(
        "data_collection_crf_designer", 214, "Data Collection & CRF Designer", "🗂️",
        "Design structured case-report forms, data dictionaries and validation rules across visits and study domains.",
        "Create database-ready variables with controlled vocabularies, units, conditional logic and completeness checks.",
        ("variable", "domain", "data_type", "required", "visit", "validation_rule", "completeness"),
        ("CSV/TSV variable dictionary", "Excel CRF specification", "BioIntel starter template"),
        ("CRF schema", "variable dictionary", "validation-rule map", "visit matrix", "data-quality readiness report"),
        ("Define domains and visits", "Create variables and controlled values", "Add validation and conditional rules", "Export the database-ready CRF package"),
        ("Case report form builder", "Variable dictionary", "Data types and units", "Required fields", "Validation rules", "Controlled vocabularies", "Repeat visits", "Conditional fields", "Query rules", "Missing-data reasons", "Import/export schema", "Database-ready package"),
        (
            _v("domain_variables", "Variables by study domain", "primary", "bar", "domain", "variables", "visit"),
            _v("visit_matrix", "Visit × domain data collection", "matrix", "heatmap", "domain", "visit"),
            _v("completeness", "Variable specification completeness", "primary", "bar", "variable", "completeness", "domain"),
            _v("types", "Data type distribution", "primary", "donut", "data_type"),
            _v("required", "Required versus optional fields", "required", "bar", "domain", "required_fields", "visit"),
            _v("validation", "Validation rule coverage", "validation", "bar", "domain", "rule_coverage", "visit"),
            _v("dependencies", "Conditional field dependencies", "dependencies", "sankey", "from", "to", "rules"),
            _v("crf_radar", "CRF readiness", "quality", "radar", "dimension", "score"),
        ),
        ("Sampling & Biospecimen Planning Studio", "Statistical Analysis Plan Studio", "Dataset Registry & Lineage"),
        "A CRF specification requires privacy, security, data-management, clinical and regulatory review before deployment.",
        ("crf", "data collection", "case report form", "variable dictionary", "validation rules", "visits"),
    ),
    PlanningModule(
        "statistical_analysis_plan", 215, "Statistical Analysis Plan Studio", "📊",
        "Build a versioned statistical analysis plan linking populations, endpoints, models, covariates, multiplicity and sensitivity analyses.",
        "Translate the protocol into explicit analysis decisions, assumptions, tables, figures and listings before outcome review.",
        ("analysis", "endpoint", "population", "model", "covariates", "multiplicity", "status"),
        ("CSV/TSV analysis inventory", "Excel SAP matrix", "BioIntel starter template"),
        ("analysis matrix", "endpoint-to-model map", "sensitivity plan", "TFL shells", "locked SAP manifest"),
        ("Define analysis populations", "Map endpoints to models and estimands", "Specify sensitivity and multiplicity", "Review, lock and export the SAP"),
        ("Analysis populations", "Primary and secondary models", "Covariate definition", "Transformation rules", "Missing-data methods", "Multiple-testing correction", "Subgroup analyses", "Sensitivity analyses", "Interim analysis", "Model assumptions", "Table/figure/listing shells", "Version locking"),
        (
            _v("analysis_status", "Analysis plan status", "primary", "bar", "analysis", "readiness_score", "status"),
            _v("endpoint_model", "Endpoint-to-model matrix", "matrix", "heatmap", "model", "endpoint"),
            _v("population", "Analyses by population", "primary", "bar", "population", "analyses", "status"),
            _v("multiplicity", "Multiplicity strategy", "multiplicity", "sunburst", "multiplicity", "endpoint", "analyses"),
            _v("sensitivity", "Sensitivity analysis coverage", "sensitivity", "bar", "endpoint", "sensitivity_count", "status"),
            _v("assumptions", "Model assumption coverage", "assumptions", "heatmap", "assumption", "analysis"),
            _v("timeline", "SAP review and lock timeline", "timeline", "timeline", "start_day", "end_day", "status"),
            _v("sap_radar", "SAP completeness", "quality", "radar", "dimension", "score"),
        ),
        ("Study Protocol Designer", "Endpoint & Outcome Strategy Studio", "Pre-Registration & Reproducibility Studio"),
        "The SAP must be reviewed and approved before unblinded outcome analysis and must reflect protocol, estimand and regulatory requirements.",
        ("sap", "statistical analysis plan", "estimand", "covariate", "multiplicity", "sensitivity analysis", "tfl"),
    ),
    PlanningModule(
        "research_feasibility_recruitment", 216, "Research Feasibility & Recruitment Planner", "📍",
        "Forecast enrolment, screen failures, site activation, dropout, cost and study-completion probability.",
        "Compare site and scenario assumptions with deterministic and simulation-based recruitment forecasts.",
        ("site", "eligible_pool", "screen_rate", "monthly_recruitment", "startup_months", "dropout_rate", "cost_per_subject"),
        ("CSV/TSV site feasibility table", "Excel recruitment assumptions", "BioIntel starter template"),
        ("recruitment forecast", "site ranking", "completion probability", "screening funnel", "cost and rescue scenarios"),
        ("Import site assumptions", "Set target and uncertainty", "Simulate recruitment and dropout", "Select sites and export the feasibility package"),
        ("Eligible population estimation", "Site recruitment rates", "Screen-failure rate", "Dropout assumptions", "Recruitment scenarios", "Competing-study effects", "Seasonality", "Site activation delays", "Rescue strategies", "Timeline estimation", "Cost estimation", "Completion probability"),
        (
            _v("recruitment", "Cumulative recruitment forecast", "forecast", "line", "month", "cumulative_enrolled", "scenario"),
            _v("site_rank", "Site feasibility ranking", "primary", "bar", "site", "feasibility_score", "risk_band"),
            _v("funnel", "Screening and enrolment funnel", "funnel", "funnel", "stage", "participants"),
            _v("completion", "Study completion probability", "simulation", "line", "month", "completion_probability", "scenario"),
            _v("cost", "Cost versus enrolment", "primary", "scatter", "projected_enrolment", "projected_cost", "risk_band", "eligible_pool"),
            _v("startup", "Site activation delays", "primary", "bar", "site", "startup_months", "risk_band"),
            _v("fan", "Recruitment uncertainty fan", "fan", "area", "month", "median_enrolled", "scenario"),
            _v("feasibility_radar", "Feasibility dimensions", "quality", "radar", "dimension", "score"),
        ),
        ("Cohort Definition & Eligibility Builder", "Clinical Trial Design Studio", "Research Timeline, Milestones & Dependencies Studio"),
        "Recruitment forecasts are scenario-based estimates and must be updated with real site data, competing studies and operational constraints.",
        ("feasibility", "recruitment", "site", "enrollment", "screen failure", "dropout", "cost"),
    ),
    PlanningModule(
        "research_timeline_dependencies", 217, "Research Timeline, Milestones & Dependencies Studio", "🗓️",
        "Plan tasks, dependencies, critical paths, resources and risk-adjusted timelines across a research programme.",
        "Convert a task inventory into a dependency-aware roadmap with milestone, delay and resource diagnostics.",
        ("task", "phase", "duration_days", "predecessor", "owner", "progress", "risk"),
        ("CSV/TSV task plan", "Excel project schedule", "BioIntel starter template"),
        ("Gantt schedule", "critical path", "milestone map", "resource load", "delay sensitivity"),
        ("Import tasks and dependencies", "Validate the dependency graph", "Calculate schedule and critical path", "Export the baseline and risk-adjusted roadmap"),
        ("Study phases", "Milestones", "Task dependencies", "Critical path", "Resource assignment", "Approval dependencies", "Sample/data availability", "Risk-adjusted timeline", "Delay simulation", "Baseline versions", "Planned-vs-actual", "Resource conflicts"),
        (
            _v("gantt", "Research programme Gantt", "timeline", "timeline", "start_day", "end_day", "phase"),
            _v("critical", "Critical path tasks", "primary", "bar", "task", "duration_days", "critical"),
            _v("dependencies", "Task dependency network", "dependencies", "sankey", "from", "to", "duration_days"),
            _v("progress", "Planned versus actual progress", "primary", "bar", "task", "progress", "phase"),
            _v("resource", "Owner workload", "resource", "bar", "owner", "workload_days", "phase"),
            _v("risk", "Delay risk heatmap", "risk_matrix", "heatmap", "phase", "owner"),
            _v("milestones", "Milestone timeline", "milestones", "scatter", "day", "milestone", "status"),
            _v("timeline_radar", "Schedule readiness", "quality", "radar", "dimension", "score"),
        ),
        ("Study Protocol Designer", "Research Risk & Mitigation Planner", "Project Portfolio"),
        "Schedule estimates depend on accurate dependencies, resource availability and external approvals. They are not contractual commitments.",
        ("timeline", "gantt", "milestone", "dependency", "critical path", "resource", "delay"),
    ),
    PlanningModule(
        "research_risk_mitigation", 218, "Research Risk & Mitigation Planner", "⚠️",
        "Identify, score, mitigate and monitor scientific, statistical, assay, data and operational research risks.",
        "Prioritise risks by probability, impact and detectability while tracking ownership, triggers and residual exposure.",
        ("risk", "category", "probability", "impact", "mitigation_status", "owner"),
        ("CSV/TSV risk register", "Excel risk tracker", "BioIntel starter template"),
        ("risk matrix", "mitigation board", "residual risk", "trigger plan", "risk trend"),
        ("Import or create risks", "Score probability and impact", "Assign mitigations, owners and triggers", "Monitor residual risk and export the register"),
        ("Scientific risks", "Recruitment risks", "Assay risks", "Data-quality risks", "Operational risks", "Statistical risks", "Probability and impact", "Mitigation ownership", "Trigger thresholds", "Contingency actions", "Residual risk", "Review history"),
        (
            _v("risk_matrix", "Probability × impact risk matrix", "primary", "scatter", "probability", "impact", "category", "risk_score"),
            _v("priority", "Top research risks", "primary", "bar", "risk", "risk_score", "category"),
            _v("residual", "Residual risk after mitigation", "primary", "bar", "risk", "residual_score", "mitigation_status"),
            _v("category", "Risk exposure by category", "category", "bar", "category", "total_risk", "mitigation_status"),
            _v("mitigation", "Mitigation status", "primary", "donut", "mitigation_status"),
            _v("owner", "Risk ownership", "owner", "bar", "owner", "open_risks", "category"),
            _v("bowtie", "Risk-to-control pathways", "controls", "sankey", "from", "to", "weight"),
            _v("risk_radar", "Risk management readiness", "quality", "radar", "dimension", "score"),
        ),
        ("Research Timeline, Milestones & Dependencies Studio", "Study Protocol Designer", "Activity & Risk Center"),
        "Risk scoring supports prioritisation but does not replace domain expert judgement, safety management or organisational governance.",
        ("risk", "mitigation", "contingency", "probability", "impact", "residual risk", "trigger"),
    ),
    PlanningModule(
        "evidence_gap_literature_planning", 219, "Evidence Gap & Literature Planning Studio", "🔎",
        "Map existing evidence, contradictions and unanswered questions to justify and prioritise new research.",
        "Structure PICO/PECO questions, evidence quality, population and endpoint gaps, contradictions and search strategies.",
        ("question", "population", "intervention", "comparator", "outcome", "evidence_count", "quality", "contradiction"),
        ("CSV/TSV evidence inventory", "Excel literature map", "BioIntel starter template"),
        ("evidence-gap matrix", "evidence pyramid", "contradiction map", "priority ranking", "search strategy manifest"),
        ("Define PICO/PECO questions", "Inventory and grade evidence", "Identify contradictions and gaps", "Prioritise research and export the search plan"),
        ("Research question decomposition", "PICO/PECO framework", "Evidence inventory", "Contradictory findings", "Evidence quality", "Missing populations", "Missing endpoints", "Knowledge-gap ranking", "Search strategy", "Study justification", "Citation-backed rationale", "Research priority scoring"),
        (
            _v("gap_priority", "Research gap priority", "primary", "bar", "question", "priority_score", "quality"),
            _v("evidence_pyramid", "Evidence quality pyramid", "quality_counts", "funnel", "quality", "records"),
            _v("gap_matrix", "Population × outcome evidence gaps", "matrix", "heatmap", "outcome", "population"),
            _v("contradiction", "Contradiction versus evidence volume", "primary", "scatter", "evidence_count", "contradiction", "quality", "priority_score"),
            _v("pico", "PICO/PECO evidence map", "pico", "sankey", "from", "to", "evidence_count"),
            _v("coverage", "Evidence coverage by domain", "coverage", "bar", "domain", "coverage_score", "quality"),
            _v("timeline", "Evidence publication timeline", "timeline", "line", "year", "records", "quality"),
            _v("evidence_radar", "Evidence planning readiness", "quality", "radar", "dimension", "score"),
        ),
        ("Study Protocol Designer", "Internet Research Hub", "Pre-Registration & Reproducibility Studio"),
        "Evidence maps depend on the completeness and quality of the imported literature inventory and do not constitute a systematic review by themselves.",
        ("evidence gap", "literature", "pico", "peco", "contradiction", "research question", "search strategy"),
    ),
    PlanningModule(
        "preregistration_reproducibility", 220, "Pre-Registration & Reproducibility Studio", "🔒",
        "Lock hypotheses, outcomes, exclusions, sample-size rationale and analysis decisions before observing study outcomes.",
        "Create checksum-bound preregistration packages, track deviations and compare planned versus executed analyses.",
        ("item", "section", "locked", "status", "planned_value", "executed_value", "deviation_reason"),
        ("CSV/TSV preregistration checklist", "Excel analysis lock", "BioIntel starter template"),
        ("locked plan manifest", "protocol checksum", "deviation log", "planned-vs-executed comparison", "registry-ready package"),
        ("Define hypotheses and confirmatory decisions", "Lock the protocol and analysis plan", "Record justified deviations", "Export the reproducibility package"),
        ("Hypothesis locking", "Primary endpoint locking", "Sample-size justification", "Exclusion rules", "Analysis-plan locking", "Random seed capture", "Protocol checksum", "Deviation tracking", "Registry-ready export", "Registered-report checklist", "Reproducibility manifest", "Planned-vs-executed comparison"),
        (
            _v("lock_status", "Preregistration lock status", "primary", "bar", "section", "locked_items", "status"),
            _v("completeness", "Preregistration completeness", "primary", "bar", "item", "completeness", "section"),
            _v("deviations", "Deviation severity", "deviations", "bar", "item", "severity", "section"),
            _v("planned_executed", "Planned versus executed alignment", "alignment", "heatmap", "comparison", "item"),
            _v("timeline", "Plan lock and deviation timeline", "timeline", "timeline", "day", "event", "status"),
            _v("sections", "Locked content by section", "primary", "donut", "section"),
            _v("audit", "Reproducibility audit trail", "audit", "sankey", "from", "to", "events"),
            _v("prereg_radar", "Reproducibility readiness", "quality", "radar", "dimension", "score"),
        ),
        ("Study Protocol Designer", "Statistical Analysis Plan Studio", "Evidence Package Studio"),
        "A preregistration package improves transparency but does not guarantee methodological quality, ethical approval or successful replication.",
        ("preregistration", "reproducibility", "protocol lock", "deviation", "registered report", "analysis plan"),
    ),
)

MODULE_BY_KEY = {module.key: module for module in PLANNING_MODULES}


def get_module(key: str) -> PlanningModule:
    try:
        return MODULE_BY_KEY[key]
    except KeyError as exc:
        raise KeyError(f"Unknown research planning module: {key}") from exc
