"""
test_3d_twin.py - Comprehensive Verification Test Suite for 3D Astronaut Digital Twin
ASTRA CARE Aerospace Health Monitoring System
"""

import unittest
from fastapi.testclient import TestClient
from app.main import app


class TestAstronautDigitalTwin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_radiation_latest(self):
        """Test GET /api/radiation/latest returns enriched dosimetry with visual aura parameters."""
        res = self.client.get("/api/radiation/latest")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["status"], "success")
        self.assertIn("absorbed_dose_rate", data)
        self.assertEqual(data["absorbed_dose_unit"], "µGy/hr")
        self.assertIn("dose_equivalent_rate", data)
        self.assertEqual(data["dose_equivalent_unit"], "µSv/hr")
        self.assertIn("cumulative_dose_ugy", data)
        self.assertEqual(data["cumulative_dose_unit"], "µGy")
        self.assertIn("visual_aura", data)
        self.assertIn("color", data["visual_aura"])
        self.assertIn("intensity", data["visual_aura"])
        self.assertIn("disclaimer", data)
        print("  ✓ /api/radiation/latest verified successfully.")

    def test_02_health_latest(self):
        """Test GET /api/health/latest returns physiological vitals with units and ranges."""
        res = self.client.get("/api/health/latest?astronaut_id=AST-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["astronaut_id"], "AST-01")
        self.assertIn("heart_rate", data)
        self.assertEqual(data["heart_rate"]["unit"], "BPM")
        self.assertIn("blood_pressure", data)
        self.assertEqual(data["blood_pressure"]["unit"], "mmHg")
        self.assertIn("oxygen_saturation", data)
        self.assertEqual(data["oxygen_saturation"]["unit"], "%")
        self.assertIn("body_temperature", data)
        self.assertEqual(data["body_temperature"]["unit"], "°C")
        self.assertIn("respiratory_rate", data)
        self.assertEqual(data["respiratory_rate"]["unit"], "breaths/min")
        self.assertEqual(data["data_classification"], "simulated_demo")
        print("  ✓ /api/health/latest verified successfully.")

    def test_03_astronaut_profile(self):
        """Test GET /api/astronaut/profile returns mission metadata and spacesuit telemetry."""
        res = self.client.get("/api/astronaut/profile?astronaut_id=AST-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["status"], "success")
        ast = data["astronaut"]
        self.assertEqual(ast["astronaut_id"], "AST-01")
        self.assertEqual(ast["name"], "Dr. Sarah Vance")
        self.assertIn("spacesuit", ast)
        suit = ast["spacesuit"]
        self.assertIn("pressure_kpa", suit)
        self.assertIn("primary_o2_reserve_pct", suit)
        self.assertIn("battery_soc_pct", suit)
        self.assertIn("co2_scrubber_efficiency_pct", suit)
        self.assertEqual(ast["medical_status"]["clearance"], "FLIGHT QUALIFIED / EVA CLEARED")
        print("  ✓ /api/astronaut/profile verified successfully.")

    def test_04_ecg_waveform(self):
        """Test GET /api/health/ecg returns Lead II rhythm strip waveform points and intervals."""
        res = self.client.get("/api/health/ecg?astronaut_id=AST-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["lead"], "Lead II (Continuous Rhythm Strip)")
        self.assertEqual(data["voltage_unit"], "mV")
        self.assertEqual(data["sampling_rate_hz"], 250)
        self.assertGreater(len(data["waveform"]), 100)
        meta = data["recording_meta"]
        self.assertIn("heart_rate_bpm", meta)
        self.assertIn("pr_interval_ms", meta)
        self.assertIn("qrs_duration_ms", meta)
        self.assertIn("qtc_bazett_ms", meta)
        self.assertEqual(data["data_classification"], "simulated_demonstration_record")
        print(f"  ✓ /api/health/ecg verified ({len(data['waveform'])} samples at 250 Hz).")

    def test_05_eeg_waveform(self):
        """Test GET /api/health/eeg returns continuous microvolts and spectral frequency bands."""
        res = self.client.get("/api/health/eeg?astronaut_id=AST-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["voltage_unit"], "µV")
        self.assertEqual(data["sampling_rate_hz"], 128)
        self.assertGreater(len(data["waveform"]), 100)
        meta = data["recording_meta"]
        self.assertIn("frequency_bands", meta)
        bands = meta["frequency_bands"]
        for b in ["delta", "theta", "alpha", "beta", "gamma"]:
            self.assertIn(b, bands)
            self.assertIn("power_pct", bands[b])
        self.assertIn("cognitive_workload", meta)
        self.assertIn("fatigue_index", meta)
        self.assertEqual(data["data_classification"], "simulated_demonstration_record")
        print(f"  ✓ /api/health/eeg verified ({len(data['waveform'])} samples at 128 Hz).")

    def test_06_body_regions_telemetry(self):
        """Test GET /api/astronaut/body-regions returns mappings for all 9 required regions + aliases."""
        res = self.client.get("/api/astronaut/body-regions?astronaut_id=AST-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["status"], "success")
        regions = data["regions"]
        required_regions = [
            "head", "chest", "heart", "lungs", "abdomen",
            "left_arm", "right_arm", "left_leg", "right_leg",
            "arms", "legs"
        ]
        for reg in required_regions:
            self.assertIn(reg, regions, f"Missing required region: {reg}")
            r_data = regions[reg]
            self.assertIn("name", r_data)
            self.assertIn("anatomical_systems", r_data)
            self.assertIn("spacesuit_interface", r_data)
            self.assertIn("primary_metrics", r_data)
            self.assertIn("radiation_research_context", r_data)
            self.assertIn("data_source", r_data)
            self.assertIn("disclaimer", r_data)
        print(f"  ✓ /api/astronaut/body-regions verified (all {len(required_regions)} regions validated).")

    def test_07_historical_endpoints(self):
        """Test GET /api/radiation/history, /api/health/history, and /api/alerts."""
        r_rad = self.client.get("/api/radiation/history?limit=5")
        self.assertEqual(r_rad.status_code, 200)

        r_hlth = self.client.get("/api/health/history?limit=5")
        self.assertEqual(r_hlth.status_code, 200)

        r_alr = self.client.get("/api/alerts?limit=5")
        self.assertEqual(r_alr.status_code, 200)
        print("  ✓ Historical telemetry and alerts endpoints verified.")

    def test_08_astronaut_model_endpoint(self):
        """Test GET /api/astronaut/model returns the realistic GLB model binary."""
        res = self.client.get("/api/astronaut/model")
        self.assertEqual(res.status_code, 200)
        self.assertIn("model/gltf-binary", res.headers.get("content-type", ""))
        self.assertGreater(len(res.content), 1_000_000)
        print(f"  ✓ /api/astronaut/model verified ({len(res.content):,} bytes GLTF binary streamed).")


if __name__ == "__main__":
    print("\n========================================================")
    print("RUNNING 3D ASTRONAUT DIGITAL TWIN VERIFICATION TESTS")
    print("========================================================")
    unittest.main()
