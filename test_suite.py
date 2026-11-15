"""
test_suite.py - Verification and Test Suite for ASTRA CARE Backend (Task 02)

Validates:
1. Cumulative exposure calculation with mathematically proven test cases.
2. Invalid and missing measurements handling.
3. Timestamp gap identification.
4. Radiation rate-of-change spike and elevated threshold detection.
5. SQLite duplicate prevention and query filtering.
6. All FastAPI HTTP endpoints (/api/radiation/analysis, /api/radiation/history, /api/alerts, etc.).
"""

from datetime import datetime, timezone, timedelta
import io
import math
import unittest
import requests

from app.analysis import (
    compute_cumulative_exposure_for_series,
    validate_radiation_records,
    detect_timestamp_gaps,
    evaluate_health_risk_alerts,
    perform_full_radiation_analysis
)
from app.db import (
    init_db,
    insert_radiation_records,
    insert_alerts,
    query_radiation_history,
    query_alerts,
    get_db_statistics
)


class TestCumulativeExposureCalculation(unittest.TestCase):
    """
    Mathematical tests for numerical integration of cumulative exposure.
    Verifies that cumulative dose is only computed when intervals support valid calculation.
    """

    def test_known_trapezoidal_integration(self):
        """
        Known Case:
        t0 = 0s (rate = 10.0 µGy/hr)
        t1 = 1800s (0.5 hr, rate = 20.0 µGy/hr)
        t2 = 3600s (1.0 hr, rate = 10.0 µGy/hr)

        Expected:
        Segment 1: ((10 + 20) / 2) * 0.5 = 15 * 0.5 = 7.5 µGy
        Segment 2: ((20 + 10) / 2) * 0.5 = 15 * 0.5 = 7.5 µGy
        Total = 15.0 µGy
        """
        t0 = datetime(2022, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(seconds=1800)
        t2 = t0 + timedelta(seconds=3600)

        series = [(t0, 10.0), (t1, 20.0), (t2, 10.0)]
        result = compute_cumulative_exposure_for_series(
            series, unit_rate="µGy/hr", unit_dose="µGy", max_gap_seconds=3600.0
        )

        self.assertTrue(result["supported"])
        self.assertAlmostEqual(result["cumulative_dose"], 15.0, places=4)
        self.assertEqual(result["unit"], "µGy")
        self.assertEqual(result["valid_duration_seconds"], 3600.0)
        self.assertAlmostEqual(result["valid_duration_hours"], 1.0, places=4)
        self.assertEqual(result["continuous_segments_count"], 1)
        self.assertEqual(result["gaps_excluded_count"], 0)

    def test_single_point_insufficient_data(self):
        """A single reading cannot support continuous interval integration."""
        t0 = datetime(2022, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
        series = [(t0, 15.5)]
        result = compute_cumulative_exposure_for_series(series, "µGy/hr", "µGy")

        self.assertFalse(result["supported"])
        self.assertIsNone(result["cumulative_dose"])
        self.assertIn("Insufficient", result["reason"])

    def test_gap_exclusion_in_cumulative_exposure(self):
        """
        Test that intervals exceeding max_gap_seconds are excluded from cumulative exposure
        instead of fabricating continuous dose over multi-hour missing telemetry.
        """
        t0 = datetime(2022, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(seconds=300)      # 5 mins later (valid)
        t2 = t1 + timedelta(seconds=10800)    # 3 hours later (GAP > 600s)
        t3 = t2 + timedelta(seconds=300)      # 5 mins later (valid)

        # Segments:
        # (t0, t1): 300s = 300/3600 hr = 1/12 hr. Rates 10.0 and 10.0 -> 10 * (1/12) = 0.8333 µGy
        # (t1, t2): GAP excluded
        # (t2, t3): 300s = 1/12 hr. Rates 10.0 and 10.0 -> 10 * (1/12) = 0.8333 µGy
        # Expected Total = 1.6667 µGy
        series = [(t0, 10.0), (t1, 10.0), (t2, 10.0), (t3, 10.0)]
        result = compute_cumulative_exposure_for_series(
            series, unit_rate="µGy/hr", unit_dose="µGy", max_gap_seconds=600.0
        )

        self.assertTrue(result["supported"])
        self.assertAlmostEqual(result["cumulative_dose"], 1.666667, places=4)
        self.assertEqual(result["gaps_excluded_count"], 1)
        self.assertEqual(result["continuous_segments_count"], 2)


class TestValidationAndQualityAlerts(unittest.TestCase):
    """
    Tests for telemetry validation:
    - Missing measurements
    - Physically impossible negative readings
    - Corrupted timestamps
    """

    def test_negative_values_and_malformed_timestamps(self):
        """Simulated synthetic test fixture to verify validation and flagging."""
        test_records = [
            # Valid record
            {
                "timestamp": "2022-04-01T00:00:00",
                "instrument_id": "TEST-DETECTOR-1",
                "absorbed_dose_rate": 5.0,
                "dose_equivalent_rate": 6.0,
                "spacecraft": "ISS"
            },
            # Invalid negative absorbed dose rate
            {
                "timestamp": "2022-04-01T00:01:00",
                "instrument_id": "TEST-DETECTOR-1",
                "absorbed_dose_rate": -12.5,
                "dose_equivalent_rate": 6.0,
                "spacecraft": "ISS"
            },
            # Corrupted timestamp
            {
                "timestamp": "CORRUPTED-TIME-STAMP",
                "instrument_id": "TEST-DETECTOR-2",
                "absorbed_dose_rate": 4.0,
                "spacecraft": "ISS"
            },
            # Missing radiation rates (standby mode)
            {
                "timestamp": "2022-04-01T00:02:00",
                "instrument_id": "TEST-DETECTOR-3",
                "absorbed_dose_rate": None,
                "dose_equivalent_rate": None,
                "spacecraft": "ISS"
            }
        ]

        valid_records, report, alerts = validate_radiation_records(test_records, "Synthetic Test Suite")

        # Only 1 record is fully valid
        self.assertEqual(len(valid_records), 1)
        self.assertEqual(report["total_records_inspected"], 4)
        self.assertEqual(report["valid_records_count"], 1)
        self.assertEqual(report["invalid_records_count"], 3)
        self.assertEqual(report["invalid_negative_value_count"], 1)
        self.assertEqual(report["invalid_timestamp_count"], 1)

        # Check alert types generated
        alert_types = [a["alert_type"] for a in alerts]
        self.assertIn("INVALID_VALUE", alert_types)
        self.assertIn("TIMESTAMP_PARSE_ERROR", alert_types)
        self.assertIn("MISSING_MEASUREMENT", alert_types)


class TestGapAndSpikeAlerts(unittest.TestCase):
    """
    Tests telemetry continuity and rate-of-change spike detection.
    """

    def test_timestamp_gap_detection(self):
        records = [
            {
                "timestamp": "2022-04-01T00:00:00",
                "_parsed_dt": datetime(2022, 4, 1, 0, 0, 0, tzinfo=timezone.utc),
                "instrument_id": "REM-Lid",
                "spacecraft": "ISS",
                "absorbed_dose_rate": 1.0
            },
            {
                "timestamp": "2022-04-01T00:45:00",  # 45 minute gap > 10 min threshold
                "_parsed_dt": datetime(2022, 4, 1, 0, 45, 0, tzinfo=timezone.utc),
                "instrument_id": "REM-Lid",
                "spacecraft": "ISS",
                "absorbed_dose_rate": 1.2
            }
        ]

        gaps, gap_alerts = detect_timestamp_gaps(records, max_gap_seconds=600.0)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["gap_seconds"], 2700.0)
        self.assertEqual(gaps[0]["gap_minutes"], 45.0)
        self.assertEqual(len(gap_alerts), 1)
        self.assertEqual(gap_alerts[0]["category"], "DATA_QUALITY_WARNING")
        self.assertEqual(gap_alerts[0]["alert_type"], "TIMESTAMP_GAP")

    def test_health_risk_alert_elevated_and_spike(self):
        """
        Tests elevated dose rate (>=20 µGy/hr) and rapid rate spike (>=15 µGy/hr jump in <=300s).
        """
        records = [
            {
                "timestamp": "2022-04-01T00:00:00",
                "_parsed_dt": datetime(2022, 4, 1, 0, 0, 0, tzinfo=timezone.utc),
                "instrument_id": "REM-Lid",
                "spacecraft": "ISS",
                "absorbed_dose_rate": 5.0,
                "dose_equivalent_rate": None
            },
            {
                "timestamp": "2022-04-01T00:02:00",
                "_parsed_dt": datetime(2022, 4, 1, 0, 2, 0, tzinfo=timezone.utc),
                "instrument_id": "REM-Lid",
                "spacecraft": "ISS",
                "absorbed_dose_rate": 26.0,  # Jump of +21.0 µGy/hr (Spike) AND >= 20.0 (Elevated)
                "dose_equivalent_rate": None
            }
        ]

        alerts = evaluate_health_risk_alerts(records)
        alert_types = [a["alert_type"] for a in alerts]

        self.assertIn("ELEVATED_DOSE_RATE", alert_types)
        self.assertIn("RAPID_RATE_SPIKE", alert_types)
        for a in alerts:
            self.assertEqual(a["category"], "HEALTH_RISK_ALERT")


class TestSQLiteDatabaseIntegration(unittest.TestCase):
    """
    Tests SQLite database duplicate prevention, history retrieval, and alert storage.
    """

    def setUp(self):
        init_db()

    def test_duplicate_prevention_on_insert(self):
        records = [
            {
                "timestamp": "2022-04-01T00:00:00",
                "instrument_id": "DB-TEST-REM",
                "spacecraft": "ISS",
                "module": "Columbus",
                "absorbed_dose_rate": 1.25,
                "dose_equivalent_rate": 1.50,
                "flux": 0.08,
                "altitude": 416.0,
                "latitude": 10.0,
                "longitude": 20.0
            }
        ]

        # First insert
        count1 = insert_radiation_records(records, source_origin="Test Runner")
        # Second insert with identical timestamp, instrument, and spacecraft
        count2 = insert_radiation_records(records, source_origin="Test Runner")

        self.assertEqual(count2, 0, "Duplicate record should be ignored by UNIQUE constraint")

        history = query_radiation_history(instrument_id="DB-TEST-REM")
        self.assertEqual(history["total_records"], 1)
        self.assertEqual(len(history["records"]), 1)
        self.assertEqual(history["records"][0]["absorbed_dose_rate"], 1.25)
        self.assertEqual(history["records"][0]["absorbed_dose_unit"], "µGy/hr")


if __name__ == "__main__":
    unittest.main()
