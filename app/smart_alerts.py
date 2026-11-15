"""
smart_alerts.py - Smart Alert Explanation and Root-Cause Attribution Engine

Provides clear root-cause explanations and actionable aerospace operational recommendations
for radiation threshold alerts, statistical machine learning anomalies, and crew health vitals warnings.

Capabilities:
1. Root-Cause Explanation:
   - Identifies the specific measurement responsible for the alert (value, threshold applied, delta).
   - Associates each alert with instrument ID, spacecraft, module, and timestamp.
2. Anomaly vs. Threshold Categorization:
   - Distinguishes statistical ML anomalies (Isolation Forest departure) from operational safety benchmarks
     (NASA-STD-3001, NCRP-132, AHA, WHO).
3. Severity and Recommended Safe Follow-Up:
   - Severity tiers: INFO, WARNING, CRITICAL, ADVISORY.
   - Prescribes concrete aerospace operational verification steps (sensor seating check,
     baseline re-test, cabin ECLSS ventilation review, CHeCS checklist review, Flight Surgeon alert).
4. Alert Deduplication & Noise Suppression:
   - Computes deterministic hash to prevent alert fatigue and redundant notifications.
   - Rejects invalid or negative values to prevent false alarms.
5. Strict Aerospace Medical Boundaries:
   - NON-DIAGNOSTIC: Never diagnoses clinical diseases.
   - NON-PRESCRIBING: Never prescribes pharmaceuticals or dosages.
   - Never invents official NASA thresholds.
"""

from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import pydantic
from pydantic import BaseModel, Field

from app.db import (
    get_db_connection,
    insert_smart_alerts,
    query_smart_alerts
)

logger = logging.getLogger("astra_care.smart_alerts")


class SmartAlertItem(BaseModel):
    alert_id: str
    alert_category: str  # 'RADIATION_THRESHOLD', 'ML_STATISTICAL_ANOMALY', 'HEALTH_VITALS_ADVISORY'
    detection_engine: str  # 'ISOLATION_FOREST_ML', 'AEROSPACE_SAFETY_RULE', 'FLIGHT_RULE_ECLSS'
    severity: str  # 'INFO', 'WARNING', 'CRITICAL', 'ADVISORY'
    instrument_id: Optional[str] = None
    astronaut_id: Optional[str] = None
    timestamp: str
    responsible_metric: str
    metric_value: Optional[float] = None
    threshold_applied: Optional[float] = None
    deviation_delta: Optional[float] = None
    unit: Optional[str] = None
    root_cause_explanation: str
    operational_recommendation: str
    guideline_reference: str = "NASA-STD-3001 Vol 1"
    is_suppressed: bool = False
    dedup_hash: Optional[str] = None


