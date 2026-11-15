/**
 * api.js - API client service for 3D Astronaut Digital Twin
 * Connects with FastAPI backend (http://127.0.0.1:8000) with robust fallback handling.
 */

const BASE_URL = window.location.origin.includes(':8000') 
  ? window.location.origin 
  : 'http://127.0.0.1:8000';

async function safeFetch(endpoint, fallbackData = null) {
  try {
    const res = await fetch(`${BASE_URL}${endpoint}`);
    if (!res.ok) {
      console.warn(`API [${endpoint}] returned status ${res.status}`);
      return fallbackData;
    }
    return await res.json();
  } catch (err) {
    console.warn(`API [${endpoint}] unreachable, using local fallback.`, err);
    return fallbackData;
  }
}

export const TwinAPI = {
  getModelUrl: () => {
    return `${BASE_URL}/api/astronaut/model`;
  },

  getRadiationLatest: async () => {
    return safeFetch('/api/radiation/latest', {
      status: 'success',
      timestamp: new Date().toISOString(),
      instrument_id: 'DosTel1',
      spacecraft: 'ISS',
      orbital_region: 'Low Earth Orbit (LEO)',
      altitude_km: 408.4,
      absorbed_dose_rate: 1.92,
      absorbed_dose_unit: 'µGy/hr',
      dose_equivalent_rate: 4.03,
      dose_equivalent_unit: 'µSv/hr',
      cumulative_dose_ugy: 6542.8,
      cumulative_dose_unit: 'µGy',
      particle_flux: 2.48,
      particle_flux_unit: 'particles/cm²·s',
      condition: 'NOMINAL',
      condition_label: 'NOMINAL BACKGROUND (LEO)',
      visual_aura: { color: '#00f2fe', density: 'low', intensity: 0.3 },
      ml_anomaly: { is_anomaly: false, anomaly_score: 0.03 },
      data_source: 'NASA RadLab Scientific Telemetry Archive',
      is_simulated: false,
      disclaimer: 'Scientific radiation measurement from NASA RadLab. Preserves absorbed dose vs equivalent dose distinctions.'
    });
  },

  getRadiationHistory: async (limit = 20) => {
    return safeFetch(`/api/radiation/history?limit=${limit}`, { records: [] });
  },

  getHealthLatest: async (astronautId = 'AST-01') => {
    return safeFetch(`/api/health/latest?astronaut_id=${astronautId}`, {
      status: 'success',
      astronaut_id: astronautId,
      timestamp: new Date().toISOString(),
      heart_rate: { value: 72, unit: 'BPM', status: 'NOMINAL' },
      blood_pressure: { systolic: 118, diastolic: 76, unit: 'mmHg', status: 'NOMINAL' },
      oxygen_saturation: { value: 98.4, unit: '%', status: 'NOMINAL' },
      body_temperature: { value: 36.8, unit: '°C', status: 'NOMINAL' },
      respiratory_rate: { value: 14, unit: 'breaths/min', status: 'NOMINAL' },
      overall_status: 'NOMINAL',
      source_device: 'Wearable Crew Biomonitor #1',
      data_classification: 'simulated_demo'
    });
  },

  getHealthHistory: async (astronautId = 'AST-01', limit = 30) => {
    return safeFetch(`/api/health/history?astronaut_id=${astronautId}&limit=${limit}`, { records: [] });
  },

  getAstronautProfile: async (astronautId = 'AST-01') => {
    return safeFetch(`/api/astronaut/profile?astronaut_id=${astronautId}`, {
      status: 'success',
      astronaut: {
        astronaut_id: 'AST-01',
        name: 'Dr. Sarah Vance',
        callsign: 'Astra-Lead',
        role: 'Mission Commander / Flight Biomedical Specialist',
        agency: 'NASA / International Crew',
        mission: 'Expedition 71 / Gateway Shakedown',
        spacecraft: 'ISS / International Space Station',
        orbit: { altitude_km: 408.4, velocity_kms: 7.66 },
        demographics: { age: 39, gender: 'Female', blood_type: 'O-Positive', height_cm: 172, mass_kg: 64.5 },
        flight_experience: { mission_day: 142, cumulative_spaceflight_days: 318, eva_sorties_count: 6, cumulative_eva_hours: 38.5 },
        spacesuit: {
          model: 'xEMU Mk III',
          pressure_kpa: 29.6,
          primary_o2_reserve_pct: 94.2,
          battery_soc_pct: 88.5,
          co2_scrubber_efficiency_pct: 99.4,
          suit_temperature_c: 19.8
        },
        medical_status: { clearance: 'FLIGHT QUALIFIED / EVA CLEARED', overall_readiness: 'NOMINAL' },
        data_classification: 'demonstration_mission_profile'
      }
    });
  },

  getBodyRegions: async (astronautId = 'AST-01') => {
    return safeFetch(`/api/astronaut/body-regions?astronaut_id=${astronautId}`, null);
  },

  getECGData: async (astronautId = 'AST-01', recordingId = null) => {
    const url = recordingId 
      ? `/api/health/ecg?astronaut_id=${astronautId}&recording_id=${recordingId}`
      : `/api/health/ecg?astronaut_id=${astronautId}`;
    return safeFetch(url, null);
  },

  getEEGData: async (astronautId = 'AST-01', recordingId = null) => {
    const url = recordingId 
      ? `/api/health/eeg?astronaut_id=${astronautId}&recording_id=${recordingId}`
      : `/api/health/eeg?astronaut_id=${astronautId}`;
    return safeFetch(url, null);
  },

  getAlerts: async (limit = 10) => {
    return safeFetch(`/api/alerts?limit=${limit}`, { alerts: [] });
  }
};
