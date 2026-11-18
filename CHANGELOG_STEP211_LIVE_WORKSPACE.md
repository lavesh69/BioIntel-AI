# Step211 — BioIntel Live Workspace Collaboration Upgrade

## Scope

Peak-potential local/LAN collaboration added on top of the complete V19.4 scientific platform. Existing module functionality is retained. Protected DTI, DTI Validation, LIMS/ELN and instrument modules are unchanged.

## Collaboration foundation

- Personal Local Mode remains the default safe path.
- Host Lab Workspace binds the Streamlit UI to a trusted LAN only after named UI accounts exist.
- Join Lab Workspace supports a workspace code or a secure time-limited invite token.
- Live heartbeat presence shows permitted module/page, activity and pseudonymized record alias.
- Same-record viewers and current editing/reviewing/running state are visible to authorized members.
- Stale browser presence and expired locks are cleaned automatically.

## Safe editing and scientific review

- Renewable record locks with controlled Owner/Admin takeover.
- SHA-256-backed record revisions and optimistic conflict checks.
- Offline-safe drafts that must pass a latest-revision check before application.
- Threaded comments, replies, mentions, edit revisions, resolve/reopen.
- Review lifecycle: draft, ready, requested, in review, reviewed, approved, changes requested, rejected, closed and archived.
- Neuro-aware annotations for EEG events, imaging ROIs, variant evidence, biomarkers, histology regions and safe timeline metadata.

## Team workflow

- Shared tasks and assignments.
- Evidence/bookmark library.
- Cross-module project and subject links.
- Research timeline.
- Shared analysis-job progress and duplicate workflow warning.
- Owner/admin/owner-controlled pause, resume, retry and cancellation requests.
- Notification centre and per-member notification preferences.
- Follow-host collaboration sessions with safe module, record and pointer synchronization—no screen spying.

## Security, privacy and administration

- Owner, Admin, Researcher, Reviewer, Viewer and Guest workspace roles.
- Per-member category, module and project access restrictions.
- PBKDF2 password hashes; optional TOTP authenticator codes.
- Hashed expiring invite tokens and revocable browser account sessions.
- Workspace privacy and presence-detail controls.
- Raw scientific uploads/results are never sent through presence or WebSocket events.
- Optional local self-signed LAN HTTPS certificate generation.
- API LAN exposure remains disabled by default and requires an explicit API key.

## Reliability and recovery

- SQLite WAL collaboration database.
- Integrity-protected workspace export and restore-as-new-workspace.
- Scheduled integrity-checked SQLite snapshots with retention.
- Recoverable trash.
- Audit JSON/CSV export.
- Database health and integrity dashboard.
- Retention cleanup.
- WebSocket reconnect/resync using an activity cursor and snapshot requests.

## Boundaries

This is collaboration and research-workflow software, not clinical authorization or public-internet hosting. Direct port forwarding is unsupported. Remote access should use an administrator-managed private VPN. Full Google-Docs-style simultaneous rich-text merging and remote identity federation are not claimed.
