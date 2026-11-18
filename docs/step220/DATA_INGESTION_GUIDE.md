# Data Ingestion Guide

Register the project and dataset before importing files. The ingestor detects supported genomics, transcriptomics, proteomics, metabolomics, imaging, spatial, and general formats; validates structure/schema where possible; streams SHA-256 and copies; rejects empty/corrupt/unsafe archives; and detects same/cross-dataset duplicates.

Use required-column checks for tabular workflows. Optional packages enable deeper BAM/CRAM/BCF, HDF5, DICOM, NIfTI, TIFF, and Parquet inspection. A dependency-missing result is not equivalent to a validated file.
