# Troubleshooting Guide

If startup fails, verify managed Python, `VERSION`, `PYTHONPATH`, writable UserData, disk space, and that no stale process owns the configured ports. Run compile/import checks and inspect sanitized logs.

For database problems, run platform integrity and audit-chain checks before restoring a verified backup. For analysis problems, inspect canonical input columns, dataset origin, sample sufficiency, QC, and dependency health. For ZIP delivery problems, confirm all five part names and SHA-256 hashes match the release manifest.
