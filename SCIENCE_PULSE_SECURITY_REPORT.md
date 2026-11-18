# Science Pulse Security Report

Implemented controls: HTTPS-only endpoints, credential/port rejection, approved-host enforcement, DNS resolution and public-IP checks, localhost/private/link-local/reserved rejection, redirect bounds, 5 MiB response cap, MIME allowlist, TLS verification, timeouts, DTD/entity rejection, safe ElementTree parsing, script/style/iframe/object removal, text length bounds, source rate spacing, tenant isolation, API role gates, audits, and bounded safe errors.

Feed HTML, scripts, attachments, and JavaScript are never executed. Provider tokens are not stored in Science Pulse rows or diagnostics.
