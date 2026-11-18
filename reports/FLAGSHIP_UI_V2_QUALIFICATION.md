# BioIntel flagship UI V2 qualification

Qualified on 2026-07-28 against the assembled `BioIntel-Step220` source tree.

## Delivered surfaces

- **BioIntel Classroom:** institution-aware hero, role-specific quick actions, persisted student/teacher/admin progress, tenant-filtered audit activity, onboarding, and the existing attendance, subjects, people, timetable, assignments, results, and circular workflows.
- **BioIntel Science Pulse:** verified-source hero, real publication/news/saved/alert/source counts, source and correction/retraction state on records, persisted alert-match counts, source configuration boundary, admin-gated ingestion/sync, and empty-source onboarding.
- **BioIntel Academy & Lecture Studio:** institution context, persisted course/studio/learner metrics, rights and media-readiness state, course catalogue, learner progress, live-class boundary, credentials, and safety controls.
- **Shiro AI:** project-isolated evidence workspace, persisted source/chunk/conversation/job metrics, honest provider readiness, evidence onboarding, grounded prompt starters, native chat, traceable citations, source preview, and direct Home/primary-sidebar discovery.

## Functional evidence

- Seven changed Python surfaces compiled successfully.
- Combined empty-state AppTests rendered Classroom, Science Pulse, Academy, and Shiro with zero exceptions and zero UI errors.
- Classroom seeded administrator and student passes covered all six sections with zero exceptions; quick navigation and empty onboarding also passed.
- Science Pulse seeded passes covered Discover, Saved research, Alerts, and Sources with zero exceptions; alert matches and source configuration state were persisted.
- Academy seeded passes covered Overview, Educator Studio, Learn, Live Classes, and Credentials & Safety with zero exceptions.
- Shiro seeded one real local evidence source, exposed four prompt starters, prefilled the native composer, generated a local grounded answer, rendered citations, and persisted the conversation with zero exceptions/errors.
- Home AppTest rendered after adding Shiro to the flagship learning entry points with zero exceptions/errors.
- 51 targeted education, Connect, and Shiro unit/integration tests passed.

## Truth boundary and known limitations

This is a production-style local UI and persistence integration, not evidence that every external service is deployed.

- Calls qualify authenticated signaling and small-room peer-to-peer WebRTC only. TURN relay, SFU/group-media infrastructure, server-side recording, and transcription/ASR are configuration-required and are not claimed.
- Academy records configured media/rights/readiness state. FFmpeg detection alone is not claimed as a qualified production transcoding worker.
- Science Pulse external providers require real configuration and successful source evidence; the UI does not invent provider health, delivery, publications, or news.
- Shiro local grounded generation is qualified. Ollama and external/OpenAI providers remain unavailable until explicitly configured; external evidence transmission is disabled by default.
- Accreditation, legal certification, synthetic dubbing, isolated bioinformatics compute, and production cloud availability are not claimed.

## Packaging acceptance

Distribution is accepted only when all four archives are present, ZIP CRC/safe-path checks pass, the reconstructed tree matches the source manifest, all four `shiro4_partN.ok` markers exist under `BioIntel-Step220/.release_parts`, and packaged Windows install/run preflight exits successfully.