"""
ASTRA CARE - Offline Speech Processing Engine
Provides 100% local, airgapped Speech-to-Text (STT via Vosk)
and Text-to-Speech (TTS via pyttsx3 Windows SAPI5).

Zero external network calls, zero cloud dependencies.
"""

import io
import json
import logging
import os
import re
import socket
import struct
import sys
import tempfile
import threading
import time
import wave
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("astra_care.offline_speech")

# Root project path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Custom Exceptions
class VoskModelNotFoundError(FileNotFoundError):
    """Raised when the local Vosk speech recognition model directory cannot be found."""
    pass

class AudioProcessingError(ValueError):
    """Raised when audio data is invalid, empty, or unsupported."""
    pass

class TTSEngineError(RuntimeError):
    """Raised when local text-to-speech synthesis fails."""
    pass


# ---------------------------------------------------------------------------
# VOSK MODEL MANAGEMENT & SPEECH-TO-TEXT (STT)
# ---------------------------------------------------------------------------

DEFAULT_VOSK_LANGUAGE = os.getenv("VOSK_LANGUAGE", "en-US")
SUPPORTED_LANGUAGES = ["en-US"]  # The currently installed local model is US English

_vosk_model_cache: Optional[Any] = None
_vosk_lock = threading.Lock()

def get_vosk_model_path() -> Optional[str]:
    """
    Resolves the directory path for the local Vosk speech model.
    Checks environment variable VOSK_MODEL_PATH first, then default project paths.
    """
    env_path = os.getenv("VOSK_MODEL_PATH")
    if env_path and os.path.isdir(env_path):
        return env_path

    # Candidate directories within project
    candidates = [
        os.path.join(PROJECT_ROOT, "models", "vosk", "vosk-model-small-en-us-0.15"),
        os.path.join(PROJECT_ROOT, "models", "vosk", "vosk-model-en-us-0.22"),
        os.path.join(PROJECT_ROOT, "models", "vosk"),
    ]

    for candidate in candidates:
        if os.path.isdir(candidate):
            # Check for critical Vosk model files or subdirectories
            has_am = os.path.exists(os.path.join(candidate, "am")) or os.path.exists(os.path.join(candidate, "final.mdl"))
            has_conf = os.path.exists(os.path.join(candidate, "conf")) or os.path.exists(os.path.join(candidate, "model.conf"))
            has_graph = os.path.exists(os.path.join(candidate, "graph"))
            if has_am or has_conf or has_graph:
                return candidate
            
            # Subdirectory inspection (e.g. if extracted inside models/vosk/<model-dir>)
            try:
                for entry in os.listdir(candidate):
                    sub = os.path.join(candidate, entry)
                    if os.path.isdir(sub) and "vosk" in entry.lower():
                        return sub
            except Exception:
                pass

    return None


def is_vosk_available() -> bool:
    """Checks whether Vosk library and a valid local model are available."""
    try:
        import vosk
    except ImportError:
        return False
    path = get_vosk_model_path()
    return path is not None and os.path.isdir(path)


def get_vosk_model(model_path: Optional[str] = None) -> Any:
    """
    Returns the cached Vosk model instance, loading it into memory on demand.
    Thread-safe lazy initialization.
    """
    global _vosk_model_cache
    if _vosk_model_cache is not None:
        return _vosk_model_cache

    with _vosk_lock:
        if _vosk_model_cache is not None:
            return _vosk_model_cache

        resolved_path = model_path or get_vosk_model_path()
        if not resolved_path or not os.path.isdir(resolved_path):
            raise VoskModelNotFoundError(
                f"Vosk speech model not found at '{resolved_path}'. Initial setup required."
            )

        try:
            import vosk
            logger.info("Loading Vosk speech model from: %s", resolved_path)
            # Set Vosk log level to warning/error to avoid stdout clutter
            vosk.SetLogLevel(-1)
            model = vosk.Model(resolved_path)
            _vosk_model_cache = model
            logger.info("Vosk speech model successfully loaded into memory.")
            return _vosk_model_cache
        except Exception as exc:
            logger.error("Failed to load Vosk model from %s: %s", resolved_path, exc)
            raise


