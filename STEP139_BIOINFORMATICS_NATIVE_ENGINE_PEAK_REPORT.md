# BioIntel AI Step 139 — Native Engine & Review Peak

## Scope

- All **15 Step 138 specialist bioinformatics modules** upgraded without duplicate navigation pages.
- **15 native scientific-input profiles** covering indexed/text/binary scientific formats with safe staging and actionable engine requirements.
- Existing **180 specialist visual assignments** retained and reorganised into Overview, QC, Primary, Advanced, Evidence and Comparison workspaces.
- Persistent scientific review, run snapshots, cohort/run comparison, reference verification and publication bundles added across the suite.

## Native data and execution upgrades

- Atomic native-file staging under the protected UserData workspace, with before/after SHA-256 verification and a 1 GB safety limit.
- Native handling for VCF/VCF.GZ, BED/BedGraph, BEDPE, GFF/GTF, MAF, FASTA, AIRR, HDF5/H5AD/H5MU/MuData and module-specific scientific tables.
- PLINK PGEN/BGEN and BigWig remain metadata-only until a qualified external engine is available; unsafe deserialisation is never attempted.
- Protected no-shell automatic plans are available for compatible one-file workflows such as bcftools stats, samtools index/depth, MACS2 peak calling, deepTools coverage, Sniffles, MAFFT, ANARCI, OpenMS file inspection and BUSCO.
- Engine plans are work-directory contained, version/readiness checked and queued through the existing background worker. Missing tools remain clearly unavailable instead of producing fake results.

## Scientific review and comparison

- Persistent record-level statuses: Needs review, Accepted, Rejected, Needs confirmation and Escalated.
- Reviewer, reason, notes, source record and audit timestamp are retained in a WAL-enabled SQLite review store.
- Checksum-verified compressed run snapshots support Run A versus Run B, cohort and parameter comparisons.
- Identifier-aligned comparison reports added/removed/changed records and numeric metric deltas.

## Reference lifecycle and publication output

- Module-specific reference requirements can be bound by relative path, pinned by SHA-256 and rechecked for missing files or checksum drift.
- Large reference hashes are cached by path, size and modification time to avoid repeated multi-GB reads.
- Each module can generate a reproducibility/publication ZIP containing result data, QC, derived tables, 12 figure datasets, interactive HTML, Plotly JSON, captions, methods, report HTML and a hash-bearing manifest.
- SVG, high-DPI PNG and PDF are produced only when the optional Kaleido renderer is installed; otherwise the manifest records the limitation honestly.

## Stability and performance controls

- Explicit Run action prevents expensive analysis on every widget change.
- Interactive calculations remain bounded to 250,000 rows and plot inputs to 5,000 records.
- Engine readiness, reference asset listing and unchanged reference hashes are cached.
- Corrupt compressed files, path traversal, unsafe ZIP members, duplicate mapping and unsupported binary formats stop with actionable errors.
- Individual visual, engine and reference failures are isolated and return stable recovery identifiers rather than crashing the entire module.

## Completed verification

| Check | Result |
|---|---:|
| Step 139 focused tests | **9 passed** |
| Step 138 compatibility tests | **20 passed** |
| Step 137 compatibility tests | **19 passed** |
| Selected core/regression tests | **65 passed** |
| Selected visual/interaction tests | **33 passed** |
| Completed separate-suite total | **146 passed, 0 failures** |
| Python compilation | **1,010/1,010 passed** |
| Navigation integrity | **206/206 entries healthy** |
| SQLite databases | **40/40 healthy** |
| Database rows inspected | **108,493** |
| Foreign-key violations | **0** |
| Scientific module smoke | **15/15 non-empty** |
| Visual construction smoke | **180/180** |
| Publication bundles | **15/15 ZIPs verified** |

## Honest qualification boundary

