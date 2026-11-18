# BioIntel AI Step 136 — Native Raw Data, Real-Engine Readiness & Background Pipelines

## Scope

Step 136 upgrades the fifteen next-generation biomedical modules without adding a new central page, navigation category, theme or duplicate workflow hub. Product version `13.2.0` is preserved as this is a module-focused capability patch.

The release adds checksum-bound native scientific file ingestion, safe bounded parsing, persistent background jobs, pause/resume/cancel controls, explicit external-engine readiness, reference-asset checksum bindings and reproducible result manifests.

## Module coverage

| Module | Native inputs and execution depth |
|---|---|
| Digital Pathology | SVS/NDPI/MRXS/SCN and conventional images; OpenSlide metadata/thumbnail readiness; segmentation-engine readiness; corrupt/truncated-image safe state |
| Long-Read Epigenome | BAM/CRAM, bedMethyl, BED and VCF; coverage/methylation preview; phasing and DMR reference readiness |
| Single-Cell Long-Read Isoforms | BAM/CRAM, GTF/GFF, H5AD and Matrix Market; transcript/cell/barcode/replicate readiness |
| Foundation Model Hub | ONNX, SafeTensors, PT/PTH, BIN and GGUF metadata-only inspection; no unsafe deserialisation; licence/checksum/hardware readiness |
| AMR Surveillance | FASTQ/FASTA/GFF/VCF; read/assembly QC; species, AMR database and phylogeny readiness |
| Spatial Medicine | H5AD/HDF5/MTX, OME-TIFF and tabular coordinates; image/coordinate/cell metadata readiness |
| Gene Therapy Vector | GenBank/FASTA/VCF/tabular construct data; feature, capacity, off-target and immunogenicity readiness |
| CAR-T Engineering | FASTA/GenBank/tabular construct data; domain/CDR, germline, antigen and manufacturing readiness |
| Federated Biomedical AI | CSV/TSV/JSONL/Parquet/Feather; site schema, round manifest, privacy and signed-update readiness |
| Clinical Biomarker & Survival | CSV/TSV/XLSX/JSONL/Parquet/Feather; patient/time/event, unit/date, site/cohort and analysis-design validation |
| Protein–Ligand Co-Design | PDB/mmCIF, SDF/MOL/MOL2/PDBQT and tables; chain/residue/ligand QC, docking-box and selectivity-panel readiness |
| Pangenome Population Medicine | GFA, VG/XG/GBZ, VCF/BCF and FASTA; graph/path, population metadata, index and coordinate readiness |
| Pharmacovigilance | CSV/TSV/XLSX/JSONL/XML/Parquet/Feather; case schema, duplicate fingerprint and terminology readiness |
| Synthetic Cohort & Trial | CSV/TSV/XLSX/JSONL/YAML/Parquet/Feather; arm/site, outcome/time, dropout and seed-lock validation |
| Autonomous Laboratory Planner | CSV/TSV/XLSX/JSONL/YAML; factor/control, replicate/power, plate, resource and approval readiness |

## Native-format safety

New native format support includes whole-slide images, bedMethyl, GenBank, SDF/MOL/MOL2/PDBQT, model checkpoints, adverse-event XML, Parquet/Feather, JSONL, YAML, HDF5, BCF and binary pangenome indexes.

Safety controls:

- Maximum upload size: 1 GB
- Inline module conversion limit: 100 MB
- Background preview limit: 500,000 records
- SHA-256 verification before and after staging
- Atomic `.partial` staging followed by verified rename
- Protected user-data staging directory
- Path traversal prevention
- Model checkpoints inspected as metadata only and never deserialised
- BCF and binary graph indexes remain external-engine placeholders instead of unsafe decoding
- Corrupt/truncated images produce an explicit safe metadata state rather than a page crash
- Compound extensions such as `.fastq.gz`, `.bedmethyl.gz`, `.ome.tif` and `.vcf.gz` are browser-selectable while strict full-suffix validation remains active

## Persistent background execution

The `nextgen_native_pipeline` job type is registered with the local worker and provides:

- Checksum-bound source payloads
- Ordered stage manifests
- Persistent queue state
- Pause, resume and cancellation requests
- Retry limits
- Per-stage progress and timeline events
- Bounded resource declarations
- Output artifact paths
- Native parse and module-conversion manifests
- Explicit failure messages without crashing the parent module

For continuously processed queues, the existing `START_BACKGROUND_WORKER_WINDOWS.bat` launcher may be used. A single worker cycle can also be triggered from each upgraded module.

## External-engine and reference boundaries

Step 136 detects installed engines, versions and executable paths, exposes protected engine-plan templates and validates reference bindings against expected SHA-256 digests. It does not falsely claim that missing executables, licensed databases or model weights are bundled.

Examples of supported readiness checks include:

- SAMtools, BCFtools, Tabix, WhatsHap and deepTools
- minimap2, MAFFT and IQ-TREE
- Kraken 2, Bracken, ABRicate and BLAST
- OpenSlide, Cellpose and StarDist
- Open Babel, AutoDock Vina, GROMACS and OpenMM
- minigraph, vg, odgi and GraphAligner
- ANARCI, IgBLAST and NetMHC tools
- ProteinMPNN and RFdiffusion

Reference bindings remain empty by default. A local administrator can bind files under `BIOINTEL_REFERENCE_ASSETS_DIR` or `data/reference_assets` in `config/step136_reference_bindings.json`, including relative path and expected SHA-256.

## Performance and stability

- Engine probes are cached.
- Only the selected module's native panel is rendered.
- File parsing is bounded and streaming where supported.
- HDF5 is inventoried without loading complete arrays.
- Whole-slide images use bounded thumbnails/metadata.
- Large module conversion is skipped safely while native QC still runs.
- Output tables are compressed as CSV.GZ.
- Temporary staging directories are removed.
- Viewer/conversion errors are isolated from primary module results.
- Existing Step 135 scientific depth and specialist viewers remain intact.

## Scientific boundary

Built-in parsing, QC, schema conversion, screening calculations, manifests and readiness checks are software capabilities. Real docking, model inference, diagnostic pathology, clinical qualification, wet-lab confirmation, current licensed reference databases and regulatory approval require genuine external assets, qualified environments and independent evidence. They are not fabricated or marked complete by this release.

## Completed verification

- Step 136 verifier: 13/13 checks passed
- Fifteen native module pipelines: 15/15 produced checksum-bound manifests
- Step 135 scientific tables preserved: 39
- Step 135 specialist viewers preserved: 49
- Selected non-overlapping regressions: 84 passed
- Python syntax: 958/958 source files passed
- Engineering quality gates: 4/4 passed
- SQLite databases: 36/36 healthy
- Indexed database rows: 108,425
- Foreign-key issues: 0
- Step 135 database hash changes: 0
- Protected pages: 5/5 byte-identical
- Runtime/cache/WAL/SHM residue before packaging: 0

The current Linux build environment does not provide compatible Streamlit or PyArrow packages, so a new Step 136 live Streamlit AppTest run is not claimed. The previously verified Step 134 all-page runtime baseline is preserved, while Step 136 native parsing, all fifteen native pipeline manifests, module scientific calculations, tables, viewers, worker registration, syntax, databases and regression suites were executed directly.
