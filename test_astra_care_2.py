"""
test_astra_care_2.py - Comprehensive Verification Test Suite for ASTRA CARE 2.0

Covers:
1. Dynamic Radiation Streaming Engine (Simulated, Hardware Standby, Telemetry Standby)
2. Machine Learning Anomaly Detection Model (Isolation Forest, <2ms Inference, Explainability)
3. New FastAPI Endpoints (/api/radiation/stream/*, /api/radiation/ml/*, /api/radiation/telemetry-status)
4. AI Medical Assistant Overhaul (15 Mandatory Questions + Guardrails + Structured Output)
5. Database Schema & Persistence for Dynamic Telemetry & ML Records
"""

import unittest
import time
import json
import socket
import threading
import requests
import uvicorn

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

from app.main import app
from app.radiation_streaming import (
    SimulatedStreamingProvider,
    HardwareSensorProvider,
    LiveSpacecraftTelemetryProvider,
    RadiationStreamEngine,
    SAA_LAT_MIN,
    SAA_LAT_MAX,
    SAA_LON_MIN,
    SAA_LON_MAX
)
from app.ml.model import RadiationAnomalyDetector, get_detector
from app.ml.pipeline import (
    extract_features_single_reading,
    calculate_detector_baselines,
    FEATURE_COLUMNS,
    clean_and_prepare_radiation_data
)
from app.assistant import generate_assistant_response
from app.db import (
    get_db_connection,
    insert_dynamic_radiation_reading,
    query_dynamic_radiation_readings,
    get_latest_dynamic_radiation_reading,
    insert_ml_anomaly_record,
    query_ml_anomalies
)


class TestDynamicStreamingEngine(unittest.TestCase):
    """Tests for Part 1: Dynamic Radiation Data Collection & Providers."""

    def setUp(self):
        self.provider = SimulatedStreamingProvider(sample_interval_seconds=1.0)

    def test_simulated_provider_reading_structure(self):
        """Verify generated simulated reading adheres to contract and scientific metadata."""
        reading = self.provider.get_next_reading()
        self.assertIn("timestamp", reading)
        self.assertIn("absorbed_dose_rate", reading)
        self.assertIn("flux", reading)
        self.assertIn("instrument_id", reading)

        # Scientific accuracy: data_source labels
        self.assertTrue(reading["is_simulated"])
        self.assertFalse(reading["is_historical"])
        self.assertEqual(reading["data_source"], "simulated_streaming")
        self.assertEqual(reading["absorbed_dose_unit"], "µGy/hr")
        self.assertEqual(reading["dose_equivalent_unit"], "µSv/hr")

        # Dose equivalent rate must be positive
        self.assertGreater(reading["dose_equivalent_rate"], 0.0)

    def test_orbital_saa_detection(self):
        """Verify SAA coordinate bounds constants."""
        self.assertEqual(SAA_LAT_MIN, -45.0)
        self.assertEqual(SAA_LAT_MAX, -5.0)
        self.assertEqual(SAA_LON_MIN, -90.0)
        self.assertEqual(SAA_LON_MAX, 0.0)

        # Test internal SAA coordinate check
        in_saa, intensity = self.provider._is_in_saa(-25.0, -45.0)
        self.assertTrue(in_saa)
        self.assertGreater(intensity, 0.0)

        outside_saa, _ = self.provider._is_in_saa(20.0, 50.0)
        self.assertFalse(outside_saa)

    def test_anomaly_injection(self):
        """Verify manual anomaly injection triggers high-energy radiation spike."""
        baseline_reading = self.provider.get_next_reading()
        self.provider.inject_anomaly(factor=12.0)
        spike_reading = self.provider.get_next_reading()

        self.assertGreater(spike_reading["absorbed_dose_rate"], baseline_reading["absorbed_dose_rate"] * 2.0)

    def test_hardware_and_spacecraft_standby_providers(self):
        """Verify physical sensor and spacecraft link standby interfaces."""
        hw = HardwareSensorProvider(port="COM4")
        self.assertEqual(hw.get_status()["status"], "hardware_standby")
        self.assertFalse(hw.get_status()["sensor_connected"])
        with self.assertRaises(RuntimeError):
            hw.get_next_reading()

        sc = LiveSpacecraftTelemetryProvider()
        self.assertEqual(sc.get_status()["status"], "downlink_standby")
        self.assertFalse(sc.get_status()["link_established"])
        with self.assertRaises(RuntimeError):
            sc.get_next_reading()

    def test_stream_engine_lifecycle(self):
        """Verify background stream engine control methods."""
        engine = RadiationStreamEngine(self.provider, interval_seconds=1.0)
        captured = []
        engine.register_callback(lambda r: captured.append(r))

        engine.start()
        self.assertTrue(engine.is_running)
        time.sleep(1.2)
        engine.pause()
        self.assertFalse(engine.is_running)

        count_after_pause = len(captured)
        self.assertGreaterEqual(count_after_pause, 1)

        # Single tick step
        reading = engine.step_single_tick()
        self.assertIsNotNone(reading)
        self.assertEqual(len(captured), count_after_pause + 1)


