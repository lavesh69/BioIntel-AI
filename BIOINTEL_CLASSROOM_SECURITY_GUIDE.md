# BioIntel Classroom Security Guide

Every protected Classroom row carries an institution ID and service methods re-check membership/role before access. Teacher authority is subject-scoped; guardian reads require an active verified child link. Audit events cover official mutations. Run only on loopback unless TLS, trusted hosts, authentication and firewall rules are explicitly configured. Uploaded files are copied to managed storage and SHA-256 hashed; malware scanning is configuration-required. Never package UserData, `.env`, logs or learner records.
