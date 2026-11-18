# BioIntel AI 15.6.0 Master Source Audit
**Owner & Founder:** Lavesh Dobriyal  
**Brand Line:** Biology, Engineered into Intelligence.  
**Audit Date:** 2026-07-26  
**Source Baseline:** Canonical 4-Part ZIP Release (BioIntel-AI-15.6.0-HEAVILY-UPGRADED-Part1(1).zip through Part4.zip)

## 1. Repository Inventory & File Statistics
- **Total Files:** 38,089
- **Total Directories:** 4,773
- **Root Batch (.bat) Files:** 287
- **Streamlit Pages:** 281
- **Python Submodules (src/biointel/):** 142
- **Wheelhouse Packages:** 242 offline .whl files

## 2. Core Architecture Stack
- **Frontend UI:** Streamlit (pp.py, 281 pages in pages/)
- **Backend API:** FastAPI (src/biointel/discovery_platform/api.py, src/biointel/api/)
- **Core Logic:** Python packages in src/biointel/
- **Database Layer:** SQLite (UserData/, datasets.db, 
uns.db), optional PostgreSQL
- **Orchestration & Background Jobs:** Resident Process Supervisor, SQLite job queues (jobs/worker.py), optional Redis & Celery
- **Runtime Environment:** CPython 3.11.9 x64 managed under %LOCALAPPDATA%\BioIntelAI

## 3. Audit Findings & Critical Observations
1. **Script Proliferation:** 287 .bat files in the root folder representing 220 historical steps. Must be consolidated into 5 canonical launchers (INSTALL_WINDOWS.bat, RUN_BOTH_WINDOWS.bat, REPAIR_WINDOWS.bat, DIAGNOSE_WINDOWS.bat, UNINSTALL_BIOINTEL_WINDOWS.bat) with deprecation redirects for legacy launchers.
2. **Page Sprawl:** 281 Streamlit pages, 170 of which are historical step-specific assurance, qualification, and verification centers. Must be organized under clear product domains (Bioinformatics, Multi-Omics, Single-Cell & Spatial, Neuroscience, Drug Discovery, Clinical/LIMS, Shiro AI, Admin/Diagnostics).
3. **Outdated Packaging Text:** Legacy text references across documentation still mention 'five ZIP parts'. The current release is strictly 4 parts.
4. **Native Engine Integration Gaps:** Heuristic and simulation fallbacks need fail-closed adapters for 15 primary engines and domain tools.
