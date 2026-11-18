# Phase 13B known limitations

- No browser qualification was run in two independent contexts, so media exchange is implemented but not proven in this environment.
- Full-mesh P2P only; default limit four. No SFU adapter/service connection and no scalable-conference claim.
- TURN configuration is supported but no TURN server was available, so relay candidates and relay-only connectivity are unproven.
- Signaling currently uses bounded polling rather than a dedicated call WebSocket. Events expire after one hour; resume/replay is limited to the caller-provided timestamp cursor.
- Waiting-room admission, moderation, persistent meeting chat/files, polls, breakout rooms, scheduled recurrence, calendar/email adapters, connection-stat UI, and automated ICE restart remain incomplete.
- Recording is deliberately unavailable. There is no recorder worker or valid media artifact, and no active/complete/available recording claim.
- Transcription/captions are unavailable; no provider/model is integrated.
- HTTPS certificate provisioning is deployment-specific. Non-loopback browser media capture requires a secure context.
- Static TURN credentials are accepted from server environment for private deployment; short-lived REST credentials are not yet implemented.
- No compliance certification is claimed.
