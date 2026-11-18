"""
Unit and integration tests for 3D Brain Cell & Spatial Atlas Studio
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.neuro_cns.brain_cell_spatial_atlas import BrainCellSpatialAtlasStudio

class TestBrainCellSpatialAtlas(unittest.TestCase):

    def setUp(self):
        self.studio = BrainCellSpatialAtlasStudio(str(ROOT))

    def test_atlas_connectors(self):
        status = self.studio.get_atlas_connector_status()
        self.assertIn("Allen Brain Atlas (ABA CCFv3)", status)
        self.assertIn("CELLxGENE Census", status)

    def test_3d_pointcloud_generation(self):
        cells = self.studio.generate_3d_brain_cell_pointcloud(num_cells=50)
        self.assertEqual(len(cells), 50)
        cell = cells[0]
        self.assertIsNotNone(cell.x)
        self.assertIsNotNone(cell.y)
        self.assertIsNotNone(cell.z)
        self.assertIn("UBERON:", cell.brain_region_uberon)

    def test_ligand_receptor_interactions(self):
        df = self.studio.compute_ligand_receptor_interactions(["Microglia", "Astrocytes"])
        self.assertGreater(len(df), 0)

    def test_mouse_to_human_mapping(self):
        df = self.studio.mouse_to_human_ortholog_mapping(["Grn", "Trem2"])
        self.assertEqual(len(df), 2)

if __name__ == "__main__":
    unittest.main()
