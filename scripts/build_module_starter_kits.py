from __future__ import annotations

import csv
import io
import json
import shutil
import textwrap
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'module_starter_kits'
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)


def csv_text(headers, rows=()):
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue()


def tsv_text(headers, rows=()):
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, delimiter='\t')
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue()


def guide(title: str, accepted: str, required: list[str], notes: list[str]) -> str:
    required_lines = '\n'.join(f'- `{item}`' for item in required) or '- See the included example files.'
    note_lines = '\n'.join(f'- {item}' for item in notes)
    return textwrap.dedent(f'''\
    # {title} — Local Data Starter Kit

    This kit is bundled inside BioIntel AI and works offline.

    ## Recommended workflow

    1. Download the blank template or the complete starter-kit ZIP.
    2. Keep required column names unchanged.
    3. Replace demo rows with your own data.
    4. Save in one of the accepted formats: **{accepted}**.
    5. Upload the completed file in the current module.
    6. Review the module's validation messages before running analysis.

    ## Required structure

    {required_lines}

    ## Notes

    {note_lines}

    > DEMO / SYNTHETIC DATA — NOT FOR CLINICAL OR SCIENTIFIC VALIDATION.
    ''').strip() + '\n'


COMMON_DNA = 'ATGCGTACGTTAGCTAGCTACGATCGATCGTTACGATCGATGCTAGCTAGCATCGATCGATCGTAGCTAGCTAA'
COMMON_DNA_2 = 'ATGCGTACGTTAGCTAGCTACGATCGATCGTTACGATCGATGCTAGATAGCATCGATCGATCGTAGCTAGCTAA'
COMMON_PROTEIN = 'MKTIIALSYIFCLVFADYKDDDDKAGFNVGDEGGFAPNILENKEALELLKQAEK'
COMMON_PROTEIN_2 = 'MNNIRRVAILAFATLSFAVQAAPVSAEKLAALEHHHHHHGSGSENLYFQGAMG'
SMILES = [('CMPD001','Aspirin','CC(=O)OC1=CC=CC=C1C(=O)O'),('CMPD002','Caffeine','CN1C(=O)N(C)c2ncn(C)c2C1=O'),('CMPD003','Acetaminophen','CC(=O)NC1=CC=C(O)C=C1')]

kits: dict[str, dict] = {}

def add(key, title, description, accepted, required, files, notes=None):
    kits[key] = {
        'title': title,
        'description': description,
        'accepted': accepted,
        'required': required,
        'notes': notes or ['Blank cells are allowed only where the module marks a field optional.', 'Use UTF-8 text encoding for CSV/TSV/FASTA files.'],
        'files': files,
    }

add('sequence_analyzer','Sequence Analyzer','DNA, RNA and protein sequence templates for direct analysis.','FASTA, FA, FNA, FAA or TXT',['A FASTA header beginning with `>`','A nucleotide or amino-acid sequence on following lines'],{
'blank_sequence.fasta':'>sample_id\nSEQUENCE_HERE\n',
'filled_dna_example.fasta':f'>demo_dna synthetic_example\n{COMMON_DNA}\n',
'filled_protein_example.faa':f'>demo_protein synthetic_example\n{COMMON_PROTEIN}\n',
'expected_sequence_summary.csv':csv_text(['sequence_id','molecule_type','length','gc_percent','status'],[['demo_dna','DNA',len(COMMON_DNA),51.3,'valid'],['demo_protein','Protein',len(COMMON_PROTEIN),'','valid']]),
})
add('sequence_comparison','Sequence Comparison','A ready two-sequence comparison pair.','FASTA, FA or TXT',['Exactly two labelled sequences for pairwise comparison'],{
'blank_pair.fasta':'>sequence_A\nSEQUENCE_A_HERE\n>sequence_B\nSEQUENCE_B_HERE\n',
'filled_pair_example.fasta':f'>reference_sequence\n{COMMON_DNA}\n>query_sequence\n{COMMON_DNA_2}\n',
'expected_comparison_summary.csv':csv_text(['reference_id','query_id','alignment_length','matches','mismatches','identity_percent'],[['reference_sequence','query_sequence',len(COMMON_DNA),76,2,97.4]]),
})
add('batch_sequence','Batch Sequence Analysis','Multi-record FASTA for batch metrics and clustering.','FASTA, FA, FNA, FAA or TXT',['One or more unique FASTA identifiers','One sequence per FASTA record'],{
'blank_batch_sequences.fasta':'>sample_001\nSEQUENCE_HERE\n>sample_002\nSEQUENCE_HERE\n',
'filled_batch_sequences.fasta':f'>sample_001\n{COMMON_DNA}\n>sample_002\n{COMMON_DNA_2}\n>protein_001\n{COMMON_PROTEIN}\n',
'expected_batch_summary.csv':csv_text(['sequence_id','type','length','valid','cluster'],[['sample_001','DNA',len(COMMON_DNA),True,1],['sample_002','DNA',len(COMMON_DNA_2),True,1],['protein_001','Protein',len(COMMON_PROTEIN),True,2]]),
})
add('drug_analyzer','Drug SMILES Analyzer','Compound identifiers and SMILES for descriptor and similarity analysis.','CSV',['`compound_id`','`name`','`smiles`'],{
'blank_compounds.csv':csv_text(['compound_id','name','smiles']),
'filled_compounds_example.csv':csv_text(['compound_id','name','smiles'],SMILES),
'expected_descriptor_output.csv':csv_text(['compound_id','canonical_smiles','molecular_weight','logp','hbd','hba','valid'],[['CMPD001',SMILES[0][2],180.16,1.2,1,4,True],['CMPD002',SMILES[1][2],194.19,-0.1,0,6,True]]),
})
DTI_HEADERS=['drug_id','canonical_smiles','target_id','protein_sequence','label','p_activity','year']
DTI_ROWS=[['D001',SMILES[0][2],'T001',COMMON_PROTEIN,1,7.2,2022],['D002',SMILES[1][2],'T002',COMMON_PROTEIN_2,0,4.1,2023],['D003',SMILES[2][2],'T001',COMMON_PROTEIN,1,6.4,2024]]
for key,title,desc in [
('dti_features','DTI Feature Builder','Drug–target pair data for feature generation.'),
('model_training','Model Training','Labelled DTI data for classification or regression training.'),
('dti_predictor','DTI Predictor','Batch drug–target pairs for local model inference.'),
('data_quality','Data Quality & Activity','DTI activity records for validation and duplicate checks.'),
]:
    add(key,title,desc,'CSV',['`canonical_smiles`','`protein_sequence`','For classification: `label`; for regression: `p_activity`'],{
    'blank_dti_dataset.csv':csv_text(DTI_HEADERS),
    'filled_dti_example.csv':csv_text(DTI_HEADERS,DTI_ROWS),
    'expected_dti_output.csv':csv_text(['drug_id','target_id','prediction','confidence','applicability','status'],[['D001','T001',0.82,0.76,'inside','exploratory'],['D002','T002',0.31,0.69,'inside','exploratory']]),
    },notes=['Use `label` values 0/1 for classification.', 'Use numeric `p_activity` for regression.', 'Protein sequences must contain standard amino-acid symbols.'])