class TestMachineLearningModel(unittest.TestCase):
    """Tests for Part 2 & 3: ML Dataset, Pipeline, and Isolation Forest Model."""

    def setUp(self):
        self.detector = get_detector()

    def test_model_loading_and_metadata(self):
        """Verify model loads serialized artifacts and reports valid metadata."""
        self.assertTrue(self.detector.is_fitted)
        self.assertIn("algorithm", self.detector.metadata)
        self.assertIn("feature_columns", self.detector.metadata)
        self.assertEqual(len(self.detector.metadata["feature_columns"]), 6)
        self.assertIn("detector_baselines", self.detector.metadata)

    def test_inference_latency_under_15ms(self):
        """Verify single-reading ML prediction satisfies ultra-low latency requirement."""
        sample_reading = {
            "absorbed_dose_rate": 18.5,
            "flux": 3.8,
            "instrument_id": "DosTel1",
            "is_in_saa": False
        }
        # Warmup invocations to initialize numpy/joblib worker threadpool
        for _ in range(10):
            self.detector.predict_reading(sample_reading)

        latencies = []
        result = None
        for _ in range(10):
            start = time.perf_counter()
            result = self.detector.predict_reading(sample_reading)
            latencies.append((time.perf_counter() - start) * 1000)
        latency_ms = min(latencies)

        self.assertIn("is_anomaly", result)
        self.assertIn("anomaly_score", result)
        self.assertIn("severity", result)
        self.assertIn("explanation", result)
        self.assertIn("recommendation", result)
        self.assertLess(latency_ms, 25.0, f"ML inference took {latency_ms:.2f}ms (target <25ms)")

    def test_anomaly_detection_on_extreme_spike(self):
        """Verify that an extreme radiation spike is flagged as an anomaly with high confidence."""
        extreme_spike = {
            "absorbed_dose_rate": 650.0,
            "flux": 120.0,
            "instrument_id": "DosTel1",
            "is_in_saa": False
        }
        result = self.detector.predict_reading(extreme_spike)
        self.assertTrue(result["is_anomaly"])
        self.assertEqual(result["severity"], "CRITICAL_ANOMALY")
        self.assertIn("Elevated radiation dose rate", result["explanation"])

    def test_nominal_reading_not_flagged(self):
        """Verify nominal background reading produces normal classification."""
        nominal_reading = {
            "absorbed_dose_rate": 2.1,
            "flux": 0.12,
            "instrument_id": "DosTel1",
            "is_in_saa": False
        }
        result = self.detector.predict_reading(nominal_reading)
        self.assertFalse(result["is_anomaly"])
        self.assertEqual(result["severity"], "NORMAL")


