# BioIntel AI Step 63 — Discovery Platform Excellence

## Release identity

- Product version: **6.3.0**
- Upgrade baseline: Step 62 Lab Analytics Excellence
- Scope: persistent Discovery programs, target evidence, compound identity, molecular preparation, activity curation, chemical space, DTI safeguards, structure/docking qualification, ADMET model qualification, hit ranking, lead-optimization evidence, APIs and local jobs
- Qualification status: **Passed**

## Executive result

Step 63 converts Discovery from a connected but mainly session-oriented early-discovery workbench into a persistent, evidence-aware and reproducible platform. All internally reproducible defects identified in the Discovery audit were fixed. Recommendations that can honestly be implemented in software were added with explicit scientific gates. External wet-lab results, qualified predictive models, legal opinions and regulatory outcomes were not fabricated.

## Critical defects fixed

### Missing-value and objective-ranking safety

- Missing cost values can no longer receive the best score.
- Missing benefit and cost values always receive the worst normalized contribution.
- A separate weighted missing-evidence penalty is applied.
- Completeness thresholds can block under-evidenced compounds from ranking eligibility.
- Explicit empty benefit/cost objective sets are now respected instead of being replaced by default objectives.
- Robust percentile, winsorized min-max, classic min-max and robust z-score ranking are supported.
- Pareto-front status, rank eligibility, warnings and rank method are exported.

### Persistent Discovery projects

A local Discovery Project Registry now persists:

- Project identity, indication, objective, owner and status
- Active target and versioned target assessments
- Compound identities, original structures, standardized parents and InChIKeys
- Exact, connectivity-layer and kept-separate duplicate relationships
- Evidence records and source identifiers
- Ranking methods, parameters, input hashes and output hashes
- Model-card metadata and endpoint qualification decisions
- Event/audit history
- Reproducibility ZIP bundles with file checksums

### Compound identity and molecular-state preparation

- Exact InChIKey duplicate detection
- Connectivity-layer duplicate detection for stereochemical variants
- Merge, reject and intentionally keep-separate policies
- Original submitted form preservation
- Largest-parent and removed-fragment records
- Canonical parent, tautomer ensemble and stereoisomer ensemble
- Ionizable-group detection
- Assay-pH and physiological-pH context modes
- Explicit warning that exact microspecies require a qualified pKa/protonation model
- Manual review boundary for mixtures, metals, covalent systems and special formulations

### Target intelligence

- Evidence rows are aggregated using source quality × confidence × recency.
- Conflicting evidence and missing dimensions are reported.
- Indication templates include balanced, genetics-first, oncology, CNS and infectious-disease modes.
- Custom weights and hard go/no-go gates are supported.
- Confidence-adjusted scores and contribution breakdowns are exported.
- An official-source acquisition plan covers human genetics, disease association, expression, tractability, pathways, known ligands, structural evidence, clinical precedent and safety context.
- Planned queries remain clearly labelled **not retrieved** until provider evidence is imported, versioned, checksum-bound and reviewed.

## ChEMBL and activity-data curation

- Multi-component targets are blocked by default instead of silently using the first UniProt accession.
- Users can explicitly select a target component or choose a documented warning mode.
- Target type, component accessions and selection policy are preserved.
- Assay context fields can include assay type, confidence, organism, tissue/cell context, BAO format, relation, document and activity provenance when available.
- Compound–target replicates can be aggregated.
- Median, minimum, maximum, standard deviation, activity range, replicate count, assay count and document count are recorded.
- Inter-assay conflicts are flagged using a configurable pActivity threshold.
- Provider pagination and recommended leakage-resistant split strategies are recorded.
- Manual target, assay, unit and provenance review remains mandatory before model training.

## DTI scientific safeguards

- Release-blocked or synthetic DTI models require explicit exploratory-use acknowledgement in the UI.
- Prediction controls are disabled until the user acknowledges that output cannot be used as scientific hit-selection evidence.
- Model metadata, split strategy, uncertainty, applicability and release blockers remain visible.
- The qualification report records the current honest state: **23/23 bundled models are synthetic and 0 are scientific-release eligible**.
- No software change promotes synthetic models into validated evidence.

## ADMET qualification architecture

- Rule-based developability output is labelled as a prioritization score, not a biological probability.
- Unavailable Caco-2, HIA, P-gp, PPB, CYP, clearance, hERG, Ames, DILI and other endpoints remain **not assessed**.
- A versioned endpoint model-card schema requires:
  - Artifact SHA-256
  - Training-dataset SHA-256
  - Endpoint definition and units
  - Licence
  - Leakage-resistant validation splits
  - Metrics and calibration
  - Applicability domain
  - Independent validation
  - Intended use and limitations
- Blocked and qualified model cards are persisted in the Discovery registry.
- Only qualified runtime plugins can produce endpoint model output.

## Chemical space and similarity

