"""
model.py - Machine Learning Anomaly Detection Model for Space Radiation Monitoring

Implements:
1. Unsupervised Anomaly Detection using Isolation Forest:
   - Evaluates multidimensional radiation feature vectors (absorbed dose rate, flux,
     detector z-score, temporal rate-of-change, flux-to-dose ratio, orbital SAA context).
   - Operates strictly unsupervised because authentic space radiation research archives
     do not possess ground-truth human event labels.
2. Explainability Engine:
   - Dissects why a reading was flagged (primary contributing feature, detector baseline
     deviation, SAA proximity, rate-of-change jump).
   - Distinguishes statistical ML anomalies from validated clinical/operational health thresholds.
3. Serialization & Deserialization:
   - Saves model weights, standard scaler, and detector baseline parameters via joblib & json.
   - Graceful fallback: automatically trains on authentic NASA RadLab dataset if not already fitted.
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.ml.pipeline import (
    FEATURE_COLUMNS,
    calculate_detector_baselines,
    clean_and_prepare_radiation_data,
    extract_features_from_dataframe,
    extract_features_single_reading
)

logger = logging.getLogger("astra_care.ml.model")

DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "datasets" / "models"
MODEL_FILE_NAME = "radiation_anomaly_model.joblib"
METADATA_FILE_NAME = "model_metadata.json"


class RadiationAnomalyDetector:
    """
    Production-grade Unsupervised Radiation Anomaly Detector for ASTRA CARE 2.0.
    Uses Isolation Forest to detect anomalous space radiation patterns and baseline excursions.
    """

    def __init__(self, contamination: float = 0.05, n_estimators: int = 100, random_state: int = 42):
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.model: Optional[IsolationForest] = None
        self.scaler: Optional[StandardScaler] = None
        self.detector_baselines: Dict[str, Dict[str, float]] = {}
        self.metadata: Dict[str, Any] = {}
        self.is_fitted = False

    def fit(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Trains the Isolation Forest anomaly detector on cleaned radiation measurements:
        1. Calculates detector baseline distributions.
        2. Computes multi-dimensional features.
        3. Scales features using StandardScaler.
        4. Fits IsolationForest trees.
        5. Computes evaluation summary and anomaly distribution.
        """
        logger.info(f"Training RadiationAnomalyDetector on {len(df)} measurements...")
        clean_df = clean_and_prepare_radiation_data(df)
        if len(clean_df) < 10:
            raise ValueError(f"Dataset too small to train Isolation Forest ({len(clean_df)} records, minimum 10 required).")

        # 1. Compute detector baselines
        self.detector_baselines = calculate_detector_baselines(clean_df)

        # 2. Extract features
        X, engineered_df = extract_features_from_dataframe(clean_df, self.detector_baselines)

        # 3. Fit StandardScaler
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # 4. Fit Isolation Forest
        self.model = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=self.random_state,
            n_jobs=-1
        )
        self.model.fit(X_scaled)
        self.is_fitted = True

        # 5. Evaluate on training distribution
        train_predictions = self.model.predict(X_scaled)  # 1 for normal, -1 for anomaly
        train_scores = self.model.decision_function(X_scaled)  # higher = more normal, lower = more anomalous
        anomalies_detected = int(np.sum(train_predictions == -1))
        anomaly_ratio = float(anomalies_detected / len(train_predictions))

        self.metadata = {
            "algorithm": "Isolation Forest (scikit-learn)",
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "training_samples_count": len(clean_df),
            "feature_columns": FEATURE_COLUMNS,
            "contamination_parameter": self.contamination,
            "n_estimators": self.n_estimators,
            "anomalies_detected_in_training": anomalies_detected,
            "training_anomaly_percentage": round(anomaly_ratio * 100.0, 2),
            "score_mean": round(float(np.mean(train_scores)), 4),
            "score_std": round(float(np.std(train_scores)), 4),
            "score_min": round(float(np.min(train_scores)), 4),
            "score_max": round(float(np.max(train_scores)), 4),
            "detector_baselines": self.detector_baselines,
            "algorithm_selection_rationale": (
                "Isolation Forest was selected because the authentic NASA RadLab telemetry contains no human-labeled "
                "ground-truth radiation anomalies. Isolation Forest builds an ensemble of random trees where abnormal "
                "observations have noticeably shorter average path lengths. It operates with O(n log n) complexity, "
                "runs streaming inference in < 2ms, handles non-linear feature interactions, and avoids distance-metric "
                "bottlenecks present in Local Outlier Factor (LOF)."
            ),
            "limitations": (
                "Unsupervised anomaly detection flags statistical deviations from training distributions; it does NOT "
                "replace validated radiation dosimetry health limits (NASA-STD-3001 / NCRP Report 132). High readings "
                "caused by expected nominal orbital dynamics (such as nominal SAA transit) are statistical excursions "
                "and must be contextualized with spacecraft orbital location."
            )
        }

        logger.info(f"Model trained successfully. Detected {anomalies_detected}/{len(clean_df)} ({round(anomaly_ratio*100, 1)}%) baseline outliers.")
        return self.metadata

    def predict_reading(
        self,
        reading: Dict[str, Any],
        previous_reading: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluates a single radiation reading in real-time streaming inference:
        - Returns binary anomaly prediction (is_anomaly: True/False)
        - Returns continuous anomaly score (decision_function)
        - Returns detailed explainability breakdown:
          * Primary contributing feature
          * Detector baseline deviation (Z-score)
          * Plain-language explanation
          * Recommended verification action
        """
        if not self.is_fitted or self.model is None or self.scaler is None:
            raise RuntimeError("Model is not fitted. Train or load model before running prediction.")

        inst = str(reading.get("instrument_id") or "UnknownDetector")
        dose_rate = float(reading.get("absorbed_dose_rate") or 0.0)

        # Extract features
        X_vec = extract_features_single_reading(reading, self.detector_baselines, previous_reading)
        X_scaled = self.scaler.transform(X_vec)

        # Isolation forest inference (decision_function: higher = normal, negative = anomalous)
        raw_score = float(self.model.decision_function(X_scaled)[0])
        is_anomaly = bool(raw_score < 0.0)

        # Baseline info
        base = self.detector_baselines.get(inst, {"mean_dose_rate": 2.0, "std_dose_rate": 0.5})
        z_score = round((dose_rate - base["mean_dose_rate"]) / base["std_dose_rate"], 2)

        # Delta info
        delta = 0.0
        if previous_reading and previous_reading.get("instrument_id") == inst:
            prev_val = previous_reading.get("absorbed_dose_rate")
            if prev_val is not None:
                delta = round(dose_rate - float(prev_val), 3)

        # Determine severity & explanation
        severity = "NORMAL"
        primary_feature = "nominal_distribution"
        explanation = f"Measurement ({dose_rate} µGy/hr) aligns with historical baseline for detector {inst} (mean: {base['mean_dose_rate']} µGy/hr)."
        recommendation = "Continue nominal telemetry monitoring."

        if is_anomaly:
            if raw_score < -0.15 or z_score >= 4.0 or dose_rate >= 50.0:
                severity = "CRITICAL_ANOMALY"
            elif raw_score < -0.08 or z_score >= 2.5 or abs(delta) >= 10.0:
                severity = "WARNING_ANOMALY"
            else:
                severity = "ADVISORY_ANOMALY"

            # Identify primary contributing feature
            # Feature columns: ["absorbed_dose_rate", "flux", "detector_z_score", "dose_rate_delta", "flux_to_dose_ratio", "is_in_saa_region"]
            scaled_features = X_scaled[0]
            max_feat_idx = int(np.argmax(np.abs(scaled_features)))
            primary_feature = FEATURE_COLUMNS[max_feat_idx]

            in_saa = reading.get("orbital_region") == "SOUTH_ATLANTIC_ANOMALY" or X_vec[0][5] == 1.0

            if dose_rate >= 50.0 or primary_feature in ("absorbed_dose_rate", "detector_z_score"):
                explanation = (
                    f"Elevated radiation dose rate: {dose_rate} µGy/hr is {z_score:+.1f}σ from {inst} baseline "
                    f"(mean: {base['mean_dose_rate']} µGy/hr, σ: {base['std_dose_rate']})."
                )
            elif primary_feature == "dose_rate_delta":
                explanation = (
                    f"Rapid rate of change: {delta:+.2f} µGy/hr surge on detector {inst} compared to previous reading."
                )
            elif primary_feature == "flux":
                explanation = (
                    f"Unusual particle flux: {reading.get('flux')} particles/(cm²·sr·s) exceeds nominal baseline."
                )
            elif in_saa:
                explanation = (
                    f"Statistical anomaly coinciding with South Atlantic Anomaly (SAA) transit pass. "
                    f"Observed rate: {dose_rate} µGy/hr ({z_score:+.1f}σ baseline excursion)."
                )
            else:
                explanation = (
                    f"Multivariate pattern anomaly: unusual correlation between dose rate ({dose_rate} µGy/hr) "
                    f"and particle flux on detector {inst}."
                )

            if in_saa:
                recommendation = "Correlate with orbital trajectory map. Elevated flux is typical during SAA transit; verify return to baseline post-transit."
            else:
                recommendation = "Verify detector operating voltage and check external space weather monitors (NOAA SWPC / GOES) for solar energetic particles."

        return {
            "is_anomaly": is_anomaly,
            "anomaly_score": round(raw_score, 4),
            "normalized_abnormality_index": round(max(0.0, min(1.0, (-raw_score + 0.2) / 0.4)), 3),
            "severity": severity,
            "primary_contributing_feature": primary_feature,
            "detector_id": inst,
            "measured_dose_rate": dose_rate,
            "detector_baseline_mean": base["mean_dose_rate"],
            "detector_baseline_std": base["std_dose_rate"],
            "baseline_z_score": z_score,
            "dose_rate_delta": delta,
            "explanation": explanation,
            "recommendation": recommendation,
            "model_version": self.metadata.get("algorithm", "Isolation Forest"),
            "distinction_notice": (
                "Statistical anomaly denotes a mathematical deviation from historical training patterns. "
                "It is distinct from medical or operational threshold alerts (NASA-STD-3001)."
            )
        }

    def save(self, model_dir: Optional[Path] = None):
        """Saves model weights and metadata to disk."""
        target_dir = model_dir or DEFAULT_MODEL_DIR
        target_dir.mkdir(parents=True, exist_ok=True)

        bundle = {
            "model": self.model,
            "scaler": self.scaler,
            "detector_baselines": self.detector_baselines,
            "contamination": self.contamination,
            "n_estimators": self.n_estimators,
            "random_state": self.random_state
        }
        model_path = target_dir / MODEL_FILE_NAME
        joblib.dump(bundle, model_path)

        metadata_path = target_dir / METADATA_FILE_NAME
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2)

        logger.info(f"Saved trained RadiationAnomalyDetector to {model_path}")

    def load(self, model_dir: Optional[Path] = None) -> bool:
        """Loads model weights and metadata from disk."""
        target_dir = model_dir or DEFAULT_MODEL_DIR
        model_path = target_dir / MODEL_FILE_NAME
        metadata_path = target_dir / METADATA_FILE_NAME

        if not model_path.exists():
            return False

        try:
            bundle = joblib.load(model_path)
            self.model = bundle["model"]
            self.scaler = bundle["scaler"]
            self.detector_baselines = bundle["detector_baselines"]
            self.contamination = bundle.get("contamination", 0.05)
            self.n_estimators = bundle.get("n_estimators", 100)
            self.random_state = bundle.get("random_state", 42)
            self.is_fitted = True

            if metadata_path.exists():
                with open(metadata_path, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)

            logger.info(f"Loaded trained RadiationAnomalyDetector from {model_path}")
            return True
        except Exception as exc:
            logger.error(f"Failed to load model from {model_path}: {exc}")
            return False


# Global singleton detector instance
_global_detector: Optional[RadiationAnomalyDetector] = None

def get_detector() -> RadiationAnomalyDetector:
    global _global_detector
    if _global_detector is None:
        _global_detector = RadiationAnomalyDetector()
        # Attempt to load saved model from disk
        if not _global_detector.load():
            logger.info("No saved model found on disk. Initializing and training on authentic NASA RadLab dataset...")
            from app.data import load_local_nasa_sample
            sample = load_local_nasa_sample()
            records = sample.get("records", [])
            if records:
                df = pd.DataFrame(records)
                _global_detector.fit(df)
                _global_detector.save()
    return _global_detector
