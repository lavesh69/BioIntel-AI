# Phase 23–30 Database Schema

Migration ID: `education_phase23_to_30_enterprise_platform_v1`

The migration is idempotent and first applies the predecessor Phase 17–22 schema so the durable Education outbox is always available. SQLite foreign keys are enabled by the shared database layer.

## Inventory

The migration adds 57 `education_p30_*` tables and 20 named `idx_p30_*` indexes.

| Domain | Tables |
|---|---|
| Pilot and support | `pilots`, `pilot_transitions`, `onboarding`, `import_jobs`, `import_rows`, `pilot_records`, `health_samples`, `support_tickets`, `support_comments` |
| Agents | `agent_definitions`, `agent_tools`, `agent_tasks`, `agent_steps`, `agent_evidence`, `agent_approvals` |
| Virtual Lab | `lab_experiments`, `lab_versions`, `lab_attempts`, `lab_steps`, `lab_notebook_entries`, `lab_assessments` |
| Mastery | `concepts`, `concept_edges`, `concept_mappings`, `mastery_policies`, `mastery_events`, `mastery_records`, `adaptive_recommendations`, `review_schedule` |
| Research | `research_papers`, `paper_claims`, `research_assets`, `asset_reviews`, `research_projects` |
| Portfolio | `portfolios`, `portfolio_items`, `skills`, `skill_evidence`, `credentials`, `credential_events`, `portfolio_shares`, `career_plans` |
| Integration | `integrations`, `sync_runs`, `api_keys`, `api_usage`, `webhooks`, `webhook_deliveries`, `plugins`, `plugin_permissions`, `mcp_policies` |
| Operations | `jobs`, `job_attempts`, `objects`, `deployment_profiles`, `recovery_runs`, `audit_chain` |

Every listed name is prefixed with `education_p30_`. Tenant-owned records carry `institution_id`; ownership is checked in the service before access. Sensitive connector configuration and webhook signing secrets are stored encrypted by the Phase 30 service.

## Integrity controls

- Foreign keys and cascade behavior for child records.
- Unique keys for idempotency, credential codes, tool/agent keys, concept keys and tenant object keys.
- Transactional import commit.
- Hash-linked audit events with chain verification.
- API keys stored as SHA-256 hashes; raw keys are returned only at creation.
- Managed-file SHA-256, size and path metadata.

## Upgrade and rollback

The migration is additive; it does not drop predecessor tables. Before migration, use `BACKUP_EDUCATION_PHASE23_TO_30_WINDOWS.bat`. Rollback restores the verified backup and uses an explicit confirmation token.

