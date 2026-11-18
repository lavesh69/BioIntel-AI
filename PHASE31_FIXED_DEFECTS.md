# Phase 31 Fixed Defects

- DTI training now defaults to one worker on Windows and exposes explicit non-zero `parallel_jobs`.
- Scientific-tool downloads now fail closed without a publisher digest and use bounded safe extraction.
- The global Streamlit CCv2 layout observer recovers from isolated registry resets.
- The runtime exception boundary is safe when the originating widget is inside a form.
- The audit parser handles UTF-8 BOM correctly and excludes runtime/test residue from source-path conclusions.
