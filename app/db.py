"""
db.py - SQLite Database Storage Layer for ASTRA CARE

Handles persistence of authentic space radiation records and generated alerts.
Guarantees duplicate prevention using SQLite UNIQUE constraints and indexes.
Preserves original timestamps, measurement units, and source attribution.
"""

import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("astra_care.db")

# Default SQLite database path
DATABASE_DIR = Path(__file__).resolve().parent.parent / "datasets"
DATABASE_PATH = DATABASE_DIR / "astra_care.db"


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Creates and returns a thread-safe connection to the SQLite database.
    Enables foreign keys and returns rows as dictionary-like Row objects.
    """
    target_path = db_path or DATABASE_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """
    Initializes database schema with required tables and indexes:
    - radiation_records: stores space telemetry records with unique constraint
    - radiation_alerts: stores data quality warnings and health risk alerts
    """
    conn = get_db_connection(db_path)
    try:
        with conn:
            # 1. Table for authentic radiation records
            conn.execute("""
            CREATE TABLE IF NOT EXISTS radiation_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                instrument_id TEXT NOT NULL,
                spacecraft TEXT DEFAULT 'ISS',
                module TEXT,
                absorbed_dose_rate REAL,
                absorbed_dose_unit TEXT DEFAULT 'µGy/hr',
                dose_equivalent_rate REAL,
                dose_equivalent_unit TEXT DEFAULT 'µSv/hr',
                flux REAL,
                flux_unit TEXT DEFAULT 'particles/(cm²·sr·s)',
                altitude REAL,
                altitude_unit TEXT DEFAULT 'km',
                latitude REAL,
                longitude REAL,
                source_origin TEXT NOT NULL,
                is_historical INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(timestamp, instrument_id, spacecraft)
            );
            """)

            # Indexes for high-performance time-series and instrument lookups
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_records_time 
            ON radiation_records(timestamp);
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_records_instrument 
            ON radiation_records(instrument_id);
            """)

            # 2. Table for generated alerts and data-quality warnings
            conn.execute("""
            CREATE TABLE IF NOT EXISTS radiation_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,           -- 'DATA_QUALITY_WARNING' or 'HEALTH_RISK_ALERT'
                severity TEXT NOT NULL,           -- 'INFO', 'WARNING', 'CRITICAL'
                alert_type TEXT NOT NULL,         -- 'ELEVATED_DOSE_RATE', 'HIGH_DOSE_RATE', etc.
                timestamp TEXT NOT NULL,
                instrument_id TEXT,
                spacecraft TEXT DEFAULT 'ISS',
                metric_name TEXT,
                metric_value REAL,
                threshold_applied REAL,
                unit TEXT,
                description TEXT NOT NULL,
                recommendation TEXT,
                guideline_reference TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(alert_type, timestamp, instrument_id, category)
            );
            """)

            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_category 
            ON radiation_alerts(category);
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_severity 
            ON radiation_alerts(severity);
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_time 
            ON radiation_alerts(timestamp);
            """)

            # 3. Table for astronaut health measurements (Task 03)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS astronaut_health_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT UNIQUE NOT NULL,
                astronaut_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                heart_rate REAL,
                heart_rate_unit TEXT DEFAULT 'BPM',
                blood_pressure_systolic REAL,
                blood_pressure_diastolic REAL,
                blood_pressure_unit TEXT DEFAULT 'mmHg',
                oxygen_saturation REAL,
                oxygen_saturation_unit TEXT DEFAULT '%',
                body_temperature REAL,
                body_temperature_unit TEXT DEFAULT '°C',
                source_device TEXT DEFAULT 'Wearable Crew Health Monitor',
                data_classification TEXT NOT NULL, -- 'simulated_demo', 'historical_study', 'sensor_telemetry'
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(astronaut_id, timestamp)
            );
            """)

            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_health_astronaut 
            ON astronaut_health_records(astronaut_id);
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_health_time 
            ON astronaut_health_records(timestamp);
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_health_class 
            ON astronaut_health_records(data_classification);
            """)

            # 4. Table for astronaut health alerts (Task 03)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS astronaut_health_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT UNIQUE NOT NULL,
                astronaut_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                category TEXT NOT NULL,           -- 'PHYSIOLOGICAL_WARNING', 'CRITICAL_VITALS_ALERT', 'DATA_QUALITY_WARNING'
                severity TEXT NOT NULL,           -- 'INFO', 'WARNING', 'CRITICAL'
                alert_type TEXT NOT NULL,         -- 'BRADYCARDIA', 'TACHYCARDIA', 'HYPOTENSION', etc.
                metric_name TEXT,
                metric_value TEXT,
                threshold_applied TEXT,
                unit TEXT,
                description TEXT NOT NULL,
                explanation TEXT NOT NULL,
                recommendation TEXT,
                guideline_reference TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(alert_type, timestamp, astronaut_id)
            );
            """)

            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_health_alerts_astronaut 
            ON astronaut_health_alerts(astronaut_id);
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_health_alerts_severity 
            ON astronaut_health_alerts(severity);
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_health_alerts_time 
            ON astronaut_health_alerts(timestamp);
            """)

            # 5. Table for dynamic streaming radiation telemetry (ASTRA CARE 2.0)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS dynamic_radiation_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reading_id TEXT UNIQUE NOT NULL,
                timestamp TEXT NOT NULL,
                instrument_id TEXT NOT NULL,
                spacecraft TEXT DEFAULT 'ISS',
                module TEXT,
                absorbed_dose_rate REAL NOT NULL,
                absorbed_dose_unit TEXT DEFAULT 'µGy/hr',
                dose_equivalent_rate REAL,
                dose_equivalent_unit TEXT DEFAULT 'µSv/hr',
                flux REAL,
                flux_unit TEXT DEFAULT 'particles/(cm²·sr·s)',
                altitude REAL,
                latitude REAL,
                longitude REAL,
                orbital_region TEXT DEFAULT 'NOMINAL_LEO',
                data_source TEXT NOT NULL,       -- 'simulated_streaming', 'sensor_telemetry', 'live_spacecraft'
                is_simulated INTEGER DEFAULT 1,
                is_live INTEGER DEFAULT 0,
                measurement_quality TEXT DEFAULT 'nominal',
                ml_is_anomaly INTEGER DEFAULT 0,
                ml_anomaly_score REAL DEFAULT 0.0,
                ml_severity TEXT DEFAULT 'NORMAL',
                ml_anomaly_reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)

            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dynamic_time 
            ON dynamic_radiation_records(timestamp);
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dynamic_instrument 
            ON dynamic_radiation_records(instrument_id);
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dynamic_source 
            ON dynamic_radiation_records(data_source);
            """)

            # 6. Table for Machine Learning Anomaly Records (ASTRA CARE 2.0)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_anomaly_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anomaly_id TEXT UNIQUE NOT NULL,
                reading_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                instrument_id TEXT NOT NULL,
                absorbed_dose_rate REAL NOT NULL,
                unit TEXT DEFAULT 'µGy/hr',
                anomaly_score REAL NOT NULL,
                severity TEXT NOT NULL,           -- 'ADVISORY_ANOMALY', 'WARNING_ANOMALY', 'CRITICAL_ANOMALY'
                primary_contributing_feature TEXT,
                baseline_z_score REAL,
                dose_rate_delta REAL,
                explanation TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                data_source TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)

            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ml_anomaly_time 
            ON ml_anomaly_records(timestamp);
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ml_anomaly_sev 
            ON ml_anomaly_records(severity);
            """)

            # 7. Table for NASA RadLab API Sync Logs (Feature 1)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS nasa_sync_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_id TEXT UNIQUE NOT NULL,
                sync_timestamp TEXT NOT NULL,
                status TEXT NOT NULL,          -- 'SUCCESS', 'FALLBACK', 'ERROR'
                source TEXT NOT NULL,          -- 'NASA_OSDR_RADLAB_API' or 'LOCAL_ARCHIVE'
                records_fetched INTEGER DEFAULT 0,
                new_records_inserted INTEGER DEFAULT 0,
                detectors_detected TEXT,
                temporal_window_start TEXT,
                temporal_window_end TEXT,
                duration_ms REAL,
                message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 8. Table for Smart Alert Explanations (Feature 4)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS smart_alert_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT UNIQUE NOT NULL,
                alert_category TEXT NOT NULL,       -- 'RADIATION_THRESHOLD', 'ML_STATISTICAL_ANOMALY', 'HEALTH_VITALS_ADVISORY'
                detection_engine TEXT NOT NULL,     -- 'ISOLATION_FOREST_ML', 'AEROSPACE_SAFETY_RULE', 'FLIGHT_RULE_ECLSS'
                severity TEXT NOT NULL,             -- 'INFO', 'WARNING', 'CRITICAL', 'ADVISORY'
                instrument_id TEXT,
                astronaut_id TEXT,
                timestamp TEXT NOT NULL,            -- Measurement timestamp
                responsible_metric TEXT NOT NULL,   -- e.g. 'absorbed_dose_rate', 'heart_rate', 'flux'
                metric_value REAL,
                threshold_applied REAL,
                deviation_delta REAL,
                unit TEXT,
                root_cause_explanation TEXT NOT NULL,
                operational_recommendation TEXT NOT NULL,
                guideline_reference TEXT,
                is_suppressed INTEGER DEFAULT 0,
                dedup_hash TEXT UNIQUE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)

            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_smart_alerts_time 
            ON smart_alert_records(timestamp);
            """)

            # Safe schema migrations for existing databases
            for col, col_type in [("retrieved_at", "TEXT"), ("orbital_region", "TEXT DEFAULT 'NOMINAL_LEO'")]:
                try:
                    conn.execute(f"ALTER TABLE radiation_records ADD COLUMN {col} {col_type};")
                except Exception:
                    pass

        logger.info(f"Initialized SQLite database schema at {target_path if (target_path := db_path or DATABASE_PATH) else 'default'}")
    finally:
        conn.close()