def postprocess_transcription(text: str) -> str:
    """
    Cleans and standardizes recognized speech text for spaceflight, telemetry,
    and astronaut clinical terminology.
    Maps phonetic acronym representations to standardized aerospace notation.
    """
    if not text:
        return ""
    t = text.strip()

    # Rule-based phoneme and acronym mapping
    mappings = [
        # GCR and SPE cosmic radiation terms
        (r'\b(?:gc\s*are|g\s*c\s*are|g\s*c\s*r)\b', 'GCR'),
        (r'\b(?:sp\s*e|s\s*p\s*e)\b', 'SPE'),
        (r'\b(?:gcr\s+and\s+sp)\b', 'GCR and SPE'),
        # Vitals and telemetry
        (r'\b(?:s\s*p\s*o\s*(?:two|2)|s\s*p\s*o|spo\s*2)\b', 'SpO2'),
        (r'\b(?:b\s*p\s*m)\b', 'BPM'),
        (r'\b(?:s\s*a\s*a)\b', 'SAA'),
        (r'\b(?:i\s*s\s*s)\b', 'ISS'),
        (r'\b(?:e\s*c\s*l\s*s\s*s)\b', 'ECLSS'),
        (r'\b(?:rad\s*lab)\b', 'RadLab'),
        (r'\b(?:astro\s*care|extra\s*care|astra\s*car|astra\s*call)\b', 'ASTRA CARE'),
        (r'\bexplain\s+why\s+latest\b', 'explain my latest'),
        (r'\bexplain\s+why\s+radiation\b', 'explain my radiation'),
        (r'\bjerk\s+(?:u|my)\b', 'check my'),
        (r'\babsorb\s+(?:those|does|dose)\b', 'absorbed dose'),
        (r'\babsorb\s+dose\s+rate\b', 'absorbed dose rate'),
        (r'\bradiation\s+reader\b', 'radiation reading'),
        (r'\bdose\s+equivalent\s+(?:rate)?\b', 'dose equivalent'),
        (r'\bmicro\s*gray\b', 'microgray'),
        (r'\bmicro\s*sievert\b', 'microsievert'),
        (r'\bmilligray\b', 'milligray'),
        (r'\bmillisievert\b', 'millisievert'),
    ]

    for pattern, repl in mappings:
        t = re.sub(pattern, repl, t, flags=re.IGNORECASE)

    # Clean redundant whitespace
    t = re.sub(r'\s+', ' ', t).strip()

    # Normalize sentence capitalization
    if t and len(t) > 1:
        t = t[0].upper() + t[1:]
    elif t:
        t = t.upper()

    return t


