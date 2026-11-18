# Education Science Academy Database Migration Plan

Migration ID: `education_science_academy_v1`.

Create one durable SQLite database under managed UserData. Tables are grouped as:
- identity scope: institutions, education_memberships, guardian_links;
- Classroom: academic_units, subjects, enrollments, teacher_assignments, timetable_entries, attendance_sessions, attendance_records, attendance_corrections, materials, assignments, submissions, grades, examinations, results, circulars, circular_acknowledgements, academic_events;
- Science Pulse: pulse_sources, publications, publication_identifiers, news_items, follows, saved_research, alerts, alert_deliveries, ai_summaries, research_trends, source_sync_jobs;
- Academy: educator_profiles, courses, course_sections, lectures, lecture_files, video_renditions, academy_enrollments, watch_progress, watch_events, quizzes, quiz_attempts, certificates, content_reports, content_rights;
- shared: education_audit_events.

All tables use primary keys, UTC timestamps and state. Protected records include institution ID. Add indexes for tenant/resource, due dates, publication DOI/PMID, source timestamps, course/lecture and user progress. Enable foreign keys and WAL. Migration is idempotent and verified from empty DB and reopen/restart. No destructive legacy-table changes.
