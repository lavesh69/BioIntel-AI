import os
from typing import Optional
from biointel.connect.connect_service import ConnectService
from biointel.education.classroom_service import ClassroomService
from biointel.education.science_pulse_service import SciencePulseService
from biointel.education.academy_service import AcademyService
from biointel.education.universe_workspaces_service import UniverseWorkspacesService

def seed_education_demo_data(root_dir: Optional[str] = None):
    print("Seeding Education Demo Data across all database engines...")
    if root_dir is None:
        root_dir = os.getcwd()

    # 1. Connect
    cs = ConnectService(root_dir)
    cs.create_or_update_profile("user_demo_1", {
        "name": "Dr. Aarav Sharma",
        "headline": "Professor of Computational Genomics | BioIntel Fellow",
        "institution": "Indian Institute of Science",
        "lab": "Genome Architecture & Structural Bioinformatics Lab",
        "bio": "Researching pangenome graphs, long-read assemblies and structural variant calling algorithms.",
        "orcid": "0000-0001-9283-4712",
        "skills": ["Pangenomics", "BioPython", "Graph Alignments", "Nextflow"],
        "interests": ["Structural Variants", "T2T Human Genome", "Nanopore Sequencing"]
    })
    cs.create_or_update_profile("user_demo_2", {
        "name": "Dr. Elena Rostova",
        "headline": "Lead Structural Biologist & AI Drug Discovery Specialist",
        "institution": "EMBL Heidelberg",
        "lab": "Molecular Dynamics & Target Discovery Unit",
        "bio": "Applying deep learning protein design, binding pocket analysis and cryo-EM model refinement.",
        "orcid": "0000-0003-4912-8841",
        "skills": ["PyMOL", "AlphaFold2", "Molecular Docking", "GROMACS"],
        "interests": ["ProteinMPNN", "Allosteric Inhibitors", "Cryo-EM"]
    })

    cs.create_post("user_demo_1", "Dr. Aarav Sharma", "publication",
                   "Excited to share our latest benchmark on graph-based pangenome alignment accuracy across diverse human cohorts! Check out the open pipeline code in BioIntel Studio.",
                   metadata={"doi": "10.1038/s41587-026-01982-x", "journal": "Nature Biotechnology"})
    
    cs.create_post("user_demo_2", "Dr. Elena Rostova", "dataset",
                   "We just deposited a benchmark dataset of 1,200 high-resolution protein-ligand co-crystal structures with binding affinity annotations.",
                   metadata={"pdb_ids": ["7XYZ", "8ABC", "9DEF"], "samples": 1200})

    # 2. Classroom
    cls = ClassroomService(root_dir)
    c1 = cls.add_class("M.Sc. Bioinformatics - Batch 2026", "2025-2026", "Department of Computational Biology", "Dr. Aarav Sharma")
    c2 = cls.add_class("B.Tech Biotechnology - Year 3", "2025-2026", "School of Bio-Sciences", "Dr. Elena Rostova")

    cls.create_assignment(c1["class_id"], "Pangenome Graph Construction Assignment", "Build a GFA graph using minigraph on the provided 5 human contigs.", "2026-08-15T23:59:00Z")
    cls.create_assignment(c2["class_id"], "Molecular Docking & Lipinski Rule Analysis", "Validate SMILES for 20 FDA-approved kinase inhibitors and run vina docking.", "2026-08-20T23:59:00Z")

    cls.mark_attendance(c1["class_id"], "std_101", "2026-07-29", "Present", "On time")
    cls.mark_attendance(c1["class_id"], "std_102", "2026-07-29", "Present", "Active participant")

    # 3. Science Pulse
    sp = SciencePulseService(root_dir)
    sp.add_article({
        "article_id": "art_pubmed_3819201",
        "source": "PubMed",
        "doi_pmid": "PMID: 3819201",
        "title": "Scalable Pangenome Graph Indexing for Population-Scale Variant Discovery",
        "authors": "Sharma A, Rostova E, Dobriyal L",
        "abstract": "We describe a memory-efficient suffix-array indexing strategy for variation graphs that scales linearly with sequence length.",
        "journal": "Genome Research",
        "pub_date": "2026-07-15",
        "saved": True,
        "tags": ["Pangenome", "Indexing", "Variant Calling"]
    })
    sp.add_article({
        "article_id": "art_biorxiv_2026_07_8819",
        "source": "bioRxiv",
        "doi_pmid": "10.1101/2026.07.29.591029",
        "title": "Zero-shot De Novo Protein Design targeting Undruggable Transcription Factors",
        "authors": "Rostova E, Patel K, Sharma A",
        "abstract": "Generative diffusion models conditioned on surface electrostatic maps generate nanomolar binders for Myc and Kras.",
        "journal": "bioRxiv Preprint",
        "pub_date": "2026-07-28",
        "saved": True,
        "tags": ["Protein Design", "Diffusion", "Cancer Targets"]
    })

    # 4. Academy
    ac = AcademyService(root_dir)
    ac.add_course(
        "Mastering Pangenomics & Graph Genome Algorithms",
        "Bioinformatics",
        "Dr. Aarav Sharma",
        "Comprehensive hands-on course covering GFA format, minigraph, vg toolset, and variation graph alignment.",
        [
            {"title": "Lesson 1: Introduction to Variation Graphs", "duration": "45 mins"},
            {"title": "Lesson 2: GFA Format & Haplotype Paths", "duration": "60 mins"},
            {"title": "Lesson 3: Aligning Reads to Pangenomes with VG", "duration": "90 mins"}
        ]
    )
    ac.add_course(
        "AI-Driven Small Molecule & Biologics Design",
        "Drug Discovery",
        "Dr. Elena Rostova",
        "Explore RDKit descriptors, Lipinski rules, PyTorch DTI predictors, and AlphaFold-multimer interface design.",
        [
            {"title": "Lesson 1: Chemical Structure Representation & SMILES", "duration": "40 mins"},
            {"title": "Lesson 2: Feature Engineering & Fingerprints", "duration": "75 mins"},
            {"title": "Lesson 3: Molecular Docking & Binding Free Energy", "duration": "90 mins"}
        ]
    )

    # 5. Universe Workspaces (20 modules)
    uv = UniverseWorkspacesService(root_dir)
    universe_modules = [
        ("adaptive_learning", "Adaptive Mastery Track - Structural Biology", {"level": "Advanced", "mastery_score": 92.4, "topics_covered": 18}),
        ("virtual_lab", "Virtual PCR & Gel Electrophoresis Experiment", {"amplicon_len": 450, "annealing_temp": 58.5, "gel_concentration": "1.5%"}),
        ("bioinformatics_sandbox", "RNA-seq Differential Expression Sandbox", {"tool": "DESeq2", "padj_cutoff": 0.05, "genes_up": 142, "genes_down": 89}),
        ("shiro_tutor", "Shiro AI Tutor - CRISPR Guide Design Practice", {"gene": "BRCA1", "exon": 11, "pam_type": "NGG", "top_guides": 5}),
        ("learning_analytics", "Departmental Cohort Retention Analytics", {"retention_rate": 96.8, "assignment_completion": 94.2}),
        ("digital_library", "Open Access Structural Genomics Collection", {"books": 45, "papers": 380, "protocols": 112}),
        ("student_research_hub", "Student Innovation Grant: Single-Cell Spatial Atlas", {"budget": 15000, "status": "Approved", "pi": "Rohan Gupta"}),
        ("competition_center", "National BioHackathon 2026 - Pangenome Challenge", {"teams": 32, "lead_board": "Team BioIntel", "prize_pool": "$25,000"}),
        ("career_hub", "Global Postdoctoral Fellowships in Computational Biology", {"postings": 14, "featured": "EMBL Fellowship 2026"}),
        ("academic_portfolio", "Verified Credentials Portfolio - BioIntel Certified Architect", {"credential_id": "CERT-2026-9921", "verification_hash": "a8f9c1e3b2"}),
        ("lab_management", "Confocal Microscopy Instrument Scheduling & Buffer Inventory", {"active_reservations": 8, "laser_health": "100%"}),
        ("question_bank", "Genomics & Sequence Analysis Item Bank", {"multiple_choice": 240, "numerical": 80, "peer_reviewed": True}),
        ("lecture_intelligence", "Real-Time Speech-to-Text & Multilingual Translation Engine", {"languages": ["English", "Hindi", "Spanish", "French"]}),
        ("academic_erp", "Semester Fee, Enrolment & Transcript Management System", {"active_students": 520, "compliance_rate": "100%"}),
        ("gamified_learning", "BioQuest: Protein Folding Quest", {"xp_points": 1450, "current_rank": "Master Binder"}),
        ("teaching_support", "Peer Review & Pedagogy Quality Assurance Board", {"reviews_completed": 24, "quality_score": 4.9}),
        ("offline_learning", "Cached Offline Course Packs & Mobile Sync Engine", {"downloaded_mb": 420, "sync_status": "Up-to-date"}),
        ("open_science", "FAIR Data Repository & Micro-Attribution Hub", {"datasets_published": 12, "fair_score": 98.5}),
        ("collaboration_network", "Inter-Institutional Research Network", {"collaborating_institutions": 16, "joint_projects": 8}),
        ("safety_moderation", "Scientific Content Integrity & Minor Safety Controls", {"flagged_content": 0, "safety_policy": "Strict Academic"})
    ]

    for mod_key, title, payload in universe_modules:
        uv.save_record(mod_key, title, payload, created_by="DemoSeeder")

    print("Education Demo Data successfully seeded!")

if __name__ == "__main__":
    seed_education_demo_data()
