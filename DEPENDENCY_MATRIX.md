# Dependency Matrix

The native Step220 analysis framework uses bundled Python packages where available and reports optional tool state explicitly.

| Capability | Native/bundled dependency | Optional external dependency | Offline behavior |
|---|---|---|---|
| Core API and schemas | FastAPI, Pydantic | None | Fully local |
| UI | Streamlit, pandas, Plotly | None | Fully local |
| Persistence | Python `sqlite3` | None | Fully local |
| Numeric/scientific analysis | NumPy, pandas, SciPy, scikit-learn, statsmodels | R/Bioconductor for specialist parity | Native algorithms remain available |
| Reports | reportlab, python-docx, openpyxl | None | Fully local |
| FASTQ/FASTA/VCF/text ingestion | Python standard library | FastQC, MultiQC | Native validation plus optional tool execution |
| BAM/CRAM/BCF | Header detection | pysam, samtools, Picard, bcftools | Dependency-missing state is explicit |
| Alignment | Native QC and mapping summaries | STAR, HISAT2, BWA-MEM2, minimap2 | Existing result analysis remains available |
| Variant annotation | Native prioritization | VEP, SnpEff, bcftools | Existing annotated tables remain analyzable |
| HDF5/single-cell | pandas/native adapters | h5py, scanpy ecosystem | CSV/table analyses remain available |
| Proteomics/metabolomics | Native table engines | ProteoWizard/msconvert, DIA-NN | Existing processed tables remain analyzable |
| Microbiome | Native abundance analysis | Kraken2, Bracken, MetaPhlAn, HUMAnN, QIIME2 | Existing abundance tables remain analyzable |
| Imaging | Native QC summaries | Pillow, pydicom, nibabel | Optional format-specific validation |
| Secrets | Windows DPAPI or keyring fallback | OS keyring | Environment-only fallback is explicit |
| Enterprise identity | Local PBKDF2 accounts | SSO/directory provider | Local offline accounts remain available |

## Verified external-tool state in this Windows environment

`Rscript`, `bcftools`, `bracken`, `bwa-mem2`, `diann`, `fastqc`, `hisat2`, `humann`, `kraken2`, `metaphlan`, `minimap2`, `msconvert`, `multiqc`, `picard`, `qiime`, `samtools`, `snpEff`, `star`, and `vep` were not found on PATH during release verification. They are optional and each has setup guidance in the Dependency Manager.
