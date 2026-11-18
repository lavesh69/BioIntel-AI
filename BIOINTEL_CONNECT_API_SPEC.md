# BioIntel Connect API specification

Base prefix: `/api/v1/connect`. The assembled router contains 113 operations across 92 unique paths. Requests use Pydantic models, local authenticated identity, structured 4xx mapping and object-level service authorization.

## Route families

- Base: profiles, privacy, follows, connection requests, blocks/mutes, posts/feed, uploads/media, comments, reactions, reposts, bookmarks, moderation reports and notifications.
- Messaging: `/conversations`, `/messages`, `/messages/search`, `/websocket`, `/websocket/events`.
- Community/collaboration: `/communities`, `/collaborations`, `/projects`, `/publications`, `/datasets`, `/workflows`, `/events`, `/opportunities`.
- Discovery: `/search`, `/recommendations`, `/recommendations/feedback`, `/shiro`.
- Addendum: `/stories`, `/story-highlights`, `/short-videos`, `/live-streams`, `/calls`, `/verifications`, `/onboarding`, `/accessibility`, `/drafts`, `/scheduled-posts`, `/notification-delivery`, `/admin`, `/health`.

Feeds and event history use bounded limits and sequence/cursor loading. Media completion validates ownership, type, checksum, scanning and sensitive-content acknowledgement. The WebSocket transmits durable events and accepts acknowledgement/typing frames; offline clients replay by sequence. Administrative and backup routes require administrator/local-operator roles, with moderator scope where appropriate.
