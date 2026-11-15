import React, { useState, useEffect, useRef } from 'react';
import {
  Activity,
  Heart,
  Brain,
  Radio,
  User,
  Crosshair,
  TrendingUp,
  Database,
  RotateCw,
  RefreshCw,
  Sparkles,
  AlertCircle
} from 'lucide-react';

import AstronautCanvas from './components/AstronautCanvas';
import ControlsToolbar from './components/ControlsToolbar';
import AstronautProfileCard from './components/AstronautProfileCard';
import VitalsMonitorCard from './components/VitalsMonitorCard';
import RadiationMonitorCard from './components/RadiationMonitorCard';
import BodyRegionInfoPanel from './components/BodyRegionInfoPanel';
import ECGWaveformVisualizer from './components/ECGWaveformVisualizer';
import EEGWaveformVisualizer from './components/EEGWaveformVisualizer';
import HealthTrendsCharts from './components/HealthTrendsCharts';
import HistoricalDataExplorer from './components/HistoricalDataExplorer';

import { TwinAPI } from './services/api';

export default function AstronautTwinApp() {
  // 3D Visualizer State - Default to null so FULL ASTRONAUT from helmet to boots is visible on load
  const [selectedRegion, setSelectedRegion] = useState(null);
  const [viewPreset, setViewPreset] = useState('front');
  const [autoRotate, setAutoRotate] = useState(false);
  const [wireframe, setWireframe] = useState(false);
  const [showAura, setShowAura] = useState(true);
  const [resetTrigger, setResetTrigger] = useState(0);

  // Deck Tabs
  const [activeBottomTab, setActiveBottomTab] = useState('ecg'); // 'ecg', 'eeg', 'trends', 'explorer'

  // Telemetry API State
  const [radiationData, setRadiationData] = useState(null);
  const [healthData, setHealthData] = useState(null);
  const [profileData, setProfileData] = useState(null);
  const [bodyRegionsData, setBodyRegionsData] = useState(null);
  const [ecgData, setEcgData] = useState(null);
  const [eegData, setEegData] = useState(null);
  const [healthHistory, setHealthHistory] = useState({ records: [] });
  const [radiationHistory, setRadiationHistory] = useState({ records: [] });
  const [alertsList, setAlertsList] = useState({ alerts: [] });

  const [isLoading, setIsLoading] = useState(true);
  const [lastSyncTime, setLastSyncTime] = useState(new Date());

  const controlsRef = useRef(null);

  // Fetch initial telemetry
  const loadAllTelemetry = async () => {
    try {
      const [rad, health, prof, regions, ecg, eeg, hHist, rHist, alerts] = await Promise.all([
        TwinAPI.getRadiationLatest(),
        TwinAPI.getHealthLatest('AST-01'),
        TwinAPI.getAstronautProfile('AST-01'),
        TwinAPI.getBodyRegions('AST-01'),
        TwinAPI.getECGData('AST-01'),
        TwinAPI.getEEGData('AST-01'),
        TwinAPI.getHealthHistory('AST-01', 25),
        TwinAPI.getRadiationHistory(25),
        TwinAPI.getAlerts(10)
      ]);

      if (rad) setRadiationData(rad);
      if (health) setHealthData(health);
      if (prof) setProfileData(prof);
      if (regions) setBodyRegionsData(regions);
      if (ecg) setEcgData(ecg);
      if (eeg) setEegData(eeg);
      if (hHist) setHealthHistory(hHist);
      if (rHist) setRadiationHistory(rHist);
      if (alerts) setAlertsList(alerts);

      setLastSyncTime(new Date());
    } catch (err) {
      console.error('Error fetching twin telemetry:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadAllTelemetry();

    // Auto-polling interval: 10 seconds
    const interval = setInterval(() => {
      loadAllTelemetry();
    }, 10000);

    return () => clearInterval(interval);
  }, []);

  // Handler for body region selection
  const handleSelectRegion = (regionId) => {
    setSelectedRegion(regionId);
    // Auto-switch bottom tab if heart or head is selected
    if (regionId === 'heart') {
      setActiveBottomTab('ecg');
    } else if (regionId === 'head') {
      setActiveBottomTab('eeg');
    } else if (regionId === 'chest') {
      setActiveBottomTab('trends');
    }
  };

  // Reset Camera
  const handleResetCamera = () => {
    setSelectedRegion(null);
    setViewPreset('front');
    setResetTrigger((prev) => prev + 1);
    if (controlsRef.current) {
      controlsRef.current.reset();
      controlsRef.current.target.set(0, 0, 0);
    }
  };

  // Zoom In / Out
  const handleZoomIn = () => {
    if (controlsRef.current && controlsRef.current.object) {
      const cam = controlsRef.current.object;
      cam.position.multiplyScalar(0.85);
    }
  };

  const handleZoomOut = () => {
    if (controlsRef.current && controlsRef.current.object) {
      const cam = controlsRef.current.object;
      cam.position.multiplyScalar(1.18);
    }
  };

  // Fetch specific ECG recording
  const handleSelectECGRecording = async (recId) => {
    const res = await TwinAPI.getECGData('AST-01', recId);
    if (res) setEcgData(res);
  };

  // Fetch specific EEG recording
  const handleSelectEEGRecording = async (recId) => {
    const res = await TwinAPI.getEEGData('AST-01', recId);
    if (res) setEegData(res);
  };

  const radiationIntensity = (radiationData?.absorbed_dose_rate ?? 1.92) / 20.0;

  return (
    <div className="twin-container">
      {/* Top Banner / Digital Twin System Status */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '0.75rem',
          background: 'linear-gradient(135deg, rgba(14, 23, 46, 0.9) 0%, rgba(20, 32, 64, 0.85) 100%)',
          border: '1px solid var(--twin-border)',
          borderRadius: '10px',
          padding: '0.75rem 1.25rem',
          boxShadow: '0 4px 20px rgba(0, 0, 0, 0.4)'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div
            style={{
              width: '38px',
              height: '38px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, #00f2fe 0%, #4facfe 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#060a14',
              boxShadow: '0 0 16px rgba(0, 242, 254, 0.5)'
            }}
          >
            <Sparkles size={20} />
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: '1.05rem', letterSpacing: '0.04em', color: '#fff' }}>
              3D ASTRONAUT DIGITAL TWIN • ASTRA CARE
            </div>
            <div style={{ fontSize: '0.74rem', color: 'var(--twin-cyan)', fontFamily: 'var(--twin-font-mono)' }}>
              xEMU EXPLORATION SPACESUIT • REAL-TIME PHYSIOLOGICAL & DOSIMETRY MODEL
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontFamily: 'var(--twin-font-mono)', fontSize: '0.74rem', color: 'var(--twin-text-secondary)' }}>
            <span className="twin-live-dot" />
            <span>SYNC: {lastSyncTime.toLocaleTimeString()} UTC</span>
          </div>

          <button
            type="button"
            className="twin-region-pill"
            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.35rem 0.75rem' }}
            onClick={loadAllTelemetry}
            title="Force refresh telemetry from FastAPI backend"
          >
            <RefreshCw size={12} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* ==============================================================
          MAIN 3-COLUMN LAYOUT:
          LEFT: Profile, Health Vitals, Radiation Dosimetry
          CENTRE: Large Interactive 3D Astronaut Canvas & HUD Controls
          RIGHT: Selected Body Region Inspector & Telemetry
          ============================================================== */}
      <div className="twin-layout-main">
        {/* LEFT COLUMN: Mission & Vitals */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <AstronautProfileCard profile={profileData} />
          <VitalsMonitorCard healthData={healthData} />
          <RadiationMonitorCard
            radiationData={radiationData}
            showAura={showAura}
            onToggleAura={() => setShowAura(!showAura)}
          />
        </div>

        {/* CENTRE COLUMN: 3D Astronaut Digital Twin Canvas */}
        <div className="twin-canvas-wrapper">
          {/* Canvas Floating Top HUD */}
          <div className="twin-canvas-hud-header">
            <div className="twin-hud-badge">
              <span className="twin-live-dot" />
              <span>3D DIGITAL TWIN • ORBITAL ZERO-G</span>
            </div>

            <div className="twin-hud-badge">
              <span>REGION: {selectedRegion ? selectedRegion.toUpperCase() : 'FULL BODY (ALL)'}</span>
            </div>
          </div>

          {/* Interactive Controls Toolbar & Quick Region Pills */}
          <ControlsToolbar
            autoRotate={autoRotate}
            onToggleAutoRotate={() => setAutoRotate(!autoRotate)}
            onResetCamera={handleResetCamera}
            onZoomIn={handleZoomIn}
            onZoomOut={handleZoomOut}
            viewPreset={viewPreset}
            onChangeViewPreset={setViewPreset}
            wireframe={wireframe}
            onToggleWireframe={() => setWireframe(!wireframe)}
            showAura={showAura}
            onToggleAura={() => setShowAura(!showAura)}
            selectedRegion={selectedRegion}
            onSelectRegion={handleSelectRegion}
          />

          {/* WebGL Canvas */}
          <AstronautCanvas
            selectedRegion={selectedRegion}
            onSelectRegion={handleSelectRegion}
            autoRotate={autoRotate}
            wireframe={wireframe}
            showAura={showAura}
            radiationIntensity={radiationIntensity}
            resetTrigger={resetTrigger}
            viewPreset={viewPreset}
            controlsRef={controlsRef}
          />
        </div>

        {/* RIGHT COLUMN: Selected Body Region Inspector */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <BodyRegionInfoPanel
            selectedRegion={selectedRegion}
            bodyRegionsData={bodyRegionsData}
            onSelectWaveformTab={(tab) => setActiveBottomTab(tab)}
          />
        </div>
      </div>

      {/* ==============================================================
          BOTTOM MULTI-TAB AEROSPACE DECK:
          1. ECG Waveform Rhythm Strip
          2. EEG Brainwave Frequency Spectrum
          3. Historical Health Trends (HR, SpO2, Temp)
          4. Historical Data Explorer (All measurements, filter & compare)
          ============================================================== */}
      <div className="twin-card">
        {/* Navigation Tabs */}
        <div className="twin-tabs-nav">
          <button
            type="button"
            className={`twin-tab-btn ${activeBottomTab === 'ecg' ? 'active' : ''}`}
            onClick={() => setActiveBottomTab('ecg')}
          >
            <Heart size={15} />
            <span>ECG Cardiac Rhythm Strip</span>
          </button>

          <button
            type="button"
            className={`twin-tab-btn ${activeBottomTab === 'eeg' ? 'active' : ''}`}
            onClick={() => setActiveBottomTab('eeg')}
          >
            <Brain size={15} />
            <span>EEG Brainwave Spectral Analysis</span>
          </button>

          <button
            type="button"
            className={`twin-tab-btn ${activeBottomTab === 'trends' ? 'active' : ''}`}
            onClick={() => setActiveBottomTab('trends')}
          >
            <TrendingUp size={15} />
            <span>Historical Health Trends (HR, SpO2, Temp)</span>
          </button>

          <button
            type="button"
            className={`twin-tab-btn ${activeBottomTab === 'explorer' ? 'active' : ''}`}
            onClick={() => setActiveBottomTab('explorer')}
          >
            <Database size={15} />
            <span>Historical Telemetry Explorer</span>
          </button>
        </div>

        {/* Tab Content Panes */}
        <div className="twin-card-body">
          {activeBottomTab === 'ecg' && (
            <ECGWaveformVisualizer
              ecgData={ecgData}
              onSelectRecording={handleSelectECGRecording}
              isLoading={isLoading}
            />
          )}

          {activeBottomTab === 'eeg' && (
            <EEGWaveformVisualizer
              eegData={eegData}
              onSelectRecording={handleSelectEEGRecording}
              isLoading={isLoading}
            />
          )}

          {activeBottomTab === 'trends' && (
            <HealthTrendsCharts
              healthHistory={healthHistory}
              radiationHistory={radiationHistory}
            />
          )}

          {activeBottomTab === 'explorer' && (
            <HistoricalDataExplorer
              healthHistory={healthHistory}
              radiationHistory={radiationHistory}
              alertsList={alertsList}
            />
          )}
        </div>
      </div>
    </div>
  );
}
