import React from 'react';
import { Activity, Heart, Droplets, Thermometer, Wind } from 'lucide-react';

export default function VitalsMonitorCard({ healthData }) {
  const hr = healthData?.heart_rate?.value ?? 72;
  const sysBp = healthData?.blood_pressure?.systolic ?? 118;
  const diaBp = healthData?.blood_pressure?.diastolic ?? 76;
  const spo2 = healthData?.oxygen_saturation?.value ?? 98.4;
  const tempC = healthData?.body_temperature?.value ?? 36.8;
  const respRate = healthData?.respiratory_rate?.value ?? 14;
  const status = healthData?.overall_status || 'NOMINAL';
  const dataClass = healthData?.data_classification || 'simulated_demo';

  return (
    <div className="twin-card">
      <div className="twin-card-header">
        <div className="twin-card-title">
          <Activity size={16} />
          <span>Biometric Vitals</span>
        </div>
        <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
          <span className="twin-badge info">{dataClass}</span>
          <span className={`twin-badge ${status === 'NOMINAL' ? 'normal' : 'critical'}`}>
            {status}
          </span>
        </div>
      </div>

      <div className="twin-card-body">
        {/* Heart Rate & Pulse */}
        <div className="twin-telem-row">
          <span className="twin-telem-label" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Heart size={14} color="#ef4444" className="heart-pulse-icon" />
            Heart Rate
          </span>
          <span className="twin-telem-val">
            <span style={{ fontSize: '1.25rem', color: '#ef4444', fontWeight: 800 }}>{hr}</span>
            <span className="twin-unit">BPM</span>
          </span>
        </div>

        {/* Blood Pressure */}
        <div className="twin-telem-row">
          <span className="twin-telem-label" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Droplets size={14} color="#38bdf8" />
            Blood Pressure
          </span>
          <span className="twin-telem-val">
            <span style={{ fontSize: '1.1rem', color: '#38bdf8' }}>{sysBp}/{diaBp}</span>
            <span className="twin-unit">mmHg</span>
          </span>
        </div>

        {/* Blood Oxygen Saturation */}
        <div className="twin-telem-row">
          <span className="twin-telem-label" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Activity size={14} color="#8b5cf6" />
            Oxygen Saturation
          </span>
          <span className="twin-telem-val">
            <span style={{ fontSize: '1.1rem', color: '#8b5cf6' }}>{spo2}</span>
            <span className="twin-unit">% SpO2</span>
          </span>
        </div>

        {/* Body Temperature */}
        <div className="twin-telem-row">
          <span className="twin-telem-label" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Thermometer size={14} color="#10b981" />
            Core Body Temp
          </span>
          <span className="twin-telem-val">
            <span style={{ fontSize: '1.1rem', color: '#10b981' }}>{tempC}</span>
            <span className="twin-unit">°C</span>
          </span>
        </div>

        {/* Respiratory Rate */}
        <div className="twin-telem-row">
          <span className="twin-telem-label" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Wind size={14} color="var(--twin-cyan)" />
            Respiration Rate
          </span>
          <span className="twin-telem-val">
            <span style={{ fontSize: '1.1rem', color: 'var(--twin-cyan)' }}>{respRate}</span>
            <span className="twin-unit">br/min</span>
          </span>
        </div>

        <div style={{ fontSize: '0.68rem', color: 'var(--twin-text-muted)', textAlign: 'right' }}>
          Device: {healthData?.source_device || 'Wearable Crew Biomonitor'}
        </div>
      </div>
    </div>
  );
}
