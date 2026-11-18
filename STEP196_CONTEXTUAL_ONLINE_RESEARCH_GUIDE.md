# BioIntel AI Step 196 — Contextual Online Research in 80/80 Major Modules

Every major module now includes a collapsed **Online Research & AI** panel with three modes:

1. **Free Web AI Answer** — SearXNG and official-provider evidence is summarized locally through Ollama.
2. **Official Database Results** — direct provider API results without requiring Ollama.
3. **Open Websites** — direct official website links with the current query handed off where supported.

Provider selection is contextual. Genomics uses NCBI and Ensembl; protein and structural modules use UniProt, RCSB, InterPro and STRING; discovery uses PubChem and ChEMBL; clinical modules use ClinicalTrials.gov and Europe PMC; pathway and omics modules use Reactome, STRING, NCBI and Europe PMC.

## Windows workflow

1. Run `INSTALL_WINDOWS.bat`.
2. Run `RUN_BOTH_WINDOWS.bat`.

No paid AI API key is required for the Free Web AI mode. A local Ollama model is downloaded once. Public SearXNG queries leave the computer, so confidential or patient-identifiable data must not be entered. Configure a private SearXNG instance for sensitive work.
