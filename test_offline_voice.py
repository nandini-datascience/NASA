"""
ASTRA CARE - Offline Voice Assistant Test Suite
Verifies 100% local, airgapped Speech-to-Text (Vosk) and Text-to-Speech (pyttsx3 Windows SAPI5)
processing with zero external network or cloud dependencies.
"""

import io
import json
import logging
import os
import socket
import sys
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import wave
from unittest.mock import patch

# Set working directory to project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from app.db import init_db
from app.offline_speech import (
    get_vosk_model_path,
    is_vosk_available,
    get_vosk_model,
    is_tts_available,
    get_tts_voices,
    clean_text_for_tts,
    ensure_pcm_wav_16k,
    synthesize_speech_wav,
    transcribe_audio_bytes,
    get_offline_voice_system_status,
    VoskModelNotFoundError,
    AudioProcessingError,
    TTSEngineError
)

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class TestOfflineVoiceAssistant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

        # Start dynamic uvicorn server for REST endpoints
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        import uvicorn
        from app.main import app
        config = uvicorn.Config(app=app, host="127.0.0.1", port=cls.port, log_level="warning")
        cls.server = uvicorn.Server(config)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()

        # Wait for server ready
        for _ in range(50):
            try:
                req = urllib.request.Request(f"{cls.base_url}/api/health")
                with urllib.request.urlopen(req, timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=3)

    # -------------------------------------------------------------
    # 1. LOCAL MODEL & COMPONENT AVAILABILITY
    # -------------------------------------------------------------
    def test_01_vosk_model_availability(self):
        """Verifies that the local Vosk speech recognition model exists and is loadable."""
        self.assertTrue(is_vosk_available(), "Local Vosk speech recognition model should be available.")
        model_path = get_vosk_model_path()
        self.assertIsNotNone(model_path)
        self.assertTrue(os.path.isdir(model_path), f"Vosk model path '{model_path}' must be an existing directory.")
        
        # Verify model loads into memory
        model = get_vosk_model()
        self.assertIsNotNone(model)

    def test_02_tts_engine_availability(self):
        """Verifies that pyttsx3 with Windows SAPI5 has installed voices."""
        self.assertTrue(is_tts_available(), "Local pyttsx3 SAPI5 TTS engine should be available.")
        voices = get_tts_voices()
        self.assertGreater(len(voices), 0, "At least one local SAPI5 voice must be installed on the system.")
        self.assertTrue(any("english" in v["name"].lower() or "david" in v["name"].lower() or "zira" in v["name"].lower() for v in voices))

    # -------------------------------------------------------------
    # 2. AUDIO CONVERSION & CLEANING UNIT TESTS
    # -------------------------------------------------------------
    def test_03_text_cleaning_for_speech(self):
        """Verifies that telemetry units and markdown notation are expanded for spoken clarity."""
        raw = "• Absorbed: 2.35 µGy/hr\n• Dose Eq: 4.70 µSv/hr\n• Core: 37.1°C (Δ = +0.3°C)\n• BP: 120/80 mmHg, SpO2: 98%, HR: 72 BPM"
        cleaned = clean_text_for_tts(raw)
        
        self.assertNotIn("µGy/hr", cleaned)
        self.assertIn("microgray per hour", cleaned)
        self.assertNotIn("µSv/hr", cleaned)
        self.assertIn("microsievert per hour", cleaned)
        self.assertNotIn("°C", cleaned)
        self.assertIn("degrees Celsius", cleaned)
        self.assertNotIn("mmHg", cleaned)
        self.assertIn("millimeters of mercury", cleaned)
        self.assertIn("B P M", cleaned)
        self.assertIn("S P O 2", cleaned)
        self.assertIn("delta", cleaned)

    def test_04_audio_conversion_to_16k_mono_pcm(self):
        """Verifies ensure_pcm_wav_16k converts arbitrary sample rate and stereo to 16 kHz mono WAV."""
        import numpy as np
        # Generate synthetic 44.1 kHz stereo audio
        t = np.linspace(0, 0.5, 22050, False)
        stereo_int16 = (np.vstack([np.sin(2 * np.pi * 440 * t), np.cos(2 * np.pi * 440 * t)]).T * 20000).astype(np.int16)
        
        bio = io.BytesIO()
        with wave.open(bio, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(stereo_int16.tobytes())
        
        resampled_bytes = ensure_pcm_wav_16k(bio.getvalue())
        with wave.open(io.BytesIO(resampled_bytes), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getframerate(), 16000)
            self.assertEqual(wf.getsampwidth(), 2)

    # -------------------------------------------------------------
    # 3. LOCAL SPEECH SYNTHESIS & RECOGNITION (OFFLINE ROUNDTRIP)
    # -------------------------------------------------------------
    def test_05_local_speech_synthesis(self):
        """Verifies local pyttsx3 synthesizes valid WAV audio bytes."""
        wav_bytes = synthesize_speech_wav("What is the latest radiation reading?")
        self.assertGreater(len(wav_bytes), 44)
        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        self.assertIn(b"WAVE", wav_bytes[:16])

    def test_06_local_speech_to_text_vosk(self):
        """Verifies local Vosk transcribes genuine speech generated by local TTS."""
        phrase = "what is the latest radiation reading"
        wav_bytes = synthesize_speech_wav(phrase)
        
        result = transcribe_audio_bytes(wav_bytes)
        self.assertEqual(result["status"], "success")
        self.assertIn("radiation", result["text"].lower())
        self.assertIn("reading", result["text"].lower())
        self.assertGreater(result["duration_seconds"], 0)

    # -------------------------------------------------------------
    # 4. REST API ENDPOINTS VERIFICATION
    # -------------------------------------------------------------
    def test_07_endpoint_voice_status(self):
        """Verifies GET /api/assistant/voice/status returns OFFLINE VOICE READY."""
        url = f"{self.base_url}/api/assistant/voice/status"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["indicator_text"], "OFFLINE VOICE READY")
            self.assertEqual(data["status"], "ready")
            self.assertTrue(data["vosk_available"])
            self.assertTrue(data["tts_available"])
            self.assertIn("is_offline", data)
            self.assertIn("is_online", data)
            self.assertEqual(data["is_offline"], not data["is_online"])

    def test_08_endpoint_text_to_speech(self):
        """Verifies POST /api/assistant/text-to-speech returns audio/wav stream."""
        url = f"{self.base_url}/api/assistant/text-to-speech"
        payload = json.dumps({"text": "Astronaut heart rate is 72 beats per minute.", "rate": 175}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "audio/wav")
            audio_data = resp.read()
            self.assertGreater(len(audio_data), 1000)
            self.assertTrue(audio_data.startswith(b"RIFF"))

    def test_09_endpoint_voice_to_text_raw(self):
        """Verifies POST /api/assistant/voice-to-text with raw WAV body."""
        wav_bytes = synthesize_speech_wav("explain my latest health readings")
        url = f"{self.base_url}/api/assistant/voice-to-text"
        req = urllib.request.Request(url, data=wav_bytes, headers={"Content-Type": "audio/wav"})
        
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "success")
            self.assertTrue(any(w in data["text"].lower() for w in ["health", "reading", "readings"]))

    def test_10_endpoint_voice_to_text_multipart(self):
        """Verifies POST /api/assistant/voice-to-text with multipart/form-data upload."""
        wav_bytes = synthesize_speech_wav("what is the south atlantic anomaly")
        boundary = "---------------------------974767299852498929531610575"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="speech.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n"
        ).encode() + wav_bytes + f"\r\n--{boundary}--\r\n".encode()

        url = f"{self.base_url}/api/assistant/voice-to-text"
        req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "success")
            self.assertIn("atlantic", data["text"].lower())

    # -------------------------------------------------------------
    # 5. ERROR HANDLING & EDGE CASES
    # -------------------------------------------------------------
    def test_11_empty_audio_validation(self):
        """Verifies that uploading empty or corrupt audio returns HTTP 400."""
        url = f"{self.base_url}/api/assistant/voice-to-text"
        req = urllib.request.Request(url, data=b"", headers={"Content-Type": "audio/wav"})
        
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

    def test_12_empty_text_tts_validation(self):
        """Verifies that synthesizing empty or whitespace text returns HTTP 400."""
        url = f"{self.base_url}/api/assistant/text-to-speech"
        payload = json.dumps({"text": "    "}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

    def test_13_missing_vosk_model_handling(self):
        """Verifies graceful handling when the local Vosk model is missing."""
        with patch("app.offline_speech.get_vosk_model_path", return_value=None):
            status_data = get_offline_voice_system_status()
            self.assertEqual(status_data["indicator_text"], "INITIAL SETUP REQUIRED")
            self.assertEqual(status_data["status"], "setup_required")

    def test_14_missing_tts_voice_handling(self):
        """Verifies graceful handling when local TTS voices are unavailable."""
        with patch("app.offline_speech.is_tts_available", return_value=False):
            with patch("app.offline_speech.is_vosk_available", return_value=True):
                status_data = get_offline_voice_system_status()
                self.assertEqual(status_data["indicator_text"], "VOICE OUTPUT UNAVAILABLE")
                self.assertEqual(status_data["status"], "output_unavailable")

    # -------------------------------------------------------------
    # 6. END-TO-END WORKFLOW INTEGRATION
    # -------------------------------------------------------------
    def test_15_end_to_end_voice_and_database_retrieval(self):
        """
        Tests the complete offline voice lifecycle:
        1. User speaks question ("What is the latest radiation reading?")
        2. Vosk transcribes audio into text.
        3. Text is submitted to existing POST /api/assistant/chat.
        4. Assistant queries SQLite and produces response with actual reading.
        5. Response text is synthesized into spoken audio via local TTS.
        """
        # Step 1 & 2: Speech to Text
        audio_in = synthesize_speech_wav("what is the latest radiation reading")
        stt_result = transcribe_audio_bytes(audio_in)
        self.assertEqual(stt_result["status"], "success")
        recognized_query = stt_result["text"]

        # Step 3 & 4: Query Assistant Chat
        chat_url = f"{self.base_url}/api/assistant/chat"
        chat_payload = json.dumps({"message": recognized_query, "astronaut_id": "AST-01"}).encode()
        chat_req = urllib.request.Request(chat_url, data=chat_payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(chat_req) as resp:
            self.assertEqual(resp.status, 200)
            chat_data = json.loads(resp.read().decode())
            self.assertEqual(chat_data["status"], "success")
            self.assertIn("µGy/hr", chat_data["answer"])
            assistant_answer = chat_data["answer"]

        # Step 5: Text to Speech
        spoken_wav = synthesize_speech_wav(assistant_answer)
        self.assertGreater(len(spoken_wav), 5000)
        self.assertTrue(spoken_wav.startswith(b"RIFF"))

    # -------------------------------------------------------------
    # 7. CONFIRMATION NO CLOUD APIS ARE CALLED
    # -------------------------------------------------------------
    def test_16_confirmation_no_cloud_speech_apis(self):
        """
        Ensures that offline_speech.py does NOT import or reference any cloud speech APIs:
        No Google Speech, Azure, OpenAI, AWS Polly, or cloud endpoints.
        """
        with open(os.path.join(PROJECT_ROOT, "app", "offline_speech.py"), "r", encoding="utf-8") as f:
            code = f.read().lower()

        forbidden_cloud_terms = [
            "google.cloud", "azure.cognitiveservices", "openai", "boto3",
            "speech_recognition.recognize_google", "gtts", "elevenlabs"
        ]
        for term in forbidden_cloud_terms:
            self.assertNotIn(term, code, f"Forbidden cloud speech reference '{term}' found in offline_speech.py!")

        # Verify offline indicators and local service registration
        status_data = get_offline_voice_system_status()
        self.assertEqual(status_data["speech_service"], "local_vosk_and_pyttsx3")
        self.assertIn(status_data["indicator_text"], [
            "OFFLINE VOICE READY", "INITIAL SETUP REQUIRED",
            "VOICE INPUT UNAVAILABLE", "VOICE OUTPUT UNAVAILABLE"
        ])
        # In simulated airgapped offline test, verify is_offline toggles accurately
        with patch("app.offline_speech.check_internet_connectivity", return_value=False):
            offline_data = get_offline_voice_system_status()
            self.assertTrue(offline_data["is_offline"])
            self.assertEqual(offline_data["network_indicator"], "OFFLINE – LOCAL SERVICES ACTIVE")

    # -------------------------------------------------------------
    # 8. NETWORK STATUS & LONG TEXT AUDIO CHUNKING
    # -------------------------------------------------------------
    def test_17_endpoint_network_status(self):
        """Verifies GET /api/system/network-status distinguishes online and offline modes."""
        url = f"{self.base_url}/api/system/network-status"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("is_online", data)
            self.assertIn("mode", data)
            self.assertIn("indicator_text", data)
            self.assertIn(data["indicator_text"], ["ONLINE – INTERNET AVAILABLE", "OFFLINE – LOCAL SERVICES ACTIVE"])
            self.assertTrue(data["local_services_active"])

    def test_18_endpoint_voice_status_hyphen_and_slash(self):
        """Verifies both GET /api/assistant/voice-status and /api/assistant/voice/status endpoints work."""
        for path in ["/api/assistant/voice-status", "/api/assistant/voice/status"]:
            url = f"{self.base_url}{path}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode())
                self.assertIn("status", data)
                self.assertIn("indicator_text", data)
                self.assertIn(data["indicator_text"], [
                    "OFFLINE VOICE READY", "INITIAL SETUP REQUIRED",
                    "VOICE INPUT UNAVAILABLE", "VOICE OUTPUT UNAVAILABLE"
                ])
                self.assertIn("network_indicator", data)
                self.assertIn(data["network_indicator"], [
                    "ONLINE – INTERNET AVAILABLE", "OFFLINE – LOCAL SERVICES ACTIVE"
                ])
                self.assertTrue(data["vosk_available"])
                self.assertGreaterEqual(data["voices_count"], 1)

    def test_19_long_text_tts_chunking_no_cutoff(self):
        """
        Verifies that long assistant responses (>2,000 characters) are seamlessly chunked
        and concatenated without cutting off audio or crashing the SAPI5 engine.
        """
        long_paragraph = (
            "Telemetry summary for astronaut AST-01 during orbital pass across the South Atlantic Anomaly. "
            "The active DOSTEL 1 detector inside Columbus module recorded an absorbed dose rate of 42.8 µGy/hr "
            "with a dose equivalent rate of 85.6 µSv/hr. Shielded DOSTEL 2 behind the water wall recorded 31.4 µGy/hr, "
            "confirming effective passive hydrogenous mitigation. Physiological sensors report a resting heart rate of "
            "74 BPM, blood pressure at 122/78 mmHg, SpO2 stable at 98%, and core body temperature at 36.8 °C. "
            "The Isolation Forest ML model confirmed normal telemetry within statistical baseline bounds. "
        )
        long_text = " ".join([long_paragraph] * 4)  # ~2,400 characters
        self.assertGreater(len(long_text), 2000)

        # Synthesize via function
        wav_bytes = synthesize_speech_wav(long_text)
        self.assertGreater(len(wav_bytes), 50000, "Synthesized audio for long text should exceed 50 KB.")
        self.assertTrue(wav_bytes.startswith(b"RIFF"))

        # Verify WAV format integrity
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertIn(wf.getframerate(), [16000, 22050, 44100])
            duration_sec = wf.getnframes() / wf.getframerate()
            # 2,400 chars ~ 350 words @ 175 wpm => ~100-140 seconds of speech
            self.assertGreater(duration_sec, 20.0, "Audio duration must reflect full multi-paragraph speech.")

        # Also test via REST endpoint POST /api/assistant/text-to-speech
        url = f"{self.base_url}/api/assistant/text-to-speech"
        payload = json.dumps({"text": long_text[:500]}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "audio/wav")
            audio_data = resp.read()
            self.assertTrue(audio_data.startswith(b"RIFF"))

    def test_20_spaceflight_speech_pronunciation_expansions(self):
        """Verifies spaceflight units, symbols, and acronyms are expanded into readable speech strings."""
        sample = "Rate: 25.4 µGy/hr, equiv: 50.8 µSv/hr, temp: 36.6 °C, pulse: 72 BPM, bp: 120/80 mmHg, SpO2: 98% in SAA on ISS."
        cleaned = clean_text_for_tts(sample)
        self.assertIn("microgray per hour", cleaned)
        self.assertIn("microsievert per hour", cleaned)
        self.assertIn("degrees Celsius", cleaned)
        self.assertIn("B P M", cleaned)
        self.assertIn("millimeters of mercury", cleaned)
        self.assertIn("S P O 2", cleaned)
        self.assertIn("South Atlantic Anomaly", cleaned)
        self.assertIn("I S S", cleaned)


if __name__ == "__main__":
    unittest.main()
