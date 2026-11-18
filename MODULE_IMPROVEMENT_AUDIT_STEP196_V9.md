# BioIntel AI Step 196 V9 — Weak-Module Installation Audit

This audit uses the included `STEP173_FINAL_ALL_MODULE_RATINGS.csv`. Ratings below are **actual practical readiness**, not the separate 10/10 internal software/framework score.

| Band | Modules | What V9 can automate |
| --- | ---: | --- |
| Critical: 3.50–4.36 | 5 | Public engine setup and small public references where applicable |
| Weak: 5.00–5.32 | 20 | Public engine setup and small public references where applicable |
| External gates | 25 | Cannot be installed or fabricated: authorised providers, large references, real cohorts, wet-lab/orthogonal evidence, independent sites, governance and release review |

## Critical modules

| Module | Practical readiness | Main missing runtime/reference route |
| --- | ---: | --- |
| Protein design depth | 3.50 | ProteinMPNN/RFdiffusion and weights; BindingDB/ChEMBL/ColabFold data |
| Protein-ligand co-design depth | 3.50 | ColabFold/Vina plus ProteinMPNN/RFdiffusion; large structure/database assets |
| Strain-resolved microbiome depth | 3.50 | Kraken2/Bracken/HUMAnN; 100 GB+ metagenome references |
| Spatial pathology depth | 4.25 | Cellpose/OpenSlide; scanner/instrument and independent pathology evidence |
| Phenotypic screening depth | 4.36 | Cellpose/StarDist; ChEMBL and physical imaging qualification |

## Weak modules

| Practical readiness | Modules |
| ---: | --- |
| 5.00 | AMR surveillance; antibody biologics; cancer genomics core; cell therapy/CAR-T; docking & dynamics; enzyme/pathway design; rare variant/family genetics; population GWAS; genome-editing safety; immunoinformatics/vaccine; long-read assembly; long-read epigenome; metagenomics core; One Health/environmental; pharmacogenomics; proteogenomics/neoantigen; structural variant/repeat |
| 5.11 | Digital pathology foundation-model depth |
| 5.32 | Offline copilot core; offline scientific copilot V2 |

## What the installer now handles

- 34 targeted engines are public automatic routes; the integrated Windows worker expands this to 48 public automatic engines using grouped WSL2/micromamba environments when the host has WSL2 and at least 250 GB free space.
- 7 targeted direct public references (about 1.8 GB combined) are attempted with resume-safe local staging; completed bytes are registered as **downloaded, unqualified**.
- 5 targeted engines remain provider/manual routes: Dorado, NetMHCpan, NetMHCIIpan, ProteinMPNN and RFdiffusion. The application records their real state and never marks them installed merely because a plan exists.
- The full targeted reference catalogue is about 2,825.11 GB. Large, licensed or provider-controlled assets stay operator-controlled and are never silently downloaded.

## Rating boundary

Installing a package is not a scientific qualification. V9 can move real local availability forward on a suitable Windows workstation, but it does not award 10/10 practical readiness until the existing engine/reference, model/cohort, external confirmation and governance gates have authentic evidence.
