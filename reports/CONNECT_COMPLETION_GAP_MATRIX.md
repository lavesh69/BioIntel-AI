# BioIntel Connect Completion gap matrix

This status is intentionally conservative and based on source inspection plus the baseline Connect test run.

| Module | Status | Evidence |
|---|---|---|
| Authentication and identity | partially_working | Connect identity/profile/session tables exist; complete registration/login/password reset/Argon2 workflow is not implemented in Connect. |
| Authorization and tenant isolation | partially_working | Core services enforce ownership/membership in several workflows; advanced phase services use inconsistent/in-memory checks. |
| Profiles and network | fully_working_in_local_scope | Persistent profiles, privacy, follow, connection, block and negative tests exist. |
| Research feed | fully_working_in_local_scope | Persistent posts, comments, reactions, bookmarks, reposts, moderation and tests exist. |
| Messaging | partially_working | Persistent conversations/messages/receipts/realtime replay exist; complete forward/edit/delete/retention/project-event chat coverage is incomplete. |
| Calls and meetings | partially_working | Real browser WebRTC client and authenticated signaling implemented; independent-browser/TURN/SFU qualification outstanding. |
| Projects, tasks and milestones | partially_working | Project/resource services exist; task/milestone/calculated-progress implementation is incomplete. |
| Documents, ELN and data rooms | not_acceptance_ready | Phase B uses fake export URLs, in-memory notebook/data-room state and caller-provided signature strings. |
| Grants, consortia and DAC | not_acceptance_ready | Service methods and tests exist but primary state is process-memory only. |
| Peer review, preprints and trust | not_acceptance_ready | Service methods and tests exist but primary state is process-memory only. |
| Knowledge graph and expert matching | not_acceptance_ready | Service methods exist but graph and consultation state are process-memory only; matching coverage is limited. |
| Marketplace, equipment, events and mentorship | not_acceptance_ready | Service methods exist but state is process-memory only and advanced UI pages are placeholders. |
| Developer API and webhooks | unsafe_false_success | Webhook trigger returns delivered without HTTP; secrets stored plaintext in memory. |
| Analytics and trends | unsafe_fake_metrics | Hardcoded analytics and trend rows violate the specification. |
| Preservation | unsafe_false_success | Returns archived_permanently and random checksum without creating an archive. |
| Advanced UI pages | placeholder | Pages 326-338 contain only title plus Active & Qualified info. |
| Windows installation | partially_working | Multiple scripts exist, but conflicting installer versions and stale packaging references require canonicalization. |
| Automated testing | partially_working | 45/46 Connect tests pass baseline; many advanced tests assert returned dictionaries rather than persistence/artifacts/delivery. |
| Final packaging | not_started_for_completion_spec | Prior single preview ZIP exists; required strict allowlist four-part CONNECT-COMPLETE release not built. |

## Baseline test evidence

- Command: `py -3.11 -m unittest discover -s tests/connect -p test*.py -v`
- Result: 45 passed, 1 failed.
- Failure: stale Calls test expected recording-consent behavior inconsistent with the corrected unavailable-recording state.
- Coverage: not measured; the environment does not currently contain the `coverage` package.
