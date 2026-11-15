/**
 * charts.js - ASTRA CARE Data Visualization & Chart.js Engine
 * 
 * Manages 5 interactive space-themed graphs:
 * 1. Radiation Absorbed Dose Rate Trend (µGy/hr)
 * 2. Heart Rate Trend (BPM)
 * 3. Blood Pressure Trend (Systolic & Diastolic mmHg)
 * 4. Oxygen Saturation Trend (SpO2 %)
 * 5. Body Temperature Trend (°C)
 * 
 * Features:
 * - High-contrast space aesthetics (neon strokes, dark translucent fills, custom gridlines)
 * - Tooltip formatting with authentic units
 * - Threshold indicator lines (NASA-STD-3001 & AHA benchmarks)
 * - Safe destruction and re-instantiation to prevent memory leaks
 */

const ChartsModule = {
    // Chart instances dictionary
    instances: {},

    // Theme color palette
    colors: {
        cyan: '#00f2fe',
        cyanFade: 'rgba(0, 242, 254, 0.15)',
        pink: '#ff4b72',
        pinkFade: 'rgba(255, 75, 114, 0.15)',
        purple: '#a855f7',
        purpleFade: 'rgba(168, 85, 247, 0.15)',
        blue: '#3b82f6',
        blueFade: 'rgba(59, 130, 246, 0.15)',
        green: '#10b981',
        greenFade: 'rgba(16, 185, 129, 0.15)',
        amber: '#f59e0b',
        amberFade: 'rgba(245, 158, 11, 0.15)',
        grid: 'rgba(255, 255, 255, 0.08)',
        text: 'rgba(255, 255, 255, 0.7)'
    },

    /**
     * Initializes all charts on page load.
     */
    async init() {
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js is not loaded yet. Retrying in 500ms...');
            setTimeout(() => this.init(), 500);
            return;
        }

        // Apply global Chart.js defaults
        Chart.defaults.color = this.colors.text;
        Chart.defaults.font.family = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
        Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(13, 20, 48, 0.95)';
        Chart.defaults.plugins.tooltip.borderColor = 'rgba(0, 242, 254, 0.3)';
        Chart.defaults.plugins.tooltip.borderWidth = 1;
        Chart.defaults.plugins.tooltip.padding = 10;
        Chart.defaults.plugins.tooltip.titleColor = '#ffffff';

        await this.refreshAllCharts();
    },

    /**
     * Refreshes all charts from backend APIs.
     */
    async refreshAllCharts() {
        await Promise.all([
            this.renderRadiationChart(),
            this.renderHealthCharts()
        ]);
    },

    /**
     * Destroys an existing chart instance before re-creating it.
     * 
     * @param {string} id 
     */
    destroyChart(id) {
        if (this.instances[id]) {
            this.instances[id].destroy();
            delete this.instances[id];
        }
    },

    /**
     * Common options for dark space-themed charts.
     */
    getCommonOptions(yAxisTitle = '', yMin = null, yMax = null) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        boxWidth: 12,
                        usePointStyle: true,
                        pointStyle: 'circle',
                        color: 'rgba(255, 255, 255, 0.85)'
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: this.colors.grid },
                    ticks: {
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 8,
                        color: this.colors.text
                    }
                },
                y: {
                    min: yMin,
                    max: yMax,
                    title: {
                        display: !!yAxisTitle,
                        text: yAxisTitle,
                        color: 'rgba(255, 255, 255, 0.6)',
                        font: { size: 12 }
                    },
                    grid: { color: this.colors.grid },
                    ticks: { color: this.colors.text }
                }
            }
        };
    },

    /**
     * 1. Renders Radiation Absorbed Dose Rate Trend (µGy/hr).
     */
    async renderRadiationChart() {
        const primaryCanvas = document.getElementById('chart-radiation-dose');
        const secondaryCanvas = document.getElementById('chart-radiation-dose-view');
        if (!primaryCanvas && !secondaryCanvas) return;

        try {
            // Fetch historical radiation telemetry
            const data = await apiFetch(`${CONFIG.ENDPOINTS.RADIATION_HISTORY}?limit=30`);
            const records = (data.records || []).slice().reverse(); // Chronological order

            if (records.length === 0) return;

            const labels = records.map(r => {
                const d = new Date(r.timestamp);
                return isNaN(d.getTime()) ? r.timestamp : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            });
            const values = records.map(r => r.absorbed_dose_rate);

            const renderOnCanvas = (canvas, key) => {
                if (!canvas) return;
                this.destroyChart(key);
                const ctx = canvas.getContext('2d');
                this.instances[key] = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Absorbed Dose Rate (µGy/hr)',
                            data: values,
                            borderColor: this.colors.cyan,
                            backgroundColor: this.colors.cyanFade,
                            fill: true,
                            tension: 0.35,
                            borderWidth: 2.5,
                            pointBackgroundColor: this.colors.cyan,
                            pointRadius: 3,
                            pointHoverRadius: 6
                        }]
                    },
                    options: this.getCommonOptions('Dose Rate (µGy/hr)', 0, null)
                });
            };

            if (primaryCanvas) renderOnCanvas(primaryCanvas, 'radiation');
            if (secondaryCanvas) renderOnCanvas(secondaryCanvas, 'radiation_view');

        } catch (error) {
            console.error('Error rendering radiation chart:', error);
        }
    },

    /**
     * 2-5. Renders Heart Rate, Blood Pressure, SpO2, and Body Temperature Charts.
     */
    async renderHealthCharts() {
        try {
            const data = await apiFetch(`${CONFIG.ENDPOINTS.HEALTH_HISTORY}?limit=30`);
            const records = data.records || [];
            if (records.length === 0) return;

            const labels = records.map(r => {
                const d = new Date(r.timestamp);
                return isNaN(d.getTime()) ? r.timestamp : `${d.toLocaleDateString([], { month: 'numeric', day: 'numeric' })} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
            });

            // (A) Heart Rate Chart
            const hrCanvas = document.getElementById('chart-heart-rate');
            if (hrCanvas) {
                const hrValues = records.map(r => r.heart_rate);
                this.destroyChart('heartRate');

                const ctx = hrCanvas.getContext('2d');
                this.instances['heartRate'] = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Heart Rate (BPM)',
                            data: hrValues,
                            borderColor: this.colors.pink,
                            backgroundColor: this.colors.pinkFade,
                            fill: true,
                            tension: 0.35,
                            borderWidth: 2.5,
                            pointBackgroundColor: this.colors.pink,
                            pointRadius: 4
                        }]
                    },
                    options: this.getCommonOptions('Pulse (BPM)', 40, 160)
                });
            }

            // (B) Blood Pressure Chart (Dual line: Systolic & Diastolic)
            const bpCanvas = document.getElementById('chart-blood-pressure');
            if (bpCanvas) {
                const sysValues = records.map(r => r.blood_pressure_systolic);
                const diaValues = records.map(r => r.blood_pressure_diastolic);
                this.destroyChart('bloodPressure');

                const ctx = bpCanvas.getContext('2d');
                this.instances['bloodPressure'] = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [
                            {
                                label: 'Systolic (mmHg)',
                                data: sysValues,
                                borderColor: this.colors.purple,
                                backgroundColor: this.colors.purpleFade,
                                fill: false,
                                tension: 0.35,
                                borderWidth: 2.5,
                                pointBackgroundColor: this.colors.purple,
                                pointRadius: 4
                            },
                            {
                                label: 'Diastolic (mmHg)',
                                data: diaValues,
                                borderColor: this.colors.blue,
                                backgroundColor: this.colors.blueFade,
                                fill: false,
                                tension: 0.35,
                                borderWidth: 2.5,
                                pointBackgroundColor: this.colors.blue,
                                pointRadius: 4
                            }
                        ]
                    },
                    options: this.getCommonOptions('Pressure (mmHg)', 40, 200)
                });
            }

            // (C) Oxygen Saturation (SpO2) Chart
            const spo2Canvas = document.getElementById('chart-spo2');
            if (spo2Canvas) {
                const spo2Values = records.map(r => r.oxygen_saturation);
                this.destroyChart('spo2');

                const ctx = spo2Canvas.getContext('2d');
                this.instances['spo2'] = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Oxygen Saturation (%)',
                            data: spo2Values,
                            borderColor: this.colors.green,
                            backgroundColor: this.colors.greenFade,
                            fill: true,
                            tension: 0.35,
                            borderWidth: 2.5,
                            pointBackgroundColor: this.colors.green,
                            pointRadius: 4
                        }]
                    },
                    options: this.getCommonOptions('SpO2 (%)', 85, 100)
                });
            }

            // (D) Body Temperature Chart (°C)
            const tempCanvas = document.getElementById('chart-temperature');
            if (tempCanvas) {
                const tempValues = records.map(r => r.body_temperature);
                this.destroyChart('temperature');

                const ctx = tempCanvas.getContext('2d');
                this.instances['temperature'] = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Body Temp (°C)',
                            data: tempValues,
                            borderColor: this.colors.amber,
                            backgroundColor: this.colors.amberFade,
                            fill: true,
                            tension: 0.35,
                            borderWidth: 2.5,
                            pointBackgroundColor: this.colors.amber,
                            pointRadius: 4
                        }]
                    },
                    options: this.getCommonOptions('Temp (°C)', 35.0, 40.0)
                });
            }

        } catch (error) {
            console.error('Error rendering health charts:', error);
        }
    }
};
