"""
test_frontend_views.py - Verify frontend HTML, JavaScript syntax and integration
"""

import os
import re
import unittest

class TestFrontendViews(unittest.TestCase):
    def setUp(self):
        with open('frontend/index.html', 'r', encoding='utf-8') as f:
            self.html = f.read()

    def test_all_views_present(self):
        views = [
            'dashboard', 'radiation', 'health', 'alerts', 'assistant', 'history', 'about',
            'nasa-data', 'radiation-location', 'radiation-forecast', 'smart-alerts',
            'detector-comparison', 'health-reports'
        ]
        for v in views:
            self.assertIn(f'id="view-{v}"', self.html, f"View id='view-{v}' missing from index.html")
            self.assertIn(f'data-view="{v}"', self.html, f"Navigation data-view='{v}' missing from index.html")

    def test_all_scripts_included(self):
        scripts = [
            'vendor/chart.umd.min.js',
            'js/config.js',
            'js/radiation.js',
            'js/health.js',
            'js/alerts.js',
            'js/charts.js',
            'js/assistant.js',
            'js/advanced_features.js',
            'js/dashboard.js'
        ]
        for s in scripts:
            self.assertIn(s, self.html, f"Script '{s}' missing from index.html")

    def test_javascript_files_exist(self):
        for js_file in ['config.js', 'radiation.js', 'health.js', 'alerts.js', 'charts.js', 'assistant.js', 'advanced_features.js', 'dashboard.js']:
            path = os.path.join('frontend', 'js', js_file)
            self.assertTrue(os.path.exists(path), f"File {path} does not exist")
            size = os.path.getsize(path)
            self.assertGreater(size, 100, f"File {path} is suspiciously small: {size} bytes")

    def test_config_endpoints_exist(self):
        with open('frontend/js/config.js', 'r', encoding='utf-8') as f:
            cfg = f.read()
        endpoints = [
            'NASA_LATEST', 'NASA_SYNC', 'NASA_SYNC_STATUS', 'RADIATION_LOCATIONS',
            'RADIATION_FORECAST', 'RADIATION_FORECAST_GENERATE', 'SMART_ALERTS',
            'SMART_ALERTS_EVALUATE', 'DETECTOR_COMPARISON', 'DETECTOR_LIST',
            'REPORT_PREVIEW', 'REPORT_PDF'
        ]
        for ep in endpoints:
            self.assertIn(ep, cfg, f"Endpoint {ep} missing from config.js")

if __name__ == '__main__':
    unittest.main()
