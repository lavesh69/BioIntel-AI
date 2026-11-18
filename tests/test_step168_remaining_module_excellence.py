from pathlib import Path
import sqlite3
import pandas as pd

from biointel.priority_v168 import ALL_MODULES, TARGETS, ensure_step168_assets, ensure_step168_database, priority_matrix, universal_evidence_matrix
from biointel.scientific_depth import native_input_template, run_native_workflow
from biointel.scientific_depth.profiles import MODULE_PROFILES

ROOT=Path(__file__).resolve().parents[1]
EXPECTED={
'autonomous_lab_planner':'step168_autonomous_lab_plan_feasibility','clinical_biomarker_survival':'step168_clinical_biomarker_survival_assurance','flow_cytometry':'step168_flow_cytometry_marker_populations','gene_therapy_vector':'step168_gene_therapy_vector_safety','pharmacovigilance_intelligence':'step168_pharmacovigilance_disproportionality','synthetic_cohort_trial':'step168_synthetic_cohort_trial_fidelity','background_job_engine':'step168_background_job_engine_assurance','background_jobs_core':'step168_background_jobs_core_assurance','benchmark_validation_v2':'step168_benchmark_validation_card','bioprocess_fermentation':'step168_bioprocess_batch_trajectory_assurance','causal_perturbation':'step168_causal_summary','clinical_pharma_core':'step168_clinical_pharma_endpoint_assurance','clinical_trial_biomarker':'step168_clinical_trial_biomarker_assurance','collaboration_review_v2':'step168_collaboration_review_assurance','cross_module_workspace':'step168_cross_module_workspace_lineage','data_lakehouse_v2':'step168_data_lakehouse_product_assurance','document_intelligence_core':'step168_document_intelligence_assurance','epitranscriptomics':'step168_epitranscriptomics_site_assurance','evidence_citation_engine':'step168_evidence_citation_assurance','host_pathogen_interaction':'step168_host_pathogen_interaction_assurance','knowledge_graph_core':'step168_knowledge_graph_integrity','longitudinal_multiomics':'step168_longitudinal_multiomics_assurance','multiomics_biomarker_core':'step168_multiomics_biomarker_assurance','multiomics_harmonization':'step168_multiomics_harmonization_assurance','plugin_marketplace_core':'step168_plugin_core_assurance','plugin_marketplace_v2':'step168_plugin_marketplace_assurance','provenance_ledger_v2':'step168_provenance_ledger_chain_assurance','reference_lifecycle_v2':'step168_reference_lifecycle_assurance','synthetic_biology_core':'step168_synthetic_biology_circuit_assurance','synthetic_data_privacy':'step168_synthetic_data_privacy_assurance','unified_report_builder':'step168_unified_report_assurance','universal_file_inspector':'step168_universal_file_inspection_assurance','store_readiness_core':'step168_windows_store_readiness_assurance','workflow_builder_core':'step168_workflow_core_assurance','workflow_builder_v2':'step168_workflow_builder_assurance'}

def test_step168_assets_database_and_matrices():
    written=ensure_step168_assets(ROOT)
    db=ensure_step168_database(ROOT,[(k,v.title) for k,v in MODULE_PROFILES.items()])
    assert len(written)==620
    assert len(priority_matrix(ROOT))==35
    assert len(universal_evidence_matrix())==80
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert conn.execute('SELECT COUNT(*) FROM modules').fetchone()[0]==80

def test_step168_all_focused_demo_runs():
    for key in TARGETS:
        result=run_native_workflow(key,native_input_template(key,demonstration=True),metadata={'project_root':str(ROOT)})
        assert result.status in {'pass','review'}
        assert EXPECTED[key] in result.tables
        assert 'step168_remaining_module_excellence_gate' in result.tables
        assert 'step168_universal_external_evidence_gate' in result.tables
        assert result.summary['step168_remaining_module_software_score']==10.0
        assert result.summary['step168_remaining_module_native_depth_score']==10.0
        assert result.summary['step168_external_evidence_operations_framework_score']==10.0
        assert result.summary['step168_real_world_release_eligible'] is False

def test_step168_all_80_universal_evidence_gates():
    for key in ALL_MODULES:
        result=run_native_workflow(key,native_input_template(key,demonstration=True),metadata={'project_root':str(ROOT)})
        gate=result.tables['step168_universal_external_evidence_gate'].iloc[0]
        assert gate['evidence_operations_framework_score']==10.0
        assert not bool(gate['real_world_release_eligible'])
        assert result.summary['step168_external_evidence_operations_framework_score']==10.0

def test_step168_pharmacovigilance_and_vector_controls():
    pv=pd.DataFrame({'report_id':[f'R{i}' for i in range(20)],'drug':['A']*10+['B']*10,'event':['X']*8+['Y']*2+['X']*2+['Y']*8})
    result=run_native_workflow('pharmacovigilance_intelligence',pv,metadata={'project_root':str(ROOT)})
    out=result.tables['step168_pharmacovigilance_disproportionality']
    assert out['ROR'].max()>1
    vector=pd.DataFrame({'construct_id':['good','oversize'],'dna_sequence':['ATG'+'GCT'*100+'TAA','ATG'+'GCC'*1700+'TAA']})
    result=run_native_workflow('gene_therapy_vector',vector,metadata={'project_root':str(ROOT)})
    out=result.tables['step168_gene_therapy_vector_safety']
    assert out.loc[out.construct_id=='good','step168_research_priority'].iloc[0]
    assert not out.loc[out.construct_id=='oversize','step168_research_priority'].iloc[0]

def test_step168_privacy_workflow_and_provenance_guards():
    privacy=pd.DataFrame({'age_band':['20-29']*3+['30-39']*3,'region':['N']*3+['S']*3,'diagnosis':['A','B','A','A','B','C']})
    result=run_native_workflow('synthetic_data_privacy',privacy,metadata={'project_root':str(ROOT)})
    assert result.tables['step168_synthetic_data_privacy_assurance']['k_anonymity'].min()==3
    wf=pd.DataFrame({'node':['import','qc'],'depends_on':['','import'],'input_type':['file','table'],'output_type':['table','table'],'status':['completed','completed'],'checkpoint':[True,True],'retry_limit':[1,2]})
    result=run_native_workflow('workflow_builder_v2',wf,metadata={'project_root':str(ROOT)})
    assert result.tables['step168_workflow_builder_assurance']['step168_workflow_node_ready'].all()
    prov=native_input_template('provenance_ledger_v2',demonstration=True)
    result=run_native_workflow('provenance_ledger_v2',prov,metadata={'project_root':str(ROOT)})
    assert result.tables['step168_provenance_ledger_chain_assurance']['step168_previous_hash_valid'].all()
