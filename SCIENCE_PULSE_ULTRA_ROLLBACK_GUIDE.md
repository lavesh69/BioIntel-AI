# Science Pulse Ultra Rollback Guide

Stop BioIntel and its hidden worker, restore the pre-upgrade source and SQLite backup, then run the existing Windows launcher. The source changes are additive except for safer HTTP/feed behavior and the longer worker-start timeout. Restoring the database backup removes records collected after the backup.
