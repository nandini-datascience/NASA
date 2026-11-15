"""
radiation_streaming.py - Dynamic Radiation Data Collection & Telemetry Provider Engine for ASTRA CARE 2.0

Implements:
1. Modular RadiationDataProvider interface for:
   - Simulated streaming provider (for development, demonstration, and offline evaluation)
   - Real hardware radiation sensor adapter (for future physical sensors: USB, Serial, BLE)
   - Live spacecraft telemetry feed provider (for authenticated orbital downlinks)
2. Physics-grounded simulated telemetry generator:
   - Baseline Galactic Cosmic Ray (GCR) absorbed dose rate (~1.5 - 4.0 µGy/hr)
   - South Atlantic Anomaly (SAA) transit passes (~15 - 45 µGy/hr)
   - Realistic multi-detector telemetry (DosTel1, DosTel2, Lidal, REM-Lid, CPDS-01)
   - Orbital mechanics: 92-minute orbit, 51.6° ISS orbital inclination
3. Strict scientific labelling:
   - Simulated readings are explicitly marked: is_simulated=True, is_historical=False, data_source='simulated_streaming'
   - Real sensor & live spacecraft feeds are clearly distinguished
4. Streaming Engine with background thread, configurable interval, and live event injection.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import hashlib
import logging
import math
import random
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("astra_care.streaming")

# Standard ISS Orbital Parameters
ISS_ORBIT_PERIOD_MINUTES = 92.68
ISS_INCLINATION_DEG = 51.64
EARTH_RADIUS_KM = 6371.0
ISS_ALTITUDE_KM = 418.0

# South Atlantic Anomaly (SAA) Approximate Geographic Bounds
SAA_LAT_MIN = -45.0
SAA_LAT_MAX = -5.0
SAA_LON_MIN = -90.0
SAA_LON_MAX = 0.0


class RadiationDataProvider(ABC):
    """
    Abstract Base Class for radiation telemetry data sources.
    Enables hot-swapping between simulated demonstration data, physical hardware sensors,
    and live spacecraft telemetry without rewriting application logic.
    """

    @abstractmethod
    def get_next_reading(self) -> Optional[Dict[str, Any]]:
        """Produces or fetches the next radiation telemetry measurement."""
        pass

    @abstractmethod
    def is_live(self) -> bool:
        """Returns True if the provider represents an actual live physical feed."""
        pass

    @abstractmethod
    def provider_type(self) -> str:
        """Returns provider identifier: 'simulated_streaming', 'sensor_telemetry', 'live_spacecraft'."""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Returns detailed provider health, connectivity, and telemetry metadata."""
        pass


