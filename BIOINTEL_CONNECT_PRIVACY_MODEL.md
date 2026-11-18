# BioIntel Connect privacy model

Privacy is deny-by-default for unknown scopes and enforced in services/queries.

Profiles support public, authenticated, connections and only-me visibility, with separate institution/location/activity/message/mention/download/search controls. Posts support public, followers, connections, institution members, community members, project members, private link, only-me and draft states.

Blocking is symmetric for profile/content/relationship/messaging access and removes active follows, connections and pending requests. Muting removes feed visibility without notifying the target. Community/project posts require active membership. Dataset access decisions are separate from public metadata.

Stories expire and recheck visibility for every view. Short-video feeds enforce blocks and visibility. Live/private stream access and call invitations are object-authorized. Recording requires explicit consent. Notification previews are generic unless a user explicitly enables private previews. Accessibility preferences contain no sensitive media or raw verification evidence.

Verification stores hashes and redacted summaries, not raw professional email/evidence strings. Admin/audit/backup data is administrator-only. Legal holds and soft deletion preserve required evidence without making content public.
