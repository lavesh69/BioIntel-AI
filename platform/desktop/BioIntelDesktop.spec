from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve()
script = ROOT / "biointel_desktop_server.py"

datas = []
binaries = []
hiddenimports = []
for package in [
    "streamlit", "fastapi", "uvicorn", "plotly", "pandas", "numpy", "sklearn", "rdkit", "Bio",
    "pypdf", "pdfplumber", "pypdfium2", "openpyxl", "docx", "pptx",
]:
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden
hiddenimports += collect_submodules("biointel")

analysis = Analysis(
    [str(script)],
    pathex=[str(ROOT.parent.parent / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    excludes=["tkinter", "matplotlib.tests", "numpy.tests", "pandas.tests"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="biointel-desktop-server",
    console=False,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    icon=str(ROOT / "assets" / "BioIntelAI.ico"),
)
coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="biointel-desktop-server",
)
