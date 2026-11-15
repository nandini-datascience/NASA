"""
main.py - ASTRA CARE: Astronaut Health and Space Radiation Monitoring System Backend

FastAPI Application Entry Point.
Run with:
    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import logging
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Query, Response, status, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.analysis import (
    DEFAULT_ACTION_DOSE_RATE_UGY_HR,
    DEFAULT_ADVISORY_DOSE_RATE_UGY_HR,
    DEFAULT_ADVISORY_EQ_RATE_USV_HR,
    DEFAULT_CRITICAL_DOSE_RATE_UGY_HR,
    DEFAULT_MAX_GAP_SECONDS,
    DEFAULT_SPIKE_THRESHOLD_UGY_HR,
    DISCLAIMER_TEXT,
    perform_full_radiation_analysis
)
from app.data import (
    RADIATION_FIELD_METADATA,
    fetch_nasa_radiation_sample,
    load_local_nasa_sample
)
from app.db import (
    get_db_statistics,
    init_db,
    insert_alerts,
    insert_astronaut_health_alerts,
    insert_astronaut_health_record,
    insert_radiation_records,
    query_alerts,
    query_astronaut_health_alerts,
    query_astronaut_health_history,
    query_astronaut_health_measurements,
    query_radiation_history,
    insert_dynamic_radiation_reading,
    insert_ml_anomaly_record,
    query_dynamic_radiation_readings,
    get_latest_dynamic_radiation_reading,
    query_ml_anomalies,
    query_radiation_locations,
    query_nasa_sync_logs,
    query_smart_alerts,
    query_multi_detector_stats
)
from app.health import (
    HEALTH_DISCLAIMER_TEXT,
    HEALTH_METRIC_METADATA,
    evaluate_astronaut_health_alerts,
    validate_health_measurement
)
from app.assistant import (
    ASSISTANT_DISCLAIMER,
    ChatRequest,
    ChatResponse,
    generate_assistant_response
)
from app.radiation_streaming import (
    get_stream_engine,
    SimulatedStreamingProvider,
    HardwareSensorProvider,
    LiveSpacecraftTelemetryProvider,
    default_radiation_processing_pipeline
)
from app.ml.model import get_detector
from app.nasa_sync import (
    fetch_latest_nasa_radlab_data,
    get_nasa_sync_service
)
from app.forecasting import generate_radiation_forecast
from app.smart_alerts import (
    generate_smart_alert_from_radiation,
    sync_and_generate_smart_alerts
)
from app.detector_comparison import get_detector_time_series_comparison
from app.reports import (
    compile_astronaut_report_data,
    generate_astronaut_pdf_report
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("astra_care.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Initializes SQLite database schema and seeds initial authentic NASA records
    and baseline demonstration health records if newly created.
    """
    logger.info("Initializing ASTRA CARE database schema...")
    init_db()
    stats = get_db_statistics()

    # 1. Seed NASA RadLab radiation records if empty
    if stats["stored_radiation_records_count"] == 0:
        logger.info("Seeding database with authentic NASA RadLab archive measurements...")
        try:
            local_sample = load_local_nasa_sample()
            records = local_sample.get("records", [])
            if records:
                insert_radiation_records(records, source_origin="Local NASA RadLab Sample Archive")
                analysis_results = perform_full_radiation_analysis(
                    records,
                    source_origin="Local NASA RadLab Sample Archive"
                )
                alerts = (
                    analysis_results["alerts_summary"]["data_quality_warnings"] +
                    analysis_results["alerts_summary"]["health_risk_alerts"]
                )
                insert_alerts(alerts)
                logger.info(f"Seeded {len(records)} authentic NASA radiation records.")
        except Exception as exc:
            logger.warning(f"Could not seed initial NASA records: {exc}")

    # 2. Seed baseline demonstration astronaut health records if empty
    if stats.get("stored_health_records_count", 0) == 0:
        logger.info("Seeding initial demonstration astronaut health records (clearly labeled simulated_demo)...")
        demo_vitals = [
            {
                "astronaut_id": "AST-01",
                "timestamp": "2026-11-14T08:00:00Z",
                "heart_rate": 72.0,
                "blood_pressure_systolic": 118.0,
                "blood_pressure_diastolic": 76.0,
                "oxygen_saturation": 98.5,
                "body_temperature": 36.8,
                "source_device": "Wearable Crew Patch #1",
                "data_classification": "simulated_demo",
                "notes": "Simulated nominal morning resting telemetry baseline."
            },
            {
                "astronaut_id": "AST-01",
                "timestamp": "2026-11-14T10:30:00Z",
                "heart_rate": 105.0,
                "blood_pressure_systolic": 132.0,
                "blood_pressure_diastolic": 82.0,
                "oxygen_saturation": 97.0,
                "body_temperature": 37.4,
                "source_device": "Wearable Crew Patch #1",
                "data_classification": "simulated_demo",
                "notes": "Simulated post-exercise treadmill session."
            },
            {
                "astronaut_id": "AST-02",
                "timestamp": "2026-11-14T09:15:00Z",
                "heart_rate": 64.0,
                "blood_pressure_systolic": 112.0,
                "blood_pressure_diastolic": 72.0,
                "oxygen_saturation": 99.0,
                "body_temperature": 36.7,
                "source_device": "Wearable Crew Patch #2",
                "data_classification": "simulated_demo",
                "notes": "Simulated nominal baseline observation."
            }
        ]
        for demo in demo_vitals:
            val_rec, _, _ = validate_health_measurement(demo)
            if val_rec:
                insert_astronaut_health_record(val_rec)
                health_alerts = evaluate_astronaut_health_alerts(val_rec)
                if health_alerts:
                    insert_astronaut_health_alerts(health_alerts)

    # 3. Initialize ML Anomaly Detector (ASTRA CARE 2.0)
    logger.info("Initializing Machine Learning Anomaly Detector...")
    try:
        get_detector()
    except Exception as exc:
        logger.warning(f"Could not initialize ML detector: {exc}")

    # 4. Start dynamic radiation stream engine (ASTRA CARE 2.0)
    stream_engine = get_stream_engine()
    stream_engine.start()

    # 5. Synchronize initial smart alerts
    try:
        sync_and_generate_smart_alerts()
    except Exception as exc:
        logger.warning(f"Could not initialize smart alerts: {exc}")

    yield
    logger.info("ASTRA CARE backend shutting down...")
    stream_engine.pause()
    try:
        sync_service = get_nasa_sync_service()
        sync_service.stop()
    except Exception:
        pass


# Initialize FastAPI app
app = FastAPI(
    title="ASTRA CARE – Astronaut Health and Space Radiation Monitoring System",
    description=(
        "Backend API for ASTRA CARE.\n\n"
        "Provides two distinct, modular monitoring engines:\n"
        "1. **Space Radiation Monitoring Module:** Interfaces with the NASA Open Science Data Repository "
        "(OSDR) RadLab database to provide authenticated radiation telemetry measured on the ISS.\n"
        "2. **Astronaut Health Monitoring Module:** Tracks and validates crew vitals (Heart rate, Blood pressure, "
        "SpO2, Body temperature) against validated aerospace clinical benchmarks (NASA-STD-3001, AHA, WHO).\n\n"
        "**Important Operational & Scientific Notice:**\n"
        "- NASA space radiation measurements are **authentic historical scientific records** and are NOT live.\n"
        "- Vitals telemetry is clearly distinguished between simulated demo, historical study, and sensor telemetry.\n"
        "- **Non-Diagnostic Notice:** This system tracks telemetry against aerospace benchmarks and does NOT diagnose diseases."
    ),
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Enable Cross-Origin Resource Sharing (CORS) for JavaScript Fetch API frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permits all origins for frontend development
    allow_credentials=True,
    allow_methods=["*"],  # Permits GET, POST, OPTIONS, etc.
    allow_headers=["*"],
)


# ============================================================================
# Pydantic Request Models for Astronaut Health Telemetry (Task 03)
# ============================================================================

class HealthMeasurementInput(BaseModel):
    astronaut_id: str = Field(..., description="Unique astronaut identifier (e.g. AST-01, AST-02)", json_schema_extra={"example": "AST-01"})
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp (YYYY-MM-DDTHH:MM:SSZ)", json_schema_extra={"example": "2026-11-14T12:00:00Z"})
    heart_rate: Optional[float] = Field(None, description="Heart rate in BPM (valid range 30-240)", json_schema_extra={"example": 75.0})
    blood_pressure_systolic: Optional[float] = Field(None, description="Systolic blood pressure in mmHg (50-260)", json_schema_extra={"example": 118.0})
    blood_pressure_diastolic: Optional[float] = Field(None, description="Diastolic blood pressure in mmHg (30-160)", json_schema_extra={"example": 76.0})
    oxygen_saturation: Optional[float] = Field(None, description="Oxygen saturation SpO2 in % (50-100)", json_schema_extra={"example": 98.0})
    body_temperature: Optional[float] = Field(None, description="Core body temperature in °C (30.0-44.0)", json_schema_extra={"example": 36.8})
    source_device: Optional[str] = Field("Wearable Crew Health Monitor", description="Sensor device hardware name")
    data_classification: Optional[str] = Field("simulated_demo", description="'simulated_demo', 'historical_study', or 'sensor_telemetry'")
    notes: Optional[str] = Field(None, description="Operational or clinical observation notes")


# ============================================================================
# Pydantic Request Models for Dynamic Radiation & ML (ASTRA CARE 2.0)
# ============================================================================

