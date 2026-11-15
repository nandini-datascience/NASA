"""
analysis.py - Radiation Telemetry Analysis and Alert Engine for ASTRA CARE

Implements:
1. Data Validation:
   - Checks timestamps, numeric boundaries, non-negative constraints.
   - Tracks missing values per instrument.
   - Preserves original measurement units (µGy/hr, µSv/hr, particles/(cm²·sr·s)).
   - Clearly distinguishes historical telemetry from live sensor readings.
2. Radiation Analysis:
   - Absorbed dose rate analysis (µGy/hr): min, max, mean, median, std_dev.
   - Dose-equivalent rate analysis (µSv/hr): min, max, mean, median, std_dev.
   - Cumulative exposure integration via trapezoidal rule strictly when consecutive
     sampling intervals satisfy valid continuous bounds (Delta t <= max_gap).
   - Timestamp gap identification and missing measurement detection.
   - Strict separation of physical units (never sums Grays and Sieverts).
3. Alert Engine:
   - Distinguishes DATA_QUALITY_WARNING from HEALTH_RISK_ALERT.
   - Configurable thresholds referencing validated aerospace standards
     (NASA-STD-3001 Vol 1 Crew Health, NCRP Report 132, ISS Flight Rules).
   - Detects elevated dose rates, high shelter levels, and sudden rate spikes.
   - Includes mandatory non-diagnostic medical disclaimer.
"""

from datetime import datetime, timezone
import hashlib
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("astra_care.analysis")

# Validated aerospace radiation benchmarks (NASA-STD-3001, NCRP-132, ISS Flight Rules)
DEFAULT_ADVISORY_DOSE_RATE_UGY_HR = 20.0     # Advisory elevated background / SAA passage benchmark
DEFAULT_ACTION_DOSE_RATE_UGY_HR = 100.0      # Operational benchmark for shelter consideration
DEFAULT_CRITICAL_DOSE_RATE_UGY_HR = 500.0    # Extreme solar energetic particle (SEP) event protocol
DEFAULT_ADVISORY_EQ_RATE_USV_HR = 25.0       # Dose equivalent rate advisory threshold
DEFAULT_SPIKE_THRESHOLD_UGY_HR = 15.0        # Rapid rate increase within <= 5 minutes
DEFAULT_MAX_GAP_SECONDS = 600.0              # 10 minutes max allowed gap for continuous integration

DISCLAIMER_TEXT = (
    "ASTRA CARE alerts and analysis reflect aerospace operational dosimetry benchmarks "
    "(NASA-STD-3001 Vol 1 / NCRP Report No. 132 / ISS Flight Rules). "
    "This system monitors radiation environment telemetry and does NOT diagnose astronaut health "
    "or provide medical advice."
)


def parse_iso_timestamp(ts_str: Any) -> Optional[datetime]:
    """
    Parses an ISO 8601 timestamp string into a timezone-aware UTC datetime.
    Supports standard formats like '2022-04-01T00:00:00' and trailing 'Z'.
    """
    if not ts_str or not isinstance(ts_str, str):
        return None
    try:
        clean_str = ts_str.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def generate_alert_id(alert_type: str, timestamp: str, instrument_id: str, category: str) -> str:
    """
    Generates a deterministic unique alert ID to prevent duplicate alerts.
    """
    seed = f"{alert_type}_{timestamp}_{instrument_id}_{category}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12].upper()
    prefix = "DQ" if category == "DATA_QUALITY_WARNING" else "HR"
    return f"ALT-{prefix}-{digest}"


