"""
reports.py - Astronaut Health and Space Radiation PDF Report Generator

Generates comprehensive, downloadable aerospace PDF reports for crew health and radiation exposure
using ReportLab.

Report Contents:
1. Aerospace Mission Header & Flight Metadata (Astronaut ID, Mission Day, Generated Timestamp).
2. Physiological Health Vitals Summary (Heart rate, Blood pressure, SpO2, Core body temperature).
3. Data Classification Transparency (Clearly labels simulated health data vs. historical vs. live feeds).
4. Space Radiation Dosimetry Summary (Cumulative absorbed dose, average rates, peak rate, active detectors).
5. Machine Learning Radiation Anomaly Detection Log (Isolation Forest scores, baseline Z-scores, root causes).
6. Active Safety Alerts & Advisories Log (Threshold benchmarks, root causes, operational recommendations).
7. Strict Non-Diagnostic & Non-Prescriptive Legal Notice (NASA-STD-3001 Vol 1 compliance).
"""

from datetime import datetime, timezone
import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle
)

from app.db import get_db_connection

logger = logging.getLogger("astra_care.reports")


def compile_astronaut_report_data(
    astronaut_id: Optional[str] = "AST-01",
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Compiles structured telemetry, health vitals, radiation exposure, ML anomalies,
    and safety alerts for report generation.
    """
    conn = get_db_connection(db_path)
    ast_id = astronaut_id or "AST-01"
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        # 1. Astronaut Health Records
        health_rows = conn.execute("""
        SELECT record_id, timestamp, heart_rate, heart_rate_unit,
               blood_pressure_systolic, blood_pressure_diastolic, blood_pressure_unit,
               oxygen_saturation, oxygen_saturation_unit,
               body_temperature, body_temperature_unit,
               source_device, data_classification, notes
        FROM astronaut_health_records
        WHERE astronaut_id = ?
        ORDER BY timestamp DESC
        LIMIT 20;
        """, (ast_id,)).fetchall()

        if not health_rows:
            # Query generic if specific ID not found
            health_rows = conn.execute("""
            SELECT record_id, timestamp, heart_rate, heart_rate_unit,
                   blood_pressure_systolic, blood_pressure_diastolic, blood_pressure_unit,
                   oxygen_saturation, oxygen_saturation_unit,
                   body_temperature, body_temperature_unit,
                   source_device, data_classification, notes
            FROM astronaut_health_records
            ORDER BY timestamp DESC
            LIMIT 20;
            """).fetchall()

        vitals_list = [dict(r) for r in health_rows]

        # 2. Radiation Telemetry Summary (Historical & Dynamic)
        rad_rows = conn.execute("""
        SELECT timestamp, instrument_id, absorbed_dose_rate, absorbed_dose_unit,
               dose_equivalent_rate, dose_equivalent_unit, flux, altitude, orbital_region,
               source_origin as data_source
        FROM radiation_records
        WHERE absorbed_dose_rate IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 30;
        """).fetchall()

        rad_list = [dict(r) for r in rad_rows]

        # Cumulative radiation stats
        doses = [r["absorbed_dose_rate"] for r in rad_list if r.get("absorbed_dose_rate") is not None]
        avg_dose = round(float(sum(doses) / len(doses)), 4) if doses else 0.0
        max_dose = round(float(max(doses)), 4) if doses else 0.0
        min_dose = round(float(min(doses)), 4) if doses else 0.0

        # Estimated cumulative dose in 24h period (~avg * 24)
        est_24h_absorbed_ugy = round(avg_dose * 24.0, 2)
        est_24h_equivalent_usv = round(avg_dose * 1.85 * 24.0, 2)

        # 3. ML Anomalies
        anom_rows = conn.execute("""
        SELECT anomaly_id, timestamp, instrument_id, absorbed_dose_rate, anomaly_score,
               severity, primary_contributing_feature, baseline_z_score, explanation
        FROM ml_anomaly_records
        ORDER BY timestamp DESC
        LIMIT 10;
        """).fetchall()
        anom_list = [dict(r) for r in anom_rows]

        # 4. Alerts
        alert_rows = conn.execute("""
        SELECT alert_id, severity, alert_type, timestamp, description, recommendation, guideline_reference
        FROM radiation_alerts
        ORDER BY timestamp DESC
        LIMIT 10;
        """).fetchall()
        alerts_list = [dict(r) for r in alert_rows]

        health_alert_rows = conn.execute("""
        SELECT alert_id, severity, alert_type, timestamp, description, explanation, recommendation
        FROM astronaut_health_alerts
        ORDER BY timestamp DESC
        LIMIT 10;
        """).fetchall()
        for ha in health_alert_rows:
            alerts_list.append(dict(ha))

        return {
            "report_id": f"REP-{ast_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}",
            "generated_at": now_iso,
            "astronaut_id": ast_id,
            "mission_name": "ASTRA CARE Orbital Health Monitoring - ISS Expedition",
            "telemetry_classifications": {
                "health_vitals": "simulated_demo" if any(v.get("data_classification") == "simulated_demo" for v in vitals_list) else "sensor_telemetry",
                "radiation_telemetry": "Historical NASA RadLab Archive (ISS 2022)",
                "streaming_telemetry": "Simulated Dynamic Demonstration Stream"
            },
            "data_provenance_summary": {
                "health_vitals": "simulated_demo" if any(v.get("data_classification") == "simulated_demo" for v in vitals_list) else "sensor_telemetry",
                "radiation_telemetry": "Historical NASA RadLab Archive (ISS 2022)",
                "streaming_telemetry": "Simulated Dynamic Demonstration Stream"
            },
            "health_vitals": vitals_list,
            "vitals_summary": {
                "record_count": len(vitals_list),
                "latest_vitals": vitals_list[0] if vitals_list else None,
                "vitals_records": vitals_list
            },
            "dosimetry_summary": {
                "records_evaluated": len(rad_list),
                "average_absorbed_dose_rate_ugy_hr": avg_dose,
                "peak_absorbed_dose_rate_ugy_hr": max_dose,
                "min_absorbed_dose_rate_ugy_hr": min_dose,
                "estimated_24h_absorbed_dose_ugy": est_24h_absorbed_ugy,
                "estimated_24h_dose_equivalent_usv": est_24h_equivalent_usv,
                "active_detectors": sorted(list({r["instrument_id"] for r in rad_list if r.get("instrument_id")}))
            },
            "radiation_summary": {
                "records_evaluated": len(rad_list),
                "average_absorbed_dose_rate_ugy_hr": avg_dose,
                "peak_absorbed_dose_rate_ugy_hr": max_dose,
                "min_absorbed_dose_rate_ugy_hr": min_dose,
                "estimated_24h_absorbed_dose_ugy": est_24h_absorbed_ugy,
                "estimated_24h_dose_equivalent_usv": est_24h_equivalent_usv,
                "active_detectors": sorted(list({r["instrument_id"] for r in rad_list if r.get("instrument_id")})),
                "radiation_records": rad_list[:15]
            },
            "ml_anomalies_summary": {
                "total_anomalies_flagged": len(anom_list),
                "anomalies": anom_list
            },
            "alerts_summary": {
                "total_active_alerts": len(alerts_list),
                "alerts": alerts_list
            },
            "disclaimer": (
                "ASTRA CARE reports provide operational aerospace telemetry tracking. "
                "This report does NOT provide medical diagnoses or pharmacological prescriptions. "
                "All health observations must be reviewed with the Mission Flight Surgeon. "
                "Simulated demonstration vitals and historical archives are transparently distinguished."
            )
        }
    finally:
        conn.close()


def generate_astronaut_pdf_report(
    astronaut_id: Optional[str] = "AST-01",
    db_path: Optional[Path] = None
) -> bytes:
    """
    Renders a multi-page, publication-grade PDF report using ReportLab.
    Returns the raw PDF binary bytes.
    """
    data = compile_astronaut_report_data(astronaut_id, db_path)
    buffer = io.BytesIO()

    # Document setup: 0.5-inch margins
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom aerospace color palette
    c_primary = colors.HexColor("#0f172a")     # Deep space navy
    c_secondary = colors.HexColor("#1e293b")   # Slate
    c_cyan = colors.HexColor("#06b6d4")        # Cyan accent
    c_blue = colors.HexColor("#3b82f6")        # Blue
    c_danger = colors.HexColor("#ef4444")      # Red
    c_warning = colors.HexColor("#f59e0b")     # Orange/Yellow
    c_light_bg = colors.HexColor("#f8fafc")    # Light table bg
    c_border = colors.HexColor("#cbd5e1")      # Border grey

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=c_primary
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569")
    )

    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=c_primary,
        spaceAfter=6,
        spaceBefore=10
    )

    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1e293b")
    )

    bold_label = ParagraphStyle(
        "BoldLabel",
        parent=body_style,
        fontName="Helvetica-Bold"
    )

    disclaimer_style = ParagraphStyle(
        "Disclaimer",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#64748b")
    )

    story = []

    # 1. Header Banner
    header_table_data = [
        [
            Paragraph("<b>ASTRA CARE 2.0</b> | Astronaut Health & Radiation Report", title_style),
            Paragraph(f"<b>Report ID:</b> {data['report_id']}<br/><b>Date:</b> {data['generated_at'][:10]}", subtitle_style)
        ]
    ]
    t_header = Table(header_table_data, colWidths=[4.2 * inch, 2.8 * inch])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_header)
    story.append(HRFlowable(width="100%", thickness=1.5, color=c_cyan, spaceBefore=4, spaceAfter=8))

    # 2. Metadata Box
    meta_data = [
        [
            Paragraph("<b>Target Astronaut:</b>", bold_label), Paragraph(data["astronaut_id"], body_style),
            Paragraph("<b>Mission:</b>", bold_label), Paragraph(data["mission_name"], body_style)
        ],
        [
            Paragraph("<b>Health Telemetry Status:</b>", bold_label), Paragraph("SIMULATED DEMONSTRATION DATA (Labeled)", body_style),
            Paragraph("<b>Radiation Data Source:</b>", bold_label), Paragraph("NASA RadLab Historical Archive (ISS)", body_style)
        ]
    ]
    t_meta = Table(meta_data, colWidths=[1.8 * inch, 2.0 * inch, 1.4 * inch, 2.0 * inch])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c_light_bg),
        ('BOX', (0, 0), (-1, -1), 0.5, c_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 8))

    # 3. Health Telemetry Section
    story.append(Paragraph("1. Physiological Health Vitals Log", section_heading))
    vitals_records = data["vitals_summary"]["vitals_records"]

    if vitals_records:
        vitals_table_data = [
            ["Timestamp", "Heart Rate", "Blood Pressure", "SpO2", "Body Temp", "Classification"]
        ]
        for vr in vitals_records[:8]:
            vitals_table_data.append([
                vr["timestamp"][:19].replace("T", " "),
                f"{vr.get('heart_rate', 'N/A')} BPM",
                f"{vr.get('blood_pressure_systolic', 'N/A')}/{vr.get('blood_pressure_diastolic', 'N/A')} mmHg",
                f"{vr.get('oxygen_saturation', 'N/A')}%",
                f"{vr.get('body_temperature', 'N/A')} °C",
                vr.get("data_classification", "simulated_demo")
            ])
        t_vitals = Table(vitals_table_data, colWidths=[1.6 * inch, 1.1 * inch, 1.4 * inch, 0.9 * inch, 1.0 * inch, 1.2 * inch])
        t_vitals.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), c_secondary),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_light_bg]),
            ('BOX', (0, 0), (-1, -1), 0.5, c_border),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_vitals)
    else:
        story.append(Paragraph("No physiological health records available for this astronaut.", body_style))

    story.append(Spacer(1, 8))

    # 4. Space Radiation Dosimetry Section
    story.append(Paragraph("2. Space Radiation Dosimetry & Exposure Assessment", section_heading))
    rad_sum = data["radiation_summary"]

    dosimetry_summary_data = [
        [
            Paragraph("<b>Average Absorbed Dose Rate:</b>", bold_label), Paragraph(f"{rad_sum['average_absorbed_dose_rate_ugy_hr']} µGy/hr", body_style),
            Paragraph("<b>Peak Absorbed Dose Rate:</b>", bold_label), Paragraph(f"{rad_sum['peak_absorbed_dose_rate_ugy_hr']} µGy/hr", body_style)
        ],
        [
            Paragraph("<b>Estimated 24h Absorbed Dose:</b>", bold_label), Paragraph(f"{rad_sum['estimated_24h_absorbed_dose_ugy']} µGy", body_style),
            Paragraph("<b>Estimated 24h Dose Equivalent:</b>", bold_label), Paragraph(f"{rad_sum['estimated_24h_dose_equivalent_usv']} µSv (Q ~ 1.85)", body_style)
        ],
        [
            Paragraph("<b>Active Detectors Sampled:</b>", bold_label), Paragraph(", ".join(rad_sum["active_detectors"]), body_style),
            Paragraph("<b>Safety Standard:</b>", bold_label), Paragraph("NASA-STD-3001 Vol 1 / NCRP-132", body_style)
        ]
    ]
    t_dosi = Table(dosimetry_summary_data, colWidths=[2.0 * inch, 1.6 * inch, 1.8 * inch, 1.8 * inch])
    t_dosi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
        ('BOX', (0, 0), (-1, -1), 0.5, c_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
    ]))
    story.append(t_dosi)
    story.append(Spacer(1, 8))

    # 5. Machine Learning Radiation Anomaly Detection Section
    story.append(Paragraph("3. Machine Learning Radiation Anomaly Detections (Isolation Forest)", section_heading))
    anoms = data["ml_anomalies_summary"]["anomalies"]
    if anoms:
        anom_table_data = [
            ["Anomaly ID", "Timestamp", "Detector", "Rate (µGy/hr)", "Score", "Severity", "Explanation"]
        ]
        for a in anoms[:5]:
            anom_table_data.append([
                a["anomaly_id"],
                a["timestamp"][:16].replace("T", " "),
                a["instrument_id"],
                str(a.get("absorbed_dose_rate")),
                str(round(float(a.get("anomaly_score", 0.0)), 3)),
                a["severity"].replace("_ANOMALY", ""),
                Paragraph(a.get("explanation", "Deviation from historical baseline"), body_style)
            ])
        t_anom = Table(anom_table_data, colWidths=[1.1 * inch, 1.1 * inch, 0.8 * inch, 0.9 * inch, 0.6 * inch, 0.9 * inch, 1.8 * inch])
        t_anom.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#334155")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.0),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_light_bg]),
            ('BOX', (0, 0), (-1, -1), 0.5, c_border),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_anom)
    else:
        story.append(Paragraph("No active machine learning statistical anomalies flagged in the current evaluation window.", body_style))

    story.append(Spacer(1, 8))

    # 6. Safety Alerts Log
    story.append(Paragraph("4. Mission Safety Alerts & Operational Guidance Log", section_heading))
    alerts = data["alerts_summary"]["alerts"]
    if alerts:
        alert_table_data = [
            ["Alert ID", "Severity", "Type", "Timestamp", "Description & Operational Action"]
        ]
        for al in alerts[:5]:
            desc_text = f"<b>{al.get('description', '')}</b><br/><i>Follow-up:</i> {al.get('recommendation', 'Follow standard CHeCS flight rules.')}"
            alert_table_data.append([
                al.get("alert_id", "ALT"),
                al.get("severity", "WARNING"),
                al.get("alert_type", "ADVISORY"),
                al.get("timestamp", "")[:16].replace("T", " "),
                Paragraph(desc_text, body_style)
            ])
        t_alert = Table(alert_table_data, colWidths=[1.2 * inch, 0.8 * inch, 1.3 * inch, 1.1 * inch, 2.8 * inch])
        t_alert.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.0),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, c_light_bg]),
            ('BOX', (0, 0), (-1, -1), 0.5, c_border),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_alert)
    else:
        story.append(Paragraph("Zero safety alerts or operational warnings triggered in this telemetry interval.", body_style))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#94a3b8"), spaceBefore=4, spaceAfter=6))

    # 7. Mandatory Aerospace Legal & Medical Notice
    disclaimer_text = (
        "<b>MANDATORY SCIENTIFIC & AEROSPACE MEDICAL NOTICE:</b><br/>"
        "ASTRA CARE is an informational spaceflight telemetry monitoring and research decision-support tool. "
        "This report does NOT constitute a clinical medical diagnosis, pathological prognosis, or medical prescription. "
        "All physiological parameters represent telemetry recordings and must be clinically evaluated by a certified Mission "
        "Flight Surgeon or Crew Medical Officer (CMO). Astronaut health measurements shown here are simulated demonstration "
        "data. Space radiation measurements originate from the NASA Open Science Data Repository (OSDR) RadLab archive and "
        "represent historical research measurements recorded aboard the ISS (2022); they are NOT live telemetry."
    )
    story.append(Paragraph(disclaimer_text, disclaimer_style))

    # Build PDF
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
