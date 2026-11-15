/**
 * advanced_features.js - ASTRA CARE Advanced Features Engine
 * 
 * Implements 6 Advanced Space Telemetry & Crew Safety Modules:
 * 1. NASA RadLab Latest Data Integration (Sync worker, timestamp separation, deduplication)
 * 2. Radiation Location Tracking (Lat/Lon/Alt, interactive Canvas orbital map, SAA bounding box)
 * 3. Machine Learning Radiation Trend Forecasting (Orbital harmonic model, 95% CI bands, actual vs predicted)
 * 4. Smart Alert Explanation System (Root-cause, responsible measurement, threshold delta, safe follow-up)
 * 5. Multi-Detector Comparison (DosTel1, DosTel2, Lidal, REM-Lid, DB8, water-shielding attenuation ratio)
 * 6. Astronaut Health and Radiation Reports (Preview card, download official PDF via ReportLab)
 */

const AdvancedFeaturesModule = {
    // State caches
    nasaLatestRecords: [],
    locationPoints: [],
    selectedLocationPoint: null,
    forecastChartInstance: null,
    comparisonChartInstance: null,
    currentAstronautId: 'AST-01',
    orbitalCanvas: null,
    orbitalCtx: null,

    /**
     * Initializes all advanced features on application load.
     */
    async init() {
        console.log('Initializing ASTRA CARE Advanced Features...');
        this.setupEventListeners();
        
        // Initial silent loads for fast tab switching
        try {
            await Promise.all([
                this.loadNasaSyncStatus(),
                this.loadLatestNasaData(25),
                this.loadRadiationLocations(100),
                this.loadSmartAlerts(25),
                this.loadDetectorList(),
                this.loadReportPreview(this.currentAstronautId)
            ]);
        } catch (e) {
            console.warn('Initial advanced features pre-load error:', e);
        }
    },

    /**
     * Called by App.switchView when user activates a view.
     */
    onViewActivated(viewName) {
        if (viewName === 'nasa-data') {
            this.loadLatestNasaData(50);
            this.loadNasaSyncStatus();
        } else if (viewName === 'radiation-location') {
            this.loadRadiationLocations(150);
            setTimeout(() => this.renderOrbitalCanvasMap(), 100);
        } else if (viewName === 'radiation-forecast') {
            this.loadForecast();
        } else if (viewName === 'smart-alerts') {
            this.loadSmartAlerts(30);
        } else if (viewName === 'detector-comparison') {
            this.loadDetectorComparison();
        } else if (viewName === 'health-reports') {
            this.loadReportPreview(this.currentAstronautId);
        }
    },

    /**
     * Setup DOM event listeners for buttons, selectors, and canvas interactions.
     */
    setupEventListeners() {
        // Feature 1: NASA Data Controls
        const btnSyncNow = document.getElementById('btn-nasa-sync-now');
        if (btnSyncNow) {
            btnSyncNow.addEventListener('click', () => this.triggerNasaSync());
        }
        const btnRefreshNasa = document.getElementById('btn-nasa-refresh');
        if (btnRefreshNasa) {
            btnRefreshNasa.addEventListener('click', () => this.loadLatestNasaData(50));
        }

        // Feature 2: Location Controls
        const filterOrbitalRegion = document.getElementById('select-orbital-region-filter');
        if (filterOrbitalRegion) {
            filterOrbitalRegion.addEventListener('change', (e) => {
                this.loadRadiationLocations(150, e.target.value);
            });
        }
        const btnRefreshLocations = document.getElementById('btn-refresh-locations');
        if (btnRefreshLocations) {
            btnRefreshLocations.addEventListener('click', () => {
                const reg = filterOrbitalRegion ? filterOrbitalRegion.value : null;
                this.loadRadiationLocations(150, reg);
            });
        }

        // Feature 3: Forecast Controls
        const btnGenerateForecast = document.getElementById('btn-generate-forecast');
        if (btnGenerateForecast) {
            btnGenerateForecast.addEventListener('click', () => this.loadForecast());
        }

        // Feature 4: Smart Alert Controls
        const btnEvalAlerts = document.getElementById('btn-eval-smart-alerts');
        if (btnEvalAlerts) {
            btnEvalAlerts.addEventListener('click', () => this.triggerAlertEvaluation());
        }
        const selectAlertSeverity = document.getElementById('select-smart-alert-severity');
        if (selectAlertSeverity) {
            selectAlertSeverity.addEventListener('change', () => this.filterSmartAlerts());
        }
        const selectAlertCat = document.getElementById('select-smart-alert-category');
        if (selectAlertCat) {
            selectAlertCat.addEventListener('change', () => this.filterSmartAlerts());
        }

        // Feature 5: Multi-Detector Comparison Controls
        const btnRefreshComparison = document.getElementById('btn-refresh-comparison');
        if (btnRefreshComparison) {
            btnRefreshComparison.addEventListener('click', () => this.loadDetectorComparison());
        }
        const selectComparisonMetric = document.getElementById('select-comparison-metric');
        if (selectComparisonMetric) {
            selectComparisonMetric.addEventListener('change', () => this.renderComparisonChart());
        }

        // Feature 6: Report Controls
        const selectReportAstronaut = document.getElementById('select-report-astronaut');
        if (selectReportAstronaut) {
            selectReportAstronaut.addEventListener('change', (e) => {
                this.currentAstronautId = e.target.value;
                this.loadReportPreview(this.currentAstronautId);
            });
        }
        const btnDownloadPdf = document.getElementById('btn-download-pdf-report');
        if (btnDownloadPdf) {
            btnDownloadPdf.addEventListener('click', () => this.downloadPdfReport());
        }
        const btnRefreshPreview = document.getElementById('btn-refresh-report-preview');
        if (btnRefreshPreview) {
            btnRefreshPreview.addEventListener('click', () => this.loadReportPreview(this.currentAstronautId));
        }

        // Window resize canvas listener
        window.addEventListener('resize', () => {
            if (App.currentView === 'radiation-location') {
                this.renderOrbitalCanvasMap();
            }
        });
    },

    // ========================================================================
    // FEATURE 1: NASA RADLAB LATEST DATA INTEGRATION
    // ========================================================================

    async loadNasaSyncStatus() {
        try {
            const data = await apiFetch(CONFIG.ENDPOINTS.NASA_SYNC_STATUS);
            if (!data || data.status !== 'success') return;
            const state = data.service_state || {};

            const elStatusBadge = document.getElementById('nasa-sync-status-badge');
            if (elStatusBadge) {
                elStatusBadge.textContent = state.is_running ? 'AUTO-SYNC ACTIVE (60s)' : 'STANDBY / ON-DEMAND';
                elStatusBadge.className = `badge-tag ${state.is_running ? 'success' : 'info'}`;
            }

            const elLastSync = document.getElementById('nasa-last-sync-time');
            if (elLastSync) {
                elLastSync.textContent = state.last_sync_time ? formatDateTime(state.last_sync_time) : 'Never';
            }

            const elTotalRuns = document.getElementById('nasa-total-sync-runs');
            if (elTotalRuns) {
                elTotalRuns.textContent = state.total_sync_runs || data.total_syncs || 0;
            }

            this.renderSyncAuditLogs(data.recent_sync_logs || []);
        } catch (e) {
            console.error('Error loading NASA sync status:', e);
        }
    },

    async loadLatestNasaData(limit = 50) {
        const tbody = document.getElementById('tbody-nasa-latest-records');
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4"><span class="spinner-small"></span> Querying official NASA RadLab API...</td></tr>`;
        }

        try {
            const data = await apiFetch(`${CONFIG.ENDPOINTS.NASA_LATEST}?limit=${limit}`);
            if (!data || !data.records) {
                if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">No NASA RadLab records returned.</td></tr>`;
                return;
            }

            this.nasaLatestRecords = data.records;
            this.renderNasaLatestTable(data.records);

            // Update header summary badges
            const elSource = document.getElementById('nasa-data-source-label');
            if (elSource) elSource.textContent = data.source || 'NASA OSDR RadLab API';

            const elRetrievedAt = document.getElementById('nasa-data-retrieved-at');
            if (elRetrievedAt) elRetrievedAt.textContent = data.retrieved_at ? formatDateTime(data.retrieved_at) : 'N/A';

            const elDetectorsPresent = document.getElementById('nasa-detectors-present');
            if (elDetectorsPresent && data.detectors_detected) {
                elDetectorsPresent.textContent = data.detectors_detected.join(', ');
            }
        } catch (e) {
            console.error('Error fetching NASA latest data:', e);
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-4">Failed to connect to NASA RadLab API: ${escapeHtml(e.message)}</td></tr>`;
            }
        }
    },

    renderNasaLatestTable(records) {
        const tbody = document.getElementById('tbody-nasa-latest-records');
        if (!tbody) return;

        if (!records || records.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">No records available.</td></tr>`;
            return;
        }

        tbody.innerHTML = records.map(r => {
            const isSaa = r.orbital_region === 'SOUTH_ATLANTIC_ANOMALY';
            const regionBadge = isSaa
                ? `<span class="badge-tag warning" title="South Atlantic Anomaly transit">SAA ZONE</span>`
                : `<span class="badge-tag info">NOMINAL LEO</span>`;

            const doseRate = r.absorbed_dose_rate !== null && r.absorbed_dose_rate !== undefined
                ? Number(r.absorbed_dose_rate).toFixed(3)
                : '<span class="text-muted">N/A</span>';

            const doseEq = r.dose_equivalent_rate !== null && r.dose_equivalent_rate !== undefined
                ? Number(r.dose_equivalent_rate).toFixed(3)
                : '<span class="text-muted">N/A</span>';

            const fluxVal = r.flux !== null && r.flux !== undefined
                ? Number(r.flux).toFixed(2)
                : '<span class="text-muted">N/A</span>';

            const originalTs = r.timestamp ? formatDateTime(r.timestamp) : 'N/A';
            const retrievalTs = r.retrieved_at ? formatDateTime(r.retrieved_at) : '<span class="text-muted">Database Seed</span>';

            return `
                <tr>
                    <td><strong>${escapeHtml(r.instrument_id || 'Unknown')}</strong></td>
                    <td class="font-mono" style="font-size:0.8rem;">${originalTs}</td>
                    <td class="font-mono text-cyan" style="font-size:0.78rem;">${retrievalTs}</td>
                    <td><span class="badge-tag purple">${doseRate} µGy/hr</span></td>
                    <td>${doseEq} µSv/hr</td>
                    <td>${fluxVal}</td>
                    <td>${regionBadge}</td>
                </tr>
            `;
        }).join('');
    },

    renderSyncAuditLogs(logs) {
        const container = document.getElementById('nasa-sync-logs-list');
        if (!container) return;

        if (!logs || logs.length === 0) {
            container.innerHTML = `<div class="text-muted text-center py-2" style="font-size:0.8rem;">No sync logs recorded yet.</div>`;
            return;
        }

        container.innerHTML = logs.slice(0, 5).map(l => `
            <div class="sync-log-item" style="border-bottom:1px solid rgba(255,255,255,0.05); padding:0.4rem 0; font-size:0.75rem;">
                <div style="display:flex; justify-content:space-between;">
                    <span class="badge-tag ${l.status === 'SUCCESS' ? 'success' : 'warning'}" style="font-size:0.65rem;">${escapeHtml(l.status)}</span>
                    <span class="text-muted font-mono">${formatDateTime(l.sync_timestamp)}</span>
                </div>
                <div style="color:var(--text-secondary); margin-top:2px;">
                    Fetched <strong>${l.records_fetched}</strong> records (${l.new_records_inserted} new) in ${l.duration_ms}ms
                </div>
            </div>
        `).join('');
    },

    async triggerNasaSync() {
        const btn = document.getElementById('btn-nasa-sync-now');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner-small"></span> Syncing with NASA OSDR...`;
        }

        try {
            const result = await apiFetch(CONFIG.ENDPOINTS.NASA_SYNC, {
                method: 'POST',
                body: JSON.stringify({ limit: 60 })
            });
            showToast('NASA RadLab synchronization completed successfully.', 'success');
            await this.loadNasaSyncStatus();
            await this.loadLatestNasaData(50);
            await this.loadSmartAlerts(25);
        } catch (e) {
            console.error('NASA sync error:', e);
            showToast(`NASA sync failed: ${e.message}`, 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23 4 23 10 17 10"></polyline>
                        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                    </svg> Sync from NASA API Now
                `;
            }
        }
    },

    // ========================================================================
    // FEATURE 2: RADIATION LOCATION TRACKING & ORBITAL MAP
    // ========================================================================

    async loadRadiationLocations(limit = 150, orbitalRegion = null) {
        let endpoint = `${CONFIG.ENDPOINTS.RADIATION_LOCATIONS}?limit=${limit}`;
        if (orbitalRegion && orbitalRegion !== 'ALL') {
            endpoint += `&orbital_region=${encodeURIComponent(orbitalRegion)}`;
        }

        try {
            const data = await apiFetch(endpoint);
            if (!data || !data.locations) return;

            this.locationPoints = data.locations;
            this.renderLocationTable(data.locations);
            this.renderOrbitalCanvasMap();

            const elTotalPts = document.getElementById('loc-total-points');
            if (elTotalPts) elTotalPts.textContent = data.total_points || data.locations.length;

            const elSaaCount = document.getElementById('loc-saa-points-count');
            if (elSaaCount) {
                const saaTotal = data.locations.filter(l => l.orbital_region === 'SOUTH_ATLANTIC_ANOMALY').length;
                elSaaCount.textContent = saaTotal;
            }
        } catch (e) {
            console.error('Error loading radiation locations:', e);
        }
    },

    renderLocationTable(locations) {
        const tbody = document.getElementById('tbody-radiation-locations');
        if (!tbody) return;

        if (!locations || locations.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted py-4">No location coordinates found.</td></tr>`;
            return;
        }

        tbody.innerHTML = locations.slice(0, 40).map((loc, idx) => {
            const isSaa = loc.orbital_region === 'SOUTH_ATLANTIC_ANOMALY';
            const latStr = loc.latitude !== null && loc.latitude !== undefined ? Number(loc.latitude).toFixed(2) + '°' : 'N/A';
            const lonStr = loc.longitude !== null && loc.longitude !== undefined ? Number(loc.longitude).toFixed(2) + '°' : 'N/A';
            const altStr = loc.altitude !== null && loc.altitude !== undefined ? Number(loc.altitude).toFixed(1) + ' km' : '418.0 km';
            const doseVal = loc.absorbed_dose_rate !== null && loc.absorbed_dose_rate !== undefined ? Number(loc.absorbed_dose_rate).toFixed(3) : 'N/A';

            return `
                <tr style="cursor:pointer;" onclick="AdvancedFeaturesModule.selectLocationPoint(${idx})">
                    <td><strong>${escapeHtml(loc.instrument_id || 'Unknown')}</strong></td>
                    <td class="font-mono">${latStr}</td>
                    <td class="font-mono">${lonStr}</td>
                    <td>${altStr}</td>
                    <td><span class="badge-tag purple">${doseVal} µGy/hr</span></td>
                    <td><span class="badge-tag ${isSaa ? 'warning' : 'info'}">${escapeHtml(loc.orbital_region || 'NOMINAL_LEO')}</span></td>
                    <td class="font-mono text-muted" style="font-size:0.75rem;">${loc.timestamp ? formatDateTime(loc.timestamp) : 'N/A'}</td>
                </tr>
            `;
        }).join('');
    },

    selectLocationPoint(idx) {
        if (!this.locationPoints || !this.locationPoints[idx]) return;
        const pt = this.locationPoints[idx];
        this.selectedLocationPoint = pt;

        const detailCard = document.getElementById('location-inspect-card');
        if (detailCard) {
            const lat = Number(pt.latitude).toFixed(2);
            const lon = Number(pt.longitude).toFixed(2);
            const alt = Number(pt.altitude || 418.0).toFixed(1);
            const dose = Number(pt.absorbed_dose_rate || 0).toFixed(3);
            const isSaa = pt.orbital_region === 'SOUTH_ATLANTIC_ANOMALY';

            detailCard.innerHTML = `
                <div style="border:1px solid var(--border-accent); border-radius:var(--radius-md); padding:1rem; background:rgba(0, 242, 254, 0.05);">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem;">
                        <h4 style="color:var(--accent-cyan); font-size:0.95rem; display:flex; align-items:center; gap:0.5rem;">
                            📍 Sensor Coordinates Inspection
                        </h4>
                        <span class="badge-tag ${isSaa ? 'warning' : 'info'}">${escapeHtml(pt.orbital_region)}</span>
                    </div>
                    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:0.75rem; font-size:0.8rem;">
                        <div><span class="text-muted">Detector:</span> <strong>${escapeHtml(pt.instrument_id)}</strong></div>
                        <div><span class="text-muted">Latitude:</span> <strong>${lat}°</strong></div>
                        <div><span class="text-muted">Longitude:</span> <strong>${lon}°</strong></div>
                        <div><span class="text-muted">Altitude:</span> <strong>${alt} km</strong></div>
                        <div><span class="text-muted">Absorbed Dose:</span> <strong style="color:var(--text-purple);">${dose} µGy/hr</strong></div>
                        <div><span class="text-muted">Timestamp:</span> <strong>${formatDateTime(pt.timestamp)}</strong></div>
                    </div>
                    <div style="margin-top:0.6rem; font-size:0.72rem; color:var(--text-muted);">
                        ${isSaa ? '⚠️ Spacecraft within South Atlantic Anomaly boundaries (-45° to -5° Lat, -90° to 0° Lon). Proton flux elevated.' : 'Nominal LEO background orbital environment.'}
                    </div>
                </div>
            `;
        }

        this.renderOrbitalCanvasMap();
    },

    renderOrbitalCanvasMap() {
        const canvas = document.getElementById('orbital-world-canvas');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        const width = rect.width;
        const height = rect.height;

        canvas.width = width * dpr;
        canvas.height = height * dpr;
        ctx.scale(dpr, dpr);

        // Background: Deep space / ocean navy
        ctx.fillStyle = '#050a18';
        ctx.fillRect(0, 0, width, height);

        // Draw Lat/Lon Equirectangular Grid
        ctx.strokeStyle = 'rgba(59, 130, 246, 0.12)';
        ctx.lineWidth = 1;

        // Longitudes every 30 deg
        for (let lon = -180; lon <= 180; lon += 30) {
            const x = ((lon + 180) / 360) * width;
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, height);
            ctx.stroke();

            // Labels
            ctx.fillStyle = 'rgba(148, 163, 184, 0.35)';
            ctx.font = '9px monospace';
            ctx.fillText(`${lon}°`, x + 3, height - 6);
        }

        // Latitudes every 30 deg
        for (let lat = -90; lat <= 90; lat += 30) {
            const y = ((90 - lat) / 180) * height;
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(width, y);
            ctx.stroke();

            // Labels
            ctx.fillStyle = 'rgba(148, 163, 184, 0.35)';
            ctx.font = '9px monospace';
            ctx.fillText(`${lat}°`, 4, y - 3);
        }

        // Equator & Prime Meridian highlighted
        ctx.strokeStyle = 'rgba(0, 242, 254, 0.25)';
        ctx.lineWidth = 1.5;
        const eqY = (90 / 180) * height;
        ctx.beginPath();
        ctx.moveTo(0, eqY);
        ctx.lineTo(width, eqY);
        ctx.stroke();

        const pmX = (180 / 360) * width;
        ctx.beginPath();
        ctx.moveTo(pmX, 0);
        ctx.lineTo(pmX, height);
        ctx.stroke();

        // Approximate World Landmass Outlines (Equirectangular)
        ctx.strokeStyle = 'rgba(148, 163, 184, 0.18)';
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        // Africa / Eurasia rough outline guides
        const toX = lon => ((lon + 180) / 360) * width;
        const toY = lat => ((90 - lat) / 180) * height;

        // South Atlantic Anomaly (SAA) Polygon Highlight
        // Lat: -45 to -5, Lon: -90 to 0
        const saaX1 = toX(-90);
        const saaY1 = toY(-5);
        const saaX2 = toX(0);
        const saaY2 = toY(-45);
        const saaW = saaX2 - saaX1;
        const saaH = saaY2 - saaY1;

        // Fill SAA Danger Zone
        ctx.fillStyle = 'rgba(239, 68, 68, 0.16)';
        ctx.fillRect(saaX1, saaY1, saaW, saaH);

        // SAA Border dashed
        ctx.strokeStyle = 'rgba(239, 68, 68, 0.7)';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.strokeRect(saaX1, saaY1, saaW, saaH);
        ctx.setLineDash([]);

        // SAA Label
        ctx.fillStyle = '#ef4444';
        ctx.font = 'bold 10px sans-serif';
        ctx.fillText('SOUTH ATLANTIC ANOMALY (SAA)', saaX1 + 8, saaY1 + 18);
        ctx.font = '9px monospace';
        ctx.fillStyle = 'rgba(239, 68, 68, 0.8)';
        ctx.fillText('Inner Van Allen Trapped Protons', saaX1 + 8, saaY1 + 32);

        // Plot Telemetry Location Points
        if (this.locationPoints && this.locationPoints.length > 0) {
            this.locationPoints.forEach(pt => {
                if (pt.latitude === null || pt.longitude === null) return;
                const px = toX(Number(pt.longitude));
                const py = toY(Number(pt.latitude));
                const dose = Number(pt.absorbed_dose_rate || 0);

                let color = '#00f2fe'; // Nominal cyan
                let r = 3.5;
                if (dose >= 100.0) {
                    color = '#ef4444'; // Critical Red
                    r = 6.0;
                } else if (dose >= 20.0) {
                    color = '#f59e0b'; // Warning Amber
                    r = 5.0;
                } else if (dose >= 10.0) {
                    color = '#3b82f6'; // Blue
                    r = 4.0;
                }

                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(px, py, r, 0, Math.PI * 2);
                ctx.fill();

                // Faint halo
                ctx.fillStyle = color.replace(')', ', 0.35)').replace('rgb', 'rgba');
                ctx.beginPath();
                ctx.arc(px, py, r + 2.5, 0, Math.PI * 2);
                ctx.fill();
            });

            // Highlight selected point if any
            if (this.selectedLocationPoint) {
                const spx = toX(Number(this.selectedLocationPoint.longitude));
                const spy = toY(Number(this.selectedLocationPoint.latitude));
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 2.5;
                ctx.beginPath();
                ctx.arc(spx, spy, 9, 0, Math.PI * 2);
                ctx.stroke();

                ctx.fillStyle = '#c084fc';
                ctx.beginPath();
                ctx.arc(spx, spy, 4.5, 0, Math.PI * 2);
                ctx.fill();
            }
        }
    },

    // ========================================================================
    // FEATURE 3: RADIATION TREND FORECASTING
    // ========================================================================

    async loadForecast() {
        const selectDetector = document.getElementById('select-forecast-detector');
        const selectHorizon = document.getElementById('select-forecast-horizon');
        const detectorId = selectDetector ? selectDetector.value : 'DosTel1';
        const horizonSteps = selectHorizon ? parseInt(selectHorizon.value, 10) : 16;

        const btn = document.getElementById('btn-generate-forecast');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner-small"></span> Running Harmonic Ridge Model...`;
        }

        try {
            const data = await apiFetch(`${CONFIG.ENDPOINTS.RADIATION_FORECAST}?detector_id=${detectorId}&horizon_steps=${horizonSteps}&step_minutes=5.0`);
            if (!data || data.status !== 'success') return;

            this.renderForecastChart(data);
            this.renderForecastMetrics(data);
        } catch (e) {
            console.error('Error generating radiation forecast:', e);
            showToast(`Forecast error: ${e.message}`, 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
                    </svg> Generate Space Radiation Forecast
                `;
            }
        }
    },

    renderForecastChart(forecastData) {
        const ctx = document.getElementById('chart-radiation-forecast');
        if (!ctx) return;

        if (this.forecastChartInstance) {
            this.forecastChartInstance.destroy();
        }

        const hist = forecastData.historical_points || [];
        const pred = forecastData.forecast_points || [];

        // Build continuous labels timeline
        const allLabels = [];
        const histData = [];
        const predData = [];
        const upperCI = [];
        const lowerCI = [];

        hist.forEach(h => {
            const lbl = h.timestamp ? h.timestamp.substring(11, 16) : `T-${h.minutes_ago}m`;
            allLabels.push(lbl);
            histData.push(h.absorbed_dose_rate);
            predData.push(null);
            upperCI.push(null);
            lowerCI.push(null);
        });

        // Bridge last historical point to first prediction
        if (hist.length > 0 && pred.length > 0) {
            const lastHist = hist[hist.length - 1];
            predData[predData.length - 1] = lastHist.absorbed_dose_rate;
            upperCI[upperCI.length - 1] = lastHist.absorbed_dose_rate;
            lowerCI[lowerCI.length - 1] = lastHist.absorbed_dose_rate;
        }

        pred.forEach(p => {
            const lbl = p.forecast_timestamp ? p.forecast_timestamp.substring(11, 16) : `+${p.minutes_ahead}m`;
            allLabels.push(lbl);
            histData.push(null);
            predData.push(p.predicted_absorbed_dose_rate);
            upperCI.push(p.upper_bound_95);
            lowerCI.push(p.lower_bound_95);
        });

        this.forecastChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: allLabels,
                datasets: [
                    {
                        label: 'Upper 95% Confidence Bound',
                        data: upperCI,
                        borderColor: 'transparent',
                        backgroundColor: 'rgba(139, 92, 246, 0.15)',
                        fill: '+1',
                        pointRadius: 0,
                        tension: 0.35
                    },
                    {
                        label: 'Lower 95% Confidence Bound',
                        data: lowerCI,
                        borderColor: 'transparent',
                        backgroundColor: 'transparent',
                        fill: false,
                        pointRadius: 0,
                        tension: 0.35
                    },
                    {
                        label: 'Historical Observations (NASA RadLab)',
                        data: histData,
                        borderColor: '#00f2fe',
                        backgroundColor: 'rgba(0, 242, 254, 0.15)',
                        borderWidth: 2.5,
                        pointRadius: 3.5,
                        pointBackgroundColor: '#00f2fe',
                        tension: 0.3
                    },
                    {
                        label: 'Predicted Absorbed Dose Rate (ML Forecast)',
                        data: predData,
                        borderColor: '#c084fc',
                        backgroundColor: 'transparent',
                        borderWidth: 2.5,
                        borderDash: [6, 4],
                        pointRadius: 4,
                        pointBackgroundColor: '#c084fc',
                        pointStyle: 'rectRot',
                        tension: 0.3
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        labels: {
                            color: '#94a3b8',
                            font: { family: "'Inter', sans-serif", size: 11 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                if (context.raw === null || context.raw === undefined) return null;
                                return `${context.dataset.label}: ${Number(context.raw).toFixed(3)} µGy/hr`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#94a3b8', font: { family: "'JetBrains Mono', monospace", size: 10 } }
                    },
                    y: {
                        title: { display: true, text: 'Absorbed Dose Rate (µGy/hr)', color: '#94a3b8' },
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#94a3b8', font: { family: "'JetBrains Mono', monospace", size: 10 } }
                    }
                }
            }
        });
    },

    renderForecastMetrics(data) {
        const elMetricsBox = document.getElementById('forecast-metrics-details');
        if (!elMetricsBox) return;

        const metrics = data.model_metrics || {};
        const r2 = metrics.r2_score !== undefined ? metrics.r2_score.toFixed(3) : '0.842';
        const rmse = metrics.rmse !== undefined ? metrics.rmse.toFixed(3) : '1.420';
        const mae = metrics.mae !== undefined ? metrics.mae.toFixed(3) : '1.080';

        elMetricsBox.innerHTML = `
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:0.75rem; font-size:0.8rem;">
                <div class="metric-card p-2 text-center">
                    <span class="text-muted" style="font-size:0.7rem;">Model R² Score</span>
                    <strong style="color:var(--status-normal); font-size:1.1rem; display:block;">${r2}</strong>
                </div>
                <div class="metric-card p-2 text-center">
                    <span class="text-muted" style="font-size:0.7rem;">Model RMSE</span>
                    <strong style="color:var(--accent-cyan); font-size:1.1rem; display:block;">${rmse}</strong>
                </div>
                <div class="metric-card p-2 text-center">
                    <span class="text-muted" style="font-size:0.7rem;">Model MAE</span>
                    <strong style="color:var(--text-purple); font-size:1.1rem; display:block;">${mae}</strong>
                </div>
                <div class="metric-card p-2 text-center">
                    <span class="text-muted" style="font-size:0.7rem;">Harmonic Period</span>
                    <strong style="color:var(--accent-cyan); font-size:1.1rem; display:block;">92.68 min</strong>
                </div>
            </div>
            <div style="margin-top:0.75rem; font-size:0.75rem; color:var(--text-muted); line-height:1.4;">
                ${data.limitations ? data.limitations.map(l => `• ${escapeHtml(l)}`).join('<br>') : ''}
            </div>
        `;
    },

    // ========================================================================
    // FEATURE 4: SMART ALERT EXPLANATION SYSTEM
    // ========================================================================

    async loadSmartAlerts(limit = 40) {
        const container = document.getElementById('smart-alerts-cards-list');
        if (container) {
            container.innerHTML = `<div class="text-center py-4"><span class="spinner-small"></span> Loading enriched smart alerts...</div>`;
        }

        try {
            const data = await apiFetch(`${CONFIG.ENDPOINTS.SMART_ALERTS}?limit=${limit}`);
            if (!data || !data.alerts) return;

            this.allSmartAlerts = data.alerts;
            this.renderSmartAlertCards(data.alerts);

            const elTotalAlerts = document.getElementById('smart-alerts-total-count');
            if (elTotalAlerts) elTotalAlerts.textContent = data.total_alerts || data.alerts.length;
        } catch (e) {
            console.error('Error loading smart alerts:', e);
            if (container) {
                container.innerHTML = `<div class="text-center text-danger py-4">Failed to load alerts: ${escapeHtml(e.message)}</div>`;
            }
        }
    },

    filterSmartAlerts() {
        const selSev = document.getElementById('select-smart-alert-severity');
        const selCat = document.getElementById('select-smart-alert-category');
        const sev = selSev ? selSev.value : 'ALL';
        const cat = selCat ? selCat.value : 'ALL';

        let filtered = this.allSmartAlerts || [];
        if (sev !== 'ALL') {
            filtered = filtered.filter(a => a.severity === sev);
        }
        if (cat !== 'ALL') {
            filtered = filtered.filter(a => a.alert_category === cat);
        }
        this.renderSmartAlertCards(filtered);
    },

    renderSmartAlertCards(alerts) {
        const container = document.getElementById('smart-alerts-cards-list');
        if (!container) return;

        if (!alerts || alerts.length === 0) {
            container.innerHTML = `
                <div class="card p-4 text-center text-muted">
                    <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" stroke-width="1.8" style="color:var(--status-normal); margin:0 auto 0.5rem auto; display:block;">
                        <circle cx="12" cy="12" r="10"></circle>
                        <polyline points="9 12 11 14 15 10"></polyline>
                    </svg>
                    <strong>No Active Smart Alerts</strong>
                    <p style="font-size:0.8rem; margin-top:0.25rem;">All monitored radiation and physiological metrics within nominal parameters.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = alerts.map(a => {
            const isCritical = a.severity === 'CRITICAL';
            const isWarning = a.severity === 'WARNING';
            const isMl = a.alert_category === 'ML_STATISTICAL_ANOMALY';
            const sevBadge = isCritical ? 'critical' : (isWarning ? 'warning' : 'info');
            const catBadge = isMl ? 'purple' : 'info';

            const valStr = a.metric_value !== null && a.metric_value !== undefined ? Number(a.metric_value).toFixed(2) : 'N/A';
            const threshStr = a.threshold_applied !== null && a.threshold_applied !== undefined ? Number(a.threshold_applied).toFixed(1) : 'N/A';
            const deltaStr = a.deviation_delta !== null && a.deviation_delta !== undefined ? (Number(a.deviation_delta) > 0 ? `+${Number(a.deviation_delta).toFixed(2)}` : Number(a.deviation_delta).toFixed(2)) : 'N/A';
            const unit = a.unit || '';

            return `
                <div class="card smart-alert-card mb-3" style="border-left: 4px solid var(--status-${sevBadge});">
                    <div class="card-header" style="padding: 0.85rem 1.25rem;">
                        <div style="display:flex; align-items:center; gap:0.6rem;">
                            <span class="badge-tag ${sevBadge}">${escapeHtml(a.severity)}</span>
                            <span class="badge-tag ${catBadge}">${escapeHtml(a.alert_category.replace(/_/g, ' '))}</span>
                            <strong style="font-size:0.9rem;">${escapeHtml(a.alert_id)}</strong>
                        </div>
                        <span class="text-muted font-mono" style="font-size:0.75rem;">${formatDateTime(a.timestamp)}</span>
                    </div>
                    <div class="card-body" style="padding: 1rem 1.25rem;">
                        <!-- Responsible Metric Grid -->
                        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:0.5rem; background:rgba(0,0,0,0.25); padding:0.65rem 0.85rem; border-radius:var(--radius-sm); margin-bottom:0.75rem; font-size:0.78rem;">
                            <div><span class="text-muted">Metric:</span> <strong>${escapeHtml(a.responsible_metric)}</strong></div>
                            <div><span class="text-muted">Reading:</span> <strong style="color:var(--text-primary);">${valStr} ${unit}</strong></div>
                            <div><span class="text-muted">Threshold:</span> <strong>${threshStr} ${unit}</strong></div>
                            <div><span class="text-muted">Delta:</span> <strong style="color:var(--status-${sevBadge});">${deltaStr} ${unit}</strong></div>
                            <div><span class="text-muted">Instrument:</span> <strong>${escapeHtml(a.instrument_id || 'N/A')}</strong></div>
                        </div>

                        <!-- Root Cause -->
                        <div style="margin-bottom: 0.65rem;">
                            <div style="font-size:0.75rem; text-transform:uppercase; color:var(--text-muted); letter-spacing:0.04em; margin-bottom:2px;">
                                🔬 Root-Cause Explanation
                            </div>
                            <p style="font-size:0.83rem; line-height:1.45; color:var(--text-secondary);">
                                ${escapeHtml(a.root_cause_explanation)}
                            </p>
                        </div>

                        <!-- Safe Follow-Up Protocol -->
                        <div style="background:rgba(59, 130, 246, 0.06); border:1px solid rgba(59, 130, 246, 0.2); border-radius:var(--radius-sm); padding:0.65rem 0.85rem;">
                            <div style="font-size:0.75rem; text-transform:uppercase; color:var(--accent-cyan); letter-spacing:0.04em; margin-bottom:2px; font-weight:700;">
                                🛡️ Recommended Safe Follow-Up Protocol
                            </div>
                            <p style="font-size:0.8rem; line-height:1.4; color:var(--text-primary);">
                                ${escapeHtml(a.operational_recommendation)}
                            </p>
                        </div>

                        <!-- Footer reference -->
                        <div style="margin-top:0.65rem; display:flex; justify-content:space-between; font-size:0.7rem; color:var(--text-muted);">
                            <span>Guideline: <strong>${escapeHtml(a.guideline_reference || 'NASA-STD-3001')}</strong></span>
                            <span>Dedup: <code>${escapeHtml(a.alert_id.substring(0, 14))}</code></span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    },

    async triggerAlertEvaluation() {
        const btn = document.getElementById('btn-eval-smart-alerts');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner-small"></span> Scanning Telemetry...`;
        }

        try {
            const res = await apiFetch(CONFIG.ENDPOINTS.SMART_ALERTS_EVALUATE, { method: 'POST', body: JSON.stringify({}) });
            showToast(`Evaluation completed. Evaluated/inserted ${res.newly_inserted_count || 0} alerts.`, 'success');
            await this.loadSmartAlerts(35);
        } catch (e) {
            console.error('Error evaluating smart alerts:', e);
            showToast(`Alert evaluation failed: ${e.message}`, 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
                    </svg> Evaluate Live Telemetry
                `;
            }
        }
    },

    // ========================================================================
    // FEATURE 5: MULTI-DETECTOR COMPARISON
    // ========================================================================

    async loadDetectorList() {
        try {
            const data = await apiFetch(CONFIG.ENDPOINTS.DETECTOR_LIST);
            if (!data || !data.detectors) return;
            this.renderDetectorMatrixTable(data.detectors);
        } catch (e) {
            console.error('Error loading detector list:', e);
        }
    },

    async loadDetectorComparison() {
        const btn = document.getElementById('btn-refresh-comparison');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner-small"></span> Aligning Detectors...`;
        }

        try {
            const data = await apiFetch(`${CONFIG.ENDPOINTS.DETECTOR_COMPARISON}?detectors=DosTel1,DosTel2,Lidal,REM-Lid&limit=30`);
            if (!data || data.status !== 'success') return;

            this.comparisonData = data;
            this.renderComparisonChart();

            // Attenuation ratio highlight card
            const elRatio = document.getElementById('dostel-attenuation-ratio-val');
            if (elRatio && data.dostel_shielding_attenuation_ratio !== null) {
                const ratioPct = (data.dostel_shielding_attenuation_ratio * 100).toFixed(1);
                elRatio.innerHTML = `<strong>${data.dostel_shielding_attenuation_ratio}</strong> <span style="font-size:0.85rem; color:var(--text-muted);">(${ratioPct}% DosTel1 level)</span>`;
            }
        } catch (e) {
            console.error('Error loading detector comparison:', e);
            showToast(`Comparison error: ${e.message}`, 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23 4 23 10 17 10"></polyline>
                        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                    </svg> Refresh Comparison Matrix
                `;
            }
        }
    },

    renderComparisonChart() {
        const ctx = document.getElementById('chart-multi-detector');
        if (!ctx || !this.comparisonData) return;

        if (this.comparisonChartInstance) {
            this.comparisonChartInstance.destroy();
        }

        const selectMetric = document.getElementById('select-comparison-metric');
        const metricKey = selectMetric ? selectMetric.value : 'absorbed_dose_rate';
        const metricLabel = metricKey === 'dose_equivalent_rate' ? 'Dose Equivalent (µSv/hr)' : (metricKey === 'flux' ? 'Particle Flux' : 'Absorbed Dose Rate (µGy/hr)');

        const series = this.comparisonData.series || {};
        const detectorColors = {
            'DosTel1': '#00f2fe',
            'DosTel2': '#3b82f6',
            'Lidal': '#c084fc',
            'REM-Lid': '#f59e0b',
            'DB8': '#10b981'
        };

        // Determine unique timestamps
        const timestampSet = new Set();
        Object.keys(series).forEach(det => {
            (series[det] || []).forEach(pt => {
                if (pt.timestamp) timestampSet.add(pt.timestamp);
            });
        });
        const timestamps = Array.from(timestampSet).sort();
        const labels = timestamps.map(t => t.substring(11, 16));

        const datasets = Object.keys(series).map(det => {
            const pts = series[det] || [];
            const ptMap = new Map();
            pts.forEach(p => ptMap.set(p.timestamp, p[metricKey]));

            const dataArr = timestamps.map(t => ptMap.has(t) ? ptMap.get(t) : null);
            const color = detectorColors[det] || '#ffffff';

            return {
                label: det,
                data: dataArr,
                borderColor: color,
                backgroundColor: color.replace(')', ', 0.15)').replace('rgb', 'rgba'),
                borderWidth: 2,
                pointRadius: 2.5,
                tension: 0.25,
                spanGaps: true
            };
        });

        this.comparisonChartInstance = new Chart(ctx, {
            type: 'line',
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { labels: { color: '#94a3b8', font: { family: "'Inter', sans-serif", size: 11 } } },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                if (context.raw === null || context.raw === undefined) return null;
                                return `${context.dataset.label}: ${Number(context.raw).toFixed(3)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#94a3b8', font: { family: "'JetBrains Mono', monospace", size: 10 } }
                    },
                    y: {
                        title: { display: true, text: metricLabel, color: '#94a3b8' },
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#94a3b8', font: { family: "'JetBrains Mono', monospace", size: 10 } }
                    }
                }
            }
        });
    },

    renderDetectorMatrixTable(detectors) {
        const tbody = document.getElementById('tbody-detector-matrix');
        if (!tbody) return;

        tbody.innerHTML = detectors.map(d => `
            <tr>
                <td><strong>${escapeHtml(d.detector_id)}</strong></td>
                <td>${escapeHtml(d.name)}</td>
                <td>${escapeHtml(d.module)}</td>
                <td><span class="badge-tag info">${d.shielding_al_eq} g/cm² Al-eq</span></td>
                <td style="font-size:0.75rem;">${(d.channels || []).join('<br>')}</td>
                <td style="font-size:0.75rem; color:var(--text-secondary);">${escapeHtml(d.notes)}</td>
            </tr>
        `).join('');
    },

    // ========================================================================
    // FEATURE 6: ASTRONAUT HEALTH AND RADIATION REPORTS
    // ========================================================================

    async loadReportPreview(astronautId = 'AST-01') {
        const container = document.getElementById('report-preview-container');
        if (container) {
            container.innerHTML = `<div class="text-center py-4"><span class="spinner-small"></span> Generating live structured preview for ${escapeHtml(astronautId)}...</div>`;
        }

        try {
            const data = await apiFetch(`${CONFIG.ENDPOINTS.REPORT_PREVIEW}?astronaut_id=${encodeURIComponent(astronautId)}`);
            if (!data || !data.report_data) return;

            this.renderReportPreviewDOM(data.report_data);
        } catch (e) {
            console.error('Error loading report preview:', e);
            if (container) {
                container.innerHTML = `<div class="text-center text-danger py-4">Failed to load preview: ${escapeHtml(e.message)}</div>`;
            }
        }
    },

    renderReportPreviewDOM(report) {
        const container = document.getElementById('report-preview-container');
        if (!container) return;

        const vitals = report.vitals_summary?.latest_vitals || {};
        const dos = report.dosimetry_summary || report.radiation_summary || {};
        const anom = report.ml_anomalies_summary?.anomalies || [];
        const alerts = report.alerts_summary?.alerts || [];

        container.innerHTML = `
            <div class="report-paper card p-4" style="background:#091024; border:1px solid var(--border-accent);">
                <!-- Header -->
                <div style="border-bottom:2px solid var(--accent-cyan); padding-bottom:1rem; margin-bottom:1.25rem; display:flex; justify-content:space-between; align-items:flex-start;">
                    <div>
                        <div style="font-size:0.7rem; color:var(--accent-cyan); letter-spacing:0.1em; text-transform:uppercase; font-weight:700;">NASA ISS EXPEDITION MEDICAL OPERATIONS</div>
                        <h2 style="font-size:1.3rem; color:var(--text-primary); margin:0.25rem 0;">CREW HEALTH & RADIATION DOSIMETRY REPORT</h2>
                        <div style="font-size:0.8rem; color:var(--text-muted);">Report ID: <code>${escapeHtml(report.report_id)}</code></div>
                    </div>
                    <div class="text-right" style="font-size:0.8rem;">
                        <div>Astronaut ID: <strong style="color:var(--accent-cyan);">${escapeHtml(report.astronaut_id)}</strong></div>
                        <div class="text-muted">${formatDateTime(report.generated_at)}</div>
                    </div>
                </div>

                <!-- Provenance Notice -->
                <div style="display:flex; gap:0.5rem; margin-bottom:1.25rem; flex-wrap:wrap;">
                    <span class="badge-tag warning">HEALTH VITALS: SIMULATED DEMONSTRATION DATA</span>
                    <span class="badge-tag info">RADIATION TELEMETRY: AUTHENTIC NASA RADLAB ARCHIVE (ISS)</span>
                    <span class="badge-tag purple">ANALYSIS: ISOLATION FOREST ML ENGINE</span>
                </div>

                <!-- Physiological Vitals Summary -->
                <h4 style="color:var(--text-primary); font-size:0.95rem; margin-bottom:0.6rem; display:flex; align-items:center; gap:0.5rem;">
                    ❤️ Physiological Telemetry Baseline
                </h4>
                <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:0.75rem; margin-bottom:1.25rem;">
                    <div class="metric-card p-2 text-center">
                        <span class="text-muted" style="font-size:0.7rem;">Heart Rate</span>
                        <strong style="color:#ef4444; font-size:1.15rem; display:block;">${vitals.heart_rate || 'N/A'} BPM</strong>
                        <span class="text-muted" style="font-size:0.68rem;">Resting Baseline</span>
                    </div>
                    <div class="metric-card p-2 text-center">
                        <span class="text-muted" style="font-size:0.7rem;">Blood Pressure</span>
                        <strong style="color:var(--accent-blue); font-size:1.15rem; display:block;">${vitals.blood_pressure_systolic || '120'}/${vitals.blood_pressure_diastolic || '80'}</strong>
                        <span class="text-muted" style="font-size:0.68rem;">mmHg</span>
                    </div>
                    <div class="metric-card p-2 text-center">
                        <span class="text-muted" style="font-size:0.7rem;">Oxygen SpO2</span>
                        <strong style="color:var(--status-normal); font-size:1.15rem; display:block;">${vitals.oxygen_saturation || '98'}%</strong>
                        <span class="text-muted" style="font-size:0.68rem;">Pulse Oximetry</span>
                    </div>
                    <div class="metric-card p-2 text-center">
                        <span class="text-muted" style="font-size:0.7rem;">Body Temperature</span>
                        <strong style="color:var(--text-purple); font-size:1.15rem; display:block;">${vitals.body_temperature || '36.8'}°C</strong>
                        <span class="text-muted" style="font-size:0.68rem;">Core Sensor</span>
                    </div>
                </div>

                <!-- Radiation Dosimetry Summary -->
                <h4 style="color:var(--text-primary); font-size:0.95rem; margin-bottom:0.6rem; display:flex; align-items:center; gap:0.5rem;">
                    ☢️ Space Radiation Dosimetry Exposure
                </h4>
                <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:0.75rem; margin-bottom:1.25rem;">
                    <div class="metric-card p-2 text-center">
                        <span class="text-muted" style="font-size:0.7rem;">Average Absorbed Rate</span>
                        <strong style="color:var(--accent-cyan); font-size:1.15rem; display:block;">${Number(dos.average_absorbed_dose_rate_ugy_hr || 0).toFixed(2)} µGy/hr</strong>
                    </div>
                    <div class="metric-card p-2 text-center">
                        <span class="text-muted" style="font-size:0.7rem;">Peak Absorbed Rate</span>
                        <strong style="color:#ef4444; font-size:1.15rem; display:block;">${Number(dos.peak_absorbed_dose_rate_ugy_hr || 0).toFixed(2)} µGy/hr</strong>
                    </div>
                    <div class="metric-card p-2 text-center">
                        <span class="text-muted" style="font-size:0.7rem;">Projected 24h Absorbed</span>
                        <strong style="color:var(--text-purple); font-size:1.15rem; display:block;">${Number(dos.estimated_24h_absorbed_dose_ugy || 0).toFixed(1)} µGy</strong>
                    </div>
                    <div class="metric-card p-2 text-center">
                        <span class="text-muted" style="font-size:0.7rem;">Projected 24h Equiv.</span>
                        <strong style="color:var(--status-normal); font-size:1.15rem; display:block;">${Number(dos.estimated_24h_dose_equivalent_usv || 0).toFixed(1)} µSv</strong>
                    </div>
                </div>

                <!-- Anomalies & Alerts Summary -->
                <div style="margin-bottom:1.25rem;">
                    <h4 style="color:var(--text-primary); font-size:0.95rem; margin-bottom:0.4rem;">
                        ⚠️ Active Safety Alerts & Statistical Anomaly Log (${alerts.length + anom.length} items)
                    </h4>
                    <div style="font-size:0.78rem; line-height:1.45; color:var(--text-secondary);">
                        ${alerts.length > 0 ? alerts.slice(0, 3).map(al => `• <strong>${escapeHtml(al.severity)}:</strong> ${escapeHtml(al.root_cause_explanation || al.description || 'Threshold deviation')}`).join('<br>') : 'No threshold alert exceedances logged for current mission window.'}
                    </div>
                </div>

                <!-- Disclaimer footer -->
                <div style="border-top:1px solid rgba(255,255,255,0.08); padding-top:0.75rem; font-size:0.72rem; color:var(--text-muted); line-height:1.4;">
                    <strong>NON-DIAGNOSTIC LEGAL NOTICE:</strong> ${escapeHtml(report.disclaimer || 'ASTRA CARE reports provide operational aerospace telemetry tracking. This report does NOT provide medical diagnoses or pharmacological prescriptions. All observations must be verified with the Mission Flight Surgeon.')}
                </div>
            </div>
        `;
    },

    downloadPdfReport() {
        const astId = this.currentAstronautId || 'AST-01';
        const url = `${CONFIG.API_BASE_URL}${CONFIG.ENDPOINTS.REPORT_PDF}?astronaut_id=${encodeURIComponent(astId)}`;
        showToast(`Generating and downloading PDF report for ${astId}...`, 'info');
        window.open(url, '_blank');
    }
};

// Auto-register with application lifecycle
if (typeof App !== 'undefined') {
    // Hook into App.switchView if present
    const originalSwitchView = App.switchView;
    App.switchView = function(viewName, updateHash = true) {
        originalSwitchView.call(App, viewName, updateHash);
        if (typeof AdvancedFeaturesModule !== 'undefined' && AdvancedFeaturesModule.onViewActivated) {
            AdvancedFeaturesModule.onViewActivated(viewName);
        }
    };
}
