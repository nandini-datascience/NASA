"""
test_health.py - Unit and Integration Tests for Astronaut Health Monitoring (Task 03)

Validates:
1. Physiological measurement validation and unit preservation.
2. Handling of invalid, corrupted, or out-of-range vitals.
3. Aerospace health alert engine (NASA-STD-3001, AHA, WHO benchmarks).
4. SQLite duplicate prevention and query filtering.
5. All new endpoints:
   - GET /api/health/measurements
   - POST /api/health/measurements
   - GET /api/health/history
   - GET /api/health/alerts
6. Coexistence and non-regression of existing radiation endpoints.
"""

from datetime import datetime, timezone
import threading
import time
import unittest
import requests
import uvicorn

from app.db import (
    init_db,
    insert_astronaut_health_record,
    insert_astronaut_health_alerts,
    query_astronaut_health_measurements,
    query_astronaut_health_history,
    query_astronaut_health_alerts
)
from app.health import (
    evaluate_astronaut_health_alerts,
    validate_health_measurement
)


class TestHealthValidation(unittest.TestCase):
    """Tests for physiological validation of astronaut health telemetry."""

    def test_valid_nominal_vitals(self):
        """Simulated synthetic nominal test case."""
        data = {
            "astronaut_id": "TEST-CREW-1",
            "timestamp": "2026-11-14T10:00:00Z",
            "heart_rate": 72.0,
            "blood_pressure_systolic": 118.0,
            "blood_pressure_diastolic": 76.0,
            "oxygen_saturation": 98.0,
            "body_temperature": 36.8,
            "source_device": "Wearable Biometric Patch",
            "data_classification": "simulated_demo"
        }
        val_rec, quality_alerts, errors = validate_health_measurement(data)

        self.assertEqual(len(errors), 0)
        self.assertIsNotNone(val_rec)
        self.assertEqual(val_rec["astronaut_id"], "TEST-CREW-1")
        self.assertEqual(val_rec["heart_rate"], 72.0)
        self.assertEqual(val_rec["heart_rate_unit"], "BPM")
        self.assertEqual(val_rec["blood_pressure_unit"], "mmHg")
        self.assertEqual(val_rec["oxygen_saturation_unit"], "%")
        self.assertEqual(val_rec["body_temperature_unit"], "°C")

    def test_invalid_negative_and_out_of_range_values(self):
        """Rejection of physiologically unviable or inverted readings."""
        # Case A: Heart rate 15 BPM (unviable)
        bad_hr = {
            "astronaut_id": "TEST-CREW-2",
            "timestamp": "2026-11-14T10:00:00Z",
            "heart_rate": 15.0,
            "data_classification": "simulated_demo"
        }
        rec, quality_alerts, errors = validate_health_measurement(bad_hr)
        self.assertIsNone(rec)
        self.assertTrue(any("outside physiologically viable range" in e for e in errors))

        # Case B: Inverted Blood Pressure (Systolic 80 <= Diastolic 120)
        inverted_bp = {
            "astronaut_id": "TEST-CREW-3",
            "timestamp": "2026-11-14T10:00:00Z",
            "blood_pressure_systolic": 80.0,
            "blood_pressure_diastolic": 120.0,
            "data_classification": "simulated_demo"
        }
        rec, quality_alerts, errors = validate_health_measurement(inverted_bp)
        self.assertIsNone(rec)
        self.assertTrue(any("strictly greater than diastolic" in e for e in errors))

        # Case C: Oxygen saturation > 100%
        bad_spo2 = {
            "astronaut_id": "TEST-CREW-4",
            "timestamp": "2026-11-14T10:00:00Z",
            "oxygen_saturation": 105.0,
            "data_classification": "simulated_demo"
        }
        rec, quality_alerts, errors = validate_health_measurement(bad_spo2)
        self.assertIsNone(rec)
        self.assertTrue(any("outside viable bounds" in e for e in errors))


class TestHealthAlertEngine(unittest.TestCase):
    """Tests for clinical alert rules based on NASA-STD-3001, AHA, and WHO."""

    def test_cardiovascular_alerts(self):
        # Tachycardia test (HR 108 BPM)
        tachy_rec = {
            "astronaut_id": "TEST-CREW-5",
            "timestamp": "2026-11-14T10:00:00Z",
            "heart_rate": 108.0,
            "blood_pressure_systolic": None,
            "blood_pressure_diastolic": None,
            "oxygen_saturation": None,
            "body_temperature": None
        }
        alerts = evaluate_astronaut_health_alerts(tachy_rec)
        types = [a["alert_type"] for a in alerts]
        self.assertIn("TACHYCARDIA_WARNING", types)
        self.assertEqual(alerts[0]["severity"], "WARNING")
        self.assertIn("sympathetic nervous system", alerts[0]["explanation"])

    def test_hypoxia_and_fever_alerts(self):
        # Severe Hypoxia (SpO2 88%) and Fever (38.5°C)
        crit_rec = {
            "astronaut_id": "TEST-CREW-6",
            "timestamp": "2026-11-14T10:00:00Z",
            "heart_rate": None,
            "blood_pressure_systolic": None,
            "blood_pressure_diastolic": None,
            "oxygen_saturation": 88.0,
            "body_temperature": 38.5
        }
        alerts = evaluate_astronaut_health_alerts(crit_rec)
        types = [a["alert_type"] for a in alerts]
        self.assertIn("HYPOXIA_SEVERE", types)
        self.assertIn("FEVER_HYPERTHERMIA", types)

        hypoxia_alert = [a for a in alerts if a["alert_type"] == "HYPOXIA_SEVERE"][0]
        self.assertEqual(hypoxia_alert["severity"], "CRITICAL")
        self.assertIn("cabin depressurization", hypoxia_alert["explanation"])


