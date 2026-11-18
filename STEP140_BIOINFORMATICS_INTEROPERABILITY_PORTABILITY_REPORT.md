# BioIntel AI Step 140 — Interoperability, Portability & Validation Peak

## Scope

- All **15 specialist Bioinformatics modules** upgraded without duplicate navigation pages.
- Existing **180 domain-specific visuals** retained and connected to a scientific inspection drawer.
- **15 benchmark profiles**, **15 portable workflow plans** and **15 last-mile scientific profiles** added.
- Product version remains **13.2.0**; Step 140 is the implementation milestone.

## Standards and interoperability

- Deterministic sha512t24u VRS-style sequence and allele identifiers.
- Cat-VRS-style categorical variation helper and VA-Spec-style variation descriptors.
- Phenopacket structural/HPO validation with explicit review issues.
- refget-style sequence digests, DRS object manifests and htsget regional request manifests.
- These are local compatibility helpers; full remote service conformance is not falsely claimed.

## Portable and reproducible workflow layer

- WES run requests, TES task manifests, TRS descriptors and DRS input manifests.
- CWL/Nextflow descriptor import in metadata-only mode until a qualified runtime is available.
- Shell metacharacters blocked; commands remain argument-vector based.
- Container image and SHA-256 digest locks attached to specialist tasks.
- Local, offline-Windows, HPC and WES execution profiles represented.

## Scientific validation and last-mile analysis

- Explicit truth/prediction benchmark workflow; benchmark truth is never invented.
- Subgroup performance, benchmark history and module-specific truth requirements.
- Multi-engine consensus with caller agreement, exclusive calls and ensemble confidence.
- Bootstrap confidence intervals, stability scores and leave-one-out sensitivity.
- Module-specific last-mile derived tables across all 15 modules.

## Indexed scientific data and lifecycle

- Bounded region queries for text genomic formats and optional indexed binary access.
- Companion index detection, progressive genomic tiles and safe regional limits.
- Sample/cohort harmonization, reference release difference viewer and impacted-record review.
- Result states: Draft, Reviewed, Locked, Superseded and Retracted.
- Stage-level checkpoints with input/parameter/output hashes and resume compatibility.

## Stability and optimization

- Resource planner estimates RAM, temporary disk, CPU, GPU relevance and execution mode.
- Failure intelligence classifies memory, disk, tool, integrity, timeout, permission and schema failures.
- Managed SQLite connections prevent Streamlit rerun handle leakage.
- Long workflows remain explicit-run, bounded, background-capable and failure-isolated.

## Completed verification

| Check | Result |
|---|---:|
| Distinct selected tests completed | **147 passed, 0 failures** |
| Step 140 focused tests | **17 passed** |
| Python compilation | **1,023/1,023 passed** |
| Navigation catalogue | **205/205 healthy** |
| SQLite databases | **40/40 healthy** |
| Database rows inspected | **108,493** |
| Foreign-key violations | **0** |
| Specialist module smoke | **15/15 passed** |
| Scientific visuals constructed | **180/180** |
| Publication bundles with Step 140 assets | **15/15 verified** |
| Cross-platform stress matrix | **15/15 modules passed** |

## Honest qualification boundary

The package includes a physical Windows qualification harness, but this build host is Linux. Windows 10/11 installation, DPI/scaling, sleep/resume and hardware-specific tests must be run on each target machine. Remote GA4GH services, licensed datasets, optional specialist engines, independent cohorts, wet-lab confirmation and clinical/regulatory acceptance remain external requirements.

## 1. Population Genetics, GWAS & PRS Studio

- **Last-mile features:** Fixed-effect meta-analysis when beta/SE/study are supplied, Gene burden summary, Ancestry transferability audit, PRS utility boundary
- **Benchmark truth:** association truth/replication cohort
- **Benchmark metrics:** precision, recall, f1, calibration
- **Portable workflow:** biointel.population_gwas_peak.peak-v140 · 6 tasks
- **Container/workflow digest:** sha256:0e1152eff417b2e74228fceeedd7b334b29f87f407d686c1dd40b87d9adac2eb
- **Specialist confirmation:** REGENIE/SAIGE/PLINK2, independent cohort, ancestry-matched LD panel
- **Scientific boundary:** Exploratory screening does not replace validated PLINK, SAIGE or REGENIE pipelines, imputation, ancestry-matched validation or clinical interpretation.

## 2. Epigenomics & Chromatin Accessibility Workbench

- **Last-mile features:** Allele-specific accessibility, contact-supported peak-to-gene links, replicate concordance, chromatin-state transitions
- **Benchmark truth:** validated peak/region labels
- **Benchmark metrics:** precision, recall, f1, correlation
- **Portable workflow:** biointel.epigenomics_peak.peak-v140 · 6 tasks
- **Container/workflow digest:** sha256:7d69125c9952a2a72041608075e2314de660b04424a33e9c6440a066a2fef4de
- **Specialist confirmation:** replicate-aware peak caller, Hi-C/contact map, orthogonal regulatory assay
- **Scientific boundary:** Screening-level region analysis must be confirmed with replicate-aware specialist pipelines, matched genome builds and orthogonal assays.

