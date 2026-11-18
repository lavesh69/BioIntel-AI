# Kubernetes Production Deployment

The Helm chart at `deploy/helm/biointel` provides separate API, Streamlit and worker workloads, security contexts, probes, autoscaling, disruption budgets, default-deny network policy, persistent volumes, migration hooks, optional ingress and Prometheus ServiceMonitor support.

A production release must still execute cluster-specific load, failover, backup-restore and disaster-recovery exercises. Helm readiness means the deployment architecture and controls exist; it does not certify an untested cluster.