def generate_smart_alert_from_radiation(
    reading: Dict[str, Any],
    advisory_threshold_ugy: float = 20.0,
    action_threshold_ugy: float = 100.0
) -> Optional[Dict[str, Any]]:
    """
    Evaluates a radiation reading and produces an enriched smart alert if thresholds or ML flags are met.
    """
    dose_rate = reading.get("absorbed_dose_rate")
    if dose_rate is None:
        return None

    try:
        dose_rate = float(dose_rate)
    except (ValueError, TypeError):
        return None

    # Reject invalid negative or extreme sensor glitch values (>5000 µGy/hr without confirmation)
    if dose_rate < 0.0 or dose_rate > 5000.0:
        return None

    inst = str(reading.get("instrument_id") or "UnknownDetector")
    ts = str(reading.get("timestamp") or datetime.now(timezone.utc).isoformat())
    region = reading.get("orbital_region") or "NOMINAL_LEO"
    is_ml_anomaly = bool(reading.get("ml_is_anomaly", False))
    ml_score = reading.get("ml_anomaly_score", 0.0)
    ml_severity = reading.get("ml_severity", "NORMAL")

    # 1. Operational Action Benchmark (CRITICAL > 100 µGy/hr)
    if dose_rate >= action_threshold_ugy:
        delta = round(dose_rate - action_threshold_ugy, 3)
        explanation = (
            f"Absorbed dose rate of {dose_rate:.2f} µGy/hr exceeds the operational Action Benchmark "
            f"({action_threshold_ugy} µGy/hr) by +{delta} µGy/hr on detector {inst}. "
            f"Orbital Region: {region}."
        )
        recommendation = (
            "1. Initiate crew radiation sheltering in heavily shielded modules (US Lab / Node 2 polyethylene quarters). "
            "2. Postpone or terminate all Extravehicular Activities (EVAs). "
            "3. Notify Flight Control and the Space Radiation Analysis Group (SRAG) immediately."
        )
        dedup = hashlib.sha256(f"RAD_ACTION_{inst}_{ts[:16]}".encode()).hexdigest()[:16]
        return {
            "alert_id": f"ALT-ACT-{dedup[:8].upper()}",
            "alert_category": "RADIATION_THRESHOLD",
            "detection_engine": "AEROSPACE_SAFETY_RULE",
            "severity": "CRITICAL",
            "instrument_id": inst,
            "timestamp": ts,
            "responsible_metric": "absorbed_dose_rate",
            "metric_value": dose_rate,
            "threshold_applied": action_threshold_ugy,
            "deviation_delta": delta,
            "unit": "µGy/hr",
            "root_cause_explanation": explanation,
            "operational_recommendation": recommendation,
            "guideline_reference": "NCRP Report No. 132 / ISS Flight Rules",
            "dedup_hash": dedup
        }

    # 2. Operational Advisory Benchmark (WARNING > 20 µGy/hr)
    if dose_rate >= advisory_threshold_ugy:
        delta = round(dose_rate - advisory_threshold_ugy, 3)
        region_note = "Expected during transit through the South Atlantic Anomaly (SAA)." if region == "SOUTH_ATLANTIC_ANOMALY" else "Elevated rate observed outside the South Atlantic Anomaly."
        explanation = (
            f"Absorbed dose rate of {dose_rate:.2f} µGy/hr exceeds the operational Advisory Benchmark "
            f"({advisory_threshold_ugy} µGy/hr) by +{delta} µGy/hr on detector {inst}. {region_note}"
        )
        recommendation = (
            "1. Verify spacecraft orbital position and SAA pass duration (~10-15 minutes). "
            "2. Cross-check readings with adjacent station detectors (DosTel1, DosTel2, Lidal). "
            "3. Maintain routine dosimetry tracking; no active module sheltering required unless rates exceed 100 µGy/hr."
        )
        dedup = hashlib.sha256(f"RAD_ADV_{inst}_{ts[:16]}".encode()).hexdigest()[:16]
        return {
            "alert_id": f"ALT-ADV-{dedup[:8].upper()}",
            "alert_category": "RADIATION_THRESHOLD",
            "detection_engine": "AEROSPACE_SAFETY_RULE",
            "severity": "WARNING",
            "instrument_id": inst,
            "timestamp": ts,
            "responsible_metric": "absorbed_dose_rate",
            "metric_value": dose_rate,
            "threshold_applied": advisory_threshold_ugy,
            "deviation_delta": delta,
            "unit": "µGy/hr",
            "root_cause_explanation": explanation,
            "operational_recommendation": recommendation,
            "guideline_reference": "NASA-STD-3001 Vol 1 / NCRP Report No. 132",
            "dedup_hash": dedup
        }

    # 3. Machine Learning Statistical Anomaly (Isolation Forest departure)
    if is_ml_anomaly:
        sev = "CRITICAL" if ml_severity == "CRITICAL_ANOMALY" else "WARNING"
        explanation = (
            f"Isolation Forest model flagged a multi-dimensional statistical novelty on detector {inst} "
            f"(Score: {ml_score:.3f}, Severity: {ml_severity}). "
            f"Reason: {reading.get('ml_anomaly_reason', 'Unusual multivariate deviation from historical baseline')}."
        )
        recommendation = (
            "1. Inspect detector silicon telemetry continuity and verify communication bus status. "
            "2. Check if reading correlates with orbital geomagnetic changes or sensor noise. "
            "3. Report anomaly to Biomedical Engineer (BME) if sustained."
        )
        dedup = hashlib.sha256(f"ML_ANOM_{inst}_{ts[:16]}".encode()).hexdigest()[:16]
        return {
            "alert_id": f"ALT-ML-{dedup[:8].upper()}",
            "alert_category": "ML_STATISTICAL_ANOMALY",
            "detection_engine": "ISOLATION_FOREST_ML",
            "severity": sev,
            "instrument_id": inst,
            "timestamp": ts,
            "responsible_metric": "ml_anomaly_score",
            "metric_value": ml_score,
            "threshold_applied": 0.0,
            "deviation_delta": round(abs(ml_score), 3),
            "unit": "decision_score",
            "root_cause_explanation": explanation,
            "operational_recommendation": recommendation,
            "guideline_reference": "ASTRA CARE ML Isolation Forest Model",
            "dedup_hash": dedup
        }

    return None


def sync_and_generate_smart_alerts(db_path: Optional[Path] = None) -> int:
    """
    Scans recent radiation records and ML anomaly records to populate smart alerts.
    """
    conn = get_db_connection(db_path)
    try:
        # Scan recent radiation records
        rows = conn.execute("""
        SELECT timestamp, instrument_id, absorbed_dose_rate, orbital_region, ml_is_anomaly, ml_anomaly_score, ml_severity, ml_anomaly_reason
        FROM dynamic_radiation_records
        ORDER BY timestamp DESC
        LIMIT 50;
        """).fetchall()

        alerts_to_insert = []
        for r in rows:
            alert = generate_smart_alert_from_radiation(dict(r))
            if alert:
                alerts_to_insert.append(alert)

        # Scan recent historical radiation records
        hist_rows = conn.execute("""
        SELECT timestamp, instrument_id, absorbed_dose_rate, orbital_region
        FROM radiation_records
        WHERE absorbed_dose_rate >= 20.0
        ORDER BY timestamp DESC
        LIMIT 30;
        """).fetchall()

        for hr in hist_rows:
            alert = generate_smart_alert_from_radiation(dict(hr))
            if alert:
                alerts_to_insert.append(alert)

        return insert_smart_alerts(alerts_to_insert, db_path)
    finally:
        conn.close()
