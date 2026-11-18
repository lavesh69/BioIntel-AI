# BioIntel AI 8.2.2 — Local Module Data Starter Kits

## Purpose

BioIntel AI now bundles local, offline starter files for data-consuming scientific modules. Users can download a correct blank template, a filled synthetic example, an expected-output example and a format guide from the active module without browsing external websites.

## User workflow

1. Open a supported module.
2. Expand **Local Data Starter Kit** in the sidebar.
3. Download the complete module ZIP or select an individual file.
4. Replace the synthetic example values while preserving required headers and file structure.
5. Upload the completed file in the same module.
6. Review validation messages before analysis.

## Implemented coverage

- Supported modules: **47**
- Complete module ZIP files: **47**
- Local starter-library files: **340**
- Network requests required: **0**
- Total local starter-library size: approximately **233 KB**
- Full application feature inventory preserved: **91 Streamlit entry points**

### Covered scientific formats

- CSV and TSV
- JSON
- FASTA, FA, FNA and FAA
- FASTQ
- VCF
- GFF3
- GMT
- Newick
- PDB
- Markdown and plain text

### Covered workflows

- DNA, RNA and protein sequence analysis
- Pairwise and batch sequence analysis
- SMILES, ADMET and discovery workflows
- DTI feature building, training, prediction and evaluation
- Dataset registration, validation and batch jobs
- Evidence, release-gate and report workflows
- Document extraction, OCR and evidence linking
- FASTQ/genome QC and variant annotation
- Primer, CRISPR and codon design
- Transcriptomics, proteomics and multi-omics integration
- Structural bioinformatics and pathway analysis
- qPCR, ELISA, enzyme kinetics and bioprocess analytics
- Microbiology and metagenomics
- PPI, comparative pathogen genomics, single-cell and cancer genomics
- Connected-provider configuration without embedded secrets

## Safety and scientific boundaries

- Examples are explicitly labelled synthetic/demo data.
- No example is represented as clinical, regulatory or experimental evidence.
- Provider configuration examples contain no API secrets.
- All file paths are local and constrained to `data/module_starter_kits`.
- Each module ZIP passed CRC and path-safety checks.
- Large scientific datasets are intentionally not bundled, keeping startup and package performance stable.

## UI integration

The shared application shell detects the active page key and renders the starter-kit panel only for supported modules. Unsupported pages receive no extra controls. File bytes and the starter-kit catalog use Streamlit caching to avoid repeated disk reads on reruns.

A Windows helper is also included:

```text
OPEN_MODULE_STARTER_KITS_WINDOWS.bat
```

This opens the full local starter-kit folder directly from the extracted application.

## Verification completed

- Full Streamlit entry-point sweep: **91/91 passed**
- Starter-kit module rendering: **47/47 passed**
- Starter-kit complete-download control: **47/47 passed**
- Starter-kit catalog and archive tests: **3/3 passed**
- Focused UI, reliability and hardening tests: **25/25 passed**
- Python source compilation: **586 files, 0 failures**
- Ruff scan: **0 findings**
- Starter ZIP CRC errors: **0**
- Unsafe starter ZIP paths: **0**

## Version

BioIntel AI version: **8.2.2**
