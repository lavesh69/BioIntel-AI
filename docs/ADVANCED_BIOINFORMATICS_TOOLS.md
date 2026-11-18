# Advanced bioinformatics tools add-on

BioIntel AI Step 92 adds an application-local resolver, version/status page, native Windows installer and optional WSL/Bioconda toolchain.

## Install locations

- Application: `%LOCALAPPDATA%\B91\BioIntel-AI`
- Toolchain: `%LOCALAPPDATA%\B91Tools`
- Download cache: `%LOCALAPPDATA%\B91Tools\cache`
- Tool state and checksums: `%LOCALAPPDATA%\B91Tools\state`

The tool installer is repair-safe: it does not delete existing reference databases or analysis results.

## Native portable core

The installer obtains official Windows distributions for NCBI BLAST+, MAFFT, FastQC, Bowtie 2, IQ-TREE, SnpEff and AutoDock Vina. Java 21 is installed application-locally for FastQC and SnpEff.

## WSL/Bioconda suite

Linux-first tools are installed in a dedicated Micromamba environment inside the selected WSL Ubuntu distribution. The application records the distribution, environment and detected executables.

## Reference database boundary

Kraken, MetaPhlAn, HUMAnN, Bakta, VEP, Pfam, SnpEff and BLAST databases are not silently downloaded because they may be very large, updated independently or subject to separate terms. Every workflow should record database release, checksum and assembly.
