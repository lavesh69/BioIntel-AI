# Known Limitations

- Physical Windows install/start/stop/restart, shortcut, SmartScreen and security-product behaviour require validation on supported Windows machines; container tests cannot prove them.
- External scientific engines, large reference databases, proprietary tools, model weights and licences are not automatically bundled. Runtime qualification is explicit and fail-closed.
- Many scientific computations are exploratory/research-use. Software test success is not clinical, regulatory, pharmaceutical or independent scientific validation.
- Demo/synthetic models are quarantined and labelled. They are not eligible for default scientific inference unless the model registry explicitly records separate qualification.
- Whole-slide images, large sequencing runs, graph indexes, molecular-dynamics trajectories and foundation-model workloads may require high RAM, disk or optional GPU hardware.
- Live Workspace LAN mode requires trusted-network controls and configured UI accounts; public internet port forwarding is not supported.
- Formal electronic signatures, GxP validation, institutional access governance, clinical decision support and regulated deployment require organization-specific controls beyond this release.
- Website/account/update services are specifications and optional integrations, not required core services.
