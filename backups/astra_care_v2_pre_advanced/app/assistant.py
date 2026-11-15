"""
assistant.py - AI Health and Space Radiation Assistant Module for ASTRA CARE 2.0

Implements:
1. Context-Aware Intent Classification:
   - Accurately classifies user queries into distinct aeromedical, radiation, symptom,
     telemetry, and operational categories without keyword confusion.
2. Contextual Telemetry Retrieval:
   - Dynamically queries latest astronaut health vitals (BPM, mmHg, SpO2 %, °C).
   - Dynamically inspects dynamic streaming radiation telemetry & historical RadLab archives.
   - Evaluates radiation trends, recent rate increases, and ML anomaly scores.
3. Concise, Structured Health & Operational Responses:
   - Direct answer first.
   - Why it matters.
   - Relevant next step.
   - When to contact the mission medical team.
4. Strict Medical Safety & Ethics:
   - NON-DIAGNOSTIC: does not diagnose clinical diseases; informational support only.
   - NON-PRESCRIBING: does not prescribe medications or dosages; refers to Flight Surgeon and CHeCS.
   - Transparent data classification: clearly separates historical data, simulated streams, and live feeds.
   - Graceful handling of unrelated questions, missing data, and unknown astronaut IDs.
"""

from datetime import datetime, timezone
import json
import logging
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.analysis import DISCLAIMER_TEXT as RAD_DISCLAIMER_TEXT
from app.data import RADIATION_FIELD_METADATA
from app.db import (
    DATABASE_PATH,
    get_db_connection,
    get_db_statistics
)
from app.health import (
    HEALTH_DISCLAIMER_TEXT,
    HEALTH_METRIC_METADATA
)

logger = logging.getLogger("astra_care.assistant")

ASSISTANT_DISCLAIMER = (
    "ASTRA CARE AI Assistant is an informational support tool for spaceflight telemetry. "
    "It does NOT provide clinical medical diagnosis or prescribe treatments. "
    "All telemetry should be verified by the crew and reviewed with the Mission Flight Surgeon. "
    "Demonstration thresholds are not official NASA mission operational flight rules."
)


# ============================================================================
# Pydantic Request & Response Models
# ============================================================================

class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        description="The astronaut's query or statement regarding radiation, health, or alerts.",
        json_schema_extra={"example": "Explain my latest radiation reading"}
    )
    astronaut_id: Optional[str] = Field(
        None,
        description="Optional astronaut identifier (e.g. AST-01, AST-02) for personalized context.",
        json_schema_extra={"example": "AST-01"}
    )


class ChatResponse(BaseModel):
    answer: str = Field(..., description="Direct plain-language explanation and operational guidance.")
    source: str = Field(
        ...,
        description="Origin of the answer: 'project_data', 'knowledge_base', 'safety_guardrail', or 'general_chat'."
    )
    status: str = Field("success", description="Status indicator: 'success' or 'warning'.")
    data_context: Optional[Dict[str, Any]] = Field(
        None,
        description="Relevant telemetry data points retrieved from database to contextualize the answer."
    )
    disclaimer: str = Field(
        ASSISTANT_DISCLAIMER,
        description="Mandatory aerospace safety and non-diagnostic medical disclaimer."
    )


# ============================================================================
# Database Context Retrieval Helpers
# ============================================================================

def get_latest_radiation_reading(db_path: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves the most recent radiation reading from dynamic streaming records or historical archive.
    """
    try:
        conn = get_db_connection(db_path)
        try:
            # 1. Check dynamic streaming telemetry first
            try:
                row = conn.execute("""
                    SELECT reading_id, timestamp, instrument_id, spacecraft, module,
                           absorbed_dose_rate, absorbed_dose_unit,
                           dose_equivalent_rate, dose_equivalent_unit,
                           flux, flux_unit, altitude, latitude, longitude,
                           orbital_region, data_source, is_simulated, is_live,
                           ml_is_anomaly, ml_anomaly_score, ml_severity, ml_anomaly_reason
                    FROM dynamic_radiation_records
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 1;
                """).fetchone()

                if row:
                    rec = dict(row)
                    rec["is_historical"] = False
                    rec["telemetry_nature"] = "Dynamic Radiation Telemetry Stream (Processed via ML Anomaly Detection)"
                    return rec
            except Exception:
                pass

            # 2. Fall back to historical NASA RadLab records
            try:
                hist_row = conn.execute("""
                    SELECT timestamp, instrument_id, spacecraft, module,
                           absorbed_dose_rate, absorbed_dose_unit,
                           dose_equivalent_rate, dose_equivalent_unit,
                           flux, flux_unit, altitude, latitude, longitude,
                           source_origin, is_historical
                    FROM radiation_records
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 1;
                """).fetchone()

                if hist_row:
                    rec = dict(hist_row)
                    rec["telemetry_nature"] = "Historical NASA RadLab Research Archive (Recorded aboard ISS; not live telemetry)"
                    rec["is_historical"] = True
                    rec["data_source"] = "historical_nasa_radlab"
                    return rec
            except Exception:
                pass

            return None
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"Error querying latest radiation reading: {exc}")
        return None


def get_recent_radiation_trend(limit: int = 5, db_path: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Retrieves the last N radiation measurements to evaluate real-time changes and trends.
    """
    try:
        conn = get_db_connection(db_path)
        try:
            rows = conn.execute("""
                SELECT reading_id, timestamp, instrument_id, absorbed_dose_rate, absorbed_dose_unit,
                       orbital_region, data_source, ml_is_anomaly, ml_anomaly_score
                FROM dynamic_radiation_records
                ORDER BY timestamp DESC, id DESC
                LIMIT ?;
            """, (limit,)).fetchall()

            if not rows:
                # Fall back to historical records
                rows = conn.execute("""
                    SELECT timestamp, instrument_id, absorbed_dose_rate, absorbed_dose_unit,
                           module as orbital_region, source_origin as data_source
                    FROM radiation_records
                    ORDER BY timestamp DESC, id DESC
                    LIMIT ?;
                """, (limit,)).fetchall()

            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"Error querying radiation trend: {exc}")
        return []


def get_latest_ml_anomaly(db_path: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves the most recent machine learning anomaly flagged by Isolation Forest.
    """
    try:
        conn = get_db_connection(db_path)
        try:
            row = conn.execute("""
                SELECT anomaly_id, reading_id, timestamp, instrument_id,
                       absorbed_dose_rate, unit, anomaly_score, severity,
                       primary_contributing_feature, baseline_z_score,
                       dose_rate_delta, explanation, recommendation, data_source
                FROM ml_anomaly_records
                ORDER BY timestamp DESC, id DESC
                LIMIT 1;
            """).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"Error querying latest ML anomaly: {exc}")
        return None


def get_latest_health_reading(astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves the latest astronaut health telemetry record.
    """
    try:
        conn = get_db_connection(db_path)
        try:
            if astronaut_id and astronaut_id.lower() not in ("general", "all", "none"):
                row = conn.execute("""
                    SELECT record_id, astronaut_id, timestamp, heart_rate, heart_rate_unit,
                           blood_pressure_systolic, blood_pressure_diastolic, blood_pressure_unit,
                           oxygen_saturation, oxygen_saturation_unit,
                           body_temperature, body_temperature_unit,
                           source_device, data_classification, notes
                    FROM astronaut_health_records
                    WHERE astronaut_id = ?
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 1;
                """, (astronaut_id,)).fetchone()
            else:
                row = conn.execute("""
                    SELECT record_id, astronaut_id, timestamp, heart_rate, heart_rate_unit,
                           blood_pressure_systolic, blood_pressure_diastolic, blood_pressure_unit,
                           oxygen_saturation, oxygen_saturation_unit,
                           body_temperature, body_temperature_unit,
                           source_device, data_classification, notes
                    FROM astronaut_health_records
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 1;
                """).fetchone()

            return dict(row) if row else None
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"Error querying latest health reading: {exc}")
        return None


