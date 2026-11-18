# BioIntel Science Pulse Source Guide

Administrators can register an HTTPS Crossref-compatible publication endpoint (`publication_api`) or RSS/Atom news feed (`rss`). Sources are disabled by default. Enabling a source authorizes a real network request; sync jobs record `completed`, `configuration_required`, or `external_service_unavailable` and never invent records. Responses are capped at 5 MiB, publication pages require DOI/PMID plus an original link, and article text is limited to short excerpts. API keys, publisher entitlements and provider terms remain the operator's responsibility.
