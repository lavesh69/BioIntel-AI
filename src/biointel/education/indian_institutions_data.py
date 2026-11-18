"""
BioIntel AI 15.6.0 — Indian Universities & Schools Comprehensive Directory
Provides curated NIRF/UGC/NAAC Indian Higher Education Institutions, IITs, NITs, AIIMS,
Central/State Universities, and K-12 Premier Schools with Search & Filtering.
"""

from typing import List, Dict, Any, Optional

INDIAN_INSTITUTIONS_DATABASE: List[Dict[str, Any]] = [
    # --- CENTRAL UNIVERSITIES & PREMIER INSTITUTES ---
    {
        "id": "ind_univ_001",
        "name": "Indian Institute of Science (IISc)",
        "city": "Bengaluru",
        "state": "Karnataka",
        "category": "Central Research Institute",
        "type": "University",
        "nirf_rank": "1 (Overall/Research)",
        "naac_grade": "A++",
        "programs": ["M.Tech Computational & Data Science", "Ph.D. Bioengineering", "BS Research in Biology"],
        "website": "iisc.ac.in",
        "established": 1909
    },
    {
        "id": "ind_univ_002",
        "name": "Indian Institute of Technology Bombay (IIT Bombay)",
        "city": "Mumbai",
        "state": "Maharashtra",
        "category": "IIT / Institute of National Importance",
        "type": "University",
        "nirf_rank": "3 (Engineering)",
        "naac_grade": "A++",
        "programs": ["B.Tech Biosciences & Bioengineering", "M.Sc. Biotechnology", "Ph.D. Structural Biology"],
        "website": "iitb.ac.in",
        "established": 1958
    },
    {
        "id": "ind_univ_003",
        "name": "Indian Institute of Technology Delhi (IIT Delhi)",
        "city": "New Delhi",
        "state": "Delhi",
        "category": "IIT / Institute of National Importance",
        "type": "University",
        "nirf_rank": "2 (Engineering)",
        "naac_grade": "A++",
        "programs": ["M.Tech Biochemical Engineering & Biotechnology", "Ph.D. Computational Biology"],
        "website": "iitd.ac.in",
        "established": 1961
    },
    {
        "id": "ind_univ_004",
        "name": "Indian Institute of Technology Madras (IIT Madras)",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "category": "IIT / Institute of National Importance",
        "type": "University",
        "nirf_rank": "1 (Engineering)",
        "naac_grade": "A++",
        "programs": ["B.Tech Biological Engineering", "M.Tech Data Science & AI", "Ph.D. Medical Sciences"],
        "website": "iitm.ac.in",
        "established": 1959
    },
    {
        "id": "ind_univ_005",
        "name": "All India Institute of Medical Sciences (AIIMS New Delhi)",
        "city": "New Delhi",
        "state": "Delhi",
        "category": "Medical / AIIMS",
        "type": "University",
        "nirf_rank": "1 (Medical)",
        "naac_grade": "A++",
        "programs": ["MBBS", "M.Sc. Human Anatomy & Genetics", "Ph.D. Genomics & Precision Medicine"],
        "website": "aiims.edu",
        "established": 1956
    },
    {
        "id": "ind_univ_006",
        "name": "Jawaharlal Nehru University (JNU)",
        "city": "New Delhi",
        "state": "Delhi",
        "category": "Central University",
        "type": "University",
        "nirf_rank": "2 (University)",
        "naac_grade": "A++",
        "programs": ["M.Sc. Biotechnology", "Ph.D. Molecular Medicine", "M.Sc. Computational & Systems Biology"],
        "website": "jnu.ac.in",
        "established": 1969
    },
    {
        "id": "ind_univ_007",
        "name": "University of Delhi (DU)",
        "city": "New Delhi",
        "state": "Delhi",
        "category": "Central University",
        "type": "University",
        "nirf_rank": "11 (University)",
        "naac_grade": "A+",
        "programs": ["M.Sc. Plant Molecular Biology", "M.Sc. Genetics", "B.Sc. (Hons) Biochemistry"],
        "website": "du.ac.in",
        "established": 1922
    },
    {
        "id": "ind_univ_008",
        "name": "Banaras Hindu University (BHU)",
        "city": "Varanasi",
        "state": "Uttar Pradesh",
        "category": "Central University",
        "type": "University",
        "nirf_rank": "5 (University)",
        "naac_grade": "A++",
        "programs": ["M.Sc. Bioinformatics", "M.Sc. Molecular & Human Genetics", "MBBS IMS-BHU"],
        "website": "bhu.ac.in",
        "established": 1916
    },
    {
        "id": "ind_univ_009",
        "name": "University of Hyderabad (UoH)",
        "city": "Hyderabad",
        "state": "Telangana",
        "category": "Central University",
        "type": "University",
        "nirf_rank": "10 (University)",
        "naac_grade": "A++",
        "programs": ["M.Sc. Biotechnology", "M.Tech Bioinformatics", "Ph.D. Animal Biology"],
        "website": "uohyd.ac.in",
        "established": 1974
    },
    {
        "id": "ind_univ_010",
        "name": "Aligarh Muslim University (AMU)",
        "city": "Aligarh",
        "state": "Uttar Pradesh",
        "category": "Central University",
        "type": "University",
        "nirf_rank": "9 (University)",
        "naac_grade": "A+",
        "programs": ["M.Sc. Biotechnology", "M.Sc. Interdisciplinary Biotechnology", "Ph.D. Biochemistry"],
        "website": "amu.ac.in",
        "established": 1920
    },
    {
        "id": "ind_univ_011",
        "name": "Jamia Millia Islamia (JMI)",
        "city": "New Delhi",
        "state": "Delhi",
        "category": "Central University",
        "type": "University",
        "nirf_rank": "3 (University)",
        "naac_grade": "A++",
        "programs": ["M.Sc. Biosciences", "M.Sc. Biotechnology", "Ph.D. Interdisciplinary Research"],
        "website": "jmi.ac.in",
        "established": 1920
    },
    {
        "id": "ind_univ_012",
        "name": "Jadavpur University",
        "city": "Kolkata",
        "state": "West Bengal",
        "category": "State University",
        "type": "University",
        "nirf_rank": "4 (University)",
        "naac_grade": "A+",
        "programs": ["M.Tech Biotechnology", "M.Sc. Life Sciences & Biotechnology"],
        "website": "jaduniv.edu.in",
        "established": 1955
    },
    {
        "id": "ind_univ_013",
        "name": "Anna University",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "category": "State University",
        "type": "University",
        "nirf_rank": "14 (University)",
        "naac_grade": "A++",
        "programs": ["B.Tech Biotechnology", "M.Tech Biopharmaceutical Technology"],
        "website": "annauniv.edu",
        "established": 1978
    },
    {
        "id": "ind_univ_014",
        "name": "Savitribai Phule Pune University (SPPU)",
        "city": "Pune",
        "state": "Maharashtra",
        "category": "State University",
        "type": "University",
        "nirf_rank": "12 (University)",
        "naac_grade": "A+",
        "programs": ["M.Sc. Bioinformatics (IBB)", "M.Sc. Biotechnology", "Ph.D. Zoology & Botany"],
        "website": "unipune.ac.in",
        "established": 1949
    },
    {
        "id": "ind_univ_015",
        "name": "BITS Pilani (Birla Institute of Technology and Science)",
        "city": "Pilani",
        "state": "Rajasthan",
        "category": "Deemed University",
        "type": "University",
        "nirf_rank": "20 (Overall)",
        "naac_grade": "A",
        "programs": ["M.Sc. Biological Sciences", "M.E. Biotechnology", "Ph.D. Computational Life Sciences"],
        "website": "bits-pilani.ac.in",
        "established": 1964
    },
    {
        "id": "ind_univ_016",
        "name": "Manipal Academy of Higher Education (MAHE)",
        "city": "Manipal",
        "state": "Karnataka",
        "category": "Deemed University",
        "type": "University",
        "nirf_rank": "6 (University)",
        "naac_grade": "A++",
        "programs": ["M.Sc. Molecular Biology & Human Genetics", "M.Sc. Bioinformatics", "MBBS KMC"],
        "website": "manipal.edu",
        "established": 1953
    },
    {
        "id": "ind_univ_017",
        "name": "VIT Vellore (Vellore Institute of Technology)",
        "city": "Vellore",
        "state": "Tamil Nadu",
        "category": "Deemed University",
        "type": "University",
        "nirf_rank": "8 (University)",
        "naac_grade": "A++",
        "programs": ["B.Tech Biotechnology", "M.Tech Applied Microbiology", "M.Sc. Biomedical Genetics"],
        "website": "vit.ac.in",
        "established": 1984
    },
    {
        "id": "ind_univ_018",
        "name": "Amrita Vishwa Vidyapeetham",
        "city": "Coimbatore",
        "state": "Tamil Nadu",
        "category": "Deemed University",
        "type": "University",
        "nirf_rank": "7 (University)",
        "naac_grade": "A++",
        "programs": ["M.Sc. Biotechnology", "M.Sc. Bioinformatics", "Ph.D. Nanosciences & Molecular Medicine"],
        "website": "amrita.edu",
        "established": 2003
    },
    {
        "id": "ind_univ_019",
        "name": "Panjab University (PU)",
        "city": "Chandigarh",
        "state": "Chandigarh / Punjab",
        "category": "State / Central Assisted",
        "type": "University",
        "nirf_rank": "25 (University)",
        "naac_grade": "A++",
        "programs": ["M.Sc. Biotechnology", "M.Sc. Microbial Biotechnology", "Ph.D. Biophysics"],
        "website": "puchd.ac.in",
        "established": 1882
    },
    {
        "id": "ind_univ_020",
        "name": "National Institute of Pharmaceutical Education and Research (NIPER)",
        "city": "Mohali",
        "state": "Punjab",
        "category": "Institute of National Importance",
        "type": "University",
        "nirf_rank": "1 (Pharmacy)",
        "naac_grade": "A++",
        "programs": ["M.S. (Pharm.) Pharmacoinformatics", "M.S. (Pharm.) Biotechnology", "Ph.D. Medicinal Chemistry"],
        "website": "niper.gov.in",
        "established": 1998
    },

    # --- PREMIER SCHOOLS & K-12 NETWORKS IN INDIA ---
    {
        "id": "ind_sch_001",
        "name": "Kendriya Vidyalaya Sangathan (KVS Network - 1250+ Schools)",
        "city": "Pan-India Network",
        "state": "National / All States",
        "category": "Central Government K-12 Network",
        "type": "School",
        "nirf_rank": "Top Central School System",
        "naac_grade": "CBSE Affiliated",
        "programs": ["Class XI-XII PCMB Science Stream", "Class XI-XII Computer Science & Informatics"],
        "website": "kvsangathan.nic.in",
        "established": 1963
    },
    {
        "id": "ind_sch_002",
        "name": "Jawahar Navodaya Vidyalaya (JNV Network - 660+ Schools)",
        "city": "Pan-India Network",
        "state": "National / All States",
        "category": "Central Residential School System",
        "type": "School",
        "nirf_rank": "Premier Rural Talent Network",
        "naac_grade": "CBSE Affiliated",
        "programs": ["Senior Secondary Science", "Biotechnology & AI Vocational Modules"],
        "website": "navodaya.gov.in",
        "established": 1986
    },
    {
        "id": "ind_sch_003",
        "name": "Delhi Public School (DPS R.K. Puram / Vasant Kunj / Mathura Road)",
        "city": "New Delhi",
        "state": "Delhi",
        "category": "Private K-12 Network",
        "type": "School",
        "nirf_rank": "Top Private Day/Boarding School",
        "naac_grade": "CBSE Affiliated",
        "programs": ["Class XI-XII PCMB", "STEM & Robotics Innovation Club", "Biotech Research Lab"],
        "website": "dpsrkp.net",
        "established": 1972
    },
    {
        "id": "ind_sch_004",
        "name": "Sainik School Society (Network of 33+ Military Schools)",
        "city": "Pan-India Network",
        "state": "National / Defence Ministry",
        "category": "Defence / Residential School",
        "type": "School",
        "nirf_rank": "Premier Defence Leadership Network",
        "naac_grade": "CBSE Affiliated",
        "programs": ["Class VI-XII Science & NDA Preparation", "STEM Laboratories"],
        "website": "sainikschoolsociety.in",
        "established": 1961
    },
    {
        "id": "ind_sch_005",
        "name": "DAV Public Schools Network (900+ Institutions)",
        "city": "Pan-India Network",
        "state": "National / All States",
        "category": "Private Trust K-12 Network",
        "type": "School",
        "nirf_rank": "Top National Education Chain",
        "naac_grade": "CBSE / State Affiliated",
        "programs": ["Class XI-XII PCMB", "Informatics Practices", "Biotechnology"],
        "website": "davcmc.net.in",
        "established": 1886
    },
    {
        "id": "ind_sch_006",
        "name": "The Cathedral & John Connon School",
        "city": "Mumbai",
        "state": "Maharashtra",
        "category": "Private Premier ICSE/IB School",
        "type": "School",
        "nirf_rank": "Rank 1 CISCE/IB School",
        "naac_grade": "ICSE / ISC / IB",
        "programs": ["ISC Science (Biology & Chemistry)", "IB Diploma Programme Biology HL"],
        "website": "cathedral-school.com",
        "established": 1860
    },
    {
        "id": "ind_sch_007",
        "name": "La Martiniere College / Girls' College",
        "city": "Lucknow / Kolkata",
        "state": "Uttar Pradesh / West Bengal",
        "category": "Heritage CISCE School",
        "type": "School",
        "nirf_rank": "Top Heritage Boarding/Day School",
        "naac_grade": "CISCE Affiliated",
        "programs": ["ISC Science Stream", "Computer Applications & Biotech Labs"],
        "website": "lamartiniere.org",
        "established": 1845
    },
    {
        "id": "ind_sch_008",
        "name": "Bishop Cotton School",
        "city": "Shimla",
        "state": "Himachal Pradesh",
        "category": "Heritage Boarding School",
        "type": "School",
        "nirf_rank": "Top All-Boys Boarding School",
        "naac_grade": "CISCE Affiliated",
        "programs": ["ISC Science & Technology", "Nature & Ecology Research Club"],
        "website": "bishopcottonshimla.com",
        "established": 1859
    },
    {
        "id": "ind_sch_009",
        "name": "Mayo College & Mayo College Girls' School",
        "city": "Ajmer",
        "state": "Rajasthan",
        "category": "Heritage Boarding School",
        "type": "School",
        "nirf_rank": "Top Residential School",
        "naac_grade": "CBSE Affiliated",
        "programs": ["Senior Secondary PCMB", "Environmental Science & Astronomy"],
        "website": "mayocollege.com",
        "established": 1875
    },
    {
        "id": "ind_sch_010",
        "name": "Army Public Schools (APS Network - 137+ Schools)",
        "city": "Pan-India Defence Hubs",
        "state": "National / Army Welfare Education",
        "category": "Defence Welfare K-12 Network",
        "type": "School",
        "nirf_rank": "Top Defence K-12 Network",
        "naac_grade": "CBSE Affiliated",
        "programs": ["Class XI-XII PCMB", "Artificial Intelligence & IP"],
        "website": "awesindia.com",
        "established": 1983
    }
]


