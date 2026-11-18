# BioIntel AI Helm deployment

The chart provides separate API, Streamlit and worker Deployments; non-root/read-only security contexts; startup/readiness/liveness probes; HPAs; PodDisruptionBudgets; default-deny NetworkPolicy; tenant-aware production configuration; PVCs; migration hooks; optional Ingress and ServiceMonitor.

## Required production values

Supply database, Redis, object-storage and API-client credentials through an external secret workflow or `secrets.*` values. Do not commit plaintext credentials.

```bash
helm upgrade --install biointel deploy/helm/biointel \
  --namespace biointel --create-namespace \
  --set image.repository=registry.example.com/biointel-ai \
  --set image.tag=12.3.0 \
  --set secrets.databaseUrl='postgresql://...' \
  --set secrets.redisUrl='redis://...' \
  --set secrets.objectStorageEndpoint='https://...' \
  --set secrets.objectStorageAccessKey='...' \
  --set secrets.objectStorageSecretKey='...' \
  --set-json secrets.apiClientsJson='{"clients":[...]}'
```

Run `helm lint deploy/helm/biointel` and render with `helm template` in CI before deployment. Use a GitOps controller for signed, reviewed production releases.
