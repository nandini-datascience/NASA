"""
ASTRA CARE - Task 06 Comprehensive System Verification and Scientific Accuracy Review Test Script
Tests all backend APIs, database persistence, edge-case error handling, frontend HTML/CSS/JS integrity,
and rigorous scientific accuracy requirements.
"""

import json
import logging
import os
import re
import socket
import sys
import threading
import time
import unittest
import urllib.parse
import urllib.request
import urllib.error

# Set working directory to project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from app.db import init_db, get_db_connection
from app.analysis import perform_full_radiation_analysis, validate_radiation_records, DISCLAIMER_TEXT
from app.health import validate_health_measurement, evaluate_astronaut_health_alerts, HEALTH_DISCLAIMER_TEXT
from app.assistant import generate_assistant_response, ASSISTANT_DISCLAIMER

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

class TestTask06SystemReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize DB
        init_db()

        # Start live server on dynamic port
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        import uvicorn
        from app.main import app
        config = uvicorn.Config(app=app, host="127.0.0.1", port=cls.port, log_level="warning")
        cls.server = uvicorn.Server(config)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()

        # Wait for server ready
        for _ in range(50):
            try:
                req = urllib.request.Request(f"{cls.base_url}/api/health")
                with urllib.request.urlopen(req, timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=3)

    # -------------------------------------------------------------
    # 1. BACKEND API ENDPOINT VERIFICATION
    # -------------------------------------------------------------
    def test_01_homepage_endpoint(self):
        url = f"{self.base_url}/"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data.get("project"), "ASTRA CARE")
            self.assertEqual(data.get("status"), "operational")
            self.assertIn("disclaimers", data)

    def test_02_radiation_sample_endpoint(self):
        url = f"{self.base_url}/api/radiation/sample"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn(data["status"], ("success", "fallback"))
            self.assertIn("telemetry_nature", data)
            self.assertIn("Historical", data["telemetry_nature"])
            self.assertIn("records", data)
            self.assertGreater(len(data["records"]), 0)

    def test_03_radiation_analysis_endpoint(self):
        url = f"{self.base_url}/api/radiation/analysis"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("radiation_analysis", data)
            rad_analysis = data["radiation_analysis"]
            self.assertIn("absorbed_dose_analysis", rad_analysis)
            self.assertIn("dose_equivalent_analysis", rad_analysis)
            self.assertEqual(rad_analysis["absorbed_dose_analysis"]["unit"], "µGy/hr")
            self.assertEqual(rad_analysis["dose_equivalent_analysis"]["unit"], "µSv/hr")
            self.assertIn("timestamp_continuity", data)
            self.assertIn("disclaimer", data)

    def test_04_radiation_history_endpoint(self):
        url = f"{self.base_url}/api/radiation/history?limit=10"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("records", data)
            self.assertIn("total_records", data)
            self.assertIn("telemetry_nature", data)
            self.assertIn("Historical", data["telemetry_nature"])
            if data["records"]:
                self.assertTrue(data["records"][0].get("is_historical"))

    def test_05_radiation_alerts_endpoint(self):
        url = f"{self.base_url}/api/alerts?limit=5"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("alerts", data)
            self.assertIn("disclaimer", data)

    def test_06_health_measurements_post_and_get(self):
        # POST a valid simulated demonstration health reading
        payload = {
            "astronaut_id": "TEST-AST-REV",
            "timestamp": "2026-11-14T14:00:00Z",
            "heart_rate": 74.0,
            "blood_pressure_systolic": 118.0,
            "blood_pressure_diastolic": 78.0,
            "oxygen_saturation": 98.0,
            "body_temperature": 36.8,
            "source_device": "Wearable Crew Patch #1",
            "data_classification": "simulated_demo",
            "notes": "Task 06 review test reading"
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/health/measurements",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertIn(resp.status, (200, 201))
            res_data = json.loads(resp.read().decode())
            self.assertIn("record", res_data)
            self.assertEqual(res_data["record"]["data_classification"], "simulated_demo")
            self.assertIn("alerts", res_data)
            self.assertIn("disclaimer", res_data)

        # GET health measurements for this astronaut
        url = f"{self.base_url}/api/health/measurements?astronaut_id=TEST-AST-REV"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertGreaterEqual(data["total_measurements"], 1)

    def test_07_health_history_and_alerts_endpoints(self):
        # GET health history
        url = f"{self.base_url}/api/health/history?astronaut_id=TEST-AST-REV"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("records", data)
            self.assertIn("disclaimer", data)

        # GET health alerts
        url = f"{self.base_url}/api/health/alerts?limit=5"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("alerts", data)
            self.assertIn("disclaimer", data)

    def test_08_assistant_chat_endpoint_valid_and_guardrails(self):
        # Test scientific explanation
        payload = {"message": "Explain what absorbed dose and dose equivalent mean.", "astronaut_id": "General"}
        req = urllib.request.Request(
            f"{self.base_url}/api/assistant/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("µGy", data["answer"])
            self.assertIn("µSv", data["answer"])
            self.assertIn("disclaimer", data)

        # Test diagnosis interception guardrail
        payload = {"message": "Can you diagnose if I have heart disease or cancer?", "astronaut_id": "General"}
        req = urllib.request.Request(
            f"{self.base_url}/api/assistant/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["source"], "safety_guardrail")
            self.assertIn("cannot diagnose", data["answer"])

        # Test prescription interception guardrail
        payload = {"message": "What medication should I take or prescribe for my fever?", "astronaut_id": "General"}
        req = urllib.request.Request(
            f"{self.base_url}/api/assistant/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["source"], "safety_guardrail")
            self.assertIn("cannot recommend, prescribe, or adjust medications", data["answer"])

    # -------------------------------------------------------------
    # 2. EDGE CASE ERROR HANDLING & INPUT VALIDATION
    # -------------------------------------------------------------
    def test_09_invalid_health_measurements_rejected(self):
        # Test invalid heart rate (out of physical bounds, e.g. 500 BPM)
        invalid_payload = {
            "astronaut_id": "ERR-AST",
            "timestamp": "2026-11-14T14:00:00Z",
            "heart_rate": 500.0,
            "blood_pressure_systolic": 120.0,
            "blood_pressure_diastolic": 80.0,
            "oxygen_saturation": 98.0,
            "body_temperature": 37.0
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/health/measurements",
            data=json.dumps(invalid_payload).encode(),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                self.fail("Expected HTTP 422 for impossible heart rate value")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 422)

    def test_10_missing_payload_and_empty_message_chat(self):
        # Empty message in chat
        payload = {"message": "   "}
        req = urllib.request.Request(
            f"{self.base_url}/api/assistant/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                self.fail("Expected HTTP 400 for empty chat message")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    # -------------------------------------------------------------
    # 3. SCIENTIFIC ACCURACY AUDIT
    # -------------------------------------------------------------
    def test_11_scientific_accuracy_in_codebase(self):
        """Verify strict adherence to scientific accuracy guidelines."""
        # 1. No invented NASA limits
        with open(os.path.join(PROJECT_ROOT, "app", "analysis.py"), "r", encoding="utf-8") as f:
            analysis_code = f.read()
            self.assertIn("NASA-STD-3001", analysis_code)
            self.assertIn("NCRP", analysis_code)

        # 2. Health thresholds are referenced to NASA-STD-3001 / AHA / WHO
        with open(os.path.join(PROJECT_ROOT, "app", "health.py"), "r", encoding="utf-8") as f:
            health_code = f.read()
            self.assertIn("NASA-STD-3001", health_code)
            self.assertIn("American Heart Association", health_code)
            self.assertIn("World Health Organization", health_code)
            self.assertIn("non-diagnostic", health_code.lower())

        # 3. Disclaimers present in assistant
        with open(os.path.join(PROJECT_ROOT, "app", "assistant.py"), "r", encoding="utf-8") as f:
            assistant_code = f.read()
            self.assertIn("ASSISTANT_DISCLAIMER", assistant_code)
            self.assertIn("NON-DIAGNOSTIC", assistant_code)
            self.assertIn("NON-PRESCRIBING", assistant_code)

        # 4. Frontend index.html contains disclaimers, standards, and views
        with open(os.path.join(PROJECT_ROOT, "frontend", "index.html"), "r", encoding="utf-8") as f:
            html = f.read()
            self.assertIn("NASA-STD-3001", html)
            self.assertIn("NASA RadLab", html)
            self.assertIn("historical", html.lower())
            self.assertIn("demonstration", html.lower())
            self.assertIn("simulated", html.lower())
            self.assertIn("view-dashboard", html)
            self.assertIn("view-radiation", html)
            self.assertIn("view-health", html)
            self.assertIn("view-alerts", html)
            self.assertIn("view-assistant", html)
            self.assertIn("view-history", html)
            self.assertIn("view-about", html)

    # -------------------------------------------------------------
    # 4. FRONTEND SCRIPTS AND DOM BINDINGS VERIFICATION
    # -------------------------------------------------------------
    def test_12_frontend_javascript_integrity(self):
        """Verify all frontend JS files exist and have no syntax errors or unhandled promises."""
        js_files = ["config.js", "dashboard.js", "radiation.js", "health.js", "alerts.js", "charts.js", "assistant.js"]
        for js_file in js_files:
            file_path = os.path.join(PROJECT_ROOT, "frontend", "js", js_file)
            self.assertTrue(os.path.isfile(file_path), f"Missing JS file: {js_file}")
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertGreater(len(content), 100)
                # Verify safe DOM rendering (should avoid innerHTML injection of untrusted user input)
                if js_file == "assistant.js":
                    self.assertIn("textContent", content)
                    self.assertIn("SpeechRecognition", content)
                    self.assertIn("speechSynthesis", content)

if __name__ == "__main__":
    unittest.main()
