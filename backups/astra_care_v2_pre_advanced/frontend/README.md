# ASTRA CARE – Frontend Application
### Astronaut Health and Space Radiation Monitoring System (Frontend Client)

**ASTRA CARE** is a mission-grade aerospace operations dashboard built for monitoring space radiation dosimetry and astronaut physiological vitals during long-duration spaceflight missions.

This frontend connects to the Python FastAPI backend (`http://127.0.0.1:8000`) using modern, modular JavaScript via the Fetch API, styled with a deep-space dark navy theme accented in neon cyan, blue, and purple.

---

## 🛠️ Technology Stack

- **HTML5**: Semantic markup with 6 modular views and embedded vector graphics (SVGs).
- **CSS3**: Custom design system featuring CSS variables, glassmorphic surfaces (`backdrop-filter`), responsive grid systems, glowing neon telemetry accents, and pulse animations.
- **JavaScript (ES6+)**: Pure vanilla modular architecture with standard Fetch API (`async`/`await`). No React, Angular, or Vue.
- **Chart.js v4.4.2**: Offline bundled UMD library (`frontend/js/vendor/chart.umd.min.js`) rendering high-resolution time-series graphs for radiation and physiological vitals.

---

## 🚀 Quick Start & How to Run

### Prerequisites
Ensure the ASTRA CARE FastAPI backend server is running in a terminal:
```powershell
.\venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Backend API will be live at: `http://127.0.0.1:8000` (Swagger docs at: `http://127.0.0.1:8000/docs`).

### Launching the Frontend

You can launch the frontend using either of the following methods:

#### Option 1: Lightweight HTTP Server (Recommended)
From the project root directory, run:
```powershell
.\venv\Scripts\python.exe -m http.server 3000 --directory frontend
```
Then open your web browser to:
👉 **`http://127.0.0.1:3000`**

#### Option 2: Direct File Execution
You can also open `frontend/index.html` directly in any modern browser (Chrome, Edge, Firefox, Safari, Android mobile browsers). Because FastAPI includes unrestricted CORS (`allow_origins=["*"]`), cross-origin fetch calls will succeed seamlessly.

---

## 📱 Navigation & View Architecture

The interface is structured as a Single Page Application (SPA) with smooth client-side routing and deep-linking support (`#dashboard`, `#radiation`, `#health`, `#alerts`, `#history`, `#about`):

| View | Name | Core Responsibilities & Connected Endpoints |
|---|---|---|
| **1** | **Dashboard** | Mission overview, high-level KPIs, live UTC mission clock, connection status indicator, live 15s auto-polling toggle, and quick alerts preview. |
| **2** | **Radiation Monitoring** | Direct NASA RadLab integration. Displays absorbed dose rate ($\mu\text{Gy/hr}$), equivalent dose ($\mu\text{Sv/hr}$), particle flux, altitude, cumulative exposure (trapezoidal integration), descriptive statistics, and astronaut education guide. Connects to `GET /api/radiation/sample`, `GET /api/radiation/analysis`, `GET /api/radiation/history`, and `GET /api/radiation/fields`. |
| **3** | **Health Monitoring** | Displays 4 primary vitals (Heart Rate in BPM, Blood Pressure in mmHg, SpO2 %, Core Body Temp in °C). Features a validated Vitals Telemetry Submission Form posting directly to `POST /api/health/measurements` and displaying real-time clinical feedback and triggered alerts. |
| **4** | **Safety Alerts** | Unified flight safety alert console combining radiation alerts (`GET /api/alerts`) and physiological alerts (`GET /api/health/alerts`). Filter by module (`RADIATION`, `HEALTH`), severity (`CRITICAL`, `WARNING`, `INFO`), or keyword search. |
| **5** | **AI Assistant (Voice & Text)** | Cognitive astronaut companion. Type or speak queries via Web Speech API (`SpeechRecognition`). Plays answers aloud via `SpeechSynthesis` with pause/resume/stop controls. Connects to `POST /api/assistant/chat`. |
| **6** | **Health & Rad History** | 5 high-resolution Chart.js time-series graphs: Radiation Absorbed Dose, Heart Rate, Blood Pressure (Dual-line Systolic/Diastolic), Oxygen Saturation, and Body Temperature. |
| **7** | **About ASTRA CARE** | Complete mission architecture documentation, clinical benchmarks (NASA-STD-3001, NCRP 132, AHA, WHO), data classification guidelines, and non-diagnostic disclaimers. |