class TestHealthDatabaseDuplicatePrevention(unittest.TestCase):
    """Tests SQLite duplicate prevention and query filtering."""

    def setUp(self):
        init_db()
        # Clean up any test records
        from app.db import get_db_connection
        conn = get_db_connection()
        with conn:
            conn.execute("DELETE FROM astronaut_health_records WHERE astronaut_id LIKE 'TEST%' OR astronaut_id LIKE 'AST-TEST%';")
            conn.execute("DELETE FROM astronaut_health_alerts WHERE astronaut_id LIKE 'TEST%' OR astronaut_id LIKE 'AST-TEST%';")
        conn.close()

    def test_health_duplicate_prevention(self):
        rec1 = {
            "record_id": "HLT-DUP-TEST-01",
            "astronaut_id": "TEST-CREW-DUP",
            "timestamp": "2026-11-14T11:00:00Z",
            "heart_rate": 70.0,
            "heart_rate_unit": "BPM",
            "blood_pressure_systolic": 115.0,
            "blood_pressure_diastolic": 75.0,
            "blood_pressure_unit": "mmHg",
            "oxygen_saturation": 98.0,
            "oxygen_saturation_unit": "%",
            "body_temperature": 36.7,
            "body_temperature_unit": "°C",
            "source_device": "Test Simulator",
            "data_classification": "simulated_demo",
            "notes": "Testing duplicate prevention - first submission"
        }

        # Second record with identical astronaut_id and timestamp
        rec2 = dict(rec1)
        rec2["notes"] = "Testing duplicate prevention - second submission update"

        # First insert
        ins1 = insert_astronaut_health_record(rec1)
        self.assertTrue(ins1)

        # Second insert (same astronaut_id and timestamp)
        ins2 = insert_astronaut_health_record(rec2)
        self.assertTrue(ins2)

        # Verify that exactly ONE record exists for this astronaut and timestamp (no duplicate created!)
        res = query_astronaut_health_measurements(astronaut_id="TEST-CREW-DUP")
        self.assertEqual(res["total_measurements"], 1, "Duplicate (astronaut_id, timestamp) must not create a second row")
        self.assertEqual(res["measurements"][0]["notes"], "Testing duplicate prevention - second submission update")


class TestHealthHttpEndpoints(unittest.TestCase):
    """Tests HTTP endpoints for astronaut health monitoring via FastAPI TestClient."""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db import get_db_connection

        conn = get_db_connection()
        with conn:
            conn.execute("DELETE FROM astronaut_health_records WHERE astronaut_id LIKE 'AST-TEST%';")
            conn.execute("DELETE FROM astronaut_health_alerts WHERE astronaut_id LIKE 'AST-TEST%';")
        conn.close()

        cls.client = TestClient(app)

    def test_get_health_measurements(self):
        r = self.client.get("/api/health/measurements?limit=10")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("measurements", data)
        self.assertIn("total_measurements", data)
        self.assertIn("disclaimer", data)

    def test_post_valid_health_measurement(self):
        payload = {
            "astronaut_id": "AST-TEST-POST",
            "timestamp": "2026-11-14T11:30:00Z",
            "heart_rate": 84.0,
            "blood_pressure_systolic": 122.0,
            "blood_pressure_diastolic": 78.0,
            "oxygen_saturation": 97.5,
            "body_temperature": 36.9,
            "source_device": "Crew Patch #5",
            "data_classification": "simulated_demo",
            "notes": "Simulated live demonstration post"
        }
        r = self.client.post("/api/health/measurements", json=payload)
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("record_id", data)
        self.assertTrue(data["stored_in_database"])

    def test_post_invalid_measurement_returns_422(self):
        payload = {
            "astronaut_id": "AST-TEST-BAD",
            "timestamp": "2026-11-14T11:30:00Z",
            "heart_rate": 450.0,  # Impossible
            "blood_pressure_systolic": 80.0,
            "blood_pressure_diastolic": 120.0,  # Inverted
            "data_classification": "simulated_demo"
        }
        r = self.client.post("/api/health/measurements", json=payload)
        self.assertEqual(r.status_code, 422)
        data = r.json()
        self.assertIn("validation_errors", data["detail"])

    def test_get_health_history(self):
        r = self.client.get("/api/health/history?limit=5")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("records", data)

    def test_get_health_alerts(self):
        r = self.client.get("/api/health/alerts?limit=5")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("alerts", data)
        self.assertIn("category_breakdown", data)

    def test_non_regression_radiation_endpoints(self):
        """Verifies that all existing radiation endpoints still work seamlessly."""
        # 1. System health check
        r_health = self.client.get("/api/health")
        self.assertEqual(r_health.status_code, 200)
        self.assertEqual(r_health.json()["status"], "healthy")

        # 2. Radiation sample endpoint
        r_rad = self.client.get("/api/radiation/sample?limit=2")
        self.assertEqual(r_rad.status_code, 200)
        self.assertIn("records", r_rad.json())

        # 3. Radiation analysis endpoint
        r_analysis = self.client.get("/api/radiation/analysis?limit=5")
        self.assertEqual(r_analysis.status_code, 200)
        self.assertIn("radiation_analysis", r_analysis.json())


if __name__ == "__main__":
    unittest.main()
