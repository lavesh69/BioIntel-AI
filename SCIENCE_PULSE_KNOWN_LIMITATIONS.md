# Science Pulse Known Limitations

- Public internet endpoints were not called during deterministic release qualification; every built-in source requires target-machine external validation.
- Email, desktop, and institution-specific notification providers require administrator configuration.
- Education Home delivery requires a real institution ID and active membership.
- Metadata/abstract access does not imply access to paid full text; Shiro contexts explicitly preserve this boundary.
- Crossref Event Data availability and schema behavior can change externally.
- SQLite is the qualified local-first database; PostgreSQL deployment is not implemented in this release.
- A closed desktop application or powered-off computer does not fetch content.
- Long-duration hourly/daily behavior was clock/state tested, not observed for a literal week.
