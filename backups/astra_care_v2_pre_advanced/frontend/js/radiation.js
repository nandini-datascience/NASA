/**
 * radiation.js - ASTRA CARE Dynamic Radiation Telemetry & ML Anomaly Detection Module
 * 
 * Capabilities (ASTRA CARE 2.0):
 * 1. Dynamic Radiation Telemetry Engine:
 *    - Simulated streaming provider with LEO physics & SAA transit modeling
 *    - Standby interfaces for physical hardware sensors & live spacecraft links
 *    - Stream deck controls: Start/Pause, Single Tick, Cadence selector, Anomaly Injection
 * 2. Real-Time Machine Learning Anomaly Detection:
 *    - Real-time scoring using scikit-learn Isolation Forest (<2ms inference)
 *    - Detector-specific baseline normalization (DosTel1, DosTel2, Lidal, REM-Lid)
 *    - Live anomaly gauge, Z-score calculation, and plain-language explainability breakdown
 * 3. Real-Time Dynamic Rolling Trend Chart:
 *    - Interactive neon Chart.js time-series tracking recent dynamic telemetry points
 *    - Distinct visual markers for nominal vs. ML-detected anomalies
 * 4. Historical NASA RadLab Scientific Research Archive:
 *    - Retains full backward compatibility with static NASA RadLab dataset
 *    - Trapezoidal numerical integration for cumulative absorbed dose
 *    - Statistical dispersion analysis and astronaut educational guides
 */

