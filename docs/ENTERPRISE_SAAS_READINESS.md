# Enterprise and Commercial SaaS Readiness

## Enterprise controls

- strict tenant isolation and request-scoped tenant context;
- role and membership enforcement;
- tenant-prefixed filesystem and object-store routing;
- API authentication, authorization, audit and rate limits;
- subscription, entitlement, quota and usage controls;
- tenant export, deletion, restriction and rectification requests;
- Kubernetes deployment, observability and security gates;
- controlled release, backup, restore and disaster-recovery procedures.

## Commercial control plane

The SaaS control plane supports plans, subscriptions, idempotent usage metering, quotas, feature entitlements and tenant data-right workflows. Payment processing, taxation, commercial contracts and invoicing remain external legal/finance integrations.

## SLA and operations

A production deployment must define availability and support SLA objectives, alerting, incident severity, escalation, customer communications, recovery-time/recovery-point objectives and evidence from load, failover and restore exercises.

## Tenant isolation boundary

Public scientific reference catalogs may be shared. Tenant-created datasets, models, reports, jobs, documents, usage records and exports must always be tenant-scoped and access-controlled.
