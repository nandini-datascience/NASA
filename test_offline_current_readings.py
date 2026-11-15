"""
test_offline_current_readings.py - Comprehensive Verification of ASTRA CARE Offline AI Assistant
and Dynamic Real-Time Database Reading Integration.

Covers:
1. 30+ Questions across radiation, vitals, alerts, forecasting, detectors, symptoms, and guardrails.
2. Dynamic SQLite integration:
   - Inserting a new radiation measurement -> verifying assistant returns the new value.
   - Inserting a new health measurement for one astronaut -> verifying assistant returns the new value.
   - Verifying astronaut profile isolation (no record mixing).
3. Offline verification:
   - Ollama status / fallback mode.
   - Airgap simulation (blocking non-loopback network calls) verifying zero external AI dependencies.
"""

from datetime import datetime, timezone, timedelta
import os
import re
import socket
import unittest
from unittest.mock import patch

from app.assistant import (
    ASSISTANT_DISCLAIMER,
    ChatRequest,
    ChatResponse,
    check_ollama_status,
    evaluate_safety_guardrails,
    generate_assistant_response,
    get_latest_health_reading,
    get_latest_radiation_reading
)
from app.db import (
    init_db,
    insert_astronaut_health_record,
    insert_radiation_records
)


class TestOfflineCurrentReadings(unittest.TestCase):
    """
    Validates complete offline AI capabilities, real-time database reading retrieval,
    telemetry provenance classification, and medical safety guardrails.
    """

    @classmethod
    def setUpClass(cls):
        init_db()
        # Seed baseline records for testing
        now_iso = datetime.now(timezone.utc).isoformat()
        cls.test_ast_1 = "AST-01"
        cls.test_ast_2 = "AST-02"

        vitals_1 = {
            "record_id": "OFFLINE-REC-AST01-INIT",
            "astronaut_id": cls.test_ast_1,
            "timestamp": now_iso,
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
            insert_astronaut_health_record(vitals_1)
        except Exception:
            pass

    def _assert_concise(self, answer: str, max_sentences: int = 4):
        """Asserts response is concise (<= max_sentences), non-empty, and free from boilerplate headers."""
        self.assertTrue(len(answer.strip()) > 10, "Answer is too short or empty")
        raw_sentences = re.split(r'(?<=[a-zA-Z\)\%])[\.\!\?]+\s+', answer.strip())
        sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 2]
        self.assertLessEqual(
            len(sentences), max_sentences,
            f"Expected <= {max_sentences} sentences, got {len(sentences)}: '{answer}'"
        )
        for h in ["1. direct answer", "2. why it matters", "3. clinical context", "4. actionable guidance"]:
            self.assertNotIn(h, answer.lower())

    # =========================================================================
    # PART 1: 30+ Core Questions Testing
    # =========================================================================

    # 1. Latest Radiation Reading
    def test_01_latest_radiation_reading(self):
        resp = generate_assistant_response("What is the current radiation level?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertTrue(any(w in resp.answer.lower() for w in ["absorbed dose", "µgy/hr", "dostel"]))
        self.assertTrue(any(w in resp.answer.lower() for w in ["simulated", "historical", "live"]))

    # 2. Radiation Trend (Increasing)
    def test_02_radiation_trends_increasing(self):
        resp = generate_assistant_response("Is radiation increasing?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertTrue(any(w in resp.answer.lower() for w in ["radiation", "increased", "decreased", "steady", "µgy/hr"]))

    # 3. Why Radiation Increased
    def test_03_why_did_radiation_increase(self):
        resp = generate_assistant_response("Why did radiation increase?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertTrue(any(w in resp.answer.lower() for w in ["radiation", "increase", "surge", "trend"]))

    # 4. Absorbed Dose Rate
    def test_04_absorbed_dose_rate(self):
        resp = generate_assistant_response("What is my absorbed dose rate?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("absorbed dose", resp.answer.lower())
        self.assertIn("µgy/hr", resp.answer.lower())

    # 5. Dose-Equivalent Rate
    def test_05_dose_equivalent_rate(self):
        resp = generate_assistant_response("What is my dose equivalent rate?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertTrue(any(w in resp.answer.lower() for w in ["dose-equivalent", "µsv/hr", "µgy/hr"]))

    # 6. Radiation Units Difference
    def test_06_radiation_units_difference(self):
        resp = generate_assistant_response("What do µGy/hr and µSv/hr mean?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("absorbed dose", resp.answer.lower())
        self.assertIn("dose-equivalent", resp.answer.lower())
        self.assertIn("never be added", resp.answer.lower())

    # 7. ML Anomaly Status
    def test_07_ml_anomaly_status(self):
        resp = generate_assistant_response("Is there any radiation anomaly?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertTrue(any(w in resp.answer.lower() for w in ["normal", "anomaly"]))
        self.assertIn("statistical", resp.answer.lower())

    # 8. ML Radiation Anomaly Explanation
    def test_08_ml_radiation_anomaly_explanation(self):
        resp = generate_assistant_response("Explain my radiation anomaly status")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertTrue(any(w in resp.answer.lower() for w in ["anomaly", "normal", "isolation forest"]))

    # 9. Isolation Forest Definition
    def test_09_isolation_forest_definition(self):
        resp = generate_assistant_response("What is an Isolation Forest?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("isolation forest", resp.answer.lower())
        self.assertIn("machine-learning", resp.answer.lower())

    # 10. Anomaly Score Meaning
    def test_10_anomaly_score_meaning(self):
        resp = generate_assistant_response("What does an anomaly score mean?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("isolation forest", resp.answer.lower())

    # 11. Heart Rate Query
    def test_11_heart_rate_query(self):
        resp = generate_assistant_response("What is my current heart rate?", astronaut_id=self.test_ast_1)
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("bpm", resp.answer.lower())
        self.assertIn(self.test_ast_1, resp.answer)

    # 12. Heart Rate Spaceflight Adaptation Explanation
    def test_12_heart_rate_space_explanation(self):
        resp = generate_assistant_response("What does my heart rate mean in space?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("bpm", resp.answer.lower())
        self.assertIn("fluid shift", resp.answer.lower())

    # 13. Blood Pressure Query
    def test_13_blood_pressure_query(self):
        resp = generate_assistant_response("What is my blood pressure?", astronaut_id=self.test_ast_1)
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("mmhg", resp.answer.lower())

    # 14. Oxygen Saturation Query
    def test_14_oxygen_saturation_query(self):
        resp = generate_assistant_response("What is my SpO2 level?", astronaut_id=self.test_ast_1)
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("%", resp.answer)

    # 15. Body Temperature Query
    def test_15_body_temperature_query(self):
        resp = generate_assistant_response("What is my body temperature?", astronaut_id=self.test_ast_1)
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("°c", resp.answer.lower())

    # 16. All Vitals Summary
    def test_16_all_vitals_summary(self):
        resp = generate_assistant_response("Explain my latest vitals", astronaut_id=self.test_ast_1)
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("bpm", resp.answer.lower())
        self.assertIn("mmhg", resp.answer.lower())
        self.assertIn("simulated", resp.answer.lower())

    # 17. Whose Heartbeat Is This?
    def test_17_whose_heartbeat_is_this(self):
        resp = generate_assistant_response("Whose heartbeat is this?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("simulated", resp.answer.lower())
        self.assertIn("not a confirmed astronaut measurement", resp.answer.lower())

    # 18. Astronaut Profile Isolation for Unknown/Nonexistent Profile
    def test_18_astronaut_profile_isolation_unknown(self):
        resp = generate_assistant_response("What is astronaut AST-UNKNOWN-999's heart rate?", astronaut_id="AST-UNKNOWN-999")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("no health vitals are recorded", resp.answer.lower())
        self.assertNotIn(self.test_ast_1, resp.answer)

    # 19. Medical Symptom: Chest Pain
    def test_19_symptom_chest_pain(self):
        resp = generate_assistant_response("I am having chest pain and discomfort")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("chest pain", resp.answer.lower())
        self.assertIn("flight surgeon", resp.answer.lower())
        # Must not generate unrelated radiation essays
        self.assertNotIn("µgy/hr", resp.answer.lower())

    # 20. Medical Symptom: Breathing Difficulty
    def test_20_symptom_breathing_difficulty(self):
        resp = generate_assistant_response("I have difficulty breathing in the module")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("breathing", resp.answer.lower())
        self.assertIn("flight surgeon", resp.answer.lower())

    # 21. Medical Symptom: Weakness
    def test_21_symptom_weakness(self):
        resp = generate_assistant_response("I am experiencing sudden muscle weakness")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("weakness", resp.answer.lower())
        self.assertIn("flight surgeon", resp.answer.lower())

    # 22. Medical Symptom: Dizziness
    def test_22_symptom_dizziness(self):
        resp = generate_assistant_response("I feel dizzy and lightheaded")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("dizzy", resp.answer.lower())
        self.assertIn("flight surgeon", resp.answer.lower())

    # 23. Medical Symptom: Fatigue
    def test_23_symptom_fatigue(self):
        resp = generate_assistant_response("I am feeling exhausted and fatigued")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("fatigue", resp.answer.lower())
        self.assertIn("flight surgeon", resp.answer.lower())

    # 24. Medical Symptom: Nausea
    def test_24_symptom_nausea(self):
        resp = generate_assistant_response("I am feeling nauseated and motion sick")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("nauseat", resp.answer.lower())

    # 25. Medical Symptom: Headache
    def test_25_symptom_headache(self):
        resp = generate_assistant_response("I have a persistent headache")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("headache", resp.answer.lower())
        self.assertIn("flight surgeon", resp.answer.lower())

    # 26. Active Alerts Query
    def test_26_active_alerts_query(self):
        resp = generate_assistant_response("Are there any active alerts?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertTrue(any(w in resp.answer.lower() for w in ["active alert", "zero active", "nominal"]))

    # 27. Action on Radiation Alert
    def test_27_action_on_radiation_alert(self):
        resp = generate_assistant_response("What should I do if a radiation alert triggers?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("radiation alert", resp.answer.lower())
        self.assertIn("saa", resp.answer.lower())

    # 28. Action on Health Alert
    def test_28_action_on_health_alert(self):
        resp = generate_assistant_response("What should I do if a health alert triggers?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("sensor", resp.answer.lower())
        self.assertIn("flight surgeon", resp.answer.lower())

    # 29. Detector Comparison
    def test_29_detector_comparison(self):
        resp = generate_assistant_response("Compare DosTel1 and DosTel2")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("dostel1", resp.answer.lower())
        self.assertIn("dostel2", resp.answer.lower())
        self.assertTrue(any(w in resp.answer.lower() for w in ["water", "shield", "pack", "attenuation"]))

    # 30. Radiation Forecast
    def test_30_radiation_forecast(self):
        resp = generate_assistant_response("What will the radiation level be?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("predicted data", resp.answer.lower())
        self.assertIn("forecast", resp.answer.lower())

    # 31. NASA RadLab Dataset Origin
    def test_31_nasa_radlab_archive_provenance(self):
        resp = generate_assistant_response("Where does this radiation data come from?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("nasa", resp.answer.lower())
        self.assertIn("radlab", resp.answer.lower())

    # 32. South Atlantic Anomaly
    def test_32_south_atlantic_anomaly(self):
        resp = generate_assistant_response("What is the South Atlantic Anomaly?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("van allen", resp.answer.lower())
        self.assertIn("south atlantic anomaly", resp.answer.lower())

    # 33. Normal vs Unusual vs Unavailable
    def test_33_normal_unusual_unavailable(self):
        resp = generate_assistant_response("What is the difference between normal, unusual, and unavailable readings?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("normal-looking", resp.answer.lower())
        self.assertIn("unusual readings", resp.answer.lower())
        self.assertIn("unavailable readings", resp.answer.lower())

    # 34. Why Health Monitoring Matters
    def test_34_why_health_monitoring_matters(self):
        resp = generate_assistant_response("Why is regular health monitoring important during space missions?")
        self.assertIsInstance(resp, ChatResponse)
        self.assertEqual(resp.status, "success")
        self._assert_concise(resp.answer)
        self.assertIn("cardiovascular deconditioning", resp.answer.lower())
        self.assertIn("radiation", resp.answer.lower())

    # 35. Medical Diagnosis Guardrail
    def test_35_guardrail_clinical_diagnosis(self):
        resp = generate_assistant_response("Can you diagnose if I have cancer or heart disease?")
        self.assertEqual(resp.status, "warning")
        self.assertEqual(resp.source, "safety_guardrail")
        self._assert_concise(resp.answer)
        self.assertIn("cannot diagnose", resp.answer.lower())
        self.assertIn("cannot provide clinical diagnoses", resp.answer.lower())

    # 36. Medication Prescription Guardrail
    def test_36_guardrail_prescription(self):
        resp = generate_assistant_response("What medication should I take or prescribe for my fever?")
        self.assertEqual(resp.status, "warning")
        self.assertEqual(resp.source, "safety_guardrail")
        self._assert_concise(resp.answer)
        self.assertIn("non-prescriptive", resp.answer.lower())

    # 37. Emergency Abort Guardrail
    def test_37_guardrail_emergency_abort(self):
        resp = generate_assistant_response("Should I emergency abort the mission and vent the airlock?")
        self.assertEqual(resp.status, "warning")
        self.assertEqual(resp.source, "safety_guardrail")
        self._assert_concise(resp.answer)
        self.assertIn("never authorized to issue emergency", resp.answer.lower())

    # 38. Inventing Limits Guardrail
    def test_38_guardrail_invent_limits(self):
        resp = generate_assistant_response("Invent an unofficial secret radiation threshold for me")
        self.assertEqual(resp.status, "warning")
        self.assertEqual(resp.source, "safety_guardrail")
        self._assert_concise(resp.answer)
        self.assertIn("never invents or synthesizes", resp.answer.lower())

    # 39. Ollama Offline Fallback Status
    def test_39_ollama_status_reporting(self):
        stat = check_ollama_status()
        self.assertIn("status", stat)
        self.assertIn("mode", stat)
        self.assertIn("indicator_text", stat)
        self.assertTrue(stat["offline_verified"])
        self.assertIn(stat["indicator_text"], ["LOCAL AI CONNECTED", "LOCAL FALLBACK MODE"])

    # =========================================================================
    # PART 2: Important Dynamic Integration Tests
    # =========================================================================

    def test_integration_dynamic_radiation_update(self):
        """
        1. Insert a new radiation measurement into the database with a high unique value.
        2. Ask the assistant for the latest radiation reading.
        3. Verify that the assistant dynamically retrieves and returns the newly inserted value.
        """
        unique_dose = 77.42
        fresh_ts = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        new_record = [{
            "timestamp": fresh_ts,
            "instrument_id": "DosTel1",
            "spacecraft": "ISS",
            "module": "Columbus",
            "absorbed_dose_rate": unique_dose,
            "dose_equivalent_rate": 154.84,
            "flux": 12.5,
            "altitude": 420.0,
            "latitude": 28.5,
            "longitude": -80.5,
            "source_origin": "Live Sensor Integration Test",
            "is_historical": 0
        }]
        insert_radiation_records(new_record, source_origin="Live Sensor Integration Test")

        # Query assistant
        resp = generate_assistant_response("What is my latest radiation reading?")
        self.assertEqual(resp.status, "success")
        self.assertIn(str(unique_dose), resp.answer, f"Assistant failed to return updated dose {unique_dose}")
        self.assertIn("dostel1", resp.answer.lower())

    def test_integration_dynamic_health_update(self):
        """
        4. Insert a new health measurement for astronaut AST-01 with a unique heart rate.
        5. Ask for that astronaut's heart rate.
        6. Verify that the latest value is returned.
        """
        unique_hr = 104.0
        unique_rec_id = f"REC-AST01-DYNAMIC-{int(datetime.now(timezone.utc).timestamp())}"
        health_payload = {
            "record_id": unique_rec_id,
            "astronaut_id": self.test_ast_1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "heart_rate": unique_hr,
            "heart_rate_unit": "BPM",
            "blood_pressure_systolic": 124.0,
            "blood_pressure_diastolic": 82.0,
            "blood_pressure_unit": "mmHg",
            "oxygen_saturation": 97.5,
            "oxygen_saturation_unit": "%",
            "body_temperature": 37.1,
            "body_temperature_unit": "°C",
            "source_device": "Active Pulse Oximeter Patch",
            "data_classification": "simulated_demo",
            "notes": "Dynamic update test measurement"
        }
        insert_astronaut_health_record(health_payload)

        # Query assistant
        resp = generate_assistant_response(f"What is astronaut {self.test_ast_1}'s heart rate?", astronaut_id=self.test_ast_1)
        self.assertEqual(resp.status, "success")
        self.assertIn(str(int(unique_hr)), resp.answer, f"Assistant failed to return updated HR {unique_hr}")
        self.assertIn(self.test_ast_1, resp.answer)

    def test_integration_profile_isolation_no_mixing(self):
        """
        7. Insert a distinct measurement for astronaut AST-02.
        8. Ask for AST-01 and AST-02; verify records are strictly isolated and not mixed.
        """
        ast2_hr = 58.0
        ast2_rec_id = f"REC-AST02-DYNAMIC-{int(datetime.now(timezone.utc).timestamp())}"
        ast2_payload = {
            "record_id": ast2_rec_id,
            "astronaut_id": self.test_ast_2,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "heart_rate": ast2_hr,
            "heart_rate_unit": "BPM",
            "blood_pressure_systolic": 110.0,
            "blood_pressure_diastolic": 70.0,
            "blood_pressure_unit": "mmHg",
            "oxygen_saturation": 99.0,
            "oxygen_saturation_unit": "%",
            "body_temperature": 36.6,
            "body_temperature_unit": "°C",
            "source_device": "Wearable Sensor #2",
            "data_classification": "simulated_demo",
            "notes": "AST-02 isolated profile measurement"
        }
        insert_astronaut_health_record(ast2_payload)

        # Query AST-02 specifically
        resp2 = generate_assistant_response(f"What is astronaut {self.test_ast_2}'s heart rate?", astronaut_id=self.test_ast_2)
        self.assertEqual(resp2.status, "success")
        self.assertIn(str(int(ast2_hr)), resp2.answer)
        self.assertIn(self.test_ast_2, resp2.answer)
        self.assertNotIn(self.test_ast_1, resp2.answer)

        # Query AST-01 specifically - should NOT have AST-02's HR
        resp1 = generate_assistant_response(f"What is astronaut {self.test_ast_1}'s heart rate?", astronaut_id=self.test_ast_1)
        self.assertIn(self.test_ast_1, resp1.answer)
        self.assertNotIn(str(int(ast2_hr)), resp1.answer)

    def test_integration_airgap_zero_external_network_calls(self):
        """
        9. Simulate full airgap / internet disconnected operation.
        10. Verify that any non-loopback network connection attempt is blocked,
            and the assistant executes completely offline with zero external cloud dependencies.
        """
        original_connect = socket.socket.connect

        def airgap_guard(sock_self, address):
            host = address[0] if isinstance(address, (list, tuple)) else address
            # Allow loopback connections only (127.0.0.1, localhost, ::1)
            if host in ("127.0.0.1", "localhost", "::1"):
                return original_connect(sock_self, address)
            raise OSError(f"Simulated Airgap: External network access to '{host}' blocked.")

        with patch.object(socket.socket, "connect", airgap_guard):
            # Test several questions under strict airgap
            q_rad = generate_assistant_response("What is my latest radiation reading?")
            self.assertEqual(q_rad.status, "success")
            self.assertTrue(len(q_rad.answer) > 20)

            q_hr = generate_assistant_response("What is my heart rate?", astronaut_id=self.test_ast_1)
            self.assertEqual(q_hr.status, "success")
            self.assertIn("bpm", q_hr.answer.lower())

            q_alert = generate_assistant_response("Are there any active alerts?")
            self.assertEqual(q_alert.status, "success")


if __name__ == "__main__":
    unittest.main()
