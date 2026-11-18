from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_neuro_cns_page_boots_without_streamlit_exception() -> None:
    app = AppTest.from_file("pages/263_Neuro_CNS_Intelligence_Studio.py", default_timeout=30)
    app.run()
    assert not app.exception
    labels = [widget.label for widget in app.selectbox]
    assert "Workspace" in labels
    assert "Neuro/CNS module" in labels
