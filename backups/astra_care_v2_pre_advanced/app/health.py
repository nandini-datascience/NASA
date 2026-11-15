"""
health.py - Astronaut Health Monitoring Module for ASTRA CARE

Handles:
1. Vitals telemetry management:
   - Heart rate (BPM)
   - Blood pressure (mmHg) [Systolic / Diastolic]
   - Oxygen saturation (SpO2 %)
   - Body temperature (°C)
2. Rigorous physiological data validation:
   - Format, units, and physiological range verification
   - Missing and corrupted value detection
   - Data classification ('simulated_demo', 'historical_study', 'sensor_telemetry')
3. Aerospace health alert engine:
   - Configurable rules referencing validated benchmarks:
     * NASA-STD-3001 (NASA Space Flight Human-System Standard, Crew Health)
     * AHA / ACC (American Heart Association Blood Pressure & Cardiovascular Guidelines)
     * WHO (World Health Organization Clinical Oximetry & Thermoregulation Standards)
   - Detailed explanations of why a metric warrants operational attention
   - Strict non-diagnostic disclaimer (does not diagnose diseases)
"""

from datetime import datetime, timezone
import hashlib
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("astra_care.health")

# Non-diagnostic medical disclaimer
HEALTH_DISCLAIMER_TEXT = (
    "ASTRA CARE alerts and vital telemetry reflect aerospace operational benchmarks "
    "(NASA-STD-3001 Vol 1 / AHA / WHO). This system monitors physiological telemetry and "
    "does NOT diagnose medical diseases or clinical conditions. "
    "All telemetry requires clinical review by a certified Flight Surgeon."
)

# Standard Valid Physiological Boundaries & Measurement Units
HEALTH_METRIC_METADATA: Dict[str, Dict[str, Any]] = {
    "heart_rate": {
        "unit": "BPM (beats per minute)",
        "description": "Resting cardiac pulse frequency.",
        "valid_range": [30.0, 240.0],
        "nominal_range": [60.0, 100.0],
        "guideline_reference": "NASA-STD-3001 Vol 1 / American Heart Association (AHA)"
    },
    "blood_pressure_systolic": {
        "unit": "mmHg (millimeters of mercury)",
        "description": "Peak arterial pressure during cardiac contraction (systole).",
        "valid_range": [50.0, 260.0],
        "nominal_range": [90.0, 119.0],
        "guideline_reference": "AHA / ACC 2017 Blood Pressure Clinical Guidelines"
    },
    "blood_pressure_diastolic": {
        "unit": "mmHg (millimeters of mercury)",
        "description": "Minimum arterial pressure during cardiac relaxation (diastole).",
        "valid_range": [30.0, 160.0],
        "nominal_range": [60.0, 79.0],
        "guideline_reference": "AHA / ACC 2017 Blood Pressure Clinical Guidelines"
    },
    "oxygen_saturation": {
        "unit": "% (SpO2 percentage)",
        "description": "Fraction of oxygen-saturated hemoglobin relative to total hemoglobin.",
        "valid_range": [50.0, 100.0],
        "nominal_range": [95.0, 100.0],
        "guideline_reference": "WHO Pulse Oximetry Guidelines / NASA Pressurized Cabin Spec"
    },
    "body_temperature": {
        "unit": "°C (degrees Celsius)",
        "description": "Core body temperature.",
        "valid_range": [30.0, 44.0],
        "nominal_range": [36.1, 37.2],
        "guideline_reference": "NASA-STD-3001 Thermoregulation Standards"
    }
}

# Default Validated Thresholds
DEFAULT_HEALTH_THRESHOLDS = {
    "heart_rate": {
        "bradycardia_critical": 40.0,
        "bradycardia_warning": 50.0,
        "tachycardia_warning": 100.0,
        "tachycardia_critical": 130.0
    },
    "blood_pressure": {
        "systolic_hypotension": 90.0,
        "diastolic_hypotension": 60.0,
        "systolic_elevated": 120.0,
        "systolic_stage1": 130.0,
        "diastolic_stage1": 80.0,
        "systolic_stage2": 140.0,
        "diastolic_stage2": 90.0,
        "systolic_crisis": 180.0,
        "diastolic_crisis": 120.0
    },
    "oxygen_saturation": {
        "hypoxia_mild": 94.0,       # SpO2 <= 94% warning
        "hypoxia_severe": 90.0      # SpO2 < 90% critical
    },
    "body_temperature": {
        "hypothermia_critical": 35.0,
        "hypothermia_warning": 35.5,
        "fever_warning": 38.0,
        "hyperthermia_critical": 39.0
    }
}