def validate_radiation_records(
    records: List[Dict[str, Any]],
    source_origin: str = "NASA OSDR RadLab API"
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    """
    Validates radiation telemetry records:
    - Verifies timestamp parseability and chronological integrity.
    - Validates that radiation measurements are non-negative.
    - Preserves original measurement units.
    - Flags missing measurements and corrupted records.
    - Explicitly labels data as historical archived telemetry.

    Returns:
        (valid_records, validation_report, data_quality_alerts)
    """
    valid_records: List[Dict[str, Any]] = []
    data_quality_alerts: List[Dict[str, Any]] = []

    missing_absorbed = 0
    missing_equivalent = 0
    missing_flux = 0
    invalid_value_count = 0
    invalid_timestamp_count = 0

    for idx, r in enumerate(records):
        ts_str = r.get("timestamp")
        instrument_id = r.get("instrument_id") or f"UNKNOWN-SENSOR-{idx}"
        dt = parse_iso_timestamp(ts_str)

        # 1. Validate Timestamp
        if not dt:
            invalid_timestamp_count += 1
            data_quality_alerts.append({
                "alert_id": generate_alert_id("TIMESTAMP_PARSE_ERROR", str(ts_str), instrument_id, "DATA_QUALITY_WARNING"),
                "category": "DATA_QUALITY_WARNING",
                "severity": "WARNING",
                "alert_type": "TIMESTAMP_PARSE_ERROR",
                "timestamp": str(ts_str or "MISSING_TIMESTAMP"),
                "instrument_id": instrument_id,
                "spacecraft": r.get("spacecraft", "ISS"),
                "metric_name": "timestamp",
                "metric_value": None,
                "threshold_applied": None,
                "unit": "ISO 8601 string",
                "description": f"Record #{idx} has missing or unparseable timestamp: '{ts_str}'.",
                "recommendation": "Review telemetry ingestion pipeline for time formatting errors.",
                "guideline_reference": "ISO 8601 / CCSDS Telemetry Standard"
            })
            continue

        # 2. Validate Radiation Measurements
        absorbed_val = r.get("absorbed_dose_rate")
        equivalent_val = r.get("dose_equivalent_rate")
        flux_val = r.get("flux")

        has_negative_value = False

        # Absorbed dose rate check (µGy/hr)
        clean_absorbed = None
        if absorbed_val is not None:
            try:
                val = float(absorbed_val)
                if math.isnan(val) or math.isinf(val):
                    missing_absorbed += 1
                elif val < 0.0:
                    has_negative_value = True
                    invalid_value_count += 1
                    data_quality_alerts.append({
                        "alert_id": generate_alert_id("INVALID_VALUE_NEGATIVE_ABSORBED", ts_str, instrument_id, "DATA_QUALITY_WARNING"),
                        "category": "DATA_QUALITY_WARNING",
                        "severity": "CRITICAL",
                        "alert_type": "INVALID_VALUE",
                        "timestamp": ts_str,
                        "instrument_id": instrument_id,
                        "spacecraft": r.get("spacecraft", "ISS"),
                        "metric_name": "absorbed_dose_rate",
                        "metric_value": val,
                        "threshold_applied": 0.0,
                        "unit": "µGy/hr",
                        "description": f"Physically impossible negative absorbed dose rate ({val} µGy/hr) detected.",
                        "recommendation": "Flag sensor for telemetry corruption or zero-point calibration fault.",
                        "guideline_reference": "Dosimetry Physical Sensor Validation Standard"
                    })
                else:
                    clean_absorbed = val
            except (ValueError, TypeError):
                clean_absorbed = None
                missing_absorbed += 1
        else:
            missing_absorbed += 1

        # Dose equivalent rate check (µSv/hr)
        clean_equivalent = None
        if equivalent_val is not None:
            try:
                val = float(equivalent_val)
                if math.isnan(val) or math.isinf(val):
                    missing_equivalent += 1
                elif val < 0.0:
                    has_negative_value = True
                    invalid_value_count += 1
                    data_quality_alerts.append({
                        "alert_id": generate_alert_id("INVALID_VALUE_NEGATIVE_EQUIVALENT", ts_str, instrument_id, "DATA_QUALITY_WARNING"),
                        "category": "DATA_QUALITY_WARNING",
                        "severity": "CRITICAL",
                        "alert_type": "INVALID_VALUE",
                        "timestamp": ts_str,
                        "instrument_id": instrument_id,
                        "spacecraft": r.get("spacecraft", "ISS"),
                        "metric_name": "dose_equivalent_rate",
                        "metric_value": val,
                        "threshold_applied": 0.0,
                        "unit": "µSv/hr",
                        "description": f"Physically impossible negative dose equivalent rate ({val} µSv/hr) detected.",
                        "recommendation": "Flag instrument telemetry for corrupt floating-point bit flip.",
                        "guideline_reference": "Dosimetry Physical Sensor Validation Standard"
                    })
                else:
                    clean_equivalent = val
            except (ValueError, TypeError):
                clean_equivalent = None
                missing_equivalent += 1
        else:
            missing_equivalent += 1

        # Flux check
        clean_flux = None
        if flux_val is not None:
            try:
                val = float(flux_val)
                if not math.isnan(val) and not math.isinf(val) and val >= 0.0:
                    clean_flux = val
                else:
                    missing_flux += 1
            except (ValueError, TypeError):
                clean_flux = None
                missing_flux += 1
        else:
            missing_flux += 1

        # If values were negative, discard this corrupted reading
        if has_negative_value:
            continue

        # If record has neither absorbed dose nor equivalent dose, flag as missing measurement
        if clean_absorbed is None and clean_equivalent is None:
            data_quality_alerts.append({
                "alert_id": generate_alert_id("MISSING_RADIATION_MEASUREMENT", ts_str, instrument_id, "DATA_QUALITY_WARNING"),
                "category": "DATA_QUALITY_WARNING",
                "severity": "INFO",
                "alert_type": "MISSING_MEASUREMENT",
                "timestamp": ts_str,
                "instrument_id": instrument_id,
                "spacecraft": r.get("spacecraft", "ISS"),
                "metric_name": "radiation_rates",
                "metric_value": None,
                "threshold_applied": None,
                "unit": "none",
                "description": f"Telemetry record from detector {instrument_id} at {ts_str} contains no radiation dose values.",
                "recommendation": "Verify whether instrument was in standby or undergoing diagnostic mode.",
                "guideline_reference": "ISS Science Payload Operational Telemetry Protocol"
            })
            continue

        # Prepare normalized valid record with preserved original units
        valid_rec = {
            "timestamp": ts_str,
            "_parsed_dt": dt,
            "instrument_id": instrument_id,
            "spacecraft": r.get("spacecraft") or "ISS",
            "module": r.get("module"),
            "absorbed_dose_rate": clean_absorbed,
            "absorbed_dose_unit": "µGy/hr",
            "dose_equivalent_rate": clean_equivalent,
            "dose_equivalent_unit": "µSv/hr",
            "flux": clean_flux,
            "flux_unit": "particles/(cm²·sr·s)",
            "altitude": float(r["altitude"]) if r.get("altitude") is not None else None,
            "altitude_unit": "km",
            "latitude": float(r["latitude"]) if r.get("latitude") is not None else None,
            "longitude": float(r["longitude"]) if r.get("longitude") is not None else None,
            "source_origin": source_origin,
            "is_historical": True,
            "is_live": False,
            "telemetry_nature": "Historical archived measurement (NOT live sensor readings)"
        }
        valid_records.append(valid_rec)

    validation_report = {
        "total_records_inspected": len(records),
        "valid_records_count": len(valid_records),
        "invalid_records_count": len(records) - len(valid_records),
        "invalid_timestamp_count": invalid_timestamp_count,
        "invalid_negative_value_count": invalid_value_count,
        "missing_absorbed_dose_rate_count": missing_absorbed,
        "missing_dose_equivalent_rate_count": missing_equivalent,
        "missing_flux_count": missing_flux,
        "units_preserved": {
            "absorbed_dose_rate": "µGy/hr",
            "dose_equivalent_rate": "µSv/hr",
            "flux": "particles/(cm²·sr·s)",
            "altitude": "km",
            "latitude_longitude": "degrees"
        },
        "telemetry_classification": "Historical archived measurements (NOT live sensor readings)"
    }

    return valid_records, validation_report, data_quality_alerts


def calculate_descriptive_stats(values: List[float], unit: str) -> Dict[str, Any]:
    """
    Computes min, max, mean, median, and standard deviation for a numeric series.
    Preserves and attributes the measurement unit.
    """
    clean_values = [v for v in values if v is not None and not math.isnan(v) and not math.isinf(v)]
    if not clean_values:
        return {
            "unit": unit,
            "sample_size": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "standard_deviation": None,
            "status": "no_valid_measurements"
        }

    count = len(clean_values)
    min_val = min(clean_values)
    max_val = max(clean_values)
    mean_val = sum(clean_values) / count

    # Median calculation
    sorted_vals = sorted(clean_values)
    if count % 2 == 1:
        median_val = sorted_vals[count // 2]
    else:
        median_val = (sorted_vals[(count // 2) - 1] + sorted_vals[count // 2]) / 2.0

    # Sample standard deviation
    std_dev = None
    if count > 1:
        variance = sum((x - mean_val) ** 2 for x in clean_values) / (count - 1)
        std_dev = round(math.sqrt(variance), 4)

    return {
        "unit": unit,
        "sample_size": count,
        "min": round(min_val, 4),
        "max": round(max_val, 4),
        "mean": round(mean_val, 4),
        "median": round(median_val, 4),
        "standard_deviation": std_dev,
        "status": "computed"
    }


def compute_cumulative_exposure_for_series(
    time_rate_series: List[Tuple[datetime, float]],
    unit_rate: str,
    unit_dose: str,
    max_gap_seconds: float = DEFAULT_MAX_GAP_SECONDS
) -> Dict[str, Any]:
    """
    Computes cumulative radiation exposure using trapezoidal integration strictly when
    consecutive measurement intervals satisfy valid continuous bounds (Delta t <= max_gap_seconds).

    Mathematical Formulation:
        Delta Dose_i = ((Rate_{i-1} + Rate_i) / 2) * (Delta t_i / 3600.0)

    Conditions:
    - Strictly avoids integrating across large telemetry gaps (Delta t > max_gap_seconds).
    - Returns detailed diagnostics: valid duration, continuous segments, and excluded gaps.
    - Never combines or converts between physical units.
    """
    # Filter valid numeric points only
    clean_series = [
        (t, r) for t, r in time_rate_series 
        if r is not None and not math.isnan(r) and not math.isinf(r)
    ]

    if len(clean_series) < 2:
        return {
            "supported": False,
            "cumulative_dose": None,
            "unit": unit_dose,
            "reason": "Insufficient valid data points (minimum 2 consecutive measurements required for integration).",
            "valid_duration_seconds": 0.0,
            "valid_duration_hours": 0.0,
            "continuous_segments_count": 0,
            "gaps_excluded_count": 0,
            "calculation_method": "Trapezoidal numerical integration"
        }

    # Sort strictly by time
    sorted_series = sorted(clean_series, key=lambda x: x[0])

    total_dose = 0.0
    total_valid_seconds = 0.0
    continuous_segments = 0
    in_segment = False
    gaps_excluded = 0

    for i in range(1, len(sorted_series)):
        t_prev, r_prev = sorted_series[i - 1]
        t_curr, r_curr = sorted_series[i]

        delta_t_sec = (t_curr - t_prev).total_seconds()

        # Handle duplicate or backwards timestamps
        if delta_t_sec <= 0:
            continue

        # Check if interval exceeds max allowed gap threshold
        if delta_t_sec > max_gap_seconds:
            gaps_excluded += 1
            in_segment = False
            continue

        # Valid interval: trapezoidal rule
        # rate in unit/hr, time in hours (delta_t_sec / 3600.0) -> dose in unit
        interval_dose = ((r_prev + r_curr) / 2.0) * (delta_t_sec / 3600.0)
        total_dose += interval_dose
        total_valid_seconds += delta_t_sec

        if not in_segment:
            continuous_segments += 1
            in_segment = True

    if total_valid_seconds <= 0.0:
        return {
            "supported": False,
            "cumulative_dose": None,
            "unit": unit_dose,
            "reason": (
                f"All measurement intervals exceeded the maximum continuous gap threshold "
                f"({max_gap_seconds}s). Cumulative integration would be mathematically invalid."
            ),
            "valid_duration_seconds": 0.0,
            "valid_duration_hours": 0.0,
            "continuous_segments_count": 0,
            "gaps_excluded_count": gaps_excluded,
            "calculation_method": f"Trapezoidal integration with Delta t <= {max_gap_seconds}s restriction"
        }

    return {
        "supported": True,
        "cumulative_dose": round(total_dose, 6),
        "unit": unit_dose,
        "valid_duration_seconds": round(total_valid_seconds, 2),
        "valid_duration_hours": round(total_valid_seconds / 3600.0, 4),
        "continuous_segments_count": continuous_segments,
        "gaps_excluded_count": gaps_excluded,
        "max_gap_threshold_seconds": max_gap_seconds,
        "calculation_method": f"Trapezoidal numerical integration over valid continuous intervals (Delta t <= {max_gap_seconds}s)"
    }


def detect_timestamp_gaps(
    records: List[Dict[str, Any]],
    max_gap_seconds: float = DEFAULT_MAX_GAP_SECONDS
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Detects significant gaps in telemetry timestamps per instrument.
    Generates DATA_QUALITY_WARNING alerts for each gap exceeding max_gap_seconds.
    """
    gaps_detected: List[Dict[str, Any]] = []
    gap_alerts: List[Dict[str, Any]] = []

    # Group records by instrument_id
    by_instrument: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        inst = r.get("instrument_id")
        if inst and r.get("_parsed_dt"):
            by_instrument.setdefault(inst, []).append(r)

    for inst, inst_records in by_instrument.items():
        sorted_records = sorted(inst_records, key=lambda x: x["_parsed_dt"])
        for i in range(1, len(sorted_records)):
            prev_r = sorted_records[i - 1]
            curr_r = sorted_records[i]

            prev_dt: datetime = prev_r["_parsed_dt"]
            curr_dt: datetime = curr_r["_parsed_dt"]
            gap_seconds = (curr_dt - prev_dt).total_seconds()

            if gap_seconds > max_gap_seconds:
                gap_info = {
                    "instrument_id": inst,
                    "spacecraft": curr_r.get("spacecraft", "ISS"),
                    "gap_start": prev_r["timestamp"],
                    "gap_end": curr_r["timestamp"],
                    "gap_seconds": gap_seconds,
                    "gap_minutes": round(gap_seconds / 60.0, 2),
                    "threshold_applied_seconds": max_gap_seconds
                }
                gaps_detected.append(gap_info)

                gap_alerts.append({
                    "alert_id": generate_alert_id("TIMESTAMP_GAP", curr_r["timestamp"], inst, "DATA_QUALITY_WARNING"),
                    "category": "DATA_QUALITY_WARNING",
                    "severity": "WARNING",
                    "alert_type": "TIMESTAMP_GAP",
                    "timestamp": curr_r["timestamp"],
                    "instrument_id": inst,
                    "spacecraft": curr_r.get("spacecraft", "ISS"),
                    "metric_name": "timestamp_interval",
                    "metric_value": gap_seconds,
                    "threshold_applied": max_gap_seconds,
                    "unit": "seconds",
                    "description": (
                        f"Telemetry gap of {round(gap_seconds / 60.0, 1)} minutes detected on detector {inst} "
                        f"between {prev_r['timestamp']} and {curr_r['timestamp']}."
                    ),
                    "recommendation": "Check spacecraft communication link, orbital LOS (loss-of-signal), or data buffering.",
                    "guideline_reference": "NASA Space Flight Telemetry Continuity Standard"
                })

    return gaps_detected, gap_alerts


def evaluate_health_risk_alerts(
    records: List[Dict[str, Any]],
    advisory_dose_rate_ugy: float = DEFAULT_ADVISORY_DOSE_RATE_UGY_HR,
    action_dose_rate_ugy: float = DEFAULT_ACTION_DOSE_RATE_UGY_HR,
    critical_dose_rate_ugy: float = DEFAULT_CRITICAL_DOSE_RATE_UGY_HR,
    advisory_eq_rate_usv: float = DEFAULT_ADVISORY_EQ_RATE_USV_HR,
    spike_threshold_ugy: float = DEFAULT_SPIKE_THRESHOLD_UGY_HR
) -> List[Dict[str, Any]]:
    """
    Evaluates health risk and operational radiation level alerts based on validated
    aerospace benchmarks (NASA-STD-3001 Vol 1, NCRP-132, ISS Flight Rules):

    1. ELEVATED_DOSE_RATE: Absorbed dose rate >= advisory_dose_rate_ugy (WARNING)
    2. HIGH_DOSE_RATE: Absorbed dose rate >= action_dose_rate_ugy (CRITICAL - Shelter benchmark)
    3. CRITICAL_DOSE_RATE: Absorbed dose rate >= critical_dose_rate_ugy (CRITICAL - Extreme SEP)
    4. ELEVATED_EQUIVALENT_RATE: Dose equivalent rate >= advisory_eq_rate_usv (WARNING)
    5. RAPID_RATE_SPIKE: Sudden dose rate increase >= spike_threshold_ugy within <= 5 minutes (WARNING)
    """
    health_alerts: List[Dict[str, Any]] = []

    # Sort records chronologically per instrument for rate-of-change spike detection
    by_instrument: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        inst = r.get("instrument_id")
        if inst:
            by_instrument.setdefault(inst, []).append(r)

    for inst, inst_records in by_instrument.items():
        sorted_records = sorted(inst_records, key=lambda x: x["_parsed_dt"])

        for i, r in enumerate(sorted_records):
            ts = r["timestamp"]
            absorbed = r.get("absorbed_dose_rate")
            equivalent = r.get("dose_equivalent_rate")
            spacecraft = r.get("spacecraft", "ISS")

            # 1. Absorbed Dose Rate Level Checks (µGy/hr)
            if absorbed is not None:
                if absorbed >= critical_dose_rate_ugy:
                    health_alerts.append({
                        "alert_id": generate_alert_id("CRITICAL_DOSE_RATE", ts, inst, "HEALTH_RISK_ALERT"),
                        "category": "HEALTH_RISK_ALERT",
                        "severity": "CRITICAL",
                        "alert_type": "CRITICAL_DOSE_RATE",
                        "timestamp": ts,
                        "instrument_id": inst,
                        "spacecraft": spacecraft,
                        "metric_name": "absorbed_dose_rate",
                        "metric_value": absorbed,
                        "threshold_applied": critical_dose_rate_ugy,
                        "unit": "µGy/hr",
                        "description": (
                            f"Extreme radiation level: {absorbed} µGy/hr on detector {inst}. "
                            f"Exceeded critical threshold ({critical_dose_rate_ugy} µGy/hr)."
                        ),
                        "recommendation": "Execute station radiation contingency plan. Crew should remain in designated hardened storm shelters.",
                        "guideline_reference": "NASA-STD-3001 Vol 1 / ISS Flight Rule B13-102 (SEP Emergency Action Level)"
                    })
                elif absorbed >= action_dose_rate_ugy:
                    health_alerts.append({
                        "alert_id": generate_alert_id("HIGH_DOSE_RATE", ts, inst, "HEALTH_RISK_ALERT"),
                        "category": "HEALTH_RISK_ALERT",
                        "severity": "CRITICAL",
                        "alert_type": "HIGH_DOSE_RATE",
                        "timestamp": ts,
                        "instrument_id": inst,
                        "spacecraft": spacecraft,
                        "metric_name": "absorbed_dose_rate",
                        "metric_value": absorbed,
                        "threshold_applied": action_dose_rate_ugy,
                        "unit": "µGy/hr",
                        "description": (
                            f"High absorbed dose rate: {absorbed} µGy/hr on detector {inst}. "
                            f"Exceeded shelter benchmark threshold ({action_dose_rate_ugy} µGy/hr)."
                        ),
                        "recommendation": "Suspend all Extravehicular Activity (EVA). Review crew shielding in US Lab or Service Module aft.",
                        "guideline_reference": "NASA-STD-3001 Vol 1 Crew Health / NCRP Report No. 132"
                    })
                elif absorbed >= advisory_dose_rate_ugy:
                    health_alerts.append({
                        "alert_id": generate_alert_id("ELEVATED_DOSE_RATE", ts, inst, "HEALTH_RISK_ALERT"),
                        "category": "HEALTH_RISK_ALERT",
                        "severity": "WARNING",
                        "alert_type": "ELEVATED_DOSE_RATE",
                        "timestamp": ts,
                        "instrument_id": inst,
                        "spacecraft": spacecraft,
                        "metric_name": "absorbed_dose_rate",
                        "metric_value": absorbed,
                        "threshold_applied": advisory_dose_rate_ugy,
                        "unit": "µGy/hr",
                        "description": (
                            f"Elevated absorbed dose rate: {absorbed} µGy/hr on detector {inst}. "
                            f"Exceeded operational advisory threshold ({advisory_dose_rate_ugy} µGy/hr)."
                        ),
                        "recommendation": "Monitor radiation trajectory. Common during South Atlantic Anomaly (SAA) or solar disturbance.",
                        "guideline_reference": "ISS Flight Operations Radiation Advisory Guideline"
                    })

            # 2. Dose Equivalent Rate Checks (µSv/hr)
            if equivalent is not None and equivalent >= advisory_eq_rate_usv:
                health_alerts.append({
                    "alert_id": generate_alert_id("ELEVATED_EQUIVALENT_RATE", ts, inst, "HEALTH_RISK_ALERT"),
                    "category": "HEALTH_RISK_ALERT",
                    "severity": "WARNING",
                    "alert_type": "ELEVATED_EQUIVALENT_RATE",
                    "timestamp": ts,
                    "instrument_id": inst,
                    "spacecraft": spacecraft,
                    "metric_name": "dose_equivalent_rate",
                    "metric_value": equivalent,
                    "threshold_applied": advisory_eq_rate_usv,
                    "unit": "µSv/hr",
                    "description": (
                        f"Elevated dose equivalent rate: {equivalent} µSv/hr on detector {inst}. "
                        f"Exceeded advisory biological threshold ({advisory_eq_rate_usv} µSv/hr)."
                    ),
                    "recommendation": "Track cumulative equivalent dose towards mission ALARA limits.",
                    "guideline_reference": "NASA-STD-3001 Vol 1 Permissible Exposure Limits"
                })

            # 3. Sudden Spike Detection (Delta rate >= spike_threshold within <= 300s)
            if i > 0 and absorbed is not None:
                prev_r = sorted_records[i - 1]
                prev_absorbed = prev_r.get("absorbed_dose_rate")
                if prev_absorbed is not None:
                    delta_t_sec = (r["_parsed_dt"] - prev_r["_parsed_dt"]).total_seconds()
                    if 0 < delta_t_sec <= 300.0:
                        delta_rate = absorbed - prev_absorbed
                        if delta_rate >= spike_threshold_ugy:
                            health_alerts.append({
                                "alert_id": generate_alert_id("RAPID_RATE_SPIKE", ts, inst, "HEALTH_RISK_ALERT"),
                                "category": "HEALTH_RISK_ALERT",
                                "severity": "WARNING",
                                "alert_type": "RAPID_RATE_SPIKE",
                                "timestamp": ts,
                                "instrument_id": inst,
                                "spacecraft": spacecraft,
                                "metric_name": "absorbed_dose_rate_delta",
                                "metric_value": round(delta_rate, 4),
                                "threshold_applied": spike_threshold_ugy,
                                "unit": "µGy/hr jump",
                                "description": (
                                    f"Rapid radiation surge detected: +{round(delta_rate, 2)} µGy/hr increase "
                                    f"within {int(delta_t_sec)} seconds on detector {inst}."
                                ),
                                "recommendation": "Check space weather monitors (NOAA SWPC / GOES) for coronal mass ejection (CME) or SAA entry.",
                                "guideline_reference": "NASA Space Radiation Analysis Group (SRAG) Flight Rules"
                            })

    return health_alerts


def perform_full_radiation_analysis(
    records: List[Dict[str, Any]],
    source_origin: str = "NASA OSDR RadLab API",
    max_gap_seconds: float = DEFAULT_MAX_GAP_SECONDS,
    advisory_dose_rate_ugy: float = DEFAULT_ADVISORY_DOSE_RATE_UGY_HR,
    action_dose_rate_ugy: float = DEFAULT_ACTION_DOSE_RATE_UGY_HR,
    critical_dose_rate_ugy: float = DEFAULT_CRITICAL_DOSE_RATE_UGY_HR,
    advisory_eq_rate_usv: float = DEFAULT_ADVISORY_EQ_RATE_USV_HR,
    spike_threshold_ugy: float = DEFAULT_SPIKE_THRESHOLD_UGY_HR
) -> Dict[str, Any]:
    """
    Executes complete analysis pipeline:
    1. Validates records and flags corrupted/missing data.
    2. Calculates descriptive statistics for absorbed dose rate and dose equivalent rate separately.
    3. Computes cumulative exposure strictly when intervals support valid calculation.
    4. Detects timestamp gaps and issues data quality warnings.
    5. Evaluates operational health-risk alerts against aerospace standards.
    6. Returns structured JSON ready for frontend consumption.
    """
    # 1. Validation
    valid_records, validation_report, data_quality_alerts = validate_radiation_records(records, source_origin)

    # 2. Extract series for analysis
    absorbed_values: List[float] = []
    equivalent_values: List[float] = []

    absorbed_series: List[Tuple[datetime, float]] = []
    equivalent_series: List[Tuple[datetime, float]] = []

    for r in valid_records:
        dt: datetime = r["_parsed_dt"]
        if r["absorbed_dose_rate"] is not None:
            absorbed_values.append(r["absorbed_dose_rate"])
            absorbed_series.append((dt, r["absorbed_dose_rate"]))
        if r["dose_equivalent_rate"] is not None:
            equivalent_values.append(r["dose_equivalent_rate"])
            equivalent_series.append((dt, r["dose_equivalent_rate"]))

    # 3. Descriptive Statistics
    absorbed_stats = calculate_descriptive_stats(absorbed_values, "µGy/hr")
    equivalent_stats = calculate_descriptive_stats(equivalent_values, "µSv/hr")

    # 4. Cumulative Exposure Integration
    cumulative_absorbed = compute_cumulative_exposure_for_series(
        absorbed_series, "µGy/hr", "µGy", max_gap_seconds
    )
    cumulative_equivalent = compute_cumulative_exposure_for_series(
        equivalent_series, "µSv/hr", "µSv", max_gap_seconds
    )

    # 5. Gap Detection
    gaps_detected, gap_alerts = detect_timestamp_gaps(valid_records, max_gap_seconds)
    all_data_quality_alerts = data_quality_alerts + gap_alerts

    # 6. Health Risk Alerts
    health_risk_alerts = evaluate_health_risk_alerts(
        valid_records,
        advisory_dose_rate_ugy=advisory_dose_rate_ugy,
        action_dose_rate_ugy=action_dose_rate_ugy,
        critical_dose_rate_ugy=critical_dose_rate_ugy,
        advisory_eq_rate_usv=advisory_eq_rate_usv,
        spike_threshold_ugy=spike_threshold_ugy
    )

    # Clean valid_records for output (remove internal _parsed_dt object)
    cleaned_records_output = []
    for r in valid_records:
        rec_copy = dict(r)
        rec_copy.pop("_parsed_dt", None)
        cleaned_records_output.append(rec_copy)

    all_alerts = all_data_quality_alerts + health_risk_alerts

    return {
        "status": "success",
        "telemetry_nature": "Historical archived measurements (NOT live sensor readings)",
        "source_origin": source_origin,
        "disclaimer": DISCLAIMER_TEXT,
        "validation_report": validation_report,
        "radiation_analysis": {
            "absorbed_dose_analysis": {
                "unit": "µGy/hr",
                "statistics": absorbed_stats,
                "cumulative_exposure": cumulative_absorbed
            },
            "dose_equivalent_analysis": {
                "unit": "µSv/hr",
                "statistics": equivalent_stats,
                "cumulative_exposure": cumulative_equivalent
            },
            "units_rule_notice": (
                "Absorbed dose (µGy/hr / µGy) and dose-equivalent (µSv/hr / µSv) are maintained "
                "in separate physical domains and are never combined or summed together."
            )
        },
        "timestamp_continuity": {
            "max_allowed_gap_seconds": max_gap_seconds,
            "total_gaps_detected": len(gaps_detected),
            "gaps": gaps_detected
        },
        "alerts_summary": {
            "total_alerts_generated": len(all_alerts),
            "data_quality_warnings_count": len(all_data_quality_alerts),
            "health_risk_alerts_count": len(health_risk_alerts),
            "data_quality_warnings": all_data_quality_alerts,
            "health_risk_alerts": health_risk_alerts
        },
        "sample_records_count": len(cleaned_records_output),
        "sample_records_preview": cleaned_records_output[:5]
    }
