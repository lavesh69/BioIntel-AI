# BioIntel AI 15.6.0 Release Blockers & Resolution Plan

| Blocker ID | Description | Severity | Target Phase | Resolution Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **BLK-01** | Outdated text in docs/batch files referencing 'five ZIP parts' | Medium | Phase 1 | Comprehensive text replacement across docs, .bat files, and JSON manifests to 4-part release contract. |
| **BLK-02** | Root directory clutter (287 .bat files) | Medium | Phase 1 | Consolidate into 5 canonical launchers (INSTALL, RUN_BOTH, REPAIR, DIAGNOSE, UNINSTALL) with legacy redirects. |
| **BLK-03** | Streamlit page sprawl (281 pages) | High | Phase 3 | Reorganize navigation into clean product domains; move assurance/internal pages under Admin/QA tabs. |
| **BLK-04** | Process leaks / unkilled child processes on launch failure | High | Phase 1 | Implement process-tree killing (psutil.Process.children) in RUN_BOTH_WINDOWS.bat and resident supervisor. |
| **BLK-05** | Native engine fail-closed qualification enforcement | High | Phase 4 | Ensure all engine outputs clearly identify engine version and status (NATIVE / PROXY / UNAVAILABLE). |
