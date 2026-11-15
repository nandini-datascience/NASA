import React, { useState } from 'react';
import { TrendingUp, Heart, Activity, Thermometer, Calendar } from 'lucide-react';

export default function HealthTrendsCharts({ healthHistory, radiationHistory }) {
  const [timePeriod, setTimePeriod] = useState('24h');
  const [activeMetric, setActiveMetric] = useState('heart_rate');

  const records = healthHistory?.records || [];

  // Generate synthetic baseline series if records are few
  const samplePoints = records.length > 0
    ? records.slice(0, 15).reverse()
    : [
        { timestamp: '2026-11-14T00:00:00Z', heart_rate: 68, oxygen_saturation: 98.6, body_temperature: 36.6 },
        { timestamp: '2026-11-14T04:00:00Z', heart_rate: 58, oxygen_saturation: 99.0, body_temperature: 36.4 },
        { timestamp: '2026-11-14T08:00:00Z', heart_rate: 74, oxygen_saturation: 98.4, body_temperature: 36.7 },
        { timestamp: '2026-11-14T12:00:00Z', heart_rate: 102, oxygen_saturation: 97.8, body_temperature: 37.1 },
        { timestamp: '2026-11-14T16:00:00Z', heart_rate: 76, oxygen_saturation: 98.5, body_temperature: 36.8 },
        { timestamp: '2026-11-14T20:00:00Z', heart_rate: 70, oxygen_saturation: 98.4, body_temperature: 36.8 }
      ];

  // Helper to extract values
  const getValues = () => {
    switch (activeMetric) {
      case 'oxygen_saturation':
        return samplePoints.map((p) => ({
          t: p.timestamp,
          v: p.oxygen_saturation ?? 98.4,
          unit: '%'
        }));
      case 'body_temperature':
        return samplePoints.map((p) => ({
          t: p.timestamp,
          v: p.body_temperature ?? 36.8,
          unit: '°C'
        }));
      case 'heart_rate':
      default:
        return samplePoints.map((p) => ({
          t: p.timestamp,
          v: p.heart_rate ?? 72,
          unit: 'BPM'
        }));
    }
  };

  const points = getValues();
  const minVal = Math.min(...points.map((p) => p.v));
  const maxVal = Math.max(...points.map((p) => p.v));
  const pad = (maxVal - minVal) * 0.15 || 2;
  const yMin = Math.floor(minVal - pad);
  const yMax = Math.ceil(maxVal + pad);

  // SVG Chart Dimensions
  const svgWidth = 840;
  const svgHeight = 180;
  const paddingX = 45;
  const paddingY = 25;

  const chartW = svgWidth - paddingX * 2;
  const chartH = svgHeight - paddingY * 2;

  const getCoordinates = (index, value) => {
    const x = paddingX + (index / (points.length - 1 || 1)) * chartW;
    const y = svgHeight - paddingY - ((value - yMin) / (yMax - yMin || 1)) * chartH;
    return { x, y };
  };

  // Build SVG path
  const pathD = points.reduce((acc, pt, i) => {
    const { x, y } = getCoordinates(i, pt.v);
    return i === 0 ? `M ${x} ${y}` : `${acc} L ${x} ${y}`;
  }, '');

  const areaD = points.length > 0
    ? `${pathD} L ${paddingX + chartW} ${svgHeight - paddingY} L ${paddingX} ${svgHeight - paddingY} Z`
    : '';

  const getMetricColor = () => {
    if (activeMetric === 'oxygen_saturation') return '#8b5cf6';
    if (activeMetric === 'body_temperature') return '#10b981';
    return '#ef4444';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
      {/* Top Filter Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
        {/* Metric Selector Buttons */}
        <div style={{ display: 'flex', gap: '0.4rem' }}>
          <button
            type="button"
            className={`twin-region-pill ${activeMetric === 'heart_rate' ? 'active' : ''}`}
            onClick={() => setActiveMetric('heart_rate')}
          >
            Heart Rate (BPM)
          </button>
          <button
            type="button"
            className={`twin-region-pill ${activeMetric === 'oxygen_saturation' ? 'active' : ''}`}
            onClick={() => setActiveMetric('oxygen_saturation')}
          >
            Oxygen SpO2 (%)
          </button>
          <button
            type="button"
            className={`twin-region-pill ${activeMetric === 'body_temperature' ? 'active' : ''}`}
            onClick={() => setActiveMetric('body_temperature')}
          >
            Body Temp (°C)
          </button>
        </div>

        {/* Time Period Filter */}
        <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
          <span style={{ fontSize: '0.72rem', color: 'var(--twin-text-secondary)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <Calendar size={12} /> Range:
          </span>
          {['1h', '6h', '24h', '7d', 'All'].map((p) => (
            <button
              key={p}
              type="button"
              className={`twin-region-pill ${timePeriod === p ? 'active' : ''}`}
              style={{ padding: '0.15rem 0.5rem', fontSize: '0.68rem' }}
              onClick={() => setTimePeriod(p)}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* SVG Time-Series Chart */}
      <div className="twin-waveform-box" style={{ padding: '0.5rem' }}>
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          style={{ width: '100%', height: '180px', display: 'block' }}
        >
          <defs>
            <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={getMetricColor()} stopOpacity="0.4" />
              <stop offset="100%" stopColor={getMetricColor()} stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          <line x1={paddingX} y1={paddingY} x2={paddingX + chartW} y2={paddingY} stroke="rgba(255,255,255,0.06)" />
          <line x1={paddingX} y1={paddingY + chartH / 2} x2={paddingX + chartW} y2={paddingY + chartH / 2} stroke="rgba(255,255,255,0.06)" />
          <line x1={paddingX} y1={svgHeight - paddingY} x2={paddingX + chartW} y2={svgHeight - paddingY} stroke="rgba(255,255,255,0.12)" />

          {/* Y Axis Labels */}
          <text x={paddingX - 8} y={paddingY + 4} fill="#64748b" fontSize="10" textAnchor="end" fontFamily="monospace">
            {yMax}
          </text>
          <text x={paddingX - 8} y={paddingY + chartH / 2 + 4} fill="#64748b" fontSize="10" textAnchor="end" fontFamily="monospace">
            {((yMax + yMin) / 2).toFixed(1)}
          </text>
          <text x={paddingX - 8} y={svgHeight - paddingY} fill="#64748b" fontSize="10" textAnchor="end" fontFamily="monospace">
            {yMin}
          </text>

          {/* Area Fill */}
          <path d={areaD} fill="url(#chartGradient)" />

          {/* Line Stroke */}
          <path d={pathD} fill="none" stroke={getMetricColor()} strokeWidth="2.5" strokeLinecap="round" />

          {/* Data Points */}
          {points.map((pt, i) => {
            const { x, y } = getCoordinates(i, pt.v);
            return (
              <g key={i}>
                <circle cx={x} cy={y} r="3.5" fill="#fff" stroke={getMetricColor()} strokeWidth="2" />
                <text x={x} y={svgHeight - 8} fill="#64748b" fontSize="9" textAnchor="middle" fontFamily="monospace">
                  {new Date(pt.t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="twin-disclaimer-banner">
        <strong>Historical Record Source:</strong> Telemetry compiled from SQLite database. Classified as simulated demonstration records. NASA physiological benchmark: NASA-STD-3001 Vol 1.
      </div>
    </div>
  );
}
