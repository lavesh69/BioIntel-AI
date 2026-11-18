# Science Pulse Ultra Migration Guide

No destructive database migration is required. Existing `science_pulse_news_first_v2` databases are opened in place. Back up `UserData/databases/biointel_science_pulse.sqlite` before upgrade. On first worker start, new official sources are upserted without resetting user enable/approval choices for existing rows.
