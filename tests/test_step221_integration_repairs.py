from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.services.clinical_trials_service import ClinicalTrialsService
from biointel.services.engine_license_service import VERIFICATION_REQUIRED, verify_license_key
from biointel.services.pdf_rag_service import DocumentExtractionError, PDFRAGService
from biointel.services.weather_environment_engine import WeatherEnvironmentEngine
from biointel.ui.navigation import PAGE_BY_KEY, catalogue_integrity


class FakeResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.payload = payload
        self.status = status
        self.headers: dict[str, str] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int | None = None) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class IntegrationRepairTests(unittest.TestCase):
    def test_release_gate_prefers_current_archive_manifest(self) -> None:
        scripts = ROOT / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        import step206_release_gate

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "release").mkdir()
            current = root / "release" / "SOURCE_MANIFEST_SHA256.json"
            current.write_text(
                json.dumps({"files": [{"path": "app.py", "size_bytes": 1, "sha256": "x"}]}),
                encoding="utf-8",
            )
            (root / "STEP220_SOURCE_MANIFEST_SHA256.json").write_text(
                json.dumps({"entries": [{"path": "legacy.py", "size_bytes": 1, "sha256": "y"}]}),
                encoding="utf-8",
            )
            path, rows = step206_release_gate._source_manifest_rows(root)
        self.assertEqual(path, current)
        self.assertEqual(rows[0]["path"], "app.py")

    def test_run_both_repairs_stale_or_incomplete_install(self) -> None:
        launcher = (ROOT / "RUN_BOTH_WINDOWS.bat").read_text(encoding="utf-8")
        self.assertIn(":ENSURE_CURRENT_INSTALL", launcher)
        self.assertIn("release\\SOURCE_MANIFEST_SHA256.json", launcher)
        self.assertIn("fc /b", launcher)
        self.assertIn(":INSTALL_CURRENT_RELEASE", launcher)

    def test_requested_pages_are_curated(self) -> None:
        expected = {
            "engine_license_compliance": "Administration",
            "lab_pdf_notebook_rag": "Documents",
            "live_clinical_trials": "Clinical Research",
            "system_health_connectivity_weather": "Connectivity & Environment",
        }
        self.assertEqual({key: PAGE_BY_KEY[key].category for key in expected}, expected)
        integrity = catalogue_integrity(ROOT)
        self.assertTrue(integrity["healthy"], integrity)
        for key in expected:
            self.assertFalse(PAGE_BY_KEY[key].key.startswith("auto_"))

    def test_license_prefix_is_not_accepted(self) -> None:
        result = verify_license_key("BIOINTEL-ANYTHING")
        self.assertFalse(result["valid"])
        self.assertEqual(result["verification_status"], VERIFICATION_REQUIRED)
        self.assertNotIn("BIOINTEL-ANYTHING", result["key"])

    def test_pdf_binary_is_not_decoded_or_fabricated(self) -> None:
        service = PDFRAGService()
        with self.assertRaises(DocumentExtractionError):
            service.extract_text_from_pdf_bytes(b"%PDF-1.4\nnot a valid PDF", "broken.pdf")
        self.assertEqual(service.chunks, [])

    def test_text_and_notebook_index_real_content(self) -> None:
        service = PDFRAGService()
        chunks = service.index_bytes(b"Cell lysis used buffer X and centrifugation.", "notes.md")
        self.assertIn("buffer X", chunks[0].content)
        result = service.query("cell lysis")
        self.assertTrue(result.evidence_found)
        no_evidence = service.query("unrelated-xylophone-token")
        self.assertFalse(no_evidence.evidence_found)
        notebook = {"cells": [{"cell_type": "markdown", "source": ["## Protocol\n", "Wash twice."]}]}
        nb_chunks = service.index_bytes(json.dumps(notebook).encode(), "lab.ipynb")
        self.assertEqual(nb_chunks[0].section, "Cell 1")

    def test_clinical_trials_failure_never_creates_fallback_trial(self) -> None:
        def fail(*_args, **_kwargs):
            raise urllib.error.URLError("offline")
        with tempfile.TemporaryDirectory() as directory:
            service = ClinicalTrialsService(directory, opener=fail, sleeper=lambda _value: None)
            records = service.search_trials("glioblastoma", limit=10)
        self.assertEqual(records, [])
        self.assertEqual(service.last_status, "ClinicalTrials.gov Unavailable")

    def test_unknown_location_never_becomes_new_delhi(self) -> None:
        def fail(*_args, **_kwargs):
            raise urllib.error.URLError("offline")
        with tempfile.TemporaryDirectory() as directory:
            engine = WeatherEnvironmentEngine(directory, opener=fail, sleeper=lambda _value: None)
            results = engine.geocode_location_search("this place does not exist")
        self.assertEqual(results, [])

    def test_weather_values_and_fahrenheit_are_provider_backed(self) -> None:
        hours = [f"2026-07-24T{hour:02d}:00" for hour in range(24)]
        forecast = {
            "timezone": "Asia/Kolkata",
            "elevation": 210,
            "current": {
                "time": hours[0], "temperature_2m": 20, "apparent_temperature": 18,
                "relative_humidity_2m": 60, "pressure_msl": 1009, "precipitation": 1.2,
                "rain": 1.2, "snowfall": 0, "weather_code": 61, "cloud_cover": 80,
                "wind_speed_10m": 12, "wind_direction_10m": 180, "wind_gusts_10m": 20,
            },
            "hourly": {
                "time": hours, "temperature_2m": [20] * 24, "apparent_temperature": [18] * 24,
                "dew_point_2m": [10] * 24, "relative_humidity_2m": [60] * 24,
                "precipitation_probability": [70] * 24, "precipitation": [1.2] * 24,
                "rain": [1.2] * 24, "snowfall": [0] * 24, "weather_code": [61] * 24,
                "visibility": [10000] * 24, "uv_index": [3] * 24,
                "wind_speed_10m": [12] * 24, "wind_direction_10m": [180] * 24,
                "wind_gusts_10m": [20] * 24,
            },
            "daily": {
                "time": ["2026-07-24"], "weather_code": [61], "temperature_2m_max": [25],
                "temperature_2m_min": [15], "apparent_temperature_max": [24],
                "apparent_temperature_min": [14], "sunrise": ["2026-07-24T05:30"],
                "sunset": ["2026-07-24T19:15"], "uv_index_max": [5],
                "precipitation_sum": [4], "rain_sum": [4], "snowfall_sum": [0],
                "precipitation_probability_max": [80], "wind_speed_10m_max": [22],
                "wind_gusts_10m_max": [30],
            },
        }
        aqi = {"current": {"time": hours[0], "us_aqi": 72, "european_aqi": 40,
            "pm2_5": 19, "pm10": 28, "ozone": 50, "nitrogen_dioxide": 17,
            "sulphur_dioxide": 3, "carbon_monoxide": 110}}
        def opener(request, **_kwargs):
            url = request.full_url
            return FakeResponse(aqi if "air-quality" in url else forecast)
        with tempfile.TemporaryDirectory() as directory:
            engine = WeatherEnvironmentEngine(directory, opener=opener, now=lambda: 1_753_315_200)
            result = engine.fetch_weather_and_forecast(28.6, 77.2, "Delhi", "Fahrenheit")
        self.assertEqual(result["current"]["temperature"], 68.0)
        self.assertEqual(result["current"]["feels_like"], 64.4)
        self.assertEqual(result["hourly_24h"][0]["dew_point"], 50.0)
        self.assertEqual(result["daily_7d"][0]["temp_max"], 77.0)
        self.assertEqual(result["air_quality"]["aqi_index"], 72.0)
        self.assertEqual(result["alerts_status"], "Official Weather Alerts Unavailable")


if __name__ == "__main__":
    unittest.main(verbosity=2)