"""
Unit and integration tests for Native Scientific Engine Runtime Center
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import unittest
from biointel.engines.engine_runtime_center import (
    ScientificEngineRuntimeCenter,
    detect_hardware_and_environment,
    TARGET_ENGINES
)

class TestEngineRuntimeCenter(unittest.TestCase):

    def setUp(self):
        self.center = ScientificEngineRuntimeCenter(str(ROOT))

    def test_target_engines_count(self):
        self.assertEqual(len(TARGET_ENGINES), 15)

    def test_environment_detection(self):
        env = detect_hardware_and_environment()
        self.assertIsNotNone(env.os_name)
        self.assertGreater(env.cpu_cores_logical, 0)
        self.assertGreater(env.ram_total_gb, 0.0)

    def test_probe_engine(self):
        status = self.center.probe_engine("NiBabel")
        self.assertIn(status.mode, ["NATIVE", "PROXY_SIMULATION", "UNAVAILABLE"])
        self.assertEqual(status.pinned_version, "5.3.2")

    def test_benchmark_qualification(self):
        res = self.center.run_benchmark_qualification("PyTorch")
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["duration_seconds"], 0.0)

    def test_diagnostics_report(self):
        report = self.center.export_diagnostics_report()
        self.assertIn("environment", report)
        self.assertIn("engine_statuses", report)
        self.assertEqual(len(report["engine_statuses"]), 15)

if __name__ == "__main__":
    unittest.main()
