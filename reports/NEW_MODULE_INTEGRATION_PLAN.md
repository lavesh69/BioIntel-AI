# New Module Integration Plan

## Architecture
Create `biointel.education` as one bounded context with:
- `database.py`: versioned SQLite migration and foreign-key/index validation.
- `auth.py`: centralized institution/role/resource authorization.
- `classroom.py`, `pulse.py`, `academy.py`: durable domain services.
- `api.py`: authenticated FastAPI routes; no trust in hidden UI.
- `ui.py`: role-aware Streamlit workspaces and truthful dependency states.
- `search.py`: permission-aware cross-ecosystem search.

## Reused components
Connect identity IDs, Calls capability/linking, notification interface, UserData path conventions, Windows installer/runtime, media hashing, Shiro no-autonomous-publish rule.

## New pages
- BioIntel Classroom
- BioIntel Science Pulse
- BioIntel Academy & Lecture Studio

## Security boundaries
Every private row carries institution ownership. Authorization checks compare actor membership, scoped role and resource institution before reads or writes. Guardian access is child-link limited. Official records require workflow transitions and audit events. Public publication/news results expose only lawful metadata, excerpt and original-source links.

## External adapters
Publication/news HTTP and FFmpeg adapters expose health plus `CONFIGURATION REQUIRED`/`EXTERNAL SERVICE UNAVAILABLE`; they never emit fabricated records or processed files.

## Delivery sequence
Migration -> authorization -> services -> API -> UI -> tests -> Windows gate -> four-part packaging.
