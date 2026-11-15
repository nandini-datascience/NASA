"""
test_endpoints.py - Comprehensive API Endpoint Testing via Live Uvicorn Server

Tests all HTTP endpoints:
- GET /
- GET /api/radiation/sample
- GET /api/radiation/fields
- GET /api/health
- GET /api/radiation/analysis
- GET /api/radiation/history
- GET /api/alerts
- GET /docs (Swagger UI)
- CORS Preflight & Fetch integration
"""

import threading
import time
import requests
import uvicorn
from app.main import app


def run_server():
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=8002,
        log_level="warning"
    )
    server = uvicorn.Server(config)
    return server


def main():
    server = run_server()
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    session = requests.Session()
    session.trust_env = False  # Avoid sandbox loopback proxy interference

    base_url = "http://127.0.0.1:8002"

    # Wait for server to bind and be ready
    for _ in range(30):
        time.sleep(0.5)
        try:
            r_check = session.get(f"{base_url}/api/health", timeout=1.0)
            if r_check.status_code == 200:
                break
        except Exception:
            pass

    try:
        print("=== 1. Testing GET / (Homepage) ===")
        r = session.get(f"{base_url}/")
        print("Status:", r.status_code)
        data = r.json()
        print("Project:", data["project"])
        print("Database Status:", data["database_status"])
        assert r.status_code == 200
        assert data["status"] == "operational"
        assert "endpoints" in data

        print("\n=== 2. Testing GET /api/health ===")
        r = session.get(f"{base_url}/api/health")
        print("Status:", r.status_code)
        data = r.json()
        print("Health payload:", data)
        assert r.status_code == 200
        assert data["status"] == "healthy"
        assert data["database"]["status"] == "connected"

        print("\n=== 3. Testing GET /api/radiation/fields ===")
        r = session.get(f"{base_url}/api/radiation/fields")
        print("Status:", r.status_code)
        data = r.json()
        print("Field count:", len(data["fields"]))
        assert r.status_code == 200
        assert "absorbed_dose_rate" in data["fields"]
        assert "dose_equivalent_rate" in data["fields"]

        print("\n=== 4. Testing GET /api/radiation/sample ===")
        r = session.get(f"{base_url}/api/radiation/sample?limit=5")
        print("Status:", r.status_code)
        data = r.json()
        print("Source status:", data["source_status"])
        print("Records returned:", len(data["records"]))
        assert r.status_code == 200
        assert len(data["records"]) > 0

        print("\n=== 5. Testing GET /api/radiation/analysis ===")
        # Use advisory threshold 2.0 µGy/hr to trigger alerts on real NASA data for testing alert engine
        r = session.get(f"{base_url}/api/radiation/analysis?limit=25&advisory_threshold_ugy=2.0")
        print("Status:", r.status_code)
        data = r.json()
        print("Analysis status:", data["status"])
        print("Absorbed dose stats:", data["radiation_analysis"]["absorbed_dose_analysis"]["statistics"])
        print("Cumulative absorbed dose:", data["radiation_analysis"]["absorbed_dose_analysis"]["cumulative_exposure"])
        print("Dose-equivalent stats:", data["radiation_analysis"]["dose_equivalent_analysis"]["statistics"])
        print("Cumulative dose-equivalent:", data["radiation_analysis"]["dose_equivalent_analysis"]["cumulative_exposure"])
        print("Validation report:", data["validation_report"])
        print("Alerts summary:", {
            "total": data["alerts_summary"]["total_alerts_generated"],
            "quality_warnings": data["alerts_summary"]["data_quality_warnings_count"],
            "health_alerts": data["alerts_summary"]["health_risk_alerts_count"]
        })
        assert r.status_code == 200
        assert "absorbed_dose_analysis" in data["radiation_analysis"]
        assert "dose_equivalent_analysis" in data["radiation_analysis"]
        assert data["radiation_analysis"]["absorbed_dose_analysis"]["unit"] == "µGy/hr"
        assert data["radiation_analysis"]["dose_equivalent_analysis"]["unit"] == "µSv/hr"
        assert data["alerts_summary"]["health_risk_alerts_count"] > 0

        print("\n=== 6. Testing GET /api/radiation/history ===")
        r = session.get(f"{base_url}/api/radiation/history?limit=10&offset=0")
        print("Status:", r.status_code)
        data = r.json()
        print("Total stored in DB:", data["total_records"])
        print("Returned in page:", data["returned_count"])
        print("First record:", data["records"][0] if data["records"] else None)
        assert r.status_code == 200
        assert data["total_records"] > 0
        assert len(data["records"]) <= 10

        print("\n=== 7. Testing GET /api/alerts ===")
        r = session.get(f"{base_url}/api/alerts?limit=10")
        print("Status:", r.status_code)
        data = r.json()
        print("Total alerts stored:", data["total_alerts"])
        print("Category breakdown:", data["category_breakdown"])
        print("Severity breakdown:", data["severity_breakdown"])
        if data["alerts"]:
            print("First alert sample:", data["alerts"][0])
        assert r.status_code == 200

        print("\n=== 8. Testing GET /api/alerts with category filter ===")
        r = session.get(f"{base_url}/api/alerts?category=DATA_QUALITY_WARNING&limit=5")
        data = r.json()
        print("Filtered quality warnings count:", data["returned_count"])
        for a in data["alerts"]:
            assert a["category"] == "DATA_QUALITY_WARNING"

        print("\n=== 9. Testing GET /docs (FastAPI Swagger UI) ===")
        r = session.get(f"{base_url}/docs")
        print("Status:", r.status_code)
        assert r.status_code == 200
        assert "swagger" in r.text.lower() or "swagger-ui" in r.text.lower()

        print("\n=== 10. Testing CORS with JavaScript Fetch Origin ===")
        r = session.get(
            f"{base_url}/api/radiation/analysis",
            headers={"Origin": "http://localhost:3000"}
        )
        print("CORS Access-Control-Allow-Origin:", r.headers.get("access-control-allow-origin"))
        assert r.headers.get("access-control-allow-origin") in ["http://localhost:3000", "*"]

        print("\n=======================================================")
        print(">>> ALL 10 ENDPOINT INTEGRATION TESTS PASSED SUCCESSFULLY! <<<")
        print("=======================================================")

    finally:
        server.should_exit = True


if __name__ == "__main__":
    main()
