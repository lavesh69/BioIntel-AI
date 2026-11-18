# Science Pulse Ultra Adapter SDK

The current contract is `ProviderAdapter.fetch(client, query, limit, checkpoint) -> FetchResult(records, checkpoint)`. `ProviderRegistry` supplies pacing, three bounded attempts and source-specific checkpoints. `SafeHttpClient` is injectable for deterministic tests.

Status: PARTIALLY_IMPLEMENTED. Version detection, schema-change callbacks, formal plugin discovery and per-provider rate-limit policy objects remain to be built.
