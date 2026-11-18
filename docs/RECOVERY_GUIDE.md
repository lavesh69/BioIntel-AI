# Step 9 Recovery Guide

## Create a backup in the UI

Open **Workspace Backup & Restore**, choose whether to include cache or demo
models, then download the ZIP.

## Create a backup on Windows

```text
BACKUP_WORKSPACE_WINDOWS.bat
```

## Create a backup from CLI

```powershell
python -m biointel workspace-backup --output backups\workspace.zip
```

## Restore from CLI

```powershell
python -m biointel workspace-restore --backup backups\workspace.zip
```

Add `--overwrite` only when existing files should be replaced.

## Run diagnostics

```powershell
python -m biointel diagnose
```

Or open **System Diagnostics & Offline Cache**.

## Repair dependencies

```text
REPAIR_BIOINTEL_WINDOWS.bat
```

The repair script recreates or repairs the Python environment and reinstalls
requirements. It does not intentionally delete models, reports or backups.

## Cache management

```powershell
python -m biointel cache-status
python -m biointel cache-clear
python -m biointel cache-clear --all
```