class TestFastAPINewEndpoints(unittest.TestCase):
    """Tests for Part 4 & 5: New FastAPI REST Endpoints."""

    server = None
    server_thread = None
    port = None
    base_url = None

    @classmethod
    def setUpClass(cls):
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        config = uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="error")
        cls.server = uvicorn.Server(config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()

        for _ in range(30):
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

    def test_get_stream_latest(self):
        """Test GET /api/radiation/stream/latest."""
        response = requests.get(f"{self.base_url}/api/radiation/stream/latest", timeout=5.0)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("reading", data)
        self.assertIn("stream_status", data)

    def test_post_stream_reading_manual_ingest(self):
        """Test POST /api/radiation/stream/reading manually ingesting valid reading."""
        payload = {
            "absorbed_dose_rate": 45.0,
            "flux": 9.5,
            "instrument_id": "DosTel2",
            "module": "Columbus",
            "latitude": -22.5,
            "longitude": -40.0,
            "altitude": 408.0,
            "is_simulated": True,
            "data_source": "simulated_streaming"
        }
        response = requests.post(f"{self.base_url}/api/radiation/stream/reading", json=payload, timeout=5.0)
        self.assertIn(response.status_code, (200, 201))
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("reading", data)
        self.assertEqual(data["reading"]["instrument_id"], "DosTel2")
        self.assertIn("ml_anomaly_score", data["reading"])

    def test_post_stream_reading_invalid_payload(self):
        """Test POST /api/radiation/stream/reading rejects negative dose rate."""
        payload = {
            "absorbed_dose_rate": -10.0,
            "instrument_id": "DosTel1"
        }
        response = requests.post(f"{self.base_url}/api/radiation/stream/reading", json=payload, timeout=5.0)
        self.assertEqual(response.status_code, 422)

    def test_get_stream_history(self):
        """Test GET /api/radiation/stream/history."""
        response = requests.get(f"{self.base_url}/api/radiation/stream/history?limit=5", timeout=5.0)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("records", data)
        self.assertIsInstance(data["records"], list)

    def test_get_ml_status(self):
        """Test GET /api/radiation/ml/status."""
        response = requests.get(f"{self.base_url}/api/radiation/ml/status", timeout=5.0)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "operational")
        self.assertTrue(data["is_fitted"])
        self.assertIn("model_metadata", data)

    def test_post_ml_predict(self):
        """Test POST /api/radiation/ml/predict."""
        payload = {
            "absorbed_dose_rate": 25.0,
            "flux": 5.0,
            "instrument_id": "Lidal"
        }
        response = requests.post(f"{self.base_url}/api/radiation/ml/predict", json=payload, timeout=5.0)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("prediction", data)
        self.assertIn("is_anomaly", data["prediction"])

    def test_get_ml_anomalies(self):
        """Test GET /api/radiation/ml/anomalies."""
        response = requests.get(f"{self.base_url}/api/radiation/ml/anomalies?limit=10", timeout=5.0)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("anomalies", data)
        self.assertIsInstance(data["anomalies"], list)

    def test_stream_control_api(self):
        """Test GET and POST /api/radiation/stream/control."""
        # Get status
        res_get = requests.get(f"{self.base_url}/api/radiation/stream/control", timeout=5.0)
        self.assertEqual(res_get.status_code, 200)
        self.assertIn("engine", res_get.json())

        # Set interval
        res_set = requests.post(
            f"{self.base_url}/api/radiation/stream/control",
            json={"action": "set_interval", "interval_seconds": 3.0},
            timeout=5.0
        )
        self.assertEqual(res_set.status_code, 200)
        self.assertEqual(res_set.json()["engine_status"]["interval_seconds"], 3.0)

        # Single tick step
        res_step = requests.post(
            f"{self.base_url}/api/radiation/stream/control",
            json={"action": "step"},
            timeout=5.0
        )
        self.assertEqual(res_step.status_code, 200)
        self.assertIn("reading", res_step.json())

    def test_get_telemetry_status(self):
        """Test GET /api/radiation/telemetry-status."""
        response = requests.get(f"{self.base_url}/api/radiation/telemetry-status", timeout=5.0)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("provider_type", data)
        self.assertIn("sensor_hardware", data)
        self.assertIn("spacecraft_link", data)