class IncomingRadiationInput(BaseModel):
    instrument_id: Optional[str] = Field("DosTel1", description="Radiation detector identifier (e.g. DosTel1, DosTel2, Lidal, REM-Lid)")
    detector_id: Optional[str] = Field(None, description="Alias for instrument_id")
    timestamp: Optional[str] = Field(None, description="ISO 8601 UTC timestamp. Defaults to current UTC.")
    absorbed_dose_rate: float = Field(..., ge=0.0, description="Absorbed dose rate in µGy/hr")
    absorbed_dose_unit: Optional[str] = Field("µGy/hr", description="Unit of measurement")
    dose_equivalent_rate: Optional[float] = Field(None, ge=0.0, description="Dose equivalent rate in µSv/hr")
    dose_equivalent_unit: Optional[str] = Field("µSv/hr", description="Unit of measurement")
    flux: Optional[float] = Field(None, ge=0.0, description="Particle flux in particles/(cm²·sr·s)")
    particle_flux: Optional[float] = Field(None, ge=0.0, description="Alias for particle flux")
    spacecraft: Optional[str] = Field("ISS", description="Host spacecraft platform")
    module: Optional[str] = Field("Columbus", description="Internal pressurized module")
    altitude: Optional[float] = Field(418.0, description="Orbital altitude in km")
    altitude_km: Optional[float] = Field(None, description="Alias for altitude")
    latitude: Optional[float] = Field(None, description="Sub-satellite geographic latitude (-90 to +90)")
    longitude: Optional[float] = Field(None, description="Sub-satellite geographic longitude (-180 to +180)")
    orbital_region: Optional[str] = Field("NOMINAL_LEO", description="Orbital region (e.g. NOMINAL_LEO, SOUTH_ATLANTIC_ANOMALY)")
    data_source: Optional[str] = Field("simulated_streaming", description="'simulated_streaming', 'sensor_telemetry', or 'live_spacecraft'")
    is_simulated: Optional[bool] = Field(None, description="Explicit simulated data flag")
    measurement_quality: Optional[str] = Field("nominal", description="'nominal', 'degraded', 'simulated_event'")


class StreamControlInput(BaseModel):
    action: str = Field(..., description="'start', 'pause', 'tick', 'set_interval', 'inject_anomaly', 'clear_anomaly'")
    interval_seconds: Optional[float] = Field(None, ge=1.0, le=60.0, description="Sampling interval in seconds (1.0 to 60.0)")
    anomaly_type: Optional[str] = Field("SOLAR_SPIKE", description="Injected anomaly type: 'SOLAR_SPIKE', 'SAA_SURGE', 'SENSOR_NOISE'")
    anomaly_magnitude: Optional[float] = Field(35.0, ge=1.0, le=1000.0, description="Surge magnitude in µGy/hr")
    duration_ticks: Optional[int] = Field(3, ge=1, le=50, description="Duration in stream ticks")


class MLPredictInput(BaseModel):
    instrument_id: str = Field("DosTel1", description="Detector identifier")
    absorbed_dose_rate: float = Field(..., ge=0.0, description="Absorbed dose rate in µGy/hr")
    flux: Optional[float] = Field(None, ge=0.0, description="Particle flux in particles/(cm²·sr·s)")
    latitude: Optional[float] = Field(None, description="Sub-satellite latitude")
    longitude: Optional[float] = Field(None, description="Sub-satellite longitude")
    orbital_region: Optional[str] = Field("NOMINAL_LEO", description="Orbital region")


# ============================================================================
# Pydantic Request Models for Advanced Features (Tasks 01-06)
# ============================================================================

class ForecastRequestInput(BaseModel):
    detector_id: Optional[str] = Field("DosTel1", description="Detector to forecast ('DosTel1', 'DosTel2', 'Lidal', 'REM-Lid')")
    horizon_steps: Optional[int] = Field(16, ge=4, le=100, description="Number of forecasting steps")
    step_minutes: Optional[float] = Field(5.0, ge=1.0, le=60.0, description="Step interval in minutes")


class NasaSyncRequestInput(BaseModel):
    start_time: Optional[str] = Field(None, description="Start timestamp ISO string (e.g. 2022-04-01T00:00:00)")
    end_time: Optional[str] = Field(None, description="End timestamp ISO string (e.g. 2022-04-01T01:00:00)")
    spacecraft: Optional[str] = Field("ISS", description="Spacecraft identifier")
    limit: Optional[int] = Field(120, ge=1, le=1000, description="Maximum records to retrieve")


class SmartAlertEvalInput(BaseModel):
    advisory_threshold_ugy: Optional[float] = Field(20.0, ge=0.0, description="Advisory threshold in µGy/hr")
    action_threshold_ugy: Optional[float] = Field(100.0, ge=0.0, description="Action threshold in µGy/hr")


# ============================================================================
# General & System Routes
# ============================================================================

@app.get(
    "/",
    tags=["General"],
    summary="ASTRA CARE System Homepage",
    response_description="System status, mission overview, and API navigation links"
)
async def homepage() -> Dict[str, Any]:
    """
    Root endpoint for ASTRA CARE.
    Returns service identification, operational mode, and helpful links.
    """
    stats = get_db_statistics()
    return {
        "project": "ASTRA CARE",
        "system_name": "AI-Powered Astronaut Health Monitoring and Dynamic Space Radiation Detection System",
        "version": "2.0.0",
        "status": "operational",
        "modules": {
            "radiation_monitoring": "NASA RadLab Radiation Telemetry, Analysis, and Dosimetry Alerts",
            "dynamic_radiation_streaming": "Continuous Multi-Provider Radiation Ingestion (Simulated Stream / Sensor Standby)",
            "machine_learning_anomaly_detection": "Unsupervised Isolation Forest Radiation Pattern Analysis & Anomaly Scoring",
            "astronaut_health_monitoring": "Crew Vitals Telemetry, Physiological Validation, and Medical Guidance Alerts",
            "ai_health_assistant": "Interactive Space Health & Radiation Plain-Language Assistant with Intelligent Intent Routing"
        },
        "database_status": {
            "type": "SQLite",
            "historical_radiation_records_stored": stats["stored_radiation_records_count"],
            "dynamic_radiation_records_stored": stats.get("stored_dynamic_radiation_count", 0),
            "radiation_alerts_stored": stats["stored_radiation_alerts_count"],
            "ml_anomalies_stored": stats.get("stored_ml_anomalies_count", 0),
            "astronaut_health_records_stored": stats["stored_health_records_count"],
            "astronaut_health_alerts_stored": stats["stored_health_alerts_count"],
            "monitored_astronauts": stats["monitored_astronauts"]
        },
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_json": "/openapi.json"
        },
        "endpoints": {
            "homepage": "/",
            "radiation_sample": "/api/radiation/sample",
            "radiation_analysis": "/api/radiation/analysis",
            "radiation_history": "/api/radiation/history",
            "radiation_alerts": "/api/alerts",
            "radiation_stream_reading_post": "/api/radiation/stream/reading",
            "radiation_stream_latest": "/api/radiation/stream/latest",
            "radiation_stream_history": "/api/radiation/stream/history",
            "radiation_ml_status": "/api/radiation/ml/status",
            "radiation_ml_predict": "/api/radiation/ml/predict",
            "radiation_ml_anomalies": "/api/radiation/ml/anomalies",
            "radiation_stream_control_get": "/api/radiation/stream/control",
            "radiation_stream_control_post": "/api/radiation/stream/control",
            "radiation_telemetry_status": "/api/radiation/telemetry-status",
            "health_measurements_get": "/api/health/measurements",
            "health_measurements_post": "/api/health/measurements",
            "health_history": "/api/health/history",
            "health_alerts": "/api/health/alerts",
            "radiation_field_definitions": "/api/radiation/fields",
            "assistant_chat": "/api/assistant/chat",
            "assistant_status": "/api/assistant/status",
            "assistant_voice_status": "/api/assistant/voice-status",
            "assistant_voice_to_text": "/api/assistant/voice-to-text",
            "assistant_text_to_speech": "/api/assistant/text-to-speech",
            "system_network_status": "/api/system/network-status",
            "system_health": "/api/health"
        },
        "disclaimers": {
            "radiation": DISCLAIMER_TEXT,
            "health": HEALTH_DISCLAIMER_TEXT,
            "assistant": ASSISTANT_DISCLAIMER
        }
    }