class SimulatedStreamingProvider(RadiationDataProvider):
    """
    Generates realistic, continuous, physics-informed space radiation telemetry.
    Simulates orbital movement of the ISS, periodic passage through the South Atlantic
    Anomaly (SAA), multi-detector geometry, and controllable anomaly events for ML testing.
    """

    DETECTORS = [
        {"id": "DosTel1", "module": "Columbus", "q_factor": 1.5, "base_ugy": 2.1, "noise_std": 0.25},
        {"id": "DosTel2", "module": "Columbus", "q_factor": 1.5, "base_ugy": 2.4, "noise_std": 0.30},
        {"id": "Lidal", "module": "Columbus", "q_factor": 1.8, "base_ugy": 2.2, "noise_std": 0.28},
        {"id": "REM-Lid", "module": "US Lab", "q_factor": 1.4, "base_ugy": 1.1, "noise_std": 0.18},
        {"id": "CPDS-01", "module": "Node 2", "q_factor": 1.6, "base_ugy": 1.8, "noise_std": 0.22}
    ]

    def __init__(self, sample_interval_seconds: float = 5.0):
        self.sample_interval = sample_interval_seconds
        self.orbital_phase_rad = 0.0  # 0 to 2*pi along orbit
        self.longitude_drift_deg = -80.0  # Starting longitude
        self.active_detector_idx = 0
        self.injected_anomaly: Optional[Dict[str, Any]] = None
        self.total_readings_emitted = 0
        self.last_emitted_time: Optional[datetime] = None

    def provider_type(self) -> str:
        return "simulated_streaming"

    def is_live(self) -> bool:
        return False  # Never claim simulated data is live!

    def inject_anomaly_event(self, anomaly_type: str = "SOLAR_SPIKE", duration_readings: int = 4, magnitude_ugy: float = 35.0):
        """
        Injects a temporary radiation surge or sensor glitch to test ML anomaly detection.
        Types: 'SOLAR_SPIKE', 'SAA_SURGE', 'SENSOR_NOISE', 'EXTREME_SEP'
        """
        self.injected_anomaly = {
            "type": anomaly_type,
            "remaining": duration_readings,
            "magnitude": magnitude_ugy
        }
        logger.info(f"Injected test radiation anomaly: {anomaly_type} (+{magnitude_ugy} µGy/hr for {duration_readings} ticks)")

    def inject_anomaly(self, factor: float = 10.0, duration_readings: int = 3, reason: str = "INJECTED_TEST_SPIKE"):
        """
        Alias for inject_anomaly_event for compatibility with test suites and external controllers.
        """
        magnitude = max(25.0, factor * 4.0)
        self.inject_anomaly_event(anomaly_type=reason, duration_readings=duration_readings, magnitude_ugy=magnitude)

    def clear_injected_anomaly(self):
        self.injected_anomaly = None

    def _is_in_saa(self, lat: float, lon: float) -> Tuple[bool, float]:
        """
        Calculates whether the spacecraft is within the SAA and returns an intensity factor (0.0 to 1.0).
        """
        if SAA_LAT_MIN <= lat <= SAA_LAT_MAX and SAA_LON_MIN <= lon <= SAA_LON_MAX:
            # Centered around Lat -25, Lon -45
            center_lat, center_lon = -25.0, -45.0
            dist = math.sqrt(((lat - center_lat) / 20.0) ** 2 + ((lon - center_lon) / 45.0) ** 2)
            intensity = max(0.0, 1.0 - dist)
            return True, intensity
        return False, 0.0

    def get_next_reading(self) -> Dict[str, Any]:
        """
        Computes the next realistic space radiation measurement.
        """
        now = datetime.now(timezone.utc)
        self.last_emitted_time = now

        # 1. Advance orbital position
        # One full orbit (2*pi) in 92.68 minutes
        phase_step = (2 * math.pi * (self.sample_interval / 60.0)) / ISS_ORBIT_PERIOD_MINUTES
        self.orbital_phase_rad = (self.orbital_phase_rad + phase_step) % (2 * math.pi)

        # Longitude rotates ~24 degrees west per orbit (~0.258 deg/min)
        lon_step = (360.0 / ISS_ORBIT_PERIOD_MINUTES) * (self.sample_interval / 60.0)
        self.longitude_drift_deg = (self.longitude_drift_deg - lon_step)
        if self.longitude_drift_deg < -180.0:
            self.longitude_drift_deg += 360.0

        # Latitude from orbital inclination
        current_lat = ISS_INCLINATION_DEG * math.sin(self.orbital_phase_rad)
        current_lon = self.longitude_drift_deg
        current_alt = ISS_ALTITUDE_KM + (2.0 * math.cos(self.orbital_phase_rad))  # small orbital eccentricity

        # 2. Select detector in round-robin fashion
        detector_info = self.DETECTORS[self.active_detector_idx]
        self.active_detector_idx = (self.active_detector_idx + 1) % len(self.DETECTORS)

        # 3. Base Galactic Cosmic Ray (GCR) Dose Rate
        base_rate = detector_info["base_ugy"]
        noise = random.gauss(0.0, detector_info["noise_std"])
        absorbed_dose_rate = max(0.2, base_rate + noise)

        # 4. South Atlantic Anomaly (SAA) Proton Belt Contribution
        in_saa, saa_intensity = self._is_in_saa(current_lat, current_lon)
        orbital_region = "NOMINAL_LEO"
        if in_saa:
            orbital_region = "SOUTH_ATLANTIC_ANOMALY"
            # In SAA, proton flux elevates absorbed dose significantly (~10 to 45 µGy/hr)
            absorbed_dose_rate += saa_intensity * random.uniform(15.0, 38.0)

        # 5. Injected Anomaly Handling (for ML verification)
        anomaly_flag_desc = None
        if self.injected_anomaly and self.injected_anomaly["remaining"] > 0:
            a_type = self.injected_anomaly["type"]
            a_mag = self.injected_anomaly["magnitude"]
            absorbed_dose_rate += a_mag + random.gauss(0.0, 1.5)
            anomaly_flag_desc = f"Injected Test Event: {a_type}"
            self.injected_anomaly["remaining"] -= 1
            if self.injected_anomaly["remaining"] <= 0:
                self.injected_anomaly = None

        # Dose equivalent rate (µSv/hr) = absorbed_dose_rate * radiation quality factor Q
        dose_eq_rate = round(absorbed_dose_rate * detector_info["q_factor"], 4)
        absorbed_dose_rate = round(absorbed_dose_rate, 4)

        # Particle flux (particles/(cm²·sr·s))
        flux_val = round((absorbed_dose_rate * 0.055) + random.uniform(0.01, 0.04), 4)

        # Unique reading ID
        ts_iso = now.isoformat()
        reading_hash = hashlib.sha256(f"{detector_info['id']}_{ts_iso}_{absorbed_dose_rate}".encode()).hexdigest()[:12].upper()
        reading_id = f"STR-{detector_info['id']}-{reading_hash}"

        self.total_readings_emitted += 1

        reading = {
            "reading_id": reading_id,
            "timestamp": ts_iso,
            "instrument_id": detector_info["id"],
            "spacecraft": "ISS",
            "module": detector_info["module"],
            "absorbed_dose_rate": absorbed_dose_rate,
            "absorbed_dose_unit": "µGy/hr",
            "dose_equivalent_rate": dose_eq_rate,
            "dose_equivalent_unit": "µSv/hr",
            "flux": flux_val,
            "flux_unit": "particles/(cm²·sr·s)",
            "altitude": round(current_alt, 2),
            "altitude_unit": "km",
            "latitude": round(current_lat, 4),
            "longitude": round(current_lon, 4),
            "orbital_region": orbital_region,
            "data_source": "simulated_streaming",
            "is_simulated": True,
            "is_historical": False,
            "is_live": False,
            "measurement_quality": "simulated_event" if anomaly_flag_desc else "nominal",
            "telemetry_nature": "Simulated dynamic radiation stream (demonstration; NOT live spacecraft telemetry)",
            "test_annotation": anomaly_flag_desc
        }

        return reading

    def get_status(self) -> Dict[str, Any]:
        return {
            "provider_type": self.provider_type(),
            "status": "active_streaming",
            "is_live": self.is_live(),
            "is_simulated": True,
            "sample_interval_seconds": self.sample_interval,
            "total_readings_emitted": self.total_readings_emitted,
            "last_emitted_time": self.last_emitted_time.isoformat() if self.last_emitted_time else None,
            "detectors_available": [d["id"] for d in self.DETECTORS],
            "injected_anomaly_active": bool(self.injected_anomaly),
            "telemetry_notice": "Streaming simulated demonstration telemetry with authentic LEO orbital physics."
        }