VALID_DATA_CLASSIFICATIONS = {"simulated_demo", "historical_study", "sensor_telemetry"}


def parse_iso_timestamp(ts_str: Any) -> Optional[datetime]:
    """Parses an ISO timestamp into a timezone-aware UTC datetime."""
    if not ts_str or not isinstance(ts_str, str):
        return None
    try:
        clean = ts_str.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def generate_health_alert_id(alert_type: str, timestamp: str, astronaut_id: str) -> str:
    """Generates a deterministic unique ID for health alerts to avoid duplicates."""
    seed = f"HEALTH_{alert_type}_{timestamp}_{astronaut_id}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12].upper()
    return f"ALT-MED-{digest}"


def validate_health_measurement(
    data: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """
    Validates an incoming astronaut health measurement:
    - Verifies presence of astronaut_id and timestamp.
    - Validates data_classification ('simulated_demo', 'historical_study', 'sensor_telemetry').
    - Confirms values fall within physiologically valid limits.
    - Checks that systolic blood pressure exceeds diastolic pressure.
    - Preserves measurement units.

    Returns:
        (validated_record_or_None, data_quality_alerts, validation_error_messages)
    """
    errors: List[str] = []
    data_quality_alerts: List[Dict[str, Any]] = []

    # 1. Astronaut Identifier
    astronaut_id = data.get("astronaut_id")
    if not astronaut_id or not str(astronaut_id).strip():
        errors.append("Field 'astronaut_id' is required.")
        return None, data_quality_alerts, errors
    astronaut_id = str(astronaut_id).strip()

    # 2. Timestamp Validation
    raw_ts = data.get("timestamp")
    dt = parse_iso_timestamp(raw_ts)
    if not dt:
        errors.append(f"Invalid or missing ISO 8601 timestamp: '{raw_ts}'. Format should be 'YYYY-MM-DDTHH:MM:SSZ'.")
        data_quality_alerts.append({
            "alert_id": generate_health_alert_id("TIMESTAMP_PARSE_ERROR", str(raw_ts), astronaut_id),
            "astronaut_id": astronaut_id,
            "timestamp": str(raw_ts or datetime.now(timezone.utc).isoformat()),
            "category": "DATA_QUALITY_WARNING",
            "severity": "WARNING",
            "alert_type": "TIMESTAMP_PARSE_ERROR",
            "metric_name": "timestamp",
            "metric_value": str(raw_ts),
            "threshold_applied": "ISO 8601 UTC format",
            "unit": "string",
            "description": f"Health telemetry for {astronaut_id} has invalid timestamp: '{raw_ts}'.",
            "explanation": "Timestamp cannot be ordered chronologically without valid UTC ISO 8601 format.",
            "recommendation": "Synchronize telemetry device clock with spacecraft master UTC time.",
            "guideline_reference": "CCSDS Space Telemetry Time Code Standard"
        })
        return None, data_quality_alerts, errors

    clean_timestamp = dt.isoformat()

    # 3. Data Classification Validation
    raw_classification = data.get("data_classification", "simulated_demo")
    if raw_classification not in VALID_DATA_CLASSIFICATIONS:
        errors.append(
            f"Invalid data_classification '{raw_classification}'. "
            f"Must be one of: {sorted(list(VALID_DATA_CLASSIFICATIONS))}."
        )
        return None, data_quality_alerts, errors

    # 4. Numeric Physiological Validations
    validated_fields: Dict[str, Optional[float]] = {}
    has_at_least_one_metric = False

    # (a) Heart Rate (BPM)
    hr_val = data.get("heart_rate")
    if hr_val is not None:
        try:
            val = float(hr_val)
            if math.isnan(val) or math.isinf(val):
                validated_fields["heart_rate"] = None
            elif val < HEALTH_METRIC_METADATA["heart_rate"]["valid_range"][0] or \
                 val > HEALTH_METRIC_METADATA["heart_rate"]["valid_range"][1]:
                errors.append(
                    f"Heart rate {val} BPM is outside physiologically viable range (30-240 BPM)."
                )
                data_quality_alerts.append({
                    "alert_id": generate_health_alert_id("INVALID_HEART_RATE", clean_timestamp, astronaut_id),
                    "astronaut_id": astronaut_id,
                    "timestamp": clean_timestamp,
                    "category": "DATA_QUALITY_WARNING",
                    "severity": "CRITICAL",
                    "alert_type": "INVALID_HEALTH_VALUE",
                    "metric_name": "heart_rate",
                    "metric_value": str(val),
                    "threshold_applied": "30-240 BPM",
                    "unit": "BPM",
                    "description": f"Physiologically unviable heart rate ({val} BPM) detected on {astronaut_id}.",
                    "explanation": "Value violates human physiological survival limits; indicates sensor detachment, motion artifact, or telemetry corruption.",
                    "recommendation": "Inspect electrocardiogram / pulse oximeter electrode placement and signal-to-noise ratio.",
                    "guideline_reference": "AHA Diagnostic Electrocardiography Standards"
                })
            else:
                validated_fields["heart_rate"] = round(val, 1)
                has_at_least_one_metric = True
        except (ValueError, TypeError):
            errors.append(f"Heart rate '{hr_val}' must be a numeric value.")
    else:
        validated_fields["heart_rate"] = None

    # (b) Blood Pressure (Systolic & Diastolic)
    sys_val = data.get("blood_pressure_systolic")
    dia_val = data.get("blood_pressure_diastolic")

    clean_sys: Optional[float] = None
    clean_dia: Optional[float] = None

    if sys_val is not None:
        try:
            val = float(sys_val)
            if not math.isnan(val) and not math.isinf(val):
                if val < HEALTH_METRIC_METADATA["blood_pressure_systolic"]["valid_range"][0] or \
                   val > HEALTH_METRIC_METADATA["blood_pressure_systolic"]["valid_range"][1]:
                    errors.append(f"Systolic blood pressure {val} mmHg is outside viable bounds (50-260 mmHg).")
                else:
                    clean_sys = round(val, 1)
        except (ValueError, TypeError):
            errors.append(f"Systolic pressure '{sys_val}' must be numeric.")

    if dia_val is not None:
        try:
            val = float(dia_val)
            if not math.isnan(val) and not math.isinf(val):
                if val < HEALTH_METRIC_METADATA["blood_pressure_diastolic"]["valid_range"][0] or \
                   val > HEALTH_METRIC_METADATA["blood_pressure_diastolic"]["valid_range"][1]:
                    errors.append(f"Diastolic blood pressure {val} mmHg is outside viable bounds (30-160 mmHg).")
                else:
                    clean_dia = round(val, 1)
        except (ValueError, TypeError):
            errors.append(f"Diastolic pressure '{dia_val}' must be numeric.")

    # Check systolic > diastolic relationship
    if clean_sys is not None and clean_dia is not None:
        if clean_sys <= clean_dia:
            errors.append(
                f"Systolic pressure ({clean_sys} mmHg) must be strictly greater than diastolic pressure ({clean_dia} mmHg)."
            )
            data_quality_alerts.append({
                "alert_id": generate_health_alert_id("INVALID_BP_INVERSION", clean_timestamp, astronaut_id),
                "astronaut_id": astronaut_id,
                "timestamp": clean_timestamp,
                "category": "DATA_QUALITY_WARNING",
                "severity": "CRITICAL",
                "alert_type": "INVALID_HEALTH_VALUE",
                "metric_name": "blood_pressure",
                "metric_value": f"{clean_sys}/{clean_dia}",
                "threshold_applied": "Systolic > Diastolic",
                "unit": "mmHg",
                "description": f"Physiologically invalid inverted blood pressure ({clean_sys}/{clean_dia} mmHg).",
                "explanation": "Systolic pressure must exceed diastolic pressure during normal pulsatile arterial flow.",
                "recommendation": "Recalibrate arterial pressure cuff and repeat sphygmomanometer reading.",
                "guideline_reference": "AHA Blood Pressure Measurement Standards"
            })
        else:
            has_at_least_one_metric = True

    validated_fields["blood_pressure_systolic"] = clean_sys
    validated_fields["blood_pressure_diastolic"] = clean_dia

    # (c) Oxygen Saturation (SpO2 %)
    spo2_val = data.get("oxygen_saturation")
    if spo2_val is not None:
        try:
            val = float(spo2_val)
            if math.isnan(val) or math.isinf(val):
                validated_fields["oxygen_saturation"] = None
            elif val < HEALTH_METRIC_METADATA["oxygen_saturation"]["valid_range"][0] or \
                 val > HEALTH_METRIC_METADATA["oxygen_saturation"]["valid_range"][1]:
                errors.append(f"Oxygen saturation {val}% is outside viable bounds (50%-100%).")
                data_quality_alerts.append({
                    "alert_id": generate_health_alert_id("INVALID_SPO2_VALUE", clean_timestamp, astronaut_id),
                    "astronaut_id": astronaut_id,
                    "timestamp": clean_timestamp,
                    "category": "DATA_QUALITY_WARNING",
                    "severity": "CRITICAL",
                    "alert_type": "INVALID_HEALTH_VALUE",
                    "metric_name": "oxygen_saturation",
                    "metric_value": str(val),
                    "threshold_applied": "50.0 - 100.0%",
                    "unit": "%",
                    "description": f"Oxygen saturation reading ({val}%) is physiologically impossible or unviable.",
                    "explanation": "SpO2 values cannot exceed 100% or fall below 50% without sensor fault.",
                    "recommendation": "Check pulse oximeter probe alignment and peripheral perfusion.",
                    "guideline_reference": "WHO Pulse Oximetry Technical Standard"
                })
            else:
                validated_fields["oxygen_saturation"] = round(val, 1)
                has_at_least_one_metric = True
        except (ValueError, TypeError):
            errors.append(f"Oxygen saturation '{spo2_val}' must be numeric.")
    else:
        validated_fields["oxygen_saturation"] = None

    # (d) Body Temperature (°C)
    temp_val = data.get("body_temperature")
    if temp_val is not None:
        try:
            val = float(temp_val)
            if math.isnan(val) or math.isinf(val):
                validated_fields["body_temperature"] = None
            elif val < HEALTH_METRIC_METADATA["body_temperature"]["valid_range"][0] or \
                 val > HEALTH_METRIC_METADATA["body_temperature"]["valid_range"][1]:
                errors.append(f"Body temperature {val}°C is outside human survival bounds (30.0°C-44.0°C).")
                data_quality_alerts.append({
                    "alert_id": generate_health_alert_id("INVALID_TEMP_VALUE", clean_timestamp, astronaut_id),
                    "astronaut_id": astronaut_id,
                    "timestamp": clean_timestamp,
                    "category": "DATA_QUALITY_WARNING",
                    "severity": "CRITICAL",
                    "alert_type": "INVALID_HEALTH_VALUE",
                    "metric_name": "body_temperature",
                    "metric_value": str(val),
                    "threshold_applied": "30.0 - 44.0°C",
                    "unit": "°C",
                    "description": f"Body temperature {val}°C is outside human physiological survival bounds.",
                    "explanation": "Temperature sensor is detached, uncalibrated, or corrupted.",
                    "recommendation": "Inspect tympanic or core thermal sensor probe.",
                    "guideline_reference": "NASA Space Flight Clinical Thermometry Guidelines"
                })
            else:
                validated_fields["body_temperature"] = round(val, 2)
                has_at_least_one_metric = True
        except (ValueError, TypeError):
            errors.append(f"Body temperature '{temp_val}' must be numeric.")
    else:
        validated_fields["body_temperature"] = None

    if not has_at_least_one_metric and not errors:
        errors.append("At least one valid health measurement (heart rate, blood pressure, SpO2, or temperature) must be provided.")

    if errors:
        return None, data_quality_alerts, errors

    # Generate unique record ID
    rec_hash = hashlib.sha256(f"{astronaut_id}_{clean_timestamp}_{validated_fields}".encode()).hexdigest()[:12].upper()
    record_id = f"HLT-{astronaut_id}-{rec_hash}"

    validated_record = {
        "record_id": record_id,
        "astronaut_id": astronaut_id,
        "timestamp": clean_timestamp,
        "heart_rate": validated_fields["heart_rate"],
        "heart_rate_unit": "BPM",
        "blood_pressure_systolic": validated_fields["blood_pressure_systolic"],
        "blood_pressure_diastolic": validated_fields["blood_pressure_diastolic"],
        "blood_pressure_unit": "mmHg",
        "oxygen_saturation": validated_fields["oxygen_saturation"],
        "oxygen_saturation_unit": "%",
        "body_temperature": validated_fields["body_temperature"],
        "body_temperature_unit": "°C",
        "source_device": str(data.get("source_device") or "Wearable Crew Health Monitor"),
        "data_classification": raw_classification,
        "notes": str(data.get("notes") or "")
    }

    return validated_record, data_quality_alerts, []


def evaluate_astronaut_health_alerts(
    record: Dict[str, Any],
    custom_thresholds: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Evaluates health alert rules against validated aerospace and medical benchmarks:
    - NASA-STD-3001 Vol 1 (Crew Health Standards)
    - AHA / ACC (American Heart Association Blood Pressure Guidelines)
    - WHO Pulse Oximetry & Clinical Vitals Standards

    Strictly explains why an alert was triggered without claiming to diagnose diseases.
    """
    thresholds = DEFAULT_HEALTH_THRESHOLDS.copy()
    if custom_thresholds:
        thresholds.update(custom_thresholds)

    astronaut_id = record["astronaut_id"]
    timestamp = record["timestamp"]
    alerts: List[Dict[str, Any]] = []

    hr = record.get("heart_rate")
    sys_bp = record.get("blood_pressure_systolic")
    dia_bp = record.get("blood_pressure_diastolic")
    spo2 = record.get("oxygen_saturation")
    temp = record.get("body_temperature")

    # 1. Heart Rate Evaluation (BPM)
    if hr is not None:
        hr_cfg = thresholds["heart_rate"]
        if hr < hr_cfg["bradycardia_critical"]:
            alerts.append({
                "alert_id": generate_health_alert_id("BRADYCARDIA_CRITICAL", timestamp, astronaut_id),
                "astronaut_id": astronaut_id,
                "timestamp": timestamp,
                "category": "CRITICAL_VITALS_ALERT",
                "severity": "CRITICAL",
                "alert_type": "BRADYCARDIA_CRITICAL",
                "metric_name": "heart_rate",
                "metric_value": str(hr),
                "threshold_applied": f"< {hr_cfg['bradycardia_critical']} BPM",
                "unit": "BPM",
                "description": f"Severe bradycardia: Heart rate {hr} BPM is critically depressed.",
                "explanation": (
                    "Marked resting bradycardia in an astronaut can compromise systemic perfusion "
                    "and cerebral blood flow. In microgravity, shifts in autonomic tone can alter cardiac pacing."
                ),
                "recommendation": "Evaluate crew consciousness, recheck pulse synchronously, and notify Flight Surgeon immediately.",
                "guideline_reference": "NASA-STD-3001 Vol 1 / AHA Bradycardia Management Guidelines"
            })
        elif hr < hr_cfg["bradycardia_warning"]:
            alerts.append({
                "alert_id": generate_health_alert_id("BRADYCARDIA_WARNING", timestamp, astronaut_id),
                "astronaut_id": astronaut_id,
                "timestamp": timestamp,
                "category": "PHYSIOLOGICAL_WARNING",
                "severity": "WARNING",
                "alert_type": "BRADYCARDIA_WARNING",
                "metric_name": "heart_rate",
                "metric_value": str(hr),
                "threshold_applied": f"< {hr_cfg['bradycardia_warning']} BPM",
                "unit": "BPM",
                "description": f"Bradycardia advisory: Heart rate is {hr} BPM (below standard resting 50 BPM).",
                "explanation": (
                    "While well-conditioned astronauts often exhibit athletic bradycardia during sleep or deep rest, "
                    "unexpected daytime drops warrant monitoring for conduction delay or fatigue."
                ),
                "recommendation": "Confirm whether astronaut is asleep or resting; monitor for dizziness or orthostatic weakness.",
                "guideline_reference": "NASA Crew Health Evaluation Protocols"
            })
        elif hr >= hr_cfg["tachycardia_critical"]:
            alerts.append({
                "alert_id": generate_health_alert_id("TACHYCARDIA_CRITICAL", timestamp, astronaut_id),
                "astronaut_id": astronaut_id,
                "timestamp": timestamp,
                "category": "CRITICAL_VITALS_ALERT",
                "severity": "CRITICAL",
                "alert_type": "TACHYCARDIA_CRITICAL",
                "metric_name": "heart_rate",
                "metric_value": str(hr),
                "threshold_applied": f">= {hr_cfg['tachycardia_critical']} BPM",
                "unit": "BPM",
                "description": f"Severe resting tachycardia: Heart rate {hr} BPM exceeds critical threshold.",
                "explanation": (
                    "High resting heart rate in spaceflight may indicate acute physical deconditioning, "
                    "significant hypovolemia, elevated cabin carbon dioxide (CO2), cardiac arrhythmia, or acute stress."
                ),
                "recommendation": "Instruct crew member to cease physical activity, verify cabin atmospheric CO2 levels, and notify Flight Surgeon.",
                "guideline_reference": "NASA-STD-3001 Vol 1 / Space Medicine Clinical Operations Protocols"
            })
        elif hr >= hr_cfg["tachycardia_warning"]:
            alerts.append({
                "alert_id": generate_health_alert_id("TACHYCARDIA_WARNING", timestamp, astronaut_id),
                "astronaut_id": astronaut_id,
                "timestamp": timestamp,
                "category": "PHYSIOLOGICAL_WARNING",
                "severity": "WARNING",
                "alert_type": "TACHYCARDIA_WARNING",
                "metric_name": "heart_rate",
                "metric_value": str(hr),
                "threshold_applied": f">= {hr_cfg['tachycardia_warning']} BPM",
                "unit": "BPM",
                "description": f"Elevated resting heart rate: {hr} BPM (exceeds nominal resting limit 100 BPM).",
                "explanation": (
                    "Resting heart rate above 100 BPM indicates sympathetic nervous system activation, "
                    "mild dehydration, post-exercise recovery lag, or early orthostatic intolerance."
                ),
                "recommendation": "Check hydration status, log recent exercise, and repeat vital check after 15 minutes of rest.",
                "guideline_reference": "AHA Adult Cardiac Assessment Standards"
            })

    # 2. Blood Pressure Evaluation (mmHg)
    if sys_bp is not None and dia_bp is not None:
        bp_cfg = thresholds["blood_pressure"]
        bp_str = f"{sys_bp}/{dia_bp}"

        if sys_bp >= bp_cfg["systolic_crisis"] or dia_bp >= bp_cfg["diastolic_crisis"]:
            alerts.append({
                "alert_id": generate_health_alert_id("HYPERTENSIVE_CRISIS", timestamp, astronaut_id),
                "astronaut_id": astronaut_id,
                "timestamp": timestamp,
                "category": "CRITICAL_VITALS_ALERT",
                "severity": "CRITICAL",
                "alert_type": "HYPERTENSIVE_CRISIS",
                "metric_name": "blood_pressure",
                "metric_value": bp_str,
                "threshold_applied": f">={bp_cfg['systolic_crisis']}/{bp_cfg['diastolic_crisis']} mmHg",
                "unit": "mmHg",
                "description": f"Hypertensive urgency benchmark: Blood pressure {bp_str} mmHg is severely elevated.",
                "explanation": (
                    "Marked arterial hypertension increases vascular wall shear stress and intracranial pressure. "
                    "In spaceflight, fluid shifts towards the head (cephalad shift) exacerbate microvascular cephalic pressure."
                ),
                "recommendation": "Have astronaut rest seated/recumbent immediately, recheck pressure after 5 minutes, and alert Flight Surgeon.",
                "guideline_reference": "AHA/ACC 2017 Guidelines on High Blood Pressure in Adults"
            })
        elif sys_bp < bp_cfg["systolic_hypotension"] or dia_bp < bp_cfg["diastolic_hypotension"]:
            alerts.append({
                "alert_id": generate_health_alert_id("HYPOTENSION_WARNING", timestamp, astronaut_id),
                "astronaut_id": astronaut_id,
                "timestamp": timestamp,
                "category": "PHYSIOLOGICAL_WARNING",
                "severity": "WARNING",
                "alert_type": "HYPOTENSION_WARNING",
                "metric_name": "blood_pressure",
                "metric_value": bp_str,
                "threshold_applied": f"<{bp_cfg['systolic_hypotension']}/{bp_cfg['diastolic_hypotension']} mmHg",
                "unit": "mmHg",
                "description": f"Hypotension advisory: Blood pressure {bp_str} mmHg is below normal autoregulatory range.",
                "explanation": (
                    "Low blood pressure in microgravity or during re-adaptation can precipitate orthostatic intolerance, "
                    "lightheadedness, and risk of syncope due to reduction in circulating blood volume."
                ),
                "recommendation": "Encourage fluid/electrolyte intake (oral rehydration salt protocol) and monitor for presyncope symptoms.",
                "guideline_reference": "NASA Space Flight Orthostatic Intolerance Management Protocol"
            })
        elif sys_bp >= bp_cfg["systolic_stage2"] or dia_bp >= bp_cfg["diastolic_stage2"]:
            alerts.append({
                "alert_id": generate_health_alert_id("HYPERTENSION_STAGE_2", timestamp, astronaut_id),
                "astronaut_id": astronaut_id,
                "timestamp": timestamp,
                "category": "PHYSIOLOGICAL_WARNING",
                "severity": "WARNING",
                "alert_type": "HYPERTENSION_STAGE_2",
                "metric_name": "blood_pressure",
                "metric_value": bp_str,
                "threshold_applied": f">={bp_cfg['systolic_stage2']}/{bp_cfg['diastolic_stage2']} mmHg",
                "unit": "mmHg",
                "description": f"Stage 2 Hypertension benchmark: Blood pressure {bp_str} mmHg.",
                "explanation": (
                    "Sustained blood pressure at this level increases cardiovascular load and ocular venous pressure. "
                    "Relevant to monitoring Spaceflight-Associated Neuro-ocular Syndrome (SANS)."
                ),
                "recommendation": "Log dietary sodium, verify resting status, and schedule follow-up measurement with Flight Surgeon.",
                "guideline_reference": "AHA/ACC Hypertension Benchmarks / NASA SANS Clinical Framework"
            })
        elif sys_bp >= bp_cfg["systolic_stage1"] or dia_bp >= bp_cfg["diastolic_stage1"]:
            alerts.append({
                "alert_id": generate_health_alert_id("HYPERTENSION_STAGE_1", timestamp, astronaut_id),
                "astronaut_id": astronaut_id,
                "timestamp": timestamp,
                "category": "PHYSIOLOGICAL_WARNING",
                "severity": "INFO",
                "alert_type": "HYPERTENSION_STAGE_1",
                "metric_name": "blood_pressure",
                "metric_value": bp_str,
                "threshold_applied": f">={bp_cfg['systolic_stage1']}/{bp_cfg['diastolic_stage1']} mmHg",
                "unit": "mmHg",
                "description": f"Stage 1 Hypertension advisory: Blood pressure {bp_str} mmHg.",
                "explanation": "Mild elevation in arterial pressure; may reflect routine operational workload or temporary stress.",
                "recommendation": "Track daily trend to distinguish transient elevation from persistent baseline shifts.",
                "guideline_reference": "AHA/ACC 2017 Blood Pressure Categories"
            })

    # 3. Oxygen Saturation Evaluation (SpO2 %)
    if spo2 is not None:
        spo2_cfg = thresholds["oxygen_saturation"]
        if spo2 < spo2_cfg["hypoxia_severe"]:
            alerts.append({
                "alert_id": generate_health_alert_id("HYPOXIA_SEVERE", timestamp, astronaut_id),
                "astronaut_id": astronaut_id,
                "timestamp": timestamp,
                "category": "CRITICAL_VITALS_ALERT",
                "severity": "CRITICAL",
                "alert_type": "HYPOXIA_SEVERE",
                "metric_name": "oxygen_saturation",
                "metric_value": str(spo2),
                "threshold_applied": f"< {spo2_cfg['hypoxia_severe']}%",
                "unit": "%",
                "description": f"Critical hypoxia alert: Oxygen saturation {spo2}% is dangerously low.",
                "explanation": (
                    "Severe arterial hypoxemia impairs cognitive reasoning, visual acuity, and motor coordination. "
                    "In closed spacecraft cabins or EVA spacesuits, this indicates potential cabin depressurization, "
                    "life-support oxygen delivery failure, or respiratory compromise."
                ),
                "recommendation": "Immediately administer emergency supplemental oxygen mask, verify cabin atmospheric pO2, and alert Mission Control.",
                "guideline_reference": "NASA-STD-3001 Vol 2 Spacecraft Atmosphere Specifications / WHO Critical Care Guidelines"
            })
        elif spo2 <= spo2_cfg["hypoxia_mild"]:
            alerts.append({
                "alert_id": generate_health_alert_id("HYPOXIA_MILD", timestamp, astronaut_id),
                "astronaut_id": astronaut_id,
                "timestamp": timestamp,
                "category": "PHYSIOLOGICAL_WARNING",
                "severity": "WARNING",
                "alert_type": "HYPOXIA_MILD",
                "metric_name": "oxygen_saturation",
                "metric_value": str(spo2),
                "threshold_applied": f"<= {spo2_cfg['hypoxia_mild']}%",
                "unit": "%",
                "description": f"Mild hypoxemia warning: Oxygen saturation {spo2}% (below nominal 95%).",
                "explanation": (
                    "Sub-optimal hemoglobin saturation. Can occur from shallow breathing, sleep apnea, "
                    "elevated ambient CO2 (air stagnation pockets in zero-g), or sensor malposition."
                ),
                "recommendation": "Check cabin ventilation fans to eliminate local CO2 pockets; verify oximeter sensor fit.",
                "guideline_reference": "ISS Environmental Control and Life Support System (ECLSS) Flight Rules"
            })

    # 4. Body Temperature Evaluation (°C)
    if temp is not None:
        temp_cfg = thresholds["body_temperature"]
        if temp >= temp_cfg["hyperthermia_critical"]:
            alerts.append({
                "alert_id": generate_health_alert_id("HYPERTHERMIA_CRITICAL", timestamp, astronaut_id),
                "astronaut_id": astronaut_id,
                "timestamp": timestamp,
                "category": "CRITICAL_VITALS_ALERT",
                "severity": "CRITICAL",
                "alert_type": "HYPERTHERMIA_CRITICAL",
                "metric_name": "body_temperature",
                "metric_value": str(temp),
                "threshold_applied": f">= {temp_cfg['hyperthermia_critical']}°C",
                "unit": "°C",
                "description": f"Critical hyperthermia alert: Core body temperature {temp}°C is dangerously high.",
                "explanation": (
                    "Severe hyperthermia threatens cellular metabolic stability and neurological function. "
                    "In microgravity, convective body cooling is absent, making active heat rejection critical."
                ),
                "recommendation": "Initiate immediate active cooling, ensure hydration, and contact Flight Surgeon for emergency medical intervention.",
                "guideline_reference": "NASA Space Flight Medical Operations Protocol"
            })
        elif temp >= temp_cfg["fever_warning"]:
            alerts.append({
                "alert_id": generate_health_alert_id("FEVER_HYPERTHERMIA", timestamp, astronaut_id),
                "astronaut_id": astronaut_id,
                "timestamp": timestamp,
                "category": "PHYSIOLOGICAL_WARNING",
                "severity": "WARNING",
                "alert_type": "FEVER_HYPERTHERMIA",
                "metric_name": "body_temperature",
                "metric_value": str(temp),
                "threshold_applied": f">= {temp_cfg['fever_warning']}°C",
                "unit": "°C",
                "description": f"Fever / elevated core temperature: {temp}°C.",
                "explanation": (
                    "Elevated core temperature may reflect infection, inflammatory reaction, or 'space fever' "
                    "(chronic 1°C elevation in zero-g due to blunted radiant heat loss and altered circadian rhythm)."
                ),
                "recommendation": "Check for associated symptoms (chills, pain, rash); notify Flight Surgeon.",
                "guideline_reference": "NASA Space Flight Clinical Thermoregulation Standards"
            })
        elif temp < temp_cfg["hypothermia_critical"]:
            alerts.append({
                "alert_id": generate_health_alert_id("HYPOTHERMIA_CRITICAL", timestamp, astronaut_id),
                "astronaut_id": astronaut_id,
                "timestamp": timestamp,
                "category": "CRITICAL_VITALS_ALERT",
                "severity": "CRITICAL",
                "alert_type": "HYPOTHERMIA_CRITICAL",
                "metric_name": "body_temperature",
                "metric_value": str(temp),
                "threshold_applied": f"< {temp_cfg['hypothermia_critical']}°C",
                "unit": "°C",
                "description": f"Critical hypothermia alert: Core body temperature {temp}°C is severely depressed.",
                "explanation": "Severe hypothermia impairs myocardial conduction and metabolic enzymatic processes.",
                "recommendation": "Apply thermal blankets, check suit/cabin thermal control settings, and notify Flight Surgeon immediately.",
                "guideline_reference": "NASA-STD-3001 Vol 1 Crew Thermal Guidelines"
            })
        elif temp < temp_cfg["hypothermia_warning"]:
            alerts.append({
                "alert_id": generate_health_alert_id("HYPOTHERMIA_WARNING", timestamp, astronaut_id),
                "astronaut_id": astronaut_id,
                "timestamp": timestamp,
                "category": "PHYSIOLOGICAL_WARNING",
                "severity": "WARNING",
                "alert_type": "HYPOTHERMIA_WARNING",
                "metric_name": "body_temperature",
                "metric_value": str(temp),
                "threshold_applied": f"< {temp_cfg['hypothermia_warning']}°C",
                "unit": "°C",
                "description": f"Mild hypothermia advisory: Core body temperature {temp}°C.",
                "explanation": "Sub-optimal core temperature; can occur in unheated modules or during extended EVA preparations.",
                "recommendation": "Adjust cabin temperature or don additional thermal garments.",
                "guideline_reference": "NASA Thermal Comfort Standards"
            })

    return alerts