def insert_radiation_records(
    records: List[Dict[str, Any]],
    source_origin: str = "NASA OSDR RadLab API",
    db_path: Optional[Path] = None,
    retrieved_at: Optional[str] = None
) -> int:
    """
    Inserts a list of radiation telemetry records into the database.
    Duplicates with matching (timestamp, instrument_id, spacecraft) are automatically skipped.

    Returns the number of new records inserted.
    """
    if not records:
        return 0

    now_iso = retrieved_at or datetime.now(timezone.utc).isoformat()
    conn = get_db_connection(db_path)
    inserted_count = 0
    try:
        with conn:
            cursor = conn.cursor()
            for r in records:
                timestamp = r.get("timestamp")
                instrument_id = r.get("instrument_id")
                if not timestamp or not instrument_id:
                    continue

                lat = r.get("latitude")
                lon = r.get("longitude")
                region = r.get("orbital_region")
                if not region:
                    if lat is not None and lon is not None and -45.0 <= float(lat) <= -5.0 and -90.0 <= float(lon) <= 0.0:
                        region = "SOUTH_ATLANTIC_ANOMALY"
                    else:
                        region = "NOMINAL_LEO"

                cursor.execute("""
                INSERT OR IGNORE INTO radiation_records (
                    timestamp,
                    instrument_id,
                    spacecraft,
                    module,
                    absorbed_dose_rate,
                    absorbed_dose_unit,
                    dose_equivalent_rate,
                    dose_equivalent_unit,
                    flux,
                    flux_unit,
                    altitude,
                    altitude_unit,
                    latitude,
                    longitude,
                    source_origin,
                    is_historical,
                    retrieved_at,
                    orbital_region
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    str(timestamp),
                    str(instrument_id),
                    r.get("spacecraft") or "ISS",
                    r.get("module"),
                    r.get("absorbed_dose_rate"),
                    "µGy/hr",
                    r.get("dose_equivalent_rate"),
                    "µSv/hr",
                    r.get("flux"),
                    "particles/(cm²·sr·s)",
                    r.get("altitude"),
                    "km",
                    lat,
                    lon,
                    source_origin,
                    1,  # is_historical: 1 (True)
                    r.get("retrieved_at") or now_iso,
                    region
                ))
                if cursor.rowcount > 0:
                    inserted_count += 1
    finally:
        conn.close()

    return inserted_count


def insert_alerts(
    alerts: List[Dict[str, Any]],
    db_path: Optional[Path] = None
) -> int:
    """
    Inserts generated alerts into the database.
    Duplicates with matching (alert_type, timestamp, instrument_id, category) are skipped.

    Returns the number of new alerts inserted.
    """
    if not alerts:
        return 0

    conn = get_db_connection(db_path)
    inserted_count = 0
    try:
        with conn:
            cursor = conn.cursor()
            for a in alerts:
                cursor.execute("""
                INSERT OR IGNORE INTO radiation_alerts (
                    alert_id,
                    category,
                    severity,
                    alert_type,
                    timestamp,
                    instrument_id,
                    spacecraft,
                    metric_name,
                    metric_value,
                    threshold_applied,
                    unit,
                    description,
                    recommendation,
                    guideline_reference
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    a.get("alert_id"),
                    a.get("category"),
                    a.get("severity"),
                    a.get("alert_type"),
                    a.get("timestamp"),
                    a.get("instrument_id"),
                    a.get("spacecraft") or "ISS",
                    a.get("metric_name"),
                    a.get("metric_value"),
                    a.get("threshold_applied"),
                    a.get("unit"),
                    a.get("description"),
                    a.get("recommendation"),
                    a.get("guideline_reference")
                ))
                if cursor.rowcount > 0:
                    inserted_count += 1
    finally:
        conn.close()

    return inserted_count


