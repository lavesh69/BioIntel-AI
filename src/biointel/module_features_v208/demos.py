from __future__ import annotations

import numpy as np
import pandas as pd


def demo_payload(feature_key: str, *, seed: int = 208):
    rng = np.random.default_rng(seed)
    if feature_key == "advanced_eeg_meg":
        fs = 128.0
        time = np.arange(0, 20, 1 / fs)
        frame = pd.DataFrame({
            "time": time,
            "Fz": np.sin(2*np.pi*10*time) + 0.2*rng.normal(size=len(time)),
            "Cz": 0.7*np.sin(2*np.pi*6*time + 0.2) + 0.2*rng.normal(size=len(time)),
            "Pz": 0.5*np.sin(2*np.pi*20*time) + 0.2*rng.normal(size=len(time)),
        })
        frame.loc[800:805, "Fz"] += 8
        return {"data": frame, "sampling_rate": fs, "time_col": "time"}
    if feature_key == "advanced_neuroimaging":
        x, y, z = np.mgrid[-1:1:32j, -1:1:32j, -1:1:24j]
        volume = np.exp(-4*(x*x+y*y+z*z)) + 0.08*rng.normal(size=x.shape)
        volume[(x-0.25)**2 + (y+0.1)**2 + z**2 < 0.06] += 1.5
        atlas = np.zeros_like(volume, dtype=int)
        atlas[x < 0] = 1
        atlas[x >= 0] = 2
        return {"volume": volume, "voxel_spacing_mm": (1.2, 1.2, 1.5), "atlas": atlas}
    if feature_key == "advanced_neurogenetics":
        return pd.DataFrame({
            "chrom": ["chr1", "2", "X", "MT"],
            "pos": [10101, 20202, 30303, 404],
            "ref": ["A", "G", "C", "T"],
            "alt": ["G", "A,T", "T", "C"],
            "gene": ["SCN2A", "LRRK2", "MECP2", "MT-ND1"],
            "consequence": ["missense_variant", "frameshift_variant", "splice_donor_variant", "missense_variant"],
            "gnomad_af": [0.0001, 0.0, 0.00001, 0.002],
            "clinvar": ["uncertain significance", "pathogenic", "pathogenic", "conflicting"],
            "hpo": ["seizure", "parkinsonism", "developmental delay", "mitochondrial disease"],
            "inheritance": ["de novo", "dominant", "x-linked", "maternal"],
            "genome_build": ["GRCh38"]*4,
        })
    if feature_key == "advanced_expression_atlas":
        genes = ["GRIN2B", "SCN2A", "LRRK2"]
        regions = ["cortex", "hippocampus", "striatum"]
        cells = ["neuron", "astrocyte", "microglia"]
        rows = []
        for gene in genes:
            for region in regions:
                for cell in cells:
                    for condition in ["control", "disease"]:
                        base = 1 + genes.index(gene)*0.4 + regions.index(region)*0.2 + cells.index(cell)*0.3
                        rows.append({"gene": gene, "region": region, "cell_type": cell, "condition": condition, "expression": max(0, base + (0.5 if condition == "disease" and cell == "microglia" else 0) + rng.normal(0,0.1)), "dataset": "Synthetic Neuro Atlas", "dataset_version": "demo-1", "license": "synthetic", "source": "BioIntel generated demo"})
        return pd.DataFrame(rows)
    if feature_key == "advanced_neuro_omics":
        n = 80
        y = np.array([0]*(n//2)+[1]*(n//2))
        data = {"sample_id": [f"S{i+1}" for i in range(n)], "group": np.where(y, "condition", "control")}
        for j in range(20):
            data[f"marker_{j+1}"] = rng.normal(y*(0.8 if j < 4 else 0.1), 1, n)
        return pd.DataFrame(data)
    if feature_key == "advanced_precision_neurology":
        n = 75
        cluster = np.repeat([0,1,2], 25)
        return pd.DataFrame({"subject_id": [f"N{i+1}" for i in range(n)], **{f"feature_{j+1}": rng.normal(cluster*(0.7 if j<3 else -0.4), 0.6, n) for j in range(8)}})
    if feature_key == "advanced_neuro_pk":
        return {"dose_mg": 50.0, "dosing_interval_h": 12.0, "doses": 8, "target_kd_nm": 25.0}
    if feature_key == "advanced_target_evidence":
        return pd.DataFrame({"target": ["LRRK2","LRRK2","SCN2A","GRIN2B","TREM2","TREM2"], "disease": ["Parkinson disease","Parkinson disease","Epilepsy","Neurodevelopmental disorder","Alzheimer disease","Alzheimer disease"], "evidence_score": [0.8,0.6,0.9,0.7,0.75,0.55], "source": ["genetics","literature","genetics","functional","genetics","expression"], "direction": ["increase","decrease","loss","loss","loss","loss"]})
    if feature_key == "advanced_trial_intelligence":
        return pd.DataFrame({"trial_id": ["NCT001","nct001","NCT002","NCT003"], "phase": ["Phase II","2","Phase 1","Phase III"], "status": ["Recruiting","recruiting","Completed","Terminated"], "primary_endpoint": ["Motor score","Motor score","Safety",None], "last_update": ["2026-01-01","2026-01-01","2024-06-01","2022-01-01"], "compound": ["Compound A","Compound A","Compound B","Compound C"], "target": ["LRRK2","LRRK2","SCN2A","GRIN2B"]})
    if feature_key == "neuro_oncology":
        rows=[]
        for sample in [f"T{i}" for i in range(1,16)]:
            for marker in ["IDH1","ATRX","EGFR","MGMT","TERT"]:
                rows.append({"sample_id": sample,"marker":marker,"value":rng.normal(1 if marker in {"EGFR","TERT"} and int(sample[1:])%3==0 else 0,0.5)})
        return pd.DataFrame(rows)
    if feature_key == "epilepsy_diary":
        dates=pd.date_range("2026-01-01",periods=60,freq="D")
        sleep=rng.normal(7,1,len(dates))
        adherence=np.clip(rng.normal(0.9,0.1,len(dates)),0,1)
        events=rng.poisson(np.clip(1.5-0.12*sleep+1.2*(1-adherence),0.05,None))
        return pd.DataFrame({"date":dates,"event_count":events,"sleep_hours":sleep,"medication_adherence":adherence,"stress_score":rng.integers(1,6,len(dates))})
    if feature_key == "movement_disorders":
        fs=50.0
        t=np.arange(0,30,1/fs)
        return {"data": pd.DataFrame({"time":t,"accel_x":0.5*np.sin(2*np.pi*5*t)+0.2*rng.normal(size=len(t)),"accel_y":0.3*np.sin(2*np.pi*1.8*t)+0.2*rng.normal(size=len(t)),"accel_z":1+0.2*np.sin(2*np.pi*1.8*t+0.5)+0.2*rng.normal(size=len(t))}),"sampling_rate":fs}
    if feature_key == "autonomic_hrv":
        rr=np.clip(rng.normal(850,80,300),500,1300)
        return pd.DataFrame({"rr_ms":rr,"posture":np.where(np.arange(len(rr))<150,"supine","standing")})
    if feature_key == "speech_language":
        return pd.DataFrame({"sample_id":[f"V{i+1}" for i in range(40)],"speech_rate":rng.normal(3.8,0.5,40),"pause_fraction":rng.beta(2,8,40),"jitter":rng.normal(0.015,0.004,40),"lexical_diversity":rng.normal(0.55,0.08,40),"mean_utterance_length":rng.normal(9,2,40)})
    if feature_key == "neurodegeneration_progression":
        rows=[]
        for subject in range(20):
            slope=rng.normal(0.4,0.15)
            for month in [0,6,12,18,24]:
                rows.append({"subject_id":f"P{subject+1}","time_months":month,"cognitive_score":30-slope*month/12+rng.normal(0,0.4),"imaging_atrophy":slope*month/12+rng.normal(0,0.1),"fluid_marker":1+slope*0.5*month/12+rng.normal(0,0.1),"digital_mobility":10-slope*0.8*month/12+rng.normal(0,0.2)})
        return pd.DataFrame(rows)
    if feature_key == "neuropathology":
        image=rng.normal(0.75,0.05,(256,256))
        yy,xx=np.mgrid[:256,:256]
        for _ in range(80):
            cy,cx=rng.integers(10,246,2); radius=rng.integers(2,7)
            image[(yy-cy)**2+(xx-cx)**2<radius**2]-=rng.uniform(0.25,0.55)
        return np.clip(image,0,1)
    if feature_key == "neurocritical_care":
        time=pd.date_range("2026-01-01",periods=180,freq="10min")
        icp=12+rng.normal(0,1.5,len(time)); icp[110:120]+=8
        return pd.DataFrame({"timestamp":time,"icp":icp,"map":80+rng.normal(0,5,len(time)),"gcs_proxy":14+rng.normal(0,0.5,len(time))})

    if feature_key == "genomic_cohort_qc":
        n=48
        return pd.DataFrame({"sample_id":[f"S{i+1}" for i in range(n)],"genome_build":np.where(np.arange(n)==2,"GRCh37","GRCh38"),"batch":np.where(np.arange(n)<24,"A","B"),"group":np.where(np.arange(n)%2,"case","control"),"reported_sex":np.where(np.arange(n)%2,"F","M"),"inferred_sex":np.where(np.arange(n)%2,"F","M"),"relatedness":np.where(np.arange(n)==5,0.25,0.01),"chrom":np.where(np.arange(n)%2,"chr1","chr2")})
    if feature_key == "single_cell_qc":
        matrix=rng.poisson(0.4,(200,100)).astype(float)
        matrix[:5]*=10
        genes=["MT-ND1","MT-CO1",*[f"GENE{i}" for i in range(98)]]
        return {"matrix":pd.DataFrame(matrix,columns=genes),"gene_names":genes}
    if feature_key == "spatial_qc":
        n=150
        x=rng.uniform(0,20,n); y=rng.uniform(0,20,n)
        value=np.sin(x/4)+np.cos(y/5)+rng.normal(0,0.2,n)
        return pd.DataFrame({"x":x,"y":y,"expression":value,"region":np.where(x<10,"left","right")})
    if feature_key == "multiomics_qc":
        n=60
        batch=np.where(np.arange(n)<30,"B1","B2")
        data={"sample_id":[f"M{i+1}" for i in range(n)],"batch":batch,"group":np.where(np.arange(n)%2,"case","control")}
        for i in range(25): data[f"feature_{i+1}"]=rng.normal((batch=="B2")*(0.8 if i<6 else 0),1,n)
        return pd.DataFrame(data)
    if feature_key == "microbiome_controls":
        samples=[f"S{i+1}" for i in range(20)]+["NEG1","NEG2"]
        features=[f"Taxon_{i+1}" for i in range(30)]
        abundance=pd.DataFrame(rng.poisson(2,(len(samples),len(features))),index=samples,columns=features)
        abundance.loc[["NEG1","NEG2"],"Taxon_1":"Taxon_3"]+=20
        metadata=pd.DataFrame({"sample_id":samples,"is_negative_control":[False]*20+[True,True]})
        return {"abundance":abundance,"metadata":metadata}

    if feature_key == "compound_standardization":
        return pd.DataFrame({"compound_id":["C1","C2","C3","C4"],"smiles":["CC(=O)Oc1ccccc1C(=O)O","CCO.Cl","C[N+](C)(C)C","invalid"]})
    if feature_key == "docking_validation":
        rows=[]
        for ligand in ["L1","L2","L3"]:
            for pose in range(1,6):
                rows.append({"ligand_id":ligand,"pose_id":pose,"docking_score":rng.normal(-8 if ligand=="L1" else -7,0.5),"rmsd":abs(rng.normal(1.5,0.7)),"h_bonds":rng.integers(0,5),"pi_contacts":rng.integers(0,3)})
        return pd.DataFrame(rows)
    if feature_key == "admet_calibration":
        n=50
        x=rng.normal(size=(n,4)); measured=1.2*x[:,0]-0.7*x[:,1]+rng.normal(0,0.3,n); predicted=0.8*measured+0.4+rng.normal(0,0.35,n)
        ref=pd.DataFrame({"compound_id":[f"R{i}" for i in range(n)],"measured":measured,"predicted":predicted,"mw":300+30*x[:,0],"logp":2+x[:,1],"tpsa":70+10*x[:,2],"rotb":4+x[:,3]})
        qry=pd.DataFrame({"compound_id":[f"Q{i}" for i in range(10)],"mw":300+30*rng.normal(size=10),"logp":2+rng.normal(size=10),"tpsa":70+10*rng.normal(size=10),"rotb":4+rng.normal(size=10)})
        return {"reference":ref,"query":qry}
    if feature_key == "lead_optimization":
        return pd.DataFrame({"compound_id":[f"L{i+1}" for i in range(35)],"potency":rng.uniform(0,1,35),"selectivity":rng.uniform(0,1,35),"clearance":rng.uniform(0,1,35),"toxicity":rng.uniform(0,1,35),"scaffold":[f"S{i%7}" for i in range(35)]})
    if feature_key == "protein_design":
        ref="MKTIIALSYIFCLVFADYKDDDDK"*4
        candidates=[]
        for i in range(8):
            seq=list(ref)
            for pos in rng.choice(len(seq),size=i+1,replace=False): seq[pos]=rng.choice(list("ACDEFGHIKLMNPQRSTVWY"))
            candidates.append({"candidate_id":f"P{i+1}","sequence":"".join(seq)})
        return {"reference":ref,"candidates":pd.DataFrame(candidates),"conserved_positions":[2,5,10,20]}
    if feature_key == "antibody_developability":
        base="EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEWVSAISGSGGSTYYADSVKGRFTISRDNSKNTLYLQMNSLRAEDTAVYYCARGGGYWGQGTLVTVSS"
        return pd.DataFrame({"antibody_id":["Ab1","Ab2","Ab3"],"sequence":[base,base.replace("A","M",2),base+"NGNG"]})
    if feature_key == "neoantigen":
        return pd.DataFrame({"peptide":["SLYNTVATL","GILGFVFTL","LLFGYPVYV","AAAKKKLLL"],"hla":["HLA-A*02:01"]*4,"binding_affinity_nm":[20,120,600,50],"rna_expression":[25,5,40,0.2],"variant_allele_fraction":[0.45,0.2,0.5,0.1],"normal_tissue_expression":[0,0,5,0],"clonality":[0.9,0.5,0.8,0.2]})
    if feature_key == "assay_planning":
        return {"groups":["vehicle","compound_low","compound_high"],"effect_size":0.8,"power":0.85}

    if feature_key == "microscopy_qc":
        image=rng.normal(0.15,0.03,(256,256,3))
        yy,xx=np.mgrid[:256,:256]
        for channel in range(3):
            for _ in range(50):
                cy,cx=rng.integers(8,248,2); radius=rng.integers(3,9)
                image[(yy-cy)**2+(xx-cx)**2<radius**2,channel]+=rng.uniform(0.4,0.8)
        return np.clip(image,0,1)
    if feature_key == "plate_qc":
        rows=[]
        for plate in ["P1","P2"]:
            for r,row in enumerate("ABCDEFGH"):
                for col in range(1,13):
                    control="sample"
                    mean=0
                    if col==1: control="negative"; mean=0
                    if col==12: control="positive"; mean=5
                    rows.append({"plate":plate,"well":f"{row}{col}","control_type":control,"measurement":rng.normal(mean,0.4)})
        return pd.DataFrame(rows)
    if feature_key == "bioprocess":
        t=np.linspace(0,48,49); biomass=0.1*np.exp(0.12*t)/(1+0.1*(np.exp(0.12*t)-1)); product=np.maximum(0,0.8*(biomass-0.1))+rng.normal(0,0.01,len(t)); substrate=20-6*biomass
        return pd.DataFrame({"time_hours":t,"biomass":biomass,"product":product,"substrate":substrate,"ph":7-0.01*t+rng.normal(0,0.03,len(t)),"do":80-1.1*t+rng.normal(0,2,len(t)),"temperature":37+rng.normal(0,0.1,len(t))})
    if feature_key == "metagenomics_controls":
        rows=[]
        for sample in [f"S{i+1}" for i in range(12)]+["NEG1","NEG2"]:
            neg=sample.startswith("NEG")
            for taxon in [f"Taxon_{i+1}" for i in range(15)]:
                value=rng.poisson(20 if neg and taxon in {"Taxon_1","Taxon_2"} else 2)
                rows.append({"sample_id":sample,"taxon":taxon,"abundance":value,"is_negative_control":neg})
        return pd.DataFrame(rows)
    if feature_key == "synthetic_biology":
        return {"sequence":"ATG"+"GCTGAACTG"*80+"GAATTC"+"TTTTTTTT"+"TAA","construct_name":"DemoCircuit"}
    if feature_key == "primer_crispr":
        target="ACGT"*30+"GACTGACTGACTGACTGACTTGG"+"TGCA"*20
        genome=target+"NNNN"+target.replace("GACTGACTGACTGACTGACT","GACTGACTGACTGACTGACC")
        primers=pd.DataFrame({"primer_id":["F1","R1"],"sequence":["ACGTACGTACGTACGTACGT","TGCATGCATGCATGCATGCA"]})
        return {"primers":primers,"target_sequence":target,"genome_sequence":genome}
    if feature_key == "organoid":
        rows=[]
        for oid in range(15):
            for time in [0,2,4,6,8]:
                rows.append({"organoid_id":f"O{oid+1}","time":time,"diameter_x":100+oid+time*8+rng.normal(0,4),"diameter_y":95+oid+time*7+rng.normal(0,4),"diameter_z":90+oid+time*6+rng.normal(0,4)})
        return pd.DataFrame(rows)
    if feature_key == "gene_therapy":
        return {"sequence":"ACGT"*1050,"vector_type":"AAV","promoter":"CAG","target_tissue":"CNS"}
    if feature_key == "experiment_planner":
        return {"groups":["control","treatment_low","treatment_high"],"replicates":6,"blocks":["Day-1","Day-2"]}
    if feature_key in {"format_readiness","tool_readiness","reproducibility"}:
        return None
    raise KeyError(feature_key)
