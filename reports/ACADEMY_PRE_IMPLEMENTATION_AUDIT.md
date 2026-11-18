# Academy Pre-Implementation Audit

## Existing capability
Calls/VC, durable media objects, document exports and accessibility settings exist. No educator/course/lecture/enrollment/watch-progress/quiz/certificate/content-rights ecosystem exists.

## Reuse
- Authenticated Connect identities and Calls capability reporting.
- Media checksum/storage primitives and Windows FFmpeg detection conventions.
- Moderation/audit patterns.

## Required additions
Tenant-scoped educator profiles, courses and hierarchy, lecture upload metadata, rights confirmations, actual file validation/checksum, processing adapter with honest dependency state, enrollment, watch progress/events, quizzes, certificates with completion gates, discussions, moderation and live-class links.
