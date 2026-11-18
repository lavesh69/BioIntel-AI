from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdvancedPlanningProfile:
    module_key: str
    standards: tuple[str, ...]
    advanced_features: tuple[str, ...]
    advanced_visuals: tuple[str, ...]
    consistency_links: tuple[str, ...]
    critical_checks: tuple[str, ...]


_SHARED_STANDARDS = (
    "BioIntel research digital-thread contract",
    "SPIRIT-style protocol readiness profile",
    "ICH E6(R3)-style quality-by-design readiness profile",
    "ICH E9(R1)-style estimand and sensitivity profile",
    "CDISC protocol/data-model interoperability readiness",
)


def _p(
    key: str,
    features: tuple[str, ...],
    visuals: tuple[str, ...],
    links: tuple[str, ...],
    checks: tuple[str, ...],
    standards: tuple[str, ...] = _SHARED_STANDARDS,
) -> AdvancedPlanningProfile:
    return AdvancedPlanningProfile(key, standards, features, visuals, links, checks)


ADVANCED_PROFILES: dict[str, AdvancedPlanningProfile] = {
    "study_protocol_designer": _p(
        "study_protocol_designer",
        (
            "SPIRIT-style checklist workspace", "Schedule-of-activities builder", "Protocol synopsis generator",
            "Critical-to-quality factor registry", "Benefit-risk planning section", "Safety reporting plan",
            "Monitoring strategy", "Data-management-plan linkage", "Protocol amendment impact analysis",
            "Protocol deviation taxonomy", "Country and site appendix support", "Protocol template comparison",
        ),
        (
            "Schedule-of-activities matrix", "Participant journey", "Protocol dependency graph",
            "Completeness-versus-risk matrix", "Amendment impact Sankey", "Critical-to-quality map",
        ),
        ("endpoint_outcome_strategy", "sample_size_power_studio", "data_collection_crf_designer", "statistical_analysis_plan", "preregistration_reproducibility"),
        ("Objectives linked to endpoints", "Every endpoint represented in the CRF", "Power assumptions current", "Amendments impact-assessed"),
    ),
    "biostatistics_design": _p(
        "biostatistics_design",
        (
            "Generalized linear model planning", "Mixed-effects model planning", "Longitudinal analysis",
            "Competing-risk and recurrent-event planning", "Nonparametric planning", "Multiple imputation",
            "Causal estimands", "Bayesian analysis", "Multiplicity strategies", "Subgroup interaction planning",
            "Robustness checks", "Assumption diagnostics",
        ),
        ("Model-selection tree", "Assumption matrix", "Effect-size forest", "Sensitivity tornado", "Missing-data comparison", "Method compatibility map"),
        ("sample_size_power_studio", "endpoint_outcome_strategy", "statistical_analysis_plan"),
        ("Outcome-model compatibility", "Multiplicity documented", "Missing-data strategy defined", "Assumptions sensitivity-tested"),
    ),
    "sample_size_power_studio": _p(
        "sample_size_power_studio",
        (
            "Bayesian assurance", "Group-sequential design", "Adaptive sample-size re-estimation",
            "Stepped-wedge cluster design", "Crossover design", "Repeated-event planning",
            "Multiple and co-primary endpoints", "Precision-based planning", "Nuisance-parameter uncertainty",
            "Simulation-based non-inferiority", "Internal pilot design", "Recruitment feasibility coupling",
        ),
        ("Power surface", "Assurance distribution", "Sample-size contour", "Noncompliance sensitivity", "Interim boundaries", "ICC heatmap", "Expected-versus-maximum sample size"),
        ("study_protocol_designer", "research_feasibility_recruitment", "statistical_analysis_plan"),
        ("Effect size sourced", "Variance sourced", "Dropout justified", "Multiplicity reflected", "Recruitment target feasible"),
    ),
    "clinical_trial_design_studio": _p(
        "clinical_trial_design_studio",
        (
            "Basket, umbrella and platform trial planning", "Seamless phase design", "Adaptive enrichment",
            "Group-sequential stopping", "Dose-escalation simulation", "CRM and BOIN-style planning",
            "Response-adaptive randomization", "Master protocol support", "Data-monitoring committee charter",
            "Safety stopping rules", "Interim decision simulation", "Operating-characteristic simulation",
        ),
        ("Master-protocol architecture", "Dose-transition pathway", "Interim decision tree", "Operating-characteristics dashboard", "Arm lifecycle timeline", "Recruitment by cohort", "Decision boundaries"),
        ("randomization_blinding_allocation", "endpoint_outcome_strategy", "research_feasibility_recruitment", "research_risk_mitigation"),
        ("Arms and cohorts consistent", "Safety rules explicit", "Interim decisions prespecified", "Recruitment assumptions stress-tested"),
    ),
    "experimental_design_doe": _p(
        "experimental_design_doe",
        (
            "Mixture designs", "Definitive screening designs", "Split-plot designs", "Nested experiments",
            "Robust parameter design", "Sequential design augmentation", "D-optimal and I-optimal designs",
            "Constrained design spaces", "Multi-response desirability", "Alias and confounding inspection",
            "Lack-of-fit planning", "Replicate and centre-point optimization",
        ),
        ("Design-space explorer", "Alias matrix", "Prediction-variance map", "Desirability surface", "Sequential augmentation", "Factor correlation", "Prediction profiler"),
        ("sampling_biospecimen_planning", "research_timeline_dependencies", "research_risk_mitigation"),
        ("Design estimable", "Alias structure reviewed", "Replicates sufficient", "Constraints documented"),
    ),
    "randomization_blinding_allocation": _p(
        "randomization_blinding_allocation",
        (
            "Minimization", "Covariate-adaptive randomization", "Response-adaptive allocation",
            "Variable block schedules", "Unequal allocation", "Cluster allocation", "Central randomization",
            "Allocation concealment", "Emergency unblinding", "Independent code-list export",
            "Randomization simulation", "Predictability and imbalance audit",
        ),
        ("Allocation balance trajectory", "Covariate imbalance", "Predictability risk", "Block-size distribution", "Site-by-arm heatmap", "Unblinding timeline"),
        ("cohort_eligibility_builder", "data_collection_crf_designer", "clinical_trial_design_studio"),
        ("Strata available in CRF", "Concealment documented", "Seed protected", "Imbalance within tolerance"),
    ),
    "cohort_eligibility_builder": _p(
        "cohort_eligibility_builder",
        (
            "Computable phenotype builder", "Nested AND/OR/NOT logic", "Temporal eligibility rules",
            "Diagnosis, medication and laboratory windows", "Genomic and biomarker criteria", "Washout periods",
            "Historical-data requirements", "Rule provenance", "Portable cohort definition", "Source feasibility",
            "Duplicate participant handling", "Eligibility-rule sensitivity",
        ),
        ("Cohort attrition funnel", "Rule dependency graph", "Temporal eligibility timeline", "Rule overlap UpSet", "Site eligible population", "Sensitivity waterfall"),
        ("study_protocol_designer", "research_feasibility_recruitment", "synthetic_cohort_trial"),
        ("Rules computable", "Time windows explicit", "Source variables available", "Eligibility impact simulated"),
    ),
    "endpoint_outcome_strategy": _p(
        "endpoint_outcome_strategy",
        (
            "Full estimand framework", "Intercurrent-event strategies", "Composite endpoints", "Hierarchical endpoints",
            "Win-ratio planning", "Repeated-measure endpoints", "Patient-reported outcomes", "Endpoint adjudication",
            "Minimal clinically important difference", "Measurement-error planning", "Missing-outcome strategy", "Endpoint validation evidence",
        ),
        ("Objective-estimand-endpoint map", "Endpoint hierarchy", "Intercurrent-event matrix", "Burden-versus-value", "Composite contribution", "Adjudication workflow"),
        ("study_protocol_designer", "sample_size_power_studio", "data_collection_crf_designer", "statistical_analysis_plan"),
        ("Primary endpoint unique", "Estimand complete", "Collection variables present", "Analysis method prespecified"),
    ),
    "biomarker_study_planning": _p(
        "biomarker_study_planning",
        (
            "Analytical validity plan", "Clinical validity plan", "Clinical utility plan", "Pre-analytical variable plan",
            "Discovery-verification-validation phases", "Nested cross-validation planning", "Locked cut-off strategy",
            "Internal-external validation", "Platform transferability", "Calibration and decision-curve planning",
            "Multiplex panel optimization", "Companion-diagnostic readiness checklist",
        ),
        ("Biomarker roadmap", "Evidence maturity ladder", "Cut-off stability surface", "Leakage map", "Specimen-to-result chain", "Transferability matrix", "Intended-use diagram"),
        ("sampling_biospecimen_planning", "data_collection_crf_designer", "statistical_analysis_plan", "validation_cohort_manager"),
        ("Intended use explicit", "Cut-off locked", "Independent validation planned", "Pre-analytics controlled"),
    ),
    "sampling_biospecimen_planning": _p(
        "sampling_biospecimen_planning",
        (
            "Pre-analytical variable registry", "Collection-device selection", "Processing-time limits", "Centrifugation and stabilization plan",
            "Aliquot optimization", "Minimum residual volume", "Freeze-thaw policy", "Shipping excursion simulation",
            "Sample-priority hierarchy", "Derivative specimen tracking", "Biobank capacity forecast", "Biospecimen reconciliation rules",
        ),
        ("Pre-analytical process map", "Sample derivative tree", "Volume simulation", "Temperature excursion", "Storage forecast", "Availability timeline", "Collection risk map"),
        ("study_protocol_designer", "data_collection_crf_designer", "research_timeline_dependencies", "research_budget_burden"),
        ("Volumes feasible", "Visit schedule aligned", "Storage capacity sufficient", "Excursion policy defined"),
    ),
    "data_collection_crf_designer": _p(
        "data_collection_crf_designer",
        (
            "CDASH-aligned variable library", "FHIR and eSource mapping", "EHR prepopulation readiness", "ePRO and eCOA forms",
            "Repeating forms", "Complex skip logic", "Cross-form edit checks", "Range and consistency checks",
            "Query-generation rules", "Coding dictionaries", "Multilingual metadata", "ODM-style machine-readable export",
        ),
        ("Form logic flow", "Variable lineage", "FHIR-to-CRF matrix", "Edit-check network", "Entry burden", "Visit-form coverage"),
        ("study_protocol_designer", "endpoint_outcome_strategy", "statistical_analysis_plan", "randomization_blinding_allocation"),
        ("Endpoints collectable", "Strata variables present", "Units controlled", "Edit checks complete"),
    ),
    "statistical_analysis_plan": _p(
        "statistical_analysis_plan",
        (
            "Estimand-to-analysis mapping", "Analysis population rules", "Derived-variable specification", "Missing-data strategy",
            "Multiple-imputation specification", "Multiplicity procedure", "Interim-analysis methods", "Subgroup interaction rules",
            "Sensitivity and tipping-point analyses", "TFL shell builder", "ADaM-style dataset specification", "R/Python/SAS skeleton generation", "Mock-data validation",
        ),
        ("Endpoint-estimand-model Sankey", "Population overlap", "Multiplicity decision tree", "Missing-data grid", "TFL roadmap", "Dataset-variable lineage"),
        ("endpoint_outcome_strategy", "data_collection_crf_designer", "sample_size_power_studio", "preregistration_reproducibility"),
        ("Every endpoint mapped", "Analysis populations computable", "Missingness handled", "Sensitivity analyses defined"),
    ),
    "synthetic_cohort_trial": _p(
        "synthetic_cohort_trial",
        (
            "Correlated-variable generation", "Longitudinal trajectories", "Time-to-event generation", "Recurrent events",
            "Informative dropout", "MAR and MNAR missingness", "Site and investigator effects", "Treatment noncompliance",
            "Protocol deviations", "Confounding and selection bias", "Digital-twin scenarios", "Real-cohort calibration", "Privacy and disclosure-risk audit",
        ),
        ("Real-versus-synthetic distributions", "Correlation preservation", "Longitudinal fan plot", "Site heterogeneity", "Missingness mechanism", "Effect recovery", "Privacy-utility trade-off"),
        ("cohort_eligibility_builder", "clinical_trial_design_studio", "sample_size_power_studio", "research_feasibility_recruitment"),
        ("Simulation assumptions registered", "Privacy risk reviewed", "Calibration target documented", "Seed reproducible"),
    ),
    "research_feasibility_recruitment": _p(
        "research_feasibility_recruitment",
        (
            "Competing-trial effects", "Seasonal recruitment", "Country and site start-up distributions", "Referral funnel",
            "Participant retention", "Site dropout", "Recruitment rescue scenarios", "Recruitment caps",
            "Cost per randomized participant", "Contract and activation delays", "Bayesian recruitment updating", "Real-time forecast recalibration",
        ),
        ("Recruitment fan chart", "Site activation Gantt", "Recruitment funnel", "Cost-time Pareto", "Completion probability", "Rescue comparison", "Geographic feasibility"),
        ("cohort_eligibility_builder", "sample_size_power_studio", "research_timeline_dependencies", "research_budget_burden"),
        ("Eligible pool sufficient", "Site rates evidence-backed", "Dropout included", "Rescue trigger defined"),
    ),
    "research_timeline_dependencies": _p(
        "research_timeline_dependencies",
        (
            "PERT duration estimates", "Monte Carlo schedule risk", "Resource leveling", "Critical-chain buffers",
            "Parallel workstreams", "Approval and vendor dependencies", "Baseline versus forecast", "Automatic downstream rescheduling",
            "Calendar and holiday constraints", "Milestone confidence", "Delay root-cause analysis", "Scenario snapshots",
        ),
        ("Probabilistic Gantt", "Critical-path network", "Criticality index", "Resource overload heatmap", "Milestone intervals", "Delay propagation", "Scenario comparison"),
        ("study_protocol_designer", "sampling_biospecimen_planning", "research_feasibility_recruitment", "research_risk_mitigation"),
        ("Dependencies acyclic", "Resources not overallocated", "Approval gates present", "Buffers justified"),
    ),
    "research_risk_mitigation": _p(
        "research_risk_mitigation",
        (
            "Quality-by-design critical-to-quality factors", "FMEA", "Bow-tie analysis", "Leading and lagging indicators",
            "Key risk indicators", "Risk appetite", "Trigger thresholds", "Control effectiveness",
            "Residual and emerging risks", "Risk dependencies", "Monte Carlo aggregate exposure", "CAPA handoff",
        ),
        ("Dynamic FMEA", "Risk bow-tie", "Dependency network", "KRI control chart", "Aggregate exposure", "Mitigation trend", "Emerging-risk radar"),
        ("study_protocol_designer", "research_timeline_dependencies", "research_budget_burden"),
        ("Critical risks controlled", "Owners assigned", "Triggers measurable", "Residual risk accepted"),
    ),
    "evidence_gap_literature_planning": _p(
        "evidence_gap_literature_planning",
        (
            "Living evidence map", "Citation import", "Duplicate-publication detection", "PICO ontology mapping",
            "Study-design classification", "Risk-of-bias fields", "Evidence certainty grading", "Contradiction detection",
            "Population and outcome gaps", "Search-string versioning", "Screening decision log", "Update alerts", "Systematic-review protocol export",
        ),
        ("Living evidence network", "PICO evidence cube", "Risk-of-bias heatmap", "Certainty map", "Contradiction forest", "Duplication risk", "Update timeline"),
        ("study_protocol_designer", "endpoint_outcome_strategy", "preregistration_reproducibility"),
        ("Search reproducible", "Evidence duplicates removed", "Bias assessed", "Gaps linked to objectives"),
    ),
    "preregistration_reproducibility": _p(
        "preregistration_reproducibility",
        (
            "Registry-specific templates", "OSF-style export", "Clinical registry fields", "Registered-report checklist",
            "Timestamped cryptographic lock", "Embargo metadata", "Public and private modes", "Analysis-code hash",
            "Data-dictionary hash", "Deviation classification", "Outcome-switching detection", "Planned-versus-reported comparison", "Reproduction checklist",
        ),
        ("Lock and amendment timeline", "Outcome-switching matrix", "Planned-versus-executed Sankey", "Deviation waterfall", "Dependency graph", "Completeness radar", "Artefact integrity map"),
        ("study_protocol_designer", "statistical_analysis_plan", "data_collection_crf_designer"),
        ("Hypotheses locked", "Outcomes locked", "Analysis hash captured", "Deviations classified"),
    ),
}


def get_advanced_profile(module_key: str) -> AdvancedPlanningProfile:
    try:
        return ADVANCED_PROFILES[module_key]
    except KeyError as exc:
        raise KeyError(f"No advanced research-planning profile for {module_key}") from exc
