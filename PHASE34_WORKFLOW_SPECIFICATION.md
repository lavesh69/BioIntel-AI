# Phase 34 Workflow Specification

Schema identifier: `biointel.research-workflow.v1`

Each versioned workflow records project, name, domain, semantic version,
canonical specification SHA-256, validation status, lifecycle state, approver,
creator, and timestamps.

Each step records:

- unique step ID and directed dependencies;
- approved tool ID, name, version, expected inputs and outputs;
- bounded parameters and resources (CPU, memory, disk, GPU metadata);
- timeout and retry limits;
- cache/checkpoint flags;
- controlled execution adapter.

Validation rejects missing dependencies, cycles, duplicate step IDs, unapproved
tools, unsupported parameters, and all ordinary-user `command`, `shell`, or
`executable` fields. Submission also rejects datasets whose file formats are not
accepted by every workflow step.

Native executable templates:

| Template | Domain | Status |
|---|---|---|
| `genomics_fasta_qc` | genomics | native executable |
| `genomics_fastq_qc` | genomics | native executable |
| `variant_vcf_qc` | population genetics | native executable |
| `omics_table_qc` | transcriptomics/proteomics/microbiome | native executable |
| `structure_metadata` | structural biology | native executable |

The alignment/annotation, single-cell clustering, taxonomic classification,
docking, and phylogenetics entries are adapter interfaces only. Their third-party
tools are not bundled and no execution claim is made.

Nextflow, Snakemake, CWL, WDL, command-line, container, institution worker,
Docker, Kubernetes, Slurm, SSH batch, and object-storage integrations are
represented by controlled adapter boundaries. They remain disabled until a real
administrator configuration and infrastructure validation exists.
