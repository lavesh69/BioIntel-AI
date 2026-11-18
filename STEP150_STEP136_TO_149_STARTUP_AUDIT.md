# BioIntel AI Step 150 — Step 136–149 Windows Startup Audit

- ZIP archives scanned: **84**
- Exact bug introduced: **Step 145**
- Inherited by: **Step 146, Step 147, Step 148**
- Step 136–144: **not affected by this launcher argument bug**
- Step 149 archive: **fixed**, but a mixed/incomplete extraction can leave Step 145 files behind.

## Exact unsafe command

```bat
--root "%~dp0"
```

`%~dp0` ends with a backslash. Under the affected Windows command-line path, the closing quote could be retained as filename text, producing `BioIntel-AI"\reports` and WinError 123.

## Step-by-step result

| Step | Status |
|---:|---|
| 136 | Not affected |
| 137 | Not affected |
| 138 | Not affected |
| 139 | Not affected |
| 140 | Not affected |
| 141 | Not affected |
| 142 | Not affected |
| 143 | Not affected |
| 144 | Not affected |
| 145 | Affected |
| 146 | Affected |
| 147 | Affected |
| 148 | Affected |
| 149 | Not affected |

## Step 150 controls

- All four ZIP-part sentinels required before install/start.
- SHA-256 verification of critical launcher and preflight files.
- Startup refuses stale Step 145 files instead of executing them.
- Python preflight repairs accidental quote residue in root and environment paths.
- Separate self-healing hotfix for already extracted Step 145–149 folders.
- Clean four-part extraction launcher to avoid Windows “Skip existing files” mixes.
