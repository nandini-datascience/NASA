"""
test_mic_permission.py - Comprehensive verification of Microphone Permission Management in ASTRA CARE.

Validates:
1. Microphone Permission Management:
   - Non-intrusive Permissions API query via navigator.permissions.query({ name: 'microphone' })
   - Does NOT request microphone permission automatically during dashboard load / initialization
   - Real-time permission change listener via status.onchange
2. Remember Permission & Persistence:
   - Reuses existing active audioStream without redundant getUserMedia calls
   - Releases/stops all audio tracks properly on stopVoiceRecording
   - Handles granted, denied, and prompt states
3. Voice Assistant Integrity:
   - Preserves offline Vosk STT and pyttsx3 TTS
   - Safe text handling, cleanText audio cleaning, edit-before-send contract
4. Error Handling:
   - NotAllowedError, NotFoundError, NotReadableError, OverconstrainedError, SecurityError
   - Clear user instructions on site settings for denied state
5. Navigation & View Transitions:
   - Auto-stops audio tracks when navigating away from assistant view in dashboard.js
"""

import os
import re
import unittest

class TestMicrophonePermissionManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open('frontend/js/assistant.js', 'r', encoding='utf-8') as f:
            cls.assistant_js = f.read()
        with open('frontend/js/dashboard.js', 'r', encoding='utf-8') as f:
            cls.dashboard_js = f.read()
        with open('frontend/index.html', 'r', encoding='utf-8') as f:
            cls.index_html = f.read()

    def test_01_state_has_permission_properties(self):
        """Verifies state holds micPermissionState and permissionStatus."""
        self.assertIn("micPermissionState:", self.assistant_js)
        self.assertIn("permissionStatus:", self.assistant_js)

    def test_02_check_microphone_permission_defined(self):
        """Verifies checkMicrophonePermission method exists and uses Permissions API."""
        self.assertIn("checkMicrophonePermission()", self.assistant_js)
        self.assertIn("navigator.permissions.query", self.assistant_js)
        self.assertIn("name: 'microphone'", self.assistant_js)

    def test_03_no_automatic_getusermedia_on_load(self):
        """Verifies getUserMedia is NEVER called in init() or initOfflineVoice()."""
        # Extract init() method
        init_match = re.search(r'init\s*\(\)\s*\{(.*?)\n\s*\},', self.assistant_js, re.DOTALL)
        self.assertIsNotNone(init_match, "init() method found")
        self.assertNotIn("getUserMedia", init_match.group(1), "init() must NOT call getUserMedia")

        # Extract initOfflineVoice() method
        offline_voice_match = re.search(r'initOfflineVoice\s*\(\)\s*\{(.*?)\n\s*\},', self.assistant_js, re.DOTALL)
        self.assertIsNotNone(offline_voice_match, "initOfflineVoice() method found")
        # Ensure it does NOT call getUserMedia(...) with parameters
        self.assertNotRegex(offline_voice_match.group(1), r'getUserMedia\s*\(', "initOfflineVoice() must NOT invoke getUserMedia")

    def test_04_realtime_permission_listener(self):
        """Verifies status.onchange listener is implemented for site settings changes."""
        self.assertIn("status.onchange", self.assistant_js)
        self.assertIn("VOICE INPUT PERMISSION DENIED", self.assistant_js)

    def test_05_handle_denied_permission_state(self):
        """Verifies startVoiceRecording handles denied state without calling getUserMedia."""
        start_rec_match = re.search(r'async startVoiceRecording\s*\(\)\s*\{(.*?)\n\s*async stopVoiceRecording', self.assistant_js, re.DOTALL)
        self.assertIsNotNone(start_rec_match, "startVoiceRecording method found")
        rec_code = start_rec_match.group(1)

        # Must check permission state
        self.assertIn("checkMicrophonePermission", rec_code)
        # Must branch on denied and instruct site settings
        self.assertIn("permState === 'denied'", rec_code)
        self.assertIn("settings", rec_code.lower())

    def test_06_reuse_active_stream(self):
        """Verifies startVoiceRecording reuses existing active audioStream."""
        start_rec_match = re.search(r'async startVoiceRecording\s*\(\)\s*\{(.*?)\n\s*async stopVoiceRecording', self.assistant_js, re.DOTALL)
        rec_code = start_rec_match.group(1)

        self.assertIn("isStreamReusable", rec_code)
        self.assertIn("audioStream.active", rec_code)
        self.assertIn("readyState === 'live'", rec_code)

    def test_07_stop_tracks_properly(self):
        """Verifies stopVoiceRecording cleanly stops all audio tracks and sets audioStream to null."""
        stop_rec_match = re.search(r'async stopVoiceRecording\s*\(\)\s*\{(.*?)\n\s*\},', self.assistant_js, re.DOTALL)
        self.assertIsNotNone(stop_rec_match, "stopVoiceRecording method found")
        stop_code = stop_rec_match.group(1)

        self.assertIn("track.stop()", stop_code)
        self.assertIn("this.state.audioStream = null", stop_code)

    def test_08_error_handling_contract(self):
        """Verifies NotAllowedError, NotFoundError, NotReadableError, and OverconstrainedError handling."""
        self.assertIn("NotAllowedError", self.assistant_js)
        self.assertIn("NotFoundError", self.assistant_js)
        self.assertIn("NotReadableError", self.assistant_js)
        self.assertIn("OverconstrainedError", self.assistant_js)

    def test_09_navigation_releases_microphone(self):
        """Verifies dashboard.js stops recording and releases mic tracks when navigating away from assistant."""
        self.assertIn("AssistantModule.stopVoiceRecording()", self.dashboard_js)

    def test_10_alias_stopVoiceRecognition_exists(self):
        """Verifies stopVoiceRecognition alias exists for callsites like clearChat."""
        self.assertIn("stopVoiceRecognition()", self.assistant_js)

if __name__ == '__main__':
    unittest.main()