@app.get(
    "/api/health",
    tags=["General"],
    summary="System Health & API Connectivity Check",
    response_description="Operational status of backend, database, and NASA RadLab connection"
)
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for system monitoring.
    Verifies that the backend is running and reports local dataset and database health.
    """
    local_data_ok = False
    try:
        sample = load_local_nasa_sample()
        local_data_ok = bool(sample.get("records"))
    except Exception:
        local_data_ok = False

    db_stats = get_db_statistics()

    return {
        "status": "healthy",
        "service": "ASTRA CARE Backend",
        "version": "3.0.0",
        "database": {
            "status": "connected",
            "radiation_records": db_stats["stored_radiation_records_count"],
            "radiation_alerts": db_stats["stored_radiation_alerts_count"],
            "health_records": db_stats["stored_health_records_count"],
            "health_alerts": db_stats["stored_health_alerts_count"]
        },
        "local_dataset_available": local_data_ok,
        "nasa_api_target": "https://visualization.osdr.nasa.gov/radlab/api"
    }


# ============================================================================
# Astronaut Health Monitoring Endpoints (Task 03)
# ============================================================================

@app.get(
    "/api/health/measurements",
    tags=["Astronaut Health Monitoring"],
    summary="Retrieve Current / Recent Astronaut Health Measurements",
    response_description="Recent validated vitals records with measurement units and classification"
)
async def get_health_measurements(
    astronaut_id: Optional[str] = Query(
        default=None,
        description="Filter by astronaut identifier (e.g. AST-01, AST-02)"
    ),
    data_classification: Optional[str] = Query(
        default=None,
        description="Filter by classification: 'simulated_demo', 'historical_study', 'sensor_telemetry', or 'all'"
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
        description="Maximum records to return"
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Pagination offset"
    )
) -> Dict[str, Any]:
    """
    Retrieves recent astronaut physiological measurements from the SQLite database:
    - **Heart Rate**: BPM (beats per minute)
    - **Blood Pressure**: Systolic & Diastolic in mmHg
    - **Oxygen Saturation**: SpO2 %
    - **Body Temperature**: °C

    Telemetry is clearly tagged by data classification:
    - `simulated_demo`: Simulated demonstration data
    - `historical_study`: Archived research telemetry
    - `sensor_telemetry`: Direct sensor device feed
    """
    clean_id = getattr(astronaut_id, "default", astronaut_id)
    clean_class = getattr(data_classification, "default", data_classification)

    raw_limit = getattr(limit, "default", limit)
    try:
        clean_limit = int(raw_limit) if raw_limit is not None else 50
    except (ValueError, TypeError):
        clean_limit = 50

    raw_offset = getattr(offset, "default", offset)
    try:
        clean_offset = int(raw_offset) if raw_offset is not None else 0
    except (ValueError, TypeError):
        clean_offset = 0

    return query_astronaut_health_measurements(
        astronaut_id=clean_id,
        data_classification=clean_class,
        limit=clean_limit,
        offset=clean_offset
    )


@app.post(
    "/api/health/measurements",
    tags=["Astronaut Health Monitoring"],
    summary="Record New Astronaut Health Measurement",
    status_code=status.HTTP_201_CREATED,
    response_description="Validation status, stored record, and evaluated physiological alerts"
)
async def create_health_measurement(
    payload: HealthMeasurementInput
) -> Dict[str, Any]:
    """
    Accepts, validates, evaluates, and stores a new astronaut health observation.

    **Validation Rules:**
    - Timestamp must be valid UTC ISO 8601 string.
    - Values must conform to physiological bounds (HR: 30-240 BPM, SpO2: 50-100%, Temp: 30-44°C).
    - Systolic blood pressure must strictly exceed diastolic blood pressure.
    - Preserves measurement units: BPM, mmHg, %, °C.

    **Aerospace Alert Engine:**
    Evaluates readings against **NASA-STD-3001 Vol 1**, **AHA**, and **WHO** guidance.
    Stores any generated health alerts into SQLite.
    """
    data_dict = payload.model_dump()
    validated_record, data_quality_alerts, validation_errors = validate_health_measurement(data_dict)

    if validation_errors:
        # Save any data quality warning alerts even if measurement is rejected
        if data_quality_alerts:
            insert_astronaut_health_alerts(data_quality_alerts)
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Physiological Data Validation Failed",
                "validation_errors": validation_errors,
                "data_quality_alerts": data_quality_alerts,
                "disclaimer": HEALTH_DISCLAIMER_TEXT
            }
        )

    # Evaluate physiological alert rules
    health_alerts = evaluate_astronaut_health_alerts(validated_record)
    all_alerts = data_quality_alerts + health_alerts

    # Persist record and alerts to SQLite
    stored_ok = insert_astronaut_health_record(validated_record)
    if all_alerts:
        insert_astronaut_health_alerts(all_alerts)

    return {
        "status": "success",
        "message": "Astronaut health measurement validated and recorded successfully.",
        "record_id": validated_record["record_id"],
        "stored_in_database": stored_ok,
        "record": validated_record,
        "alerts_triggered_count": len(all_alerts),
        "alerts": all_alerts,
        "disclaimer": HEALTH_DISCLAIMER_TEXT
    }


@app.get(
    "/api/health/history",
    tags=["Astronaut Health Monitoring"],
    summary="Query Historical Astronaut Health Vitals",
    response_description="Paginated time-series records of astronaut health telemetry"
)
async def get_health_history(
    astronaut_id: Optional[str] = Query(
        default=None,
        description="Filter by astronaut identifier"
    ),
    start_time: Optional[str] = Query(
        default=None,
        description="Filter by minimum timestamp (ISO 8601 UTC)"
    ),
    end_time: Optional[str] = Query(
        default=None,
        description="Filter by maximum timestamp (ISO 8601 UTC)"
    ),
    data_classification: Optional[str] = Query(
        default=None,
        description="Filter by classification ('simulated_demo', 'historical_study', 'sensor_telemetry', or 'all')"
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
        description="Records per page"
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Pagination offset"
    )
) -> Dict[str, Any]:
    """
    Retrieves time-series vitals history stored in the SQLite database.
    Historical records reflect recorded research telemetry and are NOT claimed to represent live astronaut health.
    """
    clean_id = getattr(astronaut_id, "default", astronaut_id)
    clean_start = getattr(start_time, "default", start_time)
    clean_end = getattr(end_time, "default", end_time)
    clean_class = getattr(data_classification, "default", data_classification)

    raw_limit = getattr(limit, "default", limit)
    try:
        clean_limit = int(raw_limit) if raw_limit is not None else 50
    except (ValueError, TypeError):
        clean_limit = 50

    raw_offset = getattr(offset, "default", offset)
    try:
        clean_offset = int(raw_offset) if raw_offset is not None else 0
    except (ValueError, TypeError):
        clean_offset = 0

    return query_astronaut_health_history(
        astronaut_id=clean_id,
        start_time=clean_start,
        end_time=clean_end,
        data_classification=clean_class,
        limit=clean_limit,
        offset=clean_offset
    )


@app.get(
    "/api/health/alerts",
    tags=["Astronaut Health Monitoring"],
    summary="Query Astronaut Health Alerts & Advisories",
    response_description="Paginated astronaut health alerts and physiological warnings"
)
async def get_health_alerts(
    astronaut_id: Optional[str] = Query(
        default=None,
        description="Filter by astronaut identifier"
    ),
    severity: Optional[str] = Query(
        default=None,
        description="Filter by severity ('INFO', 'WARNING', 'CRITICAL', or 'all')"
    ),
    alert_type: Optional[str] = Query(
        default=None,
        description="Filter by alert type (e.g. 'TACHYCARDIA', 'HYPOTENSION', 'HYPOXIA_MILD')"
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
        description="Alerts per page"
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Pagination offset"
    )
) -> Dict[str, Any]:
    """
    Retrieves astronaut health alerts and physiological warnings from SQLite.
    Each alert explains the physiological rationale referencing **NASA-STD-3001 / AHA / WHO** guidelines,
    without diagnosing clinical disease.
    """
    clean_id = getattr(astronaut_id, "default", astronaut_id)
    clean_sev = getattr(severity, "default", severity)
    clean_type = getattr(alert_type, "default", alert_type)

    raw_limit = getattr(limit, "default", limit)
    try:
        clean_limit = int(raw_limit) if raw_limit is not None else 50
    except (ValueError, TypeError):
        clean_limit = 50

    raw_offset = getattr(offset, "default", offset)
    try:
        clean_offset = int(raw_offset) if raw_offset is not None else 0
    except (ValueError, TypeError):
        clean_offset = 0

    return query_astronaut_health_alerts(
        astronaut_id=clean_id,
        severity=clean_sev,
        alert_type=clean_type,
        limit=clean_limit,
        offset=clean_offset
    )


# ============================================================================
# Space Radiation Monitoring Endpoints (Task 01 & Task 02)
# ============================================================================

@app.get(
    "/api/radiation/sample",
    tags=["Radiation Monitoring"],
    summary="Get NASA RadLab Radiation Measurements",
    response_description="Authentic space radiation records with measurement units and spacecraft coordinates"
)
async def get_radiation_sample(
    start_time: str = Query(
        default="2022-04-01T00:00:00",
        description="ISO 8601 UTC timestamp start window (YYYY-MM-DDTHH:MM:SS)"
    ),
    end_time: str = Query(
        default="2022-04-01T00:15:00",
        description="ISO 8601 UTC timestamp end window (YYYY-MM-DDTHH:MM:SS)"
    ),
    spacecraft: str = Query(
        default="ISS",
        description="Spacecraft platform identifier (e.g., ISS)"
    ),
    limit: int = Query(
        default=25,
        ge=1,
        le=200,
        description="Maximum number of records to return (1-200)"
    ),
    allow_fallback: bool = Query(
        default=True,
        description="If True, loads local authentic NASA dataset if NASA API is unreachable"
    )
) -> Dict[str, Any]:
    """
    Retrieves actual NASA RadLab radiation measurements for spacecraft environments (e.g. ISS).
    """
    clean_start = str(getattr(start_time, "default", start_time))
    clean_end = str(getattr(end_time, "default", end_time))
    clean_spacecraft = str(getattr(spacecraft, "default", spacecraft))

    raw_limit = getattr(limit, "default", limit)
    try:
        clean_limit = int(raw_limit) if raw_limit is not None else 25
    except (ValueError, TypeError):
        clean_limit = 25

    raw_fallback = getattr(allow_fallback, "default", allow_fallback)
    clean_fallback = bool(raw_fallback) if raw_fallback is not None else True

    try:
        data = fetch_nasa_radiation_sample(
            start_time=clean_start,
            end_time=clean_end,
            spacecraft=clean_spacecraft,
            limit=clean_limit,
            allow_fallback=clean_fallback
        )
        if data.get("records"):
            insert_radiation_records(
                data["records"],
                source_origin=data.get("source", "NASA OSDR RadLab API")
            )
        return data

    except Exception as exc:
        logger.error(f"Error serving radiation sample: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "NASA RadLab Radiation Service Unavailable",
                "message": str(exc),
                "suggestion": "The NASA external API may be experiencing downtime. Set allow_fallback=true to use cached authentic measurements."
            }
        )


@app.get(
    "/api/radiation/analysis",
    tags=["Radiation Monitoring"],
    summary="Perform Comprehensive Radiation Telemetry Analysis",
    response_description="Descriptive statistics, cumulative exposure, data validation, and generated alerts"
)
async def get_radiation_analysis(
    start_time: str = Query(
        default="2022-04-01T00:00:00",
        description="ISO 8601 UTC timestamp start window (YYYY-MM-DDTHH:MM:SS)"
    ),
    end_time: str = Query(
        default="2022-04-01T00:30:00",
        description="ISO 8601 UTC timestamp end window (YYYY-MM-DDTHH:MM:SS)"
    ),
    spacecraft: str = Query(
        default="ISS",
        description="Spacecraft identifier"
    ),
    limit: int = Query(
        default=100,
        ge=2,
        le=500,
        description="Maximum telemetry records to analyze (2-500)"
    ),
    max_gap_seconds: float = Query(
        default=DEFAULT_MAX_GAP_SECONDS,
        ge=60.0,
        le=86400.0,
        description="Maximum continuous time interval in seconds"
    ),
    advisory_threshold_ugy: float = Query(
        default=DEFAULT_ADVISORY_DOSE_RATE_UGY_HR,
        ge=0.1,
        description="Operational advisory threshold in µGy/hr"
    ),
    action_threshold_ugy: float = Query(
        default=DEFAULT_ACTION_DOSE_RATE_UGY_HR,
        ge=1.0,
        description="Operational action threshold in µGy/hr"
    ),
    allow_fallback: bool = Query(
        default=True,
        description="If True, analyzes authentic local dataset when NASA API is unreachable"
    )
) -> Dict[str, Any]:
    r"""
    Performs full scientific analysis of space radiation telemetry:
    - Data validation & missing values
    - Descriptive statistics for absorbed dose (µGy/hr) and dose-equivalent (µSv/hr)
    - Cumulative exposure integration via trapezoidal rule strictly when intervals satisfy continuous bounds ($\Delta t \le \text{max\_gap\_seconds}$)
    - Timestamp gap detection
    - Aerospace health risk alerts (NASA-STD-3001 / NCRP-132 / ISS Flight Rules)
    """
    clean_start = str(getattr(start_time, "default", start_time))
    clean_end = str(getattr(end_time, "default", end_time))
    clean_spacecraft = str(getattr(spacecraft, "default", spacecraft))

    raw_limit = getattr(limit, "default", limit)
    try:
        clean_limit = int(raw_limit) if raw_limit is not None else 100
    except (ValueError, TypeError):
        clean_limit = 100

    raw_gap = getattr(max_gap_seconds, "default", max_gap_seconds)
    try:
        clean_gap = float(raw_gap) if raw_gap is not None else DEFAULT_MAX_GAP_SECONDS
    except (ValueError, TypeError):
        clean_gap = DEFAULT_MAX_GAP_SECONDS

    raw_advisory = getattr(advisory_threshold_ugy, "default", advisory_threshold_ugy)
    clean_advisory = float(raw_advisory) if raw_advisory is not None else DEFAULT_ADVISORY_DOSE_RATE_UGY_HR

    raw_action = getattr(action_threshold_ugy, "default", action_threshold_ugy)
    clean_action = float(raw_action) if raw_action is not None else DEFAULT_ACTION_DOSE_RATE_UGY_HR

    raw_fallback = getattr(allow_fallback, "default", allow_fallback)
    clean_fallback = bool(raw_fallback) if raw_fallback is not None else True

    try:
        data_payload = fetch_nasa_radiation_sample(
            start_time=clean_start,
            end_time=clean_end,
            spacecraft=clean_spacecraft,
            limit=clean_limit,
            allow_fallback=clean_fallback
        )
        records = data_payload.get("records", [])
        source = data_payload.get("source", "NASA OSDR RadLab API")

        analysis_result = perform_full_radiation_analysis(
            records=records,
            source_origin=source,
            max_gap_seconds=clean_gap,
            advisory_dose_rate_ugy=clean_advisory,
            action_dose_rate_ugy=clean_action
        )

        if records:
            insert_radiation_records(records, source_origin=source)

        alerts_to_store = (
            analysis_result["alerts_summary"]["data_quality_warnings"] +
            analysis_result["alerts_summary"]["health_risk_alerts"]
        )
        if alerts_to_store:
            insert_alerts(alerts_to_store)

        return analysis_result

    except Exception as exc:
        logger.error(f"Error performing radiation analysis: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Radiation Analysis Failed",
                "message": str(exc)
            }
        )


@app.get(
    "/api/radiation/history",
    tags=["Radiation Monitoring"],
    summary="Query Stored Historical Radiation Telemetry",
    response_description="Paginated list of stored radiation records from SQLite database"
)
async def get_radiation_history(
    start_time: Optional[str] = Query(
        default=None,
        description="Filter by minimum ISO 8601 timestamp"
    ),
    end_time: Optional[str] = Query(
        default=None,
        description="Filter by maximum ISO 8601 timestamp"
    ),
    spacecraft: Optional[str] = Query(
        default=None,
        description="Filter by spacecraft platform (e.g., ISS)"
    ),
    instrument_id: Optional[str] = Query(
        default=None,
        description="Filter by detector identifier (e.g., REM-Lid, DosTel1, DosTel2)"
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
        description="Number of records to return per page (1-500)"
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of records to skip for pagination"
    )
) -> Dict[str, Any]:
    """
    Retrieves stored radiation records from the local SQLite database.
    """
    clean_start = getattr(start_time, "default", start_time)
    clean_end = getattr(end_time, "default", end_time)
    clean_spacecraft = getattr(spacecraft, "default", spacecraft)
    clean_inst = getattr(instrument_id, "default", instrument_id)

    raw_limit = getattr(limit, "default", limit)
    try:
        clean_limit = int(raw_limit) if raw_limit is not None else 50
    except (ValueError, TypeError):
        clean_limit = 50

    raw_offset = getattr(offset, "default", offset)
    try:
        clean_offset = int(raw_offset) if raw_offset is not None else 0
    except (ValueError, TypeError):
        clean_offset = 0

    return query_radiation_history(
        start_time=clean_start,
        end_time=clean_end,
        spacecraft=clean_spacecraft,
        instrument_id=clean_inst,
        limit=clean_limit,
        offset=clean_offset
    )


@app.get(
    "/api/alerts",
    tags=["Radiation Monitoring"],
    summary="Query Generated Radiation Alerts and Data-Quality Warnings",
    response_description="Paginated alerts filtered by category, severity, and instrument"
)
async def get_alerts(
    category: Optional[str] = Query(
        default=None,
        description="Filter by alert category: 'DATA_QUALITY_WARNING', 'HEALTH_RISK_ALERT', or 'all'"
    ),
    severity: Optional[str] = Query(
        default=None,
        description="Filter by severity level: 'INFO', 'WARNING', 'CRITICAL', or 'all'"
    ),
    instrument_id: Optional[str] = Query(
        default=None,
        description="Filter by instrument identifier"
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
        description="Number of alerts to return per page"
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Pagination offset"
    )
) -> Dict[str, Any]:
    """
    Retrieves stored radiation alerts and data quality warnings from SQLite.
    """
    clean_cat = getattr(category, "default", category)
    clean_sev = getattr(severity, "default", severity)
    clean_inst = getattr(instrument_id, "default", instrument_id)

    raw_limit = getattr(limit, "default", limit)
    try:
        clean_limit = int(raw_limit) if raw_limit is not None else 50
    except (ValueError, TypeError):
        clean_limit = 50

    raw_offset = getattr(offset, "default", offset)
    try:
        clean_offset = int(raw_offset) if raw_offset is not None else 0
    except (ValueError, TypeError):
        clean_offset = 0

    return query_alerts(
        category=clean_cat,
        severity=clean_sev,
        instrument_id=clean_inst,
        limit=clean_limit,
        offset=clean_offset
    )


@app.get(
    "/api/radiation/fields",
    tags=["Radiation Monitoring"],
    summary="Radiation Telemetry Field Dictionary & Units",
    response_description="Definitions, measurement units, and data types for radiation fields"
)
async def get_radiation_field_definitions() -> Dict[str, Any]:
    """
    Returns scientific definitions, data types, and international units of measurement
    for all space radiation fields tracked by the ASTRA CARE system.
    """
    return {
        "status": "success",
        "description": "Standardized radiation telemetry fields from NASA RadLab",
        "fields": RADIATION_FIELD_METADATA
    }


# ============================================================================
# Dynamic Space Radiation Streaming & Machine Learning Endpoints (ASTRA CARE 2.0)
# ============================================================================

@app.post(
    "/api/radiation/stream/reading",
    tags=["Dynamic Radiation Streaming & ML"],
    summary="Ingest Incoming Radiation Telemetry Measurement",
    status_code=status.HTTP_201_CREATED,
    response_description="Enriched radiation measurement with ML anomaly evaluation"
)
async def ingest_incoming_radiation_reading(payload: IncomingRadiationInput) -> Dict[str, Any]:
    """
    Ingests an incoming radiation measurement from a connected sensor, live telemetry feed,
    or simulated client:
    1. Validates measurement values and units.
    2. Executes unsupervised Machine Learning anomaly detection (Isolation Forest).
    3. Evaluates aerospace operational threshold benchmarks (NASA-STD-3001 / NCRP-132).
    4. Persists measurement and evaluated alerts into SQLite.
    """
    data_dict = payload.model_dump()
    ts = data_dict.get("timestamp") or datetime.now(timezone.utc).isoformat()
    inst = data_dict.get("instrument_id") or data_dict.get("detector_id") or "DosTel1"
    dose = float(data_dict["absorbed_dose_rate"])
    flux_val = data_dict.get("flux") or data_dict.get("particle_flux") or (dose * 0.055)
    alt = data_dict.get("altitude") or data_dict.get("altitude_km") or 418.0

    reading_hash = hashlib.sha256(f"{inst}_{ts}_{dose}".encode()).hexdigest()[:12].upper()
    reading_id = f"ING-{inst}-{reading_hash}"

    reading = {
        "reading_id": reading_id,
        "timestamp": ts,
        "instrument_id": inst,
        "detector_id": inst,
        "spacecraft": data_dict.get("spacecraft") or "ISS",
        "module": data_dict.get("module") or "Columbus",
        "absorbed_dose_rate": dose,
        "absorbed_dose_unit": data_dict.get("absorbed_dose_unit") or "µGy/hr",
        "dose_equivalent_rate": data_dict.get("dose_equivalent_rate"),
        "dose_equivalent_unit": data_dict.get("dose_equivalent_unit") or "µSv/hr",
        "flux": flux_val,
        "flux_unit": data_dict.get("flux_unit") or "particles/(cm²·sr·s)",
        "altitude": alt,
        "latitude": data_dict.get("latitude"),
        "longitude": data_dict.get("longitude"),
        "orbital_region": data_dict.get("orbital_region") or "NOMINAL_LEO",
        "data_source": data_dict.get("data_source") or "simulated_streaming",
        "is_simulated": data_dict.get("is_simulated") if data_dict.get("is_simulated") is not None else (data_dict.get("data_source") == "simulated_streaming"),
        "is_live": data_dict.get("data_source") in ("sensor_telemetry", "live_spacecraft"),
        "measurement_quality": data_dict.get("measurement_quality") or "nominal",
        "telemetry_nature": "Dynamic radiation telemetry reading (processed via ML anomaly detection)"
    }

    try:
        enriched = default_radiation_processing_pipeline(reading)
        return {
            "status": "success",
            "message": "Radiation measurement ingested, evaluated via ML model, and stored.",
            "reading": enriched
        }
    except Exception as exc:
        logger.error(f"Error ingesting radiation measurement: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Ingestion Failed", "message": str(exc)}
        )


@app.get(
    "/api/radiation/stream/latest",
    tags=["Dynamic Radiation Streaming & ML"],
    summary="Get Latest Dynamic Radiation Telemetry Reading",
    response_description="Most recent dynamic radiation measurement with ML anomaly evaluation"
)
async def get_latest_stream_reading(
    instrument_id: Optional[str] = Query(default=None, description="Optional filter by detector ID")
) -> Dict[str, Any]:
    """
    Returns the latest dynamic radiation reading from the streaming engine or SQLite.
    Includes machine learning anomaly score, baseline z-score, and plain-language explanation.
    """
    engine = get_stream_engine()
    latest = engine.get_latest()

    # If stream engine hasn't ticked yet or filter specified, consult SQLite
    if not latest or (instrument_id and latest.get("instrument_id") != instrument_id):
        db_latest = get_latest_dynamic_radiation_reading(instrument_id)
        if db_latest:
            latest = db_latest
        elif not latest:
            # Trigger immediate tick to prime cache
            latest = engine.tick_once()

    if not latest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "No Dynamic Readings", "message": "No dynamic radiation readings have been received yet."}
        )

    # Attach detector baseline metadata
    detector = get_detector()
    inst = latest.get("instrument_id", "Unknown")
    baseline = detector.detector_baselines.get(inst, {"mean_dose_rate": 2.0, "std_dose_rate": 0.5})

    return {
        "status": "success",
        "reading": latest,
        "detector_baseline": baseline,
        "stream_status": {
            "is_running": engine.is_running,
            "interval_seconds": engine.interval_seconds,
            "provider_type": engine.provider.provider_type(),
            "is_live": engine.provider.is_live()
        },
        "disclaimer": (
            "Dynamic streaming telemetry provides continuous orbital radiation monitoring. "
            "ML anomaly flags indicate statistical novelty (Isolation Forest) and are distinct from "
            "clinical medical diagnosis or official mission flight rules."
        )
    }


@app.get(
    "/api/radiation/stream/history",
    tags=["Dynamic Radiation Streaming & ML"],
    summary="Retrieve Stored Dynamic Radiation Telemetry History",
    response_description="Paginated list of dynamic radiation measurements"
)
async def get_stream_history(
    instrument_id: Optional[str] = Query(default=None, description="Filter by detector (e.g. DosTel1, Lidal, REM-Lid)"),
    data_source: Optional[str] = Query(default=None, description="Filter by data source (simulated_streaming, sensor_telemetry)"),
    limit: int = Query(default=50, ge=1, le=500, description="Readings per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset")
) -> Dict[str, Any]:
    """
    Retrieves stored dynamic radiation measurements from SQLite with pagination and filtering.
    """
    return query_dynamic_radiation_readings(
        instrument_id=instrument_id,
        data_source=data_source,
        limit=limit,
        offset=offset
    )


@app.get(
    "/api/radiation/ml/status",
    tags=["Dynamic Radiation Streaming & ML"],
    summary="Get Machine Learning Model Status & Metadata",
    response_description="Trained model architecture, training metrics, features, and baselines"
)
async def get_ml_status() -> Dict[str, Any]:
    """
    Returns training information, hyperparameters, contamination rate, feature columns,
    detector baseline statistics, and evaluation metrics for the Isolation Forest radiation model.
    """
    detector = get_detector()
    return {
        "status": "operational" if detector.is_fitted else "standby",
        "is_fitted": detector.is_fitted,
        "model_metadata": detector.metadata,
        "detector_baselines": detector.detector_baselines,
        "feature_columns": detector.metadata.get("feature_columns", []),
        "disclaimer": (
            "ASTRA CARE Radiation Anomaly Detector utilizes unsupervised Isolation Forest modeling. "
            "Anomaly scores represent deviation from historical ISS detector baselines and do NOT invent "
            "unofficial NASA medical or flight rules."
        )
    }


@app.post(
    "/api/radiation/ml/predict",
    tags=["Dynamic Radiation Streaming & ML"],
    summary="Predict Anomaly for Given Radiation Reading",
    response_description="Machine learning prediction, continuous anomaly score, and explanation"
)
async def predict_radiation_anomaly(payload: MLPredictInput) -> Dict[str, Any]:
    """
    Runs real-time machine learning inference on an arbitrary input radiation measurement.
    Returns:
    - is_anomaly (boolean)
    - anomaly_score (continuous decision function; negative = anomalous)
    - severity (NORMAL, ADVISORY_ANOMALY, WARNING_ANOMALY, CRITICAL_ANOMALY)
    - plain-language explainability breakdown
    """
    detector = get_detector()
    reading_dict = payload.model_dump()
    result = detector.predict_reading(reading_dict)
    return {
        "status": "success",
        "input_measurement": reading_dict,
        "prediction": result
    }


@app.get(
    "/api/radiation/ml/anomalies",
    tags=["Dynamic Radiation Streaming & ML"],
    summary="Retrieve Machine Learning Detected Radiation Anomalies",
    response_description="Paginated list of detected anomalies with explainability rationale"
)
async def get_ml_anomalies(
    severity: Optional[str] = Query(default=None, description="Filter by severity (ADVISORY_ANOMALY, WARNING_ANOMALY, CRITICAL_ANOMALY)"),
    instrument_id: Optional[str] = Query(default=None, description="Filter by detector ID"),
    limit: int = Query(default=50, ge=1, le=500, description="Anomalies per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset")
) -> Dict[str, Any]:
    """
    Retrieves stored machine learning radiation anomalies from SQLite.
    Includes feature attribution, baseline Z-scores, and operational recommendations.
    """
    return query_ml_anomalies(
        severity=severity,
        instrument_id=instrument_id,
        limit=limit,
        offset=offset
    )


@app.get(
    "/api/radiation/stream/control",
    tags=["Dynamic Radiation Streaming & ML"],
    summary="Get Radiation Telemetry Streaming Engine Control Status",
    response_description="Engine running status, sampling interval, active provider, and reading counts"
)
async def get_stream_control_status() -> Dict[str, Any]:
    """
    Returns the operational state of the background radiation streaming engine.
    """
    engine = get_stream_engine()
    return {
        "status": "success",
        "engine": engine.get_engine_status()
    }


@app.post(
    "/api/radiation/stream/control",
    tags=["Dynamic Radiation Streaming & ML"],
    summary="Control Radiation Streaming Engine",
    response_description="Updated streaming state after requested control action"
)
async def control_radiation_stream(payload: StreamControlInput) -> Dict[str, Any]:
    """
    Controls the background streaming provider:
    - 'start': Resumes automatic background streaming.
    - 'pause': Halts automatic background streaming.
    - 'tick': Manually steps one reading forward.
    - 'set_interval': Changes sampling interval (1.0 to 60.0s).
    - 'inject_anomaly': Injects test surge (e.g. SOLAR_SPIKE) to test ML detector.
    - 'clear_anomaly': Clears any active injected test event.
    """
    engine = get_stream_engine()
    action = payload.action.lower().strip()
    message = ""

    reading = None
    if action in ("start", "resume"):
        engine.start()
        message = "Radiation streaming engine started."
    elif action in ("pause", "stop"):
        engine.pause()
        message = "Radiation streaming engine paused."
    elif action in ("tick", "step"):
        reading = engine.tick_once()
        message = f"Manually stepped 1 reading: {reading.get('instrument_id') if reading else 'none'}."
    elif action == "set_interval":
        if payload.interval_seconds:
            engine.set_interval(payload.interval_seconds)
            message = f"Sampling interval set to {payload.interval_seconds}s."
    elif action == "inject_anomaly":
        if isinstance(engine.provider, SimulatedStreamingProvider):
            engine.provider.inject_anomaly_event(
                anomaly_type=payload.anomaly_type or "SOLAR_SPIKE",
                duration_readings=payload.duration_ticks or 3,
                magnitude_ugy=payload.anomaly_magnitude or 40.0
            )
            message = f"Injected test radiation anomaly: {payload.anomaly_type} (+{payload.anomaly_magnitude} µGy/hr)."
        else:
            message = "Anomaly injection only supported on SimulatedStreamingProvider."
    elif action == "clear_anomaly":
        if isinstance(engine.provider, SimulatedStreamingProvider):
            engine.provider.clear_injected_anomaly()
            message = "Injected anomaly cleared."
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid Action", "message": f"Unknown streaming control action: '{action}'."}
        )

    return {
        "status": "success",
        "action_executed": action,
        "message": message,
        "reading": reading,
        "engine_status": engine.get_engine_status(),
        "engine": engine.get_engine_status()
    }


@app.get(
    "/api/radiation/telemetry-status",
    tags=["Dynamic Radiation Streaming & ML"],
    summary="Comprehensive Data Source & Telemetry Hardware Status",
    response_description="Real vs simulated vs historical data source classification"
)
async def get_telemetry_status() -> Dict[str, Any]:
    """
    Returns the comprehensive data source classification across all three telemetry tiers:
    1. Historical Research Telemetry (NASA RadLab archive)
    2. Simulated Dynamic Stream (Active demonstration provider)
    3. Real Physical Sensor & Spacecraft Downlink (Standby / Disconnected)
    """
    engine = get_stream_engine()
    hardware_provider = HardwareSensorProvider()
    spacecraft_provider = LiveSpacecraftTelemetryProvider()

    stats = get_db_statistics()

    return {
        "status": "success",
        "provider_type": engine.provider.provider_type(),
        "sensor_hardware": hardware_provider.get_status(),
        "spacecraft_link": spacecraft_provider.get_status(),
        "active_data_source": {
            "source_id": engine.provider.provider_type(),
            "is_live": engine.provider.is_live(),
            "is_simulated": True if engine.provider.provider_type() == "simulated_streaming" else False,
            "label": "Physics-Grounded Simulated Spacecraft Stream (Development & Demonstration)",
            "details": engine.provider.get_status()
        },
        "available_sources": {
            "historical_archive": {
                "name": "NASA Open Science Data Repository (OSDR) RadLab Archive",
                "status": "connected_local_and_api",
                "telemetry_nature": "Historical scientific records (recorded aboard ISS; not live)",
                "records_stored": stats.get("stored_radiation_records_count", 0)
            },
            "simulated_stream": {
                "name": "ASTRA CARE Physics-Based Orbital Streaming Provider",
                "status": "active_streaming" if engine.is_running else "paused",
                "sample_interval_seconds": engine.interval_seconds,
                "is_simulated": True
            },
            "physical_hardware_sensor": hardware_provider.get_status(),
            "live_spacecraft_telemetry": spacecraft_provider.get_status()
        },
        "scientific_integrity_notice": (
            "In compliance with scientific accuracy standards, simulated telemetry is strictly labeled "
            "as simulated demonstration data. Physical radiation hardware sensors and live orbital downlinks "
            "are currently in standby. Historical NASA measurements are never presented as real-time readings."
        )
    }


# ============================================================================
# AI Health Assistant Endpoints (Task 04)
# ============================================================================

@app.post(
    "/api/assistant/chat",
    tags=["AI Health Assistant"],
    summary="Chat with AI Health and Radiation Assistant",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    response_description="Contextual, safety-conscious explanations of radiation, vital signs, and safety alerts"
)
async def chat_with_assistant(payload: ChatRequest) -> Dict[str, Any]:
    """
    Conversational assistant for astronauts and flight controllers.

    Capabilities:
    1. Explains space radiation measurements (absorbed dose in µGy/hr, dose equivalent in µSv/hr) and units.
    2. Explains astronaut vitals (Heart rate BPM, Blood pressure mmHg, SpO2 %, Core body temp °C).
    3. Explains the difference between normal, unusual, and unavailable telemetry.
    4. Explains available radiation alerts and clinical health alerts.
    5. Provides safe operational guidance (verifying sensors, following flight rules, contacting the Flight Surgeon).
    6. Explains the importance of continuous health monitoring in space.
    7. Answers questions using available SQLite project data and context.

    Safety Guardrails:
    - Strictly non-diagnostic and non-prescriptive.
    - Never invents official NASA medical limits or operational flight rules.
    - Never issues unauthorized emergency vehicle or abort commands.
    - Transparently distinguishes historical research data, simulated demo vitals, and sensor feeds.
    - Operates 100% offline with zero external API key requirements.
    """
    clean_message = payload.message.strip() if payload.message else ""
    if not clean_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Invalid Message",
                "message": "Message field cannot be empty or whitespace only.",
                "disclaimer": ASSISTANT_DISCLAIMER
            }
        )

    try:
        response = generate_assistant_response(
            message=clean_message,
            astronaut_id=payload.astronaut_id
        )
        return response.model_dump()
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Validation Error", "message": str(val_err)}
        )
    except Exception as exc:
        logger.error(f"Error processing assistant chat: {exc}")
        return {
            "answer": (
                "The AI Assistant encountered a temporary database or telemetry processing issue. "
                "For critical telemetry inquiries or physiological concerns, please consult the "
                "Mission Flight Surgeon and Biomedical Engineer (BME) directly."
            ),
            "source": "knowledge_base",
            "status": "warning",
            "data_context": {"error_type": type(exc).__name__, "detail": str(exc)},
            "disclaimer": ASSISTANT_DISCLAIMER
        }


@app.get(
    "/api/assistant/status",
    tags=["AI Health Assistant"],
    summary="Local AI Assistant Connection & Offline Status Check",
    response_description="Status of local Ollama AI model, network mode, and fallback engine"
)
async def get_assistant_status() -> Dict[str, Any]:
    """
    Returns the operational status of the local AI assistant.
    Verifies if Ollama is running locally on 127.0.0.1:11434 or if the system
    is operating in local fallback mode. Reports network status (online vs offline).
    Runs 100% offline with zero cloud access.
    """
    from app.assistant import check_ollama_status
    status_info = check_ollama_status()
    try:
        from app.offline_speech import get_offline_voice_system_status
        voice_status = get_offline_voice_system_status()
        status_info["voice"] = voice_status
        is_online = voice_status.get("is_online", False)
        status_info["is_online"] = is_online
        status_info["network_indicator"] = "ONLINE – INTERNET AVAILABLE" if is_online else "OFFLINE – LOCAL SERVICES ACTIVE"
    except Exception:
        status_info["voice"] = {"indicator_text": "VOICE INPUT UNAVAILABLE", "status": "input_unavailable"}
        status_info["is_online"] = False
        status_info["network_indicator"] = "OFFLINE – LOCAL SERVICES ACTIVE"
    return status_info


@app.get(
    "/api/system/network-status",
    tags=["General"],
    summary="Internet & Network Connectivity Mode Check",
    response_description="Online vs offline mode status with aerospace indicators"
)
async def get_system_network_status() -> Dict[str, Any]:
    """
    Quickly checks internet connectivity to distinguish between ONLINE and OFFLINE modes.
    Non-blocking and cached for 4 seconds.
    """
    from app.offline_speech import check_internet_connectivity
    is_online = await run_in_threadpool(check_internet_connectivity)
    return {
        "is_online": is_online,
        "mode": "online" if is_online else "offline",
        "indicator_text": "ONLINE – INTERNET AVAILABLE" if is_online else "OFFLINE – LOCAL SERVICES ACTIVE",
        "local_services_active": True,
        "nasa_sync_available": is_online,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


class TextToSpeechInput(BaseModel):
    text: str = Field(..., min_length=1, description="Text to synthesize into spoken audio", json_schema_extra={"example": "Your latest heart rate is 75 BPM."})
    voice_id: Optional[str] = Field(None, description="Optional local TTS voice identifier")
    rate: Optional[int] = Field(175, ge=100, le=250, description="Speech rate in words per minute (default 175)")


@app.get(
    "/api/assistant/voice-status",
    tags=["AI Health Assistant"],
    summary="Offline Voice Assistant Operational Status",
    response_description="Status of local Vosk STT model and pyttsx3 SAPI5 TTS engine"
)
@app.get(
    "/api/assistant/voice/status",
    tags=["AI Health Assistant"],
    summary="Offline Voice Assistant Operational Status (Alias)",
    response_description="Status of local Vosk STT model and pyttsx3 SAPI5 TTS engine"
)
async def get_offline_voice_status() -> Dict[str, Any]:
    """
    Reports operational readiness of local speech components:
    - OFFLINE VOICE READY: both local Vosk STT and pyttsx3 SAPI5 TTS available
    - INITIAL SETUP REQUIRED: local Vosk model missing
    - VOICE INPUT UNAVAILABLE: microphone or Vosk STT unavailable
    - VOICE OUTPUT UNAVAILABLE: local TTS engine unavailable
    - ONLINE – INTERNET AVAILABLE / OFFLINE – LOCAL SERVICES ACTIVE
    """
    from app.offline_speech import get_offline_voice_system_status
    return await run_in_threadpool(get_offline_voice_system_status)


@app.post(
    "/api/assistant/voice-to-text",
    tags=["AI Health Assistant"],
    summary="Offline Speech-to-Text Recognition (Vosk)",
    response_description="Transcribed text from uploaded audio"
)
async def voice_to_text(
    request: Request,
    file: Optional[UploadFile] = File(None)
) -> Dict[str, Any]:
    """
    Converts user microphone speech audio into text using local Vosk.
    100% offline; zero cloud network calls.
    Accepts multipart/form-data with 'file', or raw audio bytes in request body.
    Executed in threadpool worker to prevent blocking FastAPI event loop.
    """
    audio_bytes = b""
    if file is not None:
        try:
            audio_bytes = await file.read()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "File Read Error", "message": f"Could not read uploaded audio: {exc}"}
            )
    else:
        try:
            audio_bytes = await request.body()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Body Read Error", "message": f"Could not read request body: {exc}"}
            )

    if not audio_bytes or len(audio_bytes) < 44:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid Audio", "message": "Uploaded audio is empty or missing audio data."}
        )

    try:
        from app.offline_speech import (
            transcribe_audio_bytes,
            VoskModelNotFoundError,
            AudioProcessingError
        )
        result = await run_in_threadpool(transcribe_audio_bytes, audio_bytes)
        return result
    except VoskModelNotFoundError as v_err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "Vosk Model Not Found",
                "message": str(v_err),
                "indicator_text": "INITIAL SETUP REQUIRED"
            }
        )
    except AudioProcessingError as a_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "Audio Processing Error", "message": str(a_err)}
        )
    except Exception as exc:
        logger.error(f"Error during offline voice transcription: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Transcription Error", "message": str(exc)}
        )


@app.post(
    "/api/assistant/text-to-speech",
    tags=["AI Health Assistant"],
    summary="Offline Text-to-Speech Synthesis (pyttsx3 Windows SAPI5)",
    response_description="WAV audio bytes synthesized locally"
)
async def text_to_speech(payload: TextToSpeechInput):
    """
    Generates spoken audio from assistant text response using local pyttsx3 with Windows SAPI5.
    100% offline; zero cloud network calls.
    Returns audio/wav format.
    Executed in threadpool worker to prevent blocking FastAPI event loop.
    Supports arbitrarily long responses without audio cutoffs via seamless chunking.
    """
    clean_text = payload.text.strip() if payload.text else ""
    if not clean_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid Text", "message": "Text field cannot be empty or whitespace only."}
        )

    try:
        from app.offline_speech import synthesize_speech_wav, TTSEngineError
        wav_bytes = await run_in_threadpool(
            synthesize_speech_wav,
            clean_text,
            payload.voice_id,
            payload.rate or 175
        )
        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "inline; filename=speech.wav",
                "Content-Length": str(len(wav_bytes))
            }
        )
    except TTSEngineError as tts_err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "TTS Engine Error",
                "message": str(tts_err),
                "indicator_text": "VOICE OUTPUT UNAVAILABLE"
            }
        )
    except Exception as exc:
        logger.error(f"Error during TTS synthesis: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "TTS Synthesis Error", "message": str(exc)}
        )
    except TTSEngineError as tts_err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "TTS Engine Error",
                "message": str(tts_err),
                "indicator_text": "VOICE OUTPUT UNAVAILABLE"
            }
        )
    except Exception as exc:
        logger.error(f"Error during TTS synthesis: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "TTS Synthesis Error", "message": str(exc)}
        )


# ============================================================================
# FEATURE 1: NASA RADLAB LATEST DATA INTEGRATION
# ============================================================================

@app.get(
    "/api/radiation/nasa/latest",
    tags=["NASA RadLab Live Integration"],
    summary="Retrieve Latest NASA RadLab Data",
    status_code=status.HTTP_200_OK,
    response_description="Latest available authentic radiation measurements across ISS detectors"
)
async def get_latest_nasa_radlab_records(
    limit: int = Query(120, ge=1, le=500, description="Maximum records to retrieve"),
    allow_fallback: bool = Query(True, description="Allow verified local archive fallback if NASA API times out")
) -> Dict[str, Any]:
    """
    Fetches the latest space radiation measurements from the official NASA RadLab API.
    Covers detectors DosTel1, DosTel2, Lidal, and REM-Lid.
    Includes separate timestamps: original NASA measurement timestamp vs. retrieval timestamp.
    Strictly classified as historical scientific archives.
    """
    try:
        data = fetch_latest_nasa_radlab_data(limit=limit, allow_fallback=allow_fallback)
        return data
    except Exception as exc:
        logger.error(f"Error fetching latest NASA RadLab data: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "NASA RadLab API Unavailable",
                "message": str(exc),
                "disclaimer": "External NASA OSDR service may be experiencing connectivity issues or maintenance."
            }
        )


@app.post(
    "/api/radiation/nasa/sync",
    tags=["NASA RadLab Live Integration"],
    summary="Trigger On-Demand NASA RadLab Sync",
    status_code=status.HTTP_200_OK,
    response_description="Sync execution results, new records stored, and status"
)
async def trigger_nasa_radlab_sync(payload: Optional[NasaSyncRequestInput] = None) -> Dict[str, Any]:
    """
    Triggers an on-demand synchronization with the NASA RadLab API, deduplicating
    records and updating the SQLite repository and smart alerts.
    """
    sync_service = get_nasa_sync_service()
    start_time = payload.start_time if payload else None
    end_time = payload.end_time if payload else None
    spacecraft = payload.spacecraft if payload else "ISS"
    limit = payload.limit if payload else 120

    try:
        result = sync_service.sync_once(
            start_time=start_time,
            end_time=end_time,
            spacecraft=spacecraft,
            limit=limit
        )
        # Update smart alerts based on newly synced data
        sync_and_generate_smart_alerts()
        return {
            "status": "success",
            "message": "NASA RadLab synchronization completed successfully.",
            "sync_details": result
        }
    except Exception as exc:
        logger.error(f"Error during on-demand NASA RadLab sync: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Sync Execution Error",
                "message": str(exc)
            }
        )


@app.get(
    "/api/radiation/nasa/sync-status",
    tags=["NASA RadLab Live Integration"],
    summary="Check NASA RadLab Sync Status",
    status_code=status.HTTP_200_OK,
    response_description="Status of background worker and recent synchronization logs"
)
async def get_nasa_sync_status(
    log_limit: int = Query(20, ge=1, le=100, description="Number of recent sync logs to retrieve")
) -> Dict[str, Any]:
    """
    Returns the running state of the automated background sync service and audit history.
    """
    sync_service = get_nasa_sync_service()
    status_info = sync_service.get_status()
    logs_res = query_nasa_sync_logs(limit=log_limit)
    log_items = logs_res.get("logs", []) if isinstance(logs_res, dict) else logs_res
    return {
        "status": "success",
        "service_state": status_info,
        "recent_sync_logs": log_items,
        "total_syncs": logs_res.get("total_syncs", len(log_items)) if isinstance(logs_res, dict) else len(log_items)
    }


# ============================================================================
# FEATURE 2: RADIATION LOCATION TRACKING
# ============================================================================

@app.get(
    "/api/radiation/locations",
    tags=["Radiation Location Tracking"],
    summary="Query Radiation Location Points",
    status_code=status.HTTP_200_OK,
    response_description="Geographic coordinates, altitude, orbital region, and radiation dose rate"
)
async def get_radiation_locations(
    limit: int = Query(200, ge=1, le=2000, description="Max location points"),
    orbital_region: Optional[str] = Query(None, description="'SOUTH_ATLANTIC_ANOMALY' or 'NOMINAL_LEO'")
) -> Dict[str, Any]:
    """
    Returns authentic radiation telemetry mapped to geographic coordinates (lat, lon, altitude)
    and classified into orbital regions (South Atlantic Anomaly vs Nominal LEO).
    """
    loc_res = query_radiation_locations(limit=limit, orbital_region=orbital_region)
    loc_list = loc_res.get("locations", []) if isinstance(loc_res, dict) else loc_res
    saa_bounds = {
        "name": "South Atlantic Anomaly (SAA)",
        "latitude_range": [-45.0, -5.0],
        "longitude_range": [-90.0, 0.0],
        "polygon_coordinates": [
            [-45.0, -90.0],
            [-5.0, -90.0],
            [-5.0, 0.0],
            [-45.0, 0.0],
            [-45.0, -90.0]
        ],
        "description": "Geomagnetic depression in Van Allen inner radiation belt where trapped energetic proton flux increases significantly."
    }
    return {
        "status": "success",
        "total_points": len(loc_list),
        "orbital_region_filter": orbital_region,
        "saa_boundary_definition": saa_bounds,
        "locations": loc_list,
        "scientific_integrity_notice": "All coordinates and dose rates are authentic historical telemetry from NASA RadLab or dynamic streaming simulation."
    }


# ============================================================================
# FEATURE 3: RADIATION TREND FORECASTING
# ============================================================================

@app.get(
    "/api/radiation/forecast",
    tags=["Radiation Forecasting"],
    summary="Get Space Radiation Trend Forecast",
    status_code=status.HTTP_200_OK,
    response_description="Point predictions, 95% confidence intervals, and orbital harmonics"
)
async def get_radiation_forecast(
    detector_id: str = Query("DosTel1", description="Detector identifier e.g. DosTel1, DosTel2, Lidal"),
    horizon_steps: int = Query(16, ge=4, le=100, description="Forecast steps ahead"),
    step_minutes: float = Query(5.0, ge=1.0, le=60.0, description="Time step in minutes")
) -> Dict[str, Any]:
    """
    Generates a physics-aware machine learning forecast for space radiation levels.
    Incorporates ISS 92.68-minute orbital harmonics and autoregressive lag terms.
    Provides expanding 95% confidence uncertainty margins.
    """
    try:
        forecast = generate_radiation_forecast(
            detector_id=detector_id,
            horizon_steps=horizon_steps,
            step_minutes=step_minutes
        )
        return forecast
    except Exception as exc:
        logger.error(f"Error generating radiation forecast: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Forecast Generation Error", "message": str(exc)}
        )


@app.post(
    "/api/radiation/forecast/generate",
    tags=["Radiation Forecasting"],
    summary="Generate Custom Radiation Forecast",
    status_code=status.HTTP_200_OK,
    response_description="Point predictions and confidence bounds from custom parameters"
)
async def post_generate_radiation_forecast(payload: ForecastRequestInput) -> Dict[str, Any]:
    """
    POST endpoint to generate a custom space radiation forecast.
    """
    try:
        forecast = generate_radiation_forecast(
            detector_id=payload.detector_id or "DosTel1",
            horizon_steps=payload.horizon_steps or 16,
            step_minutes=payload.step_minutes or 5.0
        )
        return forecast
    except Exception as exc:
        logger.error(f"Error generating radiation forecast: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Forecast Generation Error", "message": str(exc)}
        )


# ============================================================================
# FEATURE 4: SMART ALERT EXPLANATION SYSTEM
# ============================================================================

@app.get(
    "/api/alerts/smart",
    tags=["Smart Alerts"],
    summary="Query Enriched Smart Alerts",
    status_code=status.HTTP_200_OK,
    response_description="Smart alerts with root-cause explanations and safe operational follow-ups"
)
async def get_smart_alerts(
    limit: int = Query(50, ge=1, le=200, description="Maximum alerts to retrieve"),
    severity: Optional[str] = Query(None, description="'CRITICAL', 'WARNING', 'ADVISORY', 'INFO'"),
    category: Optional[str] = Query(None, description="'RADIATION_THRESHOLD', 'ML_STATISTICAL_ANOMALY', 'HEALTH_VITALS_ADVISORY'")
) -> Dict[str, Any]:
    """
    Queries enriched smart alerts with root causes, responsible measurements, threshold deltas,
    and concrete operational recommendations.
    """
    alerts_res = query_smart_alerts(limit=limit, severity=severity, category=category)
    alert_items = alerts_res.get("alerts", []) if isinstance(alerts_res, dict) else alerts_res
    total = alerts_res.get("total_alerts", len(alert_items)) if isinstance(alerts_res, dict) else len(alert_items)
    return {
        "status": "success",
        "total_alerts": total,
        "filter_severity": severity,
        "filter_category": category,
        "alerts": alert_items,
        "non_diagnostic_notice": "Alerts provide operational engineering triage recommendations and do not diagnose medical pathologies."
    }


@app.post(
    "/api/alerts/evaluate",
    tags=["Smart Alerts"],
    summary="Trigger Smart Alert Evaluation",
    status_code=status.HTTP_200_OK,
    response_description="Triggers evaluation of current database records and populates new smart alerts"
)
async def trigger_smart_alert_evaluation(payload: Optional[SmartAlertEvalInput] = None) -> Dict[str, Any]:
    """
    Scans radiation and ML telemetry records to identify new threshold exceedances or statistical anomalies.
    """
    try:
        inserted_count = sync_and_generate_smart_alerts()
        recent_res = query_smart_alerts(limit=25)
        recent_list = recent_res.get("alerts", []) if isinstance(recent_res, dict) else recent_res
        return {
            "status": "success",
            "message": f"Smart alert evaluation completed. Processed/inserted {inserted_count} alerts.",
            "newly_inserted_count": inserted_count,
            "recent_alerts": recent_list
        }
        return {
            "status": "success",
            "message": f"Smart alert evaluation completed. Processed/inserted {inserted_count} alerts.",
            "newly_inserted_count": inserted_count,
            "recent_alerts": recent_alerts
        }
    except Exception as exc:
        logger.error(f"Error evaluating smart alerts: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Alert Evaluation Error", "message": str(exc)}
        )


# ============================================================================
# FEATURE 5: MULTI-DETECTOR COMPARISON
# ============================================================================

@app.get(
    "/api/radiation/detectors/comparison",
    tags=["Multi-Detector Comparison"],
    summary="Compare Multi-Detector Radiation Telemetry",
    status_code=status.HTTP_200_OK,
    response_description="Synchronized time-series, shielding attenuation ratios, and detector statistics"
)
async def get_multi_detector_comparison(
    detectors: Optional[str] = Query(None, description="Comma-separated detector IDs e.g. 'DosTel1,DosTel2,Lidal,REM-Lid'"),
    limit: int = Query(30, ge=5, le=100, description="Telemetry points per detector")
) -> Dict[str, Any]:
    """
    Compares telemetry across multiple ISS radiation instruments.
    Analyzes differences in absorbed dose rate, dose-equivalent, and particle flux.
    Computes DosTel2 vs DosTel1 water-wall shielding attenuation ratio.
    """
    det_list = None
    if detectors:
        det_list = [d.strip() for d in detectors.split(",") if d.strip()]
    comparison = get_detector_time_series_comparison(detectors=det_list, limit_per_detector=limit)
    return comparison


@app.get(
    "/api/radiation/detectors/list",
    tags=["Multi-Detector Comparison"],
    summary="List ISS Radiation Detectors Specifications",
    status_code=status.HTTP_200_OK,
    response_description="Detector specifications, module locations, and shielding geometries"
)
async def get_radiation_detectors_list() -> Dict[str, Any]:
    """
    Returns technical specifications, mounting locations, and scientific shielding context
    for all monitored ISS radiation detectors.
    """
    detectors = [
        {
            "detector_id": "DosTel1",
            "name": "DOSTEL 1 (Dose Telescope 1)",
            "spacecraft": "ISS",
            "module": "Columbus (Starboard Bulkhead)",
            "shielding_al_eq": 15.0,
            "shielding_description": "Standard European module aluminum bulkhead hull (~15 g/cm² Al-eq)",
            "channels": ["absorbed_dose_rate (µGy/hr)", "flux (particles/(cm²·sr·s))", "dose_equivalent_rate (µSv/hr)"],
            "sensor_type": "Passivated Implanted Planar Silicon (PIPS) Telescope",
            "notes": "Provides reference baseline external module ionizing exposure."
        },
        {
            "detector_id": "DosTel2",
            "name": "DOSTEL 2 (Dose Telescope 2)",
            "spacecraft": "ISS",
            "module": "Columbus (Forward Bulkhead)",
            "shielding_al_eq": 22.0,
            "shielding_description": "Bulkhead hull augmented by adjacent crew water stowage bags (~22 g/cm² Al-eq)",
            "channels": ["absorbed_dose_rate (µGy/hr)", "flux (particles/(cm²·sr·s))", "dose_equivalent_rate (µSv/hr)"],
            "sensor_type": "Passivated Implanted Planar Silicon (PIPS) Telescope",
            "notes": "Matched DOSTEL detector; consistently measures 10-25% lower dose due to hydrogenous secondary particle moderation by water wall."
        },
        {
            "detector_id": "Lidal",
            "name": "LIDAL (Light Ion Detector for ALTEA)",
            "spacecraft": "ISS",
            "module": "Columbus (Central Overhead)",
            "shielding_al_eq": 18.0,
            "shielding_description": "Central module location surrounded by scientific experiment racks (~18 g/cm² Al-eq)",
            "channels": ["absorbed_dose_rate (µGy/hr)", "particle_flux", "ion_time_of_flight"],
            "sensor_type": "Silicon Strip Detector paired with fast plastic scintillation Time-of-Flight (ToF) bar",
            "notes": "Measures particle velocity and atomic number (Z) charge discrimination for light and heavy cosmic ray ions."
        },
        {
            "detector_id": "REM-Lid",
            "name": "REM-Lid (Radiation Environment Monitor)",
            "spacecraft": "ISS",
            "module": "Columbus / US Lab Destiny",
            "shielding_al_eq": 17.0,
            "shielding_description": "Internal pressurized cabin bulkhead (~17 g/cm² Al-eq)",
            "channels": ["absorbed_dose_rate (µGy/hr)", "microdosimetric_spectra"],
            "sensor_type": "High-pressure tissue-equivalent ionization chamber / solid state",
            "notes": "Measures microdosimetric radiation energy deposition in tissue-equivalent geometry."
        },
        {
            "detector_id": "DB8",
            "name": "DB-8 (Pille-MKS Dosimetry System)",
            "spacecraft": "ISS",
            "module": "Russian Service Module (Zvezda, Crew Quarters)",
            "shielding_al_eq": 28.0,
            "shielding_description": "Interior sleeping quarters surrounded by dense equipment racks and life-support subsystems (~28 g/cm² Al-eq)",
            "channels": ["absorbed_dose_rate (µGy/hr)", "cumulative_dose (mGy)"],
            "sensor_type": "Thermoluminescent dosimeter reader with real-time scintillation counters",
            "notes": "Monitors radiation exposure in crew sleeping quarters."
        }
    ]
    return {
        "status": "success",
        "total_detectors": len(detectors),
        "detectors": detectors,
        "calibration_notice": "Detectors have different physical geometries, active areas, and threshold sensitivities. Cross-detector comparisons should account for shielding differences."
    }


# ============================================================================
# FEATURE 6: ASTRONAUT HEALTH AND RADIATION REPORTS
# ============================================================================

@app.get(
    "/api/reports/preview",
    tags=["Astronaut Reports"],
    summary="Preview Astronaut Health and Radiation Report",
    status_code=status.HTTP_200_OK,
    response_description="Structured JSON preview of astronaut health vitals, dosimetry, and alerts"
)
async def preview_astronaut_report(
    astronaut_id: str = Query("AST-01", description="Astronaut identifier e.g. AST-01, AST-02")
) -> Dict[str, Any]:
    """
    Compiles structured report data for previewing before PDF generation.
    Clearly marks simulated demonstration data vs historical NASA scientific archive.
    """
    try:
        report_data = compile_astronaut_report_data(astronaut_id=astronaut_id)
        return {
            "status": "success",
            "report_data": report_data
        }
    except Exception as exc:
        logger.error(f"Error compiling report data: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Report Preview Error", "message": str(exc)}
        )


@app.get(
    "/api/reports/pdf",
    tags=["Astronaut Reports"],
    summary="Download Astronaut Health and Radiation PDF Report",
    status_code=status.HTTP_200_OK,
    response_description="Downloadable binary PDF report"
)
async def download_astronaut_pdf_report(
    astronaut_id: str = Query("AST-01", description="Astronaut identifier e.g. AST-01, AST-02")
):
    """
    Generates a professional, print-ready PDF health and radiation report for the specified astronaut.
    Includes flight metadata, vitals table, radiation dosimetry, ML anomalies, and safety disclaimers.
    """
    try:
        pdf_bytes = generate_astronaut_pdf_report(astronaut_id=astronaut_id)
        filename = f"ASTRA_CARE_Report_{astronaut_id}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "application/pdf"
            }
        )
    except Exception as exc:
        logger.error(f"Error generating PDF report: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "PDF Generation Error", "message": str(exc)}
        )

