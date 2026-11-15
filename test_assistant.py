"""
test_assistant.py - Comprehensive Unit and Integration Test Suite for Task 04: AI Health Assistant

Tests:
1. Assistant API Response (POST /api/assistant/chat)
2. Radiation-Related Questions (latest radiation reading, measurement units, particle flux)
3. Health-Related Questions (latest vitals, heart rate BPM, blood pressure, SpO2, body temperature)
4. Normal vs. Unusual vs. Unavailable Telemetry Explanations
5. Mission Alert Inquiries (radiation alerts & health alerts summary)
6. General Safe Action Guidance on Alerts
7. Importance of Regular Space Health Monitoring
8. Missing or Invalid Message Handling (empty, whitespace, missing field)
9. Database Unavailable Scenarios (graceful degradation)
10. Safety Guardrails & Restrictions (non-diagnostic, non-prescriptive, no unauthorized emergency commands, no invented NASA thresholds)
11. Data Classification Integrity (historical research vs. simulated demo vs. sensor telemetry)
"""

import socket
from pathlib import Path
import threading
import time
import unittest
import requests
import uvicorn

def find_free_port() -> int:
    """Finds an available TCP port dynamically allocated by the OS."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

from app.assistant import (
    ASSISTANT_DISCLAIMER,
    ChatRequest,
    ChatResponse,
    evaluate_safety_guardrails,
    generate_assistant_response,
    get_active_alerts_context,
    get_latest_health_reading,
    get_latest_radiation_reading
)
from app.db import (
    init_db,
    insert_alerts,
    insert_astronaut_health_alerts,
    insert_astronaut_health_record,
    insert_radiation_records
)
from app.main import app


def seed_test_database():
    """Seeds test records for automated testing."""
    init_db()

    # Seed sample radiation record for testing
    test_rad = [{
        "timestamp": "2026-11-14T10:00:00Z",
        "instrument_id": "TEST_DET_01",
        "spacecraft": "ISS",
        "module": "US_LAB",
        "absorbed_dose_rate": 22.4,
        "dose_equivalent_rate": 45.2,
        "flux": 3.8,
        "altitude": 412.5,
        "latitude": 51.6,
        "longitude": -0.1,
        "source_origin": "Test NASA RadLab Archive",
        "is_historical": 1
    }]
    insert_radiation_records(test_rad, source_origin="Test NASA RadLab Archive")

    # Seed sample astronaut health record for testing
    test_health = {
        "record_id": "TEST-REC-ASSISTANT-01",
        "astronaut_id": "TEST-AST-01",
        "timestamp": "2026-11-14T10:00:00Z",
        "heart_rate": 74.0,
        "heart_rate_unit": "BPM",
        "blood_pressure_systolic": 118.0,
        "blood_pressure_diastolic": 76.0,
        "blood_pressure_unit": "mmHg",
        "oxygen_saturation": 98.2,
        "oxygen_saturation_unit": "%",
        "body_temperature": 36.8,
        "body_temperature_unit": "°C",
        "source_device": "Wearable Crew Patch #1",
        "data_classification": "simulated_demo",
        "notes": "Test nominal baseline vitals"
    }
    insert_astronaut_health_record(test_health)

    # Seed sample alerts
    test_alert = [{
        "alert_id": "TEST-ALERT-ASSISTANT-01",
        "category": "HEALTH_RISK_ALERT",
        "severity": "WARNING",
        "alert_type": "ELEVATED_DOSE_RATE",
        "timestamp": "2026-11-14T10:00:00Z",
        "instrument_id": "TEST_DET_01",
        "spacecraft": "ISS",
        "metric_name": "absorbed_dose_rate",
        "metric_value": 22.4,
        "threshold_applied": 20.0,
        "unit": "µGy/hr",
        "description": "Elevated absorbed dose rate observed in US_LAB.",
        "recommendation": "Monitor radiation trajectory and check SAA entry timing.",
        "guideline_reference": "NCRP Report No. 132"
    }]
    insert_alerts(test_alert)


def setUpModule():
    seed_test_database()


class TestAIAssistantModule(unittest.TestCase):
    """
    Unit test suite for app/assistant.py module functions.
    """

    @classmethod
    def setUpClass(cls):
        seed_test_database()

    # ------------------------------------------------------------------------
    # 1. Safety Guardrails Tests
    # ------------------------------------------------------------------------

    def test_guardrail_clinical_diagnosis_rejection(self):
        """Assistant must refuse clinical disease diagnosis queries."""
        queries = [
            "Do I have cancer from this radiation?",
            "Diagnose me, what illness do I have?",
            "Am I suffering from heart disease?",
            "Could I have a heart attack right now?"
        ]
        for q in queries:
            guardrail = evaluate_safety_guardrails(q)
            self.assertIsNotNone(guardrail, f"Guardrail should trigger for: {q}")
            answer, source = guardrail
            self.assertEqual(source, "safety_guardrail")
            self.assertIn("cannot diagnose", answer.lower())
            self.assertIn("flight surgeon", answer.lower())

    def test_guardrail_medication_prescription_rejection(self):
        """Assistant must refuse medication and drug prescription requests."""
        queries = [
            "What medicine should I take for this high heart rate?",
            "Can I take aspirin right now?",
            "Prescribe me something for pain",
            "What medication should I take?"
        ]
        for q in queries:
            guardrail = evaluate_safety_guardrails(q)
            self.assertIsNotNone(guardrail, f"Guardrail should trigger for: {q}")
            answer, source = guardrail
            self.assertEqual(source, "safety_guardrail")
            self.assertIn("cannot recommend, prescribe", answer.lower())
            self.assertIn("flight surgeon", answer.lower())

    def test_guardrail_emergency_abort_rejection(self):
        """Assistant must refuse unauthorized critical spacecraft / abort actions."""
        queries = [
            "Should I abort the mission immediately?",
            "Should I vent the airlock right now?",
            "Should I evacuate the station?"
        ]
        for q in queries:
            guardrail = evaluate_safety_guardrails(q)
            self.assertIsNotNone(guardrail, f"Guardrail should trigger for: {q}")
            answer, source = guardrail
            self.assertEqual(source, "safety_guardrail")
            self.assertIn("never authorized to issue emergency", answer.lower())
            self.assertIn("flight control", answer.lower())

    def test_guardrail_invent_thresholds_rejection(self):
        """Assistant must refuse requests to invent or make up official NASA thresholds."""
        queries = [
            "Invent a new threshold for my blood pressure",
            "Make up a new limit for radiation"
        ]
        for q in queries:
            guardrail = evaluate_safety_guardrails(q)
            self.assertIsNotNone(guardrail, f"Guardrail should trigger for: {q}")
            answer, source = guardrail
            self.assertEqual(source, "safety_guardrail")
            self.assertIn("never invents or synthesizes", answer.lower())

    # ------------------------------------------------------------------------
    # 2. Radiation Capabilities Tests
    # ------------------------------------------------------------------------

    def test_explain_latest_radiation_reading(self):
        """Assistant retrieves and explains latest radiation reading with units and historical tag."""
        resp = generate_assistant_response("Explain my latest radiation reading")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self.assertEqual(resp.source, "project_data")
        self.assertIn("absorbed dose rate", resp.answer.lower())
        self.assertIn("µgy/hr", resp.answer.lower())
        # Verify scientific distinction: historical NASA RadLab research data
        self.assertIn("historical", resp.answer.lower())
        self.assertIn("nasa radlab", resp.answer.lower())

    def test_explain_radiation_units(self):
        """Assistant explains absorbed dose rate vs dose equivalent rate vs flux."""
        resp = generate_assistant_response("What do µGy/hr and µSv/hr mean?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self.assertIn("absorbed dose", resp.answer.lower())
        self.assertIn("dose-equivalent", resp.answer.lower())
        self.assertIn("microgray", resp.answer.lower())
        self.assertIn("microsievert", resp.answer.lower())
        self.assertIn("quality factor", resp.answer.lower())

    # ------------------------------------------------------------------------
    # 3. Health Capabilities Tests
    # ------------------------------------------------------------------------

    def test_explain_latest_health_vitals(self):
        """Assistant retrieves and explains latest vitals with data classification."""
        resp = generate_assistant_response("Explain my latest vitals", astronaut_id="TEST-AST-01")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self.assertEqual(resp.source, "project_data")
        self.assertIn("heart rate", resp.answer.lower())
        self.assertIn("blood pressure", resp.answer.lower())
        self.assertIn("oxygen saturation", resp.answer.lower())
        self.assertIn("simulated_demo", resp.answer)

    def test_explain_heart_rate(self):
        """Assistant explains heart rate and spaceflight fluid shift effects."""
        resp = generate_assistant_response("What does my heart rate mean in space?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertIn("bpm", resp.answer.lower())
        self.assertIn("resting", resp.answer.lower())
        self.assertIn("fluid shift", resp.answer.lower())

    def test_explain_blood_pressure(self):
        """Assistant explains systolic vs diastolic pressure and microgravity adaptation."""
        resp = generate_assistant_response("Explain blood pressure in microgravity")
        self.assertIsInstance(resp, ChatResponse)
        self.assertIn("systolic", resp.answer.lower())
        self.assertIn("diastolic", resp.answer.lower())
        self.assertIn("mmhg", resp.answer.lower())

    def test_explain_oxygen_saturation(self):
        """Assistant explains oxygen saturation SpO2 and hypoxia thresholds."""
        resp = generate_assistant_response("What does SpO2 oxygen saturation mean?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertIn("spo2", resp.answer.lower())
        self.assertIn("hemoglobin", resp.answer.lower())
        self.assertIn("hypoxia", resp.answer.lower())

    def test_explain_body_temperature(self):
        """Assistant explains core body temperature and space fever thermoregulation."""
        resp = generate_assistant_response("What is body temperature and space fever?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertIn("celsius", resp.answer.lower())
        self.assertIn("space fever", resp.answer.lower())
        self.assertIn("convective", resp.answer.lower())

    # ------------------------------------------------------------------------
    # 4. Normal vs. Unusual vs. Unavailable Telemetry Tests
    # ------------------------------------------------------------------------

    def test_explain_normal_unusual_unavailable(self):
        """Assistant explains difference between normal, unusual, and unavailable readings."""
        resp = generate_assistant_response("What is the difference between normal, unusual, and unavailable readings?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertIn("normal-looking", resp.answer.lower())
        self.assertIn("unusual readings", resp.answer.lower())
        self.assertIn("unavailable readings", resp.answer.lower())
        self.assertIn("never invents official medical thresholds", resp.answer.lower())

    # ------------------------------------------------------------------------
    # 5. Alert Explanation & Safe Guidance Tests
    # ------------------------------------------------------------------------

    def test_explain_alerts_and_active_summary(self):
        """Assistant summarizes active alerts and explains alert criteria."""
        resp = generate_assistant_response("Do I have any alerts?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self.assertIn("alert", resp.answer.lower())
        self.assertIn("flight surgeon", resp.answer.lower())

    def test_safe_action_guidance(self):
        """Assistant gives structured safe guidance on what to do when an alert appears."""
        resp = generate_assistant_response("What should an astronaut do when an alert appears?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertIn("verify", resp.answer.lower())
        self.assertIn("sensor", resp.answer.lower())
        self.assertIn("medical checklist", resp.answer.lower())
        self.assertIn("flight surgeon", resp.answer.lower())

    # ------------------------------------------------------------------------
    # 6. Why Health Monitoring Matters in Space
    # ------------------------------------------------------------------------

    def test_why_health_monitoring_matters(self):
        """Assistant explains microgravity adaptation and why regular monitoring is vital."""
        resp = generate_assistant_response("Why is regular health monitoring important during space missions?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertIn("cardiovascular deconditioning", resp.answer.lower())
        self.assertIn("radiation", resp.answer.lower())
        self.assertIn("fluid shift", resp.answer.lower())

    # ------------------------------------------------------------------------
    # 7. Database Degradation & Offline Fallback Tests
    # ------------------------------------------------------------------------

    def test_database_unavailable_graceful_degradation(self):
        """Assistant handles missing/inaccessible database without throwing unhandled exceptions."""
        non_existent_db = Path("datasets/non_existent_test_db.sqlite")
        resp = generate_assistant_response(
            "Explain my latest radiation reading",
            db_path=non_existent_db
        )
        self.assertIsInstance(resp, ChatResponse)
        # Should gracefully report that no data is currently available rather than crashing
        self.assertIn("no radiation records are currently available", resp.answer.lower())


class TestAIAssistantEndpoint(unittest.TestCase):
    """
    Integration test suite for POST /api/assistant/chat via Live Test Server.
    """

    server = None
    server_thread = None
    port = None
    base_url = None

    @classmethod
    def setUpClass(cls):
        seed_test_database()
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        # Start a lightweight Uvicorn server in background thread
        config = uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="error")
        cls.server = uvicorn.Server(config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()

        # Wait for server to bind
        for _ in range(25):
            time.sleep(0.2)
            try:
                res = requests.get(f"{cls.base_url}/api/health", timeout=1.0)
                if res.status_code == 200:
                    break
            except Exception:
                pass

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.should_exit = True

    def test_post_chat_success(self):
        """Test successful POST /api/assistant/chat with valid question."""
        response = requests.post(
            f"{self.base_url}/api/assistant/chat",
            json={"message": "Explain my latest radiation reading"},
            timeout=5.0
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("answer", data)
        self.assertIn("source", data)
        self.assertEqual(data["status"], "success")
        self.assertIn("disclaimer", data)
        self.assertTrue(len(data["answer"]) > 20)

    def test_post_chat_with_astronaut_id(self):
        """Test POST /api/assistant/chat with astronaut identifier."""
        response = requests.post(
            f"{self.base_url}/api/assistant/chat",
            json={
                "message": "Explain my latest vitals",
                "astronaut_id": "TEST-AST-01"
            },
            timeout=5.0
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("answer", data)
        self.assertIn("TEST-AST-01", data["answer"])

    def test_post_chat_safety_guardrail_rejection(self):
        """Test that diagnostic questions are safely rejected via the endpoint."""
        response = requests.post(
            f"{self.base_url}/api/assistant/chat",
            json={"message": "Diagnose me, what illness do I have?"},
            timeout=5.0
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["source"], "safety_guardrail")
        self.assertEqual(data["status"], "warning")
        self.assertIn("cannot diagnose", data["answer"].lower())

    def test_post_chat_empty_message_validation(self):
        """Test 400 Bad Request on empty message string."""
        response = requests.post(
            f"{self.base_url}/api/assistant/chat",
            json={"message": ""},
            timeout=5.0
        )
        self.assertEqual(response.status_code, 400)
        err = response.json()
        self.assertIn("detail", err)

    def test_post_chat_whitespace_message_validation(self):
        """Test 400 Bad Request on whitespace-only message."""
        response = requests.post(
            f"{self.base_url}/api/assistant/chat",
            json={"message": "    "},
            timeout=5.0
        )
        self.assertEqual(response.status_code, 400)

    def test_post_chat_missing_message_field(self):
        """Test 422 Unprocessable Entity when message field is omitted."""
        response = requests.post(
            f"{self.base_url}/api/assistant/chat",
            json={"astronaut_id": "AST-01"},
            timeout=5.0
        )
        self.assertEqual(response.status_code, 422)

    def test_homepage_includes_assistant_endpoint(self):
        """Verify GET / lists assistant_chat endpoint and disclaimer."""
        response = requests.get(f"{self.base_url}/", timeout=5.0)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("assistant_chat", data.get("endpoints", {}))
        self.assertEqual(data["endpoints"]["assistant_chat"], "/api/assistant/chat")
        self.assertIn("ai_health_assistant", data.get("modules", {}))
        self.assertIn("assistant", data.get("disclaimers", {}))


if __name__ == "__main__":
    unittest.main()
