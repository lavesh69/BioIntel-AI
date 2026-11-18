# Education Database Schema

## Version

Migration: `education_phase17_to_22_unified_os_v1`

The migration is additive and repeatable (`CREATE TABLE/INDEX IF NOT EXISTS` plus
`INSERT OR IGNORE`). It never drops or recreates a user database during startup.

## New Phase 17–22 tables

| Area | Tables |
|---|---|
| Migration and resources | `education_os_migrations`, `education_resource_registry`, `education_role_bindings` |
| Cross-module workflow | `education_workflow_instances`, `education_outbox`, `education_idempotency_keys` |
| Course-aware Shiro | `education_shiro_scopes`, `education_shiro_scope_acl`, `education_shiro_documents`, `education_shiro_generated_artifacts` |
| Connect bridge | `education_connect_identities`, `education_channel_links` |
| Explainable intelligence | `education_intervention_recommendations` |
| Studio | `education_studio_projects`, `education_studio_versions`, `education_studio_assets`, `education_studio_citations`, `education_studio_reviews`, `education_studio_publications` |
| Operations | `education_feature_flags_v22`, `education_health_checks_v22`, `education_release_checks_v22` |
| Science Pulse | `education_pulse_canonical_records`, `education_pulse_canonical_links` |

## Integrity properties

- Tenant foreign keys point to `institutions(id)`.
- Resource uniqueness: institution + type + external ID.
- Role uniqueness: institution + user + role + resource scope.
- Outbox uniqueness: institution + dedupe key.
- Idempotency uniqueness: institution + actor + operation + idempotency key.
- Shiro scope uniqueness: institution + course + classroom.
- Studio version uniqueness: project + version number.
- Intervention uniqueness: institution + student + subject + concept + reason code.
- Pulse provider-link uniqueness: institution + provider record.

Indexes cover tenant/resource lookups, role authorization, workflow stage, outbox
delivery, Shiro scope lookup, intervention review, Studio lists and health history.

## Existing schema

A fresh complete Education migration produced 205 application tables, 60 explicit indexes
and 14 recorded Education migration IDs. Existing Phase 2–16 academic, Academy,
Examination, Universe, job, notification, RAG, backup and analytics tables are retained.

## Migration behavior

Startup applies migrations within normal SQLite transactions. Foreign keys are enabled.
User content is not seeded automatically. Demo seed operations remain explicit and use
separate demo storage.

