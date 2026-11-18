"""
Unit and integration tests for Native Neural Electrophysiology & Spike-Sorting Center
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.electrophysiology.spike_sorting_center import SpikeSortingCenter

class TestSpikeSortingCenter(unittest.TestCase):

    def setUp(self):
        self.center = SpikeSortingCenter(str(ROOT))

    def test_sorters_matrix(self):
        adapters = self.center.get_sorter_adapters_status()
        self.assertIn("SpikeInterface", adapters)
        self.assertIn("Kilosort (v4.0)", adapters)
        self.assertTrue(adapters["SpikeInterface"].installed)

    def test_probe_geometry(self):
        probe = self.center.get_probe_geometry("Neuropixels 1.0")
        self.assertEqual(probe.num_channels, 384)
        self.assertEqual(len(probe.channel_positions_um), 384)

    def test_spike_sorting_pipeline(self):
        res = self.center.run_spike_sorting_pipeline("SpikeInterface", "Neuropixels 1.0", 10.0)
        self.assertGreater(len(res["units"]), 0)
        self.assertIn("cell_type", res["units"][0])

if __name__ == "__main__":
    unittest.main()