add('model_evaluation','Model Evaluation','Held-out labels and prediction probabilities for evaluation.','CSV',['`sample_id`','`y_true`','`y_score` or `y_pred`'],{
'blank_model_evaluation.csv':csv_text(['sample_id','y_true','y_score','split']),
'filled_model_evaluation.csv':csv_text(['sample_id','y_true','y_score','split'],[['S001',1,0.91,'test'],['S002',0,0.18,'test'],['S003',1,0.72,'test'],['S004',0,0.41,'test']]),
'expected_metrics.csv':csv_text(['metric','value'],[['roc_auc',0.94],['balanced_accuracy',0.88],['brier_score',0.12]]),
})
add('external_validation','External Validation & Drift','Independent labelled records for external validation and drift review.','CSV',['Model input feature columns','Ground-truth target column'],{
'blank_external_validation.csv':csv_text(DTI_HEADERS),
'filled_external_validation.csv':csv_text(DTI_HEADERS,DTI_ROWS),
'expected_validation_summary.csv':csv_text(['dataset','rows','performance_metric','performance_value','drift_state'],[['external_example',3,'roc_auc',0.83,'review']]),
})
add('external_databases','Scientific Database Lookup','Offline query list for provider lookup sessions.','CSV',['`query_id`','`provider`','`query_type`','`query_value`'],{
'blank_provider_queries.csv':csv_text(['query_id','provider','query_type','query_value']),
'filled_provider_queries.csv':csv_text(['query_id','provider','query_type','query_value'],[['Q001','UniProt','protein_accession','P00533'],['Q002','PubChem','compound_name','aspirin'],['Q003','RCSB','pdb_id','1M17']]),
'expected_lookup_log.csv':csv_text(['query_id','provider','status','local_cache_path'],[['Q001','UniProt','pending',''],['Q002','PubChem','pending','']]),
})
add('chembl_builder','ChEMBL Dataset Builder','Target and activity filters for reproducible dataset building.','CSV',['`target_id` or `target_name`','Optional activity and organism filters'],{
'blank_chembl_targets.csv':csv_text(['target_id','target_name','organism','activity_type','min_pchembl']),
'filled_chembl_targets.csv':csv_text(['target_id','target_name','organism','activity_type','min_pchembl'],[['CHEMBL203','EGFR','Homo sapiens','IC50',6.0],['CHEMBL279','VEGFR2','Homo sapiens','Ki',6.0]]),
'expected_chembl_dataset.csv':csv_text(['molecule_chembl_id','target_chembl_id','canonical_smiles','standard_type','standard_value','standard_units','pchembl_value'],[['CHEMBL_DEMO_1','CHEMBL203',SMILES[0][2],'IC50',100,'nM',7.0]]),
})
add('dataset_registry','Dataset Registry & Lineage','Dataset registration metadata and provenance.','CSV',['`dataset_name`','`version`','`file_path`','`source`','`licence`'],{
'blank_dataset_registry.csv':csv_text(['dataset_name','version','file_path','source','licence','organism','assay_type','notes']),
'filled_dataset_registry.csv':csv_text(['dataset_name','version','file_path','source','licence','organism','assay_type','notes'],[['example_activity','1.0','data/my_activity.csv','local_lab','internal','Homo sapiens','binding','demo row']]),
'expected_registry_receipt.json':json.dumps({'dataset_id':'generated-after-registration','sha256':'calculated-locally','status':'registered','lineage_edges':0},indent=2),
})
add('batch_jobs','Resumable Batch Jobs','Batch prediction records with stable identifiers.','CSV',['`job_row_id`','Model input columns'],{
'blank_batch_job.csv':csv_text(['job_row_id','drug_id','canonical_smiles','target_id','protein_sequence']),
'filled_batch_job.csv':csv_text(['job_row_id','drug_id','canonical_smiles','target_id','protein_sequence'],[[1,'D001',SMILES[0][2],'T001',COMMON_PROTEIN],[2,'D002',SMILES[1][2],'T002',COMMON_PROTEIN_2]]),
'expected_batch_job_results.csv':csv_text(['job_row_id','status','prediction','error'],[[1,'completed',0.82,''],[2,'completed',0.31,'']]),
})
add('appearance','Appearance Studio','Portable local UI preference profile.','JSON',['Valid JSON object','Theme and font names available in the installed app'],{
'blank_ui_preferences.json':json.dumps({'palette':'Genomic Noir','font_family':'Inter','appearance_mode':'Dark','compact':False,'reduce_motion':False},indent=2),
'filled_ui_preferences_example.json':json.dumps({'palette':'CRISPR Cyan','font_family':'Inter','heading_font_family':'Space Grotesk','data_font_family':'JetBrains Mono','appearance_mode':'Dark','compact':False,'reduce_motion':True,'high_contrast':False,'font_scale':1.0},indent=2),
'expected_import_receipt.json':json.dumps({'status':'preferences_imported','restart_required':False},indent=2),
})
add('project_portfolio','Project Portfolio','Controlled project bundle for offline project import.','JSON',['`project_name`','`status`','`milestones`','`tasks`'],{
'blank_project_bundle.json':json.dumps({'project_name':'','description':'','status':'planned','milestones':[],'tasks':[],'resources':[]},indent=2),
'filled_project_bundle.json':json.dumps({'project_name':'EGFR discovery pilot','description':'Synthetic planning example','status':'active','milestones':[{'name':'Data QC','status':'complete'}],'tasks':[{'name':'Run feature audit','status':'open'}],'resources':[]},indent=2),
'expected_project_import.json':json.dumps({'status':'imported','project_id':'generated-locally','warnings':[]},indent=2),
})
add('evidence_studio','Evidence Package Studio','Evidence-package manifest and a minimal package layout.','ZIP or JSON',['`manifest.json` inside the ZIP','Checksum-bound evidence file entries'],{
'blank_evidence_manifest.json':json.dumps({'package_name':'','created_at_utc':'','files':[],'claims':[],'limitations':[]},indent=2),
'filled_evidence_manifest.json':json.dumps({'package_name':'demo_evidence_package','created_at_utc':'2026-01-01T00:00:00Z','files':[{'path':'results.csv','sha256':'replace-with-real-sha256'}],'claims':['Software workflow demonstration only'],'limitations':['Synthetic example']},indent=2),
'expected_verification_receipt.json':json.dumps({'integrity':'passed','file_count':1,'claim_count':1,'release_eligible':False},indent=2),
})
add('report_studio','Research Report Studio','Structured report metadata and findings.','CSV or JSON',['Study title and context','Findings, limitations and recommendations'],{
'blank_report_findings.csv':csv_text(['section','finding','confidence','limitation','recommendation']),
'filled_report_findings.csv':csv_text(['section','finding','confidence','limitation','recommendation'],[['Sequence QC','Mean read quality passed the demo threshold','medium','Synthetic reads','Validate on instrument data']]),
'report_metadata.json':json.dumps({'title':'Example BioIntel Report','project':'Demo','author':'','date':'','research_use_only':True},indent=2),
'expected_report_bundle_manifest.json':json.dumps({'status':'ready','formats':['html','json','docx','csv'],'findings':1,'limitations':1},indent=2),
})
add('scientific_curation','Scientific Data Curation','Activity records with provenance and units.','CSV or TSV',['`compound_id`','`target_id`','`activity_type`','`activity_value`','`activity_unit`','`source`'],{
'blank_activity_curation.csv':csv_text(['compound_id','target_id','activity_type','activity_value','activity_unit','organism','assay_id','source','source_record_id']),
'filled_activity_curation.csv':csv_text(['compound_id','target_id','activity_type','activity_value','activity_unit','organism','assay_id','source','source_record_id'],[['D001','EGFR','IC50',120,'nM','Homo sapiens','ASSAY001','local_demo','REC001']]),
'expected_curated_activity.csv':csv_text(['compound_id','target_id','standard_value_nM','p_activity','qc_state'],[['D001','EGFR',120,6.92,'reviewed']]),
})
add('scientific_release_gate','Scientific Release Gate','Release evidence JSONs for validation, leakage and provenance gates.','JSON',['Validation metrics','Leakage/split audit','Evidence manifest'],{
'blank_external_validation.json':json.dumps({'dataset_id':'','metrics':{},'independent':False,'notes':''},indent=2),
'blank_split_audit.json':json.dumps({'split_strategy':'','duplicate_pairs':0,'scaffold_overlap_percent':0.0,'target_overlap_percent':0.0},indent=2),
'blank_evidence_manifest.json':json.dumps({'artifacts':[],'checksums_verified':False,'limitations':[]},indent=2),
'filled_release_evidence_example.json':json.dumps({'dataset_id':'demo_external','metrics':{'roc_auc':0.82},'independent':False,'notes':'Synthetic example only'},indent=2),
'expected_release_decision.json':json.dumps({'decision':'blocked','blockers':['Replace blank templates with real evidence'],'reviewer_required':True},indent=2),
})
add('real_evidence_studio','Real Evidence Studio','Evidence rows with source, assay context and review state.','CSV, TSV or TXT',['`source`','`source_record_id`','`claim`','`evidence_type`'],{
'blank_evidence_records.csv':csv_text(['source','source_record_id','claim','evidence_type','organism','assay_type','review_state','notes']),
'filled_evidence_records.csv':csv_text(['source','source_record_id','claim','evidence_type','organism','assay_type','review_state','notes'],[['local_demo','REC001','Example compound activity','assay','Homo sapiens','binding','needs_review','Synthetic example']]),
'expected_review_queue.csv':csv_text(['source_record_id','review_state','blocking_issue'],[['REC001','needs_review','Source verification required']]),
})
add('benchmark_leakage_lab','Benchmark & Leakage Lab','Separate train and independent benchmark tables.','CSV',['Identical feature columns across both files','Target label column'],{
'blank_training.csv':csv_text(DTI_HEADERS),
'blank_independent_test.csv':csv_text(DTI_HEADERS),
'filled_training_example.csv':csv_text(DTI_HEADERS,DTI_ROWS[:2]),
'filled_independent_test_example.csv':csv_text(DTI_HEADERS,DTI_ROWS[2:]),
'expected_leakage_audit.csv':csv_text(['check','value','status'],[['exact_pair_overlap',0,'pass'],['drug_overlap_percent',33.3,'review']]),
})
add('document_intelligence','Document Intelligence Center','Small local documents covering supported text and table formats.','PDF, DOCX, XLSX, CSV, TSV, TXT, MD, HTML, JSON, XML or YAML',['A supported local document','No executable or active content'],{
'blank_document_notes.md':'# Study title\n\n## Objective\n\n## Methods\n\n## Results\n\n## Limitations\n',
'filled_document_example.md':'# Synthetic EGFR Study Note\n\n## Objective\nDemonstrate local document extraction.\n\n## Result\nNo scientific claim is made.\n',
'filled_table_example.csv':csv_text(['sample','measurement','unit'],[['S001',1.24,'a.u.'],['S002',1.31,'a.u.']]),
'filled_metadata_example.json':json.dumps({'document_type':'study_note','synthetic':True,'tags':['EGFR','demo']},indent=2),
'expected_extraction.json':json.dumps({'blocks':[{'type':'heading','text':'Synthetic EGFR Study Note'},{'type':'paragraph','text':'Demonstrate local document extraction.'}],'tables':1},indent=2),
})
add('ocr_layout_review','OCR & Layout Review','OCR correction queue template.','CSV',['`page`','`block_id`','`original_text`','`corrected_text`'],{
'blank_ocr_corrections.csv':csv_text(['page','block_id','original_text','corrected_text','reviewer','status']),
'filled_ocr_corrections.csv':csv_text(['page','block_id','original_text','corrected_text','reviewer','status'],[[1,'B001','prote1n','protein','','pending']]),
'expected_ocr_review.csv':csv_text(['block_id','status','accepted_text'],[['B001','approved','protein']]),
})
add('batch_document_processor','Batch Document Processor','Multiple safe local document examples plus a processing manifest.','CSV, TXT, MD, HTML or JSON',['One or more supported documents','Optional document manifest'],{
'document_01.md':'# Demo document 01\nSynthetic local document for batch extraction.\n',
'document_02.txt':'Demo document 02\nNo clinical or scientific claim.\n',
'document_03.csv':csv_text(['entity','value'],[['gene','EGFR'],['compound','aspirin']]),
'blank_batch_manifest.csv':csv_text(['filename','document_type','project_id']),
'filled_batch_manifest.csv':csv_text(['filename','document_type','project_id'],[['document_01.md','study_note','DEMO'],['document_02.txt','plain_text','DEMO'],['document_03.csv','table','DEMO']]),
'expected_batch_status.csv':csv_text(['filename','status','blocks','tables'],[['document_01.md','completed',2,0],['document_03.csv','completed',1,1]]),
})
add('document_evidence_bridge','Document Evidence Bridge','Document-to-evidence link mapping.','CSV',['`document_id`','`block_id`','`evidence_id`','`relationship`'],{
'blank_document_evidence_links.csv':csv_text(['document_id','block_id','evidence_id','relationship','review_state']),
'filled_document_evidence_links.csv':csv_text(['document_id','block_id','evidence_id','relationship','review_state'],[['DOC001','B001','EVID001','supports','needs_review']]),
'expected_bridge_summary.csv':csv_text(['document_id','linked_evidence_count','approved_count'],[['DOC001',1,0]]),
})
add('local_data','Local Data Manager','Portable local data-import manifest.','CSV',['`relative_path`','`asset_type`','`description`'],{
'blank_local_asset_manifest.csv':csv_text(['relative_path','asset_type','description','source','licence']),
'filled_local_asset_manifest.csv':csv_text(['relative_path','asset_type','description','source','licence'],[['data/my_sequences.fasta','sequence','Local sequence panel','local','internal']]),
'expected_import_summary.json':json.dumps({'discovered':1,'accepted':1,'rejected':0},indent=2),
})
# Bioinformatics and lab kits
add('fastq_genomics_qc','FASTQ & Genome QC','Small single-end, paired-end and assembly examples.','FASTQ, FASTQ.GZ and FASTA',['FASTQ records contain identifier, sequence, separator and quality lines','Paired files use matching read identifiers'],{
'blank_reads.fastq':'@read_001\nACGTACGT\n+\nIIIIIIII\n',
'filled_reads_R1.fastq':'@demo_read_001/1\nACGTACGTACGTACGT\n+\nIIIIIIIIIIIIIIII\n@demo_read_002/1\nGGCCTTAAGGCCTTAA\n+\nHHHHHHHHHHHHHHHH\n',
'filled_reads_R2.fastq':'@demo_read_001/2\nTGCATGCATGCATGCA\n+\nIIIIIIIIIIIIIIII\n@demo_read_002/2\nTTAAGGCCTTAAGGCC\n+\nHHHHHHHHHHHHHHHH\n',
'filled_assembly.fasta':f'>contig_001\n{COMMON_DNA * 2}\n',
'expected_fastq_qc.csv':csv_text(['file','reads','mean_length','mean_quality','gc_percent','status'],[['filled_reads_R1.fastq',2,16,39.5,50.0,'pass']]),
})
add('variant_annotation','Variant & Annotation Workbench','Matching VCF, reference FASTA and GFF3 examples.','VCF, VCF.GZ, FASTA, GFF3 or GTF',['VCF columns follow VCF specification','Reference contig names match VCF and GFF3'],{
'blank_variants.vcf':'##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n',
'filled_variants.vcf':'##fileformat=VCFv4.2\n##contig=<ID=chrDemo,length=156>\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\nchrDemo\t10\tvar1\tT\tC\t60\tPASS\tDP=42\n',
'filled_reference.fasta':f'>chrDemo\n{COMMON_DNA * 2}\n',
'filled_annotations.gff3':'##gff-version 3\nchrDemo\tBioIntel\tgene\t1\t120\t.\t+\t.\tID=gene1;Name=DEMO1\nchrDemo\tBioIntel\tCDS\t1\t90\t.\t+\t0\tID=cds1;Parent=gene1\n',
'expected_variant_annotations.csv':csv_text(['chrom','pos','ref','alt','gene','consequence','qc_state'],[['chrDemo',10,'T','C','DEMO1','coding_variant','review']]),
})
add('primer_crispr_codon','Primer, CRISPR & Codon Studio','Target sequence plus optional design-region table.','FASTA or CSV',['A validated target nucleotide sequence','Optional 0-based design start/end coordinates'],{
'blank_target.fasta':'>target_id\nTARGET_DNA_SEQUENCE_HERE\n',
'filled_target.fasta':f'>demo_target\n{COMMON_DNA * 3}\n',
'blank_design_regions.csv':csv_text(['target_id','start_0_based','end_exclusive','design_type']),
'filled_design_regions.csv':csv_text(['target_id','start_0_based','end_exclusive','design_type'],[['demo_target',10,120,'primer'],['demo_target',25,95,'crispr']]),
'expected_design_candidates.csv':csv_text(['candidate_id','type','sequence','start','end','score','warning'],[['P001','forward_primer','CGTTAGCTAGCTACGATCGA',8,28,0.84,'demo only']]),
})
add('transcriptomics_expression','Transcriptomics Expression Lab','Gene-count matrix and editable sample metadata.','CSV or TSV',['First column is a gene identifier','Remaining columns are samples','Metadata contains `sample` and `group`'],{
'blank_gene_counts.csv':csv_text(['gene_id','sample_01','sample_02','sample_03','sample_04']),
'filled_gene_counts.csv':csv_text(['gene_id','CTRL_01','CTRL_02','TRT_01','TRT_02'],[['EGFR',120,130,240,255],['TP53',85,80,79,76],['GAPDH',1000,980,1020,995]]),
'blank_sample_metadata.csv':csv_text(['sample','group','batch','condition']),
'filled_sample_metadata.csv':csv_text(['sample','group','batch','condition'],[['CTRL_01','control','B1','vehicle'],['CTRL_02','control','B1','vehicle'],['TRT_01','treated','B1','compound'],['TRT_02','treated','B1','compound']]),
'expected_differential_expression.csv':csv_text(['gene_id','log2_fold_change','p_value','adjusted_p_value','status'],[['EGFR',0.98,0.004,0.012,'significant']]),
})
add('protein_annotation','Protein Annotation & Proteomics','Protein FASTA plus long-format intensity data.','FASTA, FAA, CSV or TSV',['Unique protein identifiers','Proteomics table includes protein, sample and intensity'],{
'blank_proteins.fasta':'>protein_id\nAMINO_ACID_SEQUENCE_HERE\n',
'filled_proteins.fasta':f'>PROT001 demo_protein\n{COMMON_PROTEIN}\n>PROT002 demo_protein_2\n{COMMON_PROTEIN_2}\n',
'blank_protein_intensity.csv':csv_text(['protein','sample','intensity','group','batch']),
'filled_protein_intensity.csv':csv_text(['protein','sample','intensity','group','batch'],[['PROT001','CTRL_01',12000,'control','B1'],['PROT001','TRT_01',18000,'treated','B1'],['PROT002','CTRL_01',9000,'control','B1']]),
'expected_protein_summary.csv':csv_text(['protein','length','mean_intensity','fold_change','qc_state'],[['PROT001',len(COMMON_PROTEIN),15000,1.5,'review']]),
})
PDB='''HEADER    DEMO STRUCTURE\nATOM      1  N   ALA A   1      11.104  13.207   9.421  1.00 20.00           N\nATOM      2  CA  ALA A   1      12.560  13.300   9.215  1.00 20.00           C\nATOM      3  C   ALA A   1      13.192  12.002   8.725  1.00 20.00           C\nATOM      4  O   ALA A   1      12.596  10.927   8.835  1.00 20.00           O\nTER\nEND\n'''
add('structural_bioinformatics','Structural Bioinformatics','Small valid PDB example and residue-selection table.','PDB, CIF or mmCIF',['Atomic coordinate records','Valid chain and residue identifiers'],{
'blank_structure_notes.csv':csv_text(['structure_id','chain','residue_start','residue_end','label']),
'filled_structure.pdb':PDB,
'filled_structure_notes.csv':csv_text(['structure_id','chain','residue_start','residue_end','label'],[['demo_structure','A',1,1,'demo_site']]),
'expected_structure_summary.csv':csv_text(['structure_id','chains','residues','atoms','qc_state'],[['demo_structure',1,1,4,'valid_demo']]),
})
add('admet_discovery','ADMET Triage & Developability','Batch compound library for rule-based developability triage.','CSV',['`compound_id` or `name`','`smiles`'],{
'blank_admet_compounds.csv':csv_text(['compound_id','name','smiles','assay_ph']),
'filled_admet_compounds.csv':csv_text(['compound_id','name','smiles','assay_ph'],[[a,b,c,7.4] for a,b,c in SMILES]),
'expected_admet_triage.csv':csv_text(['compound_id','developability_score','risk_level','applicability','critical_blockers'],[['CMPD001',78,'medium','inside',''],['CMPD002',71,'medium','inside','']]),
})
add('pathway_network','Pathway & Network Analysis','Ranked gene list and optional GMT pathway collection.','CSV, TSV, GMT or TXT',['Gene list contains identifier and ranking score','GMT lines use pathway, description and genes'],{
'blank_ranked_genes.csv':csv_text(['gene','score','p_value']),
'filled_ranked_genes.csv':csv_text(['gene','score','p_value'],[['EGFR',2.4,0.001],['AKT1',1.9,0.006],['TP53',-1.5,0.02],['MAPK1',1.2,0.04]]),
'blank_pathways.gmt':'PATHWAY_NAME\tdescription\tGENE1\tGENE2\n',
'filled_pathways.gmt':'EGFR_SIGNALING\tSynthetic pathway\tEGFR\tAKT1\tMAPK1\nDNA_DAMAGE\tSynthetic pathway\tTP53\tATM\tBRCA1\n',
'expected_pathway_results.csv':csv_text(['pathway','enrichment_score','p_value','adjusted_p_value','leading_genes'],[['EGFR_SIGNALING',2.1,0.006,0.018,'EGFR;AKT1;MAPK1']]),
})
# Wet-lab comprehensive bundle
add('wetlab_biotechnology','Wet-Lab Biotechnology','qPCR, ELISA, enzyme-kinetics and bioprocess local templates.','CSV, TSV or Excel-compatible CSV',['Use the specific file matching the selected assay tab','Keep units and control roles explicit'],{
'blank_qpcr.csv':csv_text(['sample','target_ct','reference_ct','group','role']),
'filled_qpcr.csv':csv_text(['sample','target_ct','reference_ct','group','role'],[['CTRL_1',25.1,19.8,'control','target'],['CTRL_2',25.4,20.0,'control','target'],['TRT_1',23.0,19.7,'treated','target'],['NTC','','','control','NTC']]),
'blank_qpcr_long.csv':csv_text(['sample','gene','ct','target','group','role']),
'filled_qpcr_long.csv':csv_text(['sample','gene','ct','target','group','role'],[['CTRL_1','EGFR',25.1,True,'control','Target'],['CTRL_1','GAPDH',19.8,False,'control','Reference'],['TRT_1','EGFR',23.0,True,'treated','Target'],['TRT_1','GAPDH',19.7,False,'treated','Reference']]),
'blank_elisa.csv':csv_text(['well','sample_id','sample_type','concentration','response','dilution']),
'filled_elisa.csv':csv_text(['well','sample_id','sample_type','concentration','response','dilution'],[['A1','STD_0','standard',0,0.05,1],['A2','STD_1','standard',1,0.18,1],['A3','STD_2','standard',10,0.72,1],['A4','STD_3','standard',100,1.42,1],['B1','UNKNOWN_1','unknown','',0.66,2]]),
'blank_enzyme_kinetics.csv':csv_text(['substrate_concentration','initial_rate','inhibitor_concentration','replicate','unit']),
'filled_enzyme_kinetics.csv':csv_text(['substrate_concentration','initial_rate','inhibitor_concentration','replicate','unit'],[[0.5,0.20,0,'R1','uM/min'],[1,0.34,0,'R1','uM/min'],[2,0.52,0,'R1','uM/min'],[5,0.73,0,'R1','uM/min']]),
'blank_bioprocess.csv':csv_text(['batch','time_h','biomass_g_L','substrate_g_L','product_g_L','volume_L']),
'filled_bioprocess.csv':csv_text(['batch','time_h','biomass_g_L','substrate_g_L','product_g_L','volume_L'],[['B1',0,0.2,20,0,1.0],['B1',4,0.8,15,0.1,1.0],['B1',8,2.1,8,0.8,1.0],['B2',0,0.2,20,0,1.0],['B2',4,0.7,16,0.1,1.0]]),
'expected_assay_summary.csv':csv_text(['assay','metric','value','qc_state'],[['qPCR','relative_expression',2.1,'review'],['ELISA','unknown_concentration',8.4,'inside_range'],['Enzyme','Vmax',0.92,'demo']]),
})
add('microbiology_metagenomics','Microbiology & Metagenomics','Taxon abundance and matching sample metadata.','CSV or TSV',['First column is taxon','Remaining columns match metadata sample values'],{
'blank_taxon_abundance.csv':csv_text(['taxon','sample_01','sample_02','sample_03']),
'filled_taxon_abundance.csv':csv_text(['taxon','S01','S02','S03'],[['Bacteroides',120,95,40],['Faecalibacterium',80,75,20],['Escherichia',5,8,55]]),
'blank_microbiome_metadata.csv':csv_text(['sample','group','batch','subject']),
'filled_microbiome_metadata.csv':csv_text(['sample','group','batch','subject'],[['S01','control','B1','P01'],['S02','control','B1','P02'],['S03','case','B1','P03']]),
'expected_diversity.csv':csv_text(['sample','shannon','observed_taxa','group'],[['S01',0.78,3,'control'],['S03',0.93,3,'case']]),
})
add('omics_integration','Omics Integration Hub','Matched transcriptomics, proteomics and optional metabolomics matrices.','CSV or TSV',['First column is feature identifier','Sample columns match across omics files'],{
'blank_transcriptomics.csv':csv_text(['feature_id','S01','S02','S03']),
'filled_transcriptomics.csv':csv_text(['feature_id','S01','S02','S03'],[['EGFR',5.2,5.5,7.1],['AKT1',4.1,4.0,5.3]]),
'blank_proteomics.csv':csv_text(['feature_id','S01','S02','S03']),
'filled_proteomics.csv':csv_text(['feature_id','S01','S02','S03'],[['EGFR',10.2,10.6,12.1],['AKT1',8.3,8.1,9.0]]),
'filled_metabolomics.csv':csv_text(['feature_id','S01','S02','S03'],[['Lactate',1.2,1.3,2.1],['Glucose',4.9,4.8,3.7]]),
'expected_integration.csv':csv_text(['feature_id','cross_omics_score','supporting_layers','status'],[['EGFR',0.88,2,'concordant']]),
})
add('alignment_phylogeny','Alignment & Phylogeny','Homologous FASTA sequences and expected tree text.','FASTA, FA, ALN or Newick',['Two or more homologous sequences with unique identifiers'],{
'blank_homologs.fasta':'>taxon_1\nSEQUENCE_HERE\n>taxon_2\nSEQUENCE_HERE\n',
'filled_homologs.fasta':f'>isolate_A\n{COMMON_DNA}\n>isolate_B\n{COMMON_DNA_2}\n>isolate_C\n{COMMON_DNA[:-4]}TTAA\n',
'expected_tree.newick':'((isolate_A:0.01,isolate_B:0.02):0.01,isolate_C:0.03);\n',
'expected_distance_matrix.csv':csv_text(['taxon','isolate_A','isolate_B','isolate_C'],[['isolate_A',0,0.026,0.039],['isolate_B',0.026,0,0.052],['isolate_C',0.039,0.052,0]]),
})
add('ppi_interaction_ml','Protein Interaction ML','Labelled and candidate protein-pair tables.','CSV',['`protein_a`','`protein_b`','`sequence_a`','`sequence_b`','Training file also needs `label`'],{
'blank_ppi_training.csv':csv_text(['protein_a','protein_b','sequence_a','sequence_b','label']),
'filled_ppi_training.csv':csv_text(['protein_a','protein_b','sequence_a','sequence_b','label'],[['P001','P002',COMMON_PROTEIN,COMMON_PROTEIN_2,1],['P001','P003',COMMON_PROTEIN,'MALWMRLLPLLALLALWGPGPG',0]]),
'blank_ppi_candidates.csv':csv_text(['protein_a','protein_b','sequence_a','sequence_b']),
'filled_ppi_candidates.csv':csv_text(['protein_a','protein_b','sequence_a','sequence_b'],[['P002','P003',COMMON_PROTEIN_2,'MALWMRLLPLLALLALWGPGPG']]),
'expected_ppi_predictions.csv':csv_text(['protein_a','protein_b','interaction_probability','applicability'],[['P002','P003',0.64,'inside']]),
})
add('comparative_pathogen_genomics','Comparative Pathogen Genomics','Query and reference genome FASTA panels.','FASTA, FA or FNA',['Query contigs/genomes','Reference records with stable identifiers'],{
'blank_query_genome.fasta':'>query_genome\nGENOME_SEQUENCE_HERE\n',
'filled_query_genome.fasta':f'>query_isolate\n{COMMON_DNA * 4}\n',
'blank_reference_panel.fasta':'>reference_1\nREFERENCE_SEQUENCE_HERE\n',
'filled_reference_panel.fasta':f'>reference_A\n{COMMON_DNA * 4}\n>reference_B\n{COMMON_DNA_2 * 4}\n',
'expected_assignment.csv':csv_text(['query_id','best_reference','identity_percent','coverage_percent','bootstrap_support_percent'],[['query_isolate','reference_A',99.2,100,94]]),
})
add('single_cell_heterogeneity','Single-Cell Heterogeneity','Genes-by-cells matrix and cell metadata.','CSV, TSV, 10x ZIP or H5AD',['First column is gene','Remaining columns are cell identifiers','Metadata contains `cell`'],{
'blank_single_cell_counts.csv':csv_text(['gene','cell_001','cell_002','cell_003']),
'filled_single_cell_counts.csv':csv_text(['gene','C001','C002','C003','C004'],[['CD3D',8,7,0,0],['MS4A1',0,0,9,8],['MALAT1',20,22,19,21],['EGFR',1,0,3,4]]),
'blank_cell_metadata.csv':csv_text(['cell','sample','batch','condition','donor']),
'filled_cell_metadata.csv':csv_text(['cell','sample','batch','condition','donor'],[['C001','S01','B1','control','D01'],['C002','S01','B1','control','D01'],['C003','S02','B1','treated','D02'],['C004','S02','B1','treated','D02']]),
'expected_cell_clusters.csv':csv_text(['cell','cluster','cell_type_candidate','qc_state'],[['C001',0,'T-cell-like','review'],['C003',1,'B-cell-like','review']]),
})
add('cancer_genomics','Cancer Genomics','Somatic variants plus optional metadata, CNV, SV and callable territory.','CSV, TSV or MAF',['Variant table includes chromosome, position, ref, alt, gene and sample'],{
'blank_somatic_variants.csv':csv_text(['sample','chromosome','position','ref','alt','gene','consequence','vaf','depth','protein_change','filter']),
'filled_somatic_variants.csv':csv_text(['sample','chromosome','position','ref','alt','gene','consequence','vaf','depth','protein_change','filter'],[['TUMOR01','7',55249071,'C','T','EGFR','missense_variant',0.34,180,'p.L858R','PASS']]),
'blank_cancer_metadata.csv':csv_text(['sample','cohort','tumor_type','batch','timepoint']),
'filled_cancer_metadata.csv':csv_text(['sample','cohort','tumor_type','batch','timepoint'],[['TUMOR01','demo','lung','B1','baseline']]),
'blank_cnv_segments.csv':csv_text(['sample','chromosome','start','end','log2_ratio','copy_number']),
'filled_cnv_segments.csv':csv_text(['sample','chromosome','start','end','log2_ratio','copy_number'],[['TUMOR01','7',55000000,56000000,1.2,6]]),
'blank_sv_fusions.csv':csv_text(['sample','event_type','gene_1','gene_2','support']),
'filled_sv_fusions.csv':csv_text(['sample','event_type','gene_1','gene_2','support'],[['TUMOR01','fusion','EML4','ALK',42]]),
'blank_callable_territory.csv':csv_text(['sample','callable_megabases']),
'expected_cancer_summary.csv':csv_text(['sample','actionable_candidates','tmb_per_mb','cnv_events','sv_events'],[['TUMOR01',1,0.03,1,1]]),
})
add('metagenomics_pipeline','Metagenomics Pipeline','Abundance, metadata, function profile and Newick tree bundle.','CSV, TSV, NWK or Newick',['Abundance first column is taxon','Metadata includes sample and group','Functional sample columns match metadata'],{
'blank_taxon_abundance.csv':csv_text(['taxon','S01','S02','S03']),
'filled_taxon_abundance.csv':csv_text(['taxon','S01','S02','S03'],[['Taxon_A',100,80,20],['Taxon_B',30,35,90],['Taxon_C',5,8,15]]),
'blank_sample_metadata.csv':csv_text(['sample','group','batch','site','subject','timepoint']),
'filled_sample_metadata.csv':csv_text(['sample','group','batch','site','subject','timepoint'],[['S01','control','B1','gut','P01','T0'],['S02','control','B1','gut','P02','T0'],['S03','case','B1','gut','P03','T0']]),
'blank_functional_profile.csv':csv_text(['feature','pathway','S01','S02','S03']),
'filled_functional_profile.csv':csv_text(['feature','pathway','S01','S02','S03'],[['K00001','Glycolysis',50,48,62],['K00002','TCA cycle',22,25,30]]),
'filled_phylogenetic_tree.nwk':'((Taxon_A:0.1,Taxon_B:0.1):0.2,Taxon_C:0.3);\n',
'expected_metagenomics_results.csv':csv_text(['analysis','feature','effect','adjusted_p_value','status'],[['differential_abundance','Taxon_B',1.8,0.04,'screening']]),
})
add('discovery_command_center','Discovery Command Center','Target-evidence scoring input.','CSV',['`dimension`','`score`','Optional confidence and source fields'],{
'blank_target_evidence.csv':csv_text(['dimension','score','confidence','source_type','source','source_id','evidence_date','notes']),
'filled_target_evidence.csv':csv_text(['dimension','score','confidence','source_type','source','source_id','evidence_date','notes'],[['genetic_support',0.82,0.75,'publication','local_demo','EVID001','2026-01-01','Synthetic example'],['tractability',0.68,0.70,'structure','local_demo','PDB_DEMO','2026-01-01','Synthetic example']]),
'expected_target_priority.csv':csv_text(['target','priority_score','evidence_dimensions','confidence','status'],[['EGFR',0.75,2,0.72,'review']]),
})
add('connected_data_explorer','Connected Data Explorer','Provider/entity query manifest for repeatable exploration.','CSV or JSON',['Provider name','Entity type','Identifier or query'],{
'blank_connected_queries.csv':csv_text(['query_id','provider','entity_type','identifier','fields']),
'filled_connected_queries.csv':csv_text(['query_id','provider','entity_type','identifier','fields'],[['Q001','UniProt','protein','P00533','name;sequence;organism'],['Q002','PubChem','compound','aspirin','cid;canonical_smiles']]),
'expected_connected_results.csv':csv_text(['query_id','status','records','cache_state'],[['Q001','ready',1,'local']]),
})
add('provider_integration_center','Provider Integration Center','Safe provider configuration without secrets.','JSON',['Provider name and base URL','No passwords or API secrets in shared files'],{
'blank_provider_profile.json':json.dumps({'provider_name':'','base_url':'','enabled':False,'timeout_seconds':30,'rate_limit_per_minute':30,'licence_note':'','api_key_env_var':''},indent=2),
'filled_provider_profile_example.json':json.dumps({'provider_name':'Example Provider','base_url':'https://example.invalid/api','enabled':False,'timeout_seconds':30,'rate_limit_per_minute':30,'licence_note':'Replace with official provider terms','api_key_env_var':'BIOINTEL_EXAMPLE_API_KEY'},indent=2),
'expected_connection_test.json':json.dumps({'provider_name':'Example Provider','status':'disabled','records_checked':0},indent=2),
},notes=['Do not write actual API keys inside this file.', 'Use environment-variable names in `api_key_env_var`.', 'The example URL is intentionally non-routable.'])

