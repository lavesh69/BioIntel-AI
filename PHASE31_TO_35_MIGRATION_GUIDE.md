# Phase 31–35 Migration Guide

1. Stop BioIntel AI and confirm the local health endpoint is closed.
2. Back up the existing application release and the separate `UserData` directory.
3. Verify the production ZIP with `BioIntel-AI-Phase31-to-35-SHA256.txt`.
4. Keep the production ZIP beside `BioIntel-AI-Windows-Installer.exe`.
5. Run the installer as the normal user. Administrator rights are not required for the
   default LocalAppData target.
6. The installer extracts to a temporary directory, verifies the launcher, moves the
   prior `current` release into a timestamped `rollback` directory, and atomically moves
   the new release into `current`.
7. Start BioIntel AI. The idempotent
   `education_phase31_to_35_research_platform_v1` migration creates missing Phase 32–35
   tables without dropping Phase 1–30 data.
8. Verify home, Phase 32–35 capabilities, user/tenant isolation, and a representative
   workflow before opening the deployment to users.

Do not copy databases between tenants or bypass institutional retention/consent policy.
Keep the prior release and backup until post-upgrade acceptance is complete.
