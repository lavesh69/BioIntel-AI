# Science Pulse Ultra Database Schema

Canonical migration: `science_pulse_news_first_v2`.

The preserved schema contains sources, normalized items, aliases, sync runs, worker leases, alerts, deliveries, preferences, digests, integrations and audit events. WAL-backed SQLite remains canonical for this local-first Windows release.

No Ultra graph, claim-evidence, source-pack, story-timeline, watchlist or webhook tables were added; those capabilities remain NOT_IMPLEMENTED.