class HardwareSensorProvider(RadiationDataProvider):
    """
    Pluggable hardware radiation sensor adapter for physical Geiger counters,
    silicon diode dosimeters, or solid-state detectors (USB/UART/Serial/BLE).
    """

    def __init__(self, port: str = "COM3", baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.connected = False
        self.last_error = "No physical hardware sensor attached on serial interface."

    def provider_type(self) -> str:
        return "sensor_telemetry"

    def is_live(self) -> bool:
        return self.connected

    def get_next_reading(self) -> Optional[Dict[str, Any]]:
        if not self.connected:
            raise RuntimeError("No physical hardware sensor connected on serial port.")
        return None

    def get_status(self) -> Dict[str, Any]:
        return {
            "provider_type": self.provider_type(),
            "status": "hardware_standby" if not self.connected else "hardware_connected",
            "is_live": self.connected,
            "sensor_connected": self.connected,
            "port": self.port,
            "baudrate": self.baudrate,
            "device_status": "disconnected" if not self.connected else "operational",
            "last_error": self.last_error,
            "instructions": "Connect USB/UART radiation sensor (e.g. RadSense-3001, bGeigie, Gamma-Scout) to activate real physical telemetry."
        }


class LiveSpacecraftTelemetryProvider(RadiationDataProvider):
    """
    Pluggable orbital telemetry adapter for authenticated live spacecraft feeds
    (e.g., NASA OSDR Live Telemetry Stream, ESA Columbus Payload Feed, JAXA Kibo Stream).
    """

    def __init__(self, endpoint_url: Optional[str] = None, api_key: Optional[str] = None):
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.connected = False

    def provider_type(self) -> str:
        return "live_spacecraft"

    def is_live(self) -> bool:
        return self.connected

    def get_next_reading(self) -> Optional[Dict[str, Any]]:
        if not self.connected:
            raise RuntimeError("Live spacecraft telemetry downlink is not established.")
        return None

    def get_status(self) -> Dict[str, Any]:
        return {
            "provider_type": self.provider_type(),
            "status": "downlink_standby",
            "orbital_feed_status": "orbital_feed_standby",
            "is_live": False,
            "link_established": self.connected,
            "endpoint_configured": bool(self.endpoint_url),
            "instructions": "Configure live NASA/ESA spacecraft telemetry API endpoint and authentication token to switch to live downlink."
        }


class RadiationStreamEngine:
    """
    Manages active streaming provider, coordinates automatic data processing,
    runs the ML anomaly evaluation, and updates the shared telemetry state.
    """

    def __init__(
        self,
        provider: Optional[RadiationDataProvider] = None,
        process_callback: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        interval_seconds: float = 5.0
    ):
        self.provider: RadiationDataProvider = provider or SimulatedStreamingProvider(sample_interval_seconds=interval_seconds)
        self.process_callback = process_callback
        self.interval_seconds = interval_seconds
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Cache of recent dynamic readings (for fast polling / UI)
        self._recent_readings: List[Dict[str, Any]] = []
        self._max_recent_cache = 100
        self.latest_reading: Optional[Dict[str, Any]] = None

    def register_callback(self, callback: Callable[[Dict[str, Any]], Dict[str, Any]]):
        """Register processing callback function."""
        with self._lock:
            self.process_callback = callback

    def step_single_tick(self) -> Optional[Dict[str, Any]]:
        """Alias for tick_once."""
        return self.tick_once()

    def set_provider(self, provider: RadiationDataProvider):
        with self._lock:
            self.provider = provider
            logger.info(f"Switched radiation stream provider to: {provider.provider_type()}")

    def set_interval(self, seconds: float):
        clamped = max(1.0, min(60.0, float(seconds)))
        with self._lock:
            self.interval_seconds = clamped
            if isinstance(self.provider, SimulatedStreamingProvider):
                self.provider.sample_interval = clamped
        logger.info(f"Updated streaming interval to {clamped}s")

    def tick_once(self) -> Optional[Dict[str, Any]]:
        """
        Manually produces, processes, and caches a single telemetry reading.
        Useful for synchronous testing and step-by-step evaluation.
        """
        reading = self.provider.get_next_reading()
        if not reading:
            return None

        # Execute processing pipeline callback (ML evaluation, alert checks, DB persistence)
        processed = reading
        if self.process_callback:
            try:
                cb_res = self.process_callback(reading)
                if isinstance(cb_res, dict):
                    processed = cb_res
            except Exception as exc:
                logger.error(f"Error in stream processing callback: {exc}")

        with self._lock:
            self.latest_reading = processed
            self._recent_readings.append(processed)
            if len(self._recent_readings) > self._max_recent_cache:
                self._recent_readings.pop(0)

        return processed

    def _stream_worker(self):
        logger.info(f"Radiation stream engine background worker started (interval: {self.interval_seconds}s)")
        while not self._stop_event.is_set():
            try:
                self.tick_once()
            except Exception as exc:
                logger.error(f"Error in radiation streaming worker: {exc}")

            # Sleep in short increments to allow responsive stopping
            sleep_chunks = int(self.interval_seconds * 10)
            for _ in range(max(1, sleep_chunks)):
                if self._stop_event.is_set():
                    break
                time.sleep(0.1)

        logger.info("Radiation stream engine background worker stopped.")

    def start(self):
        with self._lock:
            if self.is_running:
                return
            self.is_running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._stream_worker, daemon=True)
            self._thread.start()
            logger.info("Radiation stream engine started.")

    def pause(self):
        with self._lock:
            if not self.is_running:
                return
            self.is_running = False
            self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Radiation stream engine paused.")

    def get_latest(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return dict(self.latest_reading) if self.latest_reading else None

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            count = min(limit, len(self._recent_readings))
            return [dict(r) for r in self._recent_readings[-count:]]

    def get_engine_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "is_running": self.is_running,
                "interval_seconds": self.interval_seconds,
                "provider": self.provider.get_status(),
                "cached_readings_count": len(self._recent_readings),
                "latest_timestamp": self.latest_reading.get("timestamp") if self.latest_reading else None,
                "latest_detector": self.latest_reading.get("instrument_id") if self.latest_reading else None,
                "latest_dose_rate": self.latest_reading.get("absorbed_dose_rate") if self.latest_reading else None
            }