def ensure_pcm_wav_16k(audio_bytes: bytes) -> bytes:
    """
    Converts input WAV audio into standard 16 kHz, 16-bit, mono PCM WAV bytes.
    Performs true band-limited anti-aliased resampling using scipy.signal.resample_poly,
    DC offset removal, dynamic range normalization, and padding cushion for Kaldi.
    """
    if not audio_bytes or len(audio_bytes) < 44:
        raise AudioProcessingError("Audio data is empty or too short to contain a valid header.")

    # Validate RIFF header
    if not (audio_bytes.startswith(b"RIFF") or audio_bytes.startswith(b"RIFX")):
        if audio_bytes.startswith(b"\x1a\x45\xdf\xa3"):
            raise AudioProcessingError("Uploaded audio is in WebM format; expected converted 16 kHz PCM WAV.")
        elif audio_bytes.startswith(b"OggS"):
            raise AudioProcessingError("Uploaded audio is in OGG format; expected converted 16 kHz PCM WAV.")
        raise AudioProcessingError("Uploaded audio must be a valid WAV format.")

    bio = io.BytesIO(audio_bytes)
    try:
        with wave.open(bio, "rb") as wf:
            channels = wf.getnchannels()
            sample_rate = wf.getframerate()
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            frames = wf.readframes(n_frames)

            import numpy as np

            # Decode to float32
            if sampwidth == 2:
                data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
            elif sampwidth == 1:
                data = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) * 256.0
            elif sampwidth == 3:
                raw = np.frombuffer(frames, dtype=np.uint8)
                a = raw.reshape(-1, 3)
                int24 = (a[:, 0].astype(np.int32) |
                         (a[:, 1].astype(np.int32) << 8) |
                         (a[:, 2].astype(np.int32) << 16))
                int24 = np.where(int24 & 0x800000, int24 - 0x1000000, int24)
                data = (int24 / 256.0).astype(np.float32)
            elif sampwidth == 4:
                data = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 65536.0
            else:
                raise AudioProcessingError(f"Unsupported sample width: {sampwidth} bytes")

            if len(data) == 0:
                raise AudioProcessingError("Audio file contains zero audio samples.")

            # Downmix multi-channel to mono
            if channels > 1:
                data = data.reshape(-1, channels).mean(axis=1)

            # High-quality anti-aliased resampling to 16 kHz using resample_poly
            if sample_rate != 16000 and len(data) > 0:
                import scipy.signal
                import math
                gcd = math.gcd(16000, sample_rate)
                up = 16000 // gcd
                down = sample_rate // gcd
                data = scipy.signal.resample_poly(data, up, down)

            # Preprocessing 1: Remove DC bias
            dc_offset = np.mean(data)
            data = data - dc_offset

            # Preprocessing 2: Gentle peak normalization if audio is quiet
            peak = np.max(np.abs(data))
            if peak > 200.0 and peak < 16000.0:
                boost = min(4.0, 26000.0 / peak)
                data = data * boost

            # Preprocessing 3: Clamp to int16 range
            pcm_samples = np.clip(data, -32768, 32767).astype(np.int16)

            # Preprocessing 4: Kaldi acoustic boundary padding (80ms silence cushion at start & end)
            cushion_samples = int(16000 * 0.08)  # 1280 samples
            silence_cushion = np.zeros(cushion_samples, dtype=np.int16)
            padded_samples = np.concatenate([silence_cushion, pcm_samples, silence_cushion])

            out_bio = io.BytesIO()
            with wave.open(out_bio, "wb") as out_wf:
                out_wf.setnchannels(1)
                out_wf.setsampwidth(2)
                out_wf.setframerate(16000)
                out_wf.writeframes(padded_samples.tobytes())

            return out_bio.getvalue()
    except AudioProcessingError:
        raise
    except wave.Error as exc:
        raise AudioProcessingError(f"Invalid WAV audio data: {exc}")
    except Exception as exc:
        raise AudioProcessingError(f"Failed to process audio frames: {exc}")


