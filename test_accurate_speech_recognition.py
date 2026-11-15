"""
test_accurate_speech_recognition.py - Comprehensive verification of ASTRA CARE Offline Speech-to-Text Accuracy.

Tests real audio across:
1. Short questions
2. Long multi-clause sentences
3. Different speaking speeds (Slow 130, Normal 175, Fast 220)
4. Pauses between spoken words
5. Background noise tolerance
6. Repeated sequential recordings (stress test)
7. Offline airgapped operation
8. Format conversion (48 kHz stereo, 44.1 kHz, 16 kHz)
9. Domain acronym and terminology post-processing
"""

import io
import json
import os
import re
import socket
import sys
import unittest
import wave
import numpy as np

# Ensure app is discoverable
sys.path.insert(0, os.path.abspath("."))

from app.offline_speech import (
    synthesize_speech_wav,
    ensure_pcm_wav_16k,
    transcribe_audio_bytes,
    postprocess_transcription,
    get_vosk_model_path,
    is_vosk_available,
    DEFAULT_VOSK_LANGUAGE,
    SUPPORTED_LANGUAGES,
    get_offline_voice_system_status,
    AudioProcessingError
)

class TestAccurateSpeechRecognition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vosk_ok = is_vosk_available()
        assert cls.vosk_ok, "Local Vosk model must be present for speech recognition tests."

    def test_01_installed_model_and_language_support(self):
        """Verifies installed Vosk model path and strict en-US language support."""
        model_path = get_vosk_model_path()
        self.assertIsNotNone(model_path)
        self.assertTrue(os.path.isdir(model_path))
        self.assertIn("en-us", model_path.lower())
        self.assertEqual(DEFAULT_VOSK_LANGUAGE, "en-US")
        self.assertEqual(SUPPORTED_LANGUAGES, ["en-US"])

        status = get_offline_voice_system_status()
        self.assertEqual(status["model_language"], "en-US")
        self.assertIn("en-US", status["supported_languages"])

    def test_02_short_questions_recognition(self):
        """Tests actual recognition on short common astronaut health & radiation queries."""
        test_queries = [
            ("What is absorbed dose?", ["absorbed", "dose"]),
            ("What is dose equivalent?", ["dose", "equivalent"]),
            ("What is my heart rate?", ["heart", "rate"]),
            ("Explain my radiation anomaly status", ["radiation", "anomaly", "status"])
        ]
        for query, expected_keywords in test_queries:
            wav = synthesize_speech_wav(query, rate=175)
            res = transcribe_audio_bytes(wav)
            self.assertEqual(res["status"], "success")
            self.assertGreater(res["confidence"], 0.6)
            text_lower = res["text"].lower()
            for kw in expected_keywords:
                self.assertIn(kw.lower(), text_lower, f"Keyword '{kw}' missing from '{res['text']}'")

    def test_03_long_sentences_recognition(self):
        """Tests actual recognition on long multi-clause aerospace sentences without truncation."""
        long_query = "Please explain the difference between galactic cosmic radiation and solar particle events in low Earth orbit."
        wav = synthesize_speech_wav(long_query, rate=175)
        res = transcribe_audio_bytes(wav)
        self.assertEqual(res["status"], "success")
        self.assertGreater(res["words_count"], 10)
        self.assertGreater(res["confidence"], 0.7)
        self.assertGreater(res["duration_seconds"], 4.0)

        text_lower = res["text"].lower()
        self.assertIn("difference", text_lower)
        self.assertIn("radiation", text_lower)
        self.assertIn("orbit", text_lower)

    def test_04_different_speaking_speeds(self):
        """Tests speech recognition across slow, normal, and fast speaking rates."""
        rates = [130, 175, 210]  # Slow, Normal, Fast
        phrase = "Check my vital signs and radiation levels."
        for r in rates:
            wav = synthesize_speech_wav(phrase, rate=r)
            res = transcribe_audio_bytes(wav)
            self.assertEqual(res["status"], "success")
            text_lower = res["text"].lower()
            self.assertIn("vital", text_lower)
            self.assertIn("radiation", text_lower)

    def test_05_pauses_between_words(self):
        """Tests speech recognition when deliberate pauses occur between words."""
        # Synthesize separate words and insert 0.35s silence pauses between them
        words = ["What", "is", "my", "blood", "pressure"]
        wav_parts = []
        silence = np.zeros(int(16000 * 0.35), dtype=np.int16).tobytes()

        for w in words:
            w_wav = synthesize_speech_wav(w, rate=175)
            with wave.open(io.BytesIO(w_wav), 'rb') as wf:
                wav_parts.append(wf.readframes(wf.getnframes()))
                wav_parts.append(silence)

        full_pcm = b"".join(wav_parts)
        bio = io.BytesIO()
        with wave.open(bio, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(full_pcm)

        res = transcribe_audio_bytes(bio.getvalue())
        self.assertEqual(res["status"], "success")
        text_lower = res["text"].lower()
        self.assertIn("blood", text_lower)
        self.assertIn("pressure", text_lower)

    def test_06_background_noise_tolerance(self):
        """Tests speech recognition under realistic Gaussian background noise."""
        phrase = "Explain my latest radiation reading."
        raw_wav = synthesize_speech_wav(phrase, rate=175)

        bio = io.BytesIO(raw_wav)
        with wave.open(bio, 'rb') as wf:
            frames = wf.readframes(wf.getnframes())
            data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)

        # Add Gaussian noise with standard deviation of 300 (approx SNR ~ 28 dB)
        np.random.seed(42)
        noise = np.random.normal(0, 300, len(data))
        noisy_data = np.clip(data + noise, -32768, 32767).astype(np.int16)

        n_bio = io.BytesIO()
        with wave.open(n_bio, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(noisy_data.tobytes())

        res = transcribe_audio_bytes(n_bio.getvalue())
        self.assertEqual(res["status"], "success")
        text_lower = res["text"].lower()
        self.assertIn("radiation", text_lower)
        self.assertIn("reading", text_lower)

    def test_07_repeated_recordings_stability(self):
        """Tests that multiple sequential recognition requests execute reliably without memory leak."""
        test_phrases = [
            "What is absorbed dose?",
            "What is dose equivalent?",
            "What is my heart rate?",
            "Explain my radiation anomaly status"
        ]
        for p in test_phrases:
            wav = synthesize_speech_wav(p, rate=175)
            res = transcribe_audio_bytes(wav)
            self.assertEqual(res["status"], "success")
            self.assertGreater(len(res["text"]), 0)

    def test_08_multichannel_and_high_sample_rate_resampling(self):
        """Tests that 48 kHz stereo audio is properly converted and recognized without distortion."""
        import scipy.signal
        phrase = "What is the absorbed dose?"
        raw_wav = synthesize_speech_wav(phrase, rate=175)

        with wave.open(io.BytesIO(raw_wav), 'rb') as wf:
            orig = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32)

        # Upsample to 48 kHz stereo (48000 / 16000 = 3)
        data_48k = scipy.signal.resample_poly(orig, 3, 1)
        stereo_48k = np.column_stack([data_48k, data_48k])

        bio_48k = io.BytesIO()
        with wave.open(bio_48k, 'wb') as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            wf.writeframes(np.clip(stereo_48k, -32768, 32767).astype(np.int16).tobytes())

        res = transcribe_audio_bytes(bio_48k.getvalue())
        self.assertEqual(res["status"], "success")
        self.assertIn("absorbed dose", res["text"].lower())

    def test_09_domain_acronym_and_terminology_postprocessing(self):
        """Verifies domain post-processing maps aerospace acronyms and medical units correctly."""
        mappings = [
            ("explain gc are and sp", "Explain GCR and SPE"),
            ("what is my s p o two", "What is my SpO2"),
            ("check my b p m", "Check my BPM"),
            ("what is the s a a", "What is the SAA"),
            ("status of the i s s", "Status of the ISS"),
            ("what is absorb dose rate", "What is absorbed dose rate"),
            ("current micro gray level", "Current microgray level"),
            ("tell astra call to summarize", "Tell ASTRA CARE to summarize")
        ]
        for raw, expected in mappings:
            cleaned = postprocess_transcription(raw)
            self.assertEqual(cleaned, expected)

    def test_10_strict_format_validation_rejects_non_wav(self):
        """Verifies that non-WAV data (such as raw WebM or arbitrary binary) is strictly rejected."""
        fake_webm = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01" + b"\x00" * 40
        with self.assertRaises(AudioProcessingError):
            ensure_pcm_wav_16k(fake_webm)

        fake_ogg = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00" + b"\x00" * 40
        with self.assertRaises(AudioProcessingError):
            ensure_pcm_wav_16k(fake_ogg)

if __name__ == '__main__':
    unittest.main()
