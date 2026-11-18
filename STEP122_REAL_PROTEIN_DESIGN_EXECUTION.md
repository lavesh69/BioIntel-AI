# Step 122 — Real Protein Design Execution Upgrade

## Scope

This release upgrades only the AI Protein Design & Mutation Engineering workflow while preserving all existing modules and the requested excluded/locked source pages.

## Added capabilities

- Five guided local backends: ProteinMPNN, RFdiffusion, ColabFold, FoldX and RosettaScripts.
- Immutable PDB/FASTA staging with SHA-256 input manifests.
- PDB atom, chain, residue and model validation before execution.
- Protein sequence validation with bounded length and strict amino-acid alphabet.
- Executable discovery through application-local tools, PATH, manifest aliases, WSL or explicit environment overrides.
- Model/database asset registry with directory/file SHA-256, quick fingerprints and recorded licence acceptance.
- CPU, memory, disk and CUDA preflight.
- Bounded backend-specific parameters instead of arbitrary shell arguments.
- ProteinMPNN chain and fixed-position constraints with a persistent JSONL constraint file.
- RFdiffusion deterministic seed, contig and hotspot controls.
- ColabFold model/recycle/relax/template controls.
- FoldX mutation-list validation and persistent mutation file.
- RosettaScripts staged XML and deterministic nstruct execution.
- Audited subprocess execution without shell interpolation.
- Persistent planned/running/completed/failed checkpoints.
- Resume completed runs without duplicate execution.
- FASTA, PDB/mmCIF, confidence JSON and energy-table output parsing.
- Candidate-level sequence identity, substitution, hydrophobicity, charge and liability summaries.
- Output file size and SHA-256 inventory.
- Headless JSON request runner and Windows launchers.
- Explicit scientific and clinical release gates.

## Execution boundary

The software can execute locally installed backends only when their executable, official/local model assets, integrity evidence, licence acknowledgement and hardware prerequisites are available. It does not redistribute restricted weights and does not claim that generated sequences or structures are experimentally validated.

## Required external confirmation

- Independent structural review and clash/interface assessment
- Expression and solubility testing
- Folding and stability assays
- Binding and functional activity assays
- Safety, novelty and intellectual-property review
