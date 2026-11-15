"""
assistant.py - AI Health and Space Radiation Assistant Module for ASTRA CARE

Provides intelligent, safety-conscious explanations and operational guidance for astronauts,
flight controllers, and medical teams.

Capabilities:
1. Explains space radiation telemetry (absorbed dose in µGy/hr, dose equivalent in µSv/hr,
   flux, altitude) and scientific units in plain language.
2. Explains astronaut physiological vitals (heart rate BPM, blood pressure mmHg, SpO2 %,
   body temperature °C) and orbital adaptation mechanisms (fluid shift, space fever).
3. Explains the difference between normal-looking, unusual, and unavailable readings
   without inventing official astronaut medical thresholds.
4. Explains available radiation alerts and clinical health alerts.
5. Provides general, safe operational guidance when an alert occurs (verifying sensors,
   following mission-approved medical procedures, notifying the Flight Surgeon).
6. Explains why continuous health monitoring is critical during space missions
   (microgravity cardiovascular deconditioning, bone/muscle atrophy, radiation exposure).
7. Answers contextual questions using available project data (SQLite database telemetry).

Safety Guardrails & Regulatory Compliance:
- Strictly NON-DIAGNOSTIC: Never diagnoses diseases or medical conditions.
- Strictly NON-PRESCRIBING: Never prescribes pharmaceuticals or medical treatments.
- Strictly NON-EMERGENCY-DIRECTIVE: Never issues unauthorized critical spacecraft actions.
- Truthful data attribution: Explicitly distinguishes between historical research data
  (NASA RadLab), simulated demonstration vitals ('simulated_demo'), and sensor telemetry.
- Graceful degradation: Operates 100% offline with zero external API key requirements,
  while supporting optional external LLMs via environment variables (GEMINI_API_KEY).
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

# Standard mission guidance disclaimer included with all assistant communications
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
    """
    Incoming chat request payload for the AI Health Assistant.
    """
    message: str = Field(
        ...,
        description="The astronaut's query or statement regarding radiation, health, or alerts.",
        json_schema_extra={"example": "Explain my latest radiation reading"}
    )
    astronaut_id: Optional[str] = Field(
        None,
        description="Optional astronaut identifier (e.g. AST-01, CREW-01) for personalized context.",
        json_schema_extra={"example": "AST-01"}
    )


class ChatResponse(BaseModel):
    """
    Structured response returned by the AI Health Assistant.
    """
    answer: str = Field(..., description="Plain-language explanation and operational guidance.")
    source: str = Field(
        ...,
        description="Origin of the answer: 'project_data', 'knowledge_base', 'safety_guardrail', or 'external_llm'."
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
    Retrieves the most recent radiation record stored in the database.
    Explicitly tags the record as historical NASA RadLab research data.
    """
    try:
        conn = get_db_connection(db_path)
        try:
            row = conn.execute("""
                SELECT timestamp, instrument_id, spacecraft, module,
                       absorbed_dose_rate, absorbed_dose_unit,
                       dose_equivalent_rate, dose_equivalent_unit,
                       flux, flux_unit, altitude, altitude_unit,
                       latitude, longitude, source_origin, is_historical
                FROM radiation_records
                ORDER BY timestamp DESC, id DESC
                LIMIT 1;
            """).fetchone()

            if not row:
                return None

            rec = dict(row)
            rec["telemetry_nature"] = "Historical NASA RadLab Research Archive (Recorded aboard ISS; not live telemetry)"
            rec["is_historical"] = True
            return rec
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"Error querying latest radiation reading: {exc}")
        return None


