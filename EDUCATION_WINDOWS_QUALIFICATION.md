# Education Windows Qualification

## Qualified local environment

- OS family: Windows
- Python: CPython 3.11 x64
- Paths: spaces and Unicode tested
- Persistence: SQLite local default
- Streamlit: 1.58
- Offline media dependency: `imageio-ffmpeg==0.6.0`

## Scripts

- `EXTRACT_INSTALL_RUN_EDUCATION_PHASE17_TO_22_4PART_WINDOWS.bat`
- `INSTALL_EDUCATION_PHASE17_TO_22_WINDOWS.bat`
- `RUN_EDUCATION_PHASE17_TO_22_WORKER_WINDOWS.bat`
- `DIAGNOSE_EDUCATION_PHASE17_TO_22_WINDOWS.bat`

All scripts use `%~dp0`, quoted paths and per-user LocalAppData defaults. The Python worker
also performs an exclusive PID lease check and removes a stale lease only after verifying
that its process is not alive.

## Results

- Unicode/space-path diagnostic: passed.
- One-pass durable worker: passed.
- Duplicate worker lease test: passed.
- Dependency lock checksum: passed.
- Windows wheelhouse: 122/122 wheels present, readable and hash-matched.
- Python compile-all: passed.
- Target Education/Connect/Shiro suite: 206 passed.

## Operational use

1. Keep all four matching ZIPs and the extraction BAT in one folder.
2. Run the extraction BAT as a normal user.
3. The package extracts under `%LOCALAPPDATA%\BioIntelAI\InstallSource`.
4. The managed installer installs under `%LOCALAPPDATA%\BioIntelAI\App`.
5. Run the diagnostic BAT after installation.
6. Run the worker BAT for durable Education events; it auto-discovers an institution
   administrator unless an explicit administrator ID is provided.

## Boundaries

The local call implementation and signaling state are retained. Public relay behavior is
not qualified without real TURN credentials. Android/mobile browser responsiveness is
preserved; no separate native Android application was created.