const RadiationModule = {
    // Historical NASA RadLab state
    currentSample: null,
    currentAnalysis: null,
    historyRecords: [],
    fieldsMetadata: null,

    // Dynamic 2.0 Streaming & ML state
    latestStreamReading: null,
    streamStatus: {
        is_running: true,
        interval_seconds: 2.0,
        mode: 'simulated_streaming'
    },
    streamPollTimer: null,
    dynamicChart: null,
    dynamicChartData: {
        labels: [],
        values: [],
        anomalies: []
    },

    /**
     * Initializes all radiation monitoring components (Dynamic Stream + Historical Archive).
     */
    async init() {
        console.log('Initializing ASTRA CARE Radiation Module (Dynamic Telemetry + ML + RadLab)...');

        // 1. Setup Stream Controls Event Listeners
        this.setupStreamControls();

        // 2. Initialize Dynamic Chart
        this.initDynamicChart();

        // 3. Load Dynamic & Historical Data in Parallel
        await Promise.allSettled([
            this.loadTelemetryStatus(),
            this.loadLatestStreamReading(),
            this.loadStreamHistory(),
            this.loadRadiationSample(),
            this.loadRadiationAnalysis(),
            this.loadRadiationHistory(),
            this.loadFieldDefinitions()
        ]);

        // 4. Start Polling Loop for Dynamic Streaming Telemetry
        this.startStreamPolling();
    },

    /**
     * Sets up event listeners for streaming controls (Play/Pause, Step, Interval, Anomaly).
     */
    setupStreamControls() {
        const toggleBtn = document.getElementById('btn-toggle-stream');
        const stepBtn = document.getElementById('btn-step-stream');
        const intervalSelect = document.getElementById('select-stream-interval');
        const anomalyBtn = document.getElementById('btn-inject-anomaly');

        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => this.toggleStream());
        }

        if (stepBtn) {
            stepBtn.addEventListener('click', () => this.stepStream());
        }

        if (intervalSelect) {
            intervalSelect.addEventListener('change', (e) => {
                const sec = parseFloat(e.target.value);
                if (!isNaN(sec) && sec > 0) {
                    this.updateInterval(sec);
                }
            });
        }

        if (anomalyBtn) {
            anomalyBtn.addEventListener('click', () => this.injectAnomaly());
        }
    },

    /**
     * Starts continuous polling for the latest dynamic stream reading.
     */
    startStreamPolling() {
        if (this.streamPollTimer) {
            clearInterval(this.streamPollTimer);
        }

        const pollMs = Math.max(1000, (this.streamStatus.interval_seconds || 2.0) * 1000);
        this.streamPollTimer = setInterval(() => {
            if (this.streamStatus.is_running) {
                this.loadLatestStreamReading();
            }
        }, pollMs);
    },

    /**
     * Fetches the latest dynamic stream reading and updates UI & ML cards.
     */
    async loadLatestStreamReading() {
        try {
            const data = await apiFetch(CONFIG.ENDPOINTS.RADIATION_STREAM_LATEST);
            if (data && data.reading) {
                this.latestStreamReading = data.reading;
                this.renderDynamicRadiationCard(data.reading);
                this.renderMLAnomalyCard(data.reading);
                this.renderThresholdCard(data.reading);
                this.updateDynamicChart(data.reading);
                this.prependDynamicTableRow(data.reading);
            }
            if (data && data.stream_status) {
                this.streamStatus = data.stream_status;
                this.updateStreamStatusUI();
            }
            return data;
        } catch (error) {
            console.warn('Failed to load latest dynamic stream reading:', error);
        }
    },

    /**
     * Fetches recent dynamic stream history from SQLite and renders into table.
     */
    async loadStreamHistory(limit = 15) {
        try {
            const data = await apiFetch(`${CONFIG.ENDPOINTS.RADIATION_STREAM_HISTORY}?limit=${limit}`);
            if (data && data.records) {
                this.renderDynamicHistoryTable(data.records);
            }
        } catch (error) {
            console.warn('Failed to load dynamic stream history:', error);
        }
    },

    /**
     * Fetches current telemetry provider status.
     */
    async loadTelemetryStatus() {
        try {
            const data = await apiFetch(CONFIG.ENDPOINTS.RADIATION_TELEMETRY_STATUS);
            if (data) {
                const provBadge = document.getElementById('telemetry-provider-badge');
                const sensorBadge = document.getElementById('telemetry-sensor-badge');
                const linkBadge = document.getElementById('telemetry-link-badge');

                if (provBadge && data.provider_type) {
                    provBadge.textContent = data.provider_type.replace(/_/g, ' ').toUpperCase();
                }
                if (sensorBadge && data.sensor_hardware) {
                    sensorBadge.textContent = `HARDWARE: ${data.sensor_hardware.status.toUpperCase()}`;
                    sensorBadge.className = `badge-tag ${data.sensor_hardware.connected ? 'normal' : 'info'}`;
                }
                if (linkBadge && data.spacecraft_link) {
                    linkBadge.textContent = `SPACECRAFT: ${data.spacecraft_link.status.toUpperCase()}`;
                    linkBadge.className = `badge-tag ${data.spacecraft_link.connected ? 'normal' : 'purple'}`;
                }
            }
        } catch (error) {
            console.warn('Failed to load telemetry status:', error);
        }
    },

    /**
     * Toggles the dynamic streaming engine between running and paused.
     */
    async toggleStream() {
        const nextAction = this.streamStatus.is_running ? 'stop' : 'start';
        try {
            const res = await apiFetch(CONFIG.ENDPOINTS.RADIATION_STREAM_CONTROL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: nextAction })
            });

            if (res && res.status) {
                this.streamStatus = res.status;
                this.updateStreamStatusUI();
                showToast(
                    this.streamStatus.is_running ? '▶ Dynamic radiation stream resumed.' : '⏸ Dynamic radiation stream paused.',
                    'info'
                );
            }
        } catch (error) {
            console.error('Error toggling stream:', error);
            showToast(`Stream control failed: ${error.message}`, 'error');
        }
    },

    /**
     * Advances the streaming engine by a single reading step.
     */
    async stepStream() {
        try {
            const res = await apiFetch(CONFIG.ENDPOINTS.RADIATION_STREAM_CONTROL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'step' })
            });

            if (res && res.reading) {
                this.latestStreamReading = res.reading;
                this.renderDynamicRadiationCard(res.reading);
                this.renderMLAnomalyCard(res.reading);
                this.renderThresholdCard(res.reading);
                this.updateDynamicChart(res.reading);
                this.prependDynamicTableRow(res.reading);
                showToast('⚡ Stepped 1 dynamic radiation reading.', 'normal');
            }
        } catch (error) {
            console.error('Error stepping stream:', error);
            showToast(`Step failed: ${error.message}`, 'error');
        }
    },

    /**
     * Updates streaming cadence interval.
     */
    async updateInterval(seconds) {
        try {
            const res = await apiFetch(CONFIG.ENDPOINTS.RADIATION_STREAM_CONTROL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'set_interval', interval_seconds: seconds })
            });

            if (res && res.status) {
                this.streamStatus = res.status;
                this.updateStreamStatusUI();
                this.startStreamPolling();
                showToast(`Stream cadence adjusted to ${seconds}s.`, 'info');
            }
        } catch (error) {
            console.error('Error updating interval:', error);
            showToast(`Cadence update failed: ${error.message}`, 'error');
        }
    },

    /**
     * Injects a high-energy synthetic radiation spike for ML detection testing.
     */
    async injectAnomaly() {
        try {
            const res = await apiFetch(CONFIG.ENDPOINTS.RADIATION_STREAM_CONTROL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'inject_anomaly', anomaly_factor: 15.0 })
            });

            if (res) {
                showToast('⚠️ Test Anomaly Injected! Next reading will evaluate spike through ML model.', 'warning');
                setTimeout(() => this.loadLatestStreamReading(), 300);
            }
        } catch (error) {
            console.error('Error injecting anomaly:', error);
            showToast(`Anomaly injection failed: ${error.message}`, 'error');
        }
    },

    /**
     * Updates stream deck control UI elements (button labels, status badges).
     */
    updateStreamStatusUI() {
        const toggleBtn = document.getElementById('btn-toggle-stream');
        const summaryEl = document.getElementById('telemetry-status-summary');
        const intervalSelect = document.getElementById('select-stream-interval');

        if (toggleBtn) {
            if (this.streamStatus.is_running) {
                toggleBtn.textContent = '⏸ Pause Stream';
                toggleBtn.classList.remove('btn-stream-play');
            } else {
                toggleBtn.textContent = '▶ Start Stream';
                toggleBtn.classList.add('btn-stream-play');
            }
        }

        if (summaryEl) {
            const stateText = this.streamStatus.is_running ? 'Active' : 'Paused';
            const cadenceText = `${this.streamStatus.interval_seconds || 2.0}s cadence`;
            summaryEl.textContent = `${stateText} • ${cadenceText}`;
            summaryEl.style.color = this.streamStatus.is_running ? 'var(--accent-cyan)' : 'var(--status-warning)';
        }

        if (intervalSelect && this.streamStatus.interval_seconds) {
            intervalSelect.value = String(Math.round(this.streamStatus.interval_seconds));
        }
    },

    /**
     * Renders primary dynamic radiation reading metrics on Card 1.
     */
    renderDynamicRadiationCard(r) {
        if (!r) return;

        const doseEl = document.getElementById('stream-absorbed-dose');
        const unitEl = document.getElementById('stream-absorbed-unit');
        const eqEl = document.getElementById('stream-dose-equivalent');
        const detEl = document.getElementById('stream-detector-id');
        const baseEl = document.getElementById('stream-detector-baseline');
        const regionEl = document.getElementById('stream-orbital-region');
        const sourceEl = document.getElementById('stream-source-label');

        if (doseEl) {
            doseEl.textContent = formatNumber(r.absorbed_dose_rate, 2);
        }
        if (unitEl) {
            unitEl.textContent = r.absorbed_dose_rate_unit || 'µGy/hr';
        }
        if (eqEl) {
            eqEl.textContent = r.dose_equivalent_rate !== undefined && r.dose_equivalent_rate !== null ?
                formatNumber(r.dose_equivalent_rate, 2) : '—';
        }
        if (detEl) {
            detEl.textContent = r.detector_id || 'DosTel1';
        }
        if (baseEl) {
            const meanVal = r.detector_baseline_mean || 14.2;
            baseEl.textContent = `μ: ${meanVal.toFixed(1)} µGy/hr`;
        }
        if (regionEl) {
            if (r.is_in_saa) {
                regionEl.textContent = 'South Atlantic Anomaly (SAA)';
                regionEl.className = 'badge-tag critical';
            } else {
                regionEl.textContent = r.orbit_region || 'LEO Nominal';
                regionEl.className = 'badge-tag info';
            }
        }
        if (sourceEl) {
            sourceEl.textContent = r.data_source || 'simulated_streaming';
        }
    },

    /**
     * Renders ML Isolation Forest Anomaly Detection outputs on Card 2.
     */
    renderMLAnomalyCard(r) {
        if (!r) return;

        const scoreEl = document.getElementById('stream-ml-score');
        const badgeEl = document.getElementById('stream-ml-status-badge');
        const gaugeEl = document.getElementById('stream-ml-gauge');
        const explainEl = document.getElementById('stream-ml-explanation');
        const zscoreEl = document.getElementById('stream-detector-zscore');

        // Isolation forest score is normalized (0 = normal, 1 = high anomaly confidence)
        const score = typeof r.anomaly_score === 'number' ? r.anomaly_score : 0.0;
        const isAnomaly = Boolean(r.is_anomaly);

        if (scoreEl) {
            scoreEl.textContent = score.toFixed(4);
        }

        if (badgeEl) {
            if (isAnomaly) {
                badgeEl.textContent = 'ANOMALY DETECTED';
                badgeEl.className = 'badge-tag critical pulse-critical';
            } else {
                badgeEl.textContent = 'NOMINAL';
                badgeEl.className = 'badge-tag normal';
            }
        }

        if (gaugeEl) {
            const pct = Math.min(100, Math.max(8, score * 100));
            gaugeEl.style.width = `${pct}%`;
            if (isAnomaly) {
                gaugeEl.className = 'ml-gauge-fill critical';
            } else if (score > 0.4) {
                gaugeEl.className = 'ml-gauge-fill warning';
            } else {
                gaugeEl.className = 'ml-gauge-fill';
            }
        }

        if (explainEl) {
            explainEl.textContent = r.anomaly_explanation ||
                (isAnomaly ? 'Multi-feature deviation isolated by decision trees.' : 'Telemetry is consistent with historical baseline geometry.');
        }

        if (zscoreEl) {
            if (typeof r.detector_z_score === 'number') {
                const sign = r.detector_z_score >= 0 ? '+' : '';
                zscoreEl.textContent = `${sign}${r.detector_z_score.toFixed(2)}σ`;
                zscoreEl.style.color = Math.abs(r.detector_z_score) > 3.0 ? 'var(--status-critical)' : 'var(--accent-cyan)';
            } else {
                zscoreEl.textContent = '—';
            }
        }
    },

    /**
     * Renders Aerospace Threshold checks on Card 3.
     */
    renderThresholdCard(r) {
        if (!r) return;

        const badgeEl = document.getElementById('stream-threshold-badge');
        const saaEl = document.getElementById('stream-saa-status');

        if (badgeEl) {
            const level = r.threshold_level || 'NORMAL';
            if (level === 'CRITICAL') {
                badgeEl.textContent = 'CRITICAL: SHELTER PROTOCOL';
                badgeEl.className = 'badge-tag critical';
            } else if (level === 'WARNING') {
                badgeEl.textContent = 'WARNING: ELEVATED FLUX';
                badgeEl.className = 'badge-tag warning';
            } else {
                badgeEl.textContent = 'WITHIN LIMITS';
                badgeEl.className = 'badge-tag normal';
            }
        }

        if (saaEl) {
            if (r.is_in_saa) {
                saaEl.textContent = 'SAA Transit (High Influx)';
                saaEl.style.color = 'var(--status-warning)';
            } else {
                saaEl.textContent = 'Normal Shielding';
                saaEl.style.color = 'var(--accent-cyan)';
            }
        }
    },

    /**
     * Initializes the real-time dynamic radiation trend chart (Chart.js).
     */
    initDynamicChart() {
        const canvas = document.getElementById('chart-dynamic-radiation');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        if (this.dynamicChart) {
            this.dynamicChart.destroy();
        }

        this.dynamicChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: this.dynamicChartData.labels,
                datasets: [{
                    label: 'Dynamic Absorbed Dose Rate (µGy/hr)',
                    data: this.dynamicChartData.values,
                    borderColor: '#00f2fe',
                    backgroundColor: 'rgba(0, 242, 254, 0.1)',
                    borderWidth: 2,
                    tension: 0.3,
                    fill: true,
                    pointBackgroundColor: (context) => {
                        const idx = context.dataIndex;
                        return this.dynamicChartData.anomalies[idx] ? '#ff4b72' : '#00f2fe';
                    },
                    pointBorderColor: '#ffffff',
                    pointRadius: (context) => {
                        const idx = context.dataIndex;
                        return this.dynamicChartData.anomalies[idx] ? 6 : 3;
                    },
                    pointHoverRadius: 7
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    x: {
                        grid: { color: 'rgba(255, 255, 255, 0.08)' },
                        ticks: { color: 'rgba(255, 255, 255, 0.7)', maxRotation: 0 }
                    },
                    y: {
                        grid: { color: 'rgba(255, 255, 255, 0.08)' },
                        ticks: { color: 'rgba(255, 255, 255, 0.7)' },
                        title: { display: true, text: 'µGy/hr', color: 'rgba(255, 255, 255, 0.7)' },
                        beginAtZero: true
                    }
                },
                plugins: {
                    legend: {
                        labels: { color: 'rgba(255, 255, 255, 0.8)' }
                    },
                    tooltip: {
                        callbacks: {
                            afterLabel: (ctx) => {
                                const idx = ctx.dataIndex;
                                return this.dynamicChartData.anomalies[idx] ? '⚠️ ML Isolation Forest Anomaly' : 'Nominal Reading';
                            }
                        }
                    }
                }
            }
        });
    },

    /**
     * Appends a new point to the real-time dynamic trend chart.
     */
    updateDynamicChart(r) {
        if (!this.dynamicChart || !r) return;

        const timeLabel = (r.timestamp || '').split('T')[1]?.split('.')[0] || new Date().toLocaleTimeString();
        const doseVal = typeof r.absorbed_dose_rate === 'number' ? r.absorbed_dose_rate : 0.0;
        const isAnomaly = Boolean(r.is_anomaly);

        this.dynamicChartData.labels.push(timeLabel);
        this.dynamicChartData.values.push(doseVal);
        this.dynamicChartData.anomalies.push(isAnomaly);

        // Maintain sliding window of 25 latest readings
        if (this.dynamicChartData.labels.length > 25) {
            this.dynamicChartData.labels.shift();
            this.dynamicChartData.values.shift();
            this.dynamicChartData.anomalies.shift();
        }

        this.dynamicChart.update();
    },

    /**
     * Prepends a single dynamic reading to the stream history table.
     */
    prependDynamicTableRow(r) {
        const tbody = document.getElementById('dynamic-radiation-table-body');
        if (!tbody || !r) return;

        // If placeholder row exists, remove it
        const placeholder = tbody.querySelector('.loading-inline');
        if (placeholder) {
            tbody.innerHTML = '';
        }

        const tr = document.createElement('tr');
        if (r.is_anomaly) {
            tr.className = 'row-anomaly-alert';
        }

        const isAnomaly = Boolean(r.is_anomaly);
        const anomalyScoreStr = typeof r.anomaly_score === 'number' ? r.anomaly_score.toFixed(3) : '—';
        const zscoreStr = typeof r.detector_z_score === 'number' ? `${r.detector_z_score >= 0 ? '+' : ''}${r.detector_z_score.toFixed(1)}σ` : '—';

        tr.innerHTML = `
            <td class="mono-cell">${formatDateTime(r.timestamp)}</td>
            <td class="font-mono"><strong>${escapeHtml(r.detector_id || 'DosTel1')}</strong></td>
            <td class="mono-cell" style="color: ${r.absorbed_dose_rate >= 100 ? 'var(--status-critical)' : '#fff'}; font-weight: 600;">
                ${formatNumber(r.absorbed_dose_rate, 2)}
            </td>
            <td class="mono-cell">${r.dose_equivalent_rate ? formatNumber(r.dose_equivalent_rate, 2) : '—'}</td>
            <td>
                <span class="badge-tag ${r.is_in_saa ? 'warning' : 'info'}" style="font-size: 0.68rem;">
                    ${r.is_in_saa ? 'SAA' : 'LEO'}
                </span>
            </td>
            <td class="mono-cell" style="font-size: 0.78rem;">${anomalyScoreStr} (${zscoreStr})</td>
            <td>
                <span class="badge-tag ${isAnomaly ? 'critical pulse-critical' : 'normal'}" style="font-size: 0.68rem;">
                    ${isAnomaly ? 'ANOMALY' : 'NOMINAL'}
                </span>
            </td>
            <td>
                <span class="badge-tag ${r.threshold_level === 'CRITICAL' ? 'critical' : (r.threshold_level === 'WARNING' ? 'warning' : 'normal')}" style="font-size: 0.68rem;">
                    ${escapeHtml(r.threshold_level || 'NORMAL')}
                </span>
            </td>
        `;

        tbody.insertBefore(tr, tbody.firstChild);

        // Keep table to at most 15 rows
        while (tbody.children.length > 15) {
            tbody.removeChild(tbody.lastChild);
        }
    },

    /**
     * Renders multiple records from stream history query.
     */
    renderDynamicHistoryTable(records) {
        const tbody = document.getElementById('dynamic-radiation-table-body');
        if (!tbody) return;

        if (!records || records.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
                        No dynamic telemetry records logged yet. Dynamic stream engine is initializing...
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = '';
        records.forEach(r => this.prependDynamicTableRow(r));
    },

    // =========================================================================
    // HISTORICAL NASA RADLAB RESEARCH DATA METHODS (PRESERVED)
    // =========================================================================

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
            if (eqRate !== null && eqRate !== undefined) {
                eqEl.textContent = formatNumber(eqRate, 4);
                if (eqUnitEl) eqUnitEl.textContent = 'µSv/hr';
                if (eqStatusEl) {
                    eqStatusEl.textContent = 'CALCULATED (Q=1.5)';
                    eqStatusEl.className = 'badge badge-info';
                }
            } else {
                eqEl.textContent = 'N/A';
                if (eqStatusEl) {
                    eqStatusEl.textContent = 'UNAVAILABLE';
                    eqStatusEl.className = 'badge badge-warning';
                }
            }
        }

        // 3. Spacecraft Location & Detector Metadata
        const altEl = document.getElementById('rad-altitude');
        const coordsEl = document.getElementById('rad-coords');
        const moduleEl = document.getElementById('rad-spacecraft-module');
        const detectorEl = document.getElementById('rad-detector-id');

        if (altEl) altEl.textContent = latest.altitude_km !== null ? formatNumber(latest.altitude_km, 1) : '408.0';
        if (coordsEl) {
            const lat = latest.latitude !== null ? `${latest.latitude.toFixed(2)}°` : '0.00°';
            const lon = latest.longitude !== null ? `${latest.longitude.toFixed(2)}°` : '0.00°';
            coordsEl.textContent = `${lat}, ${lon}`;
        }
        if (moduleEl) moduleEl.textContent = latest.module || 'Columbus';
        if (detectorEl) detectorEl.textContent = latest.detector_id || 'DosTel1';
    },

    /**
     * Renders radiation statistical analysis and cumulative trapezoidal dose.
     */
    renderAnalysisStats(analysis) {
        if (!analysis) return;

        // Cumulative Exposure
        const cumValEl = document.getElementById('rad-cumulative-value');
        const cumDurationEl = document.getElementById('rad-cumulative-duration');
        const cumSegsEl = document.getElementById('rad-cumulative-segments');
        const cumMethodEl = document.getElementById('rad-cumulative-method');

        if (analysis.cumulative_absorbed_dose_microgray) {
            const cum = analysis.cumulative_absorbed_dose_microgray;
            if (cumValEl) cumValEl.textContent = formatNumber(cum.cumulative_value_ugy, 4);
            if (cumDurationEl) cumDurationEl.textContent = `${cum.total_valid_duration_hours.toFixed(2)} hrs`;
            if (cumSegsEl) cumSegsEl.textContent = `${cum.continuous_segments_count} continuous blocks`;
            if (cumMethodEl) cumMethodEl.textContent = cum.integration_method || 'Trapezoidal (valid intervals)';
        }

        // Statistical Distribution
        if (analysis.absorbed_dose_rate_ugy_hr) {
            const stats = analysis.absorbed_dose_rate_ugy_hr;
            const minEl = document.getElementById('rad-stat-min');
            const maxEl = document.getElementById('rad-stat-max');
            const meanEl = document.getElementById('rad-stat-mean');
            const medianEl = document.getElementById('rad-stat-median');
            const stdEl = document.getElementById('rad-stat-std');
            const samplesEl = document.getElementById('rad-stat-samples');

            if (minEl) minEl.textContent = formatNumber(stats.min, 4);
            if (maxEl) maxEl.textContent = formatNumber(stats.max, 4);
            if (meanEl) meanEl.textContent = formatNumber(stats.mean, 4);
            if (medianEl) medianEl.textContent = formatNumber(stats.median, 4);
            if (stdEl) stdEl.textContent = formatNumber(stats.std, 4);
            if (samplesEl) samplesEl.textContent = `${stats.valid_readings_count} records`;
        }
    },

    /**
     * Renders historical radiation records in the data table.
     */
    renderRadiationHistoryTable(data) {
        const tbody = document.getElementById('radiation-history-tbody');
        const totalCountEl = document.getElementById('rad-history-total-count');

        if (totalCountEl && data) {
            totalCountEl.textContent = data.total_count || (data.records ? data.records.length : 0);
        }

        if (!tbody) return;

        if (!data || !data.records || data.records.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                        No radiation sensor records found in local SQLite database.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = data.records.map(record => {
            const doseRate = record.absorbed_dose_rate !== null ? formatNumber(record.absorbed_dose_rate, 4) : '—';
            const doseEq = record.dose_equivalent_rate !== null ? formatNumber(record.dose_equivalent_rate, 4) : '—';
            const flux = record.particle_flux !== null ? formatNumber(record.particle_flux, 2) : '—';
            const alt = record.altitude_km !== null ? formatNumber(record.altitude_km, 1) : '—';

            return `
                <tr>
                    <td class="font-mono">${formatDateTime(record.timestamp)}</td>
                    <td class="font-mono"><strong>${escapeHtml(record.detector_id || '—')}</strong></td>
                    <td>${escapeHtml(record.module || '—')}</td>
                    <td class="font-mono" style="color: var(--accent-cyan);">${doseRate}</td>
                    <td class="font-mono">${doseEq}</td>
                    <td class="font-mono">${flux}</td>
                    <td>${alt}</td>
                </tr>
            `;
        }).join('');
    },

    /**
     * Renders educational guide cards for astronauts and controllers.
     */
    renderEducationalGuides(fields) {
        const guideContainer = document.getElementById('radiation-guide-container');
        if (!guideContainer) return;

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

            <div class="guide-card">
                <div class="guide-header">
                    <span class="guide-icon">🤖</span>
                    <h4>What is Machine Learning Anomaly Detection?</h4>
                </div>
                <p>
                    ASTRA CARE 2.0 uses a scikit-learn <strong>Isolation Forest</strong> algorithm trained on verified NASA RadLab telemetry.
                    The model isolates multidimensional anomalies (absorbed dose rate, particle flux, detector geometry baseline Z-scores, and SAA coordinates)
                    in under 2 milliseconds without relying on rigid static thresholds alone.
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