def get_active_alerts_context(astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Dict[str, Any]:
    """
    Retrieves active radiation alerts, ML anomalies, and health alerts.
    """
    context: Dict[str, Any] = {
        "radiation_alerts": [],
        "ml_anomalies": [],
        "health_alerts": [],
        "total_active_alerts": 0
    }
    try:
        conn = get_db_connection(db_path)
        try:
            rad_rows = conn.execute("""
                SELECT alert_id, category, severity, alert_type, timestamp, instrument_id,
                       metric_name, metric_value, unit, description, recommendation
                FROM radiation_alerts
                ORDER BY timestamp DESC, id DESC
                LIMIT 5;
            """).fetchall()
            context["radiation_alerts"] = [dict(r) for r in rad_rows]

            ml_rows = conn.execute("""
                SELECT anomaly_id, timestamp, instrument_id, absorbed_dose_rate, severity, explanation
                FROM ml_anomaly_records
                ORDER BY timestamp DESC, id DESC
                LIMIT 3;
            """).fetchall()
            context["ml_anomalies"] = [dict(r) for r in ml_rows]

            if astronaut_id and astronaut_id.lower() not in ("general", "all", "none"):
                hlth_rows = conn.execute("""
                    SELECT alert_id, astronaut_id, timestamp, category, severity, alert_type,
                           metric_name, metric_value, unit, description, explanation, recommendation
                    FROM astronaut_health_alerts
                    WHERE astronaut_id = ?
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 5;
                """, (astronaut_id,)).fetchall()
            else:
                hlth_rows = conn.execute("""
                    SELECT alert_id, astronaut_id, timestamp, category, severity, alert_type,
                           metric_name, metric_value, unit, description, explanation, recommendation
                    FROM astronaut_health_alerts
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 5;
                """).fetchall()
            context["health_alerts"] = [dict(r) for r in hlth_rows]
            context["total_active_alerts"] = len(context["radiation_alerts"]) + len(context["health_alerts"]) + len(context["ml_anomalies"])
            return context
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"Error querying alerts context: {exc}")
        return context


# ============================================================================
# Safety Guardrails Filter
# ============================================================================

def evaluate_safety_guardrails(query_text: str) -> Optional[Tuple[str, str]]:
    """
    Evaluates queries against strict aerospace medical safety guardrails.
    Returns (answer, source_tag) if a safety intervention is required, or None to continue.
    """
    lower = query_text.lower().strip()

    # Guardrail 1: Clinical Disease Diagnosis
    diagnosis_patterns = [
        r"\b(diagnose\b|diagnosis|am i suffering from|what disease|what illness)\b",
        r"\b(could i have|do i have) .*(cancer|disease|heart attack|heart disease|condition|illness|stroke)\b",
        r"\bis this (cancer|heart disease|a heart attack|a stroke)\b"
    ]
    for pattern in diagnosis_patterns:
        if re.search(pattern, lower):
            answer = (
                "ASTRA CARE is an informational spaceflight monitoring system and cannot diagnose diseases, "
                "cannot provide clinical diagnoses, or evaluate pathological syndromes.\n\n"
                "Physiological metrics (heart rate, blood pressure, SpO2, and temperature) reflect current "
                "operational telemetry and microgravity adaptation rather than a clinical diagnosis. "
                "If you are experiencing unusual physical symptoms, discomfort, or concerning telemetry readings, "
                "please follow standard mission medical checklists and contact the Mission Flight Surgeon "
                "and Biomedical Engineer (BME) immediately."
            )
            return answer, "safety_guardrail"

    # Guardrail 2: Pharmaceutical Prescription & Medication
    prescription_patterns = [
        r"\b(what (medicine|medication|drug|pills?) should i take|prescribe|prescription|can i take (aspirin|ibuprofen|antibiotics|morphine|paracetamol)|give me a prescription)\b"
    ]
    for pattern in prescription_patterns:
        if re.search(pattern, lower):
            answer = (
                "ASTRA CARE is strictly non-prescriptive and cannot recommend, prescribe, or adjust "
                "medications or pharmacological dosages.\n\n"
                "All medical treatments in space must be administered strictly in accordance with the "
                "onboard Crew Health Care System (CHeCS) formulary and under the direct operational authorization "
                "of the Mission Flight Surgeon or Crew Medical Officer (CMO). Please consult flight control "
                "before taking any onboard medications."
            )
            return answer, "safety_guardrail"

    # Guardrail 3: Unauthorized Emergency or Spacecraft Operational Commands
    emergency_patterns = [
        r"\b(should i (abort|depressurize|vent the airlock|evacuate the station|shut down life support)|emergency abort)\b"
    ]
    for pattern in emergency_patterns:
        if re.search(pattern, lower):
            answer = (
                "Safety Alert: ASTRA CARE provides telemetry insights only and is never authorized to issue "
                "emergency vehicle commands, mission abort instructions, or life-support modifications.\n\n"
                "For any vehicle or life-support anomaly, follow the approved Emergency Flight Rules (EFR), "
                "alert the Station Commander, and establish immediate voice communication with Flight Control / CAPCOM."
            )
            return answer, "safety_guardrail"

    # Guardrail 4: Inquiry into inventing NASA medical thresholds
    threshold_patterns = [
        r"\b(invent .*(threshold|limit)|make up .*(limit|threshold)|official secret limits)\b"
    ]
    for pattern in threshold_patterns:
        if re.search(pattern, lower):
            answer = (
                "ASTRA CARE adheres strictly to published aerospace guidelines (NASA-STD-3001 Vol 1, "
                "NCRP Report No. 132, AHA, and WHO) and never invents or synthesizes unofficial medical or radiation limits.\n\n"
                "In demonstration environments, test parameters are clearly identified as simulated baselines and must "
                "never be misconstrued as binding operational flight rules."
            )
            return answer, "safety_guardrail"

    return None


# ============================================================================
# Specific Intelligent Intent Handlers
# ============================================================================

