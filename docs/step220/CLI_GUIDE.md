# CLI Guide

Run `biointel research-platform --help` for the current command catalog. Commands use the same storage/service layer as UI and API. Select custom local paths with the database/artifact options; otherwise the configured UserData location is used.

Machine-readable commands emit JSON. Non-zero exits represent validation, dependency, storage, or lifecycle failures and should not be ignored in automation.
