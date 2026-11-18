# Education / Science Pulse / Academy Implementation Status

Final qualification label for this pass: **IMPLEMENTED WITH CONFIGURATION-REQUIRED FEATURES**. This is not a claim that every item in the 55-phase aspiration is production-complete.

| Area | Verified local capability | Status |
|---|---|---|
| Classroom | institution/units/subjects, memberships, teacher assignment, enrollment, timetable conflict detection, attendance/lock/correction, guardian isolation, materials, assignments/submissions/grading, exams/results, circular approval/acknowledgement, dashboard/search, restart persistence | LOCAL MODE |
| Science Pulse | HTTPS Crossref-compatible and RSS adapters, bounded responses, DOI/PMID dedupe, preprint/retraction labels, lawful excerpts/links, alerts, saved research, cited AI-summary records, graceful sync jobs | LOCAL MODE; provider configuration required |
| Academy | educator authorization, rights declaration, original video upload/hash, courses, enrollment, progress, quizzes, completion-gated certificates, moderation reports | LOCAL MODE; FFmpeg processing configuration required |
| Calls/VC | authenticated WebRTC signaling client, membership isolation, peer-to-peer mesh capability disclosure | LOCAL MODE; TURN/SFU/recording/transcription unavailable until configured and verified |
| Shiro | existing standalone project-evidence assistant preserved | CONFIGURATION REQUIRED for institution-scoped education integration |
| Windows | CPython 3.11.9 x64 preflight and short managed-path checks passed | Final archive install retest follows manifest rebuild |

See `BIOINTEL_NEW_MODULES_KNOWN_LIMITATIONS.md` for incomplete product areas.