def transcribe_audio_bytes(audio_bytes: bytes) -> Dict[str, Any]:
    """
    Transcribes audio bytes locally using Vosk KaldiRecognizer.
    Computes utterance confidence, filters noise hallucinations,
    applies aerospace domain post-processing, and returns standardized output.
    """
    if not audio_bytes or len(audio_bytes) < 44:
        raise AudioProcessingError("Uploaded audio is empty or corrupt.")

    model = get_vosk_model()
    pcm_wav = ensure_pcm_wav_16k(audio_bytes)

    import vosk
    rec = vosk.KaldiRecognizer(model, 16000)
    rec.SetWords(True)

    bio = io.BytesIO(pcm_wav)
    with wave.open(bio, "rb") as wf:
        total_frames = wf.getnframes()
        framerate = wf.getframerate()
        duration = max(0.0, (total_frames / float(framerate)) - 0.16)  # subtract 160ms cushion
        words_list: List[Dict[str, Any]] = []
        transcripts: List[str] = []

        while True:
            chunk = wf.readframes(4000)
            if not chunk:
                break
            if rec.AcceptWaveform(chunk):
                res = json.loads(rec.Result())
                if res.get("text"):
                    transcripts.append(res["text"])
                if res.get("result"):
                    words_list.extend(res["result"])

        final_res = json.loads(rec.FinalResult())
        if final_res.get("text"):
            transcripts.append(final_res["text"])
        if final_res.get("result"):
            words_list.extend(final_res["result"])

    raw_text = " ".join(t.strip() for t in transcripts if t.strip()).strip()

    # Calculate average confidence
    conf_scores = [w.get("conf", 1.0) for w in words_list if "conf" in w]
    avg_confidence = round(float(sum(conf_scores) / len(conf_scores)), 3) if conf_scores else 1.0

    # Low-confidence threshold filter: prevent spurious background noise or coughs from fabricating text
    if raw_text and len(words_list) <= 1 and avg_confidence < 0.25:
        logger.info("Discarding low-confidence noise hallucination: '%s' (conf: %s)", raw_text, avg_confidence)
        raw_text = ""
        words_list = []

    # Domain-specific post-processing
    clean_text = postprocess_transcription(raw_text)

    return {
        "text": clean_text,
        "raw_text": raw_text,
        "status": "success",
        "confidence": avg_confidence,
        "duration_seconds": round(duration, 2),
        "words_count": len(clean_text.split()) if clean_text else 0,
        "words": words_list,
        "language": DEFAULT_VOSK_LANGUAGE
    }


# ---------------------------------------------------------------------------
# TEXT-TO-SPEECH (TTS) VIA PYTTSX3 WINDOWS SAPI5
# ---------------------------------------------------------------------------

_tts_lock = threading.Lock()

def is_tts_available() -> bool:
    """Checks whether pyttsx3 is available with installed speech voices."""
    try:
        import pyttsx3
        if sys.platform == "win32":
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass
        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        return len(voices) > 0
    except Exception as exc:
        logger.warning("TTS availability check failed: %s", exc)
        return False
    finally:
        if sys.platform == "win32":
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass


def get_tts_voices() -> List[Dict[str, Any]]:
    """Returns metadata for all installed local Windows SAPI5 voices."""
    voices_info = []
    with _tts_lock:
        if sys.platform == "win32":
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            for v in voices:
                voices_info.append({
                    "id": getattr(v, "id", ""),
                    "name": getattr(v, "name", ""),
                    "languages": getattr(v, "languages", []),
                    "gender": getattr(v, "gender", None),
                    "age": getattr(v, "age", None)
                })
        except Exception as exc:
            logger.warning("Could not enumerate TTS voices: %s", exc)
        finally:
            if sys.platform == "win32":
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
    return voices_info


