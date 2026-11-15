"""
pipeline.py - Radiation Data Preprocessing & Feature Engineering Pipeline for ASTRA CARE ML

Implements:
1. Dataset cleaning, deduplication, and non-negative constraints.
2. Chronological timestamp ordering and time-aware train/test splitting (prevents future leakage).
3. Detector baseline statistics computation (mean and std_dev per detector geometry).
4. Feature engineering:
   - Absorbed dose rate (µGy/hr)
   - Particle flux (particles/(cm²·sr·s))
   - Detector-specific Z-score (deviation relative to detector's historical baseline)
   - Temporal rate of change (Delta dose_rate / Delta t)
   - Particle-to-dose physical ratio
   - SAA (South Atlantic Anomaly) spatial bounding indicator
"""

from datetime import datetime, timezone
import logging
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

logger = logging.getLogger("astra_care.ml.pipeline")

FEATURE_COLUMNS = [
    "absorbed_dose_rate",
    "flux",
    "detector_z_score",
    "dose_rate_delta",
    "flux_to_dose_ratio",
    "is_in_saa_region"
]

# South Atlantic Anomaly (SAA) Bounding Coordinates
SAA_LAT_MIN = -45.0
SAA_LAT_MAX = -5.0
SAA_LON_MIN = -90.0
SAA_LON_MAX = 0.0


def is_coordinate_in_saa(lat: Optional[float], lon: Optional[float]) -> float:
    """Returns 1.0 if coordinate is within the South Atlantic Anomaly, else 0.0."""
    if lat is None or lon is None:
        return 0.0
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        if math.isnan(lat_f) or math.isnan(lon_f):
            return 0.0
        if SAA_LAT_MIN <= lat_f <= SAA_LAT_MAX and SAA_LON_MIN <= lon_f <= SAA_LON_MAX:
            return 1.0
        return 0.0
    except (ValueError, TypeError):
        return 0.0


def clean_and_prepare_radiation_data(data: Union[List[Dict[str, Any]], pd.DataFrame]) -> pd.DataFrame:
    """
    Cleans raw NASA RadLab records:
    - Parses timestamps to timezone-aware UTC datetime.
    - Sorts chronologically.
    - Enforces non-negative physical values.
    - Removes duplicate (timestamp, instrument_id) readings.
    - Fills missing flux using median ratio if absorbed dose is available.
    """
    if isinstance(data, list):
        df = pd.DataFrame(data)
    else:
        df = data.copy()

    if df.empty:
        return pd.DataFrame()

    # 1. Clean string column names
    df.columns = [col.strip() for col in df.columns]

    # 2. Parse timestamps
    if "timestamp" not in df.columns:
        raise ValueError("Dataset must contain a 'timestamp' column.")

    df["dt"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["dt"]).sort_values("dt").reset_index(drop=True)

    # 3. Clean instrument_id
    if "instrument_id" not in df.columns:
        df["instrument_id"] = "UNKNOWN_DETECTOR"
    df["instrument_id"] = df["instrument_id"].astype(str).str.strip()

    # 4. Clean numeric radiation rates
    if "absorbed_dose_rate" not in df.columns:
        raise ValueError("Dataset must contain 'absorbed_dose_rate' column.")

    df["absorbed_dose_rate"] = pd.to_numeric(df["absorbed_dose_rate"], errors="coerce")
    # Discard non-numeric or negative values
    df = df[df["absorbed_dose_rate"].notnull() & (df["absorbed_dose_rate"] >= 0.0)].copy()

    # Clean flux
    if "flux" in df.columns:
        df["flux"] = pd.to_numeric(df["flux"], errors="coerce")
        df.loc[df["flux"] < 0.0, "flux"] = np.nan
    else:
        df["flux"] = np.nan

    # Fill missing flux using detector median flux-to-dose ratio (typical ~0.05 - 0.07 particles/(cm²·sr·s) per µGy/hr)
    valid_ratio = df[df["flux"].notnull() & (df["absorbed_dose_rate"] > 0.0)]
    if not valid_ratio.empty:
        median_ratio = (valid_ratio["flux"] / valid_ratio["absorbed_dose_rate"]).median()
    else:
        median_ratio = 0.055

    df["flux"] = df["flux"].fillna(df["absorbed_dose_rate"] * median_ratio)

    # Clean orbital coordinates
    for coord in ["latitude", "longitude", "altitude"]:
        if coord in df.columns:
            df[coord] = pd.to_numeric(df[coord], errors="coerce")
        else:
            df[coord] = np.nan

    # 5. Remove exact duplicate detector readings at the same timestamp
    df = df.drop_duplicates(subset=["dt", "instrument_id"]).reset_index(drop=True)

    return df


