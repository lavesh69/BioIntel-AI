# Phase 32 Conflict Resolution Matrix

| Entity | Strategy | Behavior |
|---|---|---|
| Messages, audit logs | Append-only merge | New immutable entries are retained. |
| Final submissions | Immutable record rejection | Conflicting mutation is rejected and recorded. |
| Grades, credentials | Server-authoritative | Authorized server version is accepted with history. |
| Notes, files | Manual resolution | Both checksums are retained as an open conflict. |
| Preferences | Field-level merge | Dictionary fields merge; resolution is recorded. |
| Notifications | Latest valid version | Monotonic version wins; clock time alone is insufficient. |
| Other supported entities | Latest valid version | Higher valid entity version wins. |
| Database migrations | Not sync-eligible | Migrations are never synchronized as user data. |

A single universal last-write-wins rule is not used. Every detected conflict records strategy, both checksums, state, reason, time, and resolver.