class IndianInstitutionsDirectory:
    """Service to search, filter, and retrieve Indian Universities and Schools."""

    def __init__(self, data: Optional[List[Dict[str, Any]]] = None):
        self._data = data or INDIAN_INSTITUTIONS_DATABASE

    def search_institutions(
        self,
        query: str = "",
        type_filter: str = "All",
        category_filter: str = "All",
        state_filter: str = "All"
    ) -> List[Dict[str, Any]]:
        """Filter and search Indian universities and schools by query, type, category, and state."""
        results = []
        q_clean = query.strip().lower()

        for inst in self._data:
            # Type filter (University vs School)
            if type_filter != "All" and inst["type"] != type_filter:
                continue

            # Category filter
            if category_filter != "All" and category_filter.lower() not in inst["category"].lower():
                continue

            # State filter
            if state_filter != "All" and state_filter.lower() not in inst["state"].lower():
                continue

            # Search query matching
            if q_clean:
                searchable_text = f"{inst['name']} {inst['city']} {inst['state']} {inst['category']} {' '.join(inst['programs'])}".lower()
                if q_clean not in searchable_text:
                    continue

            results.append(inst)

        return results

    def get_states(self) -> List[str]:
        """Get unique sorted list of Indian States/UTs present in database."""
        states = sorted(list(set(inst["state"] for inst in self._data)))
        return ["All"] + states

    def get_categories(self) -> List[str]:
        """Get unique list of institution categories."""
        cats = sorted(list(set(inst["category"] for inst in self._data)))
        return ["All"] + cats