def default_radiation_processing_pipeline(reading: Dict[str, Any]) -> Dict[str, Any]:
    """
    Automatic end-to-end processing pipeline for incoming radiation telemetry:
    1. Runs ML Anomaly Detection (Isolation Forest).
    2. Enriches reading with anomaly score, baseline z-score, and plain-language explanation.
    3. Persists ML anomaly record into SQLite if flagged.
    4. Evaluates aerospace operational threshold benchmarks (NASA-STD-3001 / NCRP-132).
    5. Stores dynamic reading into SQLite database.
    """
    from app.ml.model import get_detector
    from app.db import insert_dynamic_radiation_reading, insert_ml_anomaly_record, insert_alerts
    from app.analysis import generate_alert_id

    engine = get_stream_engine()
    prev_reading = engine.latest_reading

    # 1. Machine Learning Anomaly Detection Inference
    detector = get_detector()
    ml_eval = detector.predict_reading(reading, prev_reading)

    reading["ml_is_anomaly"] = ml_eval["is_anomaly"]
    reading["ml_anomaly_score"] = ml_eval["anomaly_score"]
    reading["ml_severity"] = ml_eval["severity"]
    reading["ml_anomaly_reason"] = ml_eval["explanation"]
    reading["ml_analysis"] = ml_eval

    # 2. Persist ML Anomaly Record if flagged
    if ml_eval["is_anomaly"]:
        anomaly_rec = {
            "anomaly_id": f"ML-ALT-{reading['reading_id']}",
            "reading_id": reading["reading_id"],
            "timestamp": reading["timestamp"],
            "instrument_id": reading["instrument_id"],
            "absorbed_dose_rate": reading["absorbed_dose_rate"],
            "unit": reading.get("absorbed_dose_unit", "µGy/hr"),
            "anomaly_score": ml_eval["anomaly_score"],
            "severity": ml_eval["severity"],
            "primary_contributing_feature": ml_eval.get("primary_contributing_feature"),
            "baseline_z_score": ml_eval.get("baseline_z_score"),
            "dose_rate_delta": ml_eval.get("dose_rate_delta"),
            "explanation": ml_eval["explanation"],
            "recommendation": ml_eval["recommendation"],
            "data_source": reading.get("data_source", "simulated_streaming")
        }
        try:
            insert_ml_anomaly_record(anomaly_rec)
        except Exception as exc:
            logger.warning(f"Error persisting ML anomaly: {exc}")

    # 3. Validated Threshold Radiation Alert (NASA-STD-3001 / NCRP-132)
    dose_rate = float(reading.get("absorbed_dose_rate") or 0.0)
    if dose_rate >= 20.0:
        sev = "CRITICAL" if dose_rate >= 100.0 else "WARNING"
        threshold_applied = 100.0 if dose_rate >= 100.0 else 20.0
        alt_type = "HIGH_DOSE_RATE" if dose_rate >= 100.0 else "ELEVATED_DOSE_RATE"
        alert_obj = {
            "alert_id": generate_alert_id(alt_type, reading["timestamp"], reading["instrument_id"], "HEALTH_RISK_ALERT"),
            "category": "HEALTH_RISK_ALERT",
            "severity": sev,
            "alert_type": alt_type,
            "timestamp": reading["timestamp"],
            "instrument_id": reading["instrument_id"],
            "spacecraft": reading.get("spacecraft", "ISS"),
            "metric_name": "absorbed_dose_rate",
            "metric_value": dose_rate,
            "threshold_applied": threshold_applied,
            "unit": "µGy/hr",
            "description": f"Radiation reading {dose_rate} µGy/hr exceeded {sev} threshold ({threshold_applied} µGy/hr).",
            "recommendation": "Monitor radiation trajectory. Common during SAA passage or solar flare activity.",
            "guideline_reference": "NASA-STD-3001 Vol 1 / NCRP Report No. 132"
        }
        try:
            insert_alerts([alert_obj])
        except Exception as exc:
            logger.warning(f"Error persisting threshold alert: {exc}")

    # 4. Persist reading into dynamic_radiation_records
    try:
        insert_dynamic_radiation_reading(reading)
    except Exception as exc:
        logger.warning(f"Error persisting dynamic radiation reading: {exc}")

    return reading


# Global singleton streaming engine instance
_global_stream_engine: Optional[RadiationStreamEngine] = None

def get_stream_engine() -> RadiationStreamEngine:
    global _global_stream_engine
    if _global_stream_engine is None:
        _global_stream_engine = RadiationStreamEngine(process_callback=default_radiation_processing_pipeline)
    return _global_stream_engine
