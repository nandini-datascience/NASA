/**
 * health.js - ASTRA CARE Astronaut Health Monitoring Module
 * 
 * Interfaces with:
 * - GET /api/health/measurements
 * - POST /api/health/measurements
 * - GET /api/health/history
 * - GET /api/health/alerts
 * 
 * Features:
 * - Renders 4 primary health vital cards (Heart Rate, Blood Pressure, SpO2, Temperature)
 * - Evaluates and visualizes clinical categories (AHA, NASA-STD-3001, WHO)
 * - Validates vitals before submission (systolic > diastolic, valid physiological ranges)
 * - Submits measurements to backend POST endpoint
 * - Explicitly tags data classification (simulated_demo, historical_study, sensor_telemetry)
 * - Renders non-diagnostic disclaimers
 */

const HealthModule = {
    currentMeasurements: [],
    latestRecord: null,

    /**
     * Initializes health monitoring data and form listeners.
     */
    async init() {
        await this.loadRecentMeasurements();
        this.setupFormListeners();
    },

    /**
     * Fetches recent astronaut health measurements from backend.
     */
    async loadRecentMeasurements(astronautId = null) {
        const loadingEl = document.getElementById('health-vitals-loading');
        if (loadingEl) loadingEl.style.display = 'block';

        try {
            let endpoint = `${CONFIG.ENDPOINTS.HEALTH_MEASUREMENTS}?limit=20`;
            if (astronautId) {
                endpoint += `&astronaut_id=${encodeURIComponent(astronautId)}`;
            }
            const data = await apiFetch(endpoint);
            this.currentMeasurements = data.measurements || [];
            if (this.currentMeasurements.length > 0) {
                this.latestRecord = this.currentMeasurements[0];
                this.renderVitalCards(this.latestRecord);
                this.renderRecentVitalsTable(this.currentMeasurements);
            } else {
                this.renderEmptyVitals();
            }
            return data;
        } catch (error) {
            console.error('Error loading health measurements:', error);
            showToast(`Could not load astronaut health vitals: ${error.message}`, 'error');
        } finally {
            if (loadingEl) loadingEl.style.display = 'none';
        }
    },

    /**
     * Renders the 4 primary health cards with physiological status and units.
     * 
     * @param {object} record - Validated astronaut health record
     */
    renderVitalCards(record) {
        if (!record) return;

        // Context header
        const astronautEl = document.getElementById('vital-astronaut-id');
        const timestampEl = document.getElementById('vital-timestamp');
        const deviceEl = document.getElementById('vital-source-device');
        const classificationEl = document.getElementById('vital-classification');

        if (astronautEl) astronautEl.textContent = record.astronaut_id || 'AST-01';
        if (timestampEl) timestampEl.textContent = formatDateTime(record.timestamp);
        if (deviceEl) deviceEl.textContent = record.source_device || 'Wearable Health Patch';
        
        if (classificationEl) {
            const cls = record.data_classification || 'simulated_demo';
            let badgeClass = 'badge-secondary';
            let labelText = 'SIMULATED DEMO DATA';

            if (cls === 'historical_study') {
                badgeClass = 'badge-warning';
                labelText = 'HISTORICAL RESEARCH TELEMETRY';
            } else if (cls === 'sensor_telemetry') {
                badgeClass = 'badge-primary';
                labelText = 'LIVE SENSOR TELEMETRY';
            }

            classificationEl.className = `badge ${badgeClass}`;
            classificationEl.textContent = labelText;
        }

        // 1. Heart Rate (BPM)
        const hrVal = record.heart_rate;
        const hrEl = document.getElementById('vital-heart-rate');
        const hrBadge = document.getElementById('vital-hr-badge');
        const hrAnim = document.getElementById('vital-hr-pulse');

        if (hrEl) {
            hrEl.textContent = hrVal !== null ? `${formatNumber(hrVal, 0)}` : '—';
            let hrStatus = 'NOMINAL (60–100 BPM)';
            let hrClass = 'badge-success';

            if (hrVal !== null) {
                if (hrVal < 40) {
                    hrStatus = 'CRITICAL BRADYCARDIA (<40 BPM)';
                    hrClass = 'badge-danger';
                } else if (hrVal < 50) {
                    hrStatus = 'BRADYCARDIA ADVISORY (<50 BPM)';
                    hrClass = 'badge-warning';
                } else if (hrVal >= 130) {
                    hrStatus = 'CRITICAL TACHYCARDIA (>=130 BPM)';
                    hrClass = 'badge-danger';
                } else if (hrVal >= 100) {
                    hrStatus = 'ELEVATED TACHYCARDIA (>=100 BPM)';
                    hrClass = 'badge-warning';
                }
            }
            if (hrBadge) {
                hrBadge.textContent = hrStatus;
                hrBadge.className = `badge ${hrClass}`;
            }
            if (hrAnim) {
                const bpm = hrVal || 72;
                const durationSec = Math.max(0.4, 60 / bpm);
                hrAnim.style.animationDuration = `${durationSec}s`;
            }
        }

        // 2. Blood Pressure (mmHg)
        const sysVal = record.blood_pressure_systolic;
        const diaVal = record.blood_pressure_diastolic;
        const bpEl = document.getElementById('vital-blood-pressure');
        const bpBadge = document.getElementById('vital-bp-badge');

        if (bpEl) {
            if (sysVal !== null && diaVal !== null) {
                bpEl.textContent = `${formatNumber(sysVal, 0)}/${formatNumber(diaVal, 0)}`;
                
                // AHA / ACC 2017 & NASA-STD-3001 Guidelines
                let bpStatus = 'NORMAL (<120/<80 mmHg)';
                let bpClass = 'badge-success';

                if (sysVal >= 180 || diaVal >= 120) {
                    bpStatus = 'HYPERTENSIVE CRISIS (>=180/120)';
                    bpClass = 'badge-danger';
                } else if (sysVal < 90 || diaVal < 60) {
                    bpStatus = 'HYPOTENSION ADVISORY (<90/<60)';
                    bpClass = 'badge-warning';
                } else if (sysVal >= 140 || diaVal >= 90) {
                    bpStatus = 'STAGE 2 HYPERTENSION (>=140/90)';
                    bpClass = 'badge-warning';
                } else if (sysVal >= 130 || diaVal >= 80) {
                    bpStatus = 'STAGE 1 HYPERTENSION (130-139/80-89)';
                    bpClass = 'badge-info';
                } else if (sysVal >= 120) {
                    bpStatus = 'ELEVATED SYSTOLIC (120-129)';
                    bpClass = 'badge-info';
                }

                if (bpBadge) {
                    bpBadge.textContent = bpStatus;
                    bpBadge.className = `badge ${bpClass}`;
                }
            } else {
                bpEl.textContent = '—';
                if (bpBadge) {
                    bpBadge.textContent = 'NOT MEASURED';
                    bpBadge.className = 'badge badge-secondary';
                }
            }
        }

        // 3. Oxygen Saturation (SpO2 %)
        const spo2Val = record.oxygen_saturation;
        const spo2El = document.getElementById('vital-spo2');
        const spo2Badge = document.getElementById('vital-spo2-badge');
        const spo2Bar = document.getElementById('vital-spo2-bar');

        if (spo2El) {
            spo2El.textContent = spo2Val !== null ? `${formatNumber(spo2Val, 1)}%` : '—';
            let spo2Status = 'OPTIMAL (>=95%)';
            let spo2Class = 'badge-success';
            let barPct = Math.min(100, Math.max(0, spo2Val || 0));

            if (spo2Val !== null) {
                if (spo2Val < 90.0) {
                    spo2Status = 'CRITICAL HYPOXIA (<90%)';
                    spo2Class = 'badge-danger';
                } else if (spo2Val <= 94.0) {
                    spo2Status = 'MILD HYPOXEMIA (90–94%)';
                    spo2Class = 'badge-warning';
                }
            }

            if (spo2Badge) {
                spo2Badge.textContent = spo2Status;
                spo2Badge.className = `badge ${spo2Class}`;
            }
            if (spo2Bar) {
                spo2Bar.style.width = `${barPct}%`;
                spo2Bar.className = `progress-fill ${spo2Class.replace('badge-', 'fill-')}`;
            }
        }

        // 4. Body Temperature (°C)
        const tempVal = record.body_temperature;
        const tempEl = document.getElementById('vital-temperature');
        const tempBadge = document.getElementById('vital-temp-badge');

        if (tempEl) {
            tempEl.textContent = tempVal !== null ? `${formatNumber(tempVal, 1)}°C` : '—';
            let tempStatus = 'NORMAL (36.1–37.2°C)';
            let tempClass = 'badge-success';

            if (tempVal !== null) {
                if (tempVal >= 39.0) {
                    tempStatus = 'CRITICAL HYPERTHERMIA (>=39.0°C)';
                    tempClass = 'badge-danger';
                } else if (tempVal >= 38.0) {
                    tempStatus = 'FEVER ALERT (>=38.0°C)';
                    tempClass = 'badge-warning';
                } else if (tempVal >= 37.5) {
                    tempStatus = 'ELEVATED / SPACE FEVER (37.5–38.0°C)';
                    tempClass = 'badge-info';
                } else if (tempVal < 35.0) {
                    tempStatus = 'CRITICAL HYPOTHERMIA (<35.0°C)';
                    tempClass = 'badge-danger';
                } else if (tempVal < 35.5) {
                    tempStatus = 'MILD HYPOTHERMIA (<35.5°C)';
                    tempClass = 'badge-warning';
                }
            }

            if (tempBadge) {
                tempBadge.textContent = tempStatus;
                tempBadge.className = `badge ${tempClass}`;
            }
        }
    },

    /**
     * Renders empty state when no health measurements exist.
     */
    renderEmptyVitals() {
        const ids = ['vital-heart-rate', 'vital-blood-pressure', 'vital-spo2', 'vital-temperature'];
        ids.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.textContent = '—';
        });
    },

    /**
     * Renders recent vitals in a summary table.
     * 
     * @param {Array} measurements 
     */
    renderRecentVitalsTable(measurements) {
        const tbody = document.getElementById('health-recent-tbody');
        if (!tbody) return;

        tbody.innerHTML = '';
        if (!measurements || measurements.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center empty-state">No vitals observations recorded.</td></tr>`;
            return;
        }

        measurements.forEach(m => {
            const tr = document.createElement('tr');
            const bpStr = (m.blood_pressure_systolic !== null && m.blood_pressure_diastolic !== null)
                ? `${formatNumber(m.blood_pressure_systolic, 0)}/${formatNumber(m.blood_pressure_diastolic, 0)} mmHg`
                : '—';

            tr.innerHTML = `
                <td><code>${formatDateTime(m.timestamp)}</code></td>
                <td><span class="astronaut-badge">${escapeHtml(m.astronaut_id)}</span></td>
                <td><strong>${m.heart_rate !== null ? `${formatNumber(m.heart_rate, 0)} BPM` : '—'}</strong></td>
                <td><strong>${bpStr}</strong></td>
                <td>${m.oxygen_saturation !== null ? `${formatNumber(m.oxygen_saturation, 1)}%` : '—'}</td>
                <td>${m.body_temperature !== null ? `${formatNumber(m.body_temperature, 1)}°C` : '—'}</td>
                <td><span class="class-pill ${m.data_classification || 'simulated_demo'}">${escapeHtml(m.data_classification || 'simulated_demo')}</span></td>
            `;
            tbody.appendChild(tr);
        });
    },

    /**
     * Configures the vital submission form listeners and pre-fills current timestamp.
     */
    setupFormListeners() {
        const form = document.getElementById('health-submit-form');
        const tsInput = document.getElementById('input-timestamp');
        const nowBtn = document.getElementById('btn-set-current-time');

        if (tsInput) {
            this.setCurrentUtcTime();
        }

        if (nowBtn) {
            nowBtn.addEventListener('click', () => this.setCurrentUtcTime());
        }

        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.handleFormSubmit();
            });
        }
    },

    /**
     * Sets current UTC time in the timestamp input.
     */
    setCurrentUtcTime() {
        const tsInput = document.getElementById('input-timestamp');
        if (tsInput) {
            const now = new Date();
            // Format to ISO string truncated to seconds: YYYY-MM-DDTHH:MM:SSZ
            tsInput.value = now.toISOString().replace(/\.\d{3}Z$/, 'Z');
        }
    },

    /**
     * Validates input values on the client before calling the POST API.
     * 
     * @param {object} payload 
     * @returns {Array<string>} Validation error messages
     */
    validateClientInputs(payload) {
        const errors = [];

        if (!payload.astronaut_id || !payload.astronaut_id.trim()) {
            errors.push('Astronaut Identifier is required (e.g. AST-01).');
        }

        if (!payload.timestamp || !payload.timestamp.trim()) {
            errors.push('Timestamp is required (ISO 8601 UTC).');
        }

        // Heart Rate Check
        if (payload.heart_rate !== null) {
            if (isNaN(payload.heart_rate) || payload.heart_rate < 30 || payload.heart_rate > 240) {
                errors.push('Heart rate must be between 30 and 240 BPM.');
            }
        }

        // Blood Pressure Check
        const sys = payload.blood_pressure_systolic;
        const dia = payload.blood_pressure_diastolic;

        if (sys !== null) {
            if (isNaN(sys) || sys < 50 || sys > 260) {
                errors.push('Systolic blood pressure must be between 50 and 260 mmHg.');
            }
        }

        if (dia !== null) {
            if (isNaN(dia) || dia < 30 || dia > 160) {
                errors.push('Diastolic blood pressure must be between 30 and 160 mmHg.');
            }
        }

        if (sys !== null && dia !== null) {
            if (sys <= dia) {
                errors.push(`Systolic pressure (${sys} mmHg) must be strictly greater than diastolic pressure (${dia} mmHg).`);
            }
        }

        // Oxygen Saturation Check
        if (payload.oxygen_saturation !== null) {
            if (isNaN(payload.oxygen_saturation) || payload.oxygen_saturation < 50 || payload.oxygen_saturation > 100) {
                errors.push('Oxygen saturation must be between 50.0% and 100.0%.');
            }
        }

        // Body Temperature Check
        if (payload.body_temperature !== null) {
            if (isNaN(payload.body_temperature) || payload.body_temperature < 30.0 || payload.body_temperature > 44.0) {
                errors.push('Body temperature must be between 30.0°C and 44.0°C.');
            }
        }

        // At least one vital must be provided
        if (payload.heart_rate === null && sys === null && dia === null && 
            payload.oxygen_saturation === null && payload.body_temperature === null) {
            errors.push('At least one vital measurement (Heart Rate, BP, SpO2, or Temp) must be entered.');
        }

        return errors;
    },

    /**
     * Handles form submission to POST /api/health/measurements.
     */
    async handleFormSubmit() {
        const feedbackEl = document.getElementById('form-feedback-banner');
        const submitBtn = document.getElementById('btn-submit-vitals');

        // Extract input values
        const astronautId = document.getElementById('input-astronaut-id')?.value.trim();
        const timestamp = document.getElementById('input-timestamp')?.value.trim();
        const hrVal = document.getElementById('input-heart-rate')?.value;
        const sysVal = document.getElementById('input-bp-systolic')?.value;
        const diaVal = document.getElementById('input-bp-diastolic')?.value;
        const spo2Val = document.getElementById('input-spo2')?.value;
        const tempVal = document.getElementById('input-temperature')?.value;
        const device = document.getElementById('input-source-device')?.value.trim() || 'Wearable Crew Health Monitor';
        const classification = document.getElementById('input-data-classification')?.value || 'simulated_demo';
        const notes = document.getElementById('input-notes')?.value.trim() || '';

        const payload = {
            astronaut_id: astronautId,
            timestamp: timestamp,
            heart_rate: hrVal ? parseFloat(hrVal) : null,
            blood_pressure_systolic: sysVal ? parseFloat(sysVal) : null,
            blood_pressure_diastolic: diaVal ? parseFloat(diaVal) : null,
            oxygen_saturation: spo2Val ? parseFloat(spo2Val) : null,
            body_temperature: tempVal ? parseFloat(tempVal) : null,
            source_device: device,
            data_classification: classification,
            notes: notes
        };

        // Client validation
        const clientErrors = this.validateClientInputs(payload);
        if (clientErrors.length > 0) {
            if (feedbackEl) {
                feedbackEl.className = 'feedback-banner error';
                feedbackEl.innerHTML = `
                    <strong>⚠️ Validation Errors:</strong>
                    <ul>${clientErrors.map(e => `<li>${escapeHtml(e)}</li>`).join('')}</ul>
                `;
                feedbackEl.style.display = 'block';
            }
            showToast('Please correct validation errors before submitting.', 'warning');
            return;
        }

        // UI Loading State
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = `<span class="spinner-small"></span> Validating & Submitting...`;
        }

        try {
            const response = await apiFetch(CONFIG.ENDPOINTS.HEALTH_MEASUREMENTS, {
                method: 'POST',
                body: JSON.stringify(payload)
            });

            // Success feedback
            if (feedbackEl) {
                let alertMsg = '';
                if (response.alerts_triggered_count > 0) {
                    alertMsg = `
                        <div class="feedback-alerts">
                            <strong>⚠️ ${response.alerts_triggered_count} Clinical Alert(s) Triggered:</strong>
                            <ul>
                                ${response.alerts.map(a => `<li>[${escapeHtml(a.severity)}] <strong>${escapeHtml(a.alert_type)}</strong>: ${escapeHtml(a.description)}</li>`).join('')}
                            </ul>
                        </div>
                    `;
                }

                feedbackEl.className = 'feedback-banner success';
                feedbackEl.innerHTML = `
                    <strong>✅ Observation Successfully Recorded!</strong>
                    <div>Record ID: <code>${escapeHtml(response.record_id)}</code></div>
                    <div>Stored in SQLite Database with preserved units.</div>
                    ${alertMsg}
                `;
                feedbackEl.style.display = 'block';
            }

            showToast(`Health record for ${astronautId} stored successfully!`, 'success');

            // Refresh recent measurements and history
            await this.loadRecentMeasurements(astronautId);
            if (typeof AlertsModule !== 'undefined' && AlertsModule.loadHealthAlerts) {
                AlertsModule.loadHealthAlerts();
            }
            if (typeof ChartsModule !== 'undefined' && ChartsModule.refreshAllCharts) {
                ChartsModule.refreshAllCharts();
            }

            // Reset inputs except astronaut and classification
            document.getElementById('input-heart-rate').value = '';
            document.getElementById('input-bp-systolic').value = '';
            document.getElementById('input-bp-diastolic').value = '';
            document.getElementById('input-spo2').value = '';
            document.getElementById('input-temperature').value = '';
            document.getElementById('input-notes').value = '';
            this.setCurrentUtcTime();

        } catch (error) {
            console.error('Error recording health measurement:', error);
            if (feedbackEl) {
                feedbackEl.className = 'feedback-banner error';
                feedbackEl.innerHTML = `
                    <strong>❌ Server Error:</strong> ${escapeHtml(error.message)}
                `;
                feedbackEl.style.display = 'block';
            }
            showToast(`Submission failed: ${error.message}`, 'error');
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = `🚀 Transmit Vitals Telemetry`;
            }
        }
    }
};
