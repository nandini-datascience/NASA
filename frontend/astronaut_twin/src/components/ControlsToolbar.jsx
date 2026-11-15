import React from 'react';
import {
  RotateCw,
  Play,
  Pause,
  ZoomIn,
  ZoomOut,
  Compass,
  Radio,
  Layers,
  Eye,
  Crosshair
} from 'lucide-react';

export default function ControlsToolbar({
  autoRotate,
  onToggleAutoRotate,
  onResetCamera,
  onZoomIn,
  onZoomOut,
  viewPreset,
  onChangeViewPreset,
  wireframe,
  onToggleWireframe,
  showAura,
  onToggleAura,
  selectedRegion,
  onSelectRegion
}) {
  // All 9 required body regions
  const regions = [
    { id: 'head', label: 'Head / CNS' },
    { id: 'chest', label: 'Chest / DCM' },
    { id: 'heart', label: 'Heart / ECG' },
    { id: 'lungs', label: 'Lungs / SpO2' },
    { id: 'abdomen', label: 'Abdomen' },
    { id: 'left_arm', label: 'Left Arm' },
    { id: 'right_arm', label: 'Right Arm' },
    { id: 'left_leg', label: 'Left Leg' },
    { id: 'right_leg', label: 'Right Leg' }
  ];

  const views = [
    { id: 'front', label: 'Front' },
    { id: 'back', label: 'Back' },
    { id: 'left', label: 'Left Side' },
    { id: 'right', label: 'Right Side' }
  ];

  return (
    <>
      {/* 9 Selectable Body Region Pills on Upper HUD */}
      <div className="twin-region-pillbar">
        {regions.map((reg) => (
          <button
            key={reg.id}
            type="button"
            className={`twin-region-pill ${selectedRegion === reg.id ? 'active' : ''}`}
            onClick={() => onSelectRegion(reg.id)}
          >
            {reg.label}
          </button>
        ))}
        {selectedRegion && (
          <button
            type="button"
            className="twin-region-pill"
            style={{ color: 'var(--twin-cyan)', borderColor: 'var(--twin-cyan)', fontWeight: 700 }}
            onClick={() => onSelectRegion(null)}
          >
            Full View
          </button>
        )}
      </div>

      {/* Floating 3D Toolbar with Views & Camera Controls */}
      <div className="twin-controls-toolbar">
        {/* Camera Views Selector Pills */}
        <div style={{ display: 'flex', gap: '0.25rem', paddingRight: '0.4rem', borderRight: '1px solid rgba(0, 242, 254, 0.25)' }}>
          {views.map((v) => (
            <button
              key={v.id}
              type="button"
              className={`twin-region-pill ${viewPreset === v.id ? 'active' : ''}`}
              style={{ padding: '0.2rem 0.55rem', fontSize: '0.68rem' }}
              onClick={() => onChangeViewPreset(v.id)}
            >
              {v.label}
            </button>
          ))}
        </div>

        {/* 360 Auto Rotate Toggle */}
        <button
          type="button"
          className={`twin-ctrl-btn ${autoRotate ? 'active' : ''}`}
          onClick={onToggleAutoRotate}
          title={autoRotate ? 'Pause 360° Auto-Rotation' : 'Start 360° Auto-Rotation'}
          aria-label="Toggle Auto-Rotation"
        >
          {autoRotate ? <Pause size={15} /> : <Play size={15} />}
        </button>

        {/* Reset Camera View Button */}
        <button
          type="button"
          className="twin-ctrl-btn"
          onClick={onResetCamera}
          title="Reset Camera Position (Fit Full Astronaut from Helmet to Boots)"
          aria-label="Reset Camera"
        >
          <Compass size={15} />
        </button>

        {/* Zoom In Button */}
        <button
          type="button"
          className="twin-ctrl-btn"
          onClick={onZoomIn}
          title="Zoom In"
          aria-label="Zoom In"
        >
          <ZoomIn size={15} />
        </button>

        {/* Zoom Out Button */}
        <button
          type="button"
          className="twin-ctrl-btn"
          onClick={onZoomOut}
          title="Zoom Out"
          aria-label="Zoom Out"
        >
          <ZoomOut size={15} />
        </button>

        {/* Radiation Field Aura Toggle */}
        <button
          type="button"
          className={`twin-ctrl-btn ${showAura ? 'active' : ''}`}
          onClick={onToggleAura}
          title={showAura ? 'Hide Radiation Field Aura' : 'Show Radiation Field Aura'}
          aria-label="Toggle Radiation Aura"
        >
          <Radio size={15} />
        </button>

        {/* Wireframe / Hologram Mode */}
        <button
          type="button"
          className={`twin-ctrl-btn ${wireframe ? 'active' : ''}`}
          onClick={onToggleWireframe}
          title={wireframe ? 'Switch to Solid Spacesuit Material' : 'Switch to Diagnostic Wireframe'}
          aria-label="Toggle Wireframe Mode"
        >
          <Layers size={15} />
        </button>
      </div>
    </>
  );
}
