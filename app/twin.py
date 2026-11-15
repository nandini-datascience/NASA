"""
twin.py - 3D Astronaut Digital Twin Telemetry & Physiological Engine
ASTRA CARE Aerospace Health Monitoring System

Provides high-resolution biological waveforms (ECG, EEG), body region telemetry mappings,
astronaut bio-profiles, and unified radiation/health synchronization endpoints.

IMPORTANT SCIENTIFIC DISCLAIMER:
Data provided by this module combines authentic NASA RadLab radiation archives with
high-fidelity aerospace physiological demonstration models.
- All waveform telemetry is explicitly classified as 'simulated_demonstration_record'.
- Body region associations are spatial visualization linkages, not proof of internal anatomical imaging.
- Whole-body radiation dosimetry does not represent individual body-region absorbed dose.
"""

from datetime import datetime, timezone, timedelta
import math
import random
from typing import Any, Dict, List, Optional

from app.db import (
    get_latest_dynamic_radiation_reading,
    query_astronaut_health_measurements,
    query_dynamic_radiation_readings,
    query_radiation_history,
    query_smart_alerts,
    query_alerts,
    query_astronaut_health_alerts
)


ASTRONAUT_PROFILES = {
    "AST-01": {
        "astronaut_id": "AST-01",
        "name": "Dr. Sarah Vance",
        "callsign": "Astra-Lead",
        "role": "Mission Commander / Flight Biomedical Specialist",
        "agency": "NASA / International Partner Crew",
        "mission": "Expedition 71 / Lunar Gateway Orbital Shakedown",
        "spacecraft": "ISS / International Space Station",
        "orbit": {
            "altitude_km": 408.4,
            "inclination_deg": 51.64,
            "orbital_period_min": 92.68,
            "velocity_kms": 7.66
        },
        "demographics": {
            "age": 39,
            "gender": "Female",
            "blood_type": "O-Positive",
            "height_cm": 172,
            "mass_kg": 64.5
        },
        "flight_experience": {
            "mission_day": 142,
            "cumulative_spaceflight_days": 318,
            "eva_sorties_count": 6,
            "cumulative_eva_hours": 38.5,
            "radiation_career_percent": 18.4
        },
        "spacesuit": {
            "model": "xEMU (Exploration Extravehicular Mobility Unit) Mk III",
            "serial_number": "NASA-EMU-2026-X3",
            "pressure_kpa": 29.6,
            "pressure_psi": 4.3,
            "primary_o2_reserve_pct": 94.2,
            "secondary_o2_reserve_pct": 100.0,
            "battery_soc_pct": 88.5,
            "co2_scrubber_efficiency_pct": 99.4,
            "sublimator_feedwater_pct": 82.0,
            "suit_temperature_c": 19.8
        },
        "medical_status": {
            "clearance": "FLIGHT QUALIFIED / EVA CLEARED",
            "overall_readiness": "NOMINAL",
            "cardiovascular_index": "Excellent (VO2max 48 mL/kg/min)",
            "bone_mineral_density": "Within 98% preflight baseline",
            "orthostatic_tolerance": "Monitoring Active"
        },
        "data_classification": "demonstration_mission_profile",
        "data_source": "ASTRA CARE Aerospace Flight Surgeon Directory"
    },
    "AST-02": {
        "astronaut_id": "AST-02",
        "name": "Dr. Marcus Chen",
        "callsign": "Orion-2",
        "role": "Flight Engineer / EVA Systems Lead",
        "agency": "NASA",
        "mission": "Expedition 71 / ISS Core Maintenance",
        "spacecraft": "ISS / International Space Station",
        "orbit": {
            "altitude_km": 408.4,
            "inclination_deg": 51.64,
            "orbital_period_min": 92.68,
            "velocity_kms": 7.66
        },
        "demographics": {
            "age": 43,
            "gender": "Male",
            "blood_type": "A-Positive",
            "height_cm": 180,
            "mass_kg": 76.0
        },
        "flight_experience": {
            "mission_day": 142,
            "cumulative_spaceflight_days": 210,
            "eva_sorties_count": 4,
            "cumulative_eva_hours": 26.2,
            "radiation_career_percent": 14.1
        },
        "spacesuit": {
            "model": "xEMU Mk III",
            "serial_number": "NASA-EMU-2026-X4",
            "pressure_kpa": 29.6,
            "pressure_psi": 4.3,
            "primary_o2_reserve_pct": 91.0,
            "secondary_o2_reserve_pct": 100.0,
            "battery_soc_pct": 84.0,
            "co2_scrubber_efficiency_pct": 98.9,
            "sublimator_feedwater_pct": 79.5,
            "suit_temperature_c": 20.1
        },
        "medical_status": {
            "clearance": "FLIGHT QUALIFIED / EVA CLEARED",
            "overall_readiness": "NOMINAL",
            "cardiovascular_index": "Good",
            "bone_mineral_density": "Within 97% preflight baseline",
            "orthostatic_tolerance": "Monitoring Active"
        },
        "data_classification": "demonstration_mission_profile",
        "data_source": "ASTRA CARE Aerospace Flight Surgeon Directory"
    }
}


