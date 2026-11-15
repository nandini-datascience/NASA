import React from 'react';
import ReactDOM from 'react-dom/client';
import AstronautTwinApp from './AstronautTwinApp';
import './styles/astronaut-twin.css';

function mountTwin() {
  const mountEl = document.getElementById('astronaut-3d-root');
  if (mountEl) {
    if (!mountEl._reactRoot) {
      const root = ReactDOM.createRoot(mountEl);
      mountEl._reactRoot = root;
      root.render(
        <React.StrictMode>
          <AstronautTwinApp />
        </React.StrictMode>
      );
      console.log('✅ ASTRA CARE 3D Astronaut Digital Twin successfully mounted.');
    }
  } else {
    console.warn('Waiting for #astronaut-3d-root element...');
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mountTwin);
} else {
  mountTwin();
}

// Export for programmatic mounting if needed
window.mountAstronautTwin = mountTwin;
