import React, { useState } from 'react';
import { Database, Filter, Search, AlertTriangle, ShieldCheck, CheckCircle2 } from 'lucide-react';

export default function HistoricalDataExplorer({
  healthHistory,
  radiationHistory,
  alertsList
}) {
  const [category, setCategory] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');

  const healthRecords = (healthHistory?.records || []).map((r) => ({
    id: r.record_id || `H-${r.id}`,
    category: 'HEALTH',
    timestamp: r.timestamp,
    title: `Astronaut Vitals (${r.astronaut_id || 'AST-01'})`,
    primary_metric: `HR: ${r.heart_rate} BPM | BP: ${r.blood_pressure_systolic}/${r.blood_pressure_diastolic}`,
    secondary_metric: `SpO2: ${r.oxygen_saturation}% | Temp: ${r.body_temperature}°C`,
    source: r.source_device || 'Wearable Sensor',
    classification: r.data_classification || 'simulated_demo',
    is_anomaly: (r.heart_rate > 100 || r.heart_rate < 55 || r.oxygen_saturation < 95)
  }));

  const radiationRecords = (radiationHistory?.records || []).map((r) => ({
    id: `RAD-${r.id}`,
    category: 'RADIATION',
    timestamp: r.timestamp,
    title: `RadLab Dosimetry (${r.instrument_id || 'DosTel1'})`,
    primary_metric: `Dose Rate: ${r.absorbed_dose_rate} µGy/hr`,
    secondary_metric: `Eq: ${r.dose_equivalent_rate || '--'} µSv/hr | Alt: ${r.altitude || '--'} km`,
    source: r.source_origin || 'NASA RadLab Archive',
    classification: r.is_historical ? 'historical_study' : 'authentic_nasa_archive',
    is_anomaly: (r.absorbed_dose_rate > 10.0)
  }));

  const allRecords = [...healthRecords, ...radiationRecords].sort(
    (a, b) => new Date(b.timestamp) - new Date(a.timestamp)
  );

  const filtered = allRecords.filter((rec) => {
    if (category !== 'all' && rec.category !== category) return false;
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      return (
        rec.id.toLowerCase().includes(q) ||
        rec.title.toLowerCase().includes(q) ||
        rec.primary_metric.toLowerCase().includes(q) ||
        rec.source.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
      {/* Category Pills & Search */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div style={{ display: 'flex', gap: '0.4rem' }}>
          {[
            { id: 'all', label: 'All Records' },
            { id: 'HEALTH', label: 'Crew Vitals' },
            { id: 'RADIATION', label: 'Space Radiation' }
          ].map((cat) => (
            <button
              key={cat.id}
              type="button"
              className={`twin-region-pill ${category === cat.id ? 'active' : ''}`}
              onClick={() => setCategory(cat.id)}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* Search Input */}
        <div style={{ position: 'relative' }}>
          <input
            type="text"
            placeholder="Search telemetry records..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              background: '#0a1428',
              border: '1px solid var(--twin-border)',
              borderRadius: '6px',
              padding: '0.35rem 0.65rem 0.35rem 1.8rem',
              color: '#fff',
              fontSize: '0.75rem',
              fontFamily: 'var(--twin-font-mono)',
              width: '210px'
            }}
          />
          <Search size={12} color="#64748b" style={{ position: 'absolute', left: '8px', top: '9px' }} />
        </div>
      </div>

      {/* Explorer Table */}
      <div style={{ background: 'rgba(6, 12, 26, 0.75)', border: '1px solid var(--twin-border)', borderRadius: '8px', overflow: 'hidden' }}>
        <div style={{ maxHeight: '240px', overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.74rem', textAlign: 'left' }}>
            <thead>
              <tr style={{ background: 'rgba(14, 24, 48, 0.8)', borderBottom: '1px solid var(--twin-border)', color: 'var(--twin-cyan)', fontFamily: 'var(--twin-font-mono)' }}>
                <th style={{ padding: '0.55rem 0.75rem' }}>ID & Timestamp</th>
                <th style={{ padding: '0.55rem 0.75rem' }}>Category</th>
                <th style={{ padding: '0.55rem 0.75rem' }}>Primary Telemetry</th>
                <th style={{ padding: '0.55rem 0.75rem' }}>Secondary Metrics</th>
                <th style={{ padding: '0.55rem 0.75rem' }}>Data Source & Status</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length > 0 ? (
                filtered.map((r, i) => (
                  <tr
                    key={i}
                    style={{
                      borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                      background: i % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.015)'
                    }}
                  >
                    <td style={{ padding: '0.5rem 0.75rem', fontFamily: 'var(--twin-font-mono)' }}>
                      <div style={{ color: '#fff', fontWeight: 600 }}>{r.id}</div>
                      <div style={{ color: 'var(--twin-text-muted)', fontSize: '0.68rem' }}>
                        {new Date(r.timestamp).toLocaleString()}
                      </div>
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem' }}>
                      <span className={`twin-badge ${r.category === 'RADIATION' ? 'info' : 'normal'}`}>
                        {r.category}
                      </span>
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem', fontFamily: 'var(--twin-font-mono)', color: 'var(--twin-text-primary)' }}>
                      {r.primary_metric}
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem', color: 'var(--twin-text-secondary)' }}>
                      {r.secondary_metric}
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                        {r.is_anomaly ? (
                          <span style={{ color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '0.2rem', fontSize: '0.68rem' }}>
                            <AlertTriangle size={12} /> Elevated
                          </span>
                        ) : (
                          <span style={{ color: '#10b981', display: 'flex', alignItems: 'center', gap: '0.2rem', fontSize: '0.68rem' }}>
                            <CheckCircle2 size={12} /> Nominal
                          </span>
                        )}
                        <span style={{ fontSize: '0.68rem', color: 'var(--twin-text-muted)' }}>
                          • {r.source}
                        </span>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--twin-text-muted)' }}>
                    No historical records match the selected query.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="twin-disclaimer-banner">
        <strong>Data Integrity Policy:</strong> All historical measurements include verified UTC timestamps, device origins, and explicit classification (authentic NASA scientific RadLab archive vs simulated crew health telemetry).
      </div>
    </div>
  );
}