---

## 📂 Frontend Directory Structure

```
frontend/
├── index.html                 # Master HTML5 single-page application
├── README.md                  # Frontend documentation & setup instructions
├── css/
│   └── style.css              # Deep-space theme, design tokens, cards, alerts, forms, chat
└── js/
    ├── config.js              # Central API configuration (http://127.0.0.1:8000), fetch helper, toasts
    ├── radiation.js           # NASA RadLab telemetry, statistics, gauges, and educational guides
    ├── health.js              # Crew vitals rendering, client-side validation, POST submission handler
    ├── alerts.js              # Unified alert feed, multi-filter engine, recommendations formatter
    ├── assistant.js           # AI Text & Voice Assistant controller (SpeechRecognition & SpeechSynthesis)
    ├── charts.js              # Chart.js engine for 5 time-series visualizations
    ├── dashboard.js           # Master SPA router, mobile drawer controller, and live polling loop
    └── vendor/
        └── chart.umd.min.js   # Offline-bundled Chart.js v4.4.2 library (no CDN dependency)
```

---

## ⚙️ Configuration & Customization

The backend API URL is configured in a single location: [frontend/js/config.js](file:///c:/Users/TEJASHWINI%20SR/OneDrive/Desktop/NASA/frontend/js/config.js):
```javascript
const CONFIG = {
    API_BASE_URL: 'http://127.0.0.1:8000',
    ENDPOINTS: {
        RADIATION_SAMPLE: '/api/radiation/sample',
        RADIATION_ANALYSIS: '/api/radiation/analysis',
        RADIATION_HISTORY: '/api/radiation/history',
        RADIATION_ALERTS: '/api/alerts',
        HEALTH_MEASUREMENTS: '/api/health/measurements',
        HEALTH_HISTORY: '/api/health/history',
        HEALTH_ALERTS: '/api/health/alerts',
        RADIATION_FIELDS: '/api/radiation/fields',
        HEALTH_ROOT: '/api/health'
    },
    POLLING_INTERVAL_MS: 15000 // 15 seconds
};
```
If deploying the backend on a remote host, simply update `API_BASE_URL` in `config.js`.

---

## 🧪 Hackathon Demonstration Walkthrough

Follow these steps to demonstrate ASTRA CARE during judging or presentations:

1. **Verify Backend Status**: Look at the top right header pill. When connected, it glows green: `Backend Online (FastAPI)`.
2. **Explore Space Radiation (View 2)**:
   - Point out that measurements are retrieved from NASA's public RadLab API.
   - Highlight the **Cumulative Exposure** card demonstrating numerical trapezoidal integration.
   - Point out that units are preserved ($\mu\text{Gy/hr}$ vs $\mu\text{Sv/hr}$) and never combined erroneously.
3. **Log Crew Vitals (View 3)**:
   - Fill out the submission form with an elevated heart rate (e.g., `125` BPM) or low oxygen (`92`% SpO2).
   - Click **Transmit Vitals to Backend**.
   - Notice the instant feedback banner showing generated safety alerts (e.g., `Tachycardia Warning`, `Hypoxia Alert`).
   - Notice the telemetry table immediately updates with the new entry tagged as `simulated_demo`.
4. **Inspect Safety Alerts Console (View 4)**:
   - Filter by `CRITICAL` or `WARNING` to see the newly generated alert alongside radiation alerts.
   - Expand the alert card to show the backend-provided explanation and clinical recommendation.
5. **Review Telemetry Visualizations (View 5)**:
   - View the 5 charts dynamically plotting the historical radiation measurements and astronaut vital signs over time.
6. **Regulatory Compliance (View 6)**:
   - Highlight strict adherence to NASA-STD-3001, AHA, and WHO benchmarks, and note the non-diagnostic medical disclaimer.
