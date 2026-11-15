import React, { useRef, useEffect, useState } from 'react';
import { Brain, Activity, Play, Pause, BarChart3 } from 'lucide-react';

export default function EEGWaveformVisualizer({ eegData, onSelectRecording, isLoading }) {
  const canvasRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(true);
  const animationFrameRef = useRef(null);
  const sweepIndexRef = useRef(0);

  const waveform = eegData?.waveform || [];
  const meta = eegData?.recording_meta || {};
  const channel = eegData?.channel || 'Fz-Cz Neurotelemetry Vector (128 Hz)';
  const workload = meta.cognitive_workload || 'Nominal Operations (42%)';
  const fatigue = meta.fatigue_index || 'Low (12%)';
  const bands = meta.frequency_bands || {};

  // Draw EEG continuous microvolts waveform
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    const render = () => {
      ctx.fillStyle = '#050a14';
      ctx.fillRect(0, 0, width, height);

      // Grid
      ctx.strokeStyle = 'rgba(139, 92, 246, 0.12)';
      ctx.lineWidth = 1;
      for (let x = 0; x < width; x += 30) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = 0; y < height; y += 25) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // Draw EEG Waveform Trace
      if (waveform.length > 1) {
        const centerY = height * 0.5;
        const scaleY = height * 0.012; // microvolts scale
        const totalPoints = waveform.length;
        const stepX = width / totalPoints;

        ctx.strokeStyle = '#a855f7';
        ctx.lineWidth = 2.0;
        ctx.shadowColor = '#a855f7';
        ctx.shadowBlur = 6;
        ctx.lineJoin = 'round';

        ctx.beginPath();
        const currentSweep = isPlaying ? sweepIndexRef.current : totalPoints;

        for (let i = 0; i < currentSweep; i++) {
          const pt = waveform[i];
          const x = i * stepX;
          const y = centerY - pt.voltage_uv * scaleY;
          if (i === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        }
        ctx.stroke();
        ctx.shadowBlur = 0;

        // Sweep Lead Marker
        if (isPlaying && currentSweep < totalPoints) {
          const leadX = currentSweep * stepX;
          ctx.fillStyle = 'rgba(168, 85, 247, 0.4)';
          ctx.fillRect(leadX, 0, 4, height);

          sweepIndexRef.current = (sweepIndexRef.current + 3) % totalPoints;
        } else if (isPlaying) {
          sweepIndexRef.current = 0;
        }
      }

      if (isPlaying) {
        animationFrameRef.current = requestAnimationFrame(render);
      }
    };

    render();

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [waveform, isPlaying]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
      {/* Top Header & Epoch Selector */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#c084fc', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Brain size={16} color="#c084fc" />
            EEG Continuous Neurotelemetry ({channel})
          </span>
          <span className="twin-badge info">{meta.title || 'Nominal Alertness'}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <select
            style={{
              background: '#0a1428',
              color: 'var(--twin-cyan)',
              border: '1px solid var(--twin-border)',
              borderRadius: '6px',
              padding: '0.35rem 0.65rem',
              fontSize: '0.75rem',
              fontFamily: 'var(--twin-font-mono)'
            }}
            value={meta.recording_id || ''}
            onChange={(e) => onSelectRecording && onSelectRecording(e.target.value)}
          >
            {eegData?.available_recordings?.map((rec) => (
              <option key={rec.recording_id} value={rec.recording_id}>
                {rec.title} ({rec.cognitive_workload})
              </option>
            ))}
          </select>

          <button
            type="button"
            className="twin-ctrl-btn"
            style={{ width: '32px', height: '32px' }}
            onClick={() => setIsPlaying(!isPlaying)}
            title={isPlaying ? 'Pause EEG Trace' : 'Resume EEG Trace'}
          >
            {isPlaying ? <Pause size={14} /> : <Play size={14} />}
          </button>
        </div>
      </div>

      {/* Main Waveform Canvas */}
      <div className="twin-waveform-box" style={{ borderColor: 'rgba(168, 85, 247, 0.35)' }}>
        <canvas
          ref={canvasRef}
          width={920}
          height={160}
          style={{ width: '100%', height: '160px', display: 'block' }}
        />
      </div>

      {/* Frequency Band Spectral Power Analysis */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '1rem', alignItems: 'start' }}>
        {/* Band Bars */}
        <div style={{ background: 'rgba(8, 16, 32, 0.6)', padding: '0.75rem', borderRadius: '8px', border: '1px solid rgba(168, 85, 247, 0.2)' }}>
          <div style={{ fontSize: '0.74rem', fontFamily: 'var(--twin-font-mono)', color: '#c084fc', marginBottom: '0.5rem', textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <BarChart3 size={14} />
            <span>Frequency Band Power Spectral Distribution</span>
          </div>

          {/* Delta */}
          <div className="twin-band-row">
            <span className="twin-band-label">Delta (0.5-4 Hz)</span>
            <div className="twin-band-bar-outer">
              <div className="twin-band-bar-inner" style={{ width: `${bands.delta?.power_pct || 12}%`, background: '#3b82f6' }} />
            </div>
            <span className="twin-band-val">{bands.delta?.power_pct || 12}%</span>
          </div>

          {/* Theta */}
          <div className="twin-band-row">
            <span className="twin-band-label">Theta (4-8 Hz)</span>
            <div className="twin-band-bar-outer">
              <div className="twin-band-bar-inner" style={{ width: `${bands.theta?.power_pct || 18}%`, background: '#06b6d4' }} />
            </div>
            <span className="twin-band-val">{bands.theta?.power_pct || 18}%</span>
          </div>

          {/* Alpha */}
          <div className="twin-band-row">
            <span className="twin-band-label">Alpha (8-13 Hz)</span>
            <div className="twin-band-bar-outer">
              <div className="twin-band-bar-inner" style={{ width: `${bands.alpha?.power_pct || 38}%`, background: '#10b981' }} />
            </div>
            <span className="twin-band-val">{bands.alpha?.power_pct || 38}%</span>
          </div>

          {/* Beta */}
          <div className="twin-band-row">
            <span className="twin-band-label">Beta (13-30 Hz)</span>
            <div className="twin-band-bar-outer">
              <div className="twin-band-bar-inner" style={{ width: `${bands.beta?.power_pct || 26}%`, background: '#f59e0b' }} />
            </div>
            <span className="twin-band-val">{bands.beta?.power_pct || 26}%</span>
          </div>

          {/* Gamma */}
          <div className="twin-band-row">
            <span className="twin-band-label">Gamma (30-45 Hz)</span>
            <div className="twin-band-bar-outer">
              <div className="twin-band-bar-inner" style={{ width: `${bands.gamma?.power_pct || 6}%`, background: '#ef4444' }} />
            </div>
            <span className="twin-band-val">{bands.gamma?.power_pct || 6}%</span>
          </div>
        </div>

        {/* Cognitive Index Metrics */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
          <div style={{ background: 'rgba(8, 16, 32, 0.6)', padding: '0.65rem 0.85rem', borderRadius: '8px', border: '1px solid rgba(0, 242, 254, 0.15)' }}>
            <div style={{ fontSize: '0.68rem', color: 'var(--twin-text-secondary)' }}>COGNITIVE WORKLOAD ESTIMATE</div>
            <div style={{ fontFamily: 'var(--twin-font-mono)', fontWeight: 700, fontSize: '1.05rem', color: 'var(--twin-cyan)', marginTop: '0.15rem' }}>
              {workload}
            </div>
          </div>

          <div style={{ background: 'rgba(8, 16, 32, 0.6)', padding: '0.65rem 0.85rem', borderRadius: '8px', border: '1px solid rgba(0, 242, 254, 0.15)' }}>
            <div style={{ fontSize: '0.68rem', color: 'var(--twin-text-secondary)' }}>FATIGUE / SLEEPINESS INDEX</div>
            <div style={{ fontFamily: 'var(--twin-font-mono)', fontWeight: 700, fontSize: '1.05rem', color: '#10b981', marginTop: '0.15rem' }}>
              {fatigue}
            </div>
          </div>
        </div>
      </div>

      {/* Scientific Notice */}
      <div className="twin-disclaimer-banner">
        <strong>Neurotelemetry Label:</strong> Multi-band EEG waveform is classified as {eegData?.data_classification || 'simulated_demonstration_record'}. Synthesizes frontal-central spatial vector for cognitive workload estimation during spaceflight tasks.
      </div>
    </div>
  );
}
