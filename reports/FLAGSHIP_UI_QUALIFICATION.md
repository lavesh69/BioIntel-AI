# BioIntel Flagship UI Qualification — 2026-07-28

## Qualified scope

This bounded UI pass upgrades four integrated Streamlit surfaces without replacing their persistence or authorization layers:

- BioIntel Classroom: role-aware overview, subjects and memberships, attendance, assignments and grading, circulars, and unified search.
- BioIntel Science Pulse: source-linked discovery, saved research, durable alerts, source registration/synchronization states, and verified metadata ingestion.
- BioIntel Academy & Lecture Studio: educator/learner workspaces, rights declarations, hashed lecture uploads, durable progress, quizzes, completion credentials, safety reports, and live-class handoff.
- BioIntel Connect: persisted network/activity/conversation/community metrics, feed modes, action links, profile readiness, notifications, and an honest Calls readiness card.

The UI uses Streamlit native containers, Material icons, responsive one-to-four-column layouts, `width="stretch"`, clear empty/error states, and forms for batched writes. Counts and records come from local persistent services; no synthetic activity or media capability is presented.

## Verification evidence

- Python compile: changed UI modules and wrapper passed.
- Regression suite: 26/26 targeted Education and Connect tests passed.
- Streamlit AppTest: Classroom 6/6 sections, Science Pulse 4/4 sections, Academy 5/5 views, and Connect Home rendered with zero final exceptions/errors.
- Interactive Science Pulse alert: persisted and appeared after rerun.
- Connect capability evidence: topology `peer-to-peer-mesh`; maximum four peers; TURN, recording, and transcription remained explicitly not configured.
- Agent live HTTP smoke: Streamlit returned HTTP 200.
- Navigation targets used by the Connect hub: 12/12 files present.

## Honest production boundary

This is a production-style, locally integrated application release. Small-room peer-to-peer media and authenticated signaling are the qualified Calls boundary. No TURN relay, SFU/group-media service, server-side recording, transcription/ASR, synthetic dubbing, external AI provider, isolated bioinformatics compute, or accreditation service is claimed without real configuration and evidence. Lecture uploads preserve original media; FFmpeg detection alone is reported as requiring worker qualification and is not treated as proof of transcoding.

## Windows and packaging

The four physical ZIPs overlay into one `BioIntel-Step220` directory. The release packager regenerates source hashes, embeds per-part manifests and all four `shiro4_partN.ok` markers under the expected root, performs safe extraction, and deep-verifies the reconstruction. Runtime state is excluded from archives.