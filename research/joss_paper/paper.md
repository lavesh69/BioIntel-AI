# BioIntel AI: A Windows-First Modular Platform for Reproducible Bioinformatics and Biomedical AI Workflows

**Author:** Lavesh Dobriyal  
**Software release:** BioIntel AI 15.0.0 / Step 192  
**Status:** Draft for author review; not yet peer reviewed

## Abstract

BioIntel AI is a Windows-first modular research platform that integrates bioinformatics, multi-omics, biomedical artificial intelligence, scientific workflow orchestration, provenance, validation and reporting. Release 15.0.0 contains 80 major logical modules and a shared project, sample, background-job, engine, reference, evidence and reproducibility layer. This paper describes the software architecture, internal deterministic benchmark framework, installation-integrity controls and limitations. Internal synthetic benchmarks test software correctness and repeatability; they are not substitutes for independent scientific, clinical, wet-lab, instrument or regulatory validation.

## Statement of need

Biomedical researchers commonly combine disconnected command-line tools, notebooks, web applications and manual reports. This fragmentation increases repeated uploads, inconsistent metadata, weak provenance and difficult Windows deployment. BioIntel AI provides a common desktop-oriented workspace with guided and expert workflows, reusable project assets, fail-closed validation gates and offline installation support.

## Architecture

The system uses a Streamlit interface, Python scientific services, SQLite-backed registries, a persistent job layer, module-specific adapters and versioned evidence/report artifacts. Shared services cover projects and samples, engine/reference qualification, cross-module handoffs, provenance, review states, diagnostics and multi-format reporting.

## Modules

The 80 major modules span genomics, single-cell and multi-omics, microbiome, protein and molecular design, imaging and spatial biology, clinical/pharma analysis, AI/model lifecycle, evidence/knowledge systems and platform operations. Each module includes a standard lifecycle covering overview, demo, inputs, QC, analysis, results, visualisation, validation, interpretation, reporting, history and qualification.

## Internal reproducibility benchmark

Each module includes a deterministic synthetic fixture, expected output, input/output SHA-256 hashes, three-run repeatability records, runtime metrics, intended-use notes and limitations. These benchmarks verify that software-owned analysis and reporting paths execute reproducibly. External comparison and scientific validity must be demonstrated separately using authentic datasets and qualified tools.

## Release integrity

Step 192 introduces atomic four-part ZIP construction, CRC testing before final rename, exact cross-part file verification, current-version consistency checks and an extracted-folder SHA-256 manifest. The release also repairs a corrupted SciPy wheel discovered in the prior offline wheelhouse and adds current-release validation to the classic `INSTALL_WINDOWS.bat` followed by `RUN_BOTH_WINDOWS.bat` workflow.

## Results

The Step 176–192 focused regression suite contains 102 passing tests. All source, page, script and test Python files compile on the build host. All 80 module publication packs are present and the Windows wheelhouse manifest, hashes and ZIP structures pass verification. The complete legacy UI suite was not executed on the Linux build host because that host lacks the packaged Python 3.11/Streamlit runtime; it must be executed after Windows installation or in the configured CI environment.

## Limitations

The bundled datasets and internal benchmarks are synthetic or demonstrative unless explicitly identified otherwise. No claim is made that all modules are clinically validated, wet-lab confirmed, regulatorily approved or superior to established tools. Licensed production databases, qualified external engines, independent cohorts, physical instrument evidence and formal expert approvals remain required according to intended use.

## Availability

The frozen four-part archive, checksums, package-integrity report, citation metadata and software bill of materials are prepared for archival upload. Public repository and DOI fields remain pending owner action. The current research-evaluation licence is not an OSI-approved licence and may need replacement before submission to journals requiring open-source licensing.

## AI-assistance disclosure

AI assistance was used during software and documentation development. All released code, claims, tests and manuscripts require human author review and responsibility.