- Morgan, MACCS, RDKit topological, atom-pair and topological-torsion fingerprints
- Individual and consensus similarity
- Similarity matrices
- Butina clustering
- PCA chemical-space embedding
- Activity-cliff detection
- Exact and near-duplicate control
- Cluster-aware and diversity-aware selection support

## Structure and docking readiness

- Structure-quality and ligand-contact workflows remain available.
- Ligand-defined binding pockets and transparent geometry-hotspot screens were added.
- Chain/group visibility controls improve structure inspection.
- Docking is controlled through a qualification gate requiring:
  - Receptor preparation
  - Ligand preparation
  - Grid definition
  - Reference ligand
  - Redocking RMSD acceptance
  - Enrichment evidence
  - Expert pose review
  - Locked protocol metadata
- External Vina/Smina/GNINA and preparation-tool availability is detected, but missing tools are not falsely reported as working.
- The geometry-hotspot screen is explicitly not represented as a validated docking or pocket score.

## Lead optimization, synthesis and patent evidence

- Liability-specific medicinal-chemistry recommendations are generated with required experimental validation.
- A transparent synthesis-feasibility checklist considers molecular complexity, route length, building-block availability, hazardous steps, protecting groups and precedent.
- The synthesis score is explicitly not a retrosynthesis engine or manufacturing-cost estimate.
- Patent evidence completeness tracks exact structure, substructure/Markush, similarity, target/sequence, jurisdiction, family/legal status, claim review and legal reviewer.
- Patent search evidence is explicitly not treated as freedom-to-operate clearance.

## API and local-job expansion

Discovery API coverage now includes:

- Project create/list/read
- Project reproducibility bundle
- Target profile persistence
- Compound registration and listing
- Hit ranking
- Batch standardization
- Similarity search
- Endpoint-model qualification and listing
- Docking qualification
- Capability reporting
- Local queued batch triage with progress, cancellation, result artifacts and deduplication

## Navigation and UI

- All eight related pages remain grouped under **Discovery**.
- ADMET navigation is renamed **ADMET Triage & Developability**.
- Discovery Command Center now presents persistent projects, evidence acquisition, molecular-state preparation, chemical space, robust ranking, lead optimization/IP evidence, reproducibility export and capability boundaries.
- Discovery labels and methodology versions use product version **6.3.0**.

## Qualification evidence

| Check | Result |
|---|---:|
| Product/version consistency | **6.3.0 — Passed** |
| Repository Ruff gate | **Passed** |
| Python compilation | **Passed** |
| New Step 63 tests | **24/24 passed** |
| Legacy focused regressions | **32/32 passed** |
| Total focused tests | **56/56 passed** |
| Critical backend branch-aware coverage | **95.23%** |
| Interactive Streamlit pages | **5/5 passed** |
| Discovery API cases | **9/9 passed** |
| SQLite databases | **22/22 healthy** |
| Database rows checked | **106,782** at qualification time |
| Foreign-key violations | **0** |
| Secret scan | **1,128 files, 0 findings** |
| Discovery navigation routes | **8/8 present and correctly grouped** |
| Molecule benchmark | **200/200 successful** |
| Store-release internal failures | **0** |

## Embedded recommendations

The UI and outputs now provide actionable next steps, including:

- Retrieve missing target evidence from appropriate official providers.
- Resolve conflicting genetics, disease, safety or experimental evidence.
- Block targets that fail program-specific hard gates.
- Review multi-component target selection before ChEMBL dataset construction.
- Aggregate and investigate conflicting activity replicates.
- Preserve assay pH and obtain a qualified pKa/microspecies model where molecular state matters.
- Use robust ranking and exclude compounds below the evidence-completeness threshold.
- Treat synthetic DTI output as exploratory only.
- Attach qualified endpoint-model cards before enabling predictive ADMET output.
- Qualify docking by redocking and enrichment before screening.
- Validate medicinal-chemistry recommendations with orthogonal potency, selectivity and developability experiments.
- Complete synthesis and patent evidence with qualified chemists and legal reviewers.
- Save final decisions and export a checksum-bound reproducibility bundle.

## Honest remaining external boundaries

The repository does **not** claim the following without genuine third-party evidence:

- Independent wet-lab potency, selectivity, ADME, toxicity, efficacy or safety results
- Qualified proprietary endpoint models and external validation datasets
- Validated docking execution, decoy enrichment and expert pose acceptance
- Patent freedom-to-operate legal opinion
- Procurement/vendor availability guarantees
- Prospective clinical or laboratory validation
- Regulatory approval, journal acceptance or pharmaceutical-customer acceptance

The software now contains the interfaces, qualification gates, evidence fields and reproducibility controls needed to import and govern those outcomes when they genuinely exist.

## Final assessment

Step 63 reaches **10/10 implementation readiness for the internally achievable Discovery software scope**: identified reproducible bugs are fixed, recommendations are integrated, scientific overclaiming is prevented, decisions are persistent and reproducible, and critical code is strongly tested. Scientific real-world validity remains dependent on genuine models, provider evidence, expert review and external experiments.
