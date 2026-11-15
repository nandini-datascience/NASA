/**
 * alerts.js - ASTRA CARE Unified Alert Management Engine
 * 
 * Interfaces with:
 * - GET /api/alerts (Space Radiation Alerts & Data Quality Warnings)
 * - GET /api/health/alerts (Astronaut Health Alerts & Physiological Warnings)
 * 
 * Features:
 * - Unifies radiation and clinical health alerts in one cohesive interface
 * - Distinct styling for CRITICAL (red), WARNING (amber), and INFO (cyan/blue)
 * - Renders backend-provided explanations, recommendations, and guideline references
 * - Never invents medical thresholds or clinical recommendations
 * - Interactive filtering by module, severity, and text search
 */

const AlertsModule = {
    radiationAlerts: [],
    healthAlerts: [],
    allAlerts: [],

    activeFilterModule: 'all',
    activeFilterSeverity: 'all',
    searchQuery: '',

    /**
     * Initializes alerts module and loads both alert streams.
     */
    async init() {
        await this.loadAllAlerts();
        this.setupFilterListeners();
    },

    /**
     * Fetches radiation and health alerts from the backend.
     */
    async loadAllAlerts() {
        const loadingEl = document.getElementById('alerts-loading-spinner');
        if (loadingEl) loadingEl.style.display = 'block';

        try {
            const [radData, healthData] = await Promise.all([
                apiFetch(`${CONFIG.ENDPOINTS.RADIATION_ALERTS}?limit=50`).catch(e => ({ alerts: [] })),
                apiFetch(`${CONFIG.ENDPOINTS.HEALTH_ALERTS}?limit=50`).catch(e => ({ alerts: [] }))
            ]);

            this.radiationAlerts = (radData.alerts || []).map(a => ({
                ...a,
                _source_module: 'radiation',
                _target_entity: a.instrument_id || a.spacecraft || 'ISS Dosimeter'
            }));

            this.healthAlerts = (healthData.alerts || []).map(a => ({
                ...a,
                _source_module: 'health',
                _target_entity: a.astronaut_id || 'Astronaut'
            }));

            // Merge and sort chronologically descending (newest first)
            this.allAlerts = [...this.radiationAlerts, ...this.healthAlerts].sort((a, b) => {
                const dateA = new Date(a.timestamp || 0).getTime();
                const dateB = new Date(b.timestamp || 0).getTime();
                return dateB - dateA;
            });

            this.updateAlertCounters();
            this.renderAlertsList();
        } catch (error) {
            console.error('Error loading alerts:', error);
            showToast(`Error loading alerts: ${error.message}`, 'error');
        } finally {
            if (loadingEl) loadingEl.style.display = 'none';
        }
    },

    /**
     * Updates alert count badges across the application.
     */
    updateAlertCounters() {
        const totalBadge = document.getElementById('global-alert-badge');
        const navAlertBadge = document.getElementById('nav-alert-badge');
        const critCountEl = document.getElementById('count-critical-alerts');
        const warnCountEl = document.getElementById('count-warning-alerts');
        const infoCountEl = document.getElementById('count-info-alerts');

        const criticals = this.allAlerts.filter(a => a.severity === 'CRITICAL').length;
        const warnings = this.allAlerts.filter(a => a.severity === 'WARNING').length;
        const infos = this.allAlerts.filter(a => a.severity === 'INFO').length;

        if (totalBadge) {
            totalBadge.textContent = this.allAlerts.length;
            totalBadge.className = `counter-pill ${criticals > 0 ? 'critical' : (warnings > 0 ? 'warning' : 'nominal')}`;
        }
        if (navAlertBadge) {
            navAlertBadge.textContent = this.allAlerts.length;
            navAlertBadge.style.display = this.allAlerts.length > 0 ? 'inline-block' : 'none';
        }

        if (critCountEl) critCountEl.textContent = criticals;
        if (warnCountEl) warnCountEl.textContent = warnings;
        if (infoCountEl) infoCountEl.textContent = infos;
    },

    /**
     * Sets up event listeners for filtering by module, severity, and search.
     */
    setupFilterListeners() {
        const moduleSelect = document.getElementById('filter-alert-module');
        const severitySelect = document.getElementById('filter-alert-severity');
        const searchInput = document.getElementById('filter-alert-search');
        const refreshBtn = document.getElementById('btn-refresh-alerts');

        if (moduleSelect) {
            moduleSelect.addEventListener('change', (e) => {
                this.activeFilterModule = e.target.value;
                this.renderAlertsList();
            });
        }

        if (severitySelect) {
            severitySelect.addEventListener('change', (e) => {
                this.activeFilterSeverity = e.target.value;
                this.renderAlertsList();
            });
        }

        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.searchQuery = e.target.value.toLowerCase().trim();
                this.renderAlertsList();
            });
        }

        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.loadAllAlerts();
                showToast('Alerts refreshed from SQLite database.', 'info');
            });
        }
    },

    /**
     * Renders filtered alerts in the alerts container.
     */
    renderAlertsList() {
        const container = document.getElementById('alerts-feed-container');
        if (!container) return;

        let filtered = this.allAlerts.filter(a => {
            // Module filter
            if (this.activeFilterModule !== 'all' && a._source_module !== this.activeFilterModule) {
                return false;
            }
            // Severity filter
            if (this.activeFilterSeverity !== 'all' && a.severity !== this.activeFilterSeverity) {
                return false;
            }
            // Search filter
            if (this.searchQuery) {
                const searchStr = `${a.alert_type} ${a.description} ${a._target_entity} ${a.metric_name || ''} ${a.guideline_reference || ''}`.toLowerCase();
                if (!searchStr.includes(this.searchQuery)) {
                    return false;
                }
            }
            return true;
        });

        if (filtered.length === 0) {
            container.innerHTML = `
                <div class="empty-alerts-card">
                    <div class="empty-icon">🛡️</div>
                    <h3>No Active Alerts</h3>
                    <p>No operational health advisories or radiation anomalies match your selected filters.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = filtered.map(alert => this.generateAlertCardHtml(alert)).join('');
    },

    /**
     * Generates HTML markup for a single alert card.
     * 
     * @param {object} alert 
     * @returns {string} HTML string
     */
    generateAlertCardHtml(alert) {
        const severity = alert.severity || 'INFO';
        const isCritical = severity === 'CRITICAL';
        const isWarning = severity === 'WARNING';
        const isInfo = severity === 'INFO';

        let sevBadgeClass = 'badge-info';
        if (isCritical) sevBadgeClass = 'badge-danger pulse-critical';
        else if (isWarning) sevBadgeClass = 'badge-warning';

        const isRadiation = alert._source_module === 'radiation';
        const moduleTag = isRadiation ? '⚛️ SPACE RADIATION' : '🩺 ASTRONAUT HEALTH';
        const moduleClass = isRadiation ? 'tag-radiation' : 'tag-health';

        const entityLabel = isRadiation ? `Detector: ${alert._target_entity}` : `Astronaut: ${alert._target_entity}`;
        const metricVal = alert.metric_value ? `${alert.metric_value} ${alert.unit || ''}` : '—';
        const thresholdVal = alert.threshold_applied ? `${alert.threshold_applied}` : 'Operational Standard';

        return `
            <div class="alert-card severity-${severity.toLowerCase()}">
                <div class="alert-card-header">
                    <div class="alert-tags">
                        <span class="module-tag ${moduleClass}">${moduleTag}</span>
                        <span class="badge ${sevBadgeClass}">${severity}</span>
                        <span class="category-tag">${escapeHtml(alert.category || 'ADVISORY')}</span>
                    </div>
                    <span class="alert-time">🕒 ${formatDateTime(alert.timestamp)}</span>
                </div>

                <div class="alert-body">
                    <div class="alert-title-row">
                        <h3 class="alert-title">${escapeHtml(alert.alert_type.replace(/_/g, ' '))}</h3>
                        <span class="target-entity-pill">${escapeHtml(entityLabel)}</span>
                    </div>

                    <p class="alert-description">${escapeHtml(alert.description)}</p>

                    <div class="alert-metrics-grid">
                        <div class="metric-box">
                            <span class="metric-label">Observed Value</span>
                            <span class="metric-value font-mono">${escapeHtml(metricVal)}</span>
                        </div>
                        <div class="metric-box">
                            <span class="metric-label">Benchmark Threshold</span>
                            <span class="metric-value font-mono">${escapeHtml(thresholdVal)}</span>
                        </div>
                        <div class="metric-box">
                            <span class="metric-label">Guideline Reference</span>
                            <span class="metric-value reference-link">${escapeHtml(alert.guideline_reference || 'NASA-STD-3001 Vol 1')}</span>
                        </div>
                    </div>

                    ${alert.explanation ? `
                        <div class="alert-section explanation-section">
                            <strong>🔬 Physiological & Mission Context:</strong>
                            <p>${escapeHtml(alert.explanation)}</p>
                        </div>
                    ` : ''}

                    ${alert.recommendation ? `
                        <div class="alert-section recommendation-section">
                            <strong>🛡️ Flight Controller / Crew Recommendation:</strong>
                            <p>${escapeHtml(alert.recommendation)}</p>
                        </div>
                    ` : ''}
                </div>

                <div class="alert-footer">
                    <span class="alert-id">ID: <code>${escapeHtml(alert.alert_id)}</code></span>
                    <span class="alert-disclaimer">Non-diagnostic aerospace operational advisory</span>
                </div>
            </div>
        `;
    }
};
