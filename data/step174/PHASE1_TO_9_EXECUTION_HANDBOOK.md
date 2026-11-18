# BioIntel AI Step 174 — Phase 1 to 9 Execution Handbook

Step 174 completes every software-owned orchestration, template, evidence-intake and verification control for Phases 1–9. It does not fabricate laboratory measurements, provider credentials, patient cohorts, expert identities, physical site history or release approvals.

## Ordered execution

1. **Physical scientific environment qualification** — `RUN_STEP174_LOCAL_ENVIRONMENT_QUALIFICATION_WINDOWS.bat`
2. **Specialist engine installation and qualification** — `PROVISION_STEP170_SCIENTIFIC_RUNTIME_WINDOWS.bat --execute`
3. **Production reference database qualification** — `DOWNLOAD_STEP170_REFERENCE_DATABASES_WINDOWS.bat`
4. **Authentic task-specific models and real cohorts** — `python scripts\step174_realworld_manager.py prepare-model-cohort --module MODULE_KEY`
5. **Independent locked benchmark validation** — `python scripts\step174_realworld_manager.py prepare-benchmark --module MODULE_KEY`
6. **Wet-lab, prospective and orthogonal confirmation** — `python scripts\step172_evidence_manager.py prepare MODULE_KEY`
7. **Independent expert sign-off** — `python scripts\step174_realworld_manager.py prepare-expert-kit --module MODULE_KEY`
8. **Qualified real-world operating history** — `python scripts\step174_realworld_manager.py prepare-history --module MODULE_KEY`
9. **Formal controlled-release review** — `python scripts\step174_realworld_manager.py prepare-release --module MODULE_KEY`

## Final command

`RUN_STEP174_PHASE1_TO_9_WINDOWS.bat`
