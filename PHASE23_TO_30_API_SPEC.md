# Phase 23–30 API Specification

OpenAPI is served by the existing FastAPI application. Phase 23–30 adds 37 paths.

## Internal Education platform

Base path: `/api/v1/education/platform`

| Area | Operations |
|---|---|
| Health | `GET /health/{institution_id}`, `GET /snapshot/{institution_id}`, `GET /release/{institution_id}` |
| Pilot | create pilot, transition lifecycle, save onboarding, dry-run import, commit import |
| Shiro | create task, approve/reject task, execute task |
| Lab | catalog, start attempt, record step, notebook, submit, assess |
| Mastery | create concept, record evidence, calculate recommendation |
| Research | create paper, transform/review/publish asset |
| Credentials | issue and public verify |
| Integration | configure integration, API key, webhook, plugin and MCP policy |

Internal routes use typed Pydantic request models and map service validation, permission, conflict and missing-record errors to safe HTTP responses.

## Public versioned API

Base path: `/api/v1`

- `GET /institutions/{institution_id}/courses` — `courses:read`
- `GET /institutions/{institution_id}/science-records` — `science:read`
- `GET /institutions/{institution_id}/credentials/{unique_code}` — `credentials:read`
- `GET /institutions/{institution_id}/agent-tasks` — `agent_tasks:read`

Use `Authorization: Bearer bia_...`. Keys are tenant-bound, scoped, expirable and locally rate-limited. Collection responses are paginated. Cross-tenant identifiers are rejected even with a valid key.

## Webhooks

Signatures use `v1=HMAC_SHA256(secret, timestamp + "." + nonce + "." + payload_json)`. Non-loopback endpoints must use HTTPS. Consumers must reject timestamps outside the configured replay window and deduplicate nonces/events.

## Compatibility

The new routers are additive and do not replace earlier `/api/v1/education` routes. OpenAPI import qualification found 704 total application paths, 37 belonging to the Phase 23–30 platform/public surface.

