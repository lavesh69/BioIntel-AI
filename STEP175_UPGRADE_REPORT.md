# BioIntel AI Step 175 — Target Environment Qualification

Version **14.7.0** adds the executable target-machine layer for the previously defined Step 175 scope: Windows/WSL2/GPU host qualification, transactional installation of 53 specialist scientific engines, production-reference acquisition for 26 reference groups, licence/checksum capture, smoke and known-answer controls, resume, rollback and fail-closed qualification.

## Delivered

- Three target hardware profiles: CPU workstation, GPU scientific workstation and reference-data server.
- Twelve isolated micromamba environment groups to reduce dependency conflicts.
- Transactional WSL2 installer with planning, execution and resume modes.
- Target Windows probe for OS build, architecture, virtualization, WSL2, distro, long paths, RAM, storage, GPU, driver, network and manual resilience tests.
- Fifty-three engine execution specifications and qualification fixtures.
- Twenty-six production-reference intake kits with release, licence, provider checksum, local SHA-256, schema, index, reviewer and rollback requirements.
- Five manual/provider-controlled engine intake kits.
- Hash-chained target execution registry.
- Native workflow assurance and a dedicated Step 175 command center.

## Honest boundary

The build host cannot physically certify another Windows/GPU machine and cannot accept restricted provider licences, download credentials, install multi-terabyte references or manufacture instrument/site results. The framework is 10/10; actual target-qualified counts are populated only after genuine execution artifacts pass.