The selected focused, compatibility, regression and scientific suites completed successfully in separate runs. A monolithic combined test command crossed the execution time cap after progress had begun, so it is not represented as a full-suite pass. Live Streamlit browser automation, a physical clean Windows installation and absent third-party scientific engines were not available in this Linux build environment. Known defects covered by the completed suites are resolved, but an absolute zero-defect guarantee for every dataset, machine, optional executable and operating-system configuration would not be technically truthful.

## 1. Population Genetics, GWAS & PRS Studio

- **Native inputs:** bcf, bed, bim, csv, fam, json, ped, pgen, psam, pvar, tsv, txt, vcf, xls, xlsx, vcf.gz
- **Preferred viewers:** genome_browser
- **Native capabilities:** PLINK/VCF cohort intake, indexed variant readiness, ancestry and kinship context, reference-locked association planning
- **Reference requirements:** Reference FASTA, Genome annotation, Ancestry reference panel, LD reference panel, Allele-frequency panel
- **Safe engine plans:** BCFtools variant statistics
- **Scientific boundary:** Exploratory screening does not replace validated PLINK, SAIGE or REGENIE pipelines, imputation, ancestry-matched validation or clinical interpretation.

## 2. Epigenomics & Chromatin Accessibility Workbench

- **Native inputs:** bam, bed, bedgraph, bedmethyl, bigwig, broadpeak, bw, cram, csv, gff, gff3, gtf, json, narrowpeak, tsv, txt, xls, xlsx, bed.gz, bedmethyl.gz, gff.gz, gtf.gz
- **Preferred viewers:** genome_browser
- **Native capabilities:** BAM/CRAM metadata intake, bedMethyl parsing, peak and signal-track readiness, replicate-aware engine planning
- **Reference requirements:** Reference FASTA, Genome annotation, Motif library, Chromatin-state atlas, Blacklist regions
- **Safe engine plans:** Index BAM/CRAM, Alignment depth profile, MACS2 peak calling, deepTools coverage track
- **Scientific boundary:** Screening-level region analysis must be confirmed with replicate-aware specialist pipelines, matched genome builds and orthogonal assays.

## 3. Pharmacogenomics & Clinical Genomics Studio

- **Native inputs:** bam, bcf, cram, csv, fam, json, ped, tsv, txt, vcf, xls, xlsx, vcf.gz
- **Preferred viewers:** genome_browser
- **Native capabilities:** variant and coverage intake, copy-number readiness, guideline-version locking, manual diplotype review
- **Reference requirements:** Reference FASTA, Pharmacogene definitions, Star-allele definitions, Guideline snapshot, Population frequency panel
- **Safe engine plans:** BCFtools call statistics, Pharmacogene coverage depth
- **Scientific boundary:** Research-use output is not a prescribing recommendation. Clinical decisions require validated genotyping, current guidelines and qualified professional review.

## 4. Structural Variant, Repeat Expansion & Mosaicism Studio

- **Native inputs:** bam, bcf, bed, bedgraph, bedpe, broadpeak, cram, csv, json, narrowpeak, tsv, txt, vcf, xls, xlsx, bed.gz, vcf.gz
- **Preferred viewers:** genome_browser
- **Native capabilities:** raw-read evidence readiness, multi-caller normalization, repeat-expansion planning, orthogonal-validation manifest
- **Reference requirements:** Reference FASTA, Repeat catalogue, Gene annotation, Population SV catalogue, Mappability/segdup tracks
- **Safe engine plans:** BCFtools structural-call statistics, Breakpoint-region depth, Sniffles long-read SV calling
- **Scientific boundary:** Breakpoints and mosaic fractions require raw-read review and orthogonal confirmation; this module does not manufacture clinical classifications.

## 5. RNA Splicing & Isoform Pathology Lab

