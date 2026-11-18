# Multi-Tenant Architecture

BioIntel Step 36 introduces request-scoped tenant isolation for authenticated API clients.

## Identity and tenant resolution

API-client definitions support `tenant_ids`, `default_tenant` and `tenant_role`. Clients select a permitted tenant with the `X-BioIntel-Tenant` header. `TenantContextMiddleware` resolves membership after authentication and rejects unknown, inactive or unauthorized tenants.

## Data isolation

Tenant-created resources use `(tenant_id, resource_id)` compound primary keys. Every read and write is executed with the resolved context's tenant ID in the SQL predicate. Callers cannot override that tenant ID inside a resource operation. Cross-tenant isolation tests verify that identifiers from another tenant return no data.

## Shared catalogs

Bundled public scientific references and platform-wide model catalogs remain shared read-only resources by design. Tenant-created datasets, workflow configuration and other private resources belong in tenant-scoped repositories.

## Production example

```json
{
  "clients": [
    {
      "client_id": "lab-admin",
      "display_name": "Lab administrator",
      "role": "admin",
      "key": "ROTATED_SECRET",
      "tenant_ids": ["lab-a", "lab-b"],
      "default_tenant": "lab-a",
      "tenant_role": "owner"
    }
  ]
}
```
