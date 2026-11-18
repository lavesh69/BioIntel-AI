# Science Pulse Migration Guide

1. Back up `UserData/databases` and the application source.
2. Start BioIntel normally. `science_pulse_mega_v1` creates only additive `sp_*` tables.
3. Existing `pulse_articles` rows are copied into canonical items with `LOCAL` provenance; the legacy table is retained.
4. Review managed source approval, run a connection test, and inspect cached/live labels.
5. Configure per-user delivery and optional Education/Connect destinations.
6. Do not delete legacy Education tables until owner acceptance and backup retention expire.
