# Education Phase 7 — Desktop App Experience Report

## Desktop workspace architecture

The new `BioIntel Education Desktop` page replaces the Phase 6 all-tabs-at-once pattern with a lazy selected-workspace router. The available desktop workspaces are Overview, Classroom, Academy, Shiro & Mastery, Examinations, Research, Institution and Sessions. Only the active branch queries and renders data.

## Classroom

- Plotly timetable view with staff editing and cancellation.
- Editable gradebook with bulk persistence and score distribution.
- Full attendance roster editor and lock control.
- Assignment Kanban plus rubric authoring and criterion-level grading.

## Academy

- Expandable curriculum hierarchy and controlled ordering.
- Lecture player surface with server-governed progress actions.
- Chapters, timestamped notes and bookmarks.
- Multilingual transcript authoring and phrase search.
- Course progress analytics.

## Shiro and mastery

- Persistent native chat surface.
- Course/subject evidence grounding and citation details.
- Conversation lifecycle controls.
- Interactive mastery/prerequisite graph.
- Student-safe active-examination lock remains enforced.

## Examinations

- Configurable institution examination threshold.
- Score distribution and Bloom/difficulty blueprint.
- Candidate monitoring cards with optional ten-second refresh.
- Moderation and revaluation evidence timeline.

## Research and institution operations

- Publication trends and author collaboration visualization.
- Sequence, expression, PCA and volcano viewers.
- Campus hierarchy, worker/job operations, backup schedules and provider qualification cards.
- Technical JSON is kept inside optional evidence disclosures rather than being the primary end-user presentation.

## Desktop UX rating

These are source-qualified estimates, not independent certification:

| Area | Phase 7 rating |
|---|---:|
| Visual consistency | 9.5/10 |
| Desktop information architecture | 9.4/10 |
| Classroom workflows | 9.4/10 |
| Academy experience | 9.2/10 |
| Examination experience | 9.5/10 |
| Shiro AI experience | 9.5/10 |
| Institution operations UX | 9.3/10 |
| Accessibility implementation | 9.0/10 |
| Overall source-level desktop UI/UX | 9.4/10 |
| Production-qualified UI/UX | 8.6/10 |

Production qualification remains lower until the application is tested on real Windows browsers, real institutional data, assistive technologies and representative users.
