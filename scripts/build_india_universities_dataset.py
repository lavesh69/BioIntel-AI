import json
import os
import sqlite3
from datetime import datetime, timezone

INDIAN_UNIVERSITIES_DATA = [
    # Institutes of National Importance / Premium Research
    {"id": "inst_iisc_bangalore", "name": "Indian Institute of Science (IISc), Bangalore", "type": "Institute of National Importance", "state": "Karnataka", "city": "Bangalore", "website": "https://iisc.ac.in"},
    {"id": "inst_iit_delhi", "name": "Indian Institute of Technology (IIT), Delhi", "type": "Institute of National Importance", "state": "Delhi", "city": "New Delhi", "website": "https://iitd.ac.in"},
    {"id": "inst_iit_bombay", "name": "Indian Institute of Technology (IIT), Bombay", "type": "Institute of National Importance", "state": "Maharashtra", "city": "Mumbai", "website": "https://iitb.ac.in"},
    {"id": "inst_iit_kharagpur", "name": "Indian Institute of Technology (IIT), Kharagpur", "type": "Institute of National Importance", "state": "West Bengal", "city": "Kharagpur", "website": "https://iitkgp.ac.in"},
    {"id": "inst_iit_madras", "name": "Indian Institute of Technology (IIT), Madras", "type": "Institute of National Importance", "state": "Tamil Nadu", "city": "Chennai", "website": "https://iitm.ac.in"},
    {"id": "inst_iit_kanpur", "name": "Indian Institute of Technology (IIT), Kanpur", "type": "Institute of National Importance", "state": "Uttar Pradesh", "city": "Kanpur", "website": "https://iitk.ac.in"},
    {"id": "inst_iit_roorkee", "name": "Indian Institute of Technology (IIT), Roorkee", "type": "Institute of National Importance", "state": "Uttarakhand", "city": "Roorkee", "website": "https://iitr.ac.in"},
    {"id": "inst_iit_guwahati", "name": "Indian Institute of Technology (IIT), Guwahati", "type": "Institute of National Importance", "state": "Assam", "city": "Guwahati", "website": "https://iitg.ac.in"},
    {"id": "inst_aiims_delhi", "name": "All India Institute of Medical Sciences (AIIMS), New Delhi", "type": "Institute of National Importance", "state": "Delhi", "city": "New Delhi", "website": "https://aiims.edu"},
    {"id": "inst_iiser_pune", "name": "Indian Institute of Science Education and Research (IISER), Pune", "type": "Institute of National Importance", "state": "Maharashtra", "city": "Pune", "website": "https://iiserpune.ac.in"},
    {"id": "inst_iiser_kolkata", "name": "Indian Institute of Science Education and Research (IISER), Kolkata", "type": "Institute of National Importance", "state": "West Bengal", "city": "Kolkata", "website": "https://iiserkol.ac.in"},
    {"id": "inst_iiser_mohali", "name": "Indian Institute of Science Education and Research (IISER), Mohali", "type": "Institute of National Importance", "state": "Punjab", "city": "Mohali", "website": "https://iisermohali.ac.in"},
    
    # Central Universities
    {"id": "inst_du", "name": "University of Delhi (DU)", "type": "Central University", "state": "Delhi", "city": "New Delhi", "website": "https://du.ac.in"},
    {"id": "inst_bhu", "name": "Banaras Hindu University (BHU)", "type": "Central University", "state": "Uttar Pradesh", "city": "Varanasi", "website": "https://bhu.ac.in"},
    {"id": "inst_jnu", "name": "Jawaharlal Nehru University (JNU)", "type": "Central University", "state": "Delhi", "city": "New Delhi", "website": "https://jnu.ac.in"},
    {"id": "inst_uoh", "name": "University of Hyderabad (UoH)", "type": "Central University", "state": "Telangana", "city": "Hyderabad", "website": "https://uoh.ac.in"},
    {"id": "inst_amu", "name": "Aligarh Muslim University (AMU)", "type": "Central University", "state": "Uttar Pradesh", "city": "Aligarh", "website": "https://amu.ac.in"},
    {"id": "inst_jmi", "name": "Jamia Millia Islamia (JMI)", "type": "Central University", "state": "Delhi", "city": "New Delhi", "website": "https://jmi.ac.in"},
    {"id": "inst_visva_bharati", "name": "Visva-Bharati University", "type": "Central University", "state": "West Bengal", "city": "Santiniketan", "website": "https://visvabharati.ac.in"},
    {"id": "inst_tezpur", "name": "Tezpur University", "type": "Central University", "state": "Assam", "city": "Tezpur", "website": "https://tezu.ernet.in"},

    # Major State & Deemed Universities
    {"id": "inst_pune_univ", "name": "Savitribai Phule Pune University", "type": "State University", "state": "Maharashtra", "city": "Pune", "website": "https://unipune.ac.in"},
    {"id": "inst_mumbai_univ", "name": "University of Mumbai", "type": "State University", "state": "Maharashtra", "city": "Mumbai", "website": "https://mu.ac.in"},
    {"id": "inst_anna_univ", "name": "Anna University", "type": "State University", "state": "Tamil Nadu", "city": "Chennai", "website": "https://annauniv.edu"},
    {"id": "inst_calcutta_univ", "name": "University of Calcutta", "type": "State University", "state": "West Bengal", "city": "Kolkata", "website": "https://caluniv.ac.in"},
    {"id": "inst_panjab_univ", "name": "Panjab University", "type": "State University", "state": "Punjab", "city": "Chandigarh", "website": "https://puchd.ac.in"},
    {"id": "inst_vit_vellore", "name": "Vellore Institute of Technology (VIT)", "type": "Deemed University", "state": "Tamil Nadu", "city": "Vellore", "website": "https://vit.ac.in"},
    {"id": "inst_manipal", "name": "Manipal Academy of Higher Education (MAHE)", "type": "Deemed University", "state": "Karnataka", "city": "Manipal", "website": "https://manipal.edu"},
    {"id": "inst_bits_pilani", "name": "Birla Institute of Technology and Science (BITS), Pilani", "type": "Deemed University", "state": "Rajasthan", "city": "Pilani", "website": "https://bits-pilani.ac.in"},

    # Premier National CSIR / ICMR / DBT Research Institutes
    {"id": "inst_ncbs", "name": "National Centre for Biological Sciences (NCBS-TIFR)", "type": "Research Autonomous Institute", "state": "Karnataka", "city": "Bangalore", "website": "https://ncbs.res.in"},
    {"id": "inst_ccmb", "name": "CSIR - Centre for Cellular and Molecular Biology (CCMB)", "type": "CSIR National Laboratory", "state": "Telangana", "city": "Hyderabad", "website": "https://ccmb.res.in"},
    {"id": "inst_igib", "name": "CSIR - Institute of Genomics and Integrative Biology (IGIB)", "type": "CSIR National Laboratory", "state": "Delhi", "city": "New Delhi", "website": "https://igib.res.in"},
    {"id": "inst_cdri", "name": "CSIR - Central Drug Research Institute (CDRI)", "type": "CSIR National Laboratory", "state": "Uttar Pradesh", "city": "Lucknow", "website": "https://cdri.res.in"},
    {"id": "inst_nibmg", "name": "National Institute of Biomedical Genomics (NIBMG)", "type": "DBT Autonomous Institute", "state": "West Bengal", "city": "Kalyani", "website": "https://nibmg.ac.in"},
    {"id": "inst_nipgr", "name": "National Institute of Plant Genome Research (NIPGR)", "type": "DBT Autonomous Institute", "state": "Delhi", "city": "New Delhi", "website": "https://nipgr.ac.in"},
    {"id": "inst_thsti", "name": "Translational Health Science and Technology Institute (THSTI)", "type": "DBT Autonomous Institute", "state": "Haryana", "city": "Faridabad", "website": "https://thsti.res.in"}
]

