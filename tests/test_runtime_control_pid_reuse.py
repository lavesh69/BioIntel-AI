from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biointel.operations.runtime_control import stop_local_runtime


class RuntimeControlPidReuseTests(unittest.TestCase):
    def test_reused_unverified_pid_does_not_block_install_or_get_killed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            root = base / "release"
            runtime = base / "UserData" / "runtime_logs"
            root.mkdir()
            runtime.mkdir(parents=True)
            state_path = runtime / "biointel-running.json"
            state_path.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "app_root": str(root),
                        "supervisor_pid": 101,
                        "ui_pid": 0,
                        "api_pid": 202,
                        "worker_pid": 303,
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("biointel.operations.runtime_control.time.sleep"),
                patch(
                    "biointel.operations.runtime_control._pid_alive",
                    side_effect=lambda pid: pid in {101, 202, 303},
                ),
                patch("biointel.operations.runtime_control._owned_process", return_value=False),
                patch(
                    "biointel.operations.runtime_control._force_stop_verified",
                    side_effect=lambda role, pid, _root: {
                        "role": role,
                        "pid": pid,
                        "state": "refused-unverified-process",
                    },
                ) as force_stop,
            ):
                result = stop_local_runtime(
                    root,
                    base / "UserData",
                    graceful_timeout_seconds=1,
                )

            self.assertEqual(result["state"], "stopped")
            self.assertEqual(result["blocking_owned_processes"], {})
            self.assertFalse(state_path.exists())
            self.assertEqual(force_stop.call_count, 3)

    def test_verified_owned_process_still_blocks_when_stop_fails(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            root = base / "release"
            runtime = base / "UserData" / "runtime_logs"
            root.mkdir()
            runtime.mkdir(parents=True)
            state_path = runtime / "biointel-running.json"
            state_path.write_text(
                json.dumps({"app_root": str(root), "supervisor_pid": 404}),
                encoding="utf-8",
            )
            with (
                patch("biointel.operations.runtime_control.time.sleep"),
                patch("biointel.operations.runtime_control._pid_alive", return_value=True),
                patch("biointel.operations.runtime_control._owned_process", return_value=True),
                patch(
                    "biointel.operations.runtime_control._force_stop_verified",
                    return_value={"role": "supervisor", "pid": 404, "state": "stop-failed"},
                ),
            ):
                result = stop_local_runtime(root, base / "UserData", graceful_timeout_seconds=1)

            self.assertEqual(result["state"], "stop-requested")
            self.assertEqual(result["blocking_owned_processes"], {"supervisor": 404})
            self.assertTrue(state_path.exists())


    def test_corrupt_primary_state_uses_atomic_status_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            root = base / "release"
            runtime = base / "UserData" / "runtime_logs"
            root.mkdir()
            runtime.mkdir(parents=True)
            state_path = runtime / "biointel-running.json"
            status_path = runtime / "biointel-runtime-status.json"
            state_path.write_bytes(b"\0" * 1255)
            status_path.write_text(
                json.dumps(
                    {
                        "status": "ready",
                        "app_root": str(root),
                        "supervisor_pid": 0,
                        "ui_pid": 0,
                        "api_pid": 0,
                        "worker_pid": 0,
                    }
                ),
                encoding="utf-8",
            )

            result = stop_local_runtime(root, base / "UserData", graceful_timeout_seconds=1)

            self.assertEqual(result["state"], "stopped")
            self.assertEqual(result["state_path"], str(state_path))
            self.assertFalse(state_path.exists())
            self.assertTrue(status_path.exists())


if __name__ == "__main__":
    unittest.main()
