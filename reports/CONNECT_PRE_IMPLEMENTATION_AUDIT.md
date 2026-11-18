# BioIntel Connect pre-implementation audit

Generated from the four authoritative CONNECT-UPGRADED archives before new Completion Specification source edits.

## Inventory

- BioIntel-AI-15.6.0-CONNECT-UPGRADED-Part1.zip: 8,926 files, 270,413,445 bytes
- BioIntel-AI-15.6.0-CONNECT-UPGRADED-Part2.zip: 8,927 files, 270,411,723 bytes
- BioIntel-AI-15.6.0-CONNECT-UPGRADED-Part3.zip: 8,928 files, 270,414,640 bytes
- BioIntel-AI-15.6.0-CONNECT-UPGRADED-Part4.zip: 8,928 files, 270,414,302 bytes
- Canonical normalized tree: 24,502 files
- Exact-path duplicates: 1
- Normalized collisions: 11253 (155 content conflicts, 11098 identical)
- Connect modules: 25
- Connect pages: 30
- Connect tests: 12

## Confirmed packaging defects

- Source split between archive root and `BioIntel-Step220/`.
- Calls UI and shiro4 markers were outside the installer root.
- Installer filename expectations did not match supplied archive names.
- Step220 markers were split between both roots.

## Canonical merge plan

1. Use one `BioIntel-Step220` root.
2. Overlay archive-root relative paths while preserving unique files.
3. Resolve every normalized content conflict explicitly.
4. Keep one `src/`, one `pages/`, one migration path, and one Windows workflow.
5. Exclude runtime data, databases, caches, logs, secrets, old ZIPs, and `UserData`.
6. Generate four strict-allowlist release ZIPs only after validation.
