# Known Limitations

Release: `15.6.0-Step220.0-WINDOWS-V20.3`

- External aligners, variant callers, pathway databases, structure tools, R/Bioconductor engines, GPU stacks, and institutional LIMS/ELN services are not bundled universally. Their adapters and dependency reporting are `Complete with optional dependency`.
- Deep BAM/CRAM/BCF, HDF5/h5ad/Loom, DICOM, NIfTI, Parquet, and whole-slide validation requires the corresponding optional Python packages.
- Imaging and spatial analytics provide QC, summary, neighborhood, and metadata workflows; full pathology segmentation, registration, and foundation-model inference are `Partially complete`.
- Explainability stores model explanation records and supports feature-level values supplied by callers. Automatic SHAP/LIME computation for arbitrary third-party models is `Partially complete` and depends on model-specific packages.
- The local execution engine safely runs registered Python analysis functions. Full distributed HPC/Kubernetes scheduling and remote cluster credentials are `Partially complete`.
- Literature verification records identifiers, versions, retraction/correction states, and provenance. Live retraction/database checks need network access and are `Complete with optional dependency`.
- Local authentication and project/dataset RBAC are implemented. Enterprise SSO, directory federation, and hardware-backed key management are `Blocked by unavailable external service` until configured by an administrator.
- The UI exposes the connected core workflows; highly specialized controls from all historical domain pages remain in their existing pages rather than being duplicated in the Step220 workspace.
- Scientific conclusions are not automatically validated. Human review, laboratory validation, external cohort confirmation, and regulatory processes remain required.
