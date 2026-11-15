/**
 * config.js - ASTRA CARE Frontend Configuration & API Client
 * 
 * Provides:
 * - Centralized backend API base URL
 * - Standardized endpoint paths
 * - Resilient fetch wrapper with timeout, CORS handling, and network error reporting
 * - Formatter helpers for dates, units, and safety escaping
 */

const CONFIG = {
    // Backend API Base URL (FastAPI)
    API_BASE_URL: 'http://127.0.0.1:8000',

    // Auto-refresh interval for live dashboard polling (milliseconds)
    POLLING_INTERVAL_MS: 15000,

    // Request timeout in milliseconds
    REQUEST_TIMEOUT_MS: 10000,

    // Endpoint paths
    ENDPOINTS: {
        // System & General
        ROOT: '/',
        HEALTH_CHECK: '/api/health',

        // Radiation Monitoring
        RADIATION_SAMPLE: '/api/radiation/sample',
        RADIATION_ANALYSIS: '/api/radiation/analysis',
        RADIATION_HISTORY: '/api/radiation/history',
        RADIATION_ALERTS: '/api/alerts',
        RADIATION_FIELDS: '/api/radiation/fields',

        // Dynamic Radiation Streaming & ML (ASTRA CARE 2.0)
        RADIATION_STREAM_LATEST: '/api/radiation/stream/latest',
        RADIATION_STREAM_HISTORY: '/api/radiation/stream/history',
        RADIATION_STREAM_CONTROL: '/api/radiation/stream/control',
        RADIATION_STREAM_READING: '/api/radiation/stream/reading',
        RADIATION_ML_STATUS: '/api/radiation/ml/status',
        RADIATION_ML_PREDICT: '/api/radiation/ml/predict',
        RADIATION_ML_ANOMALIES: '/api/radiation/ml/anomalies',
        RADIATION_TELEMETRY_STATUS: '/api/radiation/telemetry-status',

        // Astronaut Health Monitoring
        HEALTH_MEASUREMENTS: '/api/health/measurements',
        HEALTH_HISTORY: '/api/health/history',
        HEALTH_ALERTS: '/api/health/alerts',

        // AI Health Assistant (Task 04 & Task 05) & Offline Voice Assistant
        ASSISTANT_CHAT: '/api/assistant/chat',
        ASSISTANT_STATUS: '/api/assistant/status',
        VOICE_STATUS: '/api/assistant/voice/status',
        VOICE_TO_TEXT: '/api/assistant/voice-to-text',
        TEXT_TO_SPEECH: '/api/assistant/text-to-speech',
        NETWORK_STATUS: '/api/system/network-status',

        // Advanced Features Endpoints (Tasks 01-06)
        NASA_LATEST: '/api/radiation/nasa/latest',
        NASA_SYNC: '/api/radiation/nasa/sync',
        NASA_SYNC_STATUS: '/api/radiation/nasa/sync-status',
        RADIATION_LOCATIONS: '/api/radiation/locations',
        RADIATION_FORECAST: '/api/radiation/forecast',
        RADIATION_FORECAST_GENERATE: '/api/radiation/forecast/generate',
        SMART_ALERTS: '/api/alerts/smart',
        SMART_ALERTS_EVALUATE: '/api/alerts/evaluate',
        DETECTOR_COMPARISON: '/api/radiation/detectors/comparison',
        DETECTOR_LIST: '/api/radiation/detectors/list',
        REPORT_PREVIEW: '/api/reports/preview',
        REPORT_PDF: '/api/reports/pdf',

        // 3D Astronaut Digital Twin Endpoints
        TWIN_RADIATION_LATEST: '/api/radiation/latest',
        TWIN_HEALTH_LATEST: '/api/health/latest',
        TWIN_ASTRONAUT_PROFILE: '/api/astronaut/profile',
        TWIN_HEALTH_ECG: '/api/health/ecg',
        TWIN_HEALTH_EEG: '/api/health/eeg',
        TWIN_BODY_REGIONS: '/api/astronaut/body-regions'
    }
};

