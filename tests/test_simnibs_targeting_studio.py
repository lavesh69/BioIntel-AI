"""
Unit and integration tests for Neuromodulation Simulation and Targeting Studio
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.neuromodulation.simnibs_targeting_studio import SimNIBSTargetingStudio, SIMULATION_LABEL

class TestSimNIBSTargetingStudio(unittest.TestCase):

    def setUp(self):
        self.studio = SimNIBSTargetingStudio(str(ROOT))

    def test_tissue_conductivities(self):
        tissues = self.studio.get_tissue_conductivities()
        self.assertEqual(len(tissues), 5)
        names = [t.name for t in tissues]
        self.assertIn("Scalp", names)
        self.assertIn("Gray Matter", names)

    def test_e_field_simulation(self):
        res = self.studio.solve_e_field_simulation("TMS_Figure8", "M1 Target", 1.5)
        self.assertGreater(res.peak_e_field_v_m, 0.0)
        self.assertEqual(res.safety_label, SIMULATION_LABEL)

    def test_e_field_spatial_grid(self):
        pts = self.studio.generate_e_field_spatial_grid(50)
        self.assertEqual(len(pts), 50)
        self.assertIn("e_field_v_m", pts[0])

if __name__ == "__main__":
    unittest.main()
