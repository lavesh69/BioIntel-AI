# BioIntel Connect architecture

## Runtime layers

1. Streamlit 1.58 pages provide thin, native UI surfaces.
2. `biointel.connect.ui` and `complete_ui` coordinate session identity and service calls.
3. `ConnectServices` owns the Phase 1–2 services and a `CompleteConnectSuite` of 17 expanded domains.
4. FastAPI exposes versioned typed REST routes and a durable WebSocket/event-replay channel.
5. Repository/service authorization protects SQLite-backed models; media bytes live under a configurable storage root.
6. Operations uses consistent SQLite snapshots, encrypted `.biobak` files and non-production restore drills.

## Service suite

`messaging`, `communities`, `collaboration`, `discovery`, `shiro`, `stories`, `short_videos`, `live_streams`, `calls`, `verification`, `onboarding`, `delivery`, `drafts`, `lifecycle`, `accessibility`, `admin`, and `operations` share one migrated `ConnectDatabase` and repository.

## Realtime design

Each conversation increments a durable sequence. Per-user events use dedupe keys, sequence ordering and acknowledgement timestamps. WebSocket clients poll this event log, acknowledge completed delivery, and can reconnect with `after_sequence`; `/websocket/events` provides an HTTP fallback. This local deployment does not pretend to be a distributed broker.

## Configuration

- `BIOINTEL_CONNECT_DATABASE`: Connect SQLite path.
- `BIOINTEL_CONNECT_STORAGE`: media/runtime storage root.
- `BIOINTEL_CONNECT_BACKUP_KEY`: optional Fernet key; otherwise a local key is created beside backups.

All original BioIntel modules remain intact. The working release excludes agent-created virtual environments and runtime/test databases.