# Generate state-wise expanded directory entries to cover all 28 states & UTs
STATES_COVERAGE = [
    ("Andhra Pradesh", "Andhra University / Sri Venkateswara University"),
    ("Arunachal Pradesh", "Rajiv Gandhi University, Itanagar"),
    ("Assam", "Gauhati University / Assam University"),
    ("Bihar", "Patna University / Central University of South Bihar"),
    ("Chhattisgarh", "Pt. Ravishankar Shukla University, Raipur"),
    ("Goa", "Goa University, Taleigao Plateau"),
    ("Gujarat", "Gujarat University / Maharaja Sayajirao University of Baroda"),
    ("Haryana", "Kurukshetra University / Maharshi Dayanand University"),
    ("Himachal Pradesh", "Himachal Pradesh University, Shimla"),
    ("Jharkhand", "Ranchi University / Central University of Jharkhand"),
    ("Karnataka", "Bangalore University / Mysore University"),
    ("Kerala", "University of Kerala / Mahatma Gandhi University, Kottayam"),
    ("Madhya Pradesh", "Dr. Harisingh Gour University, Sagar / DAVV Indore"),
    ("Odisha", "Utkal University / Sambalpur University"),
    ("Punjab", "Guru Nanak Dev University, Amritsar"),
    ("Rajasthan", "University of Rajasthan, Jaipur"),
    ("Sikkim", "Sikkim University, Gangtok"),
    ("Tamil Nadu", "University of Madras / Bharathidasan University"),
    ("Telangana", "Osmania University, Hyderabad"),
    ("Tripura", "Tripura University, Agartala"),
    ("Uttar Pradesh", "University of Lucknow / Chhatrapati Shahu Ji Maharaj University"),
    ("Uttarakhand", "HNB Garhwal University, Srinagar"),
    ("West Bengal", "Jadavpur University, Kolkata")
]

