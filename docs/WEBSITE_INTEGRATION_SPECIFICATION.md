# BioIntel AI Website Integration Specification

## Boundary

The desktop product is offline-first. Website connectivity is optional and must never be required for core startup, local projects or bundled demonstrations. The website must not receive biomedical project data unless a user explicitly chooses a documented export and an approved deployment implements authentication, consent, retention and transport controls.

## Supported public integration

- Product, release-note, legal, support and download metadata may be published as static content.
- Download pages should publish the five exact filenames, byte sizes, SHA-256 checksums, release manifest and installation guide.
- Provider URLs must use HTTPS and pass the BioIntel network policy. Redirects must be revalidated.
- Update checks may compare signed/versioned metadata but must not silently replace the managed application.
- Online AI/scientific providers remain explicit opt-in integrations with separate credentials, rate limits, timeouts and provenance.

## Security requirements

No API key belongs in HTML, JavaScript, a ZIP archive or a log. Use short-lived server-side credentials and authenticated APIs for any future account service. Verify signatures/checksums before activation. Block private/reserved network destinations, credential-bearing URLs, unsafe redirects and archive traversal. Apply upload limits and content validation.

## Release API shape

The downloadable release manifest exposes product/version/step, shared archive root, five parts, byte sizes, SHA-256 values, total extracted size, required free disk and user instructions. Clients must reject missing, duplicate, mismatched or differently-versioned parts.

## Non-claims

Website publication does not establish clinical, regulatory, pharmaceutical, production or independent scientific validation. Capability and limitation labels from the shipped registries should be presented without alteration.
