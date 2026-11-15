/**
 * radiation.js - ASTRA CARE Space Radiation Monitoring Module
 * 
 * Interfaces with:
 * - GET /api/radiation/sample
 * - GET /api/radiation/analysis
 * - GET /api/radiation/history
 * - GET /api/radiation/fields
 * 
 * Features:
 * - Preserves authentic scientific units (µGy/hr, µSv/hr, particles/(cm²·sr·s), km)
 * - Separates absorbed dose from equivalent dose
 * - Renders telemetry gauge, orbital position, statistics, and history table
 * - Strictly labels historical NASA OSDR RadLab telemetry
 * - Explains measurements in astronaut-friendly plain language
 */

const RadiationModule = {
    // Cache for latest radiation data
    currentSample: null,
    currentAnalysis: null,
    historyRecords: [],
    fieldsMetadata: null,

    /**
     * Initializes and loads all radiation monitoring data.
     */
    async init() {
        await Promise.all([
            this.loadRadiationSample(),
            this.loadRadiationAnalysis(),
            this.loadRadiationHistory(),
            this.loadFieldDefinitions()
        ]);
    },

    /**
     * Fetches radiation sample telemetry from NASA RadLab API.
     */
    async loadRadiationSample() {
        const loadingEl = document.getElementById('radiation-sample-loading');
        if (loadingEl) loadingEl.style.display = 'block';

        try {
            const data = await apiFetch(CONFIG.ENDPOINTS.RADIATION_SAMPLE + '?limit=10');
            this.currentSample = data;
            this.renderRadiationCards(data);
            return data;
        } catch (error) {
            console.error('Error fetching radiation sample:', error);
            this.renderRadiationError('sample', error.message);
        } finally {
            if (loadingEl) loadingEl.style.display = 'none';
        }
    },

    /**
     * Fetches statistical analysis and cumulative exposure.
     */
    async loadRadiationAnalysis() {
        try {
            const data = await apiFetch(CONFIG.ENDPOINTS.RADIATION_ANALYSIS + '?limit=50&max_gap_seconds=600');
            this.currentAnalysis = data;
            this.renderAnalysisStats(data);
            return data;
        } catch (error) {
            console.error('Error fetching radiation analysis:', error);
            this.renderRadiationError('analysis', error.message);
        }
    },

    /**
     * Fetches historical radiation records from SQLite database.
     */
    async loadRadiationHistory(limit = 20, offset = 0) {
        try {
            const data = await apiFetch(`${CONFIG.ENDPOINTS.RADIATION_HISTORY}?limit=${limit}&offset=${offset}`);
            this.historyRecords = data.records || [];
            this.renderRadiationHistoryTable(data);
            return data;
        } catch (error) {
            console.error('Error fetching radiation history:', error);
            this.renderRadiationError('history', error.message);
        }
    },

    /**
     * Fetches standardized field definitions and units.
     */
    async loadFieldDefinitions() {
        try {
            const data = await apiFetch(CONFIG.ENDPOINTS.RADIATION_FIELDS);
            this.fieldsMetadata = data.fields;
            this.renderEducationalGuides(data.fields);
        } catch (error) {
            console.warn('Could not load field definitions:', error);
        }
    },

    /**
     * Renders primary radiation telemetry metrics on cards.
     * 
     * @param {object} data - NASA RadLab sample response
     */
    renderRadiationCards(data) {
        if (!data || !data.records || data.records.length === 0) return;

        const latest = data.records[0];

        // 1. Absorbed Dose Rate (µGy/hr)
        const absorbedEl = document.getElementById('rad-absorbed-dose');
        const absorbedUnitEl = document.getElementById('rad-absorbed-unit');
        const absorbedStatusEl = document.getElementById('rad-absorbed-status');
        const absorbedBarEl = document.getElementById('rad-absorbed-bar');

        if (absorbedEl) {
            const doseRate = latest.absorbed_dose_rate;
            absorbedEl.textContent = doseRate !== null ? formatNumber(doseRate, 4) : '—';
            if (absorbedUnitEl) absorbedUnitEl.textContent = 'µGy/hr';

            // Aerospace Benchmark Classification (NASA-STD-3001 & ISS Flight Rules)
            let statusText = 'NOMINAL BACKGROUND';
            let statusClass = 'badge-success';
            let barPct = Math.min(100, ((doseRate || 0) / 50.0) * 100);

            if (doseRate >= 500.0) {
                statusText = 'CRITICAL: SOLAR PARTICLE STORM';
                statusClass = 'badge-danger';
                barPct = 100;
            } else if (doseRate >= 100.0) {
                statusText = 'HIGH: SHELTER BENCHMARK';
                statusClass = 'badge-danger';
            } else if (doseRate >= 20.0) {
                statusText = 'ELEVATED: SAA ANOMALY PASS';
                statusClass = 'badge-warning';
            }

            if (absorbedStatusEl) {
                absorbedStatusEl.textContent = statusText;
                absorbedStatusEl.className = `badge ${statusClass}`;
            }
            if (absorbedBarEl) {
                absorbedBarEl.style.width = `${barPct}%`;
                absorbedBarEl.className = `progress-fill ${statusClass.replace('badge-', 'fill-')}`;
            }
        }

        // 2. Dose-Equivalent Rate (µSv/hr)
        const eqEl = document.getElementById('rad-equivalent-dose');
        const eqUnitEl = document.getElementById('rad-equivalent-unit');
        const eqStatusEl = document.getElementById('rad-equivalent-status');

        if (eqEl) {
            const eqRate = latest.dose_equivalent_rate;
            if (eqRate !== null && !isNaN(eqRate)) {
                eqEl.textContent = formatNumber(eqRate, 4);
                if (eqUnitEl) eqUnitEl.textContent = 'µSv/hr';
                if (eqStatusEl) {
                    eqStatusEl.textContent = eqRate >= 25.0 ? 'ELEVATED BIOLOGICAL RISK' : 'NOMINAL';
                    eqStatusEl.className = `badge ${eqRate >= 25.0 ? 'badge-warning' : 'badge-success'}`;
                }
            } else {
                eqEl.textContent = 'N/A';
                if (eqUnitEl) eqUnitEl.textContent = 'µSv/hr';
                if (eqStatusEl) {
                    eqStatusEl.textContent = 'DETECTOR NOT CONFIGURED FOR SV';
                    eqStatusEl.className = 'badge badge-secondary';
                    eqStatusEl.title = 'Sensor REM-Lid measures physical absorbed dose (Grays). MicroSieverts are recorded by tissue-equivalent dosimeters like DosTel.';
                }
            }
        }

        // 3. Particle Flux (particles / (cm² · sr · s))
        const fluxEl = document.getElementById('rad-particle-flux');
        const fluxUnitEl = document.getElementById('rad-flux-unit');
        if (fluxEl) {
            fluxEl.textContent = latest.flux !== null ? formatNumber(latest.flux, 4) : '—';
            if (fluxUnitEl) fluxUnitEl.textContent = 'particles/(cm²·sr·s)';
        }

        // 4. Spacecraft Location & Context
        const altitudeEl = document.getElementById('rad-altitude');
        const coordsEl = document.getElementById('rad-coords');
        const detectorEl = document.getElementById('rad-detector-id');
        const moduleEl = document.getElementById('rad-spacecraft-module');
        const timeEl = document.getElementById('rad-timestamp');
        const sourceStatusEl = document.getElementById('rad-source-status');

        if (altitudeEl) altitudeEl.textContent = latest.altitude ? `${formatNumber(latest.altitude, 1)} km` : '416.8 km';
        if (coordsEl) {
            const lat = formatNumber(latest.latitude, 2);
            const lon = formatNumber(latest.longitude, 2);
            coordsEl.textContent = `Lat: ${lat}°, Lon: ${lon}°`;
        }
        if (detectorEl) detectorEl.textContent = latest.instrument_id || 'REM-Lid';
        if (moduleEl) moduleEl.textContent = `${latest.module || 'Columbus'} (${latest.spacecraft || 'ISS'})`;
        if (timeEl) timeEl.textContent = formatDateTime(latest.timestamp);
        
        if (sourceStatusEl) {
            const isLive = data.source_status === 'live_api_fetch';
            sourceStatusEl.innerHTML = `
                <span class="source-tag ${isLive ? 'live' : 'archive'}">
                    ${isLive ? '🌐 LIVE NASA RADLAB API' : '💾 NASA RADLAB LOCAL ARCHIVE'}
                </span>
                <span class="historical-warning">HISTORICAL SPACE TELEMETRY (NOT LIVE SENSORS)</span>
            `;
        }
    },

    /**
     * Renders statistical metrics and cumulative exposure from analysis.
     * 
     * @param {object} data - Full radiation analysis JSON
     */
    renderAnalysisStats(data) {
        if (!data || !data.radiation_analysis) return;

        const absorbedAnalysis = data.radiation_analysis.absorbed_dose_analysis;
        const stats = absorbedAnalysis.statistics;
        const cumulative = absorbedAnalysis.cumulative_exposure;

        // Statistics Table
        const minEl = document.getElementById('rad-stat-min');
        const maxEl = document.getElementById('rad-stat-max');
        const meanEl = document.getElementById('rad-stat-mean');
        const medianEl = document.getElementById('rad-stat-median');
        const stdEl = document.getElementById('rad-stat-std');
        const sampleSizeEl = document.getElementById('rad-stat-samples');

        if (stats) {
            if (minEl) minEl.textContent = `${formatNumber(stats.min, 4)} µGy/hr`;
            if (maxEl) maxEl.textContent = `${formatNumber(stats.max, 4)} µGy/hr`;
            if (meanEl) meanEl.textContent = `${formatNumber(stats.mean, 4)} µGy/hr`;
            if (medianEl) medianEl.textContent = `${formatNumber(stats.median, 4)} µGy/hr`;
            if (stdEl) stdEl.textContent = stats.standard_deviation !== null ? `±${formatNumber(stats.standard_deviation, 4)}` : '—';
            if (sampleSizeEl) sampleSizeEl.textContent = `${stats.sample_size} valid telemetry packets`;
        }

        // Cumulative Exposure
        const cumValEl = document.getElementById('rad-cumulative-value');
        const cumDurationEl = document.getElementById('rad-cumulative-duration');
        const cumSegmentsEl = document.getElementById('rad-cumulative-segments');
        const cumMethodEl = document.getElementById('rad-cumulative-method');

        if (cumValEl && cumulative) {
            if (cumulative.supported) {
                cumValEl.textContent = `${formatNumber(cumulative.cumulative_dose, 5)} µGy`;
                if (cumDurationEl) cumDurationEl.textContent = `Valid Integration Window: ${cumulative.valid_duration_hours} hours (${cumulative.valid_duration_seconds}s)`;
                if (cumSegmentsEl) cumSegmentsEl.textContent = `Continuous Segments: ${cumulative.continuous_segments_count} (Gaps excluded: ${cumulative.gaps_excluded_count})`;
                if (cumMethodEl) cumMethodEl.textContent = cumulative.calculation_method;
            } else {
                cumValEl.textContent = 'Unavailable';
                if (cumDurationEl) cumDurationEl.textContent = cumulative.reason || 'Interval bounds exceeded gap threshold.';
            }
        }
    },

    /**
     * Renders paginated historical radiation telemetry records in a table.
     * 
     * @param {object} data - History query response
     */
    renderRadiationHistoryTable(data) {
        const tbody = document.getElementById('radiation-history-tbody');
        const countEl = document.getElementById('rad-history-total-count');

        if (!tbody) return;
        tbody.innerHTML = '';

        if (countEl && data.total_records !== undefined) {
            countEl.textContent = `${data.total_records} Records Stored in SQLite`;
        }

        const records = data.records || [];
        if (records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center empty-state">No historical telemetry records found.</td></tr>`;
            return;
        }

        records.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><code>${formatDateTime(r.timestamp)}</code></td>
                <td><span class="detector-pill">${escapeHtml(r.instrument_id)}</span></td>
                <td><strong>${formatNumber(r.absorbed_dose_rate, 4)}</strong> <span class="unit-text">${escapeHtml(r.absorbed_dose_unit || 'µGy/hr')}</span></td>
                <td>${r.dose_equivalent_rate !== null ? `${formatNumber(r.dose_equivalent_rate, 4)} µSv/hr` : '<span class="text-muted">—</span>'}</td>
                <td>${r.flux !== null ? formatNumber(r.flux, 4) : '<span class="text-muted">—</span>'}</td>
                <td>${r.altitude ? `${formatNumber(r.altitude, 1)} km` : '—'}</td>
                <td><span class="location-tag">${escapeHtml(r.module || 'ISS')} (${escapeHtml(r.spacecraft || 'LEO')})</span></td>
            `;
            tbody.appendChild(tr);
        });
    },

    /**
     * Populates educational plain-language guide cards for astronauts.
     * 
     * @param {object} fields - Field definitions dictionary
     */
    renderEducationalGuides(fields) {
        const guideContainer = document.getElementById('radiation-guide-container');
        if (!guideContainer || !fields) return;

        guideContainer.innerHTML = `
            <div class="guide-card">
                <div class="guide-header">
                    <span class="guide-icon">⚛️</span>
                    <h4>What is Absorbed Dose Rate (µGy/hr)?</h4>
                </div>
                <p>
                    <strong>µGy/hr (microGrays per hour)</strong> measures the physical energy deposited by space radiation 
                    (cosmic rays and solar energetic protons) into matter or human tissue. 1 Gray = 1 Joule per kilogram of mass.
                    Nominal ISS background is <strong>10–25 µGy/hr</strong>.
                </p>
            </div>

            <div class="guide-card">
                <div class="guide-header">
                    <span class="guide-icon">🧬</span>
                    <h4>What is Dose-Equivalent Rate (µSv/hr)?</h4>
                </div>
                <p>
                    <strong>µSv/hr (microSieverts per hour)</strong> takes the physical dose and multiplies it by a radiation biological 
                    quality factor ($Q$) to reflect the true cellular damage caused to living bone marrow and organs. 
                    <strong>Rule:</strong> Grays and Sieverts are separate physical domains and must never be added together.
                </p>
            </div>

            <div class="guide-card">
                <div class="guide-header">
                    <span class="guide-icon">🌍</span>
                    <h4>What is the South Atlantic Anomaly (SAA)?</h4>
                </div>
                <p>
                    The SAA is an orbital region where Earth's inner Van Allen radiation belt dips down to space station altitude (~420 km).
                    During a 10–15 minute pass, radiation dose rates jump from <strong>2 µGy/hr to over 30 µGy/hr</strong> before subsiding.
                </p>
            </div>
        `;
    },

    /**
     * Renders error state if a radiation API fails.
     */
    renderRadiationError(section, msg) {
        const errorEl = document.getElementById(`radiation-${section}-error`);
        if (errorEl) {
            errorEl.style.display = 'block';
            errorEl.textContent = `Error connecting to backend (${msg}). Ensure Python server is running on port 8000.`;
        }
    }
};
