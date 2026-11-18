# BioIntel Education Demonstration Data Report

Generated: 2026-07-28  
Seed version: `education-demo-2026.07-v1`

## Isolation contract

The demo workspace uses `UserData/education/education-demo.sqlite3` and `UserData/education/demo-media` (or the equivalent configured `BIOINTEL_USER_DATA_DIR`). It never writes demo rows into `education.sqlite3`. Every counted synthetic entity has a permanent row in `education_demo_entities` containing:

- `is_demo = 1`
- `data_origin = synthetic_demo`
- `demo_scenario`
- `seed_version`
- `created_by_demo_seed = 1`
- demo institution/persona attribution where applicable
- stable created/updated timestamps

The reset function validates the exact database and media names, their common parent, and a non-root target before removal. Production database/media targets are preserved and covered by tests.

## Deterministic contents

| Entity | Count |
|---|---:|
| Institutions | 2 |
| Switchable fictional personas | 14 |
| Stable cohort teachers | 10 |
| Stable cohort students | 50 |
| Memberships | 74 |
| Subjects | 8 |
| Attendance sessions / records | 90 / 90 |
| Assignments / submissions / grades | 15 / 109 / 109 |
| Examinations / results | 6 / 43 |
| Courses / sections / lectures | 8 / 16 / 30 |
| Academy enrollments / watch progress | 56 / 56 |
| Publications / news / alerts | 40 / 25 / 10 |
| Education Universe records | 20 (one per module) |
| Counted synthetic records | 965 |

All publication/news URLs use the reserved `example.invalid` domain. They are visibly synthetic and never presented as live scientific feeds. Lecture processing stays `configuration_required` or equivalent until a real provider creates an output.

## Personas

The selector contains fourteen fictional roles spanning university administrator, school administrator, department head, professor, teacher, lab instructor, research mentor, librarian, career coordinator, academic coordinator, moderator, university student, school student, and guardian. The additional cohort members are stable synthetic users but are intentionally not exposed as selector personas.

## Cross-module scenarios

1. Student learning lifecycle: Classroom → Academy → Shiro Tutor → Learning Analytics → Portfolio.
2. Teacher course workflow: Academy → Shiro Tutor → Lecture Intelligence → Classroom.
3. Student research workflow: Science Pulse → Digital Library → Research Hub → Shiro Tutor → Portfolio.
4. Live lecture workflow: Classroom → Lecture Intelligence → Academy → Shiro Tutor.

## Operation

From the project root:

```text
SEED_EDUCATION_DEMO_WINDOWS.bat
RESET_EDUCATION_DEMO_WINDOWS.bat
```

Cross-platform CLI equivalents:

```text
python scripts/seed_biointel_education_demo.py
python scripts/reset_biointel_education_demo.py
```

The Streamlit Education pages also provide Load, Reload, Manifest, Exit, and confirmation-gated Reset controls. Re-seeding produces the same logical counts and stable record identifiers.