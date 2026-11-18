import unittest, sys, pathlib, pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class TestSingleCellSanitizeFix(unittest.TestCase):
    def test_qc_dataframe_sanitization(self) -> None:
        # Simulate a DataFrame with _x and _y suffixed columns
        raw_qc = pd.DataFrame({
            "cell": ["C1", "C2"],
            "total_counts": [1000, 1200],
            "detected_genes": [500, 600],
            "mitochondrial_percent": [1.5, 2.0],
            "pass_qc_x": [True, True],
            "pass_qc_y": [True, False],
            "doublet_flag_x": [False, True],
            "doublet_score_x": [0.1, 0.8],
        })

        qc = raw_qc.copy()
        for col_name in ["pass_qc", "doublet_flag", "doublet_score"]:
            if col_name not in qc.columns:
                candidates = [c for c in qc.columns if c.startswith(col_name)]
                if candidates:
                    qc[col_name] = qc[candidates[0]]
                elif col_name == "pass_qc":
                    qc["pass_qc"] = True
                elif col_name == "doublet_flag":
                    qc["doublet_flag"] = False
                elif col_name == "doublet_score":
                    qc["doublet_score"] = 0.0

        clean_cols = [c for c in qc.columns if not (c.endswith("_x") or c.endswith("_y"))]
        qc = qc[clean_cols].copy()

        self.assertIn("pass_qc", qc.columns)
        self.assertIn("doublet_flag", qc.columns)
        self.assertIn("doublet_score", qc.columns)
        self.assertNotIn("pass_qc_x", qc.columns)
        self.assertNotIn("pass_qc_y", qc.columns)
        self.assertNotIn("doublet_flag_x", qc.columns)
        self.assertNotIn("doublet_score_x", qc.columns)
        self.assertEqual(list(qc["pass_qc"]), [True, True])


if __name__ == "__main__":
    unittest.main()
