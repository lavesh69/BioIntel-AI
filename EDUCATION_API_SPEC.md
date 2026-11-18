# Education OS API Specification

Base prefix: `/api/v1/education/os`

| Method | Path | Purpose |
|---|---|---|
| GET | `/health/{institution_id}` | Persistent component health snapshot |
| GET | `/home/{institution_id}` | Role-aware Education Home snapshot |
| POST | `/workflows` | Create program/course/classroom workflow |
| POST | `/workflows/{workflow_id}/enrolments` | Enrol a student |
| POST | `/workflows/{workflow_id}/assignments` | Publish an assignment |
| POST | `/assignments/{assignment_id}/submissions` | Idempotent student submission |
| POST | `/submissions/{submission_id}/grade` | Grade and refresh interventions |
| POST | `/shiro/scopes/{scope_id}/ask` | Course-scoped grounded Shiro answer |
| POST | `/interventions/refresh` | Refresh explainable recommendations |
| POST | `/interventions/{intervention_id}/review` | Accept, correct or dismiss |
| POST | `/studio/projects` | Create a Studio project |
| POST | `/studio/projects/{project_id}/versions` | Optimistic version save |
| POST | `/studio/projects/{project_id}/submit-review` | Submit for human review |
| POST | `/studio/projects/{project_id}/review` | Review decision |
| POST | `/studio/projects/{project_id}/publish` | Queue connected publication |
| POST | `/outbox/{institution_id}/dispatch` | Process bounded durable events |
| POST | `/release/{institution_id}/qualify` | Persist local qualification matrix |

## Error contract

- `400`: input or Education domain validation.
- `403`: authentication, role, resource or tenant denial.
- `404`: missing workflow/resource.
- `409`: conflict, stale version, duplicate idempotency key with a different request,
  or invalid lifecycle state.
- `422`: Pydantic request-schema validation.

Errors expose a user-safe message and do not return SQL, credentials or filesystem
internals.

## Authentication note

The existing BioIntel API/session layer remains authoritative. `actor` fields are service
identity inputs after that boundary; production deployments must not accept arbitrary
actor IDs without the existing authenticated request middleware.

## OpenAPI

All 17 routes import into the existing FastAPI application and are present in generated
OpenAPI. API contract tests verify creation, forbidden access and schema exposure.

