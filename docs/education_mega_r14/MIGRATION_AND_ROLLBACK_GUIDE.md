# Migration and Rollback Guide

Release: BioIntel AI 15.6.0 Education Mega R14  
Generated: 2026-08-01T15:23:09.992266Z

Stop services and back up UserData. Install R14, run additive migrations, validate, and retain backup. Roll back both binaries and matching UserData. Never delete a database to conceal migration errors.

## Safety

Use authorized sources, protect UserData backups, and treat external providers as explicit administrator configuration.