/**
 * Standardized API Fetch Wrapper.
 * - Handles JSON serialization/deserialization.
 * - Implements request timeouts.
 * - Dispatches connection state updates to the UI.
 * 
 * @param {string} endpoint - API path (e.g. '/api/radiation/sample')
 * @param {object} options - Standard fetch options (method, headers, body)
 * @returns {Promise<any>} Parsed JSON response
 */
async function apiFetch(endpoint, options = {}) {
    const url = `${CONFIG.API_BASE_URL}${endpoint}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CONFIG.REQUEST_TIMEOUT_MS);

    const defaultHeaders = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    };

    const fetchConfig = {
        ...options,
        signal: controller.signal,
        headers: {
            ...defaultHeaders,
            ...(options.headers || {})
        }
    };

    try {
        const response = await fetch(url, fetchConfig);
        clearTimeout(timeoutId);

        // Update connection status badge in UI
        updateConnectionStatus(true);

        if (!response.ok) {
            let errorDetail = `HTTP Error ${response.status}: ${response.statusText}`;
            try {
                const errJson = await response.json();
                if (errJson.detail) {
                    errorDetail = typeof errJson.detail === 'string' 
                        ? errJson.detail 
                        : JSON.stringify(errJson.detail);
                }
            } catch (e) {
                // Non-JSON error payload
            }
            const error = new Error(errorDetail);
            error.status = response.status;
            throw error;
        }

        return await response.json();
    } catch (error) {
        clearTimeout(timeoutId);
        if (error.name === 'AbortError') {
            updateConnectionStatus(false, 'Request Timed Out');
            throw new Error(`Connection timed out after ${CONFIG.REQUEST_TIMEOUT_MS / 1000}s. Check if backend is running.`);
        }
        updateConnectionStatus(false, error.message);
        throw error;
    }
}

/**
 * Updates the visual system connection status badge in the header/navbar.
 * 
 * @param {boolean} isConnected 
 * @param {string} errorMsg 
 */
function updateConnectionStatus(isConnected, errorMsg = '') {
    const badge = document.getElementById('connection-status-badge');
    const label = document.getElementById('connection-status-label');
    const toastContainer = document.getElementById('toast-container');

    if (!badge || !label) return;

    if (isConnected) {
        badge.className = 'status-indicator connected';
        label.textContent = 'BACKEND ONLINE';
        label.title = `Connected to ${CONFIG.API_BASE_URL}`;
    } else {
        badge.className = 'status-indicator disconnected';
        label.textContent = 'BACKEND OFFLINE';
        label.title = `Unable to reach ${CONFIG.API_BASE_URL} (${errorMsg})`;
    }
}

/**
 * Helper to display toast notifications.
 * 
 * @param {string} message 
 * @param {'success'|'warning'|'error'|'info'} type 
 * @param {number} duration 
 */
function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'warning') icon = '⚠️';
    if (type === 'error') icon = '❌';

    toast.innerHTML = `
        <span class="toast-icon">${icon}</span>
        <div class="toast-content">${escapeHtml(message)}</div>
        <button class="toast-close" onclick="this.parentElement.remove()">×</button>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 400);
    }, duration);
}

/**
 * Formats an ISO 8601 UTC timestamp for user-friendly display.
 * 
 * @param {string} isoString 
 * @returns {string} Formatted date & time
 */
function formatDateTime(isoString) {
    if (!isoString) return '—';
    try {
        const d = new Date(isoString);
        if (isNaN(d.getTime())) return isoString;
        return d.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false,
            timeZoneName: 'short'
        });
    } catch (e) {
        return isoString;
    }
}

/**
 * Formats a number with specified decimal precision.
 * 
 * @param {number|null|undefined} num 
 * @param {number} decimals 
 * @returns {string}
 */
function formatNumber(num, decimals = 2) {
    if (num === null || num === undefined || isNaN(num)) return '—';
    return Number(num).toFixed(decimals);
}

/**
 * Sanitizes input to prevent HTML injection.
 * 
 * @param {string} str 
 * @returns {string} Escaped string
 */
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
