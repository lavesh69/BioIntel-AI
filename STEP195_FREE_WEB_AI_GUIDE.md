# BioIntel AI Step 195 — Free Web AI

## User flow

1. Run `INSTALL_WINDOWS.bat`.
2. Run `RUN_BOTH_WINDOWS.bat`.
3. Open **Provider Integration Center → Free Web AI** and run the connection test.
4. Open **BioIntel Copilot** and select **Free Local + Web**.

## Components

- **Ollama:** local model generation at `http://127.0.0.1:11434`.
- **SearXNG:** private URL through `SEARXNG_URL`, or automatic discovery of a healthy HTTPS public instance.
- **Official providers:** NCBI, PubChem, UniProt, RCSB PDB, ChEMBL, Ensembl, ClinicalTrials.gov, Reactome, STRING, InterPro and Europe PMC.

The installer attempts a user-scope Ollama installation through Windows Package Manager and pulls `gemma3:1b` once. Set `BIOINTEL_SKIP_FREE_WEB_AI_SETUP=1` before installation to skip this optional step.

## Privacy

Ollama generation remains local. Web-search terms sent to public SearXNG and official provider APIs leave the computer. Do not submit patient identifiers or confidential project terms. For sensitive work, configure a private SearXNG instance.
