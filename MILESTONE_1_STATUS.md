# Step 1 Status

## Implemented

- Modular DNA/RNA/protein parsing and validation
- Raw sequence and single-record FASTA input
- Nucleotide and protein statistics
- DNA complement, reverse complement and transcription
- Six-frame translation and complete six-frame ORF detection
- Exact motif search
- Pairwise global/local alignment using `Bio.Align.PairwiseAligner`
- Protein alignment with BLOSUM62
- Streamlit pages, Plotly charts and downloads
- PDF summary generation
- Windows one-click install, run and test scripts
- Unit tests

## Verification performed

- `ruff check .` — passed
- `black --check .` — passed
- `pytest -q` — 13 tests passed
- `python -m compileall -q app.py pages src` — passed
- Streamlit server smoke test — started successfully

## Windows usage

1. Double-click `INSTALL_WINDOWS.bat` once.
2. Double-click `RUN_APP_WINDOWS.bat` whenever you want to start the application.
3. Double-click `RUN_TESTS_WINDOWS.bat` to verify the installation.

## Limitation

The current ORF finder reports complete start-to-stop ORFs. Advanced IUPAC motif translation, restriction maps, multi-record FASTA batches and Drug–Target Interaction prediction were planned for later milestones.
