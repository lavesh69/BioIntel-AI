from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

import streamlit as st


@st.cache_data(show_spinner=False)
def _load_catalog(catalog_path: str, modified_ns: int) -> dict[str, Any]:
    del modified_ns
    path = Path(catalog_path)
    if not path.is_file():
        return {"kits": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"kits": {}}
    return payload if isinstance(payload, dict) else {"kits": {}}


@st.cache_data(show_spinner=False)
def _read_local_file(path_text: str, modified_ns: int, size_bytes: int) -> bytes:
    del modified_ns, size_bytes
    path = Path(path_text)
    return path.read_bytes()


def _safe_asset(root: Path, directory: str, filename: str) -> Path | None:
    base = (root / "data" / "module_starter_kits").resolve()
    try:
        candidate = (base / directory / filename).resolve()
        candidate.relative_to(base)
    except (OSError, ValueError):
        return None
    return candidate if candidate.is_file() else None


def _mime_type(path: Path) -> str:
    explicit = {
        ".csv": "text/csv",
        ".tsv": "text/tab-separated-values",
        ".json": "application/json",
        ".zip": "application/zip",
        ".md": "text/markdown",
        ".fasta": "text/plain",
        ".fa": "text/plain",
        ".fna": "text/plain",
        ".faa": "text/plain",
        ".fastq": "text/plain",
        ".fq": "text/plain",
        ".vcf": "text/plain",
        ".gff": "text/plain",
        ".gff3": "text/plain",
        ".gtf": "text/plain",
        ".gmt": "text/plain",
        ".nwk": "text/plain",
        ".newick": "text/plain",
        ".pdb": "chemical/x-pdb",
        ".cif": "text/plain",
        ".mmcif": "text/plain",
        ".obo": "text/plain",
    }
    return explicit.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _role_label(role: str) -> str:
    labels = {
        "blank": "Blank template",
        "example": "Filled example",
        "output": "Expected output",
        "guide": "Format guide",
        "manifest": "Kit manifest",
    }
    return labels.get(role, role.replace("_", " ").title())