def query_radiation_history(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    spacecraft: Optional[str] = None,
    instrument_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Queries historical radiation records stored in SQLite with pagination and filtering.
    """
    conn = get_db_connection(db_path)
    try:
        where_clauses = ["1=1"]
        params: List[Any] = []

        if start_time:
            where_clauses.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            where_clauses.append("timestamp <= ?")
            params.append(end_time)
        if spacecraft:
            where_clauses.append("spacecraft = ?")
            params.append(spacecraft)
        if instrument_id:
            where_clauses.append("instrument_id = ?")
            params.append(instrument_id)

        where_sql = " AND ".join(where_clauses)

        # Count total records matching criteria
        count_cursor = conn.execute(f"SELECT COUNT(*) as total FROM radiation_records WHERE {where_sql};", params)
        total_records = count_cursor.fetchone()["total"]

        # Fetch paginated rows
        query_sql = f"""
        SELECT 
            id,
            timestamp,
            instrument_id,
            spacecraft,
            module,
            absorbed_dose_rate,
            absorbed_dose_unit,
            dose_equivalent_rate,
            dose_equivalent_unit,
            flux,
            flux_unit,
            altitude,
            altitude_unit,
            latitude,
            longitude,
            source_origin,
            is_historical,
            created_at
        FROM radiation_records
        WHERE {where_sql}
        ORDER BY timestamp ASC, instrument_id ASC
        LIMIT ? OFFSET ?;
        """
        rows = conn.execute(query_sql, params + [limit, offset]).fetchall()
        records = [dict(row) for row in rows]

        # Convert is_historical integer to bool for frontend JSON clarity
        for r in records:
            r["is_historical"] = bool(r.get("is_historical"))

        return {
            "status": "success",
            "total_records": total_records,
            "limit": limit,
            "offset": offset,
            "returned_count": len(records),
            "telemetry_nature": "Historical archived measurements (NOT live sensor readings)",
            "records": records
        }
    finally:
        conn.close()


def query_alerts(
    category: Optional[str] = None,
    severity: Optional[str] = None,
    instrument_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Queries radiation alerts and data quality warnings from SQLite.
    """
    conn = get_db_connection(db_path)
    try:
        where_clauses = ["1=1"]
        params: List[Any] = []

        if category and category.lower() != "all":
            where_clauses.append("category = ?")
            params.append(category.upper())
        if severity and severity.lower() != "all":
            where_clauses.append("severity = ?")
            params.append(severity.upper())
        if instrument_id:
            where_clauses.append("instrument_id = ?")
            params.append(instrument_id)

        where_sql = " AND ".join(where_clauses)

        # Count total
        count_cursor = conn.execute(f"SELECT COUNT(*) as total FROM radiation_alerts WHERE {where_sql};", params)
        total_alerts = count_cursor.fetchone()["total"]

        # Category breakdown
        breakdown_cursor = conn.execute(
            f"SELECT category, COUNT(*) as cnt FROM radiation_alerts WHERE {where_sql} GROUP BY category;",
            params
        )
        category_counts = {row["category"]: row["cnt"] for row in breakdown_cursor.fetchall()}

        # Severity breakdown
        sev_cursor = conn.execute(
            f"SELECT severity, COUNT(*) as cnt FROM radiation_alerts WHERE {where_sql} GROUP BY severity;",
            params
        )
        severity_counts = {row["severity"]: row["cnt"] for row in sev_cursor.fetchall()}

        query_sql = f"""
        SELECT 
            alert_id,
            category,
            severity,
            alert_type,
            timestamp,
            instrument_id,
            spacecraft,
            metric_name,
            metric_value,
            threshold_applied,
            unit,
            description,
            recommendation,
            guideline_reference,
            created_at
        FROM radiation_alerts
        WHERE {where_sql}
        ORDER BY timestamp DESC, id DESC
        LIMIT ? OFFSET ?;
        """
        rows = conn.execute(query_sql, params + [limit, offset]).fetchall()
        alerts = [dict(row) for row in rows]

        return {
            "status": "success",
            "total_alerts": total_alerts,
            "category_breakdown": {
                "DATA_QUALITY_WARNING": category_counts.get("DATA_QUALITY_WARNING", 0),
                "HEALTH_RISK_ALERT": category_counts.get("HEALTH_RISK_ALERT", 0)
            },
            "severity_breakdown": {
                "INFO": severity_counts.get("INFO", 0),
                "WARNING": severity_counts.get("WARNING", 0),
                "CRITICAL": severity_counts.get("CRITICAL", 0)
            },
            "limit": limit,
            "offset": offset,
            "returned_count": len(alerts),
            "disclaimer": (
                "ASTRA CARE alerts reflect spaceflight operational benchmarks (NASA-STD-3001 / NCRP-132). "
                "This system monitors radiation environment levels and does not diagnose astronaut health."
            ),
            "alerts": alerts
        }
    finally:
        conn.close()


# ============================================================================
# Astronaut Health Monitoring Database Operations (Task 03)
# ============================================================================

def insert_astronaut_health_record(
    record: Dict[str, Any],
    db_path: Optional[Path] = None
) -> bool:
    """
    Inserts or updates a validated astronaut health measurement into SQLite.
    Guarantees duplicate prevention via UNIQUE(astronaut_id, timestamp).
    """
    conn = get_db_connection(db_path)
    inserted = False
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO astronaut_health_records (
                record_id,
                astronaut_id,
                timestamp,
                heart_rate,
                heart_rate_unit,
                blood_pressure_systolic,
                blood_pressure_diastolic,
                blood_pressure_unit,
                oxygen_saturation,
                oxygen_saturation_unit,
                body_temperature,
                body_temperature_unit,
                source_device,
                data_classification,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(astronaut_id, timestamp) DO UPDATE SET
                record_id = excluded.record_id,
                heart_rate = excluded.heart_rate,
                blood_pressure_systolic = excluded.blood_pressure_systolic,
                blood_pressure_diastolic = excluded.blood_pressure_diastolic,
                oxygen_saturation = excluded.oxygen_saturation,
                body_temperature = excluded.body_temperature,
                source_device = excluded.source_device,
                data_classification = excluded.data_classification,
                notes = excluded.notes;
            """, (
                record.get("record_id"),
                record.get("astronaut_id"),
                record.get("timestamp"),
                record.get("heart_rate"),
                record.get("heart_rate_unit", "BPM"),
                record.get("blood_pressure_systolic"),
                record.get("blood_pressure_diastolic"),
                record.get("blood_pressure_unit", "mmHg"),
                record.get("oxygen_saturation"),
                record.get("oxygen_saturation_unit", "%"),
                record.get("body_temperature"),
                record.get("body_temperature_unit", "°C"),
                record.get("source_device", "Wearable Crew Health Monitor"),
                record.get("data_classification", "simulated_demo"),
                record.get("notes", "")
            ))
            if cursor.rowcount > 0:
                inserted = True
    finally:
        conn.close()

    return inserted


def insert_astronaut_health_alerts(
    alerts: List[Dict[str, Any]],
    db_path: Optional[Path] = None
) -> int:
    """
    Inserts generated astronaut health alerts into SQLite.
    Skips duplicates using UNIQUE(alert_type, timestamp, astronaut_id).
    """
    if not alerts:
        return 0

    conn = get_db_connection(db_path)
    inserted_count = 0
    try:
        with conn:
            cursor = conn.cursor()
            for a in alerts:
                cursor.execute("""
                INSERT OR IGNORE INTO astronaut_health_alerts (
                    alert_id,
                    astronaut_id,
                    timestamp,
                    category,
                    severity,
                    alert_type,
                    metric_name,
                    metric_value,
                    threshold_applied,
                    unit,
                    description,
                    explanation,
                    recommendation,
                    guideline_reference
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    a.get("alert_id"),
                    a.get("astronaut_id"),
                    a.get("timestamp"),
                    a.get("category"),
                    a.get("severity"),
                    a.get("alert_type"),
                    a.get("metric_name"),
                    str(a.get("metric_value")),
                    str(a.get("threshold_applied")),
                    a.get("unit"),
                    a.get("description"),
                    a.get("explanation"),
                    a.get("recommendation"),
                    a.get("guideline_reference")
                ))
                if cursor.rowcount > 0:
                    inserted_count += 1
    finally:
        conn.close()

    return inserted_count


def query_astronaut_health_measurements(
    astronaut_id: Optional[str] = None,
    data_classification: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Retrieves recent astronaut health measurements from SQLite with pagination and filtering.
    """
    conn = get_db_connection(db_path)
    try:
        where_clauses = ["1=1"]
        params: List[Any] = []

        if astronaut_id:
            where_clauses.append("astronaut_id = ?")
            params.append(astronaut_id)
        if data_classification and data_classification.lower() != "all":
            where_clauses.append("data_classification = ?")
            params.append(data_classification)

        where_sql = " AND ".join(where_clauses)

        # Count total
        count_cursor = conn.execute(f"SELECT COUNT(*) as total FROM astronaut_health_records WHERE {where_sql};", params)
        total_records = count_cursor.fetchone()["total"]

        query_sql = f"""
        SELECT 
            record_id,
            astronaut_id,
            timestamp,
            heart_rate,
            heart_rate_unit,
            blood_pressure_systolic,
            blood_pressure_diastolic,
            blood_pressure_unit,
            oxygen_saturation,
            oxygen_saturation_unit,
            body_temperature,
            body_temperature_unit,
            source_device,
            data_classification,
            notes,
            created_at
        FROM astronaut_health_records
        WHERE {where_sql}
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?;
        """
        rows = conn.execute(query_sql, params + [limit, offset]).fetchall()
        measurements = [dict(row) for row in rows]

        return {
            "status": "success",
            "total_measurements": total_records,
            "limit": limit,
            "offset": offset,
            "returned_count": len(measurements),
            "disclaimer": (
                "ASTRA CARE vitals telemetry monitors physiological parameters (NASA-STD-3001 / AHA). "
                "This software does not diagnose diseases. Measurements require clinical review by a Flight Surgeon."
            ),
            "measurements": measurements
        }
    finally:
        conn.close()


def query_astronaut_health_history(
    astronaut_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    data_classification: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Retrieves time-series historical astronaut health records from SQLite.
    """
    conn = get_db_connection(db_path)
    try:
        where_clauses = ["1=1"]
        params: List[Any] = []

        if astronaut_id:
            where_clauses.append("astronaut_id = ?")
            params.append(astronaut_id)
        if start_time:
            where_clauses.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            where_clauses.append("timestamp <= ?")
            params.append(end_time)
        if data_classification and data_classification.lower() != "all":
            where_clauses.append("data_classification = ?")
            params.append(data_classification)

        where_sql = " AND ".join(where_clauses)

        count_cursor = conn.execute(f"SELECT COUNT(*) as total FROM astronaut_health_records WHERE {where_sql};", params)
        total_records = count_cursor.fetchone()["total"]

        query_sql = f"""
        SELECT 
            record_id,
            astronaut_id,
            timestamp,
            heart_rate,
            heart_rate_unit,
            blood_pressure_systolic,
            blood_pressure_diastolic,
            blood_pressure_unit,
            oxygen_saturation,
            oxygen_saturation_unit,
            body_temperature,
            body_temperature_unit,
            source_device,
            data_classification,
            notes,
            created_at
        FROM astronaut_health_records
        WHERE {where_sql}
        ORDER BY timestamp ASC
        LIMIT ? OFFSET ?;
        """
        rows = conn.execute(query_sql, params + [limit, offset]).fetchall()
        records = [dict(row) for row in rows]

        return {
            "status": "success",
            "total_records": total_records,
            "limit": limit,
            "offset": offset,
            "returned_count": len(records),
            "disclaimer": (
                "Historical research vitals reflect recorded telemetry (NASA-STD-3001). "
                "Historical records do not represent current or live astronaut health."
            ),
            "records": records
        }
    finally:
        conn.close()


def query_astronaut_health_alerts(
    astronaut_id: Optional[str] = None,
    severity: Optional[str] = None,
    alert_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Queries astronaut health alerts from SQLite.
    """
    conn = get_db_connection(db_path)
    try:
        where_clauses = ["1=1"]
        params: List[Any] = []

        if astronaut_id:
            where_clauses.append("astronaut_id = ?")
            params.append(astronaut_id)
        if severity and severity.lower() != "all":
            where_clauses.append("severity = ?")
            params.append(severity.upper())
        if alert_type and alert_type.lower() != "all":
            where_clauses.append("alert_type = ?")
            params.append(alert_type.upper())

        where_sql = " AND ".join(where_clauses)

        count_cursor = conn.execute(f"SELECT COUNT(*) as total FROM astronaut_health_alerts WHERE {where_sql};", params)
        total_alerts = count_cursor.fetchone()["total"]

        # Severity breakdown
        sev_cursor = conn.execute(
            f"SELECT severity, COUNT(*) as cnt FROM astronaut_health_alerts WHERE {where_sql} GROUP BY severity;",
            params
        )
        severity_counts = {row["severity"]: row["cnt"] for row in sev_cursor.fetchall()}

        # Category breakdown
        cat_cursor = conn.execute(
            f"SELECT category, COUNT(*) as cnt FROM astronaut_health_alerts WHERE {where_sql} GROUP BY category;",
            params
        )
        category_counts = {row["category"]: row["cnt"] for row in cat_cursor.fetchall()}

        query_sql = f"""
        SELECT 
            alert_id,
            astronaut_id,
            timestamp,
            category,
            severity,
            alert_type,
            metric_name,
            metric_value,
            threshold_applied,
            unit,
            description,
            explanation,
            recommendation,
            guideline_reference,
            created_at
        FROM astronaut_health_alerts
        WHERE {where_sql}
        ORDER BY timestamp DESC, id DESC
        LIMIT ? OFFSET ?;
        """
        rows = conn.execute(query_sql, params + [limit, offset]).fetchall()
        alerts = [dict(row) for row in rows]

        return {
            "status": "success",
            "total_alerts": total_alerts,
            "category_breakdown": {
                "PHYSIOLOGICAL_WARNING": category_counts.get("PHYSIOLOGICAL_WARNING", 0),
                "CRITICAL_VITALS_ALERT": category_counts.get("CRITICAL_VITALS_ALERT", 0),
                "DATA_QUALITY_WARNING": category_counts.get("DATA_QUALITY_WARNING", 0)
            },
            "severity_breakdown": {
                "INFO": severity_counts.get("INFO", 0),
                "WARNING": severity_counts.get("WARNING", 0),
                "CRITICAL": severity_counts.get("CRITICAL", 0)
            },
            "limit": limit,
            "offset": offset,
            "returned_count": len(alerts),
            "disclaimer": (
                "ASTRA CARE alerts reflect aerospace clinical reference benchmarks (NASA-STD-3001 / AHA). "
                "They explain physiological variance and do not constitute a medical disease diagnosis."
            ),
            "alerts": alerts
        }
    finally:
        conn.close()


def insert_dynamic_radiation_reading(
    reading: Dict[str, Any],
    db_path: Optional[Path] = None
) -> bool:
    """
    Inserts an incoming dynamic radiation measurement into dynamic_radiation_records.
    Guarantees duplicate prevention using reading_id.
    """
    conn = get_db_connection(db_path)
    inserted = False
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR IGNORE INTO dynamic_radiation_records (
                reading_id,
                timestamp,
                instrument_id,
                spacecraft,
                module,
                absorbed_dose_rate,
                absorbed_dose_unit,
                dose_equivalent_rate,
                dose_equivalent_unit,
                flux,
                flux_unit,
                altitude,
                latitude,
                longitude,
                orbital_region,
                data_source,
                is_simulated,
                is_live,
                measurement_quality,
                ml_is_anomaly,
                ml_anomaly_score,
                ml_severity,
                ml_anomaly_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                reading.get("reading_id"),
                reading.get("timestamp"),
                reading.get("instrument_id"),
                reading.get("spacecraft", "ISS"),
                reading.get("module"),
                float(reading.get("absorbed_dose_rate", 0.0)),
                reading.get("absorbed_dose_unit", "µGy/hr"),
                float(reading["dose_equivalent_rate"]) if reading.get("dose_equivalent_rate") is not None else None,
                reading.get("dose_equivalent_unit", "µSv/hr"),
                float(reading["flux"]) if reading.get("flux") is not None else None,
                reading.get("flux_unit", "particles/(cm²·sr·s)"),
                float(reading["altitude"]) if reading.get("altitude") is not None else None,
                float(reading["latitude"]) if reading.get("latitude") is not None else None,
                float(reading["longitude"]) if reading.get("longitude") is not None else None,
                reading.get("orbital_region", "NOMINAL_LEO"),
                reading.get("data_source", "simulated_streaming"),
                1 if reading.get("is_simulated", True) else 0,
                1 if reading.get("is_live", False) else 0,
                reading.get("measurement_quality", "nominal"),
                1 if reading.get("ml_is_anomaly", False) else 0,
                float(reading.get("ml_anomaly_score", 0.0)),
                reading.get("ml_severity", "NORMAL"),
                reading.get("ml_anomaly_reason")
            ))
            if cursor.rowcount > 0:
                inserted = True
    finally:
        conn.close()
    return inserted


def insert_ml_anomaly_record(
    anomaly: Dict[str, Any],
    db_path: Optional[Path] = None
) -> bool:
    """
    Inserts a machine learning anomaly record into ml_anomaly_records.
    """
    conn = get_db_connection(db_path)
    inserted = False
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR IGNORE INTO ml_anomaly_records (
                anomaly_id,
                reading_id,
                timestamp,
                instrument_id,
                absorbed_dose_rate,
                unit,
                anomaly_score,
                severity,
                primary_contributing_feature,
                baseline_z_score,
                dose_rate_delta,
                explanation,
                recommendation,
                data_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                anomaly.get("anomaly_id"),
                anomaly.get("reading_id"),
                anomaly.get("timestamp"),
                anomaly.get("instrument_id"),
                float(anomaly.get("absorbed_dose_rate", 0.0)),
                anomaly.get("unit", "µGy/hr"),
                float(anomaly.get("anomaly_score", 0.0)),
                anomaly.get("severity", "WARNING_ANOMALY"),
                anomaly.get("primary_contributing_feature"),
                float(anomaly["baseline_z_score"]) if anomaly.get("baseline_z_score") is not None else None,
                float(anomaly["dose_rate_delta"]) if anomaly.get("dose_rate_delta") is not None else None,
                anomaly.get("explanation", ""),
                anomaly.get("recommendation", ""),
                anomaly.get("data_source", "simulated_streaming")
            ))
            if cursor.rowcount > 0:
                inserted = True
    finally:
        conn.close()
    return inserted


def query_dynamic_radiation_readings(
    instrument_id: Optional[str] = None,
    data_source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Retrieves stored dynamic radiation measurements from SQLite with pagination and filtering.
    """
    conn = get_db_connection(db_path)
    try:
        where_clauses = ["1=1"]
        params: List[Any] = []

        if instrument_id and instrument_id.lower() != "all":
            where_clauses.append("instrument_id = ?")
            params.append(instrument_id)
        if data_source and data_source.lower() != "all":
            where_clauses.append("data_source = ?")
            params.append(data_source)

        where_sql = " AND ".join(where_clauses)

        count_cursor = conn.execute(f"SELECT COUNT(*) as total FROM dynamic_radiation_records WHERE {where_sql};", params)
        total_records = count_cursor.fetchone()["total"]

        query_sql = f"""
        SELECT 
            reading_id,
            timestamp,
            instrument_id,
            spacecraft,
            module,
            absorbed_dose_rate,
            absorbed_dose_unit,
            dose_equivalent_rate,
            dose_equivalent_unit,
            flux,
            flux_unit,
            altitude,
            latitude,
            longitude,
            orbital_region,
            data_source,
            is_simulated,
            is_live,
            measurement_quality,
            ml_is_anomaly,
            ml_anomaly_score,
            ml_severity,
            ml_anomaly_reason,
            created_at
        FROM dynamic_radiation_records
        WHERE {where_sql}
        ORDER BY timestamp DESC, id DESC
        LIMIT ? OFFSET ?;
        """
        rows = conn.execute(query_sql, params + [limit, offset]).fetchall()
        readings = [dict(r) for r in rows]

        return {
            "status": "success",
            "total_records": total_records,
            "limit": limit,
            "offset": offset,
            "returned_count": len(readings),
            "telemetry_nature": "Dynamic space radiation stream (evaluated via Machine Learning Anomaly Detection)",
            "readings": readings,
            "records": readings
        }
    finally:
        conn.close()


def get_latest_dynamic_radiation_reading(
    instrument_id: Optional[str] = None,
    db_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieves the most recent dynamic radiation reading from SQLite.
    """
    conn = get_db_connection(db_path)
    try:
        if instrument_id and instrument_id.lower() != "all":
            row = conn.execute("""
                SELECT * FROM dynamic_radiation_records
                WHERE instrument_id = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT 1;
            """, (instrument_id,)).fetchone()
        else:
            row = conn.execute("""
                SELECT * FROM dynamic_radiation_records
                ORDER BY timestamp DESC, id DESC
                LIMIT 1;
            """).fetchone()

        return dict(row) if row else None
    finally:
        conn.close()


def query_ml_anomalies(
    severity: Optional[str] = None,
    instrument_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Retrieves detected machine learning radiation anomalies with explainability metadata.
    """
    conn = get_db_connection(db_path)
    try:
        where_clauses = ["1=1"]
        params: List[Any] = []

        if severity and severity.lower() != "all":
            where_clauses.append("severity = ?")
            params.append(severity)
        if instrument_id and instrument_id.lower() != "all":
            where_clauses.append("instrument_id = ?")
            params.append(instrument_id)

        where_sql = " AND ".join(where_clauses)

        count_cursor = conn.execute(f"SELECT COUNT(*) as total FROM ml_anomaly_records WHERE {where_sql};", params)
        total_records = count_cursor.fetchone()["total"]

        query_sql = f"""
        SELECT 
            anomaly_id,
            reading_id,
            timestamp,
            instrument_id,
            absorbed_dose_rate,
            unit,
            anomaly_score,
            severity,
            primary_contributing_feature,
            baseline_z_score,
            dose_rate_delta,
            explanation,
            recommendation,
            data_source,
            created_at
        FROM ml_anomaly_records
        WHERE {where_sql}
        ORDER BY timestamp DESC, id DESC
        LIMIT ? OFFSET ?;
        """
        rows = conn.execute(query_sql, params + [limit, offset]).fetchall()
        anomalies = [dict(r) for r in rows]

        return {
            "status": "success",
            "total_anomalies": total_records,
            "limit": limit,
            "offset": offset,
            "returned_count": len(anomalies),
            "disclaimer": (
                "ML radiation anomalies represent statistical deviations from historical detector distributions "
                "(Isolation Forest). They are distinct from validated operational flight limits."
            ),
            "anomalies": anomalies
        }
    finally:
        conn.close()


def get_db_statistics(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Returns summary counts of stored records and alerts in the SQLite database
    for radiation telemetry, dynamic streaming, ML anomalies, and astronaut health monitoring.
    """
    conn = get_db_connection(db_path)
    try:
        rad_records_cnt = conn.execute("SELECT COUNT(*) as total FROM radiation_records;").fetchone()["total"]
        rad_alerts_cnt = conn.execute("SELECT COUNT(*) as total FROM radiation_alerts;").fetchone()["total"]
        instruments = [
            row["instrument_id"] for row in
            conn.execute("SELECT DISTINCT instrument_id FROM radiation_records ORDER BY instrument_id;").fetchall()
        ]

        # Dynamic & ML stats (ASTRA CARE 2.0)
        try:
            dynamic_cnt = conn.execute("SELECT COUNT(*) as total FROM dynamic_radiation_records;").fetchone()["total"]
        except Exception:
            dynamic_cnt = 0

        try:
            ml_anomalies_cnt = conn.execute("SELECT COUNT(*) as total FROM ml_anomaly_records;").fetchone()["total"]
        except Exception:
            ml_anomalies_cnt = 0

        # Health stats
        health_records_cnt = conn.execute("SELECT COUNT(*) as total FROM astronaut_health_records;").fetchone()["total"]
        health_alerts_cnt = conn.execute("SELECT COUNT(*) as total FROM astronaut_health_alerts;").fetchone()["total"]
        astronauts = [
            row["astronaut_id"] for row in
            conn.execute("SELECT DISTINCT astronaut_id FROM astronaut_health_records ORDER BY astronaut_id;").fetchall()
        ]

        return {
            "stored_radiation_records_count": rad_records_cnt,
            "stored_radiation_alerts_count": rad_alerts_cnt,
            "tracked_instruments": instruments,
            "stored_dynamic_radiation_count": dynamic_cnt,
            "stored_ml_anomalies_count": ml_anomalies_cnt,
            "stored_health_records_count": health_records_cnt,
            "stored_health_alerts_count": health_alerts_cnt,
            "monitored_astronauts": astronauts,
            "stored_records_count": rad_records_cnt, # Backwards compatibility
            "stored_alerts_count": rad_alerts_cnt,   # Backwards compatibility
            "database_file": str(db_path or DATABASE_PATH)
        }
    finally:
        conn.close()


# ============================================================================
# Advanced Features DB Queries & Log Operations (Features 1 to 5)
# ============================================================================

def insert_nasa_sync_log(
    log_data: Dict[str, Any],
    db_path: Optional[Path] = None
) -> int:
    """
    Inserts a record of a NASA RadLab sync operation.
    """
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.cursor()
            sync_id = log_data.get("sync_id") or f"SYNC-{int(datetime.now(timezone.utc).timestamp()*1000)}"
            detectors_val = log_data.get("detectors_detected")
            if isinstance(detectors_val, (list, tuple)):
                detectors_str = ", ".join(detectors_val)
            else:
                detectors_str = str(detectors_val or "")

            cursor.execute("""
            INSERT OR REPLACE INTO nasa_sync_logs (
                sync_id,
                sync_timestamp,
                status,
                source,
                records_fetched,
                new_records_inserted,
                detectors_detected,
                temporal_window_start,
                temporal_window_end,
                duration_ms,
                message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                sync_id,
                log_data.get("sync_timestamp") or datetime.now(timezone.utc).isoformat(),
                log_data.get("status") or "SUCCESS",
                log_data.get("source") or "NASA_OSDR_RADLAB_API",
                int(log_data.get("records_fetched") or 0),
                int(log_data.get("new_records_inserted") or 0),
                detectors_str,
                log_data.get("temporal_window_start"),
                log_data.get("temporal_window_end"),
                float(log_data.get("duration_ms") or 0.0),
                log_data.get("message")
            ))
            return cursor.rowcount
    finally:
        conn.close()


def get_latest_nasa_sync_log(db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves the most recent NASA RadLab sync log record.
    """
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("""
        SELECT sync_id, sync_timestamp, status, source, records_fetched,
               new_records_inserted, detectors_detected, temporal_window_start,
               temporal_window_end, duration_ms, message, created_at
        FROM nasa_sync_logs
        ORDER BY id DESC
        LIMIT 1;
        """).fetchone()
        return dict(row) if row else None
    except Exception as exc:
        logger.warning(f"Error querying latest sync log: {exc}")
        return None
    finally:
        conn.close()


def query_nasa_sync_logs(
    limit: int = 20,
    offset: int = 0,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Retrieves paginated history of NASA RadLab sync operations.
    """
    conn = get_db_connection(db_path)
    try:
        count_row = conn.execute("SELECT COUNT(*) as total FROM nasa_sync_logs;").fetchone()
        total = count_row["total"] if count_row else 0

        rows = conn.execute("""
        SELECT sync_id, sync_timestamp, status, source, records_fetched,
               new_records_inserted, detectors_detected, temporal_window_start,
               temporal_window_end, duration_ms, message, created_at
        FROM nasa_sync_logs
        ORDER BY id DESC
        LIMIT ? OFFSET ?;
        """, (limit, offset)).fetchall()

        logs = [dict(r) for r in rows]
        return {
            "status": "success",
            "total_syncs": total,
            "limit": limit,
            "offset": offset,
            "logs": logs
        }
    except Exception as exc:
        logger.warning(f"Error querying sync logs: {exc}")
        return {"status": "success", "total_syncs": 0, "limit": limit, "offset": offset, "logs": []}
    finally:
        conn.close()


def query_radiation_locations(
    detector_id: Optional[str] = None,
    source: str = "all",
    limit: int = 150,
    offset: int = 0,
    db_path: Optional[Path] = None,
    orbital_region: Optional[str] = None
) -> Dict[str, Any]:
    """
    Queries geo-located radiation measurements across historical NASA RadLab records
    and dynamic streaming telemetry.
    """
    conn = get_db_connection(db_path)
    locations: List[Dict[str, Any]] = []
    try:
        # 1. Historical records query
        if source in ("all", "historical"):
            where = ["latitude IS NOT NULL", "longitude IS NOT NULL"]
            params: List[Any] = []
            if detector_id and detector_id.lower() != "all":
                where.append("instrument_id = ?")
                params.append(detector_id)
            if orbital_region and orbital_region.lower() != "all":
                if orbital_region.upper() == "SOUTH_ATLANTIC_ANOMALY":
                    where.append("((orbital_region = 'SOUTH_ATLANTIC_ANOMALY') OR (latitude BETWEEN -45.0 AND -5.0 AND longitude BETWEEN -90.0 AND 0.0))")
                else:
                    where.append("((orbital_region = 'NOMINAL_LEO') OR (orbital_region IS NULL AND NOT (latitude BETWEEN -45.0 AND -5.0 AND longitude BETWEEN -90.0 AND 0.0)))")

            where_sql = " AND ".join(where)
            sql = f"""
            SELECT 
                'HIST-' || id as location_id,
                timestamp,
                instrument_id,
                spacecraft,
                module,
                absorbed_dose_rate,
                absorbed_dose_unit,
                dose_equivalent_rate,
                dose_equivalent_unit,
                flux,
                altitude,
                latitude,
                longitude,
                COALESCE(orbital_region, CASE WHEN latitude BETWEEN -45.0 AND -5.0 AND longitude BETWEEN -90.0 AND 0.0 THEN 'SOUTH_ATLANTIC_ANOMALY' ELSE 'NOMINAL_LEO' END) as orbital_region,
                source_origin as data_source,
                1 as is_historical,
                0 as is_simulated,
                0 as ml_is_anomaly
            FROM radiation_records
            WHERE {where_sql}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?;
            """
            rows = conn.execute(sql, params + [limit, offset]).fetchall()
            locations.extend([dict(r) for r in rows])

        # 2. Dynamic streaming records query
        if source in ("all", "dynamic", "simulated") and len(locations) < limit:
            remaining = limit - len(locations)
            where = ["latitude IS NOT NULL", "longitude IS NOT NULL"]
            params = []
            if detector_id and detector_id.lower() != "all":
                where.append("instrument_id = ?")
                params.append(detector_id)
            if orbital_region and orbital_region.lower() != "all":
                where.append("orbital_region = ?")
                params.append(orbital_region.upper())

            where_sql = " AND ".join(where)
            sql = f"""
            SELECT 
                reading_id as location_id,
                timestamp,
                instrument_id,
                spacecraft,
                module,
                absorbed_dose_rate,
                absorbed_dose_unit,
                dose_equivalent_rate,
                dose_equivalent_unit,
                flux,
                altitude,
                latitude,
                longitude,
                orbital_region,
                data_source,
                0 as is_historical,
                is_simulated,
                ml_is_anomaly
            FROM dynamic_radiation_records
            WHERE {where_sql}
            ORDER BY timestamp DESC
            LIMIT ?;
            """
            try:
                rows = conn.execute(sql, params + [remaining]).fetchall()
                locations.extend([dict(r) for r in rows])
            except Exception:
                pass

        return {
            "status": "success",
            "count": len(locations),
            "limit": limit,
            "offset": offset,
            "saa_bounding_box": {
                "name": "South Atlantic Anomaly (SAA)",
                "lat_min": -45.0,
                "lat_max": -5.0,
                "lon_min": -90.0,
                "lon_max": 0.0,
                "description": "Region of reduced geomagnetic field intensity where inner Van Allen proton belt descends to LEO altitudes."
            },
            "locations": locations,
            "telemetry_provenance": "All geographic coordinates represent sub-satellite positions at the moment of recording. Historical coordinates do NOT represent the current real-time position of the ISS."
        }
    finally:
        conn.close()


def insert_smart_alerts(
    alerts: List[Dict[str, Any]],
    db_path: Optional[Path] = None
) -> int:
    """
    Inserts enriched smart alert records into SQLite with deduplication.
    """
    if not alerts:
        return 0

    conn = get_db_connection(db_path)
    inserted = 0
    try:
        with conn:
            cursor = conn.cursor()
            for a in alerts:
                alert_id = a.get("alert_id") or f"SMART-{hashlib.sha256(f'{a.get('alert_category')}_{a.get('timestamp')}_{a.get('instrument_id')}_{a.get('severity')}'.encode()).hexdigest()[:12].upper()}"
                dedup = a.get("dedup_hash") or f"{a.get('alert_category')}_{a.get('instrument_id')}_{a.get('timestamp')[:16]}_{a.get('severity')}"

                cursor.execute("""
                INSERT OR IGNORE INTO smart_alert_records (
                    alert_id,
                    alert_category,
                    detection_engine,
                    severity,
                    instrument_id,
                    astronaut_id,
                    timestamp,
                    responsible_metric,
                    metric_value,
                    threshold_applied,
                    deviation_delta,
                    unit,
                    root_cause_explanation,
                    operational_recommendation,
                    guideline_reference,
                    is_suppressed,
                    dedup_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    alert_id,
                    a.get("alert_category") or "RADIATION_THRESHOLD",
                    a.get("detection_engine") or "AEROSPACE_SAFETY_RULE",
                    a.get("severity") or "WARNING",
                    a.get("instrument_id"),
                    a.get("astronaut_id"),
                    str(a.get("timestamp") or datetime.now(timezone.utc).isoformat()),
                    a.get("responsible_metric") or "absorbed_dose_rate",
                    a.get("metric_value"),
                    a.get("threshold_applied"),
                    a.get("deviation_delta"),
                    a.get("unit") or "µGy/hr",
                    a.get("root_cause_explanation") or a.get("description") or "Elevated reading detected.",
                    a.get("operational_recommendation") or a.get("recommendation") or "Check sensor and follow standard protocols.",
                    a.get("guideline_reference") or "NASA-STD-3001 Vol 1",
                    1 if a.get("is_suppressed") else 0,
                    dedup
                ))
                if cursor.rowcount > 0:
                    inserted += 1
        return inserted
    finally:
        conn.close()


def query_smart_alerts(
    severity: Optional[str] = None,
    category: Optional[str] = None,
    detector_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Queries enriched smart alert records with filtering and pagination.
    """
    conn = get_db_connection(db_path)
    try:
        where = ["1=1"]
        params: List[Any] = []

        if severity and severity.lower() != "all":
            where.append("severity = ?")
            params.append(severity.upper())
        if category and category.lower() != "all":
            where.append("alert_category = ?")
            params.append(category.upper())
        if detector_id and detector_id.lower() != "all":
            where.append("instrument_id = ?")
            params.append(detector_id)

        where_sql = " AND ".join(where)

        count_cursor = conn.execute(f"SELECT COUNT(*) as total FROM smart_alert_records WHERE {where_sql};", params)
        total = count_cursor.fetchone()["total"]

        sql = f"""
        SELECT 
            alert_id,
            alert_category,
            detection_engine,
            severity,
            instrument_id,
            astronaut_id,
            timestamp,
            responsible_metric,
            metric_value,
            threshold_applied,
            deviation_delta,
            unit,
            root_cause_explanation,
            operational_recommendation,
            guideline_reference,
            is_suppressed,
            created_at
        FROM smart_alert_records
        WHERE {where_sql}
        ORDER BY timestamp DESC, id DESC
        LIMIT ? OFFSET ?;
        """
        rows = conn.execute(sql, params + [limit, offset]).fetchall()
        alerts = [dict(r) for r in rows]

        return {
            "status": "success",
            "total_alerts": total,
            "limit": limit,
            "offset": offset,
            "returned_count": len(alerts),
            "alerts": alerts
        }
    finally:
        conn.close()


def query_multi_detector_stats(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Computes cross-detector statistical summaries across available radiation sensors
    (DosTel1, DosTel2, Lidal, DB8, REM-Lid).
    """
    conn = get_db_connection(db_path)
    try:
        # Detectors in radiation_records
        sql = """
        SELECT 
            instrument_id,
            COUNT(*) as record_count,
            MIN(absorbed_dose_rate) as min_absorbed_dose,
            MAX(absorbed_dose_rate) as max_absorbed_dose,
            AVG(absorbed_dose_rate) as avg_absorbed_dose,
            MIN(dose_equivalent_rate) as min_dose_equivalent,
            MAX(dose_equivalent_rate) as max_dose_equivalent,
            AVG(dose_equivalent_rate) as avg_dose_equivalent,
            AVG(flux) as avg_flux,
            MIN(timestamp) as earliest_timestamp,
            MAX(timestamp) as latest_timestamp,
            module,
            spacecraft
        FROM radiation_records
        WHERE absorbed_dose_rate IS NOT NULL
        GROUP BY instrument_id
        ORDER BY instrument_id;
        """
        rows = conn.execute(sql).fetchall()
        detectors_summary = []

        DETECTOR_METADATA = {
            "DosTel1": {
                "name": "DLR DOSTEL 1 (Dose Tel)",
                "module": "Columbus Laboratory",
                "orientation": "Starboard",
                "nominal_q_factor": 1.75,
                "shielding_level": "Medium (~15 g/cm² Al-equivalent)",
                "notes": "Silicon semiconductor telescope measuring LET and absorbed dose in European laboratory."
            },
            "DosTel2": {
                "name": "DLR DOSTEL 2 (Dose Tel)",
                "module": "Columbus Laboratory",
                "orientation": "Forward",
                "nominal_q_factor": 1.95,
                "shielding_level": "High (~22 g/cm² Al-equivalent)",
                "notes": "Positioned adjacent to water-wall storage bags, showing slightly higher shielding attenuation."
            },
            "Lidal": {
                "name": "ALTEA-LIDAL (Light Ion Detector)",
                "module": "Columbus Laboratory",
                "orientation": "Nadir / Zenith",
                "nominal_q_factor": 2.20,
                "shielding_level": "Low-to-Medium (~10 g/cm²)",
                "notes": "Time-of-flight scintillators coupled to silicon strip detector; sensitive to fast heavy ions."
            },
            "REM-Lid": {
                "name": "Radiation Environment Monitor (REM)",
                "module": "US Laboratory / Columbus",
                "orientation": "Bulkhead",
                "nominal_q_factor": 1.80,
                "shielding_level": "Standard (~12 g/cm²)",
                "notes": "Continuous broad-spectrum ionising radiation dosimeter."
            },
            "DB8": {
                "name": "ISS DB8 Silicon Dosimeter",
                "module": "Service Module",
                "orientation": "Aft",
                "nominal_q_factor": 1.65,
                "shielding_level": "Heavy (~28 g/cm²)",
                "notes": "Russian segment dosimeter located near crew sleeping quarters."
            }
        }

        for r in rows:
            inst = r["instrument_id"]
            meta = DETECTOR_METADATA.get(inst, {
                "name": f"Radiation Detector {inst}",
                "module": r["module"] or "ISS",
                "orientation": "Internal",
                "nominal_q_factor": 1.85,
                "shielding_level": "Nominal",
                "notes": "Active radiation detection instrument aboard ISS."
            })

            detectors_summary.append({
                "instrument_id": inst,
                "name": meta["name"],
                "module": r["module"] or meta["module"],
                "spacecraft": r["spacecraft"],
                "orientation": meta["orientation"],
                "shielding_level": meta["shielding_level"],
                "nominal_q_factor": meta["nominal_q_factor"],
                "record_count": r["record_count"],
                "absorbed_dose_rate_stats": {
                    "unit": "µGy/hr",
                    "min": round(r["min_absorbed_dose"], 4) if r["min_absorbed_dose"] is not None else None,
                    "max": round(r["max_absorbed_dose"], 4) if r["max_absorbed_dose"] is not None else None,
                    "mean": round(r["avg_absorbed_dose"], 4) if r["avg_absorbed_dose"] is not None else None
                },
                "dose_equivalent_rate_stats": {
                    "unit": "µSv/hr",
                    "min": round(r["min_dose_equivalent"], 4) if r["min_dose_equivalent"] is not None else None,
                    "max": round(r["max_dose_equivalent"], 4) if r["max_dose_equivalent"] is not None else None,
                    "mean": round(r["avg_dose_equivalent"], 4) if r["avg_dose_equivalent"] is not None else None
                },
                "average_flux": round(r["avg_flux"], 4) if r["avg_flux"] is not None else None,
                "flux_unit": "particles/(cm²·sr·s)",
                "earliest_timestamp": r["earliest_timestamp"],
                "latest_timestamp": r["latest_timestamp"],
                "notes": meta["notes"]
            })

        return {
            "status": "success",
            "total_detectors_compared": len(detectors_summary),
            "detectors": detectors_summary,
            "disclaimer": (
                "Different radiation detectors occupy distinct physical modules with unique local shielding geometries "
                "and directional orientations. Variations in observed dose rate reflect localized shielding mass differences "
                "rather than sensor calibration error."
            )
        }
    finally:
        conn.close()
