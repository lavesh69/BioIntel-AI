# BioIntel Connect database schema

Two forward migrations are applied transactionally:

- `001_connect_phase1_phase2`: users, profiles/privacy, follows/connections, media/uploads, posts/revisions/attachments, comments/revisions, reactions, bookmarks/reposts, notifications, reports/cases/audit.
- `002_connect_complete_target`: 68 expanded domain tables and supporting indexes.

A clean migration produces 94 `connect_*` tables including the migration ledger. Major groups are:

- Identity: sessions, institutions, laboratories, organizations, verification, badges, onboarding and accessibility.
- Messaging: conversations/members/requests, messages/revisions/attachments/receipts/reactions/saves and realtime events.
- Communities and collaboration: communities/members/channels/resources, collaboration applications, projects/members, publications, datasets/access, workflows/versions, events/registrations and opportunities.
- Media/social: stories/views/reactions/highlights, short videos/comments/saves/shares, live streams/participants/comments/reactions, calls/participants/signals.
- Governance: drafts/revisions/scheduled posts, notification preferences/deliveries/digests, appeals/actions/holds/exports/deletion.
- Operations: backup records, service health, rate-limit/security events and cleanup events.

Tables use UUID-like text primary keys, UTC timestamps, soft deletion, state/visibility, audit JSON and optimistic `version` fields. Foreign keys and uniqueness constraints protect membership, receipts, idempotency and dedupe rules. Forward migration and complete rollback are covered by automated tests; rollback preserves only `connect_schema_migrations`.
