# BioIntel Education Phase 15 — Production Runtime & Research Intelligence

Phase 15 extends the Phase 14 source without removing existing modules.

## Implemented

- Durable institution-scoped event log with audience filtering and cursor polling.
- SSE API transport with reconnect cursor and keepalive frames.
- Hybrid RAG ranking using BM25 and deterministic local semantic vectors.
- Permission filtering, page/section citations and document SHA-256 evidence.
- Governed Ollama, OpenAI-compatible and llama.cpp runtime profiles.
- Live runtime verification and explicit consent for external processing.
- Built-in PubMed, Europe PMC, Crossref, OpenAlex and arXiv metadata adapters.
- Cursor checkpoints, normalized records and institution-level deduplication.
- Academy media registry, ffprobe metadata support and server-governed playback telemetry.
- Modular Phase 15 package, typed APIs, desktop UI and worker handlers.

## Qualification boundary

The application remains SQLite-first for legacy repositories. PostgreSQL and object-storage adapters require a deployment cutover rehearsal. Public providers, model runtimes, ffmpeg, code signing, load/security/WCAG tests and institutional pilots require real external infrastructure or independent evidence.

## Test evidence

- 134 Education/Shiro/Universe regression tests passed.
- 30 Phase 15 standalone controls passed.
- Phase 15 runtime package coverage: 92.0% statements, 79.1% branches, 88.7% combined.