## 3. Pharmacogenomics & Clinical Genomics Studio

- **Last-mile features:** CNV/hybrid allele review, phasing evidence, uncallable locus audit, guideline change impact
- **Benchmark truth:** validated diplotype/phenotype calls
- **Benchmark metrics:** accuracy, precision, recall
- **Portable workflow:** biointel.pharmacogenomics_peak.peak-v140 · 6 tasks
- **Container/workflow digest:** sha256:08b2beba7a0912aceee7af39cf53f1c140f87287cb4c46e842d1477fe66deb9b
- **Specialist confirmation:** validated star-allele caller, orthogonal genotyping, qualified clinical review
- **Scientific boundary:** Research-use output is not a prescribing recommendation. Clinical decisions require validated genotyping, current guidelines and qualified professional review.

## 4. Structural Variant, Repeat Expansion & Mosaicism Studio

- **Last-mile features:** BAF/CNV evidence integration, mosaic confidence, complex-event grouping, caller conflict queue
- **Benchmark truth:** truth SV set
- **Benchmark metrics:** precision, recall, f1
- **Portable workflow:** biointel.structural_variant_peak.peak-v140 · 6 tasks
- **Container/workflow digest:** sha256:bc3242308505caef8e8be2c148f85c7ac6a37c4e1f361d6dce7eadfaa79d82a0
- **Specialist confirmation:** raw-read inspection, long-read/orthogonal confirmation, validated SV truth set
- **Scientific boundary:** Breakpoints and mosaic fractions require raw-read review and orthogonal confirmation; this module does not manufacture clinical classifications.

## 5. RNA Splicing & Isoform Pathology Lab

- **Last-mile features:** Cryptic exon flagging, reading-frame consequence, protein-domain impact, tissue outlier support
- **Benchmark truth:** validated splicing events
- **Benchmark metrics:** precision, recall, f1, correlation
- **Portable workflow:** biointel.rna_splicing_peak.peak-v140 · 6 tasks
- **Container/workflow digest:** sha256:d60b4813a78a7b994684eaf7466d4209c43c0ad23a60ec75c507d63eb2d915a0
- **Specialist confirmation:** splice-aware alignment, RT-PCR/long-read confirmation, tissue-matched reference
- **Scientific boundary:** Built-in calculations are exploratory and do not replace splice-aware alignment, transcript assembly or validated DEXSeq, DRIMSeq, MAJIQ or long-read workflows.

## 6. Immunogenomics & Immune Repertoire Studio

- **Last-mile features:** Antigen-specificity evidence, paired-chain completeness, clonal lineage readiness, compartment migration
- **Benchmark truth:** known clonotypes/controls
- **Benchmark metrics:** accuracy, diversity_error, correlation
- **Portable workflow:** biointel.immune_repertoire.peak-v140 · 5 tasks
- **Container/workflow digest:** sha256:6f35b34cafa45fe725354128b005fe7672fa739f529442bd8737de9ab4c592d4
- **Specialist confirmation:** AIRR-compliant processing, antigen binding evidence, matched sampling design
- **Scientific boundary:** Repertoire frequencies are sensitive to library preparation, sampling depth and clonotype definition; biological conclusions require matched experimental design.

## 7. Single-Cell Multiome & Regulatory Network Studio

- **Last-mile features:** WNN-style modality weighting proxy, batch method audit, marker agreement, perturbation-aware trajectory readiness
- **Benchmark truth:** held-out labels/modalities
- **Benchmark metrics:** accuracy, ari, silhouette, correlation
- **Portable workflow:** biointel.single_cell_multiome.peak-v140 · 5 tasks
- **Container/workflow digest:** sha256:a52aee10f51bfb98f4371187d1edeb37701194e8ed743ba4b4bf1cbb458e73d1
- **Specialist confirmation:** qualified multimodal integration, independent label validation, held-out atlas
- **Scientific boundary:** Joint embeddings and transferred labels are exploratory. Validate modality integration, cell labels and regulatory links with independent evidence.

## 8. Proteogenomics & Neoantigen Discovery Studio

- **Last-mile features:** Spectrum evidence tier, immunopeptidomics support, normal-tissue exclusion, vaccine panel diversity
- **Benchmark truth:** validated peptide-spectrum matches
- **Benchmark metrics:** precision, recall, f1, calibration
- **Portable workflow:** biointel.proteogenomics_peak.peak-v140 · 6 tasks
- **Container/workflow digest:** sha256:27b76c44d9fb5982c883301717ff7881e6d60a9103663f69d47e76deda9fd6fb
- **Specialist confirmation:** target-decoy/FDR search, validated HLA typing, functional immune assay
- **Scientific boundary:** Predicted binding and immunogenicity do not establish therapeutic efficacy. Candidates require validated HLA typing, assays and safety review.

## 9. Gene Regulatory Network & TF Activity Studio