- **Native inputs:** bam, bed, bedgraph, broadpeak, cram, csv, gff, gff3, gtf, json, narrowpeak, sam, tsv, txt, xls, xlsx, bed.gz, gff.gz, gtf.gz
- **Preferred viewers:** genome_browser
- **Native capabilities:** alignment/junction readiness, transcript-version locking, long-read isoform integration, read-backed event review
- **Reference requirements:** Reference FASTA, Transcript annotation GTF, Tissue splicing reference, Protein-domain annotation
- **Safe engine plans:** Index splice alignment, Junction-region coverage
- **Scientific boundary:** Built-in calculations are exploratory and do not replace splice-aware alignment, transcript assembly or validated DEXSeq, DRIMSeq, MAJIQ or long-read workflows.

## 6. Immunogenomics & Immune Repertoire Studio

- **Native inputs:** airr, csv, fa, faa, fas, fasta, fastq, fna, fq, json, jsonl, ndjson, tsv, txt, xls, xlsx, fastq.gz, fq.gz
- **Preferred viewers:** single_cell
- **Native capabilities:** AIRR/VDJ intake, paired-chain readiness, lineage and SHM planning, sampling-depth normalization
- **Reference requirements:** AIRR schema, IMGT germline database, Public clonotype reference, HLA reference
- **Safe engine plans:** ANARCI receptor numbering
- **Scientific boundary:** Repertoire frequencies are sensitive to library preparation, sampling depth and clonotype definition; biological conclusions require matched experimental design.

## 7. Single-Cell Multiome & Regulatory Network Studio

- **Native inputs:** csv, h5, h5ad, h5mu, hdf5, json, mtx, mudata, tsv, txt, xls, xlsx, mtx.gz
- **Preferred viewers:** single_cell
- **Native capabilities:** H5AD/MuData inventory, backed single-cell preview, modality-aware QC, joint-analysis readiness
- **Reference requirements:** Genome annotation, Peak set, Cell-type reference atlas, Motif library
- **Safe engine plans:** Readiness and manual specialist workflow only
- **Scientific boundary:** Joint embeddings and transferred labels are exploratory. Validate modality integration, cell labels and regulatory links with independent evidence.

## 8. Proteogenomics & Neoantigen Discovery Studio

- **Native inputs:** bcf, csv, fa, faa, fas, fasta, fna, json, mgf, mzml, tsv, txt, vcf, xls, xlsx, mgf.gz, mzml.gz, vcf.gz
- **Preferred viewers:** mass_spectrometry
- **Native capabilities:** variant/proteome/MS intake, spectrum evidence readiness, HLA model readiness, candidate adjudication
- **Reference requirements:** Reference proteome, Transcript annotation, HLA allele database, Normal tissue atlas, Search-engine parameter set
- **Safe engine plans:** Variant source statistics, OpenMS mzML validation
- **Scientific boundary:** Predicted binding and immunogenicity do not establish therapeutic efficacy. Candidates require validated HLA typing, assays and safety review.

## 9. Gene Regulatory Network & TF Activity Studio

- **Native inputs:** bed, bedgraph, broadpeak, csv, gff, gff3, gtf, h5ad, json, narrowpeak, tsv, txt, xls, xlsx, bed.gz, gff.gz, gtf.gz
- **Preferred viewers:** multiomics
- **Native capabilities:** multi-omic evidence intake, edge-provenance locking, bootstrap network planning, perturbation scenario manifest
- **Reference requirements:** Motif library, TF-target knowledgebase, Genome annotation, Chromatin accessibility tracks
- **Safe engine plans:** Readiness and manual specialist workflow only
- **Scientific boundary:** Inferred regulatory edges are hypotheses and must be validated with perturbation, binding or orthogonal evidence.

## 10. Federated Genomic Discovery & Phenopacket Studio

- **Native inputs:** csv, json, jsonl, ndjson, tsv, txt, xls, xlsx, yaml, yml, phenopacket.json
- **Preferred viewers:** static_reporting
- **Native capabilities:** Phenopacket validation, federated query manifest, consent-aware review, source response audit
- **Reference requirements:** HPO release, GA4GH VRS schema, Beacon endpoint registry, Consent/data-use policy
- **Safe engine plans:** Readiness and manual specialist workflow only
- **Scientific boundary:** Federated discovery does not grant access to restricted records and must respect consent, governance and source-specific interpretation rules.

