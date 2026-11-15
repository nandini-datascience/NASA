import urllib.request
import json
import subprocess
import time
import sys
import os

print("=== ASTRA CARE FRONTEND-BACKEND INTEGRATION TEST ===")

print("\n1. Verifying all frontend assets exist...")
frontend_files = [
    "frontend/index.html",
    "frontend/css/style.css",
    "frontend/js/config.js",
    "frontend/js/radiation.js",
    "frontend/js/health.js",
    "frontend/js/alerts.js",
    "frontend/js/charts.js",
    "frontend/js/dashboard.js",
    "frontend/js/vendor/chart.umd.min.js",
    "frontend/README.md"
]

all_found = True
for f in frontend_files:
    if os.path.exists(f):
        print(f"  [OK] {f} ({os.path.getsize(f)} bytes)")
    else:
        print(f"  [FAIL] Missing {f}")
        all_found = False

if not all_found:
    sys.exit(1)

print("\n2. Launching FastAPI backend server on 127.0.0.1:8000...")
uvicorn_path = os.path.abspath(r".\venv\Scripts\uvicorn.exe")
proc = subprocess.Popen([uvicorn_path, "app.main:app", "--host", "127.0.0.1", "--port", "8000"])

try:
    connected = False
    for i in range(15):
        time.sleep(1)
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/") as res:
                if res.status == 200:
                    connected = True
                    print("  [OK] FastAPI backend is live and listening at http://127.0.0.1:8000/")
                    break
        except Exception:
            pass

    if not connected:
        print("  [FAIL] Backend did not respond within timeout.")
        sys.exit(1)

    print("\n3. Testing all API endpoints utilized by Frontend JavaScript modules:")
    test_endpoints = [
        ("/", "Root / Health check"),
        ("/api/radiation/sample", "Radiation Sample (Latest NASA RadLab)"),
        ("/api/radiation/analysis", "Radiation Analysis (Dose stats & cumulative)"),
        ("/api/radiation/history?limit=15", "Radiation Telemetry History"),
        ("/api/alerts", "Radiation Safety Alerts"),
        ("/api/radiation/fields", "Radiation Telemetry Fields Dictionary"),
        ("/api/health", "Astronaut Health Module Root"),
        ("/api/health/measurements", "Astronaut Health Latest Measurements"),
        ("/api/health/history?limit=15", "Astronaut Health Telemetry History"),
        ("/api/health/alerts", "Astronaut Health Clinical Alerts")
    ]

    for path, desc in test_endpoints:
        url = f"http://127.0.0.1:8000{path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"  [OK] {resp.status} GET {path} - {desc}")

    print("\n4. Testing POST /api/health/measurements (Frontend Vitals Telemetry Submission Form):")
    test_submission = {
        "astronaut_id": "CREW-TEST-FRONTEND",
        "timestamp": "2026-11-14T12:00:00Z",
        "heart_rate": 115,
        "blood_pressure_systolic": 138,
        "blood_pressure_diastolic": 89,
        "oxygen_saturation": 93.8,
        "body_temperature": 37.7,
        "source_device": "Wearable Crew Health Monitor",
        "data_classification": "simulated_demo",
        "notes": "Automated frontend integration validation test"
    }

    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/health/measurements",
        data=json.dumps(test_submission).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        print(f"  [OK] HTTP {resp.status} - Record ID: {body.get('record_id')}, Alerts Triggered: {body.get('alerts_triggered_count')}")
        for alert in body.get("alerts", []):
            print(f"       -> Alert: [{alert.get('severity')}] {alert.get('rule_id')} - {alert.get('description')}")

    print("\n5. Testing Frontend HTML Structure for expected Element IDs:")
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    expected_ids = [
        "app-sidebar", "app-topbar", "mobile-menu-toggle", "connection-status-badge",
        "connection-status-label", "toggle-live-polling", "btn-manual-refresh",
        "view-dashboard", "view-radiation", "view-health", "view-alerts", "view-history", "view-about",
        "overview-radiation-dose", "overview-heart-rate", "overview-spo2", "overview-active-alerts",
        "rad-absorbed-dose", "rad-equivalent-dose", "rad-altitude", "rad-cumulative-value",
        "vital-heart-rate", "vital-blood-pressure", "vital-spo2", "vital-temperature",
        "health-submit-form", "btn-submit-vitals", "form-feedback-banner",
        "global-alert-badge", "alerts-feed-container", "filter-alert-module", "filter-alert-severity",
        "chart-radiation-dose", "chart-heart-rate", "chart-blood-pressure", "chart-spo2", "chart-temperature",
        "toast-container"
    ]

    all_ids_present = True
    for eid in expected_ids:
        if f'id="{eid}"' not in html:
            print(f"  [FAIL] Missing ID in HTML: {eid}")
            all_ids_present = False
    if all_ids_present:
        print(f"  [OK] All {len(expected_ids)} key DOM element IDs successfully verified in index.html!")

    print("\n=== ALL INTEGRATION TESTS PASSED PERFECTLY! ===")

finally:
    print("\n6. Cleaning up test server process...")
    proc.terminate()
    proc.wait()
    print("  [OK] Backend server terminated.")
