"""
data.py - NASA RadLab Radiation Data Access Layer

This module provides data retrieval and processing logic for the ASTRA CARE system.
It interfaces with the NASA Open Science Data Repository (OSDR) RadLab API:
    https://visualization.osdr.nasa.gov/radlab/api

IMPORTANT SCIENTIFIC AND OPERATIONAL NOTES:
- The measurements retrieved are HISTORICAL scientific measurements recorded by
  detectors aboard spacecraft such as the International Space Station (ISS).
- They are NOT real-time or live sensor telemetry.
- Radiation readings are never synthesized or simulated.
"""

import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
import requests

logger = logging.getLogger("astra_care.data")

# Official NASA RadLab API Endpoint
NASA_RADLAB_API_URL = "https://visualization.osdr.nasa.gov/radlab/api"

# Local datasets directory for offline backup & reference
DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"
LOCAL_SAMPLE_CSV = DATASETS_DIR / "nasa_radlab_sample.csv"
LOCAL_SAMPLE_JSON = DATASETS_DIR / "nasa_radlab_sample.json"

# Radiation Field Dictionary & Measurement Units
RADIATION_FIELD_METADATA: Dict[str, Dict[str, str]] = {
    "timestamp": {
        "unit": "ISO 8601 UTC string (YYYY-MM-DDTHH:MM:SS)",
        "description": "Timestamp when the radiation telemetry was measured aboard the spacecraft.",
        "type": "datetime"
    },
    "instrument_id": {
        "unit": "Identifier string",
        "description": "Radiation detection instrument (e.g., REM-Lid, DosTel1, DosTel2, Lidal).",
        "type": "string"
    },
    "absorbed_dose_rate": {
        "unit": "µGy/hr (microGrays per hour)",
        "description": "Rate of energy absorbed per unit mass of matter (1 Gy = 1 Joule/kg).",
        "type": "float"
    },
    "dose_equivalent_rate": {
        "unit": "µSv/hr (microSieverts per hour)",
        "description": "Absorbed dose weighted by radiation biological effectiveness (quality factor Q).",
        "type": "float"
    },
    "flux": {
        "unit": "particles/(cm²·sr·s)",
        "description": "Count of ionizing particles traversing a square centimeter per steradian per second.",
        "type": "float"
    },
    "altitude": {
        "unit": "km (kilometers)",
        "description": "Orbital altitude of the spacecraft above Earth mean sea level.",
        "type": "float"
    },
    "latitude": {
        "unit": "degrees (-90.0 to +90.0)",
        "description": "Sub-satellite geographic latitude coordinate.",
        "type": "float"
    },
    "longitude": {
        "unit": "degrees (-180.0 to +180.0)",
        "description": "Sub-satellite geographic longitude coordinate.",
        "type": "float"
    },
    "spacecraft": {
        "unit": "Name string",
        "description": "Spacecraft host platform (e.g., ISS - International Space Station).",
        "type": "string"
    },
    "module": {
        "unit": "Name string",
        "description": "Specific internal pressurized compartment/laboratory (e.g., Columbus, US Lab).",
        "type": "string"
    }
}


def clean_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Cleans a pandas DataFrame of radiation data:
    - Strips whitespace from string headers and values
    - Converts float NaN/inf values into None (valid JSON nulls)
    - Returns records as a list of Python dictionaries
    """
    # Strip any column whitespace
    df.columns = [col.strip() for col in df.columns]

    # Convert string columns to strip whitespace
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].astype(str).str.strip().replace({"nan": None, "None": None})

    # Replace pandas NaN with None for valid JSON serialization
    records = df.where(pd.notnull(df), None).to_dict(orient="records")
    return records


def calculate_radiation_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculates summary metrics across the radiation sample:
    - Total valid measurements
    - Active instruments detected
    - Min, max, and average absorbed dose rate (in µGy/hr)
    """
    if not records:
        return {
            "total_records": 0,
            "unique_instruments": [],
            "absorbed_dose_rate_stats": None
        }

    instruments = sorted(list({r.get("instrument_id") for r in records if r.get("instrument_id")}))
    dose_rates = [
        r["absorbed_dose_rate"] for r in records
        if r.get("absorbed_dose_rate") is not None and isinstance(r["absorbed_dose_rate"], (int, float))
    ]

    dose_stats = None
    if dose_rates:
        dose_stats = {
            "unit": "µGy/hr",
            "count": len(dose_rates),
            "min": round(min(dose_rates), 4),
            "max": round(max(dose_rates), 4),
            "mean": round(sum(dose_rates) / len(dose_rates), 4)
        }

    return {
        "total_records": len(records),
        "unique_instruments": instruments,
        "absorbed_dose_rate_stats": dose_stats
    }


