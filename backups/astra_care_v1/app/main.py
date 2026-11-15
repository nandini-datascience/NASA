"""
main.py - ASTRA CARE: Astronaut Health and Space Radiation Monitoring System Backend

FastAPI Application Entry Point.
Run with:
    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager
import logging
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
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
    query_radiation_history
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

    yield
    logger.info("ASTRA CARE backend shutting down.")


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
        "system_name": "Astronaut Health and Space Radiation Monitoring System",
        "version": "3.0.0",
        "status": "operational",
        "modules": {
            "radiation_monitoring": "NASA RadLab Radiation Telemetry, Analysis, and Dosimetry Alerts",
            "astronaut_health_monitoring": "Crew Vitals Telemetry, Physiological Validation, and Medical Guidance Alerts",
            "ai_health_assistant": "Interactive Space Health & Radiation Plain-Language Assistant"
        },
        "database_status": {
            "type": "SQLite",
            "radiation_records_stored": stats["stored_radiation_records_count"],
            "radiation_alerts_stored": stats["stored_radiation_alerts_count"],
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
            "health_measurements_get": "/api/health/measurements",
            "health_measurements_post": "/api/health/measurements",
            "health_history": "/api/health/history",
            "health_alerts": "/api/health/alerts",
            "radiation_field_definitions": "/api/radiation/fields",
            "assistant_chat": "/api/assistant/chat",
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
