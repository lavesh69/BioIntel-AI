# Education Security Report

Verified controls: institution ID on protected rows; membership and role checks in service methods; subject-scoped teacher authority; verified/consented guardian links; cross-institution denial; published-result gating; locked attendance/result workflows; explicit circular approval; rights confirmation before lecture upload; SHA-256 media/material digests; 2 GiB material limit; 5 MiB external metadata-response limit; HTTPS required for non-loopback feeds; API error mapping; durable audit records; lazy API database creation; no bundled UserData/secrets.

Tested denials include cross-tenant subject creation, unassigned/outsider upload, guardian access before link, outsider circular access, non-admin source management and over-range grading.

Residual findings: uploaded files are not malware-scanned; MIME validation is extension/system based; no at-rest encryption; the education API inherits the host API identity middleware and should not be exposed without keys/TLS/trusted-host/firewall configuration; institution-scoped Shiro evidence mapping is not enabled. These are documented rather than marked passed.
