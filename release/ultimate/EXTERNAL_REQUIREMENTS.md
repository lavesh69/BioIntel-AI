# External Requirements

## Core Windows runtime

- Supported 64-bit Windows environment.
- Exact CPython 3.11.9 x64 for installation; the managed environment is created from the locked release route.
- Sufficient disk space reported by the release manifest/installer, with additional space for UserData and selected references.

## Optional scientific capability

External engines, databases and model weights are enumerated in `release/ultimate_registry`. Each asset requires an exact version, checksum, licence review, compatibility check and qualification evidence before activation. Interfaces remain available when optional dependencies are absent, but external actions remain disabled or use an explicitly bounded built-in research fallback.

## Optional collaboration/enterprise capability

Team hosting requires configured accounts and a trusted private network. PostgreSQL, Redis, object storage, OIDC and observability endpoints are optional production integrations, not core startup dependencies.

## Distribution

Public Windows distribution may additionally require publisher code-signing certificates, independent malware scanning, SmartScreen reputation, legal/support URLs and physical clean-machine validation.
