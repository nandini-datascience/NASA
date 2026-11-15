import React from 'react';
import { Radio, ShieldAlert, Zap, Orbit, AlertCircle } from 'lucide-react';

export default function RadiationMonitorCard({ radiationData, showAura, onToggleAura }) {
  const rad = radiationData || {};
  const doseRate = rad.absorbed_dose_rate ?? 1.92;
  const eqRate = rad.dose_equivalent_rate ?? 4.03;
  const cumDose = rad.cumulative_dose_ugy ?? 6542.8;
  const flux = rad.particle_flux ?? 2.48;
  const alt = rad.altitude_km ?? 408.4;
  const cond = rad.condition || 'NOMINAL';
  const condLabel = rad.condition_label || 'NOMINAL BACKGROUND (LEO)';
  const instrument = rad.instrument_id || 'DosTel1';
  const source = rad.data_source || 'NASA RadLab Repository';

  return (
    <div className="twin-card">
      <div className="twin-card-header">
        <div className="twin-card-title">
          <Radio size={16} />
          <span>Space Radiation Dosimetry</span>
        </div>
        <span className={`twin-badge ${cond === 'NOMINAL' ? 'normal' : cond === 'ADVISORY' ? 'advisory' : 'critical'}`}>
          {cond}
        </span>
      </div>

      <div className="twin-card-body">
        {/* Primary Absorbed Dose Rate */}
        <div style={{ background: 'rgba(4, 9, 22, 0.7)', border: '1px solid rgba(0, 242, 254, 0.2)', borderRadius: '8px', padding: '0.75rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--twin-text-secondary)', textTransform: 'uppercase' }}>
              Absorbed Dose Rate (Gy)
            </span>
            <span style={{ fontSize: '0.7rem', color: 'var(--twin-cyan)', fontFamily: 'var(--twin-font-mono)' }}>
              {instrument}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.4rem', marginTop: '0.2rem' }}>
            <span style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--twin-cyan)', fontFamily: 'var(--twin-font-mono)' }}>
              {doseRate}
            </span>
            <span style={{ fontSize: '0.82rem', color: 'var(--twin-text-muted)' }}>µGy/hr</span>
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--twin-text-secondary)', marginTop: '0.15rem' }}>
            {condLabel}
          </div>
        </div>

        {/* Telemetry Breakdown */}
        <div>
          <div className="twin-telem-row">
            <span className="twin-telem-label">Dose Equivalent Rate (Sv)</span>
            <span className="twin-telem-val" style={{ color: '#8b5cf6' }}>
              {eqRate} <span className="twin-unit">µSv/hr</span>
            </span>
          </div>
          <div className="twin-telem-row">
            <span className="twin-telem-label">Mission Cumulative Dose</span>
            <span className="twin-telem-val" style={{ color: '#10b981' }}>
              {cumDose} <span className="twin-unit">µGy ({(cumDose / 1000).toFixed(2)} mGy)</span>
            </span>
          </div>
          <div className="twin-telem-row">
            <span className="twin-telem-label">Particle Flux</span>
            <span className="twin-telem-val">
              {flux} <span className="twin-unit">p/cm²·s</span>
            </span>
          </div>
          <div className="twin-telem-row">
            <span className="twin-telem-label">Altitude & Orbit</span>
            <span className="twin-telem-val">
              ~{alt} km <span className="twin-unit">(LEO 51.6°)</span>
            </span>
          </div>
        </div>

        {/* Interactive Aura Toggle Pill */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(10, 18, 38, 0.6)', padding: '0.5rem 0.75rem', borderRadius: '6px' }}>
          <span style={{ fontSize: '0.73rem', color: 'var(--twin-text-secondary)' }}>
            3D Radiation Field Aura
          </span>
          <button
            type="button"
            className={`twin-region-pill ${showAura ? 'active' : ''}`}
            onClick={onToggleAura}
            style={{ padding: '0.2rem 0.6rem', fontSize: '0.68rem' }}
          >
            {showAura ? 'Aura: ACTIVE' : 'Aura: OFF'}
          </button>
        </div>

        {/* Scientific Dosimetry Disclaimer */}
        <div className="twin-disclaimer-banner">
          <strong>Dosimetry Distinction:</strong> Scientific telemetry from {source}. Distinguishes absorbed physical dose (Gy) from biological equivalent dose (Sv). Whole-body reading is not individual anatomical organ dose.
        </div>
      </div>
    </div>
  );
}