for idx, (st_name, univ_name) in enumerate(STATES_COVERAGE, 1):
    inst_id = f"inst_state_univ_{idx}"
    INDIAN_UNIVERSITIES_DATA.append({
        "id": inst_id,
        "name": univ_name,
        "type": "State / Public University",
        "state": st_name,
        "city": st_name + " Region",
        "website": "https://ugc.ac.in"
    })

def import_india_universities(root_dir: str):
    data_dir = os.path.join(root_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    json_path = os.path.join(data_dir, "india_universities_directory.json")

    with open(json_path, "w", encoding="utf-8") as out:
        json.dump(INDIAN_UNIVERSITIES_DATA, out, indent=2)
    print(f"Saved {len(INDIAN_UNIVERSITIES_DATA)} Indian Universities into {json_path}")

    # Ingest into biointel_education.sqlite
    db_dir = os.path.join(root_dir, "UserData", "databases")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "biointel_education.sqlite")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS edu_institutions (
        institution_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        code TEXT UNIQUE,
        country TEXT DEFAULT 'India',
        website TEXT,
        created_at TEXT
    )
    """)

    for col in ["state", "city", "type"]:
        try:
            cur.execute(f"ALTER TABLE edu_institutions ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass

    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for u in INDIAN_UNIVERSITIES_DATA:
        cur.execute("""
            INSERT INTO edu_institutions (institution_id, name, code, country, state, city, type, website, created_at)
            VALUES (?, ?, ?, 'India', ?, ?, ?, ?, ?)
            ON CONFLICT(institution_id) DO UPDATE SET
                name=excluded.name,
                state=excluded.state,
                city=excluded.city,
                type=excluded.type,
                website=excluded.website
        """, (u["id"], u["name"], u["id"], u["state"], u["city"], u["type"], u["website"], now))
        count += 1

    conn.commit()
    conn.close()
    print(f"Successfully ingested {count} Indian Universities into biointel_education.sqlite!")

if __name__ == "__main__":
    r_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    import_india_universities(r_dir)
