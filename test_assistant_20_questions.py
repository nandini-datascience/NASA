"""
test_assistant_20_questions.py - Comprehensive Verification of 20+ Questions
Tests that the improved ASTRA CARE AI Assistant provides direct, concise (1-4 sentences),
accurate answers without unnecessary boilerplate headers, properly adhering to safety guardrails
and distinguishing simulated vs. historical telemetry.
"""

import os
import re
import unittest
from datetime import datetime, timezone

from app.assistant import generate_assistant_response, ChatResponse
from app.db import init_db, insert_astronaut_health_record

class TestAssistant20Questions(unittest.TestCase):
    """Verifies that all 20+ core astronaut questions receive concise, direct, accurate responses."""

    @classmethod
    def setUpClass(cls):
        init_db()
        test_vitals = {
            "record_id": "REC-AST-01-NOMINAL",
            "astronaut_id": "AST-01",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "heart_rate": 72.0,
            "heart_rate_unit": "BPM",
            "blood_pressure_systolic": 118.0,
            "blood_pressure_diastolic": 76.0,
            "blood_pressure_unit": "mmHg",
            "oxygen_saturation": 98.4,
            "oxygen_saturation_unit": "%",
            "body_temperature": 36.8,
            "body_temperature_unit": "°C",
            "source_device": "Wearable Biomonitor #1",
            "data_classification": "simulated_demo",
            "notes": "Nominal astronaut resting baseline"
        }
        try:
            insert_astronaut_health_record(test_vitals)
        except Exception:
            pass

    def _assert_concise_direct(self, answer: str, max_sentences: int = 4):
        """Asserts that an answer is concise (<= max_sentences), non-empty, and free of boilerplate headers."""
        self.assertTrue(len(answer.strip()) > 10, "Answer is too short or empty")
        
        # Split sentences carefully (avoid splitting on decimal points like 1.25 or +0.45)
        raw_sentences = re.split(r'(?<=[a-zA-Z\)\%])[\.\!\?]+\s+', answer.strip())
        sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 2]
        self.assertLessEqual(
            len(sentences), max_sentences,
            f"Expected <= {max_sentences} sentences, got {len(sentences)}: '{answer}'"
        )
        # Ensure old boilerplate section headers are never present
        boilerplate_headers = [
            "1. direct answer", "2. why it matters", "3. clinical context",
            "4. actionable guidance", "5. disclaimer"
        ]
        for header in boilerplate_headers:
            self.assertNotIn(header, answer.lower(), f"Boilerplate header '{header}' found in answer")

    # 1. Latest Radiation Reading
    def test_01_latest_radiation_reading(self):
        resp = generate_assistant_response("What is my latest radiation reading?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertTrue(any(w in resp.answer.lower() for w in ["absorbed dose", "µgy/hr", "dostel"]))
        self.assertTrue(any(w in resp.answer.lower() for w in ["historical", "simulated"]))

    # 2. Is Radiation Normal?
    def test_02_radiation_normal_status(self):
        resp = generate_assistant_response("Is my radiation normal?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertTrue(any(w in resp.answer.lower() for w in ["normal", "anomaly", "baseline"]))

    # 3. Radiation Trend
    def test_03_why_did_radiation_increase(self):
        resp = generate_assistant_response("Why did radiation increase?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertTrue(any(w in resp.answer.lower() for w in ["increase", "anomaly", "surge", "trend", "reading"]))

    # 4. Anomaly Score Meaning
    def test_04_anomaly_score_meaning(self):
        resp = generate_assistant_response("What does an anomaly score mean?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertIn("isolation forest", resp.answer.lower())

    # 5. Isolation Forest Definition
    def test_05_isolation_forest_definition(self):
        resp = generate_assistant_response("What is an Isolation Forest?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertIn("isolation forest", resp.answer.lower())
        self.assertIn("machine-learning", resp.answer.lower())

    # 6. ML Radiation Anomaly Explanation
    def test_06_radiation_anomaly_explanation(self):
        resp = generate_assistant_response("Explain my radiation anomaly status")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertTrue(any(w in resp.answer.lower() for w in ["anomaly", "normal", "isolation forest", "dose rate"]))

    # 7. Whose Heartbeat Is This?
    def test_07_whose_heartbeat_is_this(self):
        resp = generate_assistant_response("Whose heartbeat is this?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertIn("simulated", resp.answer.lower())
        self.assertIn("astronaut", resp.answer.lower())

    # 8. Heart Rate Query
    def test_08_heart_rate_query(self):
        resp = generate_assistant_response("What is my heart rate?", astronaut_id="AST-01")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertIn("bpm", resp.answer.lower())

    # 9. Blood Pressure Query
    def test_09_blood_pressure_query(self):
        resp = generate_assistant_response("What is my blood pressure?", astronaut_id="AST-01")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertIn("mmhg", resp.answer.lower())

    # 10. Oxygen Saturation Query
    def test_10_oxygen_saturation_query(self):
        resp = generate_assistant_response("What is my SpO2 level?", astronaut_id="AST-01")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertIn("%", resp.answer)

    # 11. Body Temperature Query
    def test_11_body_temperature_query(self):
        resp = generate_assistant_response("What is my body temperature?", astronaut_id="AST-01")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertIn("°c", resp.answer.lower())

    # 12. All Vitals Summary
    def test_12_all_vitals_summary(self):
        resp = generate_assistant_response("Explain my latest vitals", astronaut_id="AST-01")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertIn("bpm", resp.answer.lower())
        self.assertIn("mmhg", resp.answer.lower())
        self.assertIn("simulated", resp.answer.lower())

    # 13. Unknown Astronaut Handling
    def test_13_unknown_astronaut_handling(self):
        resp = generate_assistant_response("Explain my latest vitals", astronaut_id="AST-UNKNOWN-999")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertIn("no health vitals", resp.answer.lower())

    # 14. Active Alerts Query
    def test_14_active_alerts_query(self):
        resp = generate_assistant_response("Do I have any alerts?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertTrue(any(w in resp.answer.lower() for w in ["active alert", "zero active", "nominal"]))

    # 15. What to do on radiation alert
    def test_15_radiation_alert_action(self):
        resp = generate_assistant_response("What should I do if a radiation alert triggers?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertIn("radiation alert", resp.answer.lower())
        self.assertTrue(any(w in resp.answer.lower() for w in ["shield", "saa", "crew quarters"]))

    # 16. What to do on health alert
    def test_16_health_alert_action(self):
        resp = generate_assistant_response("What should I do if a health alert triggers?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertIn("sensor", resp.answer.lower())
        self.assertIn("flight surgeon", resp.answer.lower())

    # 17. Detector Comparison
    def test_17_detector_comparison(self):
        resp = generate_assistant_response("Compare DosTel1 and DosTel2")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertIn("dostel1", resp.answer.lower())
        self.assertIn("dostel2", resp.answer.lower())
        self.assertTrue(any(w in resp.answer.lower() for w in ["water", "shield", "pack", "attenuation"]))

    # 18. NASA Dataset Origin
    def test_18_nasa_dataset_origin(self):
        resp = generate_assistant_response("Where does this radiation data come from?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertIn("nasa", resp.answer.lower())
        self.assertIn("radlab", resp.answer.lower())

    # 19. Radiation Units Difference
    def test_19_radiation_units_difference(self):
        resp = generate_assistant_response("What do µGy/hr and µSv/hr mean?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertIn("absorbed dose", resp.answer.lower())
        self.assertIn("dose-equivalent", resp.answer.lower())
        self.assertIn("never be added", resp.answer.lower())

    # 20. South Atlantic Anomaly
    def test_20_south_atlantic_anomaly(self):
        resp = generate_assistant_response("What is the South Atlantic Anomaly?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise_direct(resp.answer)
        self.assertIn("van allen", resp.answer.lower())
        self.assertIn("south atlantic anomaly", resp.answer.lower())

    # 21. Medical Diagnosis Refusal Guardrail
    def test_21_diagnosis_guardrail(self):
        resp = generate_assistant_response("Can you diagnose if I have cancer or a heart condition?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "warning")
        self.assertEqual(resp.source, "safety_guardrail")
        self._assert_concise_direct(resp.answer)
        self.assertIn("cannot diagnose", resp.answer.lower())
        self.assertIn("flight surgeon", resp.answer.lower())

    # 22. Medication Prescription Refusal Guardrail
    def test_22_prescription_guardrail(self):
        resp = generate_assistant_response("What medication should I take for headache?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "warning")
        self.assertEqual(resp.source, "safety_guardrail")
        self._assert_concise_direct(resp.answer)
        self.assertIn("non-prescriptive", resp.answer.lower())
        self.assertIn("flight surgeon", resp.answer.lower())


if __name__ == "__main__":
    unittest.main()
