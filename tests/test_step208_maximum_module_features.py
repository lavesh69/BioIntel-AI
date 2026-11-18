from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pandas as pd
import pytest

from biointel.module_features_v208.bioinformatics import BIOINFORMATICS_V208_FEATURES
from biointel.module_features_v208.demos import demo_payload
from biointel.module_features_v208.discovery import DISCOVERY_V208_FEATURES
from biointel.module_features_v208.execution import execute_feature
from biointel.module_features_v208.ingestion import (
    INTERACTIVE_PREVIEW_BYTES,
    MAX_UPLOAD_BYTES,
    detect_format,
    format_support_table,
    load_preview,
    stage_stream,
)
from biointel.module_features_v208.lab import LAB_V208_FEATURES
from biointel.module_features_v208.neuro import NEURO_V208_FEATURES
from biointel.module_features_v208.visuals import figures_for_result
from biointel.neuro_cns import __version__
from biointel.neuro_cns.catalog import MODULES, MODULE_BY_KEY
from biointel.neuro_cns.production import official_resource_plan
from biointel.ui.navigation import PAGE_CATALOG


ROOT = Path(__file__).resolve().parents[1]
FEATURES = [
    *(('Neuro/CNS', key) for key, _, _ in NEURO_V208_FEATURES),
    *(('Bioinformatics', key) for key, _, _ in BIOINFORMATICS_V208_FEATURES),
    *(('Discovery', key) for key, _, _ in DISCOVERY_V208_FEATURES),
    *(('Lab Analytics', key) for key, _, _ in LAB_V208_FEATURES),
]
NO_VISUAL_REQUIRED = {'format_readiness', 'tool_readiness', 'reproducibility'}


def _options(feature_key: str) -> dict[str, object]:
    if feature_key == 'tool_readiness':
        return {'tools': ['biointel-v208-tool-that-does-not-exist']}
    if feature_key == 'advanced_precision_neurology':
        return {'repeats': 5}
    return {}


def test_step208_registry_is_complete_and_unique() -> None:
    assert __version__ == '208.0'
    assert len(NEURO_V208_FEATURES) == 17
    assert len(BIOINFORMATICS_V208_FEATURES) == 8
    assert len(DISCOVERY_V208_FEATURES) == 8
    assert len(LAB_V208_FEATURES) == 9
    assert len(FEATURES) == 42
    assert len(FEATURES) == len(set(FEATURES))


@pytest.mark.parametrize(('category', 'feature_key'), FEATURES)
def test_every_step208_demo_executes_without_streamlit(category: str, feature_key: str) -> None:
    result = execute_feature(category, feature_key, demo_payload(feature_key), options=_options(feature_key))
    assert isinstance(result, dict)
    assert result
    boundary = str(result.get('scientific_boundary', '')).lower()
    assert boundary
    assert any(term in boundary for term in ('research', 'clinical', 'capability', 'tool discovery'))

    tables = [value for value in result.values() if isinstance(value, pd.DataFrame)]
    if feature_key not in {'reproducibility'}:
        assert tables or result.get('summary') or result.get('metrics')

    figures = figures_for_result(feature_key, result)
    if feature_key not in NO_VISUAL_REQUIRED:
        assert figures, feature_key
        assert all(len(figure.data) >= 1 for figure in figures.values())


def test_neuro_catalog_and_resource_lifecycle_cover_all_41_modules() -> None:
    assert len(MODULES) == 41
    assert len(MODULE_BY_KEY) == 41
    assert [module.number for module in MODULES] == list(range(1, 42))
    plan = official_resource_plan()
    assert plan['all_modules_covered'] is True
    assert plan['covered_modules'] == list(range(1, 42))


@pytest.mark.parametrize(
    'module_key',
    [
        'neuro_oncology',
        'epilepsy_diary',
        'movement_disorders',
        'autonomic_hrv',
        'speech_language',
        'neurodegeneration_progression',
        'neuropathology',
        'neurocritical_care',
    ],
)
def test_new_neuro_domains_are_registered(module_key: str) -> None:
    assert module_key in MODULE_BY_KEY
    module = MODULE_BY_KEY[module_key]
    assert module.number >= 34
    assert module.title
    assert module.description


def test_four_feature_center_pages_are_in_navigation_and_theme_safe() -> None:
    expected = {
        'pages/264_Neuro_Maximum_Potential_Feature_Center.py',
        'pages/265_Bioinformatics_Deep_Execution_Feature_Center.py',
        'pages/266_Discovery_Optimization_Feature_Center.py',
        'pages/267_Lab_Analytics_Advanced_Feature_Center.py',
    }
    catalog_paths = {page.path for page in PAGE_CATALOG}
    assert expected <= catalog_paths
    for relative in expected:
        source = (ROOT / relative).read_text(encoding='utf-8')
        assert 'apply_theme()' in source
        assert 'render_feature_center' in source


def test_disk_staging_is_atomic_hashed_and_previewable(tmp_path: Path) -> None:
    data = b'sample_id,value\nS1,1.5\nS2,2.5\n'
    status = stage_stream(io.BytesIO(data), filename='../unsafe cohort.csv', staging_dir=tmp_path)
    staged = Path(status['path'])
    assert staged.parent == tmp_path.resolve()
    assert staged.name == 'unsafe cohort.csv'
    assert status['size_bytes'] == len(data)
    assert status['sha256'] == hashlib.sha256(data).hexdigest()
    assert status['format'] == 'csv_tsv'
    assert status['interactive_preview_allowed'] is True
    preview = load_preview(staged, max_rows=1)
    assert preview['preview'].shape == (1, 2)
    assert preview['manifest']['sha256'] == status['sha256']


def test_upload_contract_is_one_gigabyte_with_memory_safe_preview() -> None:
    assert MAX_UPLOAD_BYTES == 1024**3
    assert INTERACTIVE_PREVIEW_BYTES == 100 * 1024**2
    assert MAX_UPLOAD_BYTES > INTERACTIVE_PREVIEW_BYTES


def test_format_registry_is_explicit_about_native_and_optional_support() -> None:
    table = format_support_table()
    assert {'format_key', 'mode', 'extensions', 'description'} <= set(table.columns)
    expected = {'bam_cram_bcf', 'nifti', 'dicom', 'edf_bdf_fif', 'h5ad', 'ome_tiff', 'mzml', 'pod5'}
    assert expected <= set(table['format_key'])
    assert detect_format('brain.nii.gz').format_key == 'nifti'
    assert detect_format('cohort.bam').mode == 'optional_adapter'
    assert detect_format('unknown.xyz') is None


def test_invalid_inputs_fail_with_clear_errors() -> None:
    with pytest.raises(ValueError, match='Microbiome control QC'):
        execute_feature('Bioinformatics', 'microbiome_controls', pd.DataFrame({'x': [1]}))
    with pytest.raises(ValueError, match='reference and query'):
        execute_feature('Discovery', 'admet_calibration', pd.DataFrame({'x': [1]}))
    with pytest.raises(ValueError, match='Primer/CRISPR'):
        execute_feature('Lab Analytics', 'primer_crispr', pd.DataFrame({'x': [1]}))
    with pytest.raises(KeyError, match='Unknown Step208 feature'):
        execute_feature('Neuro/CNS', 'not_a_feature', None)


def test_protected_module_hashes_remain_unchanged() -> None:
    payload = json.loads((ROOT / 'PROTECTED_MODULE_HASHES_STEP205.json').read_text(encoding='utf-8'))
    assert len(payload['entries']) == 17
    for entry in payload['entries']:
        path = ROOT / entry['path']
        assert path.is_file(), entry['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], entry['path']
