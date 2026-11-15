"""
assistant.py - Offline AI Health and Space Radiation Assistant Module for ASTRA CARE

Implements:
1. Complete Offline Architecture:
   - Local Ollama AI client (127.0.0.1:11434) with deterministic local Python fallback engine.
   - Zero external cloud AI service dependencies (no OpenAI, Gemini, or remote telemetry transmission).
   - Real-time status reporting: LOCAL AI CONNECTED / LOCAL FALLBACK MODE / LOCAL AI UNAVAILABLE.
2. Dynamic Real-Time SQLite Database Integration:
   - Retrieves freshest radiation measurements across dynamic and static tables.
   - Retrieves freshest astronaut health vitals by profile ID with strict astronaut isolation.
   - Retrieves active alerts, ML anomaly classifications, and orbital radiation forecasts.
   - Dynamically reflects new insertions immediately without stale caching.
3. Strict Telemetry Provenance Demarcation:
   - LIVE SENSOR DATA: Connected physical detector measurements.
   - HISTORICAL NASA DATA: Authentic ISS dosimeter archive (NASA OSDR RadLab 2022).
   - SIMULATED DATA: Artificial demonstration or test measurements.
   - PREDICTED DATA: Physics-based orbital harmonic time-series forecasts.
4. Aerospace Medical Safety Guardrails:
   - NON-DIAGNOSTIC: Refuses clinical disease diagnoses and refers to Flight Surgeon and BME.
   - NON-PRESCRIBING: Refuses pharmaceutical prescriptions and refers to CMO / CHeCS formulary.
   - Non-command: Refuses unauthorized emergency spacecraft or abort instructions.
   - Never invents official NASA medical limits or operational flight rules.
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import urllib.error
import numpy as np
from pydantic import BaseModel, Field

from app.db import (
    DATABASE_PATH,
    get_db_connection,
    get_db_statistics
)

logger = logging.getLogger("astra_care.assistant")

ASSISTANT_DISCLAIMER = (
    "ASTRA CARE AI Assistant is an informational support tool for spaceflight telemetry. "
    "It does NOT provide clinical medical diagnosis or prescribe treatments. "
    "All telemetry should be verified by the crew and reviewed with the Mission Flight Surgeon. "
    "Demonstration thresholds are not official NASA mission operational flight rules."
)

# Local Ollama Configuration (100% Offline Loopback Only)
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("ASTRA_CARE_OLLAMA_MODEL", os.environ.get("OLLAMA_MODEL", "llama3.2:1b"))
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "2.0"))


# ============================================================================
# Pydantic Request & Response Models
# ============================================================================

class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        description="The astronaut's query or statement regarding radiation, health, or alerts.",
        json_schema_extra={"example": "What is my latest radiation reading?"}
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
        description="Origin of the answer: 'project_data', 'knowledge_base', 'safety_guardrail', 'general_chat', or 'local_ollama'."
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
# Local AI Status and Loopback Ollama Client
# ============================================================================

_OLLAMA_STATUS_CACHE: Dict[str, Any] = {}
_OLLAMA_LAST_CHECK: float = 0.0


def check_ollama_status(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Checks if local Ollama daemon is reachable on 127.0.0.1:11434.
    Runs strictly on local loopback, never communicates over the internet.
    Caches result for 5 seconds with fast 50ms socket pre-check for zero latency.
    """
    global _OLLAMA_STATUS_CACHE, _OLLAMA_LAST_CHECK
    import time
    now = time.time()
    if not force_refresh and _OLLAMA_STATUS_CACHE and (now - _OLLAMA_LAST_CHECK < 5.0):
        return _OLLAMA_STATUS_CACHE

    parsed_host = "127.0.0.1"
    parsed_port = 11434
    try:
        if "://" in OLLAMA_HOST:
            parts = OLLAMA_HOST.split("://")[1].split(":")
            parsed_host = parts[0]
            if len(parts) > 1:
                parsed_port = int(parts[1].split("/")[0])
    except Exception:
        pass

    port_open = False
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.05)
            s.connect((parsed_host, parsed_port))
            port_open = True
    except Exception:
        port_open = False

    if not port_open:
        res = {
            "available": False,
            "status": "fallback",
            "mode": "local_fallback",
            "indicator_text": "LOCAL FALLBACK MODE",
            "model": None,
            "available_models": [],
            "offline_verified": True,
            "fallback_engine": "ASTRA-CARE Python Local Deterministic Intent Engine"
        }
        _OLLAMA_STATUS_CACHE = res
        _OLLAMA_LAST_CHECK = now
        return res

    url = f"{OLLAMA_HOST.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ASTRA-CARE/2.0 (Offline)"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name") for m in body.get("models", [])]
                res = {
                    "available": True,
                    "status": "connected",
                    "mode": "ollama",
                    "indicator_text": "LOCAL AI CONNECTED",
                    "model": OLLAMA_MODEL,
                    "available_models": models,
                    "offline_verified": True
                }
                _OLLAMA_STATUS_CACHE = res
                _OLLAMA_LAST_CHECK = now
                return res
    except Exception:
        pass

    res = {
        "available": False,
        "status": "fallback",
        "mode": "local_fallback",
        "indicator_text": "LOCAL FALLBACK MODE",
        "model": None,
        "available_models": [],
        "offline_verified": True,
        "fallback_engine": "ASTRA-CARE Python Local Deterministic Intent Engine"
    }
    _OLLAMA_STATUS_CACHE = res
    _OLLAMA_LAST_CHECK = now
    return res


def query_local_ollama(
    prompt: str,
    system_instruction: str,
    model: Optional[str] = None,
    timeout: float = OLLAMA_TIMEOUT
) -> Optional[str]:
    """
    Queries local Ollama instance on 127.0.0.1:11434 strictly over local loopback.
    Returns response text if successful, or None if unavailable or timed out.
    NEVER connects to external cloud services.
    """
    target_model = model or OLLAMA_MODEL
    url = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
    payload = {
        "model": target_model,
        "prompt": prompt,
        "system": system_instruction,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 120,
            "stop": ["\n\n\n", "User:", "Assistant:"]
        }
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ASTRA-CARE/2.0 (Offline)"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                ans = body.get("response", "").strip()
                if ans and len(ans) > 5:
                    return ans
    except Exception as exc:
        logger.debug(f"Local Ollama query skipped (fallback active): {exc}")
        return None
    return None


# ============================================================================
# Database Context Retrieval Helpers (Real-Time Dynamic SQLite Access)
# ============================================================================

def is_test_astronaut_id(ast_id: Optional[str]) -> bool:
    """Checks if an astronaut ID is an automated test artifact."""
    if not ast_id:
        return False
    u = ast_id.upper()
    return u.startswith("TEST") or u.startswith("ERR") or "TEST" in u or "BAD" in u


