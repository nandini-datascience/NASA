import React from 'react';
import { Crosshair, Shield, Activity, FileText, Info, TrendingUp, Clock } from 'lucide-react';

export default function BodyRegionInfoPanel({
  selectedRegion,
  bodyRegionsData,
  onSelectWaveformTab
}) {
  const regions = bodyRegionsData?.regions || {};
  const isSpecific = selectedRegion && regions[selectedRegion];
  const region = isSpecific
    ? regions[selectedRegion]
    : {
        region_id: 'full_body',
        name: 'Full Body (xEMU Spacesuit)',
        anatomical_systems: 'Whole-Body Physiological & Environmental Monitoring',
        spacesuit_interface: 'Exploration Extravehicular Mobility Unit (xEMU) Integrated Systems',
        primary_metrics: [
          { label: 'Suit Pressure', value: '29.6', unit: 'kPa', status: 'NOMINAL' },
          { label: 'Suit Temperature', value: '21.4', unit: '°C', status: 'NOMINAL' },
          { label: 'O2 System Rate', value: '0.078', unit: 'kg/h', status: 'NOMINAL' },
          { label: 'Dosimetry Alert', value: 'NORMAL', unit: '', status: 'NOMINAL' }
        ],
        radiation_research_context: 'General cosmic radiation monitoring across spacesuit dosimeter array. NASA-STD-3001 & ALARA principles apply.',
        historical_measurements: [
          { timestamp: 'T-00:05:00', label: 'Whole Body Dose Rate', value: '2.14 µGy/h' },
          { timestamp: 'T-00:15:00', label: 'Suit Differential Pressure', value: '29.7 kPa' },
          { timestamp: 'T-00:30:00', label: 'Thermal Equilibrium', value: '21.2 °C' }
        ],
        data_source: 'xEMU Integrated Biomedical Sensor Suite (NASA Operational Telemetry)',
        disclaimer: 'Interactive 3D model: Click any body region (Head, Chest, Heart, Lungs, Abdomen, Arms, Legs) to inspect focused biometric sensors.'
      };
  const currentKey = selectedRegion || 'full_body';

  return (
    <div className="twin-card" style={{ height: '100%' }}>
      <div className="twin-card-header">
        <div className="twin-card-title">
          <Crosshair size={16} />
          <span>Region Inspector: {region.name}</span>
        </div>
        <span className="twin-badge info">{region.region_id?.toUpperCase()}</span>
      </div>

      <div className="twin-card-body" style={{ overflowY: 'auto' }}>
        {/* Anatomical & Suit System Description */}
        <div>
          <div style={{ fontSize: '0.72rem', color: 'var(--twin-text-muted)', fontFamily: 'var(--twin-font-mono)', textTransform: 'uppercase' }}>
            Physiological System
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--twin-text-primary)', fontWeight: 600, marginTop: '0.1rem' }}>
            {region.anatomical_systems}
          </div>
          <div style={{ fontSize: '0.74rem', color: 'var(--twin-text-secondary)', marginTop: '0.2rem' }}>
            <strong>Suit Interface:</strong> {region.spacesuit_interface}
          </div>
        </div>

        {/* Primary Metrics Table */}
        <div style={{ background: 'rgba(6, 12, 26, 0.65)', border: '1px solid rgba(0, 242, 254, 0.15)', borderRadius: '8px', padding: '0.75rem' }}>
          <div style={{ fontSize: '0.72rem', fontFamily: 'var(--twin-font-mono)', color: 'var(--twin-cyan)', marginBottom: '0.4rem', textTransform: 'uppercase' }}>
            Active Regional Telemetry
          </div>
          {region.primary_metrics?.map((m, idx) => (
            <div key={idx} className="twin-telem-row">
              <span className="twin-telem-label">{m.label}</span>
              <span className="twin-telem-val">
                {m.value} {m.unit && <span className="twin-unit">{m.unit}</span>}
              </span>
            </div>
          ))}
        </div>

        {/* Quick Shortcut Buttons based on region */}
        {currentKey === 'heart' && (
          <button
            type="button"
            className="twin-region-pill active"
            style={{ width: '100%', padding: '0.5rem', textAlign: 'center', justifyContent: 'center' }}
            onClick={() => onSelectWaveformTab && onSelectWaveformTab('ecg')}
          >
            Open ECG Rhythm Strip Waveform →
          </button>
        )}

        {currentKey === 'head' && (
          <button
            type="button"
            className="twin-region-pill active"
            style={{ width: '100%', padding: '0.5rem', textAlign: 'center', justifyContent: 'center' }}
            onClick={() => onSelectWaveformTab && onSelectWaveformTab('eeg')}
          >
            Open EEG Brainwave Spectrum →
          </button>
        )}

        {/* Historical Measurements Mini-Feed */}
        {region.historical_measurements && region.historical_measurements.length > 0 && (
          <div>
            <div style={{ fontSize: '0.72rem', fontFamily: 'var(--twin-font-mono)', color: 'var(--twin-text-muted)', marginBottom: '0.35rem', textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <Clock size={12} />
              <span>Historical Trend Samples</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              {region.historical_measurements.map((h, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: '0.72rem',
                    fontFamily: 'var(--twin-font-mono)',
                    padding: '0.3rem 0.5rem',
                    background: 'rgba(255, 255, 255, 0.03)',
                    borderRadius: '4px'
                  }}
                >
                  <span style={{ color: 'var(--twin-text-secondary)' }}>
                    {new Date(h.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} UTC
                  </span>
                  <span style={{ color: 'var(--twin-cyan)' }}>
                    {Object.entries(h)
                      .filter(([k]) => k !== 'timestamp')
                      .map(([k, v]) => `${k.replace('_', ' ')}: ${v}`)
                      .join(' | ')}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Radiation Research & Shielding Context */}
        <div style={{ background: 'rgba(15, 23, 42, 0.5)', border: '1px solid rgba(139, 92, 246, 0.25)', borderRadius: '8px', padding: '0.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: '#a78bfa', fontSize: '0.74rem', fontWeight: 700, textTransform: 'uppercase' }}>
            <Shield size={14} />
            <span>Cosmic Radiation Research Note</span>
          </div>
          <p style={{ fontSize: '0.73rem', color: 'var(--twin-text-secondary)', lineHeight: 1.45, marginTop: '0.35rem', margin: '0.35rem 0 0 0' }}>
            {region.radiation_research_context}
          </p>
        </div>

        {/* Source metadata */}
        <div style={{ fontSize: '0.68rem', color: 'var(--twin-text-muted)' }}>
          <strong>Data Source:</strong> {region.data_source}
        </div>

        {/* Strict Aerospace Scientific Disclaimer */}
        <div className="twin-disclaimer-banner">
          <strong>Scientific Verification Notice:</strong> Spatial linkages illustrate physiological systems for operational visualization. Spacesuit 3D model does NOT contain internal radiological imaging. Whole-body radiation is NOT an individual body-region absorbed dose.
        </div>
      </div>
    </div>
  );
}
