# Education OS Architecture

## Design

The Phase 17–22 layer is an additive facade over the canonical Education database. It
does not replace the earlier Phase 2–16 services.

```text
Streamlit pages / FastAPI routes / Windows worker
                    |
             EducationOS facade
       _____________|________________
      |             |                |
Education       Shiro course      Connect bridge
Platform        scopes + ACL      + durable outbox
      |             |                |
      +-------------+----------------+
                    |
       SQLite + tenant media storage
```

## Boundaries

- `EducationPlatform`: canonical academic records, files, attendance, assignments,
  grading, examinations, Academy and institutional operations.
- `EducationOS`: canonical resource registry, role bindings, cross-module workflow,
  idempotency, outbox, interventions, Pulse canonicalization and Studio lifecycle.
- `ShiroOrchestrator`: isolated ingestion/retrieval/generation projects. Education stores
  the scope-to-course mapping and ACL.
- `ConnectServices`: persistent users, notifications, messaging, channels, moderation,
  media and calling state. Education stores identity/channel links.
- `EducationPhase16Service`: prior background jobs, notifications, RAG evaluation,
  scientific workbenches and media processing.

## Authorization

Every Education OS service call starts from an actor and institution. Resource operations
resolve `institution_id`, `resource_type` and external resource ID before authorizing.
Cross-institution registry matches fail closed. Canonical roles are:

`student`, `teacher`, `parent_guardian`, `instructor`, `examiner`, `reviewer`,
`department_administrator`, `institution_administrator`, `platform_administrator`, `guest`.

Earlier role names remain accepted through explicit aliases; they are not treated as
implicit admin roles.

## Consistency and events

- SQLite connections enable foreign keys and transactions.
- Unique keys protect resource bindings, outbox deduplication and idempotency replay.
- Studio versions use an expected-version compare-and-swap update.
- The outbox records a delivery attempt before work leaves Education services.
- Failed delivery records an error and exponential next-attempt time.
- Streamlit session state is limited to UI interaction state; authoritative workflow data
  remains in SQLite.

## Storage

- Default data: `%LOCALAPPDATA%\BioIntelAI\UserData`.
- Education DB: `education\education.sqlite3`.
- Tenant files: `education\media\<institution_id>\...`.
- Connect DB/media and Shiro data remain in their existing local-first stores.
- Optional PostgreSQL deployment adapters are preserved, but this Phase 17–22 migration
  is locally qualified against SQLite only.

