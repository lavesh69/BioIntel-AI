# BioIntel AI API Guide — Step 9 No Login

## Local start

```powershell
.\.venv\Scripts\activate
uvicorn biointel.api.main:app --app-dir src --host 127.0.0.1 --port 8000
```

Documentation:

```text
http://127.0.0.1:8000/docs
```

No login, API key or authentication header is required.

## Local safeguards

- Allowed hosts: `127.0.0.1`, `localhost`
- Maximum request body: 25 MB
- Responses use `Cache-Control: no-store`
- Responses use `X-Content-Type-Options: nosniff`
- No public CORS policy is enabled

## Endpoints

- `GET /health`
- `GET /model/status`
- `GET /system/diagnostics`
- `POST /sequence/analyze`
- `POST /sequence/align`
- `POST /dti/predict`
- `POST /dti/batch-predict`
- `POST /model/external-validate`

## Health response

```json
{
  "status": "ok",
  "access_mode": "no_login_local",
  "authentication_required": false,
  "host_policy": "localhost_only",
  "request_limit_bytes": 26214400
}
```

## Warning

Because the API has no authentication, keep it bound to `127.0.0.1`. Do not
publish it directly to the internet.

## Step 12 experience endpoints

- `GET /ui/catalog` — searchable tool metadata
- `GET /workflow/report-data` — local workspace report data

These endpoints remain no-login and localhost-only.

## Step 13 professional operations endpoints

- `GET /portfolio/projects` — local project portfolio metadata
- `GET /operations/alerts` — visible automatic operational alerts
- `GET /operations/timeline` — project, experiment and audit timeline
- `GET /executive/summary` — maturity and portfolio risk summary

All remain no-login and localhost-only.

## Step 14 governance endpoints

- `GET /governance/summary` — governance portfolio totals
- `GET /governance/projects/{project_id}` — milestones, decisions and gates
- `GET /projects/{project_id}/readiness` — transparent release-readiness score
- `GET /projects/{project_id}/lineage` — project evidence graph data
- `GET /projects/{project_id}/evidence-manifest` — reproducibility manifest
- `GET /audit/integrity` — hash-chain verification

All endpoints remain no-login and localhost-only.

## Step 15 data-library endpoints

- `GET /data/packs` — bundled data-pack manifest and library metadata
- `GET /models/benchmark` — pretrained model ranking and best-model summary

These remain no-login and localhost-only.

## Step 17 double-data endpoint

- `GET /models/double-benchmark` — six pack-v4 models trained on 32,000 rows


## Step 18 coverage endpoint

- `GET /data/coverage` — complete coverage manifest, quantities and checksum status

## Step 19 5X endpoint

- `GET /models/5x-benchmark` — six pack-v5 models, 160,000-row metadata and overall champions

## Step 21 database intelligence endpoints

- `GET /databases/status`
- `GET /intelligence/search?q=model`
- `GET /knowledge/search?q=dataset`
- `GET /analytics/overview`
- `GET /assets/search?q=model`

## Step 22 connected research endpoints

- `GET /internet/status` — outbound policy and download registry
- `GET /internet/check` — RCSB, PubChem, UniProt and ChEMBL connectivity
- `GET /internet/pdb/{pdb_id}` — RCSB entry metadata
- `POST /internet/pdb/{pdb_id}/download` — save a structure with provenance
- `GET /internet/pubchem/name/{compound_name}` — PubChem name resolver
- `POST /internet/url-download` — controlled public HTTPS importer
- `GET /chemistry/common-compounds` — search 5,000 bundled names
