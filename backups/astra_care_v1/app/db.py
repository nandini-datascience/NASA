"""
db.py - SQLite Database Storage Layer for ASTRA CARE

Handles persistence of authentic space radiation records and generated alerts.
Guarantees duplicate prevention using SQLite UNIQUE constraints and indexes.
Preserves original timestamps, measurement units, and source attribution.
"""

import logging
import sqlite3
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

        logger.info(f"Initialized SQLite database schema at {target_path if (target_path := db_path or DATABASE_PATH) else 'default'}")
    finally:
        conn.close()


def insert_radiation_records(
    records: List[Dict[str, Any]],
    source_origin: str = "NASA OSDR RadLab API",
    db_path: Optional[Path] = None
) -> int:
    """
    Inserts a list of radiation telemetry records into the database.
    Duplicates with matching (timestamp, instrument_id, spacecraft) are automatically skipped.

    Returns the number of new records inserted.
    """
    if not records:
        return 0

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
                    is_historical
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                    r.get("latitude"),
                    r.get("longitude"),
                    source_origin,
                    1  # is_historical: 1 (True)
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


def get_db_statistics(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Returns summary counts of stored records and alerts in the SQLite database
    for both radiation telemetry and astronaut health monitoring.
    """
    conn = get_db_connection(db_path)
    try:
        rad_records_cnt = conn.execute("SELECT COUNT(*) as total FROM radiation_records;").fetchone()["total"]
        rad_alerts_cnt = conn.execute("SELECT COUNT(*) as total FROM radiation_alerts;").fetchone()["total"]
        instruments = [
            row["instrument_id"] for row in
            conn.execute("SELECT DISTINCT instrument_id FROM radiation_records ORDER BY instrument_id;").fetchall()
        ]

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
            "stored_health_records_count": health_records_cnt,
            "stored_health_alerts_count": health_alerts_cnt,
            "monitored_astronauts": astronauts,
            "stored_records_count": rad_records_cnt, # Backwards compatibility
            "stored_alerts_count": rad_alerts_cnt,   # Backwards compatibility
            "database_file": str(db_path or DATABASE_PATH)
        }
    finally:
        conn.close()
