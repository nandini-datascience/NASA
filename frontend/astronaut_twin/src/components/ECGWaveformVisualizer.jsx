import React, { useRef, useEffect, useState } from 'react';
import { Heart, Activity, Play, Pause, RefreshCw, Info } from 'lucide-react';

export default function ECGWaveformVisualizer({ ecgData, onSelectRecording, isLoading }) {
  const canvasRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(true);
  const animationFrameRef = useRef(null);
  const sweepIndexRef = useRef(0);

  const waveform = ecgData?.waveform || [];
  const meta = ecgData?.recording_meta || {};
  const bpm = meta.heart_rate_bpm ?? 72;
  const rhythm = meta.rhythm || 'Normal Sinus Rhythm (NSR)';
  const pr = meta.pr_interval_ms ?? 156;
  const qrs = meta.qrs_duration_ms ?? 84;
  const qtc = meta.qtc_bazett_ms ?? 420;
  const st = meta.st_segment || 'Isoelectric (Nominal)';

  // Draw ECG Rhythm Strip with Continuous Sweep
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    const render = () => {
      // Background Grid
      ctx.fillStyle = '#050a14';
      ctx.fillRect(0, 0, width, height);

      // Standard ECG grid: 25mm/s, 10mm/mV
      ctx.strokeStyle = 'rgba(0, 242, 254, 0.08)';
      ctx.lineWidth = 1;
      const gridSize = 20;

      // Vertical lines
      for (let x = 0; x < width; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      // Horizontal lines
      for (let y = 0; y < height; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // Major grid lines
      ctx.strokeStyle = 'rgba(0, 242, 254, 0.16)';
      for (let x = 0; x < width; x += gridSize * 5) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = 0; y < height; y += gridSize * 5) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // Draw Waveform
      if (waveform.length > 1) {
        const centerY = height * 0.55;
        const scaleY = height * 0.28; // scale mV
        const totalPoints = waveform.length;
        const stepX = width / totalPoints;

        ctx.strokeStyle = '#10b981';
        ctx.lineWidth = 2.2;
        ctx.shadowColor = '#10b981';
        ctx.shadowBlur = 8;
        ctx.lineJoin = 'round';

        ctx.beginPath();
        const currentSweep = isPlaying ? sweepIndexRef.current : totalPoints;

        for (let i = 0; i < currentSweep; i++) {
          const pt = waveform[i];
          const x = i * stepX;
          const y = centerY - pt.voltage_mv * scaleY;
          if (i === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        }
        ctx.stroke();
        ctx.shadowBlur = 0;

        // Sweep Glow Lead Bar
        if (isPlaying && currentSweep < totalPoints) {
          const leadX = currentSweep * stepX;
          ctx.fillStyle = 'rgba(0, 242, 254, 0.4)';
          ctx.fillRect(leadX, 0, 4, height);

          // Advance sweep
          sweepIndexRef.current = (sweepIndexRef.current + 4) % totalPoints;
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
      {/* Top Controls & Metrics Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#10b981', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Heart size={16} color="#ef4444" />
            Lead II Electrocardiogram (ECG) Rhythm Strip
          </span>
          <span className="twin-badge normal">{rhythm}</span>
        </div>

        {/* Recording Selector */}
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
            {ecgData?.available_recordings?.map((rec) => (
              <option key={rec.recording_id} value={rec.recording_id}>
                {rec.title} ({rec.heart_rate_bpm} BPM)
              </option>
            ))}
          </select>

          <button
            type="button"
            className="twin-ctrl-btn"
            style={{ width: '32px', height: '32px' }}
            onClick={() => setIsPlaying(!isPlaying)}
            title={isPlaying ? 'Pause ECG Sweep' : 'Resume ECG Sweep'}
          >
            {isPlaying ? <Pause size={14} /> : <Play size={14} />}
          </button>
        </div>
      </div>

      {/* Main Canvas Waveform Display */}
      <div className="twin-waveform-box">
        <canvas
          ref={canvasRef}
          width={920}
          height={180}
          style={{ width: '100%', height: '180px', display: 'block' }}
        />
      </div>

      {/* Clinical Intervals Dashboard */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.65rem' }}>
        <div style={{ background: 'rgba(8, 16, 32, 0.6)', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid rgba(0, 242, 254, 0.15)' }}>
          <div style={{ fontSize: '0.68rem', color: 'var(--twin-text-secondary)' }}>HEART RATE</div>
          <div style={{ fontFamily: 'var(--twin-font-mono)', fontWeight: 700, fontSize: '1.1rem', color: '#ef4444' }}>
            {bpm} <span className="twin-unit">BPM</span>
          </div>
        </div>

        <div style={{ background: 'rgba(8, 16, 32, 0.6)', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid rgba(0, 242, 254, 0.15)' }}>
          <div style={{ fontSize: '0.68rem', color: 'var(--twin-text-secondary)' }}>PR INTERVAL</div>
          <div style={{ fontFamily: 'var(--twin-font-mono)', fontWeight: 700, fontSize: '1.1rem', color: 'var(--twin-cyan)' }}>
            {pr} <span className="twin-unit">ms (Norm: 120-200)</span>
          </div>
        </div>

        <div style={{ background: 'rgba(8, 16, 32, 0.6)', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid rgba(0, 242, 254, 0.15)' }}>
          <div style={{ fontSize: '0.68rem', color: 'var(--twin-text-secondary)' }}>QRS DURATION</div>
          <div style={{ fontFamily: 'var(--twin-font-mono)', fontWeight: 700, fontSize: '1.1rem', color: '#38bdf8' }}>
            {qrs} <span className="twin-unit">ms (Norm: &lt; 100)</span>
          </div>
        </div>

        <div style={{ background: 'rgba(8, 16, 32, 0.6)', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid rgba(0, 242, 254, 0.15)' }}>
          <div style={{ fontSize: '0.68rem', color: 'var(--twin-text-secondary)' }}>QTc (BAZETT)</div>
          <div style={{ fontFamily: 'var(--twin-font-mono)', fontWeight: 700, fontSize: '1.1rem', color: '#10b981' }}>
            {qtc} <span className="twin-unit">ms (Norm: &lt; 450)</span>
          </div>
        </div>

        <div style={{ background: 'rgba(8, 16, 32, 0.6)', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid rgba(0, 242, 254, 0.15)' }}>
          <div style={{ fontSize: '0.68rem', color: 'var(--twin-text-secondary)' }}>ST SEGMENT</div>
          <div style={{ fontFamily: 'var(--twin-font-mono)', fontWeight: 700, fontSize: '0.9rem', color: '#38bdf8', marginTop: '0.15rem' }}>
            {st}
          </div>
        </div>
      </div>

      {/* Disclaimer */}
      <div className="twin-disclaimer-banner">
        <strong>ECG Verification:</strong> Lead II rhythm strip sampled at 250 Hz. Classified as {ecgData?.data_classification || 'simulated_demonstration_record'}. Mathematical Gaussian synthesis based on NASA-STD-3001 physiological cardiac reference values.
      </div>
    </div>
  );
}
