import React from 'react';
import { User, ShieldCheck, BatteryCharging, Gauge, Wind, Compass } from 'lucide-react';

export default function AstronautProfileCard({ profile }) {
  const astronaut = profile?.astronaut || {
    astronaut_id: 'AST-01',
    name: 'Dr. Sarah Vance',
    callsign: 'Astra-Lead',
    role: 'Commander / Biomedical Lead',
    mission: 'Expedition 71 / Gateway Shakedown',
    spacecraft: 'ISS (Low Earth Orbit)',
    orbit: { altitude_km: 408.4 },
    flight_experience: { mission_day: 142, cumulative_spaceflight_days: 318, eva_sorties_count: 6, cumulative_eva_hours: 38.5 },
    spacesuit: {
      model: 'xEMU Mk III',
      pressure_kpa: 29.6,
      primary_o2_reserve_pct: 94.2,
      battery_soc_pct: 88.5,
      co2_scrubber_efficiency_pct: 99.4
    },
    medical_status: { clearance: 'FLIGHT QUALIFIED / EVA CLEARED', overall_readiness: 'NOMINAL' }
  };

  const suit = astronaut.spacesuit || {};
  const exp = astronaut.flight_experience || {};

  return (
    <div className="twin-card">
      <div className="twin-card-header">
        <div className="twin-card-title">
          <User size={16} />
          <span>Astronaut Profile</span>
        </div>
        <span className="twin-badge normal">{astronaut.medical_status?.overall_readiness || 'NOMINAL'}</span>
      </div>

      <div className="twin-card-body">
        {/* Bio Header */}
        <div style={{ display: 'flex', gap: '0.85rem', alignItems: 'center' }}>
          <div
            style={{
              width: '46px',
              height: '46px',
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #00f2fe 0%, #4facfe 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#060a14',
              fontWeight: 800,
              fontSize: '1.1rem',
              boxShadow: '0 0 15px rgba(0, 242, 254, 0.4)'
            }}
          >
            {astronaut.astronaut_id?.slice(0, 3) || 'AST'}
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.98rem', color: '#fff' }}>
              {astronaut.name}
            </div>
            <div style={{ fontSize: '0.74rem', color: 'var(--twin-cyan)', fontFamily: 'var(--twin-font-mono)' }}>
              {astronaut.astronaut_id} • CALLSIGN: "{astronaut.callsign}"
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--twin-text-secondary)' }}>
              {astronaut.role}
            </div>
          </div>
        </div>

        {/* Mission Telemetry Rows */}
        <div style={{ marginTop: '0.25rem' }}>
          <div className="twin-telem-row">
            <span className="twin-telem-label">Mission Context</span>
            <span className="twin-telem-val cyan">{astronaut.mission}</span>
          </div>
          <div className="twin-telem-row">
            <span className="twin-telem-label">Station / Orbit</span>
            <span className="twin-telem-val">{astronaut.spacecraft} (~{astronaut.orbit?.altitude_km || 408} km)</span>
          </div>
          <div className="twin-telem-row">
            <span className="twin-telem-label">Mission Elapsed Day</span>
            <span className="twin-telem-val">Day {exp.mission_day || 142} <span className="twin-unit">({exp.cumulative_spaceflight_days || 318}d career)</span></span>
          </div>
          <div className="twin-telem-row">
            <span className="twin-telem-label">EVA Experience</span>
            <span className="twin-telem-val">{exp.eva_sorties_count || 6} Sorties <span className="twin-unit">({exp.cumulative_eva_hours || 38.5} hrs)</span></span>
          </div>
        </div>

        {/* Spacesuit Telemetry Deck */}
        <div style={{ marginTop: '0.5rem', background: 'rgba(6, 12, 26, 0.65)', border: '1px solid rgba(0, 242, 254, 0.15)', borderRadius: '8px', padding: '0.65rem' }}>
          <div style={{ fontSize: '0.72rem', fontFamily: 'var(--twin-font-mono)', color: 'var(--twin-text-muted)', marginBottom: '0.4rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Spacesuit (xEMU Mk III) Life Support
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
            <div>
              <div style={{ fontSize: '0.68rem', color: 'var(--twin-text-secondary)' }}>O2 Reserves</div>
              <div style={{ fontFamily: 'var(--twin-font-mono)', fontWeight: 700, color: '#10b981', fontSize: '0.9rem' }}>
                {suit.primary_o2_reserve_pct || 94.2}%
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.68rem', color: 'var(--twin-text-secondary)' }}>Suit Pressure</div>
              <div style={{ fontFamily: 'var(--twin-font-mono)', fontWeight: 700, color: 'var(--twin-cyan)', fontSize: '0.9rem' }}>
                {suit.pressure_kpa || 29.6} <span className="twin-unit">kPa</span>
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.68rem', color: 'var(--twin-text-secondary)' }}>Battery State</div>
              <div style={{ fontFamily: 'var(--twin-font-mono)', fontWeight: 700, color: '#38bdf8', fontSize: '0.9rem' }}>
                {suit.battery_soc_pct || 88.5}%
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.68rem', color: 'var(--twin-text-secondary)' }}>CO2 Scrubber</div>
              <div style={{ fontFamily: 'var(--twin-font-mono)', fontWeight: 700, color: '#10b981', fontSize: '0.9rem' }}>
                {suit.co2_scrubber_efficiency_pct || 99.4}%
              </div>
            </div>
          </div>
        </div>

        {/* Non-diagnostic notice */}
        <div className="twin-disclaimer-banner">
          <strong>Flight Surgeon Status:</strong> {astronaut.medical_status?.clearance || 'FLIGHT QUALIFIED'}. Biometric telemetry validated under NASA-STD-3001.
        </div>
      </div>
    </div>
  );
}