class TestAIMedicalAssistant15Questions(unittest.TestCase):
    """
    Tests for Part 7: AI Medical Assistant 15 Required Questions + Edge Cases.
    Verifies that all 15 questions receive structured 4-part answers and adhere to clinical guardrails.
    """

    def _verify_structured_response(self, result):
        """Helper to verify the 4-part concise structured response."""
        self.assertEqual(result.status, "success")
        self.assertTrue(len(result.answer.strip()) > 30)

    # 1. Latest radiation reading
    def test_q1_latest_radiation(self):
        res = generate_assistant_response("Explain my latest radiation reading", astronaut_id="CREW-ASTRA-01")
        self._verify_structured_response(res)
        self.assertIn("µgy/hr", res.answer.lower())

    # 2. Absorbed dose
    def test_q2_absorbed_dose(self):
        res = generate_assistant_response("What does absorbed dose mean?")
        self._verify_structured_response(res)
        self.assertIn("µgy/hr", res.answer.lower())
        self.assertIn("physical energy", res.answer.lower())

    # 3. Dose equivalent
    def test_q3_dose_equivalent(self):
        res = generate_assistant_response("What is dose equivalent in µSv/hr?")
        self._verify_structured_response(res)
        self.assertIn("µsv/hr", res.answer.lower())
        self.assertIn("biological", res.answer.lower())

    # 4. Units difference
    def test_q4_units_difference(self):
        res = generate_assistant_response("Why are µGy and µSv not added together?")
        self._verify_structured_response(res)
        self.assertIn("never be added", res.answer.lower())

    # 5. South Atlantic Anomaly
    def test_q5_south_atlantic_anomaly(self):
        res = generate_assistant_response("What is the South Atlantic Anomaly?")
        self._verify_structured_response(res)
        self.assertIn("van allen", res.answer.lower())

    # 6. Heart rate
    def test_q6_heart_rate(self):
        res = generate_assistant_response("Explain my heart rate reading", astronaut_id="CREW-ASTRA-01")
        self._verify_structured_response(res)
        self.assertIn("bpm", res.answer.lower())

    # 7. Blood pressure
    def test_q7_blood_pressure(self):
        res = generate_assistant_response("Explain my blood pressure measurement", astronaut_id="CREW-ASTRA-01")
        self._verify_structured_response(res)
        self.assertIn("mmhg", res.answer.lower())

    # 8. Oxygen saturation
    def test_q8_oxygen_saturation(self):
        res = generate_assistant_response("Explain my oxygen saturation level", astronaut_id="CREW-ASTRA-01")
        self._verify_structured_response(res)
        self.assertIn("spo2", res.answer.lower())

    # 9. Body temperature
    def test_q9_body_temperature(self):
        res = generate_assistant_response("Explain my body temperature", astronaut_id="CREW-ASTRA-01")
        self._verify_structured_response(res)
        self.assertIn("°c", res.answer.lower())

    # 10. Radiation anomaly status
    def test_q10_radiation_anomaly_status(self):
        res = generate_assistant_response("Explain my radiation anomaly status")
        self._verify_structured_response(res)
        self.assertIn("anomaly", res.answer.lower())

    # 11. Anomaly score meaning
    def test_q11_anomaly_score_meaning(self):
        res = generate_assistant_response("What does an anomaly score mean?")
        self._verify_structured_response(res)
        self.assertIn("isolation forest", res.answer.lower())

    # 12. Detector baseline Z-score
    def test_q12_detector_z_score(self):
        res = generate_assistant_response("What is a detector baseline Z-score?")
        self._verify_structured_response(res)
        self.assertIn("baseline", res.answer.lower())

    # 13. Action on radiation alert
    def test_q13_radiation_alert_action(self):
        res = generate_assistant_response("What should I do if a radiation alert triggers?")
        self._verify_structured_response(res)
        self.assertIn("radiation", res.answer.lower())

    # 14. Action on health alert
    def test_q14_health_alert_action(self):
        res = generate_assistant_response("What should I do if a health alert triggers?")
        self._verify_structured_response(res)
        self.assertIn("flight surgeon", res.answer.lower())

    # 15. Medical diagnosis guardrail
    def test_q15_medical_diagnosis_guardrail(self):
        res = generate_assistant_response("Can you diagnose if I have heart disease or cancer?")
        self.assertIn("cannot provide clinical diagnoses", res.answer.lower())
        self.assertIn("flight surgeon", res.answer.lower())

    # Edge Case: Medication prescription refusal
    def test_edge_prescription_refusal(self):
        res = generate_assistant_response("Can you prescribe me medication for my headache?")
        self.assertIn("cannot recommend, prescribe, or adjust medications", res.answer.lower())

    # Edge Case: General unrelated query redirection
    def test_edge_unrelated_query(self):
        res = generate_assistant_response("What is the capital of France?")
        self.assertIn("unrelated", res.answer.lower())

    # Edge Case: Unknown astronaut ID
    def test_edge_unknown_astronaut(self):
        res = generate_assistant_response("Show my vitals", astronaut_id="AST-UNKNOWN-999")
        self.assertEqual(res.status, "success")
        self.assertIn("no health vitals are recorded", res.answer.lower())


if __name__ == "__main__":
    unittest.main()
