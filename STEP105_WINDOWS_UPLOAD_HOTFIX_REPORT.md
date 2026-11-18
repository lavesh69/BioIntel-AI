# BioIntel AI Step 105 — Windows Worker and 1 GB Upload Hotfix

This maintenance build addresses two user-reported problems without changing the scientific release version.

## Windows startup repair

- Replaced the Windows `os.kill(pid, 0)` liveness probe that could raise `WinError 87`.
- Added a non-destructive Windows process-handle check using `OpenProcess` and `WaitForSingleObject`.
- Treats protected processes safely and rejects invalid/stale PID values.
- Automatically removes stale `background-worker-state.json` files and recovers orphaned jobs.

## Upload repair

- Global Streamlit upload and message transport limits are now 1,024 MB (1 GB) per file.
- All 21 Step 102/103 expansion modules now open with the upload workflow selected and the uploader enabled.
- All 14 Step 104 scientific modules now open with the upload workflow selected and the uploader enabled.
- Upload pickers list only formats that the selected module can actually parse.
- H5AD is exposed for Cell Atlas Mapping; BED, VCF, FASTA, images, molecular structures and mzML are exposed only in compatible modules.
- Each shared uploader displays the 1 GB limit and rejects files above it.

## Scope and boundary

1 GB is the transport ceiling, not a guarantee that every analysis can process a 1 GB file in memory. Large raw datasets should use background, indexed or reference-based workflows where available. Module-specific safety limits may remain lower where a parser or algorithm requires bounded memory.
