/**
 * dashboard.js - ASTRA CARE Main Application Controller & View Router
 * 
 * Manages:
 * - Single Page Application (SPA) view switching (Dashboard, Radiation, Health, Alerts, History, About)
 * - Navigation state, URL hash routing, and mobile sidebar drawer
 * - Polling loop for live telemetry updates (every 15s)
 * - Quick statistics aggregations on the main Dashboard view
 * - System connectivity health checks
 */

const App = {
    currentView: 'dashboard',
    pollingTimer: null,
    isPollingActive: true,

    /**
     * Initializes the entire frontend application.
     */
    async init() {
        console.log('Initializing ASTRA CARE Frontend Dashboard...');

        // 1. Setup Navigation & Routing
        this.setupNavigation();
        this.setupMobileMenu();
        this.setupPollingControls();

        // 2. Initial Data Loading across modules
        await this.checkSystemHealth();
        await Promise.all([
            RadiationModule.init(),
            HealthModule.init(),
            AlertsModule.init(),
            ChartsModule.init(),
            typeof AssistantModule !== 'undefined' ? AssistantModule.init() : Promise.resolve()
        ]);

        // 3. Render Overview Dashboard metrics
        this.updateOverviewDashboard();

        // 4. Start Live Polling Loop
        this.startPolling();

        console.log('ASTRA CARE Dashboard ready.');
    },

    /**
     * Configures SPA view navigation (Navbar & Sidebar clicks).
     */
    setupNavigation() {
        const navLinks = document.querySelectorAll('[data-view]');
        navLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const targetView = link.getAttribute('data-view');
                this.switchView(targetView);
            });
        });

        // Handle browser Back/Forward navigation with URL hash
        window.addEventListener('hashchange', () => {
            const hashView = window.location.hash.replace('#', '');
            if (hashView && document.getElementById(`view-${hashView}`)) {
                this.switchView(hashView, false);
            }
        });

        // Read initial hash if present
        const initialHash = window.location.hash.replace('#', '');
        if (initialHash && document.getElementById(`view-${initialHash}`)) {
            this.switchView(initialHash, false);
        } else {
            this.switchView('dashboard', false);
        }
    },

    /**
     * Switches the active view/page in the SPA.
     * 
     * @param {string} viewName 
     * @param {boolean} updateHash 
     */
    switchView(viewName, updateHash = true) {
        const views = document.querySelectorAll('.app-view');
        const targetView = document.getElementById(`view-${viewName}`);

        if (!targetView) {
            console.warn(`View 'view-${viewName}' not found.`);
            return;
        }

        // Hide all views, display target
        views.forEach(v => v.classList.remove('active'));
        targetView.classList.add('active');

        // Update navigation active states
        document.querySelectorAll('[data-view]').forEach(link => {
            if (link.getAttribute('data-view') === viewName) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });

        this.currentView = viewName;
        if (updateHash) {
            window.location.hash = viewName;
        }

        // Close mobile drawer if open
        const sidebar = document.getElementById('app-sidebar');
        if (sidebar) sidebar.classList.remove('open');

        // Scroll top smoothly
        window.scrollTo({ top: 0, behavior: 'smooth' });

        // Trigger chart resize if navigating to History or Dashboard
        if (viewName === 'history' || viewName === 'dashboard' || viewName === 'radiation') {
            setTimeout(() => {
                if (typeof ChartsModule !== 'undefined' && ChartsModule.refreshAllCharts) {
                    ChartsModule.refreshAllCharts();
                }
            }, 100);
        }
    },

    /**
     * Sets up mobile drawer toggle and backdrop.
     */
    setupMobileMenu() {
        const toggleBtn = document.getElementById('mobile-menu-toggle');
        const sidebar = document.getElementById('app-sidebar');
        const backdrop = document.getElementById('sidebar-backdrop');

        if (toggleBtn && sidebar) {
            toggleBtn.addEventListener('click', () => {
                sidebar.classList.toggle('open');
                if (backdrop) backdrop.classList.toggle('open');
            });
        }

        if (backdrop && sidebar) {
            backdrop.addEventListener('click', () => {
                sidebar.classList.remove('open');
                backdrop.classList.remove('open');
            });
        }
    },

    /**
     * Configures the Auto-Refresh / Live Polling toggle and Manual Refresh button.
     */
    setupPollingControls() {
        const refreshBtn = document.getElementById('btn-manual-refresh');
        const pollingToggle = document.getElementById('toggle-live-polling');

        if (refreshBtn) {
            refreshBtn.addEventListener('click', async () => {
                refreshBtn.classList.add('rotating');
                await this.refreshAllData();
                showToast('All telemetry and alerts refreshed.', 'info');
                setTimeout(() => refreshBtn.classList.remove('rotating'), 600);
            });
        }

        if (pollingToggle) {
            pollingToggle.addEventListener('change', (e) => {
                this.isPollingActive = e.target.checked;
                if (this.isPollingActive) {
                    this.startPolling();
                    showToast('Live telemetry polling active (15s interval).', 'info');
                } else {
                    this.stopPolling();
                    showToast('Live polling paused.', 'warning');
                }
            });
        }
    },

    /**
     * Starts the automated live polling loop.
     */
    startPolling() {
        this.stopPolling();
        if (!this.isPollingActive) return;

        this.pollingTimer = setInterval(async () => {
            if (this.isPollingActive) {
                await this.refreshAllData(true);
            }
        }, CONFIG.POLLING_INTERVAL_MS);
    },

    /**
     * Stops the automated live polling loop.
     */
    stopPolling() {
        if (this.pollingTimer) {
            clearInterval(this.pollingTimer);
            this.pollingTimer = null;
        }
    },

    /**
     * Checks backend system health and database statistics.
     */
    async checkSystemHealth() {
        try {
            const data = await apiFetch(CONFIG.ENDPOINTS.HEALTH_CHECK);
            updateConnectionStatus(true);

            // Update footer or status indicators
            const dbStatusEl = document.getElementById('system-db-records');
            if (dbStatusEl && data.database) {
                const totalStored = (data.database.radiation_records || 0) + (data.database.health_records || 0);
                dbStatusEl.textContent = `${totalStored} Telemetry Records in SQLite`;
            }
        } catch (error) {
            console.warn('Backend health check failed:', error);
            updateConnectionStatus(false, error.message);
        }
    },

    /**
     * Refreshes all active telemetry across modules.
     * 
     * @param {boolean} isBackgroundPolling 
     */
    async refreshAllData(isBackgroundPolling = false) {
        try {
            await Promise.all([
                RadiationModule.loadRadiationSample(),
                RadiationModule.loadRadiationAnalysis(),
                HealthModule.loadRecentMeasurements(),
                AlertsModule.loadAllAlerts()
            ]);

            this.updateOverviewDashboard();

            // Refresh charts if on visible views
            if (this.currentView === 'history' || this.currentView === 'dashboard') {
                await ChartsModule.refreshAllCharts();
            }
        } catch (error) {
            if (!isBackgroundPolling) {
                console.error('Error refreshing telemetry:', error);
            }
        }
    },

    /**
     * Updates high-level overview metrics on the main Dashboard view.
     */
    updateOverviewDashboard() {
        // 1. Current Radiation Overview
        const radDoseEl = document.getElementById('overview-radiation-dose');
        const radStatusEl = document.getElementById('overview-radiation-status');
        if (RadiationModule.currentSample && RadiationModule.currentSample.records.length > 0) {
            const latestRad = RadiationModule.currentSample.records[0];
            const rate = latestRad.absorbed_dose_rate;
            if (radDoseEl) radDoseEl.textContent = `${formatNumber(rate, 2)} µGy/hr`;
            
            if (radStatusEl) {
                if (rate >= 100.0) {
                    radStatusEl.textContent = 'HIGH: SHELTER BENCHMARK';
                    radStatusEl.className = 'status-tag critical';
                } else if (rate >= 20.0) {
                    radStatusEl.textContent = 'ELEVATED: SAA PASS';
                    radStatusEl.className = 'status-tag warning';
                } else {
                    radStatusEl.textContent = 'NOMINAL LEO BACKGROUND';
                    radStatusEl.className = 'status-tag nominal';
                }
            }
        }

        // 2. Health Vitals Overview
        const crewHrEl = document.getElementById('overview-heart-rate');
        const crewBpEl = document.getElementById('overview-blood-pressure');
        const crewSpo2El = document.getElementById('overview-spo2');
        const crewTempEl = document.getElementById('overview-temperature');

        if (HealthModule.latestRecord) {
            const h = HealthModule.latestRecord;
            if (crewHrEl) crewHrEl.textContent = h.heart_rate !== null ? `${formatNumber(h.heart_rate, 0)} BPM` : '—';
            if (crewBpEl) {
                crewBpEl.textContent = (h.blood_pressure_systolic !== null && h.blood_pressure_diastolic !== null)
                    ? `${formatNumber(h.blood_pressure_systolic, 0)}/${formatNumber(h.blood_pressure_diastolic, 0)} mmHg`
                    : '—';
            }
            if (crewSpo2El) crewSpo2El.textContent = h.oxygen_saturation !== null ? `${formatNumber(h.oxygen_saturation, 1)}%` : '—';
            if (crewTempEl) crewTempEl.textContent = h.body_temperature !== null ? `${formatNumber(h.body_temperature, 1)}°C` : '—';
        }

        // 3. Active Alert Counters
        const criticalCount = AlertsModule.allAlerts.filter(a => a.severity === 'CRITICAL').length;
        const totalAlerts = AlertsModule.allAlerts.length;
        const alertStatEl = document.getElementById('overview-active-alerts');
        const alertTagEl = document.getElementById('overview-alerts-tag');

        if (alertStatEl) alertStatEl.textContent = totalAlerts;
        if (alertTagEl) {
            if (criticalCount > 0) {
                alertTagEl.textContent = `${criticalCount} CRITICAL ALERT(S)`;
                alertTagEl.className = 'status-tag critical';
            } else if (totalAlerts > 0) {
                alertTagEl.textContent = `${totalAlerts} OPERATIONAL ADVISORY`;
                alertTagEl.className = 'status-tag warning';
            } else {
                alertTagEl.textContent = 'ALL SYSTEMS NOMINAL';
                alertTagEl.className = 'status-tag nominal';
            }
        }

        // 4. Recent Alerts Preview List on Dashboard
        const previewContainer = document.getElementById('dashboard-alerts-preview');
        if (previewContainer) {
            const top3 = AlertsModule.allAlerts.slice(0, 3);
            if (top3.length === 0) {
                previewContainer.innerHTML = `<div class="empty-preview">✅ No active clinical or radiation alerts. Systems normal.</div>`;
            } else {
                previewContainer.innerHTML = top3.map(a => `
                    <div class="mini-alert-item severity-${a.severity.toLowerCase()}">
                        <span class="mini-sev-badge ${a.severity.toLowerCase()}">${a.severity}</span>
                        <div class="mini-alert-info">
                            <strong>${escapeHtml(a.alert_type.replace(/_/g, ' '))}</strong>
                            <span>${escapeHtml(a.description)}</span>
                        </div>
                        <span class="mini-alert-time">${formatDateTime(a.timestamp)}</span>
                    </div>
                `).join('');
            }
        }
    }
};

// Auto-boot on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});