catalog = {'version':'1.0','root':'data/module_starter_kits','kit_count':len(kits),'kits':{}}
for key, spec in sorted(kits.items()):
    folder = OUT / key
    folder.mkdir(parents=True)
    files = dict(spec['files'])
    files['FORMAT_GUIDE.md'] = guide(spec['title'], spec['accepted'], spec['required'], spec['notes'])
    entries=[]
    for name, content in files.items():
        path=folder/name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(str(content), encoding='utf-8', newline='')
        role = 'guide' if name == 'FORMAT_GUIDE.md' else ('blank' if name.startswith('blank_') else ('output' if name.startswith('expected_') else 'example'))
        entries.append({'name':name,'role':role,'size_bytes':path.stat().st_size})
    manifest={
        'module_key':key,
        'title':spec['title'],
        'description':spec['description'],
        'accepted_formats':spec['accepted'],
        'offline':True,
        'synthetic_example':True,
        'files':entries,
    }
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    entries.append({'name':'manifest.json','role':'manifest','size_bytes':(folder/'manifest.json').stat().st_size})
    zip_name=f'{key}_starter_kit.zip'
    zip_path=folder/zip_name
    with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zf:
        for entry in sorted(entries,key=lambda item:item['name']):
            zf.write(folder/entry['name'],arcname=entry['name'])
    catalog['kits'][key]={
        'title':spec['title'],
        'description':spec['description'],
        'accepted_formats':spec['accepted'],
        'directory':key,
        'zip':zip_name,
        'files':entries,
    }

(OUT/'catalog.json').write_text(json.dumps(catalog,indent=2),encoding='utf-8')
(OUT/'README.md').write_text(textwrap.dedent(f'''\
# BioIntel AI — Module Data Starter Kits

This offline library contains **{len(kits)} module-specific starter kits**.

Each kit includes:

- blank input template(s)
- filled synthetic example(s)
- expected output example(s)
- `FORMAT_GUIDE.md`
- `manifest.json`
- a complete module ZIP

Open a supported module in BioIntel AI and use the **Local Data Starter Kit** section in the sidebar.

All examples are synthetic and must not be treated as clinical, regulatory or experimental evidence.
'''),encoding='utf-8')

bat = ROOT / 'OPEN_MODULE_STARTER_KITS_WINDOWS.bat'
bat.write_text('@echo off\r\nset "ROOT=%~dp0"\r\nstart "" "%ROOT%data\\module_starter_kits"\r\n',encoding='utf-8',newline='')
print(json.dumps({'kit_count':len(kits),'catalog':str(OUT/'catalog.json'),'files':sum(1 for p in OUT.rglob('*') if p.is_file())},indent=2))
