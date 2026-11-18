"""
Unit and integration tests for Universal Neuro Data Fabric
"""

import sys
import os
import unittest
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.neuro_data_fabric import UniversalNeuroDataFabric, SUPPORTED_FORMATS

class TestNeuroDataFabric(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.fabric = UniversalNeuroDataFabric(self.tmp_dir)

    def test_format_support_count(self):
        self.assertEqual(len(SUPPORTED_FORMATS), 20)

    def test_checksum_calculation(self):
        sample_file = os.path.join(self.tmp_dir, "test.txt")
        with open(sample_file, "wb") as f:
            f.write(b"BioIntel AI Data Fabric Test Bytes")
        checksum = self.fabric.calculate_file_checksum(sample_file)
        self.assertEqual(len(checksum), 64)

    def test_format_detection(self):
        sample_csv = os.path.join(self.tmp_dir, "data.csv")
        with open(sample_csv, "w") as f:
            f.write("id,value\n1,10\n")
        fmt = self.fabric.detect_format(sample_csv)
        self.assertEqual(fmt, "CSV_TSV")

    def test_phi_scan(self):
        sample_csv = os.path.join(self.tmp_dir, "phi.csv")
        with open(sample_csv, "w") as f:
            f.write("patient_name,ssn\nJohn Doe,123-45-6789\n")
        rep = self.fabric.scan_phi_deidentify(sample_csv)
        self.assertTrue(rep.phi_detected)
        self.assertIn(rep.risk_score, ["MEDIUM", "HIGH"])

    def test_bids_validation(self):
        rep = self.fabric.validate_bids_or_nwb(self.tmp_dir, "BIDS")
        self.assertFalse(rep.is_valid)

if __name__ == "__main__":
    unittest.main()