def render_module_starter_kit_sidebar(page_key: str | None, project_root: Path) -> None:
    """Render an offline starter-kit downloader for the active module.

    The library is deliberately local-only. Files are served from the installed
    application package and never fetched from the internet. Unsupported pages
    simply render no panel.
    """

    if not page_key:
        return
    catalog_path = project_root / "data" / "module_starter_kits" / "catalog.json"
    if not catalog_path.is_file():
        return
    try:
        catalog_stat = catalog_path.stat()
    except OSError:
        return
    catalog = _load_catalog(str(catalog_path), catalog_stat.st_mtime_ns)
    kits = catalog.get("kits", {})
    if not isinstance(kits, dict):
        return
    kit = kits.get(page_key)
    if not isinstance(kit, dict):
        return

    directory = str(kit.get("directory", page_key))
    files = kit.get("files", [])
    if not isinstance(files, list):
        files = []

    with st.expander("📦 Local Data Starter Kit", expanded=False):
        st.caption(str(kit.get("description", "Offline input templates and examples.")))
        accepted = str(kit.get("accepted_formats", "module-supported formats"))
        st.markdown(f"**Accepted:** {accepted}")

        zip_name = str(kit.get("zip", ""))
        zip_path = _safe_asset(project_root, directory, zip_name)
        if zip_path is not None:
            try:
                zip_stat = zip_path.stat()
                zip_bytes = _read_local_file(str(zip_path), zip_stat.st_mtime_ns, zip_stat.st_size)
                st.download_button(
                    "Download complete starter kit",
                    data=zip_bytes,
                    file_name=zip_path.name,
                    mime="application/zip",
                    key=f"starter_kit_zip_{page_key}",
                    width="stretch",
                )
            except OSError:
                st.warning("The local starter-kit ZIP could not be read.")

        downloadable: list[tuple[dict[str, Any], Path]] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            filename = str(item.get("name", ""))
            asset = _safe_asset(project_root, directory, filename)
            if asset is not None:
                downloadable.append((item, asset))

        if downloadable:
            options = list(range(len(downloadable)))

            def format_item(index: int) -> str:
                metadata, path = downloadable[index]
                return f"{_role_label(str(metadata.get('role', 'file')))} · {path.name}"

            selected = st.selectbox(
                "Download an individual file",
                options,
                format_func=format_item,
                key=f"starter_kit_file_{page_key}",
            )
            metadata, selected_path = downloadable[int(selected)]
            try:
                selected_stat = selected_path.stat()
                selected_bytes = _read_local_file(
                    str(selected_path), selected_stat.st_mtime_ns, selected_stat.st_size
                )
                st.download_button(
                    f"Download {_role_label(str(metadata.get('role', 'file'))).lower()}",
                    data=selected_bytes,
                    file_name=selected_path.name,
                    mime=_mime_type(selected_path),
                    key=f"starter_kit_asset_{page_key}_{selected_path.name}",
                    width="stretch",
                )
            except OSError:
                st.warning("The selected local file could not be read.")

            with st.popover("View kit contents", width="stretch"):
                for metadata, path in downloadable:
                    size = int(metadata.get("size_bytes", path.stat().st_size) or 0)
                    st.markdown(
                        f"- **{_role_label(str(metadata.get('role', 'file')))}:** "
                        f"`{path.name}` · {size / 1024:.1f} KB"
                    )

        st.info(
            "Starter-kit examples are synthetic and work offline. Keep required headers unchanged, "
            "replace demo rows with your data, then upload the completed file in this module."
        )

    # Verified public/reference datasets are deliberately separated from synthetic templates.
    real_catalog_path = project_root / "data" / "real_scientific_pack" / "catalog.json"
    if not real_catalog_path.is_file():
        return
    try:
        real_stat = real_catalog_path.stat()
        real_catalog = _load_catalog(str(real_catalog_path), real_stat.st_mtime_ns)
    except OSError:
        return
    datasets = real_catalog.get("datasets", [])
    if not isinstance(datasets, list):
        return
    matches = [
        item for item in datasets
        if isinstance(item, dict) and page_key in item.get("modules", [])
    ]
    if not matches:
        return

    real_base = (project_root / "data" / "real_scientific_pack").resolve()

    def resolve_real(relative_path: str) -> Path | None:
        try:
            candidate = (project_root / relative_path).resolve()
            candidate.relative_to(real_base)
        except (OSError, ValueError):
            return None
        return candidate if candidate.is_file() else None

    with st.expander("🧪 Verified Real Public Data", expanded=False):
        st.caption(
            "Official public/reference files bundled locally with provider, release, licence and SHA-256 provenance."
        )
        labels = [f"{item.get('provider', 'Provider')} · {item.get('title', item.get('id', 'Dataset'))}" for item in matches]
        chosen_index = st.selectbox(
            "Choose a real reference dataset",
            list(range(len(matches))),
            format_func=lambda index: labels[index],
            key=f"real_public_dataset_{page_key}",
        )
        chosen = matches[int(chosen_index)]
        st.markdown(f"**Scope:** `{chosen.get('scope', 'public_reference')}`")
        if chosen.get('evidence_level'):
            st.markdown(f"**Evidence level:** {chosen.get('evidence_level')}")
        st.caption(
            f"Release: {chosen.get('release', 'not recorded')} · Licence: {chosen.get('licence', 'provider terms')}"
        )
        file_meta = chosen.get("file_metadata", [])
        available: list[tuple[dict[str, Any], Path]] = []
        for metadata in file_meta if isinstance(file_meta, list) else []:
            if not isinstance(metadata, dict):
                continue
            asset = resolve_real(str(metadata.get("path", "")))
            if asset is not None:
                available.append((metadata, asset))
        if available:
            selected_file = st.selectbox(
                "Select official file",
                list(range(len(available))),
                format_func=lambda index: f"{available[index][1].name} · {int(available[index][0].get('size_bytes', 0)) / 1024:.1f} KB",
                key=f"real_public_file_{page_key}",
            )
            metadata, asset = available[int(selected_file)]
            try:
                asset_stat = asset.stat()
                asset_bytes = _read_local_file(str(asset), asset_stat.st_mtime_ns, asset_stat.st_size)
                st.download_button(
                    "Download verified real-data file",
                    data=asset_bytes,
                    file_name=asset.name,
                    mime=_mime_type(asset),
                    key=f"real_public_download_{page_key}_{asset.name}",
                    width="stretch",
                )
                st.code(f"SHA-256: {metadata.get('sha256', '')}", language=None)
            except OSError:
                st.warning("The selected verified file could not be read.")
        st.warning(
            "Real public/reference data improve authenticity and reproducibility, but do not by themselves "
            "constitute clinical validation, regulatory approval or independent wet-lab confirmation."
        )

    validation_pages = {
        'external_validation', 'scientific_release_gate', 'real_evidence_studio',
        'dti_validation_evidence', 'scientific_data_readiness', 'wet_lab_biotechnology'
    }
    if page_key in validation_pages:
        site_pack = project_root / 'data' / 'prospective_validation_site_pack' / 'BioIntel_Prospective_Validation_Site_Pack.zip'
        if site_pack.is_file():
            with st.expander('🔒 Prospective Validation Site Pack', expanded=False):
                st.caption('Prediction locking, preregistration, blinding, chain of custody, site independence and signed outcome-import templates.')
                site_stat = site_pack.stat()
                st.download_button(
                    'Download prospective validation site pack',
                    data=_read_local_file(str(site_pack), site_stat.st_mtime_ns, site_stat.st_size),
                    file_name=site_pack.name,
                    mime='application/zip',
                    key=f'prospective_site_pack_{page_key}',
                    width='stretch',
                )
                st.warning('Readiness controls are complete, but a 10/10 completed prospective-validation score requires genuine signed outcomes from independent laboratories.')