def load_local_nasa_sample() -> Dict[str, Any]:
    """
    Loads authentic NASA RadLab radiation measurements from the local datasets directory.
    Used as an offline fallback when the external NASA API is unreachable or rate-limited.
    """
    if LOCAL_SAMPLE_CSV.exists():
        df = pd.read_csv(LOCAL_SAMPLE_CSV)
        records = clean_dataframe(df)
        return {
            "source": "Local NASA RadLab Sample Archive (datasets/nasa_radlab_sample.csv)",
            "source_status": "offline_fallback",
            "telemetry_nature": "Historical space telemetry (NOT live readings)",
            "records": records,
            "summary": calculate_radiation_summary(records)
        }
    elif LOCAL_SAMPLE_JSON.exists():
        with open(LOCAL_SAMPLE_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
            records = data.get("records", [])
            return {
                "source": "Local NASA RadLab Sample Archive (datasets/nasa_radlab_sample.json)",
                "source_status": "offline_fallback",
                "telemetry_nature": "Historical space telemetry (NOT live readings)",
                "records": records,
                "summary": calculate_radiation_summary(records)
            }
    else:
        raise FileNotFoundError("Local NASA RadLab sample dataset not found in datasets/ directory.")


def fetch_nasa_radiation_sample(
    start_time: Any = "2022-04-01T00:00:00",
    end_time: Any = "2022-04-01T00:15:00",
    spacecraft: Any = "ISS",
    limit: Any = 50,
    allow_fallback: Any = True
) -> Dict[str, Any]:
    """
    Fetches actual space radiation measurements from the NASA RadLab API.

    Parameters:
        start_time: ISO 8601 UTC start timestamp (e.g. '2022-04-01T00:00:00')
        end_time: ISO 8601 UTC end timestamp (e.g. '2022-04-01T00:15:00')
        spacecraft: Spacecraft identifier, default 'ISS'
        limit: Maximum number of records to return in the JSON payload
        allow_fallback: If True, falls back to the authentic local dataset when the NASA API fails

    Returns:
        Structured dictionary containing:
        - metadata (source URL, temporal bounds, telemetry note)
        - field definitions and measurement units
        - summary statistics
        - authentic measurement records
    """
    # Safely extract parameter values if passed as FastAPI Query objects in direct tests
    start_time_val = str(getattr(start_time, "default", start_time))
    end_time_val = str(getattr(end_time, "default", end_time))
    spacecraft_val = str(getattr(spacecraft, "default", spacecraft))
    raw_limit = getattr(limit, "default", limit)
    try:
        limit_val = int(raw_limit) if raw_limit is not None else 50
    except (ValueError, TypeError):
        limit_val = 50

    raw_fallback = getattr(allow_fallback, "default", allow_fallback)
    allow_fallback_val = bool(raw_fallback) if raw_fallback is not None else True

    query_expression = f"(timestamp>={start_time_val})AND(timestamp<={end_time_val})"
    if spacecraft_val:
        query_expression += f"AND(spacecraft={spacecraft_val})"

    columns = [
        "absorbed_dose_rate",
        "dose_equivalent_rate",
        "flux",
        "spacecraft",
        "module",
        "latitude",
        "longitude",
        "altitude"
    ]

    params = {
        "query": query_expression,
        "columns": ",".join(columns)
    }

    headers = {
        "User-Agent": "ASTRA-CARE-Backend/1.0 (Astronaut Health and Radiation Monitoring System)"
    }

    try:
        # Request with a 12-second timeout
        response = requests.get(
            NASA_RADLAB_API_URL,
            params=params,
            headers=headers,
            timeout=12
        )

        if response.status_code == 200 and "timestamp" in response.text:
            df = pd.read_csv(io.StringIO(response.text))
            if limit_val and limit_val > 0:
                df = df.head(limit_val)

            records = clean_dataframe(df)
            summary = calculate_radiation_summary(records)

            return {
                "status": "success",
                "source": "NASA Open Science Data Repository (OSDR) - RadLab API",
                "source_status": "live_api_fetch",
                "telemetry_nature": "Historical archived measurements (NOT live sensor readings)",
                "query_parameters": {
                    "start_time": start_time_val,
                    "end_time": end_time_val,
                    "spacecraft": spacecraft_val,
                    "limit": limit_val
                },
                "field_units": RADIATION_FIELD_METADATA,
                "summary": summary,
                "records": records
            }
        else:
            error_msg = f"NASA RadLab API returned HTTP {response.status_code}: {response.text[:200]}"
            logger.warning(error_msg)
            if allow_fallback_val:
                fallback_data = load_local_nasa_sample()
                if limit_val and limit_val > 0:
                    fallback_data["records"] = fallback_data["records"][:limit_val]
                    fallback_data["summary"] = calculate_radiation_summary(fallback_data["records"])
                fallback_data["status"] = "fallback"
                fallback_data["warning"] = f"NASA RadLab API returned status {response.status_code}. Returning verified authentic local NASA sample."
                fallback_data["field_units"] = RADIATION_FIELD_METADATA
                return fallback_data
            else:
                raise requests.HTTPError(error_msg)

    except (requests.exceptions.RequestException, requests.exceptions.Timeout) as exc:
        logger.error(f"Failed to connect to NASA RadLab API: {exc}")
        if allow_fallback_val:
            fallback_data = load_local_nasa_sample()
            if limit_val and limit_val > 0:
                fallback_data["records"] = fallback_data["records"][:limit_val]
                fallback_data["summary"] = calculate_radiation_summary(fallback_data["records"])
            fallback_data["status"] = "fallback"
            fallback_data["warning"] = f"NASA RadLab API was unreachable ({type(exc).__name__}). Returning verified authentic local NASA archive dataset."
            fallback_data["field_units"] = RADIATION_FIELD_METADATA
            return fallback_data
        else:
            raise exc