## 11. Viral Genomics & Within-Host Evolution Studio

- **Native inputs:** bam, bcf, cram, csv, fa, faa, fas, fasta, fastq, fna, fq, json, tsv, txt, vcf, xls, xlsx, fastq.gz, fq.gz, vcf.gz
- **Preferred viewers:** genome_browser
- **Native capabilities:** raw-read/consensus intake, primer-dropout readiness, minor-variant manifest, phylogeny and lineage planning
- **Reference requirements:** Viral reference genome, Primer scheme, Lineage database, Resistance catalogue, Antigenic-site annotation
- **Safe engine plans:** Viral VCF statistics, MAFFT sequence alignment, Viral alignment depth
- **Scientific boundary:** Low-frequency variants are highly sensitive to sequencing and contamination artefacts; confirm with validated callers, controls and replicate evidence.

## 12. Genome Annotation & Comparative Annotation Studio

- **Native inputs:** csv, fa, faa, fas, fasta, fna, gb, gbk, genbank, gff, gff3, gtf, json, tsv, txt, xls, xlsx, gff.gz, gtf.gz
- **Preferred viewers:** genome_browser
- **Native capabilities:** FASTA/GFF compatibility, gene-model evidence review, annotation transfer planning, curated GFF export readiness
- **Reference requirements:** Reference assembly, Protein evidence, RNA evidence, BUSCO lineage, Functional database releases
- **Safe engine plans:** BUSCO annotation/assembly completeness
- **Scientific boundary:** Automated annotation transfer can propagate errors. Curated gene models and experimental evidence remain authoritative.

## 13. Circular DNA, Mobile Elements & Genome Instability Studio

- **Native inputs:** bam, bcf, bed, bedgraph, bedpe, broadpeak, cram, csv, json, narrowpeak, tsv, txt, vcf, xls, xlsx, bed.gz, vcf.gz
- **Preferred viewers:** genome_browser
- **Native capabilities:** breakpoint and copy-number intake, amplicon topology readiness, ecDNA/BFB evidence review, cohort recurrence comparison
- **Reference requirements:** Reference FASTA, Gene annotation, Cancer gene census, Segmental duplications, Viral integration reference
- **Safe engine plans:** Instability-call statistics, Amplicon depth profile, Sniffles rearrangement calling
- **Scientific boundary:** Complex rearrangement structures require raw-read, assembly and orthogonal validation; inferred circles are research hypotheses.

## 14. Environmental Genomics & eDNA Surveillance Studio

- **Native inputs:** csv, fa, faa, fas, fasta, fastq, fna, fq, json, tsv, txt, xls, xlsx, fastq.gz, fq.gz
- **Preferred viewers:** multiomics
- **Native capabilities:** raw-read/count-table intake, field/lab control audit, reference coverage review, occupancy-analysis readiness
- **Reference requirements:** Taxonomic reference library, Marker-gene database, Contaminant database, Site metadata dictionary
- **Safe engine plans:** Readiness and manual specialist workflow only
- **Scientific boundary:** eDNA detection depends on sampling design, assay specificity, reference coverage and environmental persistence; presence does not prove abundance or viability.

## 15. Comparative Regulatory Genomics Studio

- **Native inputs:** bed, bedgraph, bigwig, broadpeak, bw, csv, fa, faa, fas, fasta, fna, gff, gff3, gtf, json, narrowpeak, tsv, txt, xls, xlsx, bed.gz, gff.gz, gtf.gz
- **Preferred viewers:** genome_browser
- **Native capabilities:** multi-species region intake, lift-over readiness, orthologous peak matching, regulatory gain/loss review
- **Reference requirements:** Multi-species assemblies, Whole-genome alignment, Orthology map, Motif library, Constraint tracks
- **Safe engine plans:** Readiness and manual specialist workflow only
- **Scientific boundary:** Conservation and motif presence are indirect evidence. Functional claims require species- and tissue-matched experimental validation.
