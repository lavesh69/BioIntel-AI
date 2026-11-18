# BioIntel AI Step 92 — Advanced Bioinformatics Tools Integration

## Implemented

- Application-local advanced-tool manifest and resolver
- Native Windows and WSL execution backends
- Windows-to-WSL path conversion for file arguments
- One-click native portable core installer
- Optional full Bioconda environment for Linux-first tools
- Download cache, SHA-256 state records and repair-safe reruns
- Dedicated Advanced Bioinformatics Tools interface
- Tool availability integrated into capability, phylogeny, pathogen, docking and metagenomics workflows
- Explicit separation of executable packages from large reference databases

## Scientific boundary

Bundling an executable does not validate a scientific workflow. Each analysis still requires version-locked tools, declared reference databases, quality controls and domain-appropriate validation.
