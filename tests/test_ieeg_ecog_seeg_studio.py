"""
Unit and integration tests for iEEG, ECoG and SEEG Research Studio
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.electrophysiology.ieeg_ecog_seeg_studio import IntracranialEEGStudio, SAFETY_DISCLAIMER

class TestIntracranialEEGStudio(unittest.TestCase):

    def setUp(self):
        self.studio = IntracranialEEGStudio(str(ROOT))

    def test_contact_localization(self):
        contacts = self.studio.localize_seeg_ecog_contacts(32, "SEEG Depth Electrodes")
        self.assertEqual(len(contacts), 32)
        self.assertIsNotNone(contacts[0].x)
        self.assertIsNotNone(contacts[0].high_gamma_power_db)

    def test_phase_amplitude_coupling(self):
        pac = self.studio.compute_phase_amplitude_coupling()
        self.assertGreater(pac.modulation_index, 0)
        self.assertEqual(pac.safety_disclaimer, SAFETY_DISCLAIMER)

    def test_report_generation(self):
        rep = self.studio.generate_ieeg_analysis_report()
        self.assertIn("safety_boundary", rep)
        self.assertEqual(rep["safety_boundary"], SAFETY_DISCLAIMER)

if __name__ == "__main__":
    unittest.main()
