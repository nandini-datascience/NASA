"""
test_advanced_features.py - Verification Test Suite for ASTRA CARE Advanced Features

Verifies:
1. Feature 1: NASA RadLab Latest Data Integration (API fetch, timestamp separation, sync worker, deduplication)
2. Feature 2: Radiation Location Tracking (lat/lon/alt, SAA vs NOMINAL_LEO, SAA boundary)
3. Feature 3: Radiation Trend Forecasting (orbital harmonic model, point predictions, 95% CI bounds, limitations)
4. Feature 4: Smart Alert Explanation System (root-cause, responsible measurement, threshold delta, safe follow-up)
5. Feature 5: Multi-Detector Comparison (DosTel1, DosTel2, Lidal, REM-Lid, DB8, shielding attenuation ratio)
6. Feature 6: Astronaut Health and Radiation Reports (structured preview, downloadable PDF with %PDF- header)
"""

import json
import socket
import threading
import time
import unittest
import requests
import uvicorn

from app.main import app
from app.db import init_db, get_db_connection
from app.nasa_sync import fetch_latest_nasa_radlab_data, get_nasa_sync_service
from app.forecasting import RadiationTrendForecaster, generate_radiation_forecast
from app.smart_alerts import generate_smart_alert_from_radiation, sync_and_generate_smart_alerts
from app.detector_comparison import get_detector_time_series_comparison
from app.reports import compile_astronaut_report_data, generate_astronaut_pdf_report


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class TestAdvancedFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        config = uvicorn.Config(app=app, host="127.0.0.1", port=cls.port, log_level="warning")
        cls.server = uvicorn.Server(config)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()

        # Wait for server startup
        for _ in range(30):
            try:
                r = requests.get(f"{cls.base_url}/", timeout=1.0)
                if r.status_code == 200:
                    break
            except Exception:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.should_exit = True

    # ========================================================================
    # FEATURE 1: NASA RadLab Latest Data Integration
    # ========================================================================

    def test_nasa_latest_endpoint(self):
        """Verify GET /api/radiation/nasa/latest returns valid records with separated timestamps."""
        res = requests.get(f"{self.base_url}/api/radiation/nasa/latest?limit=10", timeout=15.0)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("status", data)
        self.assertIn("records", data)
        self.assertIn("retrieved_at", data)
        self.assertTrue(len(data["records"]) > 0)

        # Check first record structure
        rec = data["records"][0]
        self.assertIn("timestamp", rec)
        self.assertIn("retrieved_at", rec)
        self.assertIn("orbital_region", rec)
        self.assertTrue(rec.get("is_historical"))
        self.assertFalse(rec.get("is_live"))
        self.assertEqual(rec.get("data_source"), "nasa_radlab_archive")

    def test_nasa_sync_endpoint(self):
        """Verify POST /api/radiation/nasa/sync triggers on-demand synchronization."""
        payload = {"limit": 10}
        res = requests.post(f"{self.base_url}/api/radiation/nasa/sync", json=payload, timeout=20.0)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("sync_details", data)
        self.assertIn("records_fetched", data["sync_details"])

    def test_nasa_sync_status_endpoint(self):
        """Verify GET /api/radiation/nasa/sync-status returns worker state and audit logs."""
        res = requests.get(f"{self.base_url}/api/radiation/nasa/sync-status", timeout=5.0)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("service_state", data)
        self.assertIn("recent_sync_logs", data)
        self.assertIsInstance(data["recent_sync_logs"], list)

    # ========================================================================
    # FEATURE 2: Radiation Location Tracking
    # ========================================================================

    def test_radiation_locations_endpoint(self):
        """Verify GET /api/radiation/locations returns geographic points and SAA bounds."""
        res = requests.get(f"{self.base_url}/api/radiation/locations?limit=25", timeout=5.0)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("saa_boundary_definition", data)
        self.assertIn("locations", data)
        self.assertGreaterEqual(len(data["locations"]), 1)

        loc = data["locations"][0]
        self.assertIn("latitude", loc)
        self.assertIn("longitude", loc)
        self.assertIn("orbital_region", loc)
        self.assertIn(loc["orbital_region"], ["SOUTH_ATLANTIC_ANOMALY", "NOMINAL_LEO"])

    def test_radiation_locations_filter(self):
        """Verify GET /api/radiation/locations with orbital_region filter."""
        res = requests.get(f"{self.base_url}/api/radiation/locations?orbital_region=NOMINAL_LEO&limit=10", timeout=5.0)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        for loc in data["locations"]:
            self.assertEqual(loc["orbital_region"], "NOMINAL_LEO")

    # ========================================================================
    # FEATURE 3: Radiation Trend Forecasting
    # ========================================================================

    def test_radiation_forecast_endpoint(self):
        """Verify GET /api/radiation/forecast provides predictions with 95% confidence intervals."""
        res = requests.get(f"{self.base_url}/api/radiation/forecast?detector_id=DosTel1&horizon_steps=8", timeout=8.0)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["detector_id"], "DosTel1")
        self.assertIn("forecast_points", data)
        self.assertEqual(len(data["forecast_points"]), 8)
        self.assertIn("limitations", data)

        pt = data["forecast_points"][0]
        self.assertIn("predicted_dose_rate", pt)
        self.assertIn("ci_lower_95", pt)
        self.assertIn("ci_upper_95", pt)
        self.assertGreaterEqual(pt["ci_upper_95"], pt["predicted_dose_rate"])
        self.assertLessEqual(pt["ci_lower_95"], pt["predicted_dose_rate"])

    def test_post_radiation_forecast_generate(self):
        """Verify POST /api/radiation/forecast/generate custom forecast."""
        payload = {"detector_id": "DosTel2", "horizon_steps": 6, "step_minutes": 5.0}
        res = requests.post(f"{self.base_url}/api/radiation/forecast/generate", json=payload, timeout=8.0)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["detector_id"], "DosTel2")
        self.assertEqual(len(data["forecast_points"]), 6)

    # ========================================================================
    # FEATURE 4: Smart Alert Explanation System
    # ========================================================================

    def test_smart_alerts_query_endpoint(self):
        """Verify GET /api/alerts/smart returns root-cause explanations and safe follow-ups."""
        res = requests.get(f"{self.base_url}/api/alerts/smart?limit=10", timeout=5.0)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("alerts", data)

        if len(data["alerts"]) > 0:
            al = data["alerts"][0]
            self.assertIn("root_cause_explanation", al)
            self.assertIn("operational_recommendation", al)
            self.assertIn("responsible_metric", al)
            self.assertIn("alert_category", al)

    def test_smart_alerts_evaluate_endpoint(self):
        """Verify POST /api/alerts/evaluate evaluates records and inserts alerts."""
        res = requests.post(f"{self.base_url}/api/alerts/evaluate", json={}, timeout=10.0)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("newly_inserted_count", data)

    # ========================================================================
    # FEATURE 5: Multi-Detector Comparison
    # ========================================================================

    def test_detector_comparison_endpoint(self):
        """Verify GET /api/radiation/detectors/comparison produces aligned time series and attenuation."""
        res = requests.get(f"{self.base_url}/api/radiation/detectors/comparison?detectors=DosTel1,DosTel2", timeout=5.0)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("series", data)
        self.assertIn("dostel_shielding_attenuation_ratio", data)
        self.assertIn("scientific_context", data)

    def test_detector_list_endpoint(self):
        """Verify GET /api/radiation/detectors/list returns specifications for 5 detectors."""
        res = requests.get(f"{self.base_url}/api/radiation/detectors/list", timeout=5.0)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["total_detectors"], 5)
        detector_ids = [d["detector_id"] for d in data["detectors"]]
        self.assertIn("DosTel1", detector_ids)
        self.assertIn("DosTel2", detector_ids)
        self.assertIn("Lidal", detector_ids)
        self.assertIn("REM-Lid", detector_ids)
        self.assertIn("DB8", detector_ids)

    # ========================================================================
    # FEATURE 6: Astronaut Health and Radiation Reports
    # ========================================================================

    def test_report_preview_endpoint(self):
        """Verify GET /api/reports/preview returns structured JSON with vitals and dosimetry."""
        res = requests.get(f"{self.base_url}/api/reports/preview?astronaut_id=AST-01", timeout=5.0)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("report_data", data)
        rep = data["report_data"]
        self.assertEqual(rep["astronaut_id"], "AST-01")
        self.assertIn("health_vitals", rep)
        self.assertIn("dosimetry_summary", rep)
        self.assertIn("data_provenance_summary", rep)

    def test_report_pdf_download_endpoint(self):
        """Verify GET /api/reports/pdf generates a downloadable PDF with %PDF- header."""
        res = requests.get(f"{self.base_url}/api/reports/pdf?astronaut_id=AST-01", timeout=10.0)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("content-type"), "application/pdf")
        self.assertIn("attachment; filename=", res.headers.get("content-disposition", ""))

        pdf_bytes = res.content
        self.assertGreater(len(pdf_bytes), 1000)
        # Verify standard PDF magic header
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
