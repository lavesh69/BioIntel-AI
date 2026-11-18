# BioIntel Education Universe qualification and known limitations

## Qualified in this release

- BioIntel Classroom, Science Pulse, Academy & Lecture Studio, and Education Universe are directly visible in the primary sidebar and on Home.
- The Education Universe exposes twenty named module contracts through one shared Streamlit page, FastAPI router and SQLite database; it does not create separate authentication or tenant systems.
- Three additive entities persist tenant-scoped records, immutable workflow events and idempotent offline operations. Optimistic versions reject stale updates, soft delete is available, and an explicit development rollback exists.
- Institution membership and role checks are applied server-side. Two-institution tests cover cross-tenant denial; protected question-bank records are unavailable to student roles.
- Real evidence/source gates are enforced for explainable learning plans, virtual-lab simulation-only records, source-linked library/opportunity entries, processing completion, analytics definitions, collaboration approvals and reproducibility privacy.
- Offline synchronization never silently overwrites a changed server record. Conflicts retain both the queued patch and current server version until the owner explicitly chooses `keep_server` or `apply_client`.
- Test evidence for this bounded pass: 16/16 education unit/integration/API/security tests passed; four education page AppTests and Home rendered with zero exceptions; AppTest created a real institution and persisted an adaptive-learning record.

## Not qualified as complete production capability

The PDF requests twenty full bespoke products. This bounded release provides a real shared workflow core for all twenty, but the following require additional implementation or configured infrastructure:

- Adaptive recommendations are not automatically calculated from attendance/quiz streams; there is no spaced-repetition scheduler.
- Virtual labs have safe workflow records but no interactive simulation engine or practical content library.
- The bioinformatics sandbox rejects shell fields and validates resource limits, but no isolated compute/notebook worker is bundled.
- Shiro Tutor records are labelled and review-gated; no grounded AI provider or institution-material retrieval was configured or tested.
- ERP, library, research, competitions, career, portfolio, laboratory, assessment, analytics, quality and gamification have durable workflows, but the bespoke calculators, feeds, exports and specialized screens listed in the matrix remain incomplete.
- No ASR, translation, synthetic dubbing or transcript processor was configured. Lecture-intelligence completion is deliberately blocked without a real output artifact.
- Offline version/conflict handling is qualified. Encrypted offline content caches, a campus LAN deployment and LAN live classes are not qualified.
- No accreditation, child-safety legal certification, verified external opportunity feed, payment provider or credential authority is claimed.

## Calls and media boundary

Authenticated WebRTC signaling and local peer-to-peer browser calls are preserved. TURN relay, SFU/group media, server recording files, transcription, PSTN and production cross-network media were not configured or proven. The application must continue to report those capabilities as configuration-required/unavailable.

## Production decision

This release is suitable for local evaluation and continued integration of the qualified workflow core. It is **not** evidence that every feature in the Education Universe master PDF is production-complete. External deployments involving minors, grades, institutional records or public credentials require independent security, privacy, accessibility, legal and operational review.