# Phase 31–35 Known Limitations

- The historical full suite remains non-green: 273 failures and 28 skips after Phase 31
  stabilization. The focused Phase 31–35 suite is green.
- Install to a short path. Exceptionally deep roots can prevent native scientific DLLs
  such as RDKit from loading even when Python source paths themselves are valid.
- The Windows installer is not Authenticode-signed; SmartScreen or institutional
  application-control policy may warn or block it.
- Desktop shortcut creation can be blocked by OneDrive, policy, or sandbox controls.
  The installed `BioIntel AI.vbs` launcher remains usable.
- The production protection model removes readable proprietary source and ships
  bytecode, but bytecode is not irreversible encryption or DRM.
- Live cloud object stores, remote sync servers, identity providers, institutional
  networks, Slurm/Kubernetes/HPC, and public API ingress were not available for testing.
- Remote compute adapters are configuration-only and disabled by default.
- Multi-device sync was verified using deterministic local adapters, not geographically
  distributed devices or a production TLS service.
- No production-scale load, soak, chaos, accessibility lab, or clean-machine hardware
  matrix was executed in this environment.
- Scientific-agent results use a deterministic local evidence runtime; no external LLM
  or live literature service is implied.
- Novelty searches are local evidence comparisons, not patentability or exhaustive
  prior-art opinions.
- Digital Twin, Discovery, hypotheses, experiments, and reports are for research and
  education only. They are not clinical diagnoses, treatment recommendations, medical
  devices, or externally validated biological claims.
- Institutional deployment requires privacy, consent, retention, ethics, biosafety,
  data-governance, security, and scientific-domain review.
