# Science Pulse Pre-Implementation Audit

## Existing capability
BioIntel already stores some publication/evidence metadata and offers connected-provider abstractions, but it has no durable user-facing Science Pulse source-sync, correction/retraction, news, follow, alert, saved-library, grounded-summary or trend service.

## Reuse
- Connected provider HTTP conventions and evidence provenance.
- Connect notifications and search patterns.
- Existing DOI/PMID fields and scientific boundary labels.

## Required additions
Durable sources, publication/news records, identifier deduplication, preprint/correction/retraction labels, lawful excerpt/metadata storage, saved items, follows, deduplicated alerts/deliveries, real-event trends and AI-summary source grounding. External ingestion remains configuration-required until a real source responds.
