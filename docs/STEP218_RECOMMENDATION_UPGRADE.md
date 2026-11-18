# Step218.1 Research Recommendation Upgrade

Release identifier: `15.6.0-Step218.1-WINDOWS-V20.1`

## Scope

This release completes the Bioinformatics Lab Analytics, Discovery and Research
Recommendation specification as a local-first, research-use decision-support
workspace. It does not invent unavailable scientific evidence and it explicitly
reports missing inputs, uncertainty, conflicts and validation requirements.

## Implemented capabilities

- Eighteen module-specific recommendation engines covering sequencing quality,
  alignment and mapping, differential expression, biomarkers, variants,
  pathways, multi-omics, single-cell, proteomics, metabolomics, microbiome,
  structural biology, drug-target discovery, experimental design, statistics,
  literature discovery, hypothesis generation and laboratory validation.
- Transparent priority, confidence and evidence grading with quality gates,
  uncertainty, contradictory evidence, alternatives, risks and limitations.
- Explainability, feature contribution, model consensus, prediction stability,
  what-if analysis and cost/feasibility assessment.
- Validation plans, editable action plans, workflow queue, review roles and
  decision status, version comparison, notebook entries, attachments and team
  assignment.
- Provenance for models, databases, references, annotations and software, plus
  persistent audit/error events and recommendation history.
- JSON, CSV, evidence CSV, HTML, PDF, DOCX, XLSX, parameter, audit,
  reproducibility-manifest and complete evidence-package ZIP exports.

## Streamlit workspace

The Research Decision Workspace exposes the required views: Overview, Evidence,
Explainability, Alternatives, Risks, Validation, Action Plan, Comparison,
History and Export. Optional CSV, TSV and JSON inputs are evaluated without
fabricating unavailable values.

## Verification

- Python compilation passed for all new and changed recommendation modules.
- The complete Step218.1 backend suite and the previous Step218 regression suite
  passed in the bundled offline runtime.
- Streamlit 1.58.0 loaded through the packaged Windows wheelhouse.
- A browser smoke test generated and persisted a dossier, rendered all ten
  workspace tabs and reported no browser console errors.
- Final four-part packaging is verified for CRC integrity, exact file-set
  coverage and zero duplicate archive paths.

## Research-use boundary

Recommendations are research-use decision support only. Clinical, diagnostic,
prescribing, manufacturing-release or regulatory decisions require validated
data, approved procedures and qualified human review.
