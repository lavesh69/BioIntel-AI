# BioIntel AI Step 111 — Real Engine & Native Format Integration

**Version:** 11.2.0  
**Generated:** 2026-07-10T18:21:58.820418+00:00

## Scope completed

Step 111 upgrades the Step 110 advanced scientific-viewer layer with real file decoding, external scientific-engine adapters, cross-view synchronization and a common statistical-rigor standard.

### Native scientific formats

The release registers **23 native format families** and routes compatible results into all **19 advanced viewers**.

- Sequence and genomics: FASTA, FASTQ, VCF/VCF.GZ, BED/peak files, GFF/GTF, SAM
- Engine-assisted indexed genomics: BAM and CRAM
- Structures: PDB and mmCIF
- Imaging: PNG, JPEG, TIFF and OME-TIFF bounded previews
- Flow cytometry: FCS
- Mass spectrometry: mzML and MGF
- Trees and graphs: Newick, Nexus and GFA
- Family and cohort data: PED/FAM
- Single-cell and sparse matrices: H5AD and Matrix Market
- Workflow, plate and scientific tables: JSON, CSV, TSV and Excel

Every native result records the source name, SHA-256 digest, native level, record counts, truncation state, parser warnings and optional engine requirement.

### Real-engine integration

**24 external scientific engines** have local readiness detection and version reporting. The registry includes SAMtools, BCFtools, HTSlib utilities, minimap2, BWA, STAR, MACS2, deepTools, PLINK 2, MAFFT, IQ-TREE, Kraken 2, Bracken, HUMAnN, AutoDock Vina, GROMACS, OpenMM, Cellpose, StarDist, OpenMS, OpenSlide, ProteinMPNN and RFdiffusion.

The release provides **12 protected, shell-free execution plans** for common indexed genomics, alignment, phylogeny, GWAS, docking, molecular-dynamics, segmentation and mzML verification tasks. Plans use argument lists instead of shell interpolation, restrict files to a protected workspace, apply timeouts and hash generated outputs.

### Advanced viewer synchronization

Viewer selections and state snapshots are stored per project in SQLite. Compatible charts and tables can consume:

- Entity IDs such as variants, cells, residues, peaks and samples
- Chromosome or interval coordinates
- Active filters
- Analysis-run identifiers
- Saved zoom or viewer configuration state

This enables a selection made in one advanced viewer to focus or highlight matching evidence in another compatible view.

### Statistical rigor standardisation

Shared analytical visuals receive a statistical and provenance footer. The full disclosure workflow records:

- Test name and null hypothesis
- Biological and technical replicate counts
- Missing and excluded records
- Effect size and confidence interval
- Assumption checks and warnings
- Multiple-testing correction
- Random seed, data hash, software version and analysis timestamp

The statistical layer includes Welch testing, Hedges/Cohen effect sizes, bootstrap confidence intervals, normality and variance checks, and Benjamini-Hochberg correction.

### Performance and safety

- Maximum upload transport: **1 GB per file**
- Interactive parsing boundary: **100 MB**
- Larger supported files: protected disk staging and background queue
- Streamed SHA-256 calculation
- Bounded previews and record limits
- Sparse/HDF5-aware readers where applicable
- Engine execution isolated from Streamlit UI reruns
- No engine is silently executed during readiness scans

## Verification completed

- Native parser/viewer fixture matrix: **23/23 passed**
- Selected Step 97–111 regression suite: **68/68 passed**
- Application self-test: **7/7 passed**
- Python compilation: **810/810 passed**
- Runtime page checks: **4/4 passed**, zero captured exceptions/errors
- Native VCF upload into advanced viewer: passed, one interactive plot rendered
- SQLite databases: **26/26 healthy**
- Indexed database rows checked: **108,063**

Final package, extraction and internal-manifest counts are recorded in the package verification report generated after archive creation.

## Honest boundaries

BAM and CRAM are recognized and staged natively, but indexed coverage and complete decoding require SAMtools/pysam and, for CRAM, the matching reference FASTA. Proprietary mass-spectrometry RAW formats and proprietary whole-slide formats require vendor readers, OpenSlide-compatible backends or licensed adapters. Native PDB/mmCIF rendering provides atom/residue inspection; advanced molecular surfaces, density maps and long trajectory playback still depend on specialist rendering or simulation engines.

These integrations improve reproducibility and scientific depth, but do not create independent clinical validation, wet-lab confirmation, regulatory approval or vendor certification.
