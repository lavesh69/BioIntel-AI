from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from .catalog import PlanningModule
from .advanced_profiles import get_advanced_profile
from .feature_density import feature_inventory, get_peak_profile, profile_digest
from .standards import REQUIREMENTS
from .specialist_engines import specialist_engine_contract
from .scientific import PlanningResult


def _safe_json(payload):
    return json.dumps(payload, indent=2, sort_keys=True, default=str, ensure_ascii=False).encode('utf-8')


def build_bundle(
    module: PlanningModule,
    result: PlanningResult,
    reviews: pd.DataFrame | None = None,
    specialist_payload: dict | None = None,
) -> tuple[bytes, dict]:
    files: dict[str, bytes] = {}
    for name, table in result.all_tables().items():
        files[f'tables/{name}.csv'] = table.to_csv(index=False).encode('utf-8')
    files['summary.json'] = _safe_json(result.summary)
    files['interpretation.json'] = _safe_json({
        'main_finding': result.main_finding,
        'confidence': result.confidence,
        'limitations': list(result.limitations),
        'recommended_next_step': result.next_step,
    })
    profile = get_advanced_profile(module.key)
    files['module_contract.json'] = _safe_json({
        'key': module.key, 'title': module.title, 'purpose': module.purpose,
        'required_columns': module.required_columns, 'features': module.features,
        'visuals': [vars(item) for item in module.visuals], 'workflow': module.workflow,
        'boundary': module.boundary, 'handoffs': module.handoffs,
        'advanced_features': profile.advanced_features,
        'advanced_visuals': profile.advanced_visuals,
        'standards_readiness_profiles': profile.standards,
        'consistency_links': profile.consistency_links,
        'critical_checks': profile.critical_checks,
    })
    peak_profile = get_peak_profile(module.key)
    files['peak_feature_contract.json'] = _safe_json({
        'profile_digest': profile_digest(module.key),
        'feature_groups': {key: list(value) for key, value in peak_profile.feature_groups.items()},
        'signature_visuals': list(peak_profile.signature_visuals),
        'validation_checks': list(peak_profile.validation_checks),
        'feature_inventory': feature_inventory(module.key).to_dict(orient='records'),
    })
    files['specialist_engine_contract.json'] = _safe_json(specialist_engine_contract(module.key))
    files['planning_os_capabilities.json'] = _safe_json({
        'digital_thread': True,
        'standards_validator': ['SPIRIT-style','ICH E6(R3)-style','ICH E9(R1)-style','CDISC/FHIR readiness'],
        'estimand_builder': True,
        'scenario_simulation': ['Optimistic','Base','Conservative','Stress','Custom'],
        'amendment_impact_analysis': True,
        'assumption_registry': True,
        'structured_collaboration': True,
        'consistency_auditor': True,
        'calculation_verification': True,
        'participant_burden_and_budget': True,
        'peak_feature_lab': True,
        'linked_study_map': True,
        'feature_density_audit': True,
        'specialist_engine_contract': specialist_engine_contract(module.key),
        'full_research_lifecycle': {
            'ethics_consent_participant_protection': True,
            'fair_data_management': True,
            'interim_monitoring_and_safety': True,
            'publication_dissemination_knowledge_translation': True,
            'cross_lifecycle_readiness_panel': True,
            'planning_module_count': 24,
        },
    })
    files['standards_readiness_requirements.json'] = _safe_json([vars(item) for item in REQUIREMENTS])
    if reviews is not None and not reviews.empty:
        files['reviews.csv'] = reviews.to_csv(index=False).encode('utf-8')
    if specialist_payload:
        files['specialist_engine_output.json'] = _safe_json(specialist_payload)
    checksums = {name: sha256(payload).hexdigest() for name, payload in files.items()}
    manifest = {
        'module_key': module.key,
        'module_title': module.title,
        'source_input_sha256': result.summary.get('input_sha256'),
        'files': checksums,
        'scientific_boundary': module.boundary,
    }
    files['manifest.json'] = _safe_json(manifest)
    buffer = BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        for name, payload in sorted(files.items()):
            archive.writestr(name, payload)
    package = buffer.getvalue()
    manifest['bundle_sha256'] = sha256(package).hexdigest()
    manifest['bundle_bytes'] = len(package)
    return package, manifest
