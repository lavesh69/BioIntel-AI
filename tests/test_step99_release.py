from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_step99_version_is_synchronized() -> None:
    assert (ROOT / "VERSION").read_text().strip() == "13.2.0"
    assert 'version = "13.2.0"' in (ROOT / "pyproject.toml").read_text()
    assert '__version__ = "13.2.0"' in (ROOT / "src/biointel/__init__.py").read_text()
    assert '"version": "13.2.0"' in (ROOT / "platform/desktop/package.json").read_text()


def test_all_eleven_modules_include_step99_excellence_layer() -> None:
    expected = {
        94: "render_pangenome_excellence",
        95: "render_long_read_excellence",
        96: "render_protein_design_excellence",
        97: "render_crispr_excellence",
        98: "render_outbreak_excellence",
        99: "render_synthetic_biology_excellence",
        100: "render_rare_disease_excellence",
        101: "render_knowledge_graph_excellence",
        102: "render_biomarker_excellence",
        103: "render_workflow_excellence",
        104: "render_innovation_hub_excellence",
    }
    for number, function in expected.items():
        page = next((ROOT / "pages").glob(f"{number}_*.py"))
        text = page.read_text()
        assert function in text
        assert "Step 99" in text


def test_step99_installer_remains_path_safe_and_python_driven() -> None:
    install = (ROOT / "INSTALL_WINDOWS.bat").read_text()
    installer_py = (ROOT / "scripts/install_windows_step97.py").read_text()
    runner_py = (ROOT / "scripts/run_biointel_step97.py").read_text()
    assert 'cd /d "%~dp0"' in install
    assert '"%PYTHON_EXE%" "%~dp0scripts\\install_windows_step97.py"' in install
    assert "subprocess.Popen" in installer_py
    assert '"--root", "."' in installer_py
    assert "_wait_ready" in runner_py
    assert "webbrowser.open(ui_url)" in runner_py


def test_step99_excellence_modules_are_packaged() -> None:
    assert (ROOT / "src/biointel/innovation/excellence_engines.py").is_file()
    assert (ROOT / "src/biointel/innovation/excellence_ui.py").is_file()
    assert (ROOT / "tests/test_step99_innovation_excellence.py").is_file()