def get_latest_health_reading(astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves the latest astronaut health telemetry record.
    Preserves data classification ('simulated_demo', 'historical_study', 'sensor_telemetry').
    """
    try:
        conn = get_db_connection(db_path)
        try:
            if astronaut_id:
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

            if not row:
                return None

            return dict(row)
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"Error querying latest health reading: {exc}")
        return None


def get_active_alerts_context(astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Dict[str, Any]:
    """
    Retrieves recent radiation and health alerts to contextualize assistant answers.
    """
    context: Dict[str, Any] = {
        "radiation_alerts": [],
        "health_alerts": [],
        "total_active_alerts": 0
    }
    try:
        conn = get_db_connection(db_path)
        try:
            # Query recent radiation alerts
            rad_rows = conn.execute("""
                SELECT alert_id, category, severity, alert_type, timestamp, instrument_id,
                       metric_name, metric_value, unit, description, recommendation
                FROM radiation_alerts
                ORDER BY timestamp DESC, id DESC
                LIMIT 5;
            """).fetchall()
            context["radiation_alerts"] = [dict(r) for r in rad_rows]

            # Query recent health alerts
            if astronaut_id:
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
            context["total_active_alerts"] = len(context["radiation_alerts"]) + len(context["health_alerts"])
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

    Enforced Guardrails:
    1. Rejects disease diagnosis requests.
    2. Rejects medication and pharmaceutical prescription requests.
    3. Rejects unauthorized emergency / spacecraft abort commands.
    4. Rejects requests to invent official NASA medical limits.
    """
    lower = query_text.lower().strip()

    # Guardrail 1: Clinical Disease Diagnosis
    # Specifically targets diagnostic questions without intercepting telemetry questions ("Do I have any alerts?")
    diagnosis_patterns = [
        r"\b(diagnose\b|diagnosis|am i suffering from|what disease|what illness)\b",
        r"\b(could i have|do i have) .*(cancer|disease|heart attack|heart disease|condition|illness|stroke)\b",
        r"\bis this (cancer|heart disease|a heart attack|a stroke)\b"
    ]
    for pattern in diagnosis_patterns:
        if re.search(pattern, lower):
            answer = (
                "ASTRA CARE is an informational spaceflight monitoring system and cannot diagnose "
                "diseases, medical conditions, or pathological syndromes.\n\n"
                "Physiological metrics (heart rate, blood pressure, SpO2, and temperature) reflect current "
                "operational telemetry and microgravity adaptation rather than a clinical diagnosis. "
                "If you are experiencing unusual physical symptoms, discomfort, or concerning telemetry readings, "
                "please follow standard mission medical checklists and contact the Mission Flight Surgeon "
                "and Biomedical Engineer (BME) immediately."
            )
            return answer, "safety_guardrail"

    # Guardrail 2: Pharmaceutical Prescription & Medication
    prescription_patterns = [
        r"\b(what (medicine|medication|drug|pills?) should i take|prescribe|can i take (aspirin|ibuprofen|antibiotics|morphine|paracetamol)|give me a prescription)\b"
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
# Domain Knowledge Base & Intent Handlers
# ============================================================================

def handle_radiation_query(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Handles radiation-related queries including latest readings, measurement units,
    dosimetry statistics, space radiation risks, and cumulative exposure.
    """
    lower = query.lower()

    # 1. User asking for their latest radiation reading
    if any(k in lower for k in ["latest radiation", "my radiation", "current radiation", "latest reading", "recent radiation", "radiation reading"]):
        latest = get_latest_radiation_reading(db_path)
        if not latest:
            answer = (
                "No radiation records are currently available in the system database.\n\n"
                "When connected to the radiation module, ASTRA CARE monitors absorbed dose rate (µGy/hr), "
                "dose-equivalent rate (µSv/hr), and particle flux. Please ensure the NASA RadLab archive data "
                "or local sample dataset has been loaded."
            )
            return answer, "project_data", None

        # Build context-aware explanation
        dose_rate = latest.get("absorbed_dose_rate")
        eq_rate = latest.get("dose_equivalent_rate")
        unit_dose = latest.get("absorbed_dose_unit", "µGy/hr")
        unit_eq = latest.get("dose_equivalent_unit", "µSv/hr")
        timestamp = latest.get("timestamp", "N/A")
        detector = latest.get("instrument_id", "Unknown Detector")
        module = latest.get("module") or "ISS Module"
        altitude = latest.get("altitude")

        dose_str = f"{dose_rate:.2f} {unit_dose}" if dose_rate is not None else "Not reported"
        eq_str = f"{eq_rate:.2f} {unit_eq}" if eq_rate is not None else "Not calculated for this detector"
        alt_str = f" at an altitude of {altitude:.1f} km" if altitude is not None else ""

        answer = (
            f"Your latest recorded radiation measurement from detector {detector} ({module}{alt_str}) is:\n"
            f"• Absorbed Dose Rate: {dose_str}\n"
            f"• Dose-Equivalent Rate: {eq_str}\n"
            f"• Measurement Timestamp: {timestamp} UTC\n\n"
            f"What this means:\n"
            f"- Absorbed dose rate ({unit_dose}) represents the physical ionizing energy deposited per unit mass of matter.\n"
            f"- Dose-equivalent ({unit_eq}) weights the absorbed dose by the radiation quality factor (Q) to account for biological impact.\n\n"
            f"Scientific Note: This measurement originates from the NASA RadLab historical scientific repository collected "
            f"aboard the International Space Station (ISS) and represents historical research telemetry rather than live telemetry."
        )
        return answer, "project_data", {"latest_radiation": latest}

    # 2. User asking about radiation units (µGy/hr vs µSv/hr vs flux)
    if any(k in lower for k in ["unit", "ugy", "usv", "µgy", "µsv", "microgray", "microsievert", "gray", "sievert", "flux"]):
        answer = (
            "Space radiation measurements in ASTRA CARE use internationally standardized dosimetry units:\n\n"
            "1. Absorbed Dose Rate (µGy/hr – microGrays per hour):\n"
            "   Measures the physical amount of radiation energy absorbed by matter. One Gray (Gy) equals one Joule "
            "   of radiation energy deposited per kilogram of matter. In Low Earth Orbit, typical baseline rates range "
            "   around 10 to 30 µGy/hr inside shielded ISS modules, increasing significantly when traversing the "
            "   South Atlantic Anomaly (SAA) or during solar particle events.\n\n"
            "2. Dose-Equivalent Rate (µSv/hr – microSieverts per hour):\n"
            "   Measures biological effectiveness. It scales the absorbed dose by a quality factor (Q) that reflects "
            "   how damaging heavy charged particles (like iron ions in Galactic Cosmic Rays) are to living human tissue "
            "   compared to standard gamma radiation.\n\n"
            "3. Particle Flux (particles/(cm²·sr·s)):\n"
            "   Measures the count of ionizing particles passing through a one square centimeter area per steradian "
            "   per second, indicating the intensity of the radiation field.\n\n"
            "Important: ASTRA CARE strictly preserves and separates absorbed dose and dose-equivalent units. "
            "They measure fundamentally different physical properties and should never be combined directly."
        )
        return answer, "knowledge_base", None

    # 3. User asking about radiation alerts / risks / shielding
    if any(k in lower for k in ["radiation alert", "radiation risk", "solar particle", "gcr", "spe", "shielding"]):
        answer = (
            "Space radiation poses long-term and acute risks during deep-space and orbital missions:\n\n"
            "• Galactic Cosmic Rays (GCR): High-energy protons and heavy nuclei originating outside the solar system. "
            "  They produce continuous, penetrating background dose rates.\n"
            "• Solar Particle Events (SPE): Sudden coronal mass ejections that produce intense surges of protons.\n"
            "• South Atlantic Anomaly (SAA): A region where Earth's inner Van Allen belt dips closest to the surface, "
            "  causing periodic spikes during ISS orbits.\n\n"
            "Radiation Alert Guidance:\n"
            "When a radiation alert triggers in ASTRA CARE (such as an elevated dose rate advisory or telemetry gap warning):\n"
            "1. Check the detector module and confirm if the spacecraft is transiting the South Atlantic Anomaly.\n"
            "2. For high-dose alerts, follow mission flight rules: retreat to heavily shielded spacecraft zones "
            "   (e.g., US Lab or sleep stations with polyethylene and water walls).\n"
            "3. Confirm detector status and alert the Mission Flight Control Team."
        )
        return answer, "knowledge_base", None

    # General radiation overview fallback
    answer = (
        "In space missions, radiation monitoring is essential because astronauts operate outside Earth's protective "
        "atmosphere. ASTRA CARE tracks absorbed dose rate in µGy/hr and dose-equivalent rate in µSv/hr using data "
        "from the NASA RadLab archive.\n\n"
        "Monitoring radiation allows flight doctors to assess cumulative mission exposure, verify spacecraft shielding "
        "effectiveness, and provide early warnings during elevated radiation events. For concerning readings, always "
        "refer to the approved mission radiation flight rules and consult the ground team."
    )
    return answer, "knowledge_base", None


def handle_health_query(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Handles queries concerning astronaut vital signs: Heart Rate (BPM), Blood Pressure (mmHg),
    Oxygen Saturation (SpO2 %), and Core Body Temperature (°C).
    """
    lower = query.lower()

    # 1. User asking for their latest health / vitals measurements
    if any(k in lower for k in ["latest health", "my vitals", "my health", "latest vitals", "current vitals", "my reading", "heart rate and blood pressure"]):
        latest = get_latest_health_reading(astronaut_id, db_path)
        if not latest:
            answer = (
                "No astronaut vital sign measurements are currently logged in the database.\n\n"
                "Astronaut vitals can be submitted through the Health Monitoring interface or POST /api/health/measurements. "
                "The system validates heart rate (BPM), blood pressure (mmHg), oxygen saturation (% SpO2), and core temperature (°C)."
            )
            return answer, "project_data", None

        astro = latest.get("astronaut_id", "Crew Member")
        hr = latest.get("heart_rate")
        sys_bp = latest.get("blood_pressure_systolic")
        dia_bp = latest.get("blood_pressure_diastolic")
        spo2 = latest.get("oxygen_saturation")
        temp = latest.get("body_temperature")
        ts = latest.get("timestamp", "N/A")
        classification = latest.get("data_classification", "simulated_demo")

        hr_str = f"{hr:.0f} BPM" if hr is not None else "Not recorded"
        bp_str = f"{sys_bp:.0f}/{dia_bp:.0f} mmHg" if (sys_bp is not None and dia_bp is not None) else "Not recorded"
        spo2_str = f"{spo2:.1f}%" if spo2 is not None else "Not recorded"
        temp_str = f"{temp:.1f} °C" if temp is not None else "Not recorded"

        class_notice = ""
        if classification == "simulated_demo":
            class_notice = "Note: This telemetry is classified as demonstration simulated data ('simulated_demo') and does not represent an actual in-flight medical record."
        elif classification == "historical_study":
            class_notice = "Note: This telemetry originates from an archived aerospace research study ('historical_study')."
        else:
            class_notice = f"Telemetry classification: {classification}."

        answer = (
            f"Here are the latest recorded vitals for {astro} (Timestamp: {ts} UTC):\n"
            f"• Heart Rate: {hr_str}\n"
            f"• Blood Pressure: {bp_str}\n"
            f"• Oxygen Saturation (SpO2): {spo2_str}\n"
            f"• Core Body Temperature: {temp_str}\n\n"
            f"{class_notice}\n\n"
            f"Operational Reminder: In microgravity, cephalad fluid shifts (fluid redistribution toward the head) "
            f"and altered vascular tone can cause natural changes in cardiovascular dynamics. If any vital sign "
            f"feels concerning, follow your mission checklist and contact the Flight Surgeon."
        )
        return answer, "project_data", {"latest_health": latest}

    # 2. Specific vital: Heart Rate
    if any(k in lower for k in ["heart rate", "bpm", "pulse", "tachycardia", "bradycardia"]):
        answer = (
            "Heart Rate Monitoring in Spaceflight (measured in BPM – beats per minute):\n\n"
            "• Resting Baseline: Under standard clinical guidelines (AHA / NASA-STD-3001), nominal resting heart "
            "  rate is typically between 60 and 100 BPM.\n"
            "• Spaceflight Considerations: Upon entering microgravity, the absence of hydrostatic pressure causes "
            "  blood to shift toward the upper body (cephalad fluid shift). Over time, astronauts experience cardiovascular "
            "  deconditioning, which can alter resting pulse and elevate exercise heart rates.\n"
            "• Low Readings (Bradycardia, <50 BPM): Common in endurance-trained astronauts, but severe drops require "
            "  evaluating sensor contact and reporting to medical staff.\n"
            "• Elevated Readings (Tachycardia, >100 BPM resting): May occur due to physical exertion, carbon dioxide "
            "  buildup, dehydration, or stress.\n\n"
            "Safety Guidance: If your resting heart rate remains unusually high or low outside of exercise periods, "
            "verify sensor placement, hydrate, and report to the Mission Flight Surgeon."
        )
        return answer, "knowledge_base", None

    # 3. Specific vital: Blood Pressure
    if any(k in lower for k in ["blood pressure", "systolic", "diastolic", "mmhg", "hypertension", "hypotension"]):
        answer = (
            "Blood Pressure Monitoring in Spaceflight (measured in mmHg – millimeters of mercury):\n\n"
            "• Measurement Components:\n"
            "  - Systolic pressure: The peak arterial pressure when the heart contracts.\n"
            "  - Diastolic pressure: The minimum arterial pressure when the heart relaxes between beats.\n"
            "  - Nominal aerospace benchmark: Typically below 120 mmHg systolic and below 80 mmHg diastolic.\n"
            "• Spaceflight Physiological Effects:\n"
            "  Without gravity pulling blood toward the lower extremities, central venous pressure and carotid artery "
            "  pressures change. The body adapts by reducing blood plasma volume over the first few days of flight.\n"
            "• Hypotension (<90/60 mmHg): May lead to lightheadedness, particularly during post-exercise recovery or "
            "  pre-landing orthostatic stress.\n"
            "• Elevated / Hypertension (>130/80 mmHg): Can be influenced by cabin workload, sleep disruption, or fluid shifts.\n\n"
            "Operational Guidance: Rest for 5 minutes before taking readings and ensure the sensor cuff is positioned at heart level."
        )
        return answer, "knowledge_base", None

    # 4. Specific vital: Oxygen Saturation (SpO2)
    if any(k in lower for k in ["oxygen", "spo2", "saturation", "hypoxia"]):
        answer = (
            "Oxygen Saturation Monitoring (measured in % SpO2 via pulse oximetry):\n\n"
            "• Clinical Meaning: SpO2 measures the percentage of hemoglobin in arterial blood that is carrying oxygen.\n"
            "• Nominal Aerospace Envelope: Typically 95% to 100% under standard spacecraft cabin atmospheric conditions "
            "  (e.g., ISS atmosphere maintained near 14.7 psi with ~21% O2).\n"
            "• Hypoxia Warning (<95% SpO2): Reduced oxygen saturation warrants immediate attention because it can impair "
            "  cognitive performance, reaction time, and vision.\n"
            "• Severe Hypoxia (<90% SpO2): Critical condition requiring immediate cabin atmosphere checks (evaluating "
            "  ambient oxygen partial pressure and CO2 scrubbers) and crew supplemental oxygen protocols.\n\n"
            "Safety Guidance: If your SpO2 reading is low, re-check the sensor probe on a warm finger, breathe normally, "
            "and alert your crewmates and mission control immediately."
        )
        return answer, "knowledge_base", None

    # 5. Specific vital: Body Temperature
    if any(k in lower for k in ["temperature", "body temp", "fever", "celsius", "hypothermia", "hyperthermia"]):
        answer = (
            "Core Body Temperature Monitoring (measured in °C – degrees Celsius):\n\n"
            "• Nominal Range: Typically 36.1°C to 37.2°C (NASA-STD-3001 thermoregulation standard).\n"
            "• Spaceflight Phenomenon ('Space Fever'): In microgravity, convective air cooling does not occur naturally. "
            "  Without gravity-driven air currents, heat dissipation relies strictly on sweat evaporation and forced "
            "  cabin ventilation. Astronauts frequently experience a sustained rise in core body temperature "
            "  (often up to 1°C higher, especially during exercise).\n"
            "• Hypothermia (<35.0°C): Unusually low core temperature, requiring thermal clothing and sensor re-check.\n"
            "• Pyrexia / Elevated (>37.5°C): May indicate physical exertion, heat stress, or physiological response.\n\n"
            "Safety Guidance: Maintain hydration, verify cabin airflow velocity, and report persistent elevated temperature "
            "to the medical team."
        )
        return answer, "knowledge_base", None

    # General vitals overview fallback
    answer = (
        "Astronaut vital signs (Heart Rate, Blood Pressure, SpO2, and Body Temperature) provide essential real-time "
        "insights into how human physiology adapts to the extreme stresses of spaceflight.\n\n"
        "Continuous monitoring enables early detection of cardiovascular deconditioning, hypoxia risks, and thermoregulatory "
        "imbalances. All telemetry is benchmarked against NASA-STD-3001 and clinical guidelines, with clear labeling "
        "distinguishing demonstration data from real sensor feeds."
    )
    return answer, "knowledge_base", None


def handle_alerts_query(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Explains the alert system and summarizes active radiation and health alerts from the database.
    """
    alerts_ctx = get_active_alerts_context(astronaut_id, db_path)
    total = alerts_ctx["total_active_alerts"]
    rad_alerts = alerts_ctx["radiation_alerts"]
    hlth_alerts = alerts_ctx["health_alerts"]

    if total == 0:
        answer = (
            "Currently, there are no active radiation or health alerts logged in the system.\n\n"
            "How the ASTRA CARE Alert System Works:\n"
            "• Radiation Alerts: Triggered on elevated absorbed dose rate (>20 µGy/hr), high-dose events (>50 µGy/hr), "
            "  or telemetry timestamp gaps exceeding safe continuous bounds.\n"
            "• Astronaut Health Alerts: Evaluated against NASA-STD-3001, AHA, and WHO benchmarks across heart rate, "
            "  blood pressure, oxygen saturation, and body temperature.\n"
            "• Severity Levels:\n"
            "  - INFO: Data quality notices, telemetry advisories, or mild baseline variations.\n"
            "  - WARNING: Notable deviations requiring operational attention and monitoring.\n"
            "  - CRITICAL: Severe anomalies requiring prompt crew notification and Flight Surgeon consultation."
        )
        return answer, "project_data", alerts_ctx

    # Format active alert summary
    lines = [f"There are currently {total} alert(s) stored in the mission database:\n"]
    if rad_alerts:
        lines.append("Space Radiation Alerts:")
        for a in rad_alerts[:3]:
            lines.append(f"• [{a.get('severity')}] {a.get('alert_type')}: {a.get('description')} (Action: {a.get('recommendation', 'Consult flight rules')})")
    if hlth_alerts:
        lines.append("\nAstronaut Health Alerts:")
        for h in hlth_alerts[:3]:
            lines.append(f"• [{h.get('severity')}] {h.get('alert_type')}: {h.get('description')} (Action: {h.get('recommendation', 'Notify Flight Surgeon')})")

    lines.append(
        "\nSafe Action Guidance for Crew:\n"
        "1. Never panic. Many alerts arise from transient operational conditions (e.g., exercise, sensor movement).\n"
        "2. Check sensor positioning and repeat the measurement.\n"
        "3. Follow approved Mission Flight Rules and the onboard Medical Checklist.\n"
        "4. Contact the Mission Flight Surgeon and biomedical ground support team."
    )
    answer = "\n".join(lines)
    return answer, "project_data", alerts_ctx


def handle_normal_unusual_unavailable_query(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Explains the difference between normal-looking, unusual, and unavailable readings
    without inventing official astronaut medical thresholds.
    """
    answer = (
        "Understanding Telemetry Status: Normal, Unusual, and Unavailable Readings:\n\n"
        "1. Normal-Looking Readings:\n"
        "   Measurements that fall within expected physiological or environmental ranges during nominal spaceflight "
        "   operations. For example, a resting heart rate between 60–100 BPM, blood pressure below 120/80 mmHg, "
        "   and baseline absorbed radiation doses between 10–30 µGy/hr in shielded ISS modules. Normal readings indicate "
        "   that sensors are functional and the astronaut's body is adapting well to current mission conditions.\n\n"
        "2. Unusual Readings:\n"
        "   Measurements that deviate noticeably from baseline patterns or operational reference benchmarks. "
        "   An unusual reading does NOT automatically mean disease or danger. Common causes include:\n"
        "   • Intense physical exercise (e.g., high heart rate on the T2 cycle ergometer or treadmill).\n"
        "   • Temporary sensor artifact, loose electrode patch, or motion noise.\n"
        "   • Radiation increases during transits through the South Atlantic Anomaly (SAA).\n"
        "   Unusual readings warrant verification, repeating the measurement, and reporting to the Flight Surgeon.\n\n"
        "3. Unavailable Readings:\n"
        "   Situations where data is missing, corrupted, or cannot be measured. This happens during communication "
        "   blackouts (Loss of Signal / LOS), detached sensor leads, depleted wearable battery, or detector maintenance. "
        "   When data is unavailable, ASTRA CARE clearly reports 'Data Unavailable' rather than guessing or fabricating numbers.\n\n"
        "Important Principle: ASTRA CARE never invents official medical thresholds. Demonstration parameters are "
        "simulated guidelines and must never replace published NASA Flight Rules."
    )
    return answer, "knowledge_base", None


def handle_safe_action_guidance_query(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Provides general, safe guidance on what an astronaut should do when an alert appears.
    """
    answer = (
        "General Operational Guidance When an Alert Appears in ASTRA CARE:\n\n"
        "Step 1: Verify Hardware & Sensor Integrity\n"
        "• Check that wearable patches, finger pulse oximeters, or blood pressure cuffs are securely positioned.\n"
        "• Ensure skin contact is clean and free of excessive perspiration or loose leads.\n"
        "• Confirm battery levels and telemetry transmission status.\n\n"
        "Step 2: Contextualize the Measurement\n"
        "• Did the alert follow recent vigorous exercise, Extravehicular Activity (EVA) preparation, or high workload?\n"
        "• For radiation alerts, verify spacecraft position (e.g., transiting the South Atlantic Anomaly) or solar activity.\n\n"
        "Step 3: Consult Mission-Approved Medical Procedures\n"
        "• Open the onboard Crew Health Care System (CHeCS) / Medical Checklist.\n"
        "• Follow established operational flight rules for the specific metric.\n"
        "• For high radiation alerts, move toward designated heavily shielded modules (such as Node 2 or US Lab).\n\n"
        "Step 4: Contact the Mission Medical Team\n"
        "• Establish voice or data contact with the Mission Flight Surgeon and Biomedical Engineer (BME).\n"
        "• Provide the exact measurement value, timestamp, and how you are feeling physically.\n\n"
        "Important: Do not take unprescribed medications or attempt unauthorized equipment alterations without "
        "flight control authorization."
    )
    return answer, "knowledge_base", None


def handle_why_monitoring_matters_query(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """
    Explains why regular health monitoring is critical during space missions.
    """
    answer = (
        "Why Continuous Health & Radiation Monitoring is Critical in Space Missions:\n\n"
        "1. Microgravity Cardiovascular Deconditioning:\n"
        "   In weightlessness, blood and body fluids shift toward the upper body (cephalad fluid shift). The body senses "
        "   this as an apparent excess of fluid and decreases blood plasma volume. Heart muscle mass also decreases "
        "   over time due to reduced workload. Regular monitoring of heart rate and blood pressure helps evaluate "
        "   orthostatic intolerance risks and cardiovascular health.\n\n"
        "2. Cumulative Space Radiation Exposure:\n"
        "   Unlike terrestrial environments protected by Earth's atmosphere and magnetosphere, space travelers are "
        "   exposed to Galactic Cosmic Rays (GCR) and Solar Particle Events (SPE). Tracking absorbed dose (µGy/hr) "
        "   and dose equivalent (µSv/hr) allows flight surgeons to monitor lifetime radiation limits and evaluate "
        "   cancer, cataracts, and tissue risks.\n\n"
        "3. Oxygenation & Atmospheric Safety:\n"
        "   Spacecraft cabins are sealed environments. Monitoring oxygen saturation (SpO2) ensures early detection "
        "   of hypoxia risks from environmental anomalies or spacesuit ventilation issues.\n\n"
        "4. Thermoregulation & 'Space Fever':\n"
        "   Because convective cooling is absent in microgravity, metabolic heat builds up faster during activity. "
        "   Core temperature monitoring prevents heat stress and hyperthermia.\n\n"
        "5. Muscle & Bone Atrophy Prevention:\n"
        "   Astronauts must perform daily countermeasure exercise (ARED, treadmill, cycle). Vitals monitoring "
        "   ensures exercise regimens are safe, effective, and protective against musculoskeletal decay."
    )
    return answer, "knowledge_base", None


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

    Execution Pipeline:
    1. Validation: Ensures message is non-empty.
    2. Safety Guardrails: Checks for diagnostic, pharmaceutical, or unauthorized emergency requests.
    3. Intent Routing & Context Retrieval:
       - Radiation questions (latest reading, units, dose stats, risks)
       - Health vitals questions (latest vitals, HR, BP, SpO2, Temp)
       - Normal vs Unusual vs Unavailable telemetry explanations
       - Alert system explanations and active alert retrieval
       - General safe action guidance
       - Importance of spaceflight health monitoring
    4. Optional External LLM Integration (if GEMINI_API_KEY is configured):
       Enhances prose while strictly maintaining retrieved data context and safety boundaries.
    5. Returns structured ChatResponse.
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

    # Step 2: Intent Routing

    # Case A: Why regular health monitoring is important
    if ("why" in lower or "importance" in lower) and any(k in lower for k in ["monitor", "health", "regular", "vital"]):
        answer, source, data_ctx = handle_why_monitoring_matters_query(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # Case B: Alert queries
    if any(k in lower for k in ["alert", "warning", "alarm", "active alerts", "my alerts"]):
        answer, source, data_ctx = handle_alerts_query(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # Case C: Normal vs unusual vs unavailable telemetry
    if any(k in lower for k in ["normal", "unusual", "unavailable", "difference between normal"]):
        answer, source, data_ctx = handle_normal_unusual_unavailable_query(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # Case D: Safe action guidance / what should an astronaut do
    if any(k in lower for k in ["what should i do", "what should an astronaut do", "what to do", "procedure", "how to respond", "action guidance"]):
        answer, source, data_ctx = handle_safe_action_guidance_query(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # Case E: Radiation specific questions
    if any(k in lower for k in ["radiation", "ugy", "usv", "µgy", "µsv", "dose", "radlab", "sievert", "gray", "cosmic ray", "flux", "microgray", "microsievert"]):
        answer, source, data_ctx = handle_radiation_query(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # Case F: Health vitals specific questions
    if any(k in lower for k in ["health", "vitals", "heart rate", "pulse", "blood pressure", "spo2", "oxygen", "temperature", "temp"]):
        answer, source, data_ctx = handle_health_query(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # Case G: Overall general astronaut assistant introduction / help
    stats = get_db_statistics(db_path)
    answer = (
        "Hello, astronaut. I am the ASTRA CARE AI Health & Radiation Assistant.\n\n"
        "I can help you monitor and understand your mission telemetry in simple, clear language:\n"
        "• Space Radiation: Explain your latest absorbed dose (µGy/hr), equivalent dose (µSv/hr), and measurement units.\n"
        "• Astronaut Vitals: Explain heart rate (BPM), blood pressure (mmHg), oxygen saturation (SpO2 %), and body temperature (°C).\n"
        "• Telemetry Status: Explain normal-looking, unusual, or unavailable readings without inventing unofficial thresholds.\n"
        "• Mission Alerts: Review active safety alerts and provide safe operational guidance.\n"
        "• Space Adaptation: Explain microgravity physiological changes and the importance of continuous monitoring.\n\n"
        f"Current Mission Database Status: {stats.get('stored_radiation_records_count', 0)} radiation records and "
        f"{stats.get('stored_health_records_count', 0)} crew health vitals stored in SQLite.\n\n"
        "How can I assist your mission today? (e.g., 'Explain my latest radiation reading', 'What does my heart rate mean?', 'Do I have any alerts?')"
    )
    return ChatResponse(
        answer=answer,
        source="knowledge_base",
        status="success",
        data_context={"system_stats": stats},
        disclaimer=ASSISTANT_DISCLAIMER
    )
