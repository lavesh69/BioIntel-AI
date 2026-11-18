# Education Test Report

## Commands and results

- `py -3.11 -m unittest tests.test_education_ecosystems -v`: 7 passed, 0 failed.
- Coverage command with branch tracking over `src/biointel/education`: 629 statements / 228 branches; total 86%, gate passed. Core platform 89%, database 96%, adapters 84%, UI 82%, API 77%. The three domains share this bounded context, so separate domain percentages would be artificial.
- Streamlit `AppTest` ran all three page files: 3 passed, 0 exceptions.
- Retained Connect/Calls regression: 14 passed, 0 failed.
- Python compilation for education, pages, API and navigation: passed.
- Windows bootstrap preflight: passed, exit 0.

Coverage evidence: `reports/education-coverage.json` and `reports/education-coverage.txt`.

No live Crossref/RSS provider, FFmpeg rendition, TURN, SFU, recording or transcription service was exercised. Those results are configuration-required, not pass.
