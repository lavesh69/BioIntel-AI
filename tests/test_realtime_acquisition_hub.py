"""
Unit and integration tests for Real-Time Multimodal Acquisition & Closed-Loop Hub
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

from biointel.acquisition.realtime_acquisition_hub import RealTimeAcquisitionHub

class TestRealTimeAcquisitionHub(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.hub = RealTimeAcquisitionHub(self.tmp_dir)

    def test_stream_discovery(self):
        streams = RealTimeAcquisitionHub.discover_active_streams()
        self.assertGreater(len(streams), 0)
        self.assertEqual(streams[0].protocol, "Open_Ephys_Socket")

    def test_ring_buffer_health(self):
        health = self.hub.get_ring_buffer_health()
        self.assertGreater(health.buffer_capacity_samples, 0)
        self.assertLess(health.latency_end_to_end_ms, 5.0)

    def test_closed_loop_command_and_human_approval(self):
        cmd = self.hub.request_outbound_command("STIM_UNIT_01", "STIMULATION_PULSE", {"current_ma": 1.5})
        self.assertEqual(cmd.approval_status, "PENDING_HUMAN_APPROVAL")
        
        approved = self.hub.approve_command(cmd.command_id, "Dr. Dobriyal")
        self.assertEqual(approved.approval_status, "APPROVED")

    def test_emergency_stop(self):
        cmd = self.hub.request_outbound_command("STIM_UNIT_01", "STIMULATION_PULSE", {"current_ma": 1.5})
        res = self.hub.trigger_emergency_stop()
        self.assertEqual(res["status"], "EMERGENCY_STOPPED")
        
        with self.assertRaises(RuntimeError):
            self.hub.request_outbound_command("STIM_UNIT_01", "STIMULATION_PULSE", {"current_ma": 1.5})

if __name__ == "__main__":
    unittest.main()