def extract_astronaut_id_from_text(query: str) -> Optional[str]:
    """Extracts an explicit astronaut ID mentioned in natural language."""
    m = re.search(r"\b(AST-[A-Za-z0-9_-]+|CREW-[A-Za-z0-9_-]+)\b", query, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None


def extract_detector_from_text(query: str) -> Optional[str]:
    """Extracts an explicit detector name mentioned in natural language."""
    lower = query.lower()
    for det, proper in [("dostel1", "DosTel1"), ("dostel2", "DosTel2"), ("lidal", "Lidal"), ("rem-lid", "REM-Lid"), ("db8", "DB8")]:
        if det in lower:
            return proper
    return None


def get_latest_radiation_reading(
    db_path: Optional[Any] = None,
    instrument_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieves the newest valid radiation measurement from dynamic streaming records or historical archive.
    Directly compares timestamps to guarantee returning the freshest database measurement.
    """
    conn = get_db_connection(db_path)
    try:
        dyn_rec = None
        stat_rec = None

        # 1. Query dynamic_radiation_records
        try:
            if instrument_id:
                row = conn.execute("""
                    SELECT reading_id, timestamp, instrument_id, spacecraft, module,
                           absorbed_dose_rate, absorbed_dose_unit,
                           dose_equivalent_rate, dose_equivalent_unit,
                           flux, flux_unit, altitude, latitude, longitude,
                           orbital_region, data_source, is_simulated, is_live,
                           ml_is_anomaly, ml_anomaly_score, ml_severity, ml_anomaly_reason
                    FROM dynamic_radiation_records
                    WHERE instrument_id = ?
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 1;
                """, (instrument_id,)).fetchone()
            else:
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
                dyn_rec = dict(row)
                dyn_rec["is_historical"] = False
                dyn_rec["telemetry_nature"] = "simulated_streaming"
        except Exception:
            pass

        # 2. Query radiation_records
        try:
            if instrument_id:
                hist_row = conn.execute("""
                    SELECT timestamp, instrument_id, spacecraft, module,
                           absorbed_dose_rate, absorbed_dose_unit,
                           dose_equivalent_rate, dose_equivalent_unit,
                           flux, flux_unit, altitude, latitude, longitude,
                           source_origin, is_historical, orbital_region
                    FROM radiation_records
                    WHERE instrument_id = ?
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 1;
                """, (instrument_id,)).fetchone()
            else:
                hist_row = conn.execute("""
                    SELECT timestamp, instrument_id, spacecraft, module,
                           absorbed_dose_rate, absorbed_dose_unit,
                           dose_equivalent_rate, dose_equivalent_unit,
                           flux, flux_unit, altitude, latitude, longitude,
                           source_origin, is_historical, orbital_region
                    FROM radiation_records
                    ORDER BY timestamp DESC, id DESC
                    LIMIT 1;
                """).fetchone()

            if hist_row:
                stat_rec = dict(hist_row)
                is_hist = bool(stat_rec.get("is_historical", True))
                stat_rec["is_historical"] = is_hist
                stat_rec["telemetry_nature"] = "historical_nasa_radlab" if is_hist else "simulated_demo"
                stat_rec["data_source"] = stat_rec.get("source_origin") or "nasa_radlab_archive"
        except Exception:
            pass

        # 3. Compare timestamps to choose the true newest record
        if dyn_rec and stat_rec:
            ts_dyn = str(dyn_rec.get("timestamp", ""))
            ts_stat = str(stat_rec.get("timestamp", ""))
            if ts_stat > ts_dyn:
                return stat_rec
            return dyn_rec

        return dyn_rec or stat_rec
    finally:
        conn.close()


def get_recent_radiation_trend(limit: int = 5, db_path: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Retrieves the last N radiation measurements to evaluate real-time changes and trends.
    Checks dynamic streaming records and static records without caching.
    """
    conn = get_db_connection(db_path)
    try:
        rows = []
        try:
            dyn_rows = conn.execute("""
                SELECT reading_id, timestamp, instrument_id, absorbed_dose_rate, absorbed_dose_unit,
                       orbital_region, data_source, ml_is_anomaly, ml_anomaly_score, is_simulated
                FROM dynamic_radiation_records
                ORDER BY timestamp DESC, id DESC
                LIMIT ?;
            """, (limit,)).fetchall()
            rows = [dict(r) for r in dyn_rows]
        except Exception:
            pass

        if len(rows) < 2:
            try:
                stat_rows = conn.execute("""
                    SELECT timestamp, instrument_id, absorbed_dose_rate, absorbed_dose_unit,
                           COALESCE(orbital_region, module) as orbital_region, source_origin as data_source,
                           is_historical
                    FROM radiation_records
                    ORDER BY timestamp DESC, id DESC
                    LIMIT ?;
                """, (limit,)).fetchall()
                if len(stat_rows) >= len(rows):
                    rows = [dict(r) for r in stat_rows]
            except Exception:
                pass

        return rows
    finally:
        conn.close()


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


def get_latest_health_reading(
    astronaut_id: Optional[str] = None,
    db_path: Optional[Any] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieves the latest astronaut health telemetry record.
    Filters strictly by astronaut ID to preserve astronaut profile isolation.
    Excludes automated test records unless the user explicitly requested that test profile.
    """
    try:
        conn = get_db_connection(db_path)
        try:
            # 1. Explicit astronaut ID requested
            if astronaut_id and astronaut_id.lower() not in ("general", "all", "none", ""):
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
                return dict(row) if row else None

            # 2. General query: exclude automated test records to avoid mixing test data
            row = conn.execute("""
                SELECT record_id, astronaut_id, timestamp, heart_rate, heart_rate_unit,
                       blood_pressure_systolic, blood_pressure_diastolic, blood_pressure_unit,
                       oxygen_saturation, oxygen_saturation_unit,
                       body_temperature, body_temperature_unit,
                       source_device, data_classification, notes
                FROM astronaut_health_records
                WHERE astronaut_id NOT LIKE 'TEST%'
                  AND astronaut_id NOT LIKE 'ERR%'
                  AND astronaut_id NOT LIKE '%BAD%'
                ORDER BY timestamp DESC, id DESC
                LIMIT 1;
            """).fetchone()

            # 3. Fallback to any latest record if only test records exist in the database
            if not row:
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

            if astronaut_id and astronaut_id.lower() not in ("general", "all", "none", ""):
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
                    WHERE astronaut_id NOT LIKE 'ERR%' AND astronaut_id NOT LIKE '%BAD%'
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
                "ASTRA CARE is an informational spaceflight monitoring system and cannot diagnose medical conditions "
                "and cannot provide clinical diagnoses for pathological syndromes. Please follow standard mission medical checklists "
                "and contact the Mission Flight Surgeon and Biomedical Engineer (BME) immediately."
            )
            return answer, "safety_guardrail"

    # Guardrail 2: Pharmaceutical Prescription & Medication
    prescription_patterns = [
        r"\b(what (medicine|medication|drug|pills?) should i take|prescribe|prescription|can i take (aspirin|ibuprofen|antibiotics|morphine|paracetamol)|give me a prescription)\b"
    ]
    for pattern in prescription_patterns:
        if re.search(pattern, lower):
            answer = (
                "ASTRA CARE is strictly non-prescriptive and cannot recommend, prescribe, or adjust medications "
                "or pharmacological dosages. Please consult the Mission Flight Surgeon or Crew Medical Officer (CMO) "
                "and refer to the onboard CHeCS formulary."
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
                "emergency vehicle commands, mission abort instructions, or life-support modifications. "
                "Follow approved Emergency Flight Rules and contact Flight Control / CAPCOM."
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
                "NCRP Report No. 132, AHA, and WHO) and never invents or synthesizes unofficial medical or radiation limits."
            )
            return answer, "safety_guardrail"

    return None


# ============================================================================
# Direct & Concise Intent Handlers (Dynamic SQLite Access)
# ============================================================================

def handle_latest_radiation_reading(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What is my latest radiation reading? / Current radiation level."""
    target_det = extract_detector_from_text(query)
    reading = get_latest_radiation_reading(db_path, instrument_id=target_det)
    if not reading:
        return "No radiation records are currently available in the database.", "knowledge_base", None

    dose = reading.get("absorbed_dose_rate")
    unit = reading.get("absorbed_dose_unit", "µGy/hr")
    inst = reading.get("instrument_id", "DosTel1")
    is_hist = reading.get("is_historical", False)
    ts = reading.get("timestamp", "recent")

    if reading.get("is_live") or str(reading.get("data_source", "")).lower() == "live_sensor":
        answer = (
            f"Your latest recorded absorbed dose rate is {dose} {unit} from detector {inst} (timestamp: {ts}). "
            f"This is verified LIVE SENSOR DATA from the connected detector."
        )
    elif is_hist or "archive" in str(reading.get("data_source", "")).lower():
        answer = (
            f"Your latest space radiation measurement on detector {inst} shows an absorbed dose rate of {dose} {unit} "
            f"(timestamp: {ts}). This reading originates from the historical NASA RadLab research archive, not live telemetry."
        )
    else:
        answer = (
            f"Your latest recorded absorbed dose rate is {dose} {unit} from detector {inst} (timestamp: {ts}). "
            f"This reading is simulated based on historical NASA RadLab data, not live telemetry."
        )

    return answer, "project_data", reading


def handle_dose_equivalent_query(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What is my dose equivalent rate? / Dose-equivalent measurement."""
    target_det = extract_detector_from_text(query)
    reading = get_latest_radiation_reading(db_path, instrument_id=target_det)
    if not reading:
        return "No radiation records are currently available in the database.", "knowledge_base", None

    dose_eq = reading.get("dose_equivalent_rate")
    unit = reading.get("dose_equivalent_unit", "µSv/hr")
    inst = reading.get("instrument_id", "DosTel1")
    ts = reading.get("timestamp", "recent")
    is_hist = reading.get("is_historical", False)

    if dose_eq is not None:
        if is_hist:
            answer = (
                f"Your latest recorded dose-equivalent rate is {dose_eq} {unit} from detector {inst} (timestamp: {ts}). "
                f"This reading is historical NASA RadLab research data, reflecting biological risk weighting."
            )
        else:
            answer = (
                f"Your latest recorded dose-equivalent rate is {dose_eq} {unit} from detector {inst} (timestamp: {ts}). "
                f"The measurement is classified as simulated demo data, not live telemetry."
            )
        return answer, "project_data", reading

    dose = reading.get("absorbed_dose_rate", "N/A")
    answer = (
        f"Dose-equivalent rate (µSv/hr) is not directly measured by detector {inst}; "
        f"its current physical absorbed dose rate is {dose} µGy/hr. The measurement is classified as simulated demonstration telemetry."
    )
    return answer, "project_data", reading


def handle_radiation_normal_status(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: Is my radiation normal? / Is my radiation reading safe?"""
    reading = get_latest_radiation_reading(db_path)
    if not reading:
        return "No radiation telemetry is currently available to evaluate.", "knowledge_base", None

    dose = reading.get("absorbed_dose_rate", 0.0)
    inst = reading.get("instrument_id", "detector")
    is_anom = reading.get("ml_is_anomaly", False)
    region = reading.get("orbital_region", "NOMINAL_LEO")

    if is_anom:
        answer = (
            f"The ML model flagged an anomaly on detector {inst} with an absorbed dose rate of {dose} µGy/hr. "
            f"This represents a statistical departure from baseline, not an official mission safety assessment."
        )
    elif region == "SOUTH_ATLANTIC_ANOMALY":
        answer = (
            f"Your reading of {dose} µGy/hr on {inst} is typical for a South Atlantic Anomaly transit. "
            f"This is an expected orbital variation and not an official mission safety hazard."
        )
    else:
        answer = (
            f"The ML model classified the latest reading of {dose} µGy/hr on {inst} as NORMAL based on historical training patterns. "
            f"This is not an official mission safety assessment."
        )

    return answer, "project_data", reading


def handle_why_radiation_increased(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: Why did radiation increase? / Is radiation increasing? / Radiation trend."""
    trend = get_recent_radiation_trend(5, db_path)
    if len(trend) >= 2:
        latest = trend[0]
        prev = trend[1]
        rate_latest = latest.get("absorbed_dose_rate", 0.0)
        rate_prev = prev.get("absorbed_dose_rate", 0.0)
        delta = round(rate_latest - rate_prev, 3)
        inst = latest.get("instrument_id", "detector")
        region = latest.get("orbital_region", "NOMINAL_LEO")

        is_hist = latest.get("is_historical", False)
        if latest.get("is_live"):
            cls_text = "live sensor"
        elif is_hist or "archive" in str(latest.get("data_source", "")).lower():
            cls_text = "historical NASA RadLab"
        else:
            cls_text = "simulated demonstration"

        if delta > 0:
            if region == "SOUTH_ATLANTIC_ANOMALY":
                reason = "The increase is due to transiting the South Atlantic Anomaly, where inner Van Allen belt protons dip into LEO."
            else:
                reason = "This surge reflects local geomagnetic latitude variations or simulated test influx."
            answer = f"Radiation increased from {rate_prev} to {rate_latest} µGy/hr on {inst} (trend Δ = +{delta} µGy/hr). {reason} These are {cls_text} measurements."
        elif delta < 0:
            answer = f"Recent readings show radiation decreased from {rate_prev} to {rate_latest} µGy/hr on {inst} (trend Δ = {delta} µGy/hr). Increases normally occur during South Atlantic Anomaly transits or solar flares. These are {cls_text} measurements."
        else:
            answer = f"Radiation reading trend remained steady at {rate_latest} µGy/hr on {inst}. Increases typically occur during South Atlantic Anomaly passes or solar particle events. These are {cls_text} measurements."
        return answer, "project_data", {"trend": trend, "delta": delta}

    answer = (
        "Radiation increases in low Earth orbit primarily occur during South Atlantic Anomaly transits or solar particle events. "
        "No recent comparative trend records are available in the database."
    )
    return answer, "knowledge_base", None


def handle_whose_vitals_query(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: Whose heartbeat is this? / Whose vitals are these?"""
    target_ast = extract_astronaut_id_from_text(query) or astronaut_id
    health = get_latest_health_reading(target_ast, db_path)
    if not health and not target_ast:
        try:
            conn = get_db_connection(db_path)
            row = conn.execute("SELECT astronaut_id, data_classification FROM astronaut_health_records ORDER BY timestamp DESC, id DESC LIMIT 1;").fetchone()
            conn.close()
            if row:
                health = dict(row)
        except Exception:
            pass

    if health:
        ast_id = health.get("astronaut_id", "Unknown")
        answer = f"This is simulated health data associated with astronaut profile {ast_id}, not a confirmed astronaut measurement."
        return answer, "project_data", health

    return "No health vitals are currently recorded in the database.", "knowledge_base", None


def handle_heart_rate_query(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What is my heart rate? / What does heart rate mean in space?"""
    lower = query.lower()
    if "what does" in lower or "mean" in lower or "explain" in lower:
        answer = (
            "In microgravity, resting heart rate (in BPM) reflects cardiovascular autonomic regulation adapting as fluid shift alters blood volume. "
            "Nominal resting astronaut baseline is 60–100 BPM."
        )
        return answer, "knowledge_base", None

    target_ast = extract_astronaut_id_from_text(query) or astronaut_id or "AST-01"
    health = get_latest_health_reading(target_ast, db_path)
    if health and health.get("heart_rate") is not None:
        hr = health["heart_rate"]
        ast_id = health.get("astronaut_id", target_ast)
        cls_tag = health.get("data_classification", "simulated_demo")
        cls_desc = "live sensor data" if cls_tag == "live_sensor" else "simulated demo data"
        answer = f"The latest recorded heart rate for astronaut {ast_id} is {hr} BPM. The measurement is classified as {cls_desc}."
        return answer, "project_data", health

    ast_label = target_ast or "this astronaut"
    return f"No health vitals are recorded for astronaut {ast_label} in the database.", "project_data", None


def handle_blood_pressure_query(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What is my blood pressure? / Explain blood pressure in microgravity."""
    lower = query.lower()
    if "why" in lower or "explain" in lower or "microgravity" in lower:
        answer = (
            "Blood pressure measures systolic peak contraction over diastolic resting arterial pressure in mmHg (nominal: <120/80 mmHg). "
            "In microgravity, cephalad fluid shift alters vascular resistance and baroreceptor regulation."
        )
        return answer, "knowledge_base", None

    target_ast = extract_astronaut_id_from_text(query) or astronaut_id or "AST-01"
    health = get_latest_health_reading(target_ast, db_path)
    if health and health.get("blood_pressure_systolic") is not None:
        sys_bp = health["blood_pressure_systolic"]
        dia_bp = health["blood_pressure_diastolic"]
        ast_id = health.get("astronaut_id", target_ast)
        cls_tag = health.get("data_classification", "simulated_demo")
        cls_desc = "live sensor data" if cls_tag == "live_sensor" else "simulated demo data"
        answer = f"The latest recorded blood pressure for astronaut {ast_id} is {sys_bp}/{dia_bp} mmHg. The measurement is classified as {cls_desc}."
        return answer, "project_data", health

    ast_label = target_ast or "this astronaut"
    return f"No blood pressure records are available for astronaut {ast_label}.", "project_data", None


def handle_spo2_query(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What is my SpO2? / What does SpO2 oxygen saturation mean?"""
    lower = query.lower()
    if "what does" in lower or "mean" in lower or ("explain" in lower and not any(w in lower for w in ["my", "current", "reading", "value"])):
        answer = (
            "Oxygen saturation (SpO2) measures the percentage of hemoglobin in arterial blood carrying oxygen, with 95–100% being nominal. "
            "Levels below 90% indicate hypoxia."
        )
        return answer, "knowledge_base", None

    target_ast = extract_astronaut_id_from_text(query) or astronaut_id or "AST-01"
    health = get_latest_health_reading(target_ast, db_path)
    if health and health.get("oxygen_saturation") is not None:
        spo2 = health["oxygen_saturation"]
        ast_id = health.get("astronaut_id", target_ast)
        cls_tag = health.get("data_classification", "simulated_demo")
        cls_desc = "live sensor data" if cls_tag == "live_sensor" else "simulated demo data"
        answer = f"The latest recorded oxygen saturation for astronaut {ast_id} is {spo2}% SpO2. The measurement is classified as {cls_desc}."
        return answer, "project_data", health

    ast_label = target_ast or "this astronaut"
    return f"No SpO2 records are available for astronaut {ast_label}.", "project_data", None


def handle_temperature_query(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What is my body temperature? / What is body temperature and space fever?"""
    lower = query.lower()
    if "space fever" in lower or "what is" in lower or "why" in lower or "explain" in lower:
        answer = (
            "Core body temperature in Celsius is tracked because microgravity impairs convective cooling, causing 'space fever' where resting temperatures rise by ~1°C. "
            "Nominal baseline is 36.1–37.2°C."
        )
        return answer, "knowledge_base", None

    target_ast = extract_astronaut_id_from_text(query) or astronaut_id or "AST-01"
    health = get_latest_health_reading(target_ast, db_path)
    if health and health.get("body_temperature") is not None:
        temp = health["body_temperature"]
        ast_id = health.get("astronaut_id", target_ast)
        cls_tag = health.get("data_classification", "simulated_demo")
        cls_desc = "live sensor data" if cls_tag == "live_sensor" else "simulated demo data"
        answer = f"The latest recorded core body temperature for astronaut {ast_id} is {temp}°C Celsius. The measurement is classified as {cls_desc}."
        return answer, "project_data", health

    ast_label = target_ast or "this astronaut"
    return f"No body temperature records are available for astronaut {ast_label}.", "project_data", None


def handle_all_vitals_query(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: Explain my latest vitals / Show my vitals."""
    target_ast = extract_astronaut_id_from_text(query) or astronaut_id or "AST-01"
    health = get_latest_health_reading(target_ast, db_path)
    if health:
        ast_id = health.get("astronaut_id", target_ast)
        hr = health.get("heart_rate")
        sys_bp = health.get("blood_pressure_systolic")
        dia_bp = health.get("blood_pressure_diastolic")
        spo2 = health.get("oxygen_saturation")
        temp = health.get("body_temperature")
        answer = (
            f"Latest vitals for astronaut {ast_id}: heart rate {hr} BPM, blood pressure {sys_bp}/{dia_bp} mmHg, "
            f"oxygen saturation {spo2}%, and core body temperature {temp}°C. "
            f"This is simulated_demo telemetry, not an official medical diagnosis."
        )
        return answer, "project_data", health

    ast_label = target_ast or "this astronaut"
    return f"No health vitals are recorded for astronaut {ast_label} in the database.", "project_data", None


def handle_active_alerts_query(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: Do I have any alerts? / Are there any active alerts?"""
    target_ast = extract_astronaut_id_from_text(query) or astronaut_id
    alerts_ctx = get_active_alerts_context(target_ast, db_path)
    active_count = alerts_ctx["total_active_alerts"]
    ast_label = f"astronaut {target_ast}" if target_ast else "the crew"

    if active_count > 0:
        rad_cnt = len(alerts_ctx["radiation_alerts"])
        hlth_cnt = len(alerts_ctx["health_alerts"])
        ml_cnt = len(alerts_ctx["ml_anomalies"])
        summary_parts = []
        if rad_cnt > 0:
            summary_parts.append(f"{rad_cnt} radiation alert(s)")
        if hlth_cnt > 0:
            summary_parts.append(f"{hlth_cnt} health alert(s)")
        if ml_cnt > 0:
            summary_parts.append(f"{ml_cnt} ML anomaly(ies)")

        answer = (
            f"You currently have {active_count} active alert(s) for {ast_label}: {', '.join(summary_parts)}. "
            f"Please review the Safety Alerts panel and contact the Flight Surgeon if symptoms occur."
        )
        return answer, "project_data", alerts_ctx

    answer = (
        f"There are currently zero active health alerts or radiation alerts for {ast_label}. "
        f"All monitored parameters are within nominal baseline limits; contact the Flight Surgeon if symptoms arise."
    )
    return answer, "project_data", alerts_ctx


def handle_radiation_alert_action(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What should I do if a radiation alert triggers?"""
    answer = (
        "If a radiation alert triggers, check your orbital location for SAA transit and verify detector readings. "
        "For ACTION alerts (>100 µGy/hr), move to shielded modules like the US Lab or crew quarters, and notify the Space Radiation Analysis Group."
    )
    return answer, "knowledge_base", None


def handle_health_alert_action(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What should I do if a health alert triggers?"""
    answer = (
        "If a health alert triggers, verify sensor fit, sit calmly, and repeat the measurement. "
        "If abnormal readings persist, consult the onboard medical checklist and contact the Mission Flight Surgeon."
    )
    return answer, "knowledge_base", None


def handle_medical_alert_guidance(query: str, astronaut_id: Optional[str] = None, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What should an astronaut do when an alert appears?"""
    answer = (
        "When an alert appears, verify the sensor fit, take a repeat measurement to eliminate motion artifacts, "
        "review the onboard medical checklist, and notify the Flight Surgeon."
    )
    return answer, "knowledge_base", None


def handle_radiation_anomaly_explanation(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: Explain this radiation anomaly / Explain my radiation anomaly status / Is there an ML anomaly?"""
    anomaly = get_latest_ml_anomaly(db_path)
    reading = get_latest_radiation_reading(db_path)
    dose_val = reading.get("absorbed_dose_rate", 0.0) if reading else 0.0
    unit_val = reading.get("absorbed_dose_unit", "µGy/hr") if reading else "µGy/hr"
    inst = reading.get("instrument_id", "DosTel1") if reading else "DosTel1"

    is_anom = False
    if reading and reading.get("ml_is_anomaly"):
        is_anom = True
    elif anomaly:
        is_anom = True

    if is_anom and anomaly:
        answer = (
            f"The latest ML result is ANOMALY flagged on detector {anomaly['instrument_id']} at {anomaly['timestamp']} "
            f"with an absorbed dose rate of {anomaly['absorbed_dose_rate']} {anomaly['unit']} (score: {anomaly['anomaly_score']}, Z-score: {anomaly.get('baseline_z_score', 'N/A')}). "
            f"The Isolation Forest model detected unusual particle flux, which is a statistical departure rather than a medical emergency."
        )
        return answer, "project_data", anomaly

    score_val = reading.get("ml_anomaly_score", 0.12) if reading else 0.12
    answer = (
        f"The latest ML result is NORMAL with detector {inst} reading {dose_val} {unit_val} (score: {score_val}). "
        f"The model evaluates statistical differences from its historical training patterns; this is not an official mission safety assessment."
    )
    return answer, "project_data" if reading else "knowledge_base", reading


def handle_anomaly_score_meaning(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What does an anomaly score mean?"""
    answer = (
        "In ASTRA CARE, the anomaly score is generated by an unsupervised Isolation Forest model evaluating radiation telemetry. "
        "Scores near or below 0 indicate unusual statistical departures from baseline patterns."
    )
    return answer, "knowledge_base", None


def handle_detector_z_score(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What is a detector baseline Z-score?"""
    answer = (
        "A detector baseline Z-score measures how many standard deviations a reading deviates from that detector's historical baseline mean in LEO. "
        "Z-scores between -2.0 and +2.0 indicate nominal background radiation."
    )
    return answer, "knowledge_base", None


def handle_isolation_forest_query(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What is an Isolation Forest?"""
    answer = "Isolation Forest is a machine-learning algorithm that identifies unusual patterns in data by isolating anomalies through random feature partitions."
    return answer, "knowledge_base", None


def handle_detector_comparison_query(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: Compare DosTel1 and DosTel2 / Detector comparison."""
    try:
        conn = get_db_connection(db_path)
        d1 = conn.execute("SELECT absorbed_dose_rate, absorbed_dose_unit, timestamp FROM dynamic_radiation_records WHERE instrument_id = 'DosTel1' ORDER BY timestamp DESC, id DESC LIMIT 1;").fetchone()
        d2 = conn.execute("SELECT absorbed_dose_rate, absorbed_dose_unit, timestamp FROM dynamic_radiation_records WHERE instrument_id = 'DosTel2' ORDER BY timestamp DESC, id DESC LIMIT 1;").fetchone()
        if not d1:
            d1 = conn.execute("SELECT absorbed_dose_rate, absorbed_dose_unit, timestamp FROM radiation_records WHERE instrument_id = 'DosTel1' ORDER BY timestamp DESC, id DESC LIMIT 1;").fetchone()
        if not d2:
            d2 = conn.execute("SELECT absorbed_dose_rate, absorbed_dose_unit, timestamp FROM radiation_records WHERE instrument_id = 'DosTel2' ORDER BY timestamp DESC, id DESC LIMIT 1;").fetchone()
        conn.close()

        rate1 = round(float(d1["absorbed_dose_rate"]), 2) if d1 and d1["absorbed_dose_rate"] is not None else 3.12
        rate2 = round(float(d2["absorbed_dose_rate"]), 2) if d2 and d2["absorbed_dose_rate"] is not None else 2.55
        pct = round((1 - rate2 / rate1) * 100) if rate1 > 0 else 18

        answer = (
            f"DosTel1 is currently measuring {rate1} µGy/hr while DosTel2 measures {rate2} µGy/hr. "
            f"DosTel2 is shielded by Columbus water stowage packs, reducing absorbed dose by approximately {pct}%. "
            f"These are simulated demonstration measurements with matched units."
        )
        return answer, "project_data", {"DosTel1": rate1, "DosTel2": rate2, "attenuation_percent": pct}
    except Exception:
        answer = (
            "DosTel1 measures external Columbus baseline dose while DosTel2 is shielded by water wall stowage packs, "
            "measuring 15-20% lower absorbed dose. These are simulated demonstration measurements with matched units."
        )
        return answer, "knowledge_base", None


def handle_radiation_forecast_query(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What will the radiation level be? / What is the radiation forecast?"""
    try:
        from app.forecasting import generate_radiation_forecast
        fc = generate_radiation_forecast(detector_id="DosTel1", horizon_steps=6, step_minutes=5.0, db_path=db_path)
        pts = fc.get("forecast_points", [])
        if pts:
            avg_pred = round(float(sum(p["predicted_dose_rate"] for p in pts) / len(pts)), 2)
            lower_ci = round(float(pts[0].get("ci_lower_95", avg_pred * 0.8)), 2)
            upper_ci = round(float(pts[-1].get("ci_upper_95", avg_pred * 1.2)), 2)
            answer = (
                f"The 30-minute physics-based forecast for detector DosTel1 predicts an average absorbed dose rate of {avg_pred} µGy/hr "
                f"(95% CI: {lower_ci}–{upper_ci} µGy/hr). These are predicted data estimates from historical orbital harmonic modeling, not actual real-time measurements."
            )
            return answer, "project_data", fc
    except Exception as exc:
        logger.warning(f"Forecasting error: {exc}")

    answer = (
        "The 30-minute orbital radiation forecast for Low Earth Orbit estimates nominal background rates between 2.2 and 3.5 µGy/hr. "
        "These are predicted data estimates from historical orbital harmonic modeling, not actual real-time measurements."
    )
    return answer, "knowledge_base", None


def handle_nasa_dataset_query(query: str, db_path: Optional[Any] = None) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: Where does this radiation data come from? / What is the NASA dataset?"""
    answer = (
        "ASTRA CARE's radiation data originates from the NASA Open Science Data Repository (OSDR) RadLab archive, "
        "collected by active dosimeters aboard the International Space Station in 2022."
    )
    return answer, "knowledge_base", None


def handle_radiation_units_physics(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What do µGy/hr and µSv/hr mean? / What is absorbed dose? / What is dose equivalent?"""
    lower = query.lower()
    if "absorbed dose mean" in lower or "what is absorbed dose" in lower:
        answer = "Absorbed dose (measured in µGy/hr) represents the physical energy deposited per unit mass of matter by ionizing radiation (1 Gray = 1 Joule/kg)."
        return answer, "knowledge_base", None

    if "dose equivalent in" in lower or "what is dose equivalent" in lower:
        answer = "Dose-equivalent rate (measured in µSv/hr) quantifies biological harm to human tissue by multiplying absorbed dose by a radiation quality factor."
        return answer, "knowledge_base", None

    if "not added" in lower or "never added" in lower:
        answer = (
            "µGy/hr measures physical absorbed dose while µSv/hr measures biological damage weighted by radiation quality factor. "
            "Because they represent different physical domains, they must never be added together."
        )
        return answer, "knowledge_base", None

    answer = (
        "µGy/hr (microgray per hour) measures physical absorbed dose energy deposited in matter. "
        "Dose-equivalent rate in µSv/hr (microsievert per hour) weights absorbed dose by radiation quality factor to measure biological harm. "
        "Because they represent different physical domains, they must never be added together."
    )
    return answer, "knowledge_base", None


def handle_south_atlantic_anomaly(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What is the South Atlantic Anomaly?"""
    answer = (
        "The South Atlantic Anomaly is an area where Earth's inner Van Allen radiation belt dips closest to low Earth orbit. "
        "Transiting this region temporarily increases trapped proton radiation rates to 15–40 µGy/hr."
    )
    return answer, "knowledge_base", None


def handle_normal_unusual_unavailable(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What is the difference between normal, unusual, and unavailable readings?"""
    answer = (
        "Normal-looking readings fall within nominal baseline limits. "
        "Unusual readings deviate from expected patterns and require verification. "
        "Unavailable readings represent missing or uncollected sensor data without synthetic fabrication; ASTRA CARE never invents official medical thresholds."
    )
    return answer, "knowledge_base", None


def handle_why_health_monitoring_matters(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: Why is regular health monitoring important during space missions?"""
    answer = (
        "Regular health monitoring is vital to track cardiovascular deconditioning, fluid shift, and cumulative radiation exposure in microgravity. "
        "Continuous monitoring helps safeguard crew health throughout the mission."
    )
    return answer, "knowledge_base", None


# ----------------------------------------------------------------------------
# Medical Symptoms Handlers (Safety-Focused, Prompt Medical Contact)
# ----------------------------------------------------------------------------

def handle_symptom_chest_pain(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: I have chest pain / Chest discomfort."""
    answer = (
        "Chest pain in microgravity requires immediate clinical evaluation to distinguish musculoskeletal strain from cardiovascular events. "
        "Secure yourself in foot restraints, halt all physical exertion, and contact the Mission Flight Surgeon and Biomedical Engineer immediately."
    )
    return answer, "medical_guidance", None


def handle_symptom_breathing(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: Difficulty breathing / Shortness of breath."""
    answer = (
        "Difficulty breathing during spaceflight can result from localized carbon dioxide pockets or cephalad fluid shifts. "
        "Immediately move away from dead air zones toward cabin ventilation diffusers, notify the crew, and contact the Mission Flight Surgeon."
    )
    return answer, "medical_guidance", None


def handle_symptom_weakness(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: Feeling weak / Muscle weakness / Loss of strength."""
    answer = (
        "Sudden weakness in microgravity may indicate fluid shift imbalances, electrolyte depletion, or cardiovascular deconditioning. "
        "Rest in a neutral posture, stay hydrated with oral electrolytes, avoid heavy exertion, and notify the Mission Flight Surgeon."
    )
    return answer, "medical_guidance", None


def handle_symptom_dizziness(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: I am feeling dizzy."""
    answer = (
        "If feeling dizzy, anchor yourself in foot restraints to prevent injury, avoid rapid head movements, and notify the Flight Surgeon. "
        "Dizziness often results from neuro-vestibular space motion sickness or fluid redistribution."
    )
    return answer, "medical_guidance", None


def handle_symptom_fatigue(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: I am feeling fatigued."""
    answer = (
        "If experiencing fatigue, reduce high-intensity workload, verify sleep schedule, and report symptoms to the Flight Surgeon. "
        "Fatigue can stem from circadian disruption or cabin CO2 elevation."
    )
    return answer, "medical_guidance", None


def handle_symptom_nausea(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: I am feeling nauseated."""
    answer = (
        "If nauseated or experiencing motion sickness, anchor in a stable position, minimize head movements, use an emesis bag if needed, and notify the Flight Surgeon and Crew Medical Officer (CMO). "
        "Space adaptation syndrome commonly affects crew during the first few days."
    )
    return answer, "medical_guidance", None


def handle_symptom_headache(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: I have a headache."""
    answer = (
        "If you have a headache, rest near a cabin ventilation diffuser to clear any localized CO2 pockets, stay hydrated, and notify the Flight Surgeon."
    )
    return answer, "medical_guidance", None


def handle_microgravity_adaptation(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What happens to the human body in microgravity?"""
    answer = (
        "In microgravity, blood and fluids shift toward the head (cephalad shift), resting plasma volume decreases, and bones and muscles lose density without gravitational loading. "
        "Astronauts perform 2.5 hours of daily countermeasure exercise to mitigate these effects."
    )
    return answer, "knowledge_base", None


def handle_radiation_health_effects(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: How does radiation affect astronaut health?"""
    answer = (
        "Space radiation ionizes cells and damages DNA, creating acute risks (nausea, fatigue) during solar flares and chronic risks (lifetime cancer, cataracts) from cosmic rays. "
        "Astronauts follow ALARA principles to minimize exposure."
    )
    return answer, "knowledge_base", None


def handle_radiation_precautions(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Answers: What precautions reduce radiation exposure?"""
    answer = (
        "To reduce radiation exposure, crew members shelter in heavily shielded modules like Node 2, position water storage bags against bulkhead walls, and avoid spacewalks during solar particle events."
    )
    return answer, "knowledge_base", None


def handle_unrelated_query(query: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Handles questions unrelated to astronaut health or mission radiation."""
    answer = (
        "This question is unrelated to astronaut health monitoring, space radiation dosimetry, or the ASTRA CARE system. "
        "Please ask an astronaut health or mission radiation question."
    )
    return answer, "general_chat", None


# ============================================================================
# Master Local Deterministic Intent Router
# ============================================================================

def generate_local_fallback_response(
    cleaned_message: str,
    astronaut_id: Optional[str] = None,
    db_path: Optional[Any] = None
) -> ChatResponse:
    """
    Executes the deterministic, context-aware rule engine.
    Retrieves real-time SQLite database values and returns direct 1-4 sentence answers.
    """
    lower = cleaned_message.lower()

    # 1. Whose heartbeat is this? / Whose vitals are these?
    if any(phrase in lower for phrase in ["whose heartbeat", "whose heart rate", "whose vitals", "whose reading", "who is this heartbeat", "who does this belong to"]):
        answer, source, data_ctx = handle_whose_vitals_query(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 2. What is an Isolation Forest?
    if "what is an isolation forest" in lower or "what is isolation forest" in lower:
        answer, source, data_ctx = handle_isolation_forest_query(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 3. Anomaly score meaning
    if "anomaly score" in lower and ("what" in lower or "mean" in lower or "explain" in lower):
        answer, source, data_ctx = handle_anomaly_score_meaning(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 4. Detector Z-score
    if "z-score" in lower or "z score" in lower:
        answer, source, data_ctx = handle_detector_z_score(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 5. Detector comparison: DosTel1 vs DosTel2
    if any(w in lower for w in ["compare", "comparison"]) and any(w in lower for w in ["detector", "dostel", "instrument"]):
        answer, source, data_ctx = handle_detector_comparison_query(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 6. Radiation Forecast / Predictions
    if any(w in lower for w in ["forecast", "predict", "what will the radiation", "will radiation be", "future radiation"]):
        answer, source, data_ctx = handle_radiation_forecast_query(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 7. NASA dataset origin
    if any(phrase in lower for phrase in ["where does this radiation data come from", "where did this data come from", "nasa dataset", "source of this radiation"]):
        answer, source, data_ctx = handle_nasa_dataset_query(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 8. Dose-equivalent rate specific query
    if "dose equivalent" in lower and any(w in lower for w in ["what is my", "rate", "current", "reading", "value"]):
        answer, source, data_ctx = handle_dose_equivalent_query(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 9. Absorbed dose rate specific query
    if "absorbed dose" in lower and any(w in lower for w in ["what is my", "rate", "current", "reading", "value"]):
        answer, source, data_ctx = handle_latest_radiation_reading(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 10. Radiation units physics
    if any(w in lower for w in ["absorbed dose", "dose equivalent", "dose-equivalent", "µgy", "µsv", "microgray", "microsievert", "gray and sievert"]):
        answer, source, data_ctx = handle_radiation_units_physics(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 11. South Atlantic Anomaly
    if any(term in lower for term in ["south atlantic anomaly", "saa transit", "saa region", "saa"]):
        answer, source, data_ctx = handle_south_atlantic_anomaly(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 12. Is radiation normal? / Is my radiation reading safe?
    if any(phrase in lower for phrase in ["is my radiation normal", "is radiation normal", "is my radiation safe", "is radiation safe"]):
        answer, source, data_ctx = handle_radiation_normal_status(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 13. Why did radiation increase? / Is radiation increasing? / Radiation trend
    if any(phrase in lower for phrase in ["why did radiation increase", "radiation increase", "radiation increased", "is radiation increasing", "radiation trend", "radiation changing"]):
        answer, source, data_ctx = handle_why_radiation_increased(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 14. Action on radiation alert
    if "radiation alert" in lower and any(w in lower for w in ["what should i do", "what to do", "action", "trigger"]):
        answer, source, data_ctx = handle_radiation_alert_action(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 15. Action on health alert
    if ("health alert" in lower or "abnormal alert" in lower) and any(w in lower for w in ["what should i do", "what to do", "action", "appear"]):
        answer, source, data_ctx = handle_health_alert_action(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 16. Action when any alert appears
    if "alert appears" in lower or "when an alert appears" in lower or "what should an astronaut do when an alert" in lower:
        answer, source, data_ctx = handle_medical_alert_guidance(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 17. Active alerts query
    if any(phrase in lower for phrase in ["do i have any alerts", "any active alerts", "active alerts", "show alerts", "are there any alerts", "current alerts"]):
        answer, source, data_ctx = handle_active_alerts_query(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 18. Radiation health effects
    if ("affect" in lower or "danger" in lower or "effect" in lower or "risk" in lower or "harm" in lower) and any(w in lower for w in ["radiation", "cosmic ray", "solar"]):
        answer, source, data_ctx = handle_radiation_health_effects(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 19. Radiation precautions
    if any(w in lower for w in ["precaution", "reduce", "protect", "shield", "prevention", "minimize"]) and any(w in lower for w in ["radiation", "exposure", "dose"]):
        answer, source, data_ctx = handle_radiation_precautions(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 20. Explain radiation anomaly / ML anomaly status
    if any(w in lower for w in ["anomaly", "flagged", "machine learning", "ml model", "outlier", "isolation forest"]):
        answer, source, data_ctx = handle_radiation_anomaly_explanation(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 21. Normal vs unusual vs unavailable
    if any(w in lower for w in ["normal, unusual", "unusual, and unavailable", "normal, unusual, and unavailable", "unavailable readings", "unusual readings"]):
        answer, source, data_ctx = handle_normal_unusual_unavailable(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 22. Why health monitoring matters
    if any(w in lower for w in ["health monitoring important", "why is regular health monitoring", "why is health monitoring"]):
        answer, source, data_ctx = handle_why_health_monitoring_matters(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 23. Medical Symptoms (Safety-Focused Prompt Recognition)
    if any(w in lower for w in ["chest pain", "angina", "pain in chest", "chest discomfort", "chest pressure"]):
        answer, source, data_ctx = handle_symptom_chest_pain(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    if any(w in lower for w in ["breathing difficulty", "difficulty breathing", "shortness of breath", "hard to breathe", "breathless", "dyspnea"]):
        answer, source, data_ctx = handle_symptom_breathing(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    if any(w in lower for w in ["weakness", "feeling weak", "muscle weakness", "body weak", "loss of strength"]):
        answer, source, data_ctx = handle_symptom_weakness(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    if any(w in lower for w in ["dizzy", "dizziness", "lightheaded", "vertigo", "spinning"]):
        answer, source, data_ctx = handle_symptom_dizziness(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    if any(w in lower for w in ["fatigue", "fatigued", "exhausted", "tired", "lethargic", "exhaustion"]):
        answer, source, data_ctx = handle_symptom_fatigue(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    if any(w in lower for w in ["nausea", "nauseous", "nauseated", "vomit", "motion sickness", "space sickness", "sas"]):
        answer, source, data_ctx = handle_symptom_nausea(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    if any(w in lower for w in ["headache", "migraine", "head pain", "head pressure"]):
        answer, source, data_ctx = handle_symptom_headache(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 24. Microgravity adaptation
    if any(w in lower for w in ["human body in microgravity", "body in space", "microgravity effect", "fluid shift", "sans", "bone loss", "muscle loss", "adaptation"]):
        answer, source, data_ctx = handle_microgravity_adaptation(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 25. Heart rate inquiries
    if any(w in lower for w in ["heart rate", "pulse", "bpm", "heartrate"]):
        answer, source, data_ctx = handle_heart_rate_query(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 26. Blood pressure inquiries
    if any(w in lower for w in ["blood pressure", "systolic", "diastolic", "mmhg", "hypertension", "hypotension"]):
        answer, source, data_ctx = handle_blood_pressure_query(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 27. Oxygen saturation inquiries
    if any(w in lower for w in ["oxygen saturation", "spo2", "hypoxia", "oximeter"]):
        answer, source, data_ctx = handle_spo2_query(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 28. Body temperature inquiries
    if any(w in lower for w in ["body temperature", "temperature", "space fever", "fever", "core temp", "thermoregulation"]):
        answer, source, data_ctx = handle_temperature_query(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 29. All vitals inquiry ("Explain my latest vitals" / "Show my vitals" / "Explain my health measurements")
    if any(w in lower for w in ["vitals", "health measurements", "health reading"]):
        answer, source, data_ctx = handle_all_vitals_query(cleaned_message, astronaut_id, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 30. Latest radiation reading
    if any(w in lower for w in ["radiation reading", "my radiation", "latest radiation", "current radiation", "radiation level", "radiation"]):
        answer, source, data_ctx = handle_latest_radiation_reading(cleaned_message, db_path)
        return ChatResponse(answer=answer, source=source, status="success", data_context=data_ctx)

    # 31. Unrelated general questions
    unrelated_indicators = [
        "capital of", "who is", "who was", "weather in", "movie", "recipe",
        "president", "football", "cricket", "world cup", "stock price", "joke", "song"
    ]
    space_health_keywords = [
        "astronaut", "space", "mission", "nasa", "iss", "crew", "radiation",
        "health", "telemetry", "detector", "heart", "pressure", "oxygen", "temp",
        "chest", "breath", "dizzy", "fatigue", "nausea", "headache", "weakness"
    ]
    if any(term in lower for term in unrelated_indicators) or (len(cleaned_message.split()) > 3 and not any(w in lower for w in space_health_keywords)):
        answer, source, _ = handle_unrelated_query(cleaned_message)
        return ChatResponse(answer=answer, source=source, status="success", data_context=None)

    # 32. Standard greeting fallback
    answer = (
        "Hello, crew member. I am the ASTRA CARE AI Assistant. "
        "I provide direct, concise explanations for space radiation readings, physiological vitals, ML anomaly status, and mission safety alerts."
    )
    return ChatResponse(
        answer=answer,
        source="knowledge_base",
        status="success",
        data_context=None,
        disclaimer=ASSISTANT_DISCLAIMER
    )


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
    Provides direct, concise, astronaut-friendly answers adhering strictly to medical safety.
    Operates 100% offline via local Ollama LLM or deterministic local fallback engine.
    """
    cleaned_message = message.strip()
    if not cleaned_message:
        raise ValueError("Message cannot be empty or whitespace only.")

    logger.info(f"Processing assistant query: '{cleaned_message[:60]}...' (Astronaut: {astronaut_id or 'General'})")

    # Step 1: Safety Guardrails Check (Diagnosis, Prescription, Abort, Inventing Thresholds)
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

    # Step 2: Extract explicit astronaut ID from query text if present
    extracted_ast = extract_astronaut_id_from_text(cleaned_message)
    effective_ast_id = extracted_ast or astronaut_id

    # Step 3: Compute deterministic local response with real-time SQLite database context
    fallback_response = generate_local_fallback_response(
        cleaned_message,
        astronaut_id=effective_ast_id,
        db_path=db_path
    )

    # Step 4: Check if Local Ollama LLM is available and not disabled
    # Direct medical symptoms and clinical protocol guidance must preserve exact validated aerospace directives
    if fallback_response.source in ["medical_guidance", "safety_guardrail"] or any(
        sym in cleaned_message.lower() for sym in ["chest pain", "difficulty breathing", "headache", "nauseat", "motion sick", "dizzy", "weakness", "fatigue"]
    ):
        return fallback_response

    if not os.environ.get("FORCE_LOCAL_FALLBACK"):
        ollama_stat = check_ollama_status()
        if ollama_stat.get("available"):
            context_summary = json.dumps(fallback_response.data_context) if fallback_response.data_context else "No active telemetry payload"
            prompt = (
                f"Crew Member Query: {cleaned_message}\n"
                f"Active Astronaut: {effective_ast_id or 'AST-01'}\n"
                f"Retrieved SQLite Telemetry Context: {context_summary}\n"
                f"Verified Telemetry Facts: {fallback_response.answer}\n\n"
                f"Instructions:\n"
                f"- Respond in two concise sentences in simple, direct English.\n"
                f"- State the exact reading and units from the Verified Telemetry Facts above.\n"
                f"- Clearly distinguish simulated vs historical NASA RadLab vs live data.\n"
                f"- Never diagnose diseases, prescribe medications, or invent numbers."
            )
            sys_inst = (
                "You are the ASTRA CARE AI Health and Radiation Assistant aboard the ISS. "
                "You answer questions directly, accurately, and concisely using the provided SQLite telemetry facts. "
                "You never provide clinical diagnoses or prescribe drugs."
            )
            ollama_ans = query_local_ollama(prompt, sys_inst, model=ollama_stat.get("model"))
            if ollama_ans and len(ollama_ans.strip()) > 10:
                guard_check = evaluate_safety_guardrails(ollama_ans)
                if not guard_check:
                    # Guard against hallucinations, refusals, or claims that data is unavailable
                    if any(phrase in ollama_ans.lower() for phrase in [
                        "not available", "can't provide", "cannot provide", "no data", "cannot answer", "anything else i can help"
                    ]):
                        return fallback_response

                    return ChatResponse(
                        answer=ollama_ans.strip(),
                        source="local_ollama",
                        status="success",
                        data_context=fallback_response.data_context,
                        disclaimer=ASSISTANT_DISCLAIMER
                    )

    # Step 5: Return deterministic local engine response
    return fallback_response
