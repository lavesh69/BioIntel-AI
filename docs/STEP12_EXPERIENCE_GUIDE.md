# Step 12 Experience Guide

## Command Center

Use Command Center to:

1. Search by tool name, description or keyword.
2. Filter by category.
3. Star frequently used tools.
4. Resume recently opened modules.
5. Review workspace readiness.

## Persistent preferences

Appearance settings are saved locally in:

```text
reports/ui_profiles/<profile>/preferences.json
```

This file contains only theme, font, accessibility preferences and page keys. It does not store
sequences, SMILES, passwords or account data.

## Report Studio

Generate a report from the UI or CLI.

UI:

```text
Research Report Studio
```

CLI:

```powershell
python -m biointel workspace-report --output reports\generated\workspace.html
```

Windows:

```text
EXPORT_WORKSPACE_REPORT_WINDOWS.bat
```

## Local privacy

Favourites, recent tools and reports stay inside the extracted project folder.
They are included in workspace backups and visible in Local Data Manager.