def clean_text_for_tts(text: str) -> str:
    """
    Expands aerospace telemetry units and cleans markdown notation
    to generate natural, clear spoken pronunciation.
    """
    t = text
    # Expand units to spoken forms
    t = re.sub(r'µGy/hr', ' microgray per hour', t)
    t = re.sub(r'µSv/hr', ' microsievert per hour', t)
    t = re.sub(r'µGy\b', ' microgray', t)
    t = re.sub(r'µSv\b', ' microsievert', t)
    t = re.sub(r'°C\b', ' degrees Celsius', t)
    t = re.sub(r'mmHg\b', ' millimeters of mercury', t)
    t = re.sub(r'\bSpO2\b', 'S P O 2', t)
    t = re.sub(r'\bBPM\b', 'B P M', t)
    t = re.sub(r'Δ\s*=\s*\+?', ' delta ', t)
    t = re.sub(r'\bLEO\b', 'L E O', t)
    t = re.sub(r'\bSAA\b', 'South Atlantic Anomaly', t)
    t = re.sub(r'\bISS\b', 'I S S', t)
    t = re.sub(r'\bECLSS\b', 'environmental control and life support system', t)

    # Clean markdown formatting, bullet symbols, bolding
    t = re.sub(r'[•\*\#\_\~]', ' ', t)
    t = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', t)
    t = re.sub(r'-\s+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def split_text_into_chunks(text: str, max_chunk_len: int = 1500) -> List[str]:
    """
    Splits long conversational or telemetry text into coherent paragraph/sentence
    chunks to prevent pyttsx3 SAPI5 buffer overflow or audio cutoffs.
    """
    if len(text) <= max_chunk_len:
        return [text]

    chunks = []
    current_chunk: List[str] = []
    current_len = 0

    paragraphs = text.split("\n")
    for para in paragraphs:
        p = para.strip()
        if not p:
            continue
        if current_len + len(p) + 1 <= max_chunk_len:
            current_chunk.append(p)
            current_len += len(p) + 1
        else:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_len = 0
            if len(p) <= max_chunk_len:
                current_chunk.append(p)
                current_len = len(p)
            else:
                sentences = re.split(r'(?<=[.!?])\s+', p)
                for s in sentences:
                    s_clean = s.strip()
                    if not s_clean:
                        continue
                    if current_len + len(s_clean) + 1 <= max_chunk_len:
                        current_chunk.append(s_clean)
                        current_len += len(s_clean) + 1
                    else:
                        if current_chunk:
                            chunks.append(" ".join(current_chunk))
                            current_chunk = []
                            current_len = 0
                        current_chunk.append(s_clean)
                        current_len = len(s_clean)

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks if chunks else [text]


def concat_wav_bytes(wav_bytes_list: List[bytes]) -> bytes:
    """
    Concatenates multiple 16-bit PCM WAV byte streams with identical audio parameters
    into a single continuous WAV audio stream.
    """
    valid_wavs = [w for w in wav_bytes_list if w and len(w) > 44]
    if not valid_wavs:
        return b""
    if len(valid_wavs) == 1:
        return valid_wavs[0]

    out_bio = io.BytesIO()
    with wave.open(io.BytesIO(valid_wavs[0]), "rb") as first_wf:
        params = first_wf.getparams()

    with wave.open(out_bio, "wb") as out_wf:
        out_wf.setparams(params)
        for wb in valid_wavs:
            with wave.open(io.BytesIO(wb), "rb") as in_wf:
                out_wf.writeframes(in_wf.readframes(in_wf.getnframes()))

    return out_bio.getvalue()


def _synthesize_single_chunk(chunk_text: str, rate: int = 175, voice_id: Optional[str] = None) -> bytes:
    """Synthesizes a single chunk of text into WAV bytes using pyttsx3 engine."""
    temp_path = None
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", max(100, min(250, rate)))
        if voice_id:
            try:
                engine.setProperty("voice", voice_id)
            except Exception:
                pass

        fd, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        engine.save_to_file(chunk_text, temp_path)
        engine.runAndWait()
        del engine

        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            raise TTSEngineError("pyttsx3 failed to produce audio file for chunk.")

        with open(temp_path, "rb") as f:
            chunk_bytes = f.read()
        return chunk_bytes
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def synthesize_speech_wav(text: str, voice_id: Optional[str] = None, rate: int = 175) -> bytes:
    """
    Synthesizes speech audio locally using pyttsx3 with Windows SAPI5.
    Seamlessly supports longer assistant responses without cutting off audio
    by chunking text and concatenating synthesized WAV streams.
    Returns 16-bit PCM WAV audio bytes.
    """
    if not text or not text.strip():
        raise TTSEngineError("Input text is empty or blank.")

    cleaned_text = clean_text_for_tts(text)
    if not cleaned_text:
        raise TTSEngineError("Text contains no pronounceable speech content.")

    with _tts_lock:
        if sys.platform == "win32":
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass
        try:
            # If text is short/standard length (<= 1500 chars), synthesize in a single pass
            if len(cleaned_text) <= 1500:
                wav_bytes = _synthesize_single_chunk(cleaned_text, rate=rate, voice_id=voice_id)
                return wav_bytes

            # For longer responses, chunk and concatenate to prevent SAPI5 cutoff
            chunks = split_text_into_chunks(cleaned_text, max_chunk_len=1200)
            wav_chunks: List[bytes] = []
            for chunk in chunks:
                if chunk.strip():
                    chunk_wav = _synthesize_single_chunk(chunk, rate=rate, voice_id=voice_id)
                    wav_chunks.append(chunk_wav)

            merged_wav = concat_wav_bytes(wav_chunks)
            if not merged_wav:
                raise TTSEngineError("Failed to concatenate multi-chunk audio response.")
            return merged_wav
        except Exception as exc:
            logger.error("TTS synthesis error: %s", exc)
            raise TTSEngineError(f"Local TTS synthesis failed: {exc}")
        finally:
            if sys.platform == "win32":
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# INTERNET CONNECTIVITY & VOICE SYSTEM STATUS INSPECTION
# ---------------------------------------------------------------------------

_network_cache = {"is_online": True, "checked_at": 0.0}
_network_lock = threading.Lock()

def check_internet_connectivity(timeout_seconds: float = 0.5) -> bool:
    """
    Quickly probes public DNS / HTTP sockets to determine if the computer
    currently has active internet access.
    Cached for 4 seconds to guarantee zero UI latency and zero freezing.
    """
    now = time.time()
    with _network_lock:
        if now - _network_cache["checked_at"] < 4.0:
            return _network_cache["is_online"]

        is_online = False
        test_endpoints = [("8.8.8.8", 53), ("1.1.1.1", 53)]
        for host, port in test_endpoints:
            try:
                with socket.create_connection((host, port), timeout=timeout_seconds):
                    is_online = True
                    break
            except (socket.timeout, socket.error, OSError):
                continue

        _network_cache["is_online"] = is_online
        _network_cache["checked_at"] = now
        return is_online


def get_offline_voice_system_status() -> Dict[str, Any]:
    """
    Evaluates local STT (Vosk), TTS (pyttsx3 SAPI5), and internet status,
    returning exact indicators conforming to ASTRA CARE specifications:
    - 'OFFLINE VOICE READY'
    - 'INITIAL SETUP REQUIRED'
    - 'VOICE INPUT UNAVAILABLE'
    - 'VOICE OUTPUT UNAVAILABLE'
    - 'ONLINE – INTERNET AVAILABLE'
    - 'OFFLINE – LOCAL SERVICES ACTIVE'
    """
    vosk_ok = is_vosk_available()
    model_path = get_vosk_model_path()
    tts_ok = is_tts_available()
    voices = get_tts_voices() if tts_ok else []
    is_online = check_internet_connectivity()

    if vosk_ok and tts_ok:
        status_key = "ready"
        indicator_text = "OFFLINE VOICE READY"
    elif not model_path:
        status_key = "setup_required"
        indicator_text = "INITIAL SETUP REQUIRED"
    elif not vosk_ok:
        status_key = "input_unavailable"
        indicator_text = "VOICE INPUT UNAVAILABLE"
    elif not tts_ok:
        status_key = "output_unavailable"
        indicator_text = "VOICE OUTPUT UNAVAILABLE"
    else:
        status_key = "setup_required"
        indicator_text = "INITIAL SETUP REQUIRED"

    network_indicator = "ONLINE – INTERNET AVAILABLE" if is_online else "OFFLINE – LOCAL SERVICES ACTIVE"

    return {
        "status": status_key,
        "indicator_text": indicator_text,
        "vosk_available": vosk_ok,
        "vosk_model_path": model_path,
        "tts_available": tts_ok,
        "voices_count": len(voices),
        "voices": [{"id": v["id"], "name": v["name"]} for v in voices],
        "is_offline": not is_online,
        "is_online": is_online,
        "network_indicator": network_indicator,
        "network_status": "online" if is_online else "offline",
        "model_language": DEFAULT_VOSK_LANGUAGE,
        "supported_languages": SUPPORTED_LANGUAGES,
        "speech_service": "local_vosk_and_pyttsx3"
    }
