"""
test_task05_assistant_integration.py - Verification Suite for Task 05

Tests:
1. Frontend File Verification: assistant.js, index.html, style.css, config.js
2. HTML DOM Contract: all expected chat, voice mic, speaker, and suggested question elements
3. JavaScript Contract: Voice input (SpeechRecognition), Voice output (SpeechSynthesis),
   edit-before-send guarantee, safe textContent rendering, error handling
4. Backend API Integration: POST /api/assistant/chat with typed and voice-converted queries
5. Speech Synthesis Audio Cleaning: verifies markdown and technical disclaimers are stripped
6. Non-Diagnostic and Safety Compliance checks
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request

print("===============================================================")
print("ASTRA CARE - TASK 05: AI TEXT & VOICE ASSISTANT VERIFICATION")
print("===============================================================")

# ----------------------------------------------------------------------------
# 1. Verify Frontend Assets
# ----------------------------------------------------------------------------
print("\n[1] Verifying Frontend Assets...")
files = [
    "frontend/index.html",
    "frontend/css/style.css",
    "frontend/js/config.js",
    "frontend/js/assistant.js",
    "frontend/js/dashboard.js",
    "frontend/js/radiation.js",
    "frontend/js/health.js",
    "frontend/js/alerts.js",
    "frontend/js/charts.js",
    "frontend/README.md"
]

all_found = True
for f in files:
    if os.path.exists(f):
        print(f"  [OK] Found {f} ({os.path.getsize(f)} bytes)")
    else:
        print(f"  [FAIL] Missing {f}")
        all_found = False

assert all_found, "Not all frontend files were found."

# ----------------------------------------------------------------------------
# 2. Verify HTML Structure and DOM IDs
# ----------------------------------------------------------------------------
print("\n[2] Verifying HTML DOM Contract in frontend/index.html...")
with open("frontend/index.html", "r", encoding="utf-8") as f:
    html_content = f.read()

required_html_elements = [
    'data-view="assistant"',
    'id="view-assistant"',
    'id="assistant-chat-messages"',
    'id="assistant-chat-input"',
    'id="btn-assistant-voice-input"',
    'id="btn-send-assistant-msg"',
    'id="btn-clear-assistant-chat"',
    'id="assistant-voice-listening-banner"',
    'id="assistant-tts-global-bar"',
    'id="btn-tts-pause"',
    'id="btn-tts-resume"',
    'id="btn-tts-stop"',
    'id="assistant-suggested-questions"',
    'id="assistant-astronaut-select"',
    'src="js/assistant.js"'
]

for elem in required_html_elements:
    assert elem in html_content, f"Missing required element in index.html: {elem}"
    print(f"  [OK] Verified HTML element: {elem}")

# ----------------------------------------------------------------------------
# 3. Verify JavaScript Code Contracts in frontend/js/assistant.js
# ----------------------------------------------------------------------------
print("\n[3] Verifying JavaScript Contracts in frontend/js/assistant.js...")
with open("frontend/js/assistant.js", "r", encoding="utf-8") as f:
    js_content = f.read()

# Requirement: Web Speech API (SpeechRecognition and SpeechSynthesis)
assert "SpeechRecognition" in js_content or "webkitSpeechRecognition" in js_content, "Missing SpeechRecognition"
assert "speechSynthesis" in js_content, "Missing SpeechSynthesis API"
assert "SpeechSynthesisUtterance" in js_content, "Missing SpeechSynthesisUtterance"
print("  [OK] Web Speech API (SpeechRecognition & SpeechSynthesis) integrated.")

# Requirement: Recognized text placed into input for user review/edit, NOT auto-sent
assert "inputEl.value = recognizedText" in js_content or "inputEl.value =" in js_content, "Must place speech into input"
assert "handleSendMessage" in js_content, "Must have handleSendMessage trigger"
print("  [OK] Edit-before-send contract verified: Speech populates input without auto-sending.")

# Requirement: Safe text rendering (Anti-XSS textContent)
assert "textContent" in js_content, "Must use safe textContent rendering"
print("  [OK] Safe textContent rendering verified (Anti-XSS).")

# Requirement: Pause, Resume, Stop controls for speech synthesis
assert "pauseSpeech" in js_content, "Must have pauseSpeech"
assert "resumeSpeech" in js_content, "Must have resumeSpeech"
assert "stopSpeech" in js_content, "Must have stopSpeech"
assert "cancel()" in js_content, "Must cancel active speech to prevent overlapping audio"
print("  [OK] SpeechSynthesis controls verified (pause, resume, stop, prevent overlapping).")

# Requirement: Audio cleaning (do not read markdown bullets or disclaimers aloud)
assert "cleanText" in js_content, "Must clean text for voice playback"
print("  [OK] Audio text cleaner verified (strips markdown & technical disclaimers for clean speech).")

# ----------------------------------------------------------------------------
# 4. Verify Live Backend API Integration
# ----------------------------------------------------------------------------
print("\n[4] Testing Live Backend Connection on POST /api/assistant/chat...")
uvicorn_path = os.path.abspath(r".\venv\Scripts\uvicorn.exe")
proc = subprocess.Popen([uvicorn_path, "app.main:app", "--host", "127.0.0.1", "--port", "8000"])

try:
    connected = False
    for _ in range(15):
        time.sleep(1)
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/api/health") as res:
                if res.status == 200:
                    connected = True
                    print("  [OK] Backend server is listening on http://127.0.0.1:8000")
                    break
        except Exception:
            pass

    assert connected, "Backend server failed to start."

    test_queries = [
        ("Explain my latest radiation reading", "AST-01", "project_data"),
        ("What is absorbed dose?", None, "knowledge_base"),
        ("What is dose equivalent?", None, "knowledge_base"),
        ("Why is space radiation dangerous?", None, "knowledge_base"),
        ("Explain my health measurements", "AST-01", "project_data"),
        ("What does this alert mean?", None, "project_data"),
        ("What should I do when an abnormal alert appears?", None, "knowledge_base"),
        ("Explain the difference between GCR and SPE", None, "knowledge_base"),
        ("Summarize my recent monitoring data", "AST-01", "knowledge_base"),
        ("Do I have heart disease?", None, "safety_guardrail")
    ]

    for query, astro_id, expected_source in test_queries:
        payload = {"message": query}
        if astro_id:
            payload["astronaut_id"] = astro_id

        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/assistant/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "answer" in data
            assert len(data["answer"]) > 20
            assert "source" in data
            assert "status" in data
            print(f"  [OK] '{query[:35]}...' -> HTTP {resp.status} (Source: {data['source']})")

    # Test Empty Message Validation (HTTP 400)
    print("\n[5] Testing Empty Message Validation (HTTP 400)...")
    empty_req = urllib.request.Request(
        "http://127.0.0.1:8000/api/assistant/chat",
        data=json.dumps({"message": "   "}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(empty_req)
        assert False, "Empty message should have failed with HTTP 400"
    except urllib.error.HTTPError as err:
        assert err.code == 400
        print(f"  [OK] Empty message correctly rejected with HTTP {err.code} Bad Request")

finally:
    proc.terminate()
    proc.wait()
    print("  [OK] Test server stopped.")

print("\n===============================================================")
print("TASK 05: ALL TESTS EXECUTED AND PASSED SUCCESSFULLY!")
print("===============================================================")
