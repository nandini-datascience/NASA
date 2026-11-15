"""
detector_comparison.py - Multi-Detector Radiation Comparison Engine

Compares space radiation detection instruments aboard the International Space Station
(such as DosTel1, DosTel2, Lidal, DB8, and REM-Lid).

Scientific Methodology:
1. Distinct Calibration & Shielding Geometries:
   - Radiation detectors aboard the ISS are mounted in different modules with varying local shielding:
     * DosTel1 (Columbus starboard bulkhead): Standard European module shielding (~15 g/cm² Al-eq).
     * DosTel2 (Columbus forward bulkhead): Adjacent to water-wall stowage packs (~22 g/cm² Al-eq).
     * Lidal (Columbus central): Light Ion Detector for ALTEA with silicon strip time-of-flight telescope.
     * REM-Lid: Broad-spectrum ionization chamber.
     * DB8: Russian Service Module dosimeter near crew quarters (~28 g/cm² Al-eq).
   - Variations in observed absorbed dose rates between detectors represent physical shielding
     attenuation and directional particle angular distributions rather than instrument malfunction.
2. Synchronized Metric Comparison:
   - Absorbed dose rate (µGy/hr).
   - Biological dose-equivalent rate (µSv/hr).
   - Particle flux (particles/(cm²·sr·s)).
   - Attenuation ratio (e.g. DosTel2 / DosTel1).
3. Handling Missing or Incompatible Data:
   - Gracefully handles detectors that do not measure specific channels (e.g. dose-equivalent without heavy-ion Q factor).
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from app.db import get_db_connection, query_multi_detector_stats

logger = logging.getLogger("astra_care.detector_comparison")


def get_detector_time_series_comparison(
    detectors: Optional[List[str]] = None,
    limit_per_detector: int = 30,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Retrieves time-series telemetry points for multiple detectors and aligns them
    for side-by-side comparative charting.
    """
    conn = get_db_connection(db_path)
    target_detectors = detectors or ["DosTel1", "DosTel2", "Lidal", "REM-Lid"]
    series_by_detector: Dict[str, List[Dict[str, Any]]] = {}

    try:
        for det in target_detectors:
            sql = """
            SELECT timestamp, instrument_id, absorbed_dose_rate, dose_equivalent_rate, flux, module
            FROM radiation_records
            WHERE instrument_id = ? AND absorbed_dose_rate IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT ?;
            """
            rows = conn.execute(sql, (det, limit_per_detector)).fetchall()
            pts = []
            for r in reversed(rows):  # Chronological order
                pts.append({
                    "timestamp": r["timestamp"],
                    "absorbed_dose_rate": round(float(r["absorbed_dose_rate"]), 4) if r["absorbed_dose_rate"] is not None else None,
                    "dose_equivalent_rate": round(float(r["dose_equivalent_rate"]), 4) if r["dose_equivalent_rate"] is not None else None,
                    "flux": round(float(r["flux"]), 4) if r["flux"] is not None else None,
                    "module": r["module"]
                })
            if pts:
                series_by_detector[det] = pts

        # Compute cross-detector differences & ratios if DosTel1 and DosTel2 are present
        ratio_dostel = None
        dostel1_pts = series_by_detector.get("DosTel1", [])
        dostel2_pts = series_by_detector.get("DosTel2", [])
        if dostel1_pts and dostel2_pts:
            avg1 = np.mean([p["absorbed_dose_rate"] for p in dostel1_pts if p["absorbed_dose_rate"] is not None])
            avg2 = np.mean([p["absorbed_dose_rate"] for p in dostel2_pts if p["absorbed_dose_rate"] is not None])
            if avg1 > 0:
                ratio_dostel = round(float(avg2 / avg1), 4)

        stats = query_multi_detector_stats(db_path)

        return {
            "status": "success",
            "detectors_evaluated": list(series_by_detector.keys()),
            "series": series_by_detector,
            "dostel_shielding_attenuation_ratio": ratio_dostel,
            "overall_detector_statistics": stats.get("detectors", []),
            "scientific_context": {
                "DosTel1_vs_DosTel2": (
                    "DosTel1 and DosTel2 are matched DOSTEL silicon semiconductor telescopes located in Columbus. "
                    "DosTel2 is positioned near water stowage containers, typically measuring 10-25% lower absorbed "
                    "dose due to secondary particle absorption by hydrogen-rich water shielding."
                ),
                "calibration_notice": (
                    "Detectors have unique physical response curves, silicon active areas, and directional orientations. "
                    "Never assume identical readings across different station locations."
                )
            }
        }
    finally:
        conn.close()