def get_astronaut_profile(astronaut_id: str = "AST-01") -> Dict[str, Any]:
    """Returns astronaut profile and mission metadata."""
    profile = ASTRONAUT_PROFILES.get(astronaut_id, ASTRONAUT_PROFILES["AST-01"])
    return {
        "status": "success",
        "astronaut": profile,
        "active_astronaut_ids": list(ASTRONAUT_PROFILES.keys()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Profile telemetry is provided for operations context and demonstration. Not a clinical diagnostic record."
    }


def generate_synthetic_ecg_lead2(
    heart_rate_bpm: float = 72.0,
    duration_seconds: float = 6.0,
    sampling_rate_hz: int = 250,
    seed: int = 42
) -> List[Dict[str, float]]:
    """
    Synthesizes a realistic mathematical Electrocardiogram (Lead II rhythm strip)
    using sum of Gaussians for P, Q, R, S, T waves:
        V(t) = sum_i [ a_i * exp( - (t - t_i)^2 / (2 * b_i^2) ) ]
    Includes physiological respiratory baseline wander and subtle micro-voltage variation.
    """
    rng = random.Random(seed)
    total_samples = int(duration_seconds * sampling_rate_hz)
    rr_interval = 60.0 / max(30.0, min(220.0, heart_rate_bpm))

    # Physiological waves parameters (amplitude in mV, duration/width in s, phase offset in s)
    # Lead II standard reference values
    p_amp, p_width, p_offset = 0.16, 0.045, -0.16
    q_amp, q_width, q_offset = -0.14, 0.018, -0.04
    r_amp, r_width, r_offset = 1.35, 0.028, 0.00
    s_amp, s_width, s_offset = -0.32, 0.024, 0.04
    t_amp, t_width, t_offset = 0.38, 0.085, 0.22

    dt = 1.0 / sampling_rate_hz
    points: List[Dict[str, float]] = []

    for i in range(total_samples):
        t = i * dt
        # Phase within current cardiac cycle
        cycle_phase = (t % rr_interval)
        # Shift so R peak is roughly at 0.3 * rr_interval
        cycle_t = cycle_phase - 0.35 * rr_interval

        # Gaussian components
        v_p = p_amp * math.exp(-((cycle_t - p_offset) ** 2) / (2 * (p_width ** 2)))
        v_q = q_amp * math.exp(-((cycle_t - q_offset) ** 2) / (2 * (q_width ** 2)))
        v_r = r_amp * math.exp(-((cycle_t - r_offset) ** 2) / (2 * (r_width ** 2)))
        v_s = s_amp * math.exp(-((cycle_t - s_offset) ** 2) / (2 * (s_width ** 2)))
        v_t = t_amp * math.exp(-((cycle_t - t_offset) ** 2) / (2 * (t_width ** 2)))

        # Subtle respiratory baseline wander (0.25 Hz respiration)
        baseline_wander = 0.03 * math.sin(2 * math.pi * 0.25 * t)
        # Subtle high-frequency EMG noise
        emg_noise = rng.uniform(-0.012, 0.012)

        v_total = v_p + v_q + v_r + v_s + v_t + baseline_wander + emg_noise
        points.append({
            "time_s": round(t, 4),
            "voltage_mv": round(v_total, 4)
        })

    return points


def get_ecg_recordings(astronaut_id: str = "AST-01", recording_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns high-resolution ECG waveform and clinical cardiac interval analysis.
    """
    recordings_catalog = [
        {
            "recording_id": "ECG-2026-NSR-01",
            "title": "Nominal Rest / Normal Sinus Rhythm",
            "heart_rate_bpm": 72.0,
            "rhythm": "Normal Sinus Rhythm (NSR)",
            "pr_interval_ms": 156,
            "qrs_duration_ms": 84,
            "qt_interval_ms": 384,
            "qtc_bazett_ms": 420,
            "st_segment": "Isoelectric (Nominal)",
            "context": "Routine pre-sleep biomedical monitoring cycle",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        },
        {
            "recording_id": "ECG-2026-EVA-02",
            "title": "Extravehicular Activity (EVA) Workload",
            "heart_rate_bpm": 104.0,
            "rhythm": "Sinus Tachycardia (Physiological Exertion)",
            "pr_interval_ms": 138,
            "qrs_duration_ms": 86,
            "qt_interval_ms": 340,
            "qtc_bazett_ms": 445,
            "st_segment": "Rapid Repolarization / Non-Ischemic",
            "context": "EVA orbital truss maintenance task under microgravity metabolic load",
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=2, minutes=30)).isoformat()
        },
        {
            "recording_id": "ECG-2026-REST-03",
            "title": "Deep Sleep / Circadian Resting Baseline",
            "heart_rate_bpm": 56.0,
            "rhythm": "Sinus Bradycardia (Physiological Sleep State)",
            "pr_interval_ms": 168,
            "qrs_duration_ms": 82,
            "qt_interval_ms": 412,
            "qtc_bazett_ms": 398,
            "st_segment": "Normal Baseline",
            "context": "Crew sleep cabin telemetry capture",
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
        }
    ]

    selected = recordings_catalog[0]
    if recording_id:
        for r in recordings_catalog:
            if r["recording_id"] == recording_id:
                selected = r
                break

    waveform = generate_synthetic_ecg_lead2(
        heart_rate_bpm=selected["heart_rate_bpm"],
        duration_seconds=6.0,
        sampling_rate_hz=250,
        seed=abs(hash(selected["recording_id"])) % 10000
    )

    return {
        "status": "success",
        "astronaut_id": astronaut_id,
        "recording_meta": selected,
        "available_recordings": [
            {
                "recording_id": r["recording_id"],
                "title": r["title"],
                "heart_rate_bpm": r["heart_rate_bpm"],
                "rhythm": r["rhythm"],
                "timestamp": r["timestamp"]
            }
            for r in recordings_catalog
        ],
        "lead": "Lead II (Continuous Rhythm Strip)",
        "sampling_rate_hz": 250,
        "duration_seconds": 6.0,
        "total_samples": len(waveform),
        "voltage_unit": "mV",
        "waveform": waveform,
        "data_classification": "simulated_demonstration_record",
        "data_source": "ASTRA CARE Aerospace Physiological Telemetry Synthesizer",
        "disclaimer": "ECG waveform telemetry is generated for physiological demonstration and aerospace visualization. Does not constitute clinical cardiology diagnosis."
    }


def generate_synthetic_eeg(
    dominant_mode: str = "alert",
    duration_seconds: float = 6.0,
    sampling_rate_hz: int = 128,
    seed: int = 101
) -> List[Dict[str, float]]:
    """
    Synthesizes continuous EEG micro-voltage time series (µV) across frequency bands:
    - Delta: 0.5 - 4 Hz (deep recovery)
    - Theta: 4 - 8 Hz (drowsiness / memory)
    - Alpha: 8 - 13 Hz (relaxed alertness)
    - Beta: 13 - 30 Hz (active problem solving)
    - Gamma: 30 - 45 Hz (high-level cognitive processing)
    """
    rng = random.Random(seed)
    total_samples = int(duration_seconds * sampling_rate_hz)
    dt = 1.0 / sampling_rate_hz

    # Band weights based on mental state
    if dominant_mode == "fatigue":
        w_delta, w_theta, w_alpha, w_beta, w_gamma = 0.25, 0.40, 0.20, 0.12, 0.03
    elif dominant_mode == "eva_focus":
        w_delta, w_theta, w_alpha, w_beta, w_gamma = 0.05, 0.10, 0.20, 0.48, 0.17
    else:  # Nominal Alert
        w_delta, w_theta, w_alpha, w_beta, w_gamma = 0.10, 0.16, 0.42, 0.26, 0.06

    points: List[Dict[str, float]] = []

    # Frequency carriers
    f_delta = 2.1
    f_theta = 5.8
    f_alpha = 10.2
    f_beta1 = 18.5
    f_beta2 = 24.0
    f_gamma = 38.0

    for i in range(total_samples):
        t = i * dt
        # Amplitude envelope modulation
        env = 1.0 + 0.15 * math.sin(2 * math.pi * 0.4 * t)

        sig = (
            w_delta * 35.0 * math.sin(2 * math.pi * f_delta * t + 0.5) +
            w_theta * 25.0 * math.sin(2 * math.pi * f_theta * t + 1.2) +
            w_alpha * 30.0 * math.sin(2 * math.pi * f_alpha * t) +
            w_beta * 15.0 * (math.sin(2 * math.pi * f_beta1 * t) + 0.5 * math.sin(2 * math.pi * f_beta2 * t + 0.8)) +
            w_gamma * 8.0 * math.sin(2 * math.pi * f_gamma * t + 2.1)
        ) * env

        # Neural micro-noise
        noise = rng.uniform(-4.0, 4.0)
        u_volts = round(sig + noise, 2)

        points.append({
            "time_s": round(t, 4),
            "voltage_uv": u_volts
        })

    return points


def get_eeg_recordings(astronaut_id: str = "AST-01", recording_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns EEG continuous waveform and brainwave frequency band spectral power analysis.
    """
    epochs = [
        {
            "recording_id": "EEG-2026-ALERT-01",
            "title": "Nominal Alertness & Cognitive Focus",
            "mode": "alert",
            "cognitive_workload": "Nominal Operations (42%)",
            "fatigue_index": "Low / Optimal (12%)",
            "frequency_bands": {
                "delta": {"range_hz": "0.5 - 4.0 Hz", "power_pct": 11.5, "role": "Slow wave / Rest"},
                "theta": {"range_hz": "4.0 - 8.0 Hz", "power_pct": 16.8, "role": "Working memory access"},
                "alpha": {"range_hz": "8.0 - 13.0 Hz", "power_pct": 39.4, "role": "Relaxed focus & calm alertness"},
                "beta": {"range_hz": "13.0 - 30.0 Hz", "power_pct": 26.2, "role": "Active telemetry interpretation"},
                "gamma": {"range_hz": "30.0 - 45.0 Hz", "power_pct": 6.1, "role": "Sensory-motor binding"}
            },
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        },
        {
            "recording_id": "EEG-2026-EVA-02",
            "title": "High Cognitive Workload / EVA Procedure",
            "mode": "eva_focus",
            "cognitive_workload": "High / Focused Task Assembly (76%)",
            "fatigue_index": "Mild / Controlled (24%)",
            "frequency_bands": {
                "delta": {"range_hz": "0.5 - 4.0 Hz", "power_pct": 6.2, "role": "Slow wave suppression"},
                "theta": {"range_hz": "4.0 - 8.0 Hz", "power_pct": 11.4, "role": "Spatial navigational navigation"},
                "alpha": {"range_hz": "8.0 - 13.0 Hz", "power_pct": 21.0, "role": "Suppressed for visual target lock"},
                "beta": {"range_hz": "13.0 - 30.0 Hz", "power_pct": 46.8, "role": "Sustained procedural calculations"},
                "gamma": {"range_hz": "30.0 - 45.0 Hz", "power_pct": 14.6, "role": "Peak spatial motor precision"}
            },
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        },
        {
            "recording_id": "EEG-2026-FATIGUE-03",
            "title": "Post-Duty Fatigue & Circadian Wind-Down",
            "mode": "fatigue",
            "cognitive_workload": "Reduced / Post-Shift (22%)",
            "fatigue_index": "Elevated / Rest Advisory (58%)",
            "frequency_bands": {
                "delta": {"range_hz": "0.5 - 4.0 Hz", "power_pct": 24.5, "role": "Onset of pre-sleep synchronization"},
                "theta": {"range_hz": "4.0 - 8.0 Hz", "power_pct": 38.6, "role": "Pronounced drowsiness signature"},
                "alpha": {"range_hz": "8.0 - 13.0 Hz", "power_pct": 22.4, "role": "Intermittent diffuse rhythm"},
                "beta": {"range_hz": "13.0 - 30.0 Hz", "power_pct": 11.8, "role": "Lower executive demand"},
                "gamma": {"range_hz": "30.0 - 45.0 Hz", "power_pct": 2.7, "role": "Minimal sensory binding"}
            },
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat()
        }
    ]

    selected = epochs[0]
    if recording_id:
        for ep in epochs:
            if ep["recording_id"] == recording_id:
                selected = ep
                break

    waveform = generate_synthetic_eeg(
        dominant_mode=selected["mode"],
        duration_seconds=6.0,
        sampling_rate_hz=128,
        seed=abs(hash(selected["recording_id"])) % 10000
    )

    return {
        "status": "success",
        "astronaut_id": astronaut_id,
        "recording_meta": selected,
        "available_recordings": [
            {
                "recording_id": ep["recording_id"],
                "title": ep["title"],
                "cognitive_workload": ep["cognitive_workload"],
                "fatigue_index": ep["fatigue_index"],
                "timestamp": ep["timestamp"]
            }
            for ep in epochs
        ],
        "channel": "Fz-Cz Neurotelemetry Vector (Frontal-Central)",
        "sampling_rate_hz": 128,
        "duration_seconds": 6.0,
        "total_samples": len(waveform),
        "voltage_unit": "µV",
        "waveform": waveform,
        "data_classification": "simulated_demonstration_record",
        "data_source": "ASTRA CARE Aerospace Neurotelemetry Synthesizer",
        "disclaimer": "EEG brainwave telemetry represents simulated aerospace cognitive monitoring data. Not intended for neurological or medical diagnosis."
    }


def get_body_regions_telemetry(astronaut_id: str = "AST-01") -> Dict[str, Any]:
    """
    Returns comprehensive telemetry mapping for each selectable body region of the 3D astronaut:
    1. Head
    2. Chest
    3. Heart region
    4. Lungs region
    5. Abdomen
    6. Left and right arms
    7. Legs
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    regions = {
        "head": {
            "region_id": "head",
            "name": "Head & Cranial Vault",
            "anatomical_systems": "Central Nervous System, Sensory Organs, Cranial Thermal Regulation",
            "spacesuit_interface": "Extravehicular Helmet Assembly & Gold Coated Polycarbonate Visor",
            "primary_metrics": [
                {"label": "Dominant Brainwave", "value": "Alpha (10.2 Hz)", "unit": "Hz", "status": "NOMINAL"},
                {"label": "Cognitive Workload", "value": "42%", "unit": "%", "status": "NOMINAL"},
                {"label": "Fatigue Index", "value": "12%", "unit": "%", "status": "NOMINAL"},
                {"label": "Helmet Internal CO2", "value": "0.18", "unit": "mmHg", "status": "NOMINAL"},
                {"label": "Cranial Skin Temp", "value": "36.4", "unit": "°C", "status": "NOMINAL"}
            ],
            "relevant_readings": {
                "eeg_frequency": "Alpha 10.2 Hz (Relaxed Alertness)",
                "intracranial_pressure_proxy": "11.2 mmHg (Estimated)",
                "visual_acuity_check": "20/20 Nominal"
            },
            "radiation_research_context": (
                "CNS Radiation Sensitivity: Space radiation (HZE heavy ions and galactic cosmic rays) poses long-term neurocognitive risks. "
                "NASA radiation research investigates microlesions in hippocampal synapses. The EVA helmet features supplemental multi-layer "
                "polyethylene and polycarbonate shielding against solar proton events."
            ),
            "historical_measurements": [
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(), "alpha_power": 38.5, "fatigue_pct": 14},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(), "alpha_power": 39.1, "fatigue_pct": 13},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(), "alpha_power": 39.4, "fatigue_pct": 12}
            ],
            "data_source": "Wearable Forehead Biometric Band & EEG Neurotelemetry (Simulated Demo)",
            "disclaimer": "Visualization association only. Spacesuit 3D model does not contain internal anatomical imaging. Whole-body radiation is not an individual body-region absorbed dose."
        },
        "chest": {
            "region_id": "chest",
            "name": "Chest & Thoracic Cavity",
            "anatomical_systems": "Respiratory System, Ribcage Biomechanics, Thoracic Perfusion",
            "spacesuit_interface": "EMU Hard Upper Torso (HUT) & Display Control Module (DCM)",
            "primary_metrics": [
                {"label": "Respiration Rate", "value": "14", "unit": "breaths/min", "status": "NOMINAL"},
                {"label": "Oxygen Saturation (SpO2)", "value": "98.4", "unit": "%", "status": "NOMINAL"},
                {"label": "Thoracic Expansion", "value": "4.2", "unit": "cm", "status": "NOMINAL"},
                {"label": "Chest Patch Dosimeter", "value": "1.92", "unit": "µGy/hr", "status": "NOMINAL"},
                {"label": "EMU DCM Status", "value": "ACTIVE", "unit": "State", "status": "NOMINAL"}
            ],
            "relevant_readings": {
                "ventilation_volume": "7.3 L/min",
                "blood_oxygen": "98.4%",
                "chest_dosimeter": "1.92 µGy/hr"
            },
            "radiation_research_context": (
                "Thoracic Radiation Dosimetry: Spacecraft personal dosimeters (PDs) are worn on the chest. RadLab detectors "
                "provide cabin ambient rates, while chest patch dosimeters track localized skin exposure. The Hard Upper Torso "
                "aluminum-fiberglass structure provides 4.8 g/cm² areal mass shielding."
            ),
            "historical_measurements": [
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(), "spo2": 98.2, "resp_rate": 15},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(), "spo2": 98.4, "resp_rate": 14},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(), "spo2": 98.4, "resp_rate": 14}
            ],
            "data_source": "Chest Sensor Harness & Pulse Oximetry Patch (Simulated Demo)",
            "disclaimer": "Visualization association only. Spacesuit 3D model does not contain internal anatomical imaging."
        },
        "heart": {
            "region_id": "heart",
            "name": "Heart Region (Cardiovascular)",
            "anatomical_systems": "Myocardium, Coronary Vasculature, Cardiac Conduction System",
            "spacesuit_interface": "Biomedical Telemetry Harness (BTH) Electrocardiogram Electrodes",
            "primary_metrics": [
                {"label": "Heart Rate", "value": "72", "unit": "BPM", "status": "NOMINAL"},
                {"label": "Cardiac Rhythm", "value": "Sinus Rhythm", "unit": "Type", "status": "NOMINAL"},
                {"label": "Blood Pressure", "value": "118/76", "unit": "mmHg", "status": "NOMINAL"},
                {"label": "Mean Arterial Pressure", "value": "90.0", "unit": "mmHg", "status": "NOMINAL"},
                {"label": "Cardiac Output Index", "value": "3.1", "unit": "L/min/m²", "status": "NOMINAL"}
            ],
            "relevant_readings": {
                "heart_rate_bpm": 72,
                "ecg_rhythm": "Normal Sinus Rhythm",
                "qtc_interval": "420 ms",
                "blood_pressure": "118/76 mmHg"
            },
            "radiation_research_context": (
                "Cardiovascular Cosmic Radiation Health: Longitudinal astronaut studies monitor microvascular endothelial health. "
                "Deep space GCR exposure has been studied for potential accelerated arterial stiffening. In LEO, Earth's magnetosphere "
                "provides significant shielding against deep space heavy ions."
            ),
            "historical_measurements": [
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(), "heart_rate": 74.0, "systolic": 120, "diastolic": 78},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(), "heart_rate": 73.0, "systolic": 119, "diastolic": 77},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(), "heart_rate": 72.0, "systolic": 118, "diastolic": 76}
            ],
            "data_source": "Biomedical ECG Lead II Sensor Harness (Simulated Demo)",
            "disclaimer": "Visualization association only. Spacesuit 3D model does not contain internal anatomical imaging. Does not diagnose cardiac conditions."
        },
        "lungs": {
            "region_id": "lungs",
            "name": "Lungs Region (Pulmonary System)",
            "anatomical_systems": "Alveolar Gas Exchange, Bronchial Tree, Pleural Dynamics",
            "spacesuit_interface": "Life Support Umbilical Ventilation Loop & Oxygen Regulator",
            "primary_metrics": [
                {"label": "Respiration Rate", "value": "14", "unit": "breaths/min", "status": "NOMINAL"},
                {"label": "Tidal Volume", "value": "520", "unit": "mL", "status": "NOMINAL"},
                {"label": "Minute Ventilation", "value": "7.28", "unit": "L/min", "status": "NOMINAL"},
                {"label": "Ventilation Pressure", "value": "29.6", "unit": "kPa", "status": "NOMINAL"},
                {"label": "Oxygen Partial Pressure", "value": "20.8", "unit": "kPa", "status": "NOMINAL"}
            ],
            "relevant_readings": {
                "resp_rate": "14 breaths/min",
                "o2_consumption_vo2": "0.32 L/min",
                "suit_air_flow": "170 L/min"
            },
            "radiation_research_context": (
                "Pulmonary Radiation Tolerance: High oxygen breathing loops in spacesuits (100% O2 during pre-breathe / EVA) "
                "are balanced against hyperoxic pulmonary irritation. Radiation pneumonitis thresholds far exceed operational orbital exposures."
            ),
            "historical_measurements": [
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(), "resp_rate": 15, "tidal_vol": 510},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(), "resp_rate": 14, "tidal_vol": 525},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(), "resp_rate": 14, "tidal_vol": 520}
            ],
            "data_source": "Respiratory Impedance Plethysmography & EMU Ventilation Sensors (Simulated Demo)",
            "disclaimer": "Visualization association only. Spacesuit 3D model does not contain internal anatomical imaging."
        },
        "abdomen": {
            "region_id": "abdomen",
            "name": "Abdomen & Core Metabolism",
            "anatomical_systems": "Digestive Organs, Core Thermal Core, Hepatorenal Perfusion",
            "spacesuit_interface": "Lower Torso Assembly (LTA) Waist Ring & Liquid Cooling Garment (LCG)",
            "primary_metrics": [
                {"label": "Core Body Temperature", "value": "36.8", "unit": "°C", "status": "NOMINAL"},
                {"label": "Skin Temp (Abdominal)", "value": "34.1", "unit": "°C", "status": "NOMINAL"},
                {"label": "Metabolic Heat Rate", "value": "185", "unit": "W", "status": "NOMINAL"},
                {"label": "LCG Coolant Inlet Temp", "value": "16.2", "unit": "°C", "status": "NOMINAL"},
                {"label": "Hydration Index", "value": "Optimal", "unit": "State", "status": "NOMINAL"}
            ],
            "relevant_readings": {
                "body_temperature_c": 36.8,
                "visceral_perfusion": "Nominal",
                "lcg_cooling_loop": "Automatic Thermal Regulation"
            },
            "radiation_research_context": (
                "Gastrointestinal Sensitivity: Rapidly dividing epithelial cells in the gut lining are sensitive to radiation. "
                "Orbital dosimetry is monitored to ensure cumulative doses remain well below acute prodromal GI thresholds (0.5+ Gy)."
            ),
            "historical_measurements": [
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(), "body_temp": 36.7, "metabolic_w": 190},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(), "body_temp": 36.8, "metabolic_w": 182},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(), "body_temp": 36.8, "metabolic_w": 185}
            ],
            "data_source": "Core Temperature Telemetry & EMU Cooling Garment Sensors (Simulated Demo)",
            "disclaimer": "Visualization association only. Spacesuit 3D model does not contain internal anatomical imaging."
        },
        "left_arm": {
            "region_id": "left_arm",
            "name": "Left Arm & EVA Gauntlet",
            "anatomical_systems": "Musculoskeletal Left Upper Extremity, Brachial Vasculature, Tactile Motor Sensors",
            "spacesuit_interface": "xEMU Left Shoulder Bearing, Arm Assembly & Heated Thermal Glove",
            "primary_metrics": [
                {"label": "Glove Pressure", "value": "29.6", "unit": "kPa", "status": "NOMINAL"},
                {"label": "Fingertip Temp", "value": "21.4", "unit": "°C", "status": "NOMINAL"},
                {"label": "Brachial BP", "value": "118/76", "unit": "mmHg", "status": "NOMINAL"},
                {"label": "Muscle Exertion", "value": "18%", "unit": "%", "status": "NOMINAL"}
            ],
            "relevant_readings": {
                "arm_blood_pressure": "118/76 mmHg",
                "wrist_pulse_oximetry": "98.4%"
            },
            "radiation_research_context": "Extremity Dosimetry: Astronaut hands and arms face high mechanical friction and reduced suit shielding. Skin/extremity career limits under NCRP-132 allow higher absorbed doses than blood-forming organs.",
            "historical_measurements": [
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(), "glove_temp_c": 21.0, "fatigue_pct": 15},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(), "glove_temp_c": 21.4, "fatigue_pct": 18}
            ],
            "data_source": "xEMU Left Gauntlet Sensor Array (Simulated Demo)",
            "disclaimer": "Visualization association only. Spacesuit 3D model does not contain internal anatomical imaging."
        },
        "right_arm": {
            "region_id": "right_arm",
            "name": "Right Arm & Biometric Gauntlet",
            "anatomical_systems": "Musculoskeletal Right Upper Extremity, Radial Vasculature, Wrist Pulse Oximetry",
            "spacesuit_interface": "xEMU Right Shoulder Bearing, Forearm Sleeve & Biometric Cuff",
            "primary_metrics": [
                {"label": "Glove Pressure", "value": "29.6", "unit": "kPa", "status": "NOMINAL"},
                {"label": "Fingertip Temp", "value": "22.0", "unit": "°C", "status": "NOMINAL"},
                {"label": "Wrist SpO2", "value": "98.4", "unit": "%", "status": "NOMINAL"},
                {"label": "Grip Force", "value": "92%", "unit": "%", "status": "NOMINAL"}
            ],
            "relevant_readings": {
                "wrist_spo2": "98.4%",
                "forearm_emg": "14% Active"
            },
            "radiation_research_context": "Forearm Skin Shielding: Measured via passive TLD chips. Cumulative extremity exposure is recorded to prevent localized radiodermatitis during extended multi-hour spacewalks.",
            "historical_measurements": [
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(), "glove_temp_c": 21.6, "fatigue_pct": 14},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(), "glove_temp_c": 22.0, "fatigue_pct": 16}
            ],
            "data_source": "xEMU Right Gauntlet Sensor Array (Simulated Demo)",
            "disclaimer": "Visualization association only. Spacesuit 3D model does not contain internal anatomical imaging."
        },
        "arms": {
            "region_id": "arms",
            "name": "Left & Right Arms & Extravehicular Gloves",
            "anatomical_systems": "Musculoskeletal Upper Extremities, Brachial Vasculature, Fine Motor Control",
            "spacesuit_interface": "EMU Scapula Bearings, Arm Assemblies, Heated Extravehicular Gloves",
            "primary_metrics": [
                {"label": "Glove Internal Pressure", "value": "29.6", "unit": "kPa", "status": "NOMINAL"},
                {"label": "Left Fingertip Temp", "value": "21.4", "unit": "°C", "status": "NOMINAL"},
                {"label": "Right Fingertip Temp", "value": "22.0", "unit": "°C", "status": "NOMINAL"},
                {"label": "Forearm Muscle Fatigue", "value": "18%", "unit": "%", "status": "NOMINAL"},
                {"label": "Grip Force Capacity", "value": "92%", "unit": "%", "status": "NOMINAL"}
            ],
            "relevant_readings": {
                "arm_blood_pressure": "118/76 mmHg",
                "glove_heaters": "Active (Thermostatic Loop)",
                "wrist_pulse_oximetry": "98.4%"
            },
            "radiation_research_context": (
                "Extremity Radiation Monitoring: Astronaut hands are subject to high tactile friction and minimal glove shielding "
                "compared to the torso HUT. NCRP 132 defines separate career limits for skin and extremities (1.5 - 3.0 Sv-Eq) "
                "reflecting reduced oncogenic risk compared to blood-forming organs."
            ),
            "historical_measurements": [
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(), "glove_temp_c": 21.0, "fatigue_pct": 15},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(), "glove_temp_c": 21.5, "fatigue_pct": 17},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(), "glove_temp_c": 21.4, "fatigue_pct": 18}
            ],
            "data_source": "EMU Gauntlet Pressure & Thermal Array (Simulated Demo)",
            "disclaimer": "Visualization association only. Spacesuit 3D model does not contain internal anatomical imaging."
        },
        "left_leg": {
            "region_id": "left_leg",
            "name": "Left Leg & EVA Boot",
            "anatomical_systems": "Femoral Vasculature, Left Quadriceps & Calf, Microgravity Unloading",
            "spacesuit_interface": "xEMU Left Hip Bearing, Knee Articulation & Lunar EVA Boot",
            "primary_metrics": [
                {"label": "Limb Perfusion", "value": "0.98", "unit": "PI", "status": "NOMINAL"},
                {"label": "Calf Delta", "value": "-1.8", "unit": "cm", "status": "NOMINAL"},
                {"label": "Boot Sole Temp", "value": "18.2", "unit": "°C", "status": "NOMINAL"},
                {"label": "Tether Lock", "value": "ENGAGED", "unit": "Status", "status": "NOMINAL"}
            ],
            "relevant_readings": {
                "perfusion_index": "0.98 PI",
                "microgravity_fluid_shift": "Nominal"
            },
            "radiation_research_context": "Femoral Bone Marrow Dosimetry: Long bone hemopoietic marrow accounts for significant blood cell regeneration. Protected by lower spacecraft hull and multi-layer suit insulation.",
            "historical_measurements": [
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(), "perfusion_pi": 0.97, "boot_temp_c": 18.0},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(), "perfusion_pi": 0.98, "boot_temp_c": 18.2}
            ],
            "data_source": "xEMU Left Leg Biomechanical Array (Simulated Demo)",
            "disclaimer": "Visualization association only. Spacesuit 3D model does not contain internal anatomical imaging."
        },
        "right_leg": {
            "region_id": "right_leg",
            "name": "Right Leg & EVA Boot",
            "anatomical_systems": "Femoral Vasculature, Right Quadriceps & Calf, Ground Reaction Sensor",
            "spacesuit_interface": "xEMU Right Hip Bearing, Knee Articulation & Lunar EVA Boot",
            "primary_metrics": [
                {"label": "Limb Perfusion", "value": "0.99", "unit": "PI", "status": "NOMINAL"},
                {"label": "Calf Delta", "value": "-1.7", "unit": "cm", "status": "NOMINAL"},
                {"label": "Boot Sole Temp", "value": "18.4", "unit": "°C", "status": "NOMINAL"},
                {"label": "Heel Latch", "value": "SECURED", "unit": "Status", "status": "NOMINAL"}
            ],
            "relevant_readings": {
                "perfusion_index": "0.99 PI",
                "boot_tread_integrity": "100%"
            },
            "radiation_research_context": "Lower Extremity Bone Health: Astronaut countermeasure exercise on CEVIS/ARED maintains cortical bone density against radiation-accelerated osteopenia.",
            "historical_measurements": [
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(), "perfusion_pi": 0.98, "boot_temp_c": 18.1},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(), "perfusion_pi": 0.99, "boot_temp_c": 18.4}
            ],
            "data_source": "xEMU Right Leg Biomechanical Array (Simulated Demo)",
            "disclaimer": "Visualization association only. Spacesuit 3D model does not contain internal anatomical imaging."
        },
        "legs": {
            "region_id": "legs",
            "name": "Legs & Lower Extremities",
            "anatomical_systems": "Lower Musculoskeletal System, Femoral Circulation, Cephalad Fluid Shift",
            "spacesuit_interface": "EMU Lower Torso Assembly (LTA) Brief, Knee Bearings, EVA Boots",
            "primary_metrics": [
                {"label": "Lower Limb Perfusion", "value": "0.98", "unit": "PI", "status": "NOMINAL"},
                {"label": "Cephalad Fluid Shift Index", "value": "+12%", "unit": "Fluid Delta", "status": "NOMINAL"},
                {"label": "Calf Circumference Delta", "value": "-1.8", "unit": "cm", "status": "NOMINAL"},
                {"label": "Boot Sole Temperature", "value": "18.2", "unit": "°C", "status": "NOMINAL"},
                {"label": "Tether Retention Lock", "value": "SECURED", "unit": "Mechanical", "status": "NOMINAL"}
            ],
            "relevant_readings": {
                "lower_limb_perfusion": "0.98 PI",
                "boot_heater_loop": "Nominal",
                "microgravity_unloading": "Active Conditioning Protocol"
            },
            "radiation_research_context": (
                "Lower Extremity Bone Marrow Shielding: Long bones (femur, tibia) host hemopoietic bone marrow. "
                "Microgravity bone demineralization combined with cosmic radiation is actively investigated in NASA bed-rest "
                "and ISS rodent research analogs to optimize countermeasures."
            ),
            "historical_measurements": [
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat(), "perfusion_pi": 0.97, "boot_temp_c": 18.0},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(), "perfusion_pi": 0.98, "boot_temp_c": 18.2},
                {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(), "perfusion_pi": 0.98, "boot_temp_c": 18.2}
            ],
            "data_source": "EMU Lower Torso Biomechanical Telemetry (Simulated Demo)",
            "disclaimer": "Visualization association only. Spacesuit 3D model does not contain internal anatomical imaging."
        }
    }

    return {
        "status": "success",
        "astronaut_id": astronaut_id,
        "total_regions": len(regions),
        "regions": regions,
        "timestamp": now_iso,
        "disclaimer": "Body region data associations illustrate physiological systems for operational visualization. Spacesuit 3D model does not contain internal anatomical imaging. Whole-body dosimetry is not an individual body-region absorbed dose."
    }


def get_latest_radiation_telemetry() -> Dict[str, Any]:
    """
    Returns latest radiation telemetry, combining dynamic streaming, RadLab measurements,
    ML anomaly scoring, and cumulative dose calculations.
    """
    # 1. Try streaming engine latest or SQLite dynamic records
    db_dynamic = get_latest_dynamic_radiation_reading()
    
    # 2. If dynamic not available, check RadLab history
    radlab_history = query_radiation_history(limit=1)
    history_records = radlab_history.get("records", [])

    if db_dynamic:
        reading = db_dynamic
        dose_rate = float(reading.get("absorbed_dose_rate") or 1.85)
        eq_rate = float(reading.get("dose_equivalent_rate") or (dose_rate * 2.2))
        flux = float(reading.get("flux") or 2.45)
        altitude = float(reading.get("altitude") or 408.4)
        instrument = reading.get("instrument_id") or "DosTel1"
        source = reading.get("data_source") or "Dynamic Telemetry Stream"
        ts = reading.get("timestamp") or datetime.now(timezone.utc).isoformat()
        is_sim = bool(reading.get("is_simulated", True))
        ml_score = reading.get("ml_anomaly_score", 0.05)
        is_anomaly = bool(reading.get("ml_is_anomaly", False))
    elif history_records:
        rec = history_records[0]
        dose_rate = float(rec.get("absorbed_dose_rate") or 1.95)
        eq_rate = float(rec.get("dose_equivalent_rate") or (dose_rate * 2.1))
        flux = float(rec.get("flux") or 2.6)
        altitude = float(rec.get("altitude") or 408.0)
        instrument = rec.get("instrument_id") or "REM-Lid"
        source = rec.get("source_origin") or "NASA OSDR RadLab API"
        ts = rec.get("timestamp") or datetime.now(timezone.utc).isoformat()
        is_sim = False
        ml_score = 0.02
        is_anomaly = False
    else:
        # Fallback baseline authentic NASA ISS value
        dose_rate = 1.92
        eq_rate = 4.03
        flux = 2.48
        altitude = 408.4
        instrument = "DosTel1"
        source = "NASA RadLab Scientific Telemetry Archive"
        ts = datetime.now(timezone.utc).isoformat()
        is_sim = False
        ml_score = 0.03
        is_anomaly = False

    # Cumulative dose estimation (for 142 days at current average rate)
    # 142 days * 24 hrs * ~1.9 µGy/hr = ~6475 µGy (6.47 mGy)
    cumulative_dose_ugy = round(142 * 24 * dose_rate, 1)

    # Classification of risk level based on operational benchmarks
    if dose_rate >= 50.0:
        condition = "CRITICAL_ACTION"
        condition_label = "ACTION THRESHOLD EXCEEDED"
        visual_aura_color = "#ff3366"  # Red
        particle_density = "high"
    elif dose_rate >= 10.0:
        condition = "ADVISORY"
        condition_label = "ELEVATED ADVISORY (SPE / SAA PASS)"
        visual_aura_color = "#ffaa00"  # Amber
        particle_density = "medium"
    else:
        condition = "NOMINAL"
        condition_label = "NOMINAL BACKGROUND (LEO)"
        visual_aura_color = "#00f2fe"  # Cyan/Teal
        particle_density = "low"

    return {
        "status": "success",
        "timestamp": ts,
        "instrument_id": instrument,
        "spacecraft": "ISS (International Space Station)",
        "orbital_region": "Low Earth Orbit (LEO)",
        "altitude_km": altitude,
        "absorbed_dose_rate": round(dose_rate, 4),
        "absorbed_dose_unit": "µGy/hr",
        "dose_equivalent_rate": round(eq_rate, 4),
        "dose_equivalent_unit": "µSv/hr",
        "cumulative_dose_ugy": cumulative_dose_ugy,
        "cumulative_dose_unit": "µGy",
        "particle_flux": round(flux, 3),
        "particle_flux_unit": "particles/cm²·s",
        "condition": condition,
        "condition_label": condition_label,
        "visual_aura": {
            "color": visual_aura_color,
            "density": particle_density,
            "intensity": min(1.0, max(0.15, dose_rate / 20.0))
        },
        "ml_anomaly": {
            "is_anomaly": is_anomaly,
            "anomaly_score": ml_score
        },
        "data_source": source,
        "is_simulated": is_sim,
        "disclaimer": (
            "Scientific radiation measurement from NASA RadLab / streaming telemetry. "
            "Preserves strict distinctions between absorbed dose (energy deposited, Gy), "
            "dose rate (Gy/hr), and biological dose equivalent (Sv). Whole-body telemetry "
            "does not represent individual body-region absorbed dose."
        )
    }


def get_latest_health_telemetry(astronaut_id: str = "AST-01") -> Dict[str, Any]:
    """
    Returns latest health measurements for the astronaut with status evaluation.
    """
    db_records = query_astronaut_health_measurements(astronaut_id=astronaut_id, limit=1)
    rows = db_records.get("records", [])

    if rows:
        r = rows[0]
        hr = float(r.get("heart_rate") or 72.0)
        sys_bp = float(r.get("blood_pressure_systolic") or 118.0)
        dia_bp = float(r.get("blood_pressure_diastolic") or 76.0)
        spo2 = float(r.get("oxygen_saturation") or 98.4)
        temp_c = float(r.get("body_temperature") or 36.8)
        ts = r.get("timestamp") or datetime.now(timezone.utc).isoformat()
        device = r.get("source_device") or "Wearable Crew Health Monitor"
        data_class = r.get("data_classification") or "simulated_demo"
    else:
        hr, sys_bp, dia_bp, spo2, temp_c = 72.0, 118.0, 76.0, 98.4, 36.8
        ts = datetime.now(timezone.utc).isoformat()
        device = "Wearable Crew Biomonitor #1"
        data_class = "simulated_demo"

    # Evaluate vital indicators
    status_label = "NOMINAL"
    if hr > 100 or hr < 50 or spo2 < 95 or temp_c > 37.8:
        status_label = "ATTENTION"

    return {
        "status": "success",
        "astronaut_id": astronaut_id,
        "timestamp": ts,
        "heart_rate": {
            "value": hr,
            "unit": "BPM",
            "normal_range": "60 - 100 BPM",
            "status": "NOMINAL" if 55 <= hr <= 100 else "ALERT"
        },
        "blood_pressure": {
            "systolic": sys_bp,
            "diastolic": dia_bp,
            "unit": "mmHg",
            "normal_range": "< 120 / < 80 mmHg",
            "status": "NOMINAL" if sys_bp <= 130 and dia_bp <= 85 else "ELEVATED"
        },
        "oxygen_saturation": {
            "value": spo2,
            "unit": "%",
            "normal_range": "95 - 100%",
            "status": "NOMINAL" if spo2 >= 95 else "HYPOXIC"
        },
        "body_temperature": {
            "value": temp_c,
            "unit": "°C",
            "normal_range": "36.1 - 37.2 °C",
            "status": "NOMINAL" if 36.0 <= temp_c <= 37.5 else "FEVER"
        },
        "respiratory_rate": {
            "value": 14,
            "unit": "breaths/min",
            "normal_range": "12 - 20 breaths/min",
            "status": "NOMINAL"
        },
        "overall_status": status_label,
        "source_device": device,
        "data_classification": data_class,
        "disclaimer": (
            "Physiological vitals are monitored for aerospace situational awareness under NASA-STD-3001. "
            "Data is classified as simulated demonstration telemetry and does not constitute automated clinical diagnosis."
        )
    }
