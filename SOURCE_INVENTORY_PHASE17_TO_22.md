# BioIntel Phase 17–22 Source Inventory

Generated: 2026-07-30T06:23:56.512622+00:00

## Canonical assembly

- Common root: `BioIntel-Step220`
- Archives: 4
- Canonical files: 13,497
- Archive corruption errors: 0
- Current non-transient files: 13,530
- Unchanged files: 13,454
- Changed files: 43
- New implementation files: 33
- Missing canonical files: 0

## Repository surface

- Streamlit pages: 354
- `src/biointel` files: 1,124
- API-named source files: 12
- Database/schema/migration files: 274
- Python tests: 311
- Windows batch scripts: 332
- Duplicate logical page-name candidates: 3

## Static review findings

| Finding | Occurrences | Files sampled |
|---|---:|---:|
| todo fixme | 8 | 5 |
| not implemented | 2 | 1 |
| pass statements | 267 | 100 |
| fake success language | 1 | 1 |
| streamlit buttons | 859 | 100 |
| streamlit session state | 1,275 | 100 |


These findings are candidates for review. `st.session_state` is valid for transient UI state;
the Phase 17–22 core workflow itself persists to SQLite. A button match is not classified as
broken unless its service action is absent.

## Canonical page decisions

- Pages 339–345 remain the canonical Education routes.
- Legacy Education routes 150–154 are compatibility wrappers into the canonical UI.
- Connect route 140 delegates to the persistent Connect hub.
- Shiro route 273 remains the canonical Shiro AI route.
- Studio route 70 exposes the persistent Phase 17–22 project/review/export service.

Full changed/new/missing paths and sampled static findings are in
`SOURCE_INVENTORY_PHASE17_TO_22.json`.
