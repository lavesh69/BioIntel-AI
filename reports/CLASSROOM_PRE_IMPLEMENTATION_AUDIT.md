# Classroom Pre-Implementation Audit

## Baseline
- Four authoritative Connect overlays were previously normalized into one `BioIntel-Step220` root; final preservation audit found zero legitimate source/page/script/config/document/asset paths missing.
- No dedicated Classroom package, migration, API router, or page exists.

## Reusable architecture
- Connect durable SQLite connection/migration conventions and authenticated local identities.
- Existing media storage and checksum validation.
- Connect notification, Calls/VC, accessibility, audit, and project services.
- Windows managed installer, wheelhouse, health checks and UserData separation.

## Required additions
- Tenant-scoped education database, centralized role/permission service, institution hierarchy, enrollments, timetable, attendance, assignments/submissions/grades, circulars/acknowledgements, guardian links, calendar and audit.
- Server-side tenant, class, teacher-assignment and guardian-child enforcement.
- Role-aware Streamlit workspace and FastAPI router.

## Security boundary
Education records remain private by default; institution ID is mandatory on every protected entity. Students cannot mutate attendance/results. Guardians need verified active links. Official results/circulars require authorized publication state.
