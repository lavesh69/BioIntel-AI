# BioIntel AI Backup and Rollback

## Automatic protection

Before activation, the Step206 installer stops the verified active runtime, backs up known SQLite stores and migrates them transactionally. Environment rebuilds preserve the previous `.venv` and restore it if post-install verification fails. Managed source replacement uses a staging directory and restores the previous release directory if activation fails.

Backups are recorded below `%LOCALAPPDATA%\BioIntelAI\UserData\backups`. Live Workspace uses verified SQLite snapshots with configured retention. The application directory and UserData are separate so repairs and uninstalls can preserve user work.

## Manual backup

1. Run `STOP_BIOINTEL_WINDOWS.bat` and confirm the runtime is stopped.
2. Copy `%LOCALAPPDATA%\BioIntelAI\UserData` to a protected destination.
3. Retain the backup timestamp, release version, checksum manifest and access-control context.
4. For external reference assets/tools, preserve their manifests, versions, licences and checksums separately.

Do not copy live SQLite databases while writers are active unless using the provided SQLite snapshot functions.

## Repair rollback

If dependency rebuilding or post-install tests fail, the installer restores the prior verified environment automatically and does not activate the failing result. Review `step206-install.json` and the support bundle before retrying.

## Data restore

Stop BioIntel, make a safety copy of the current UserData, restore only from a trusted backup, then run `DIAGNOSE_WINDOWS.bat`. Database schema downgrades are not automatic; use the documented migration/restore path and retain the pre-restore copy.

## Uninstall recovery

The safe uninstaller preserves UserData. Reinstall the same verified four-part release to restore application files and reconnect to the preserved local state. Application binaries removed by uninstall are recovered by reinstalling, not by treating UserData as an application backup.