- **Last-mile features:** Condition-specific network rewiring, edge bootstrap stability, causal evidence tier, time-series transition readiness
- **Benchmark truth:** perturbation-backed edges
- **Benchmark metrics:** precision, recall, auprc, stability
- **Portable workflow:** biointel.gene_regulatory_network.peak-v140 · 6 tasks
- **Container/workflow digest:** sha256:89dfa8eecb59bc479201669280842567fdef914fb62f179fe97122b03240eb49
- **Specialist confirmation:** perturbation evidence, binding/accessibility confirmation, independent cohort
- **Scientific boundary:** Inferred regulatory edges are hypotheses and must be validated with perturbation, binding or orthogonal evidence.

## 10. Federated Genomic Discovery & Phenopacket Studio

- **Last-mile features:** VRS-compatible identities, source availability audit, consent policy matrix, query retry manifest
- **Benchmark truth:** known case matches
- **Benchmark metrics:** precision, recall, ranking
- **Portable workflow:** biointel.federated_genomic_discovery.peak-v140 · 3 tasks
- **Container/workflow digest:** sha256:e9bd91f616aef62e7715f9ff1fc84a944e28e2d746543523accde53d73e2a380
- **Specialist confirmation:** authenticated source, source-specific governance, human case review
- **Scientific boundary:** Federated discovery does not grant access to restricted records and must respect consent, governance and source-specific interpretation rules.

## 11. Viral Genomics & Within-Host Evolution Studio

- **Last-mile features:** Amplicon protocol awareness, mixed-infection confidence, transmission uncertainty, resistance evidence tier
- **Benchmark truth:** validated variants/lineages
- **Benchmark metrics:** precision, recall, f1, frequency_error
- **Portable workflow:** biointel.viral_within_host.peak-v140 · 6 tasks
- **Container/workflow digest:** sha256:b746c9bac8bee2b898e9f2fbb5ca1d566bca4294a11dc6c5a929a9f46c065e3b
- **Specialist confirmation:** validated caller, replicate controls, epidemiological confirmation
- **Scientific boundary:** Low-frequency variants are highly sensitive to sequencing and contamination artefacts; confirm with validated callers, controls and replicate evidence.

## 12. Genome Annotation & Comparative Annotation Studio

- **Last-mile features:** Evidence-weighted model reconciliation, annotation conflict queue, transfer confidence, curator-ready corrected export
- **Benchmark truth:** curated annotation
- **Benchmark metrics:** precision, recall, f1, busco
- **Portable workflow:** biointel.genome_annotation.peak-v140 · 5 tasks
- **Container/workflow digest:** sha256:c4762ac10ec3a7846be1d70775b379da768d47419ca899a7850b4fdbd4ec027f
- **Specialist confirmation:** RNA/protein evidence, BUSCO/orthology validation, manual curation
- **Scientific boundary:** Automated annotation transfer can propagate errors. Curated gene models and experimental evidence remain authoritative.

## 13. Circular DNA, Mobile Elements & Genome Instability Studio

- **Last-mile features:** ecDNA-versus-BFB evidence proxy, purity-aware confidence, topology recurrence, long-read confirmation plan
- **Benchmark truth:** validated amplicon topology
- **Benchmark metrics:** precision, recall, topology_accuracy
- **Portable workflow:** biointel.circular_dna_instability.peak-v140 · 6 tasks
- **Container/workflow digest:** sha256:8306cd8153a55e624e32c3b55c4c4494db39fcdf8997eccaa53e1fe8adc02be0
- **Specialist confirmation:** AmpliconArchitect/Circle-Map, long-read/FISH validation, tumour purity estimate
- **Scientific boundary:** Complex rearrangement structures require raw-read, assembly and orthogonal validation; inferred circles are research hypotheses.

## 14. Environmental Genomics & eDNA Surveillance Studio

- **Last-mile features:** Occupancy uncertainty, replicate concordance, contamination source audit, environmental covariate readiness
- **Benchmark truth:** known community/control truth
- **Benchmark metrics:** precision, recall, f1, abundance_error
- **Portable workflow:** biointel.environmental_edna.peak-v140 · 6 tasks
- **Container/workflow digest:** sha256:8166eac35ee65acde816dd102591f99f5d0f3af765a78ce672a84060337d78f0
- **Specialist confirmation:** mock community, field/lab controls, validated occupancy model
- **Scientific boundary:** eDNA detection depends on sampling design, assay specificity, reference coverage and environmental persistence; presence does not prove abundance or viability.

## 15. Comparative Regulatory Genomics Studio

- **Last-mile features:** Regulatory gain/loss classification, tissue match audit, phylogenetic support readiness, ancestral-state summary
- **Benchmark truth:** validated orthologous regulatory regions
- **Benchmark metrics:** precision, recall, correlation
- **Portable workflow:** biointel.comparative_regulatory_genomics.peak-v140 · 6 tasks
- **Container/workflow digest:** sha256:30eb453839ada1c85ff9e8a24fad5093b705afe45ec5397c6495db6b7956b997
- **Specialist confirmation:** whole-genome alignment, species/tissue-matched assays, phylogenetic model
- **Scientific boundary:** Conservation and motif presence are indirect evidence. Functional claims require species- and tissue-matched experimental validation.
