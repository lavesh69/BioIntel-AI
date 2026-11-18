# Phase 31–35 Rollback Guide

1. Double-click `Stop BioIntel AI.vbs` and confirm the endpoint is closed.
2. Back up the current `UserData` directory before changing releases.
3. Open `%LOCALAPPDATA%\BioIntelAI`.
4. Confirm that `rollback` contains the timestamped prior `current` release.
5. Run `Rollback-BioIntel.ps1` from the installed release, or manually rename the current
   application directory and move the latest rollback directory to `current`.
6. Start the restored release and verify health and representative data.

Application rollback does not automatically reverse the Phase 31–35 database migration.
The migration is additive, so older application code should ignore the new tables. If
an institution requires complete database rollback, restore the pre-upgrade `UserData`
backup instead of manually dropping tables.