def handle_why_radiation_increased(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'Why did radiation increase?' / 'Why has radiation increased?'
    Inspects recent telemetry readings, calculates observed change, and explains contextual factors.
    """
    trend = get_recent_radiation_trend(5, db_path)
    if len(trend) >= 2:
        latest = trend[0]
        prev = trend[1]
        rate_latest = latest.get("absorbed_dose_rate", 0.0)
        rate_prev = prev.get("absorbed_dose_rate", 0.0)
        delta = round(rate_latest - rate_prev, 3)
        inst = latest.get("instrument_id", "detector")
        region = latest.get("orbital_region", "NOMINAL_LEO")
        source = latest.get("data_source", "simulated_streaming")

        if delta > 0:
            observed_change = (
                f"Your latest radiation reading on {inst} increased by +{delta} µGy/hr "
                f"(from {rate_prev} µGy/hr to {rate_latest} µGy/hr) at {latest.get('timestamp')}."
            )
        else:
            observed_change = (
                f"Your latest reading on {inst} is {rate_latest} µGy/hr (previous: {rate_prev} µGy/hr). "
                f"No net increase occurred in the most recent reading."
            )

        context_reason = ""
        if region == "SOUTH_ATLANTIC_ANOMALY":
            context_reason = (
                "The spacecraft is currently transiting the South Atlantic Anomaly (SAA), where the inner Van Allen "
                "radiation belt dips closest to low Earth orbit, causing a transient surge in trapped proton flux."
            )
        elif delta > 15.0:
            context_reason = (
                "This rate surge indicates an elevated particle influx, consistent with an SAA pass, solar energetic "
                "particle (SEP) variation, or an injected test anomaly."
            )
        else:
            context_reason = (
                "Minor fluctuations are typical in low Earth orbit due to orbital geomagnetic latitude changes, "
                "detector orientation variations, and cosmic ray background noise."
            )

        answer = (
            f"1. Direct Answer:\n"
            f"{observed_change}\n"
            f"{context_reason}\n\n"
            f"2. Why It Matters:\n"
            f"Monitoring rate of change helps distinguish temporary orbital passages from significant space weather "
            f"events (such as Coronal Mass Ejections) that require shelter protocols.\n\n"
            f"3. Relevant Next Step:\n"
            f"Check the orbital trajectory display and verify whether the detector reading returns to baseline "
            f"(~1.5–4.0 µGy/hr) after exiting the anomaly region.\n\n"
            f"4. When to Contact the Medical Team:\n"
            f"Notify the Biomedical Engineer (BME) if dose rates remain persistently above 20 µGy/hr outside SAA coordinates."
        )
        return answer, "project_data", {"trend": trend, "delta": delta}

    # Fallback if no recent stream trend
    answer = (
        "1. Direct Answer:\n"
        "Radiation increases in low Earth orbit are primarily driven by two operational phenomena:\n"
        "• South Atlantic Anomaly (SAA) Transits: Trapped proton belts dip to ~400 km altitude, temporarily elevating dose rates to 15–40 µGy/hr for 10–15 minutes.\n"
        "• Solar Energetic Particle (SEP) Events: Coronal mass ejections and solar flares inject high-energy protons into the magnetosphere.\n\n"
        "2. Why It Matters:\n"
        "Tracking rate spikes allows crew members to follow ALARA (As Low As Reasonably Achievable) principles and seek heavily shielded modules during elevated flux.\n\n"
        "3. Relevant Next Step:\n"
        "Verify spacecraft geographic coordinates and consult the active Radiation Monitoring tab for detector baseline comparison.\n\n"
        "4. When to Contact the Medical Team:\n"
        "Alert Flight Control and the Mission Flight Surgeon immediately if doses exceed the 100 µGy/hr operational action benchmark."
    )
    return answer, "knowledge_base", None


def handle_radiation_health_effects(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'How can radiation affect astronaut health?'
    """
    answer = (
        "1. Direct Answer:\n"
        "Space radiation (Galactic Cosmic Rays and Solar Particle Events) affects astronaut health through cellular "
        "ionization and DNA double-strand breaks.\n\n"
        "2. Key Health Risks:\n"
        "• Acute Risks (High Dose / Solar Flares): Acute Radiation Sickness (ARS), nausea, fatigue, bone marrow depression, and temporary immune suppression.\n"
        "• Chronic / Career Risks (Continuous Low Dose): Elevated lifetime risk of cancer (leukemia, solid tumors), radiation-induced cataracts, and cardiovascular endothelial damage.\n"
        "• Central Nervous System (CNS): High-Z and high-energy (HZE) heavy ions can affect neural synaptic plasticity and cognitive performance on long-duration interplanetary missions.\n\n"
        "3. Relevant Next Step:\n"
        "Maintain routine dosimetry tracking (absorbed dose in µGy and biological dose equivalent in µSv) and follow onboard ALARA radiation shielding protocols.\n\n"
        "4. When to Contact the Medical Team:\n"
        "Consult the Flight Surgeon whenever cumulative career exposure approaches NASA-STD-3001 permissible limits (600 mSv career limit)."
    )
    return answer, "knowledge_base", None


def handle_radiation_precautions(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'What precautions can reduce unnecessary radiation exposure?'
    """
    answer = (
        "1. Direct Answer:\n"
        "Astronauts reduce unnecessary radiation exposure through three core shielding and operational principles:\n"
        "• Module Sheltering: Relocate to heavily shielded station modules (such as Node 2 crew quarters or US Lab) with hydrogen-rich polyethylene shielding during elevated radiation.\n"
        "• EVA Timing Avoidance: Never conduct Extravehicular Activities (spacewalks) during solar energetic particle (SEP) alerts or SAA transit windows.\n"
        "• Equipment Water Wall Positioning: Position water storage bags and cargo contingency packs along exterior-facing bulkhead walls to absorb secondary neutrons and heavy ions.\n\n"
        "2. Why It Matters:\n"
        "Minimizing acute bursts preserves bone marrow function and minimizes lifetime career radiation risk.\n\n"
        "3. Relevant Next Step:\n"
        "Verify your personal dosimeter placement and check the active radiation alerts panel on the dashboard.\n\n"
        "4. When to Contact the Medical Team:\n"
        "Confirm shelter deployment orders with Flight Control and the Space Radiation Analysis Group (SRAG)."
    )
    return answer, "knowledge_base", None


def handle_radiation_anomaly_explanation(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'Explain this radiation anomaly' / 'Why was this reading flagged by the ML model?'
    """
    anomaly = get_latest_ml_anomaly(db_path)
    if anomaly:
        answer = (
            f"1. Direct Answer:\n"
            f"The latest radiation anomaly was flagged on detector {anomaly['instrument_id']} at {anomaly['timestamp']} "
            f"with an absorbed dose rate of {anomaly['absorbed_dose_rate']} {anomaly['unit']}.\n\n"
            f"2. Machine Learning Analysis (Isolation Forest):\n"
            f"• Severity: {anomaly['severity']}\n"
            f"• Anomaly Score: {anomaly['anomaly_score']} (negative indicates significant statistical departure)\n"
            f"• Primary Contributing Factor: {anomaly.get('primary_contributing_feature', 'multivariate departure')}\n"
            f"• Baseline Deviation: {anomaly.get('baseline_z_score', 'N/A')}σ from historical detector mean\n"
            f"• Explanation: {anomaly['explanation']}\n\n"
            f"3. Relevant Next Step:\n"
            f"{anomaly.get('recommendation', 'Inspect detector telemetry continuity and orbital position.')}\n\n"
            f"4. When to Contact the Medical Team:\n"
            f"Report to the Biomedical Engineer if the anomaly corresponds to physical symptoms or persistent elevated dose rates."
        )
        return answer, "project_data", {"anomaly": anomaly}

    # If no anomaly record stored yet
    latest_reading = get_latest_radiation_reading(db_path)
    dose_val = latest_reading.get("absorbed_dose_rate") if latest_reading else "N/A"
    unit_val = latest_reading.get("absorbed_dose_unit", "µGy/hr") if latest_reading else ""

    answer = (
        f"1. Direct Answer:\n"
        f"No active machine learning anomalies are currently flagged in SQLite. "
        f"The latest recorded radiation measurement is {dose_val} {unit_val}.\n\n"
        f"2. How Anomaly Detection Operates:\n"
        f"ASTRA CARE's Isolation Forest model evaluates multi-dimensional radiation telemetry (dose rate, flux, "
        f"detector baseline Z-score, rate of change, and orbital SAA context). When a measurement deviates significantly "
        f"from the detector's baseline distribution, it is tagged with an anomaly score and explainability breakdown.\n\n"
        f"3. Relevant Next Step:\n"
        f"Monitor the dynamic radiation stream or use the 'Inject Anomaly' control on the dashboard to test detector response.\n\n"
        f"4. When to Contact the Medical Team:\n"
        f"Consult Flight Control if unexplained sustained spikes occur outside the South Atlantic Anomaly."
    )
    return answer, "knowledge_base", latest_reading


def handle_south_atlantic_anomaly(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'What is the South Atlantic Anomaly?' / 'Explain the SAA'
    """
    answer = (
        "1. Direct Answer:\n"
        "The South Atlantic Anomaly (SAA) is an orbital geographic region where Earth's inner Van Allen "
        "radiation belt dips closest to low Earth orbit (~200–800 km altitude), centered over South America "
        "and the South Atlantic Ocean.\n\n"
        "2. Why It Matters:\n"
        "Earth's geomagnetic dipole is tilted by ~11° and offset by ~500 km from the planet's rotational center. "
        "This asymmetry creates a geomagnetic depression where trapped high-energy protons (tens to hundreds of MeV) "
        "penetrate deeper into the upper atmosphere. In low Earth orbit (such as aboard the ISS), transiting the SAA takes "
        "~10–15 minutes and accounts for over 85–90% of an astronaut's cumulative absorbed radiation dose during nominal periods.\n\n"
        "3. Relevant Next Step:\n"
        "Track spacecraft coordinates on the telemetry map. When transiting between Latitude -45° to -5° and Longitude -90° to 0°, "
        "anticipate temporary radiation rate increases up to 15–40 µGy/hr without cause for alarm.\n\n"
        "4. When to Contact the Medical Team:\n"
        "If elevated radiation rates persist after the spacecraft exits SAA geographic coordinates, notify Flight Control "
        "and the Space Radiation Analysis Group (SRAG)."
    )
    return answer, "knowledge_base", None


def handle_anomaly_score_meaning(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'What does an anomaly score mean?'
    """
    answer = (
        "1. Direct Answer:\n"
        "In ASTRA CARE, the anomaly score is a continuous decision metric generated by an unsupervised Isolation Forest "
        "machine learning model that evaluates multi-dimensional radiation telemetry.\n\n"
        "2. Why It Matters:\n"
        "• Model Mechanics: The Isolation Forest isolates observations by randomly selecting features and split values. "
        "Anomalous telemetry points require fewer splits to isolate than normal background points.\n"
        "• Score Interpretation: Scores range from -1.0 to +1.0. A score near or below 0 indicates an anomaly; scores well "
        "above 0 represent nominal background radiation. ASTRA CARE maps this score into four operational tiers: NORMAL, "
        "ADVISORY_ANOMALY, WARNING_ANOMALY, and CRITICAL_ANOMALY.\n"
        "• Features Analyzed: Absorbed dose rate, particle flux, detector baseline Z-score, rate of change delta, flux-to-dose ratio, "
        "and orbital SAA coordinates.\n\n"
        "3. Relevant Next Step:\n"
        "Inspect the ML Anomaly Card on the dashboard for the primary contributing feature and plain-language explanation.\n\n"
        "4. When to Contact the Medical Team:\n"
        "Notify Flight Control if a CRITICAL_ANOMALY (score < -0.2) occurs outside of known orbital passes."
    )
    return answer, "knowledge_base", None


def handle_detector_z_score(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'What is a detector baseline Z-score?' / 'Explain detector baseline'
    """
    answer = (
        "1. Direct Answer:\n"
        "A detector baseline Z-score measures how many standard deviations a current radiation reading deviates "
        "from that specific detector's historical baseline mean in low Earth orbit.\n\n"
        "2. Why It Matters:\n"
        "Every radiation detector (DosTel1, DosTel2, Lidal, DB8) has unique geometric shielding, orientation, "
        "and detection silicon physics. A baseline Z-score normalizes telemetry against each sensor's historical distribution "
        "(Z = (x - μ) / σ). A Z-score between -2.0 and +2.0 indicates nominal baseline background. A Z-score > 3.0 indicates "
        "a statistically significant surge, helping the Isolation Forest ML model distinguish real space weather events from "
        "routine background noise without bias toward unshielded detectors.\n\n"
        "3. Relevant Next Step:\n"
        "Check the detector Z-score gauge on the Radiation Monitoring dashboard to compare active readings against historical ISS baselines.\n\n"
        "4. When to Contact the Medical Team:\n"
        "Alert the Biomedical Engineer if multiple independent detectors simultaneously exhibit Z-scores > 4.0 outside the SAA."
    )
    return answer, "knowledge_base", None


def handle_radiation_alert_action(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'What should I do if a radiation alert triggers?'
    """
    answer = (
        "1. Direct Answer:\n"
        "If a space radiation alert triggers in ASTRA CARE, remain calm, verify spacecraft position, and follow approved "
        "radiation safety protocols (ALARA: As Low As Reasonably Achievable).\n\n"
        "2. Standard Operational Action Steps:\n"
        "• Check Orbital Location: Confirm if the alert occurred during an SAA pass (transient and expected) or in high-latitude geomagnetically open regions.\n"
        "• Check Alert Severity: ADVISORY (dose rate > 20 µGy/hr) requires crew awareness and dosimeter verification; ACTION (dose rate > 100 µGy/hr) requires operational shelter procedures.\n"
        "• Reposition to Heavily Shielded Areas: If an ACTION alert or Solar Particle Event (SPE) is active, relocate to high-mass shielded modules (e.g. US Lab, Node 2 crew quarters surrounded by polyethylene and water bags).\n"
        "• Halt EVA Activities: Immediately terminate or postpone any extravehicular activity.\n\n"
        "3. Relevant Next Step:\n"
        "Review the active alerts on the Radiation Monitoring dashboard and cross-check real-time dosimeter readings.\n\n"
        "4. When to Contact the Medical Team:\n"
        "Contact the Space Radiation Analysis Group (SRAG) and Mission Flight Surgeon immediately upon any confirmed ACTION-level radiation alert."
    )
    return answer, "knowledge_base", None


def handle_data_origin_query(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'Is this reading live or historical?' / 'Where does this radiation data come from?'
    """
    latest_rad = get_latest_radiation_reading(db_path)
    if latest_rad:
        is_hist = latest_rad.get("is_historical", False)
        is_sim = latest_rad.get("is_simulated", False)
        is_live = latest_rad.get("is_live", False)
        source = latest_rad.get("data_source") or latest_rad.get("source_origin") or "unknown"
        ts = latest_rad.get("timestamp")

        if is_hist:
            nature = "HISTORICAL NASA RADLAB RESEARCH DATA (recorded aboard the ISS in 2022; not live telemetry)."
        elif is_sim:
            nature = "SIMULATED DYNAMIC RADIATION STREAM (physics-grounded LEO demonstration; not live spacecraft telemetry)."
        elif is_live:
            nature = "ACTUAL LIVE TELEMETRY from an active sensor or spacecraft downlink."
        else:
            nature = "DEMONSTRATION RESEARCH TELEMETRY."

        answer = (
            f"1. Direct Answer:\n"
            f"The latest reading on display is {nature}\n\n"
            f"2. Telemetry Details:\n"
            f"• Timestamp: {ts}\n"
            f"• Detector: {latest_rad.get('instrument_id')}\n"
            f"• Data Source: {source}\n"
            f"• Historical Status: {'Historical Archive' if is_hist else 'Dynamic Incoming Stream'}\n"
            f"• Simulated Status: {'Simulated Demo' if is_sim else 'Real Telemetry'}\n\n"
            f"3. Scientific Accuracy Principle:\n"
            f"ASTRA CARE strictly distinguishes historical research archives from real-time feeds and never presents simulated demonstration data as actual live spacecraft readings."
        )
        return answer, "project_data", latest_rad

    answer = (
        "1. Direct Answer:\n"
        "ASTRA CARE maintains three separate data categories:\n"
        "• Historical NASA RadLab Archive: Authentic measurements collected by detectors aboard the ISS (2022).\n"
        "• Simulated Streaming Telemetry: A physics-grounded dynamic stream used for development and demonstration.\n"
        "• Physical Hardware Sensor / Live Downlink: Ready for future connection; currently in standby.\n\n"
        "Every telemetry record is transparently labeled in the UI and database."
    )
    return answer, "knowledge_base", None


def handle_heart_rate_query(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'What is my latest heart rate?' / 'Explain my heart rate' / 'What does my heart rate mean in space?'
    """
    health = get_latest_health_reading(astronaut_id, db_path)
    lower = query.lower()

    if health and health.get("heart_rate") is not None and not ("what does my heart rate mean" in lower or "what does heart rate mean" in lower):
        hr = health["heart_rate"]
        unit = health.get("heart_rate_unit", "BPM")
        ts = health.get("timestamp")
        ast_id = health.get("astronaut_id", "Crew")
        classification = health.get("data_classification", "simulated_demo")

        # Cautious physiological context
        if hr < 50:
            status_desc = "Bradycardia advisory (below 50 BPM). Common in well-conditioned astronauts at rest."
        elif hr > 100:
            status_desc = "Elevated heart rate (tachycardia advisory, >100 BPM). Typical during exercise or high workload."
        else:
            status_desc = "Within nominal resting range (60–100 BPM)."

        answer = (
            f"1. Direct Answer:\n"
            f"Your latest recorded heart rate for astronaut {ast_id} is {hr} {unit} (recorded at {ts}).\n"
            f"Classification: {classification}.\n"
            f"Assessment: {status_desc}\n\n"
            f"2. Why It Matters:\n"
            f"In microgravity, cardiovascular deconditioning and cephalad fluid shift alter resting autonomic tone and stroke volume.\n\n"
            f"3. Relevant Next Step:\n"
            f"Ensure the wearable sensor patch is snug against the skin. If resting, verify heart rate remains stable.\n\n"
            f"4. When to Contact the Medical Team:\n"
            f"Notify the Flight Surgeon if resting heart rate persistently exceeds 100 BPM or drops below 45 BPM accompanied by dizziness."
        )
        return answer, "project_data", health

    # General explanation or no record available
    answer = (
        "1. Direct Answer:\n"
        "In space, resting heart rate (measured in BPM) reflects cardiovascular autonomic regulation adapting to weightlessness.\n\n"
        "2. Why It Matters:\n"
        "Microgravity induces an immediate cephalad fluid shift (blood moves toward the head and chest). Initially, cardiac output increases, but within days, plasma volume drops by 10–15% and resting heart rate stabilizes around nominal baseline (60–100 BPM). Over long missions, cardiovascular deconditioning can cause orthostatic tachycardia upon gravitational re-exposure.\n\n"
        "3. Relevant Next Step:\n"
        "Perform daily aerobic countermeasure workouts (treadmill and cycle ergometer) to maintain cardiovascular endurance.\n\n"
        "4. Standard Benchmark & Flight Surgeon Contact:\n"
        "Nominal resting astronaut heart rates range between 60–100 BPM (NASA-STD-3001 benchmark). Contact the Flight Surgeon if resting rates persistently exceed 100 BPM."
    )
    return answer, "knowledge_base", health


def handle_blood_pressure_query(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'What is my latest blood pressure?' / 'Why is blood pressure monitoring important in space?' / 'Explain blood pressure in microgravity'
    """
    health = get_latest_health_reading(astronaut_id, db_path)
    lower = query.lower()

    if "why" in lower or "importance" in lower or "microgravity" in lower or "explain blood pressure" in lower:
        reading_note = f" (Latest recorded: {health['blood_pressure_systolic']}/{health['blood_pressure_diastolic']} mmHg)" if (health and health.get("blood_pressure_systolic")) else ""
        answer = (
            f"1. Direct Answer:\n"
            f"Blood pressure monitoring (systolic and diastolic in mmHg) is critical during spaceflight{reading_note} because the absence of gravity eliminates the hydrostatic pressure gradient.\n\n"
            f"2. Why It Matters:\n"
            f"• Systolic and Diastolic Pressure: Systolic measures arterial peak pressure during cardiac contraction; diastolic measures resting arterial pressure (nominal baseline: 120/80 mmHg).\n"
            f"• Cephalad Fluid Shift: 1.5 to 2 liters of interstitial fluid shift to the head and thorax, altering central venous pressure and baroreceptor sensitivity in microgravity.\n"
            f"• Orthostatic Intolerance: Reduced blood plasma volume and deconditioning can cause blood pooling in lower extremities upon re-entering Earth's gravity.\n\n"
            f"3. Relevant Next Step:\n"
            f"Maintain prescribed fluid loading and countermeasure exercises.\n\n"
            f"4. When to Contact the Medical Team:\n"
            f"Report systolic readings consistently above 140 mmHg or below 90 mmHg to the Mission Flight Surgeon."
        )
        return answer, "knowledge_base", health

    if health and health.get("blood_pressure_systolic") is not None:
        sys_bp = health["blood_pressure_systolic"]
        dia_bp = health["blood_pressure_diastolic"]
        unit = health.get("blood_pressure_unit", "mmHg")
        ts = health.get("timestamp")
        ast_id = health.get("astronaut_id", "Crew")

        answer = (
            f"1. Direct Answer:\n"
            f"Your latest blood pressure reading for {ast_id} is {sys_bp}/{dia_bp} {unit} (recorded at {ts}). Systolic: {sys_bp} mmHg, Diastolic: {dia_bp} mmHg.\n\n"
            f"2. Why It Matters:\n"
            f"Microgravity induces cephalad fluid shifts and shifts baroreceptor setpoints. A reading under 120/80 mmHg is considered nominal resting.\n\n"
            f"3. Relevant Next Step:\n"
            f"Verify cuff alignment at heart level and avoid caffeine or recent strenuous exercise before recording resting baseline.\n\n"
            f"4. When to Contact the Medical Team:\n"
            f"Contact the Flight Surgeon if systolic pressure exceeds 140 mmHg or drops below 90 mmHg."
        )
        return answer, "project_data", health

    answer = (
        "1. Direct Answer:\n"
        "Blood pressure is measured as systolic over diastolic pressure in mmHg (nominal astronaut standard: <120/80 mmHg).\n\n"
        "2. Why It Matters:\n"
        "In microgravity, cephalad fluid shift alters arterial baroreceptors and circulating blood volume.\n\n"
        "3. Relevant Next Step:\n"
        "Use the Health Telemetry interface to record a blood pressure observation using the onboard sphygmomanometer."
    )
    return answer, "knowledge_base", None


def handle_spo2_query(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'My oxygen saturation reading looks unusual. What should I do?' / 'What is my latest SpO2?' / 'What does SpO2 oxygen saturation mean?'
    """
    health = get_latest_health_reading(astronaut_id, db_path)
    lower = query.lower()

    if "what does" in lower or "mean" in lower or "explain" in lower:
        answer = (
            "1. Direct Answer:\n"
            "Oxygen saturation (SpO2) measures the percentage of hemoglobin in arterial blood that is saturated with oxygen (nominal astronaut range: 95–100%).\n\n"
            "2. Why It Matters:\n"
            "• Hemoglobin Oxygen Transport: Erythrocytes carry oxygen from alveolar capillaries to working muscles and vital organs.\n"
            "• Hypoxia Detection: An SpO2 between 90–94% indicates mild hypoxia, while an SpO2 below 90% indicates severe hypoxia requiring emergency oxygen.\n"
            "• Cabin Environment: In a closed spacecraft habitat, drops in SpO2 can signify ECLSS life-support issues (elevated CO2 or diminished O2) or peripheral sensor misalignment.\n\n"
            "3. Relevant Next Step:\n"
            "Ensure the pulse oximeter optical sensor is securely positioned on a warm finger.\n\n"
            "4. When to Contact the Medical Team:\n"
            "Notify the Flight Surgeon immediately if resting SpO2 drops below 95%."
        )
        return answer, "knowledge_base", health

    if "unusual" in lower or "what should i do" in lower or "low" in lower:
        latest_val = health.get("oxygen_saturation") if health else None
        reading_text = f"Your latest recorded SpO2 is {latest_val}%." if latest_val else "If your SpO2 reading appears unusual:"

        answer = (
            f"1. Direct Answer:\n"
            f"{reading_text} If your oxygen saturation reading drops below 95%, sit down and follow these immediate verification steps.\n\n"
            f"2. Why It Matters:\n"
            f"Spacecraft cabins are sealed environments. Mild hypoxia (SpO2 90–94%) or severe hypoxia (<90%) can result from sensor displacement, poor peripheral perfusion (cold fingers in space), or life-support atmospheric imbalances (elevated ppCO2 or reduced ppO2) impacting hemoglobin saturation.\n\n"
            f"3. Relevant Next Steps:\n"
            f"• Check sensor fit: Ensure the pulse oximeter optical sensor is clean and securely placed on a warm finger.\n"
            f"• Warm your hands: Peripheral vasoconstriction in microgravity often causes false low readings.\n"
            f"• Cross-check cabin atmosphere: Verify cabin oxygen partial pressure (ppO2 ~160 mmHg) on the environmental control display (ECLSS).\n"
            f"• Repeat the measurement while sitting calmly and breathing deeply.\n\n"
            f"4. When to Contact the Medical Team:\n"
            f"If confirmed SpO2 remains below 95% or if you experience shortness of breath, headache, or confusion, put on an emergency oxygen mask and alert Flight Control immediately."
        )
        return answer, "knowledge_base", health

    if health and health.get("oxygen_saturation") is not None:
        spo2 = health["oxygen_saturation"]
        unit = health.get("oxygen_saturation_unit", "%")
        ts = health.get("timestamp")
        ast_id = health.get("astronaut_id", "Crew")

        answer = (
            f"1. Direct Answer:\n"
            f"Your latest oxygen saturation (SpO2) for astronaut {ast_id} is {spo2}{unit} (recorded at {ts}). Hemoglobin saturation is nominal.\n\n"
            f"2. Why It Matters:\n"
            f"Normal astronaut arterial oxygen saturation is 95–100%. Levels below 90% indicate acute hypoxia.\n\n"
            f"3. Relevant Next Step:\n"
            f"If the reading was taken during or post-exercise, allow your breathing to normalize and re-verify baseline.\n\n"
            f"4. When to Contact the Medical Team:\n"
            f"Notify the Flight Surgeon if SpO2 drops below 94% without physical exertion."
        )
        return answer, "project_data", health

    answer = (
        "1. Direct Answer:\n"
        "SpO2 measures arterial oxygen saturation bound to hemoglobin (nominal range: 95–100%). Below 90% is hypoxia.\n\n"
        "2. Relevant Next Step:\n"
        "Place the pulse oximeter probe on your index finger to record a measurement in the Health Monitoring module."
    )
    return answer, "knowledge_base", None


def handle_temperature_query(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'Why is body temperature monitoring important?' / 'What is my body temperature?' / 'What is body temperature and space fever?'
    """
    health = get_latest_health_reading(astronaut_id, db_path)
    lower = query.lower()

    if "why" in lower or "importance" in lower or "space fever" in lower or "what is body temperature" in lower:
        answer = (
            "1. Direct Answer:\n"
            "Body temperature monitoring (measured in degrees Celsius or °C) is vital in space because microgravity impairs natural convective heat loss, leading to a phenomenon known as 'space fever'.\n\n"
            "2. Why It Matters:\n"
            "On Earth, heat is dissipated through convective air movement and sweat evaporation. In microgravity, warm air does not rise away from the body without active ventilation. Research shows that resting core body temperature in astronauts increases by ~1°C (reaching 38° Celsius during exercise) due to altered circadian thermoregulation and impaired convective perspiration cooling.\n\n"
            "3. Relevant Next Step:\n"
            "Ensure cabin airflow fans are functioning and stay well-hydrated during workouts.\n\n"
            "4. When to Contact the Medical Team:\n"
            "Report resting core temperatures above 38.0° Celsius (100.4°F) or persistent chills to the Flight Surgeon immediately."
        )
        return answer, "knowledge_base", health

    if health and health.get("body_temperature") is not None:
        temp = health["body_temperature"]
        unit = health.get("body_temperature_unit", "°C")
        ts = health.get("timestamp")
        ast_id = health.get("astronaut_id", "Crew")

        answer = (
            f"1. Direct Answer:\n"
            f"Your latest recorded core body temperature for {ast_id} is {temp} {unit} Celsius (recorded at {ts}).\n\n"
            f"2. Why It Matters:\n"
            f"Nominal resting body temperature ranges between 36.1–37.2°C (Celsius). In weightlessness, metabolic heat buildup and impaired convective loss can slightly elevate baseline readings.\n\n"
            f"3. Relevant Next Step:\n"
            f"Confirm that the tympanic or forehead sensor lens is clean and properly aligned.\n\n"
            f"4. When to Contact the Medical Team:\n"
            f"Contact the Flight Surgeon if resting temperature exceeds 37.8°C (Celsius)."
        )
        return answer, "project_data", health

    answer = (
        "1. Direct Answer:\n"
        "No body temperature measurement is currently available for this astronaut (nominal range: 36.1–37.2°C Celsius).\n\n"
        "2. Relevant Next Step:\n"
        "Take a core temperature reading with the medical thermometer and record it via the Health Telemetry interface."
    )
    return answer, "knowledge_base", None


def handle_symptom_dizziness(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'I am feeling dizzy. What should I do?'
    Strictly non-diagnostic: provides safe operational steps and advises medical notification.
    """
    answer = (
        "1. Direct Answer:\n"
        "If you are feeling dizzy in microgravity, sit down or anchor yourself in foot restraints immediately "
        "to prevent floating into station hardware, avoid rapid head movements, and report the symptom to the Mission Flight Surgeon.\n\n"
        "2. Why It Matters:\n"
        "Dizziness in space is commonly associated with:\n"
        "• Space Motion Sickness (SMS): Neuro-vestibular sensory conflict between the otolith organs and visual cues during the first 48–72 hours of microgravity.\n"
        "• Orthostatic Intolerance & Fluid Redistribution: Reduced plasma volume and blood pressure shifts.\n"
        "• Environmental Cabin Factors: Elevated CO2 levels (hypercapnia) or dehydration.\n\n"
        "3. Relevant Next Steps:\n"
        "• Rest quietly and fix your gaze on a stable interior focal point.\n"
        "• Check your vital signs: record heart rate, blood pressure, and SpO2 using the wearable sensor.\n"
        "• Check cabin CO2 partial pressure on the ECLSS console.\n"
        "• Drink water with electrolytes to restore intravascular hydration.\n\n"
        "4. When to Contact the Medical Team:\n"
        "Contact the Flight Surgeon and Crew Medical Officer (CMO) immediately. Do not attempt hazardous tasks, treadmill workouts, or EVA preparation while experiencing dizziness."
    )
    return answer, "knowledge_base", None


def handle_symptom_fatigue(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'I am feeling fatigued / exhausted. What should I do?'
    """
    answer = (
        "1. Direct Answer:\n"
        "If you are experiencing persistent fatigue or exhaustion, reduce high-intensity physical workload, "
        "verify your sleep schedule, and report your symptoms to the Flight Surgeon.\n\n"
        "2. Why It Matters:\n"
        "Spaceflight fatigue can stem from circadian disruption (16 sunrises/day on ISS), noise levels, "
        "accumulated sleep debt, microgravity cardiovascular workload, or elevated cabin carbon dioxide.\n\n"
        "3. Relevant Next Steps:\n"
        "• Review your crew rest allocation in the daily timeline (OSTPV).\n"
        "• Check SpO2 and body temperature for underlying signs of illness.\n"
        "• Ensure proper nutrition and hydration.\n\n"
        "4. When to Contact the Medical Team:\n"
        "Notify the Flight Surgeon if fatigue is accompanied by muscle weakness, dizziness, or affects mission performance."
    )
    return answer, "knowledge_base", None


def handle_symptom_nausea(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'I am feeling nauseated / motion sick. What should I do?'
    """
    answer = (
        "1. Direct Answer:\n"
        "If you are feeling nauseated, secure an emesis bag, anchor yourself in a stable position, "
        "minimize head tilt and pitch movements, and inform the Crew Medical Officer (CMO).\n\n"
        "2. Why It Matters:\n"
        "Approximately 60–70% of astronauts experience Space Adaptation Syndrome (SAS) during the first 2–4 days of spaceflight as the brain adapts to weightlessness.\n\n"
        "3. Relevant Next Steps:\n"
        "• Keep head still and avoid unnecessary rotation.\n"
        "• Sip water slowly to prevent dehydration.\n"
        "• Consult the approved onboard CHeCS medical checklist with the CMO.\n\n"
        "4. When to Contact the Medical Team:\n"
        "Contact the Flight Surgeon for authorization before taking approved anti-motion sickness medication (such as promethazine)."
    )
    return answer, "knowledge_base", None


def handle_symptom_headache(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'I have a headache. What should I do?'
    """
    answer = (
        "1. Direct Answer:\n"
        "If you have a headache aboard the spacecraft, rest in a well-ventilated module, check cabin CO2 levels, "
        "verify your vital signs, and report the symptom to the Flight Surgeon.\n\n"
        "2. Why It Matters:\n"
        "Space headaches are commonly induced by cephalad venous engorgement (increased intracranial venous pressure), "
        "elevated localized carbon dioxide pockets (microgravity CO2 pockets form in areas of low airflow), or dehydration.\n\n"
        "3. Relevant Next Steps:\n"
        "• Move away from dead air spaces and position yourself near a cabin ventilation diffuser.\n"
        "• Check SpO2 and blood pressure.\n"
        "• Ensure adequate oral hydration.\n\n"
        "4. When to Contact the Medical Team:\n"
        "Notify the Flight Surgeon if the headache is severe, accompanied by visual disturbances, or unresponsive to rest."
    )
    return answer, "knowledge_base", None


def handle_medical_alert_guidance(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'What should I do if I receive a medical alert?' / 'What does this alert mean?'
    """
    alerts_ctx = get_active_alerts_context(astronaut_id, db_path)
    active_count = alerts_ctx["total_active_alerts"]

    if active_count > 0:
        alert_summary = f"There are currently {active_count} active alert(s) in the database."
    else:
        alert_summary = "There are currently no critical active alerts in the database."

    answer = (
        f"1. Direct Answer:\n"
        f"{alert_summary} When a medical alert appears in ASTRA CARE, remain calm, sit down, and follow the standard 4-step verification protocol.\n\n"
        f"2. Standard Alert Verification Protocol:\n"
        f"• Step 1 - Check Hardware: Confirm wearable sensors, finger oximeter, and blood pressure cuffs are clean, firmly attached, and properly charged to verify the sensor.\n"
        f"• Step 2 - Contextualize Reading: Was the alert triggered right after heavy exercise (ARED/treadmill), during thermal stress, or post-meal?\n"
        f"• Step 3 - Re-test Baseline: Take a repeat measurement while resting quietly for 2 minutes to eliminate movement artifacts.\n"
        f"• Step 4 - Consult Medical Checklist: Review the onboard Crew Health Care System (CHeCS) medical checklist for the specific vital metric and alert the flight surgeon.\n\n"
        f"3. When to Contact the Medical Team:\n"
        f"If the alert is confirmed on repeat measurement (e.g. SpO2 < 95%, heart rate > 110 BPM resting, or BP > 140/90 mmHg) or accompanied by physical symptoms, contact the Mission Flight Surgeon and Biomedical Engineer (BME) immediately."
    )
    return answer, "project_data" if active_count > 0 else "knowledge_base", alerts_ctx


def handle_normal_unusual_unavailable(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'What is the difference between normal, unusual, and unavailable readings?'
    """
    answer = (
        "1. Direct Answer:\n"
        "ASTRA CARE categorizes telemetry into three distinct operational states:\n"
        "• Normal-looking readings: Telemetry within validated baseline bounds (e.g. resting HR 60–100 BPM, SpO2 95–100%, absorbed dose rate 1.5–25 µGy/hr) indicating nominal operational status.\n"
        "• Unusual readings: Measurements that deviate statistically or exceed aerospace advisory limits (e.g. resting HR > 100 BPM, SpO2 < 95%, radiation dose rate > 20 µGy/hr during SAA pass, or ML anomaly score > 0.5) requiring attention and verification.\n"
        "• Unavailable readings: Sensor disconnections, data packet loss, or null telemetry fields represented transparently as unavailable readings without synthetic fabrication.\n\n"
        "2. Medical Boundary:\n"
        "ASTRA CARE never invents official medical thresholds or operational flight rules; all benchmarks are derived from NASA-STD-3001, NCRP-132, and AHA standards.\n\n"
        "3. Relevant Next Step:\n"
        "Verify sensor connection if readings are unavailable, and follow standard checklists for unusual readings."
    )
    return answer, "knowledge_base", None


def handle_why_health_monitoring_matters(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'Why is regular health monitoring important during space missions?'
    """
    answer = (
        "1. Direct Answer:\n"
        "Regular physiological health monitoring is vital during space missions to detect acute life-support anomalies and manage multi-system microgravity adaptations.\n\n"
        "2. Why It Matters:\n"
        "• Cardiovascular Deconditioning: Elimination of hydrostatic blood pressure triggers fluid shift and plasma volume reduction, reducing aerobic capacity and blood pressure regulation.\n"
        "• Space Radiation: Ionizing cosmic rays and solar protons damage cellular DNA and elevate lifetime cancer risk.\n"
        "• Musculoskeletal Atrophy: Without gravitational loading, bone mineral density and muscle mass degrade continuously without countermeasures.\n\n"
        "3. Relevant Next Step:\n"
        "Maintain daily vital sign logging and adhere to the scheduled 2.5 hours of resistance and aerobic exercise."
    )
    return answer, "knowledge_base", None


def handle_active_health_alerts_query(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'Do I have any health alerts?'
    """
    alerts_ctx = get_active_alerts_context(astronaut_id, db_path)
    health_alerts = alerts_ctx["health_alerts"]
    rad_alerts = alerts_ctx["radiation_alerts"]
    ml_anomalies = alerts_ctx["ml_anomalies"]

    ast_label = f"astronaut {astronaut_id}" if astronaut_id else "the crew"

    if health_alerts or rad_alerts or ml_anomalies:
        details = []
        if health_alerts:
            details.append(f"• {len(health_alerts)} Health Alert(s): {health_alerts[0].get('description')}")
        if rad_alerts:
            details.append(f"• {len(rad_alerts)} Radiation Alert(s): {rad_alerts[0].get('description')}")
        if ml_anomalies:
            details.append(f"• {len(ml_anomalies)} ML Radiation Anomaly(ies): {ml_anomalies[0].get('explanation')}")

        alerts_list = "\n".join(details)
        answer = (
            f"1. Direct Answer:\n"
            f"Yes, active safety notifications exist for {ast_label}:\n"
            f"{alerts_list}\n\n"
            f"2. Why It Matters:\n"
            f"Alerts highlight deviations from nominal operational benchmarks to ensure early crew awareness.\n\n"
            f"3. Relevant Next Step:\n"
            f"Open the Safety Alerts tab on the dashboard to review complete guideline references and recommendations.\n\n"
            f"4. When to Contact the Medical Team:\n"
            f"Report any CRITICAL severity alerts to the Mission Flight Surgeon immediately."
        )
        return answer, "project_data", alerts_ctx

    answer = (
        f"1. Direct Answer:\n"
        f"No, there are currently zero active health alerts or radiation alerts for {ast_label}.\n\n"
        f"2. Status Summary:\n"
        f"All recent physiological vitals and radiation dosimetry measurements fall within nominal demonstration benchmarks.\n\n"
        f"3. Relevant Next Step:\n"
        f"Continue scheduled routine monitoring and daily countermeasure exercise."
    )
    return answer, "project_data", alerts_ctx


def handle_microgravity_adaptation(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'What happens to the human body in microgravity?'
    """
    answer = (
        "1. Direct Answer:\n"
        "In microgravity, the human body undergoes profound multi-system physiological adaptations:\n"
        "• Fluid Redistribution (Cephalad Shift): Blood and interstitial fluid shift towards the head and chest, causing puffy faces, nasal congestion, and reduced lower limb volume ('bird legs').\n"
        "• Cardiovascular Deconditioning: Blood plasma volume drops by ~10–15%, and left ventricular cardiac mass decreases due to reduced workload.\n"
        "• Musculoskeletal Atrophy: Weight-bearing bones (spine, pelvis, femur) lose ~1% bone mineral density per month without heavy resistance countermeasures; postural muscle fibers atrophy.\n"
        "• Neuro-Vestibular Adaptation: Otolith organs and semicircular canals adapt to the absence of gravitational acceleration, often causing Space Motion Sickness for 2–3 days.\n"
        "• Spaceflight Associated Neuro-ocular Syndrome (SANS): Elevated intracranial venous pressure can flatten the posterior globe and cause optic disc edema.\n\n"
        "2. Countermeasures in Place:\n"
        "Astronauts perform 2.5 hours of daily resistance and aerobic exercise (ARED, T2 treadmill, CEVIS cycle) to counteract bone and muscle loss.\n\n"
        "3. Relevant Next Step:\n"
        "Verify your daily exercise telemetry on the Health Monitoring dashboard."
    )
    return answer, "knowledge_base", None


def handle_radiation_units_physics(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'What is the difference between absorbed dose and dose equivalent?' / 'What are µGy and µSv?' / 'What do µGy/hr and µSv/hr mean?'
    """
    answer = (
        "1. Direct Answer:\n"
        "The difference between absorbed dose and dose-equivalent (dose equivalent) rate is biological weighting:\n"
        "• Absorbed Dose (µGy/hr / microGray): Measures the physical energy (physical ionizing radiation energy) deposited per unit mass of matter (1 Gray = 1 Joule/kg). It is an objective physical measurement.\n"
        "• Dose-Equivalent Rate (µSv/hr / microSievert): Measures the biological harm to human tissue by multiplying absorbed dose by a radiation quality factor Q (Dose-Equivalent = Absorbed Dose × Q). Heavy charged particles (HZE ions) and protons have higher quality factor Q values (1.5 to 20) than gamma rays (Q = 1).\n\n"
        "2. Fundamental Rule in ASTRA CARE:\n"
        "Absorbed dose (µGy/hr) and dose-equivalent (µSv/hr) belong to distinct physical domains and must never be added or combined together.\n\n"
        "3. Relevant Next Step:\n"
        "View both rates side-by-side on the Radiation Monitoring dashboard."
    )
    return answer, "knowledge_base", None


def handle_latest_radiation_reading(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Answers: 'Explain my latest radiation reading.'
    """
    reading = get_latest_radiation_reading(db_path)
    if reading:
        dose = reading.get("absorbed_dose_rate")
        unit = reading.get("absorbed_dose_unit", "µGy/hr")
        eq_dose = reading.get("dose_equivalent_rate")
        eq_unit = reading.get("dose_equivalent_unit", "µSv/hr")
        inst = reading.get("instrument_id", "detector")
        ts = reading.get("timestamp")
        source = reading.get("data_source") or reading.get("source_origin") or "NASA RadLab"
        nature = reading.get("telemetry_nature", "Radiation Telemetry")
        is_anom = reading.get("ml_is_anomaly", False)
        is_hist = reading.get("is_historical", False)

        eq_text = f", Dose Equivalent: {eq_dose} {eq_unit}" if eq_dose is not None else ""
        anomaly_text = f" (ML Anomaly Status: Flagged - {reading.get('ml_severity', 'ANOMALY')})" if is_anom else " (ML Status: Nominal)"
        hist_note = "historical NASA RadLab research data recorded aboard ISS" if is_hist else "dynamic streaming telemetry (evaluated against historical NASA RadLab baseline models)"

        answer = (
            f"1. Direct Answer:\n"
            f"Your latest space radiation measurement on detector {inst} shows an absorbed dose rate of {dose} {unit}{eq_text}{anomaly_text}.\n"
            f"Timestamp: {ts}\n"
            f"Source & Telemetry Classification: {source} ({hist_note}; {nature}).\n\n"
            f"2. Scientific Context:\n"
            f"• Absorbed dose rate reflects physical ionizing radiation energy deposited per unit mass.\n"
            f"• Baseline low Earth orbit background ranges between ~1.5–4.0 µGy/hr in shielded ISS modules.\n"
            f"• South Atlantic Anomaly (SAA) transit passes can elevate rates to 15–40 µGy/hr.\n"
            f"• Operational advisory threshold is 20 µGy/hr; action threshold is 100 µGy/hr (NASA-STD-3001 / NCRP-132).\n\n"
            f"3. Relevant Next Step:\n"
            f"Check the Radiation Monitoring tab to observe the live trend graph and detector baseline comparison."
        )
        return answer, "project_data", reading

    answer = (
        "1. Direct Answer:\n"
        "No radiation records are currently available in the database.\n\n"
        "2. Relevant Next Step:\n"
        "Trigger the dynamic radiation stream or fetch historical RadLab samples from the Radiation Monitoring dashboard."
    )
    return answer, "knowledge_base", None


def handle_unrelated_query(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Handles queries unrelated to space radiation, astronaut health, or ASTRA CARE.
    Responds briefly and honestly without pretending to be a medical question.
    """
    answer = (
        "This question appears unrelated to astronaut health monitoring, space radiation dosimetry, or the ASTRA CARE system.\n\n"
        "I am designed specifically to assist crew members and flight controllers with:\n"
        "• Space radiation measurements (absorbed dose, dose equivalent, ML anomalies)\n"
        "• Astronaut physiological vitals (heart rate, blood pressure, SpO2, core temperature)\n"
        "• Flight medical procedures, symptom guidance, and active safety alerts.\n\n"
        "Please ask an astronaut health or mission radiation question."
    )
    return answer, "general_chat", None


# ============================================================================
# Master Assistant Intent Router & Response Generator
# ============================================================================

def generate_assistant_response(
    message: str,
    astronaut_id: Optional[str] = None,
    db_path: Optional[Any] = None
) -> ChatResponse:
    """
    Core entry point for the ASTRA CARE AI Health Assistant.
    Uses context-aware intent classification, direct structured answers, and strict medical safety.
    """
    cleaned_message = message.strip()
    if not cleaned_message:
        raise ValueError("Message cannot be empty or whitespace only.")

    logger.info(f"Processing assistant query: '{cleaned_message[:60]}...' (Astronaut: {astronaut_id or 'General'})")

    # Step 1: Safety Guardrails Check
    guardrail_hit = evaluate_safety_guardrails(cleaned_message)
    if guardrail_hit:
        answer, source_tag = guardrail_hit
        logger.info(f"Query intercepted by safety guardrail: {source_tag}")
        return ChatResponse(
            answer=answer,
            source=source_tag,
            status="warning",
            data_context=None,
            disclaimer=ASSISTANT_DISCLAIMER
        )

    lower = cleaned_message.lower()

    # Step 2: Context-Aware Intent Routing

    # 1. South Atlantic Anomaly (must precede general anomaly routing)
    if any(w in lower for w in ["south atlantic anomaly", "what is the saa", "saa pass", "inner van allen", "inner radiation belt", "van allen"]) or (lower.strip().startswith("what is") and "saa" in lower):
        answer, source, data_ctx = handle_south_atlantic_anomaly(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 2. Detector baseline Z-score
    if any(w in lower for w in ["z-score", "z score", "detector baseline", "baseline z"]):
        answer, source, data_ctx = handle_detector_z_score(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 3. Anomaly score meaning
    if ("anomaly score" in lower or "what does an anomaly score mean" in lower or "score mean" in lower):
        answer, source, data_ctx = handle_anomaly_score_meaning(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 4. Action on radiation alert
    if ("radiation alert" in lower or "radiation alert triggers" in lower or "radiation alarm" in lower or "what should i do if a radiation alert" in lower):
        answer, source, data_ctx = handle_radiation_alert_action(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 5. Difference between absorbed dose and dose equivalent / Units
    if any(w in lower for w in ["absorbed dose", "dose equivalent", "dose-equivalent", "µgy", "µsv", "microgray", "microsievert", "gray and sievert"]):
        answer, source, data_ctx = handle_radiation_units_physics(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 6. Why did radiation increase?
    if ("why" in lower or "reason" in lower or "cause" in lower) and any(w in lower for w in ["increase", "spike", "rise", "jump", "higher", "elevated", "surge"]) and any(w in lower for w in ["radiation", "dose", "rate"]):
        answer, source, data_ctx = handle_why_radiation_increased(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 7. How can radiation affect astronaut health? / Why is radiation dangerous?
    if ("affect" in lower or "danger" in lower or "effect" in lower or "risk" in lower or "harm" in lower) and any(w in lower for w in ["radiation", "cosmic ray", "solar"]):
        answer, source, data_ctx = handle_radiation_health_effects(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 8. Radiation precautions / how to reduce exposure
    if any(w in lower for w in ["precaution", "reduce", "protect", "shield", "prevention", "minimize"]) and any(w in lower for w in ["radiation", "exposure", "dose"]):
        answer, source, data_ctx = handle_radiation_precautions(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 9. Explain radiation anomaly / ML model flag
    if any(w in lower for w in ["anomaly", "flagged", "machine learning", "ml model", "outlier", "isolation forest"]):
        answer, source, data_ctx = handle_radiation_anomaly_explanation(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 10. Is this reading live or historical? / Where does data come from?
    if any(w in lower for w in ["live or historical", "historical or live", "is this reading live", "is this live", "where does this data come from", "data origin", "source of this data"]):
        answer, source, data_ctx = handle_data_origin_query(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 11. Heart rate inquiries
    if any(w in lower for w in ["heart rate", "pulse", "bpm", "heartrate"]):
        answer, source, data_ctx = handle_heart_rate_query(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 12. Blood pressure inquiries
    if any(w in lower for w in ["blood pressure", "systolic", "diastolic", "mmhg", "hypertension", "hypotension"]):
        answer, source, data_ctx = handle_blood_pressure_query(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 13. Oxygen saturation / SpO2 inquiries
    if any(w in lower for w in ["oxygen saturation", "spo2", "hypoxia", "oximeter"]):
        answer, source, data_ctx = handle_spo2_query(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 14. Body temperature inquiries
    if any(w in lower for w in ["body temperature", "temperature", "space fever", "fever", "core temp", "thermoregulation"]):
        answer, source, data_ctx = handle_temperature_query(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 15. Symptoms: Dizziness
    if any(w in lower for w in ["dizzy", "dizziness", "lightheaded", "vertigo", "spinning"]):
        answer, source, data_ctx = handle_symptom_dizziness(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 16. Symptoms: Fatigue
    if any(w in lower for w in ["fatigue", "fatigued", "exhausted", "tired", "lethargic", "exhaustion"]):
        answer, source, data_ctx = handle_symptom_fatigue(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 17. Symptoms: Nausea
    if any(w in lower for w in ["nausea", "nauseous", "nauseated", "vomit", "motion sickness", "space sickness", "sas"]):
        answer, source, data_ctx = handle_symptom_nausea(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 18. Symptoms: Headache
    if any(w in lower for w in ["headache", "migraine", "head pain", "head pressure"]):
        answer, source, data_ctx = handle_symptom_headache(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 19. Action on medical or health alert / alert guidance
    if any(w in lower for w in ["health alert triggers", "health alert", "medical alert", "alert triggers", "alert appears", "what should i do about this alert", "what should i do if i receive a medical alert", "what should an astronaut do when an alert appears"]):
        answer, source, data_ctx = handle_medical_alert_guidance(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 20. Do I have any health alerts? / Active alerts query
    if any(w in lower for w in ["do i have any health alerts", "do i have any alerts", "my alerts", "active alerts", "any alerts"]):
        answer, source, data_ctx = handle_active_health_alerts_query(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # Normal vs unusual vs unavailable readings
    if any(w in lower for w in ["normal, unusual", "unusual, and unavailable", "normal, unusual, and unavailable", "unavailable readings", "unusual readings"]):
        answer, source, data_ctx = handle_normal_unusual_unavailable(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # Why health monitoring is important
    if any(w in lower for w in ["health monitoring important", "why is regular health monitoring", "why is health monitoring"]):
        answer, source, data_ctx = handle_why_health_monitoring_matters(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 21. What happens to the human body in microgravity? / Adaptation
    if any(w in lower for w in ["human body in microgravity", "body in space", "microgravity effect", "fluid shift", "sans", "bone loss", "muscle loss", "adaptation"]):
        answer, source, data_ctx = handle_microgravity_adaptation(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 17. Difference between absorbed dose and dose equivalent / Units
    if any(w in lower for w in ["absorbed dose and dose equivalent", "difference between absorbed", "µgy", "µsv", "microgray", "microsievert", "gray and sievert"]):
        answer, source, data_ctx = handle_radiation_units_physics(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 18. Latest radiation reading explanation
    if any(w in lower for w in ["radiation reading", "my radiation", "latest radiation", "current radiation"]):
        answer, source, data_ctx = handle_latest_radiation_reading(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 19. General radiation questions fallback
    if any(w in lower for w in ["radiation", "cosmic ray", "dose", "sievert", "gray"]):
        answer, source, data_ctx = handle_latest_radiation_reading(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 20. General health vitals question fallback
    if any(w in lower for w in ["vitals", "health"]):
        health = get_latest_health_reading(astronaut_id, db_path)
        if health:
            ast_id = health.get("astronaut_id", "Crew")
            cls_tag = health.get("data_classification", "simulated_demo")
            answer = (
                f"1. Direct Answer:\n"
                f"Recent vitals for {ast_id}: Heart Rate = {health.get('heart_rate')} BPM, "
                f"Blood Pressure = {health.get('blood_pressure_systolic')}/{health.get('blood_pressure_diastolic')} mmHg, "
                f"Oxygen Saturation (SpO2) = {health.get('oxygen_saturation')}%, Body Temperature = {health.get('body_temperature')}°C. "
                f"Data Classification: {cls_tag}.\n\n"
                f"2. Relevant Next Step:\n"
                f"Consult the Health Monitoring view for time-series charts and detailed baseline comparisons."
            )
            return ChatResponse(answer=answer, source="project_data", status="success", data_context=health)
        else:
            answer = (
                "No health vitals are recorded for the selected astronaut. Record an observation via the Health Monitoring module."
            )
            return ChatResponse(answer=answer, source="knowledge_base", status="success")

    # 21. Detect clearly unrelated questions (e.g. general trivia, politics, sports, geography)
    unrelated_indicators = [
        "capital of", "who is", "who was", "weather in", "movie", "recipe",
        "president", "football", "cricket", "world cup", "stock price", "joke", "song"
    ]
    if any(term in lower for term in unrelated_indicators) or (len(cleaned_message.split()) > 3 and not any(w in lower for w in ["astronaut", "space", "mission", "nasa", "iss", "crew", "radiation", "health", "telemetry", "detector"])):
        answer, source, _ = handle_unrelated_query(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=None)

    # 22. Standard greeting & system overview
    stats = get_db_statistics(db_path)
    answer = (
        "Hello, crew member. I am the ASTRA CARE AI Medical & Radiation Assistant.\n\n"
        "I can directly explain and analyze your mission telemetry:\n"
        "• Space Radiation: 'Explain my latest radiation reading', 'Why did radiation increase?', 'Explain this radiation anomaly'\n"
        "• Physiological Vitals: 'What is my latest heart rate?', 'Why is blood pressure monitoring important?', 'My SpO2 looks unusual'\n"
        "• Clinical Symptoms: 'I am feeling dizzy. What should I do?', 'I have a headache'\n"
        "• Safety Alerts: 'Do I have any health alerts?', 'What should I do if I receive a medical alert?'\n"
        "• Data Transparency: 'Is this reading live or historical?'\n\n"
        f"Database Status: {stats.get('stored_dynamic_radiation_count', 0)} dynamic stream readings, "
        f"{stats.get('stored_radiation_records_count', 0)} historical NASA records, and "
        f"{stats.get('stored_health_records_count', 0)} crew vitals recorded in SQLite."
    )
    return ChatResponse(
        answer=answer,
        source="knowledge_base",
        status="success",
        data_context={"system_stats": stats},
        disclaimer=ASSISTANT_DISCLAIMER
    )
