# BioIntel AI Step211 / Windows V19.5 — BioIntel Live Workspace Release Test Report

## Scope

Peak-potential trusted-LAN collaboration layered on the complete V19.4 scientific platform. Existing scientific modules and the V19.1–V19.4 installer/runtime work are retained. Protected DTI, DTI Validation, LIMS/ELN and instrument modules are unchanged.

## Implemented collaboration capability

- Personal Local Mode, Host Lab Workspace and Join Lab Workspace.
- Named local accounts with PBKDF2 password hashes, optional TOTP and revocable browser sessions.
- Hashed expiring invites and Owner/Admin/Researcher/Reviewer/Viewer/Guest roles.
- Per-member category, module and project restrictions.
- Heartbeat live presence, safe current module/page/record aliases and same-record viewers.
- Renewable record locks, controlled takeover, revision hashes and offline conflict checks.
- Threaded comments, mentions, edit history, resolve/reopen and scientific review lifecycle.
- Shared tasks, evidence bookmarks, cross-module project links, research timeline and notifications.
- Neuro-aware annotations for EEG events, imaging ROIs, variants, biomarkers, histology and safe timeline metadata.
- Shared analysis-job status, duplicate workflow warning and authorized control requests.
- Follow-host sessions with safe navigation/pointer synchronization and no screen spying.
- Recoverable trash, audit export, database health, retention cleanup and integrity-protected backup/restore.
- Scheduled collaboration SQLite snapshots with retention.
- WebSocket reconnect snapshots, activity-cursor resync and optional local LAN HTTPS.

## Automated validation completed before packaging

- Current release/core regression set: **115 passed**.
- Neuro/CNS backend regression: **117 passed**.
- Bioinformatics backend regression: **65 passed**.
- Discovery and Lab Analytics backend regression: **20 passed**.
- BioIntel Live Workspace focused tests: **22 passed**.
- Protected-module hash checks: **2 passed**; **17/17 recorded protected hashes unchanged**.
- Python source compilation: **1,434 checked, 0 syntax errors**.
- Runtime supervisor self-check: passed.

## Validation boundary

The build environment is Linux with Python 3.13 and does not provide native Windows BAT execution or Streamlit AppTest. The installer requires CPython 3.11.9 x64 and runs blocking native-Windows UI, API, worker, SQLite and Streamlit readiness checks before managed-release activation.

BioIntel Live Workspace is intended for trusted private LANs or an administrator-managed private VPN. Direct public-internet port forwarding, external identity federation, full Google-Docs-style text merging and clinical authorization are not claimed.
