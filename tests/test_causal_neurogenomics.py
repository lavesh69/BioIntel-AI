"""
Unit and integration tests for Causal Neurogenomics & Target Discovery
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.neuro_cns.causal_neurogenomics import CausalNeurogenomicsStudio, HarmonizedVariant

try:
    import pandas as pd
except ImportError:
    pd = None

class TestCausalNeurogenomics(unittest.TestCase):

    def setUp(self):
        self.studio = CausalNeurogenomicsStudio(str(ROOT))

    def test_gwas_harmonization(self):
        if pd is not None:
            df = pd.DataFrame([
                {"rsid": "rs5848", "chr": "17", "bp": 44358617, "ea": "T", "oa": "C", "beta": 0.38, "se": 0.04, "pvalue": 1e-10}
            ])
            harmonized = self.studio.intake_and_harmonize_gwas(df, "GRCh38")
            self.assertEqual(len(harmonized), 1)
            self.assertEqual(harmonized[0].variant_id, "rs5848")
            self.assertEqual(harmonized[0].genome_build, "GRCh38")

    def test_mendelian_randomization(self):
        instruments = [
            HarmonizedVariant("v1", "17", 44358617, "T", "C", 0.25, 0.38, 0.04, 1e-10, "GRCh38", True),
            HarmonizedVariant("v2", "7", 12854911, "C", "T", 0.30, -0.24, 0.03, 1e-8, "GRCh38", True)
        ]
        res = self.studio.calculate_mendelian_randomization(["Progranulin"], "FTD", instruments)
        self.assertEqual(res.num_instruments, 2)
        self.assertGreater(res.mean_f_statistic, 0)
        self.assertIsNotNone(res.provenance)

    def test_seven_tier_graph(self):
        nodes, edges = self.studio.generate_seven_tier_causal_graph("GRN", "FTD")
        self.assertEqual(len(nodes), 7)
        self.assertEqual(len(edges), 6)
        tiers = [n.tier for n in nodes]
        self.assertIn("Variant", tiers)
        self.assertIn("Target", tiers)
        self.assertIn("Compound", tiers)

if __name__ == "__main__":
    unittest.main()
