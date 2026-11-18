# Step 19 — Shortcomings Fixed

- Increased the largest DTI pack from 32,000 to 160,000 rows.
- Increased molecular coverage to 1,000 structures.
- Increased target coverage to 160 sequences.
- Added a 5,000-row batch input.
- Added classification, regression and prediction templates.
- Trained six models on the complete 160,000-row dataset.
- Removed repeated per-row molecule and protein validation.
- Replaced repeated pair concatenation with vectorized float32 assembly.
- Replaced the slow large-data Ridge solver with LSQR.
- Added bounded tree settings for practical Windows rebuilds.
- Verified zero train/validation/test group overlap.
- Added dedicated 5X dashboard, API and CLI status.
- Verified real Streamlit and FastAPI startup.