def calculate_detector_baselines(df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """
    Calculates historical baseline mean and standard deviation for each detector instrument.
    Essential to normalize detector geometry differences without bias.
    """
    baselines: Dict[str, Dict[str, float]] = {}

    for inst, group in df.groupby("instrument_id"):
        rates = group["absorbed_dose_rate"].values
        mean_rate = float(np.mean(rates)) if len(rates) > 0 else 2.0
        std_rate = float(np.std(rates)) if len(rates) > 1 and np.std(rates) > 1e-4 else 0.5
        fluxes = group["flux"].values
        mean_flux = float(np.mean(fluxes)) if len(fluxes) > 0 else 0.1
        std_flux = float(np.std(fluxes)) if len(fluxes) > 1 and np.std(fluxes) > 1e-4 else 0.02

        baselines[str(inst)] = {
            "mean_dose_rate": round(mean_rate, 4),
            "std_dose_rate": round(std_rate, 4),
            "mean_flux": round(mean_flux, 4),
            "std_flux": round(std_flux, 4),
            "sample_count": len(rates)
        }

    return baselines


def extract_features_from_dataframe(
    df: pd.DataFrame,
    baselines: Optional[Dict[str, Dict[str, float]]] = None
) -> Tuple[np.ndarray, pd.DataFrame]:
    """
    Extracts numerical feature matrix for machine learning:
    1. absorbed_dose_rate (µGy/hr)
    2. flux (particles/(cm²·sr·s))
    3. detector_z_score: (dose_rate - detector_mean) / detector_std
    4. dose_rate_delta: rate of change from previous reading of same detector
    5. flux_to_dose_ratio: flux / (dose_rate + 1e-5)
    6. is_in_saa_region: 1.0 if inside SAA, else 0.0
    """
    if baselines is None:
        baselines = calculate_detector_baselines(df)

    processed_df = df.copy()

    # 1. Detector Z-Score
    def get_z_score(row):
        inst = str(row["instrument_id"])
        base = baselines.get(inst, {"mean_dose_rate": 2.0, "std_dose_rate": 0.5})
        return (row["absorbed_dose_rate"] - base["mean_dose_rate"]) / base["std_dose_rate"]

    processed_df["detector_z_score"] = processed_df.apply(get_z_score, axis=1)

    # 2. Rate of Change Delta (per instrument sorted chronologically)
    processed_df["dose_rate_delta"] = 0.0
    for inst, indices in processed_df.groupby("instrument_id").groups.items():
        sub = processed_df.loc[indices]
        deltas = sub["absorbed_dose_rate"].diff().fillna(0.0)
        processed_df.loc[indices, "dose_rate_delta"] = deltas

    # 3. Flux to Dose Ratio
    processed_df["flux_to_dose_ratio"] = processed_df["flux"] / (processed_df["absorbed_dose_rate"] + 1e-5)

    # 4. SAA Bounding Region Flag
    processed_df["is_in_saa_region"] = processed_df.apply(
        lambda r: is_coordinate_in_saa(r.get("latitude"), r.get("longitude")),
        axis=1
    )

    X = processed_df[FEATURE_COLUMNS].values
    return X, processed_df


def extract_features_single_reading(
    reading: Dict[str, Any],
    baselines: Dict[str, Dict[str, float]],
    previous_reading: Optional[Dict[str, Any]] = None
) -> np.ndarray:
    """
    Extracts feature vector for a single streaming reading in real-time inference.
    """
    inst = str(reading.get("instrument_id") or "DosTel1")
    dose_rate = float(reading.get("absorbed_dose_rate") or 2.0)
    flux = float(reading.get("flux") or (dose_rate * 0.055))

    base = baselines.get(inst, {"mean_dose_rate": 2.0, "std_dose_rate": 0.5})
    z_score = (dose_rate - base["mean_dose_rate"]) / base["std_dose_rate"]

    # Compute delta from previous reading of same instrument if available
    delta = 0.0
    if previous_reading and previous_reading.get("instrument_id") == inst:
        prev_dose = previous_reading.get("absorbed_dose_rate")
        if prev_dose is not None:
            delta = dose_rate - float(prev_dose)

    flux_ratio = flux / (dose_rate + 1e-5)
    in_saa = is_coordinate_in_saa(reading.get("latitude"), reading.get("longitude"))

    vector = np.array([[
        dose_rate,
        flux,
        z_score,
        delta,
        flux_ratio,
        in_saa
    ]], dtype=np.float64)

    return vector


def time_aware_train_test_split(
    df: pd.DataFrame,
    train_ratio: float = 0.8
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Splits dataset chronologically to avoid future data leakage.
    First train_ratio of timestamps is training set; remaining is test set.
    """
    sorted_df = df.sort_values("dt").reset_index(drop=True)
    split_idx = int(len(sorted_df) * train_ratio)
    train_df = sorted_df.iloc[:split_idx].copy().reset_index(drop=True)
    test_df = sorted_df.iloc[split_idx:].copy().reset_index(drop=True)
    return train_df, test_df
