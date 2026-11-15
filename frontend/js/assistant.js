/**
 * assistant.js - ASTRA CARE AI Text and Voice Assistant Controller
 * 
 * Capabilities:
 * 1. AI Text Assistant:
 *    - Conversational chat with Python FastAPI backend (POST /api/assistant/chat).
 *    - Suggested clickable question chips.
 *    - User vs. Assistant message distinction with safe textContent rendering (Anti-XSS).
 *    - Loading indicator, auto-scrolling, clear chat functionality.
 * 2. Voice Input (Speech-to-Text):
 *    - Web Speech API (SpeechRecognition / webkitSpeechRecognition).
 *    - Microphone button with listening indicator and waveform pulse.
 *    - Converts speech into text and places inside input field for review/editing.
 *    - Does NOT auto-send; astronaut retains full edit control before submitting.
 *    - Graceful permission denial and unsupported browser handling.
 * 3. Voice Output (Text-to-Speech):
 *    - Local offline pyttsx3 Windows SAPI5 engine (replaces online window.speechSynthesis for 100% airgapped operation).
 *    - Web Speech API (SpeechSynthesis / SpeechSynthesisUtterance / window.speechSynthesis fallback reference).
 *    - Per-message speaker button and global speech control toolbar (Pause, Resume, Stop).
 *    - Prevents overlapping audio (cancels previous utterance).
 *    - Strips markdown and technical metadata, speaking only clean conversational text.
 */
function getAssistantApiUrl(endpoint) {
    const baseUrl = CONFIG.API_BASE_URL.replace(/\/+$/, '');
    const cleanEndpoint = endpoint.replace(/^\/+/, '');

    return `${baseUrl}/${cleanEndpoint}`;
}
const AssistantModule = {
    // Component State
    state: {
        messages: [],
        isListening: false,
        isProcessingAudio: false,
        mediaRecorder: null,
        audioStream: null,
        audioChunks: [],
        speechSupported: true, // Offline Vosk STT supported via backend
        ttsSupported: true,    // Offline pyttsx3 TTS supported via backend
        audioPlayer: null,     // HTMLAudioElement for local WAV playback
        currentAudioUrl: null,
        currentlyPlayingId: null,
        isPaused: false,
        isLoading: false,
        selectedAstronautId: 'AST-01',
        voiceStatus: null,
        isOnline: true,
        networkStatus: null,
        micPermissionState: 'prompt', // 'granted' | 'denied' | 'prompt' | 'unknown'
        permissionStatus: null
    },

    // Suggested Questions for Space Crew (ASTRA CARE 2.0)
    suggestedQuestions: [
        "Explain my latest radiation reading",
        "Explain my radiation anomaly status",
        "What is absorbed dose?",
        "What is dose equivalent?",
        "What is the difference between absorbed dose and dose equivalent?",
        "What is the South Atlantic Anomaly?",
        "Explain my health measurements",
        "Are you diagnosing me?",
        "What does this alert mean?",
        "What should I do when an abnormal alert appears?",
        "Explain the difference between GCR and SPE",
        "Summarize my recent monitoring data"
    ],

    /**
     * Initializes the AI Assistant UI, offline speech recognition, and offline speech synthesis.
     */
    init() {
        console.log('Initializing ASTRA CARE AI Health & Offline Voice Assistant...');

        // 1. Initialize Local Offline Voice Player
        this.initOfflineVoice();

        // 2. Bind DOM Event Listeners
        this.bindEvents();

        // 3. Render Suggested Questions Chips
        this.renderSuggestedQuestions();

        // 4. Check Local AI / Fallback Status, Offline Voice Status & Network Status
        this.fetchAssistantStatus();
        this.fetchVoiceStatus();
        this.fetchNetworkStatus();

        // 5. Initial Welcome Message
        if (this.state.messages.length === 0) {
            this.addAssistantMessage({
                answer: "Greetings, crew member. I am your ASTRA CARE AI Health and Radiation Assistant.\n\n" +
                        "I can explain your radiation dosimetry, vital signs, telemetry statuses, and active alerts " +
                        "in plain language. You can type your questions or use the microphone to speak offline.",
                source: "knowledge_base",
                status: "success",
                data_context: null
            });
        }

        console.log('AI Health Assistant initialized with 100% offline speech capabilities.');
    },

    /**
     * Initializes offline audio player and checks microphone support.
     */
    initOfflineVoice() {
        this.state.audioPlayer = new Audio();
        this.state.audioPlayer.onended = () => {
            this.resetTTSState();
        };
        this.state.audioPlayer.onerror = (e) => {
            console.warn('Local offline audio playback error:', e);
            this.resetTTSState();
        };

        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            this.state.speechSupported = true;
        } else {
            this.state.speechSupported = false;
            console.warn('Microphone recording is not supported in this browser.');
        }

        // Non-intrusively query browser microphone permission status on load (never triggers a popup)
        this.checkMicrophonePermission();
    },

    /**
     * Binds DOM event handlers for text input, buttons, and voice triggers.
     */
    bindEvents() {
        const inputEl = document.getElementById('assistant-chat-input');
        const sendBtn = document.getElementById('btn-send-assistant-msg');
        const micBtn = document.getElementById('btn-assistant-voice-input');
        const clearBtn = document.getElementById('btn-clear-assistant-chat');
        const astroSelect = document.getElementById('assistant-astronaut-select');

        // Global Voice Output Control Buttons
        const pauseVoiceBtn = document.getElementById('btn-tts-pause');
        const resumeVoiceBtn = document.getElementById('btn-tts-resume');
        const stopVoiceBtn = document.getElementById('btn-tts-stop');

        // Send Button Click
        if (sendBtn) {
            sendBtn.addEventListener('click', () => this.handleSendMessage());
        }

        // Enter Key in Input Field
        if (inputEl) {
            inputEl.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.handleSendMessage();
                }
            });
        }

        // Microphone Button Click
        if (micBtn) {
            micBtn.addEventListener('click', () => this.toggleVoiceRecognition());
        }

        // Clear Chat Button Click
        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearChat());
        }

        // Astronaut Selector Change
        if (astroSelect) {
            astroSelect.addEventListener('change', (e) => {
                this.state.selectedAstronautId = e.target.value;
                showToast(`Assistant context set to astronaut: ${e.target.value}`, 'info');
            });
        }

        // Global Voice Output Controls
        if (pauseVoiceBtn) pauseVoiceBtn.addEventListener('click', () => this.pauseSpeech());
        if (resumeVoiceBtn) resumeVoiceBtn.addEventListener('click', () => this.resumeSpeech());
        if (stopVoiceBtn) stopVoiceBtn.addEventListener('click', () => this.stopSpeech());

        // Online / Offline System Network Mode Listeners
        window.addEventListener('online', () => {
            console.log('Browser transitioned to ONLINE mode.');
            this.fetchNetworkStatus();
        });
        window.addEventListener('offline', () => {
            console.log('Browser transitioned to OFFLINE mode.');
            this.fetchNetworkStatus();
        });
    },

    /**
     * Renders suggested clickable question chips.
     */
    renderSuggestedQuestions() {
        const container = document.getElementById('assistant-suggested-questions');
        if (!container) return;

        container.innerHTML = '';
        this.suggestedQuestions.forEach(question => {
            const chip = document.createElement('button');
            chip.className = 'suggested-chip';
            chip.type = 'button';
            chip.textContent = question;
            chip.addEventListener('click', () => {
                const inputEl = document.getElementById('assistant-chat-input');
                if (inputEl) {
                    inputEl.value = question;
                    inputEl.focus();
                    this.handleSendMessage();
                }
            });
            container.appendChild(chip);
        });
    },

    /**
     * Handles message submission from input field.
     */
    async handleSendMessage() {
        const inputEl = document.getElementById('assistant-chat-input');
        if (!inputEl) return;

        const text = inputEl.value.trim();
        if (!text || this.state.isLoading) return;

        // Clear input and focus
        inputEl.value = '';
        inputEl.style.height = 'auto';

        // 1. Add User Message
        this.addUserMessage(text);

        // 2. Show Typing Indicator
        this.showTypingIndicator();

        // 3. Send to Backend API
        try {
            this.state.isLoading = true;
            const payload = {
                message: text,
                astronaut_id: this.state.selectedAstronautId
            };

            const data = await apiFetch(CONFIG.ENDPOINTS.ASSISTANT_CHAT, {
                method: 'POST',
                body: JSON.stringify(payload)
            });

            this.removeTypingIndicator();

            if (data && data.answer) {
                this.addAssistantMessage(data);
            } else {
                this.addErrorMessage("Received an unexpected response structure from the backend service.");
            }
        } catch (error) {
            this.removeTypingIndicator();
            console.error('AI Assistant Error:', error);
            this.addErrorMessage(
                `Unable to connect to the ASTRA CARE Assistant API (${error.message}). ` +
                "Ensure the FastAPI backend server is running on http://127.0.0.1:8000."
            );
        } finally {
            this.state.isLoading = false;
        }
    },

    /**
     * Appends a user message bubble. Safe rendering via textContent.
     * 
     * @param {string} text 
     */
    addUserMessage(text) {
        const id = `user-${Date.now()}`;
        const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        this.state.messages.push({
            id: id,
            role: 'user',
            text: text,
            timestamp: timeStr
        });

        const messagesContainer = document.getElementById('assistant-chat-messages');
        if (!messagesContainer) return;

        const msgWrapper = document.createElement('div');
        msgWrapper.className = 'chat-message-row user-row';
        msgWrapper.id = id;

        const avatar = document.createElement('div');
        avatar.className = 'chat-avatar user-avatar';
        avatar.textContent = 'CREW';

        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble user-bubble';

        const textContent = document.createElement('div');
        textContent.className = 'chat-text';
        textContent.textContent = text; // SAFE Anti-XSS

        const meta = document.createElement('div');
        meta.className = 'chat-meta';
        meta.textContent = timeStr;

        bubble.appendChild(textContent);
        bubble.appendChild(meta);

        msgWrapper.appendChild(bubble);
        msgWrapper.appendChild(avatar);

        messagesContainer.appendChild(msgWrapper);
        this.scrollToBottom();
    },

    /**
     * Appends an assistant response bubble. Safe text parsing via textContent.
     * 
     * @param {object} responseObj - { answer, source, status, data_context }
     */
    addAssistantMessage(responseObj) {
        const id = `asst-${Date.now()}`;
        const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        this.state.messages.push({
            id: id,
            role: 'assistant',
            text: responseObj.answer,
            source: responseObj.source,
            status: responseObj.status,
            dataContext: responseObj.data_context,
            timestamp: timeStr
        });

        const messagesContainer = document.getElementById('assistant-chat-messages');
        if (!messagesContainer) return;

        const msgWrapper = document.createElement('div');
        msgWrapper.className = 'chat-message-row assistant-row';
        msgWrapper.id = id;

        const avatar = document.createElement('div');
        avatar.className = 'chat-avatar assistant-avatar';
        avatar.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 14 14"></polyline></svg>`;

        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble assistant-bubble';

        // Badge Pill (Source)
        const badgeRow = document.createElement('div');
        badgeRow.className = 'assistant-badge-row';

        const sourceBadge = document.createElement('span');
        sourceBadge.className = `badge-tag ${responseObj.status === 'warning' ? 'warning' : 'info'}`;
        sourceBadge.textContent = responseObj.source === 'safety_guardrail' 
            ? 'Safety Guardrail' 
            : (responseObj.source === 'project_data' ? 'Telemetry Database' : 'Aerospace Knowledge');

        badgeRow.appendChild(sourceBadge);

        // Speaker Button (Voice Output)
        if (this.state.ttsSupported) {
            const speakBtn = document.createElement('button');
            speakBtn.className = 'btn-msg-speak';
            speakBtn.type = 'button';
            speakBtn.title = 'Listen to answer';
            speakBtn.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg> <span>Listen</span>`;
            
            speakBtn.addEventListener('click', () => {
                this.speakText(id, responseObj.answer, speakBtn);
            });

            badgeRow.appendChild(speakBtn);
        }

        bubble.appendChild(badgeRow);

        // Safe Body Formatting (Separating paragraphs and bullet points safely)
        const textContainer = document.createElement('div');
        textContainer.className = 'chat-text';

        const lines = responseObj.answer.split('\n');
        lines.forEach(line => {
            const p = document.createElement('p');
            p.textContent = line; // SAFE textContent
            p.style.margin = '0 0 0.45rem 0';
            if (line.trim().startsWith('•') || line.trim().startsWith('-')) {
                p.style.paddingLeft = '0.85rem';
                p.style.color = 'var(--text-cyan)';
            }
            textContainer.appendChild(p);
        });

        bubble.appendChild(textContainer);

        // Meta Footer
        const meta = document.createElement('div');
        meta.className = 'chat-meta';
        meta.textContent = `ASTRA CARE • ${timeStr}`;
        bubble.appendChild(meta);

        msgWrapper.appendChild(avatar);
        msgWrapper.appendChild(bubble);

        messagesContainer.appendChild(msgWrapper);
        this.scrollToBottom();
    },

    /**
     * Appends an error message bubble.
     * 
     * @param {string} errorText 
     */
    addErrorMessage(errorText) {
        const messagesContainer = document.getElementById('assistant-chat-messages');
        if (!messagesContainer) return;

        const msgWrapper = document.createElement('div');
        msgWrapper.className = 'chat-message-row assistant-row';

        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble assistant-bubble error-bubble';

        const textEl = document.createElement('div');
        textEl.className = 'chat-text';
        textEl.textContent = errorText; // SAFE

        bubble.appendChild(textEl);
        msgWrapper.appendChild(bubble);
        messagesContainer.appendChild(msgWrapper);
        this.scrollToBottom();
    },

    /**
     * Displays typing / processing indicator.
     */
    showTypingIndicator() {
        const messagesContainer = document.getElementById('assistant-chat-messages');
        if (!messagesContainer) return;

        const typingWrapper = document.createElement('div');
        typingWrapper.className = 'chat-message-row assistant-row';
        typingWrapper.id = 'assistant-typing-indicator';

        const avatar = document.createElement('div');
        avatar.className = 'chat-avatar assistant-avatar';
        avatar.textContent = 'AI';

        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble assistant-bubble typing-bubble';
        bubble.innerHTML = `
            <div class="typing-dots">
                <span></span><span></span><span></span>
            </div>
            <span style="font-size: 0.78rem; color: var(--text-muted); margin-left: 0.6rem;">Analyzing telemetry...</span>
        `;

        typingWrapper.appendChild(avatar);
        typingWrapper.appendChild(bubble);
        messagesContainer.appendChild(typingWrapper);
        this.scrollToBottom();
    },

    /**
     * Removes typing indicator.
     */
    removeTypingIndicator() {
        const indicator = document.getElementById('assistant-typing-indicator');
        if (indicator) {
            indicator.remove();
        }
    },

    /**
     * Checks browser microphone permission status non-intrusively via Permissions API.
     * Never triggers a permission prompt or popup.
     * Returns: 'granted' | 'denied' | 'prompt' | 'unknown'
     */
    async checkMicrophonePermission() {
        if (typeof navigator !== 'undefined' && navigator.permissions && navigator.permissions.query) {
            try {
                const status = await navigator.permissions.query({ name: 'microphone' });
                this.state.micPermissionState = status.state;
                this.state.permissionStatus = status;

                try {
                    localStorage.setItem('astra_care_mic_permission', status.state);
                } catch (e) {}

                // Real-time listener for site settings permission changes
                status.onchange = () => {
                    this.state.micPermissionState = status.state;
                    console.log(`[ASTRA CARE] Browser microphone permission updated to: ${status.state}`);
                    try {
                        localStorage.setItem('astra_care_mic_permission', status.state);
                    } catch (e) {}

                    if (status.state === 'denied') {
                        this.updateVoiceStatusUI('VOICE INPUT PERMISSION DENIED', 'permission_denied');
                        if (this.state.isListening) {
                            this.stopVoiceRecording();
                        }
                    } else if (status.state === 'granted') {
                        if (this.state.voiceStatus) {
                            this.updateVoiceStatusUI(this.state.voiceStatus.indicator_text, this.state.voiceStatus.status);
                        } else {
                            this.updateVoiceStatusUI('OFFLINE VOICE READY', 'ready');
                        }
                    } else if (status.state === 'prompt') {
                        if (this.state.voiceStatus) {
                            this.updateVoiceStatusUI(this.state.voiceStatus.indicator_text, this.state.voiceStatus.status);
                        }
                    }
                };

                return status.state;
            } catch (queryErr) {
                console.log('[ASTRA CARE] Permissions query for microphone not supported:', queryErr.message || queryErr);
            }
        }

        // Secondary fallback to localStorage persistence
        try {
            const saved = localStorage.getItem('astra_care_mic_permission');
            if (saved === 'granted' || saved === 'denied' || saved === 'prompt') {
                this.state.micPermissionState = saved;
                return saved;
            }
        } catch (e) {}

        this.state.micPermissionState = 'prompt';
        return 'prompt';
    },

    /**
     * Toggles Offline Voice Input (Microphone Recording & Local Vosk STT).
     */
    async toggleVoiceRecognition() {
        if (this.state.isProcessingAudio) {
            return;
        }
        if (this.state.isListening) {
            await this.stopVoiceRecording();
        } else {
            await this.startVoiceRecording();
        }
    },

    /**
     * Starts listening to user microphone via MediaRecorder.
     * - Checks permission state non-intrusively before calling getUserMedia.
     * - Reuses existing live audioStream if already available.
     * - If permission is already granted, starts recording silently without new prompt.
     * - If denied, presents clear site settings instructions without attempting getUserMedia.
     * - Handles NotAllowedError, NotFoundError, NotReadableError gracefully.
     */
    async startVoiceRecording() {
        // Stop any active text-to-speech output first
        this.stopSpeech();

        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            const unsupportedMsg = 'Microphone recording is not supported in this browser.';
            showToast(unsupportedMsg, 'error');
            this.setRecordingBannerState('error', unsupportedMsg);
            this.updateVoiceStatusUI('VOICE INPUT UNAVAILABLE', 'input_unavailable');
            return;
        }

        // 1. Check current permission status
        const permState = await this.checkMicrophonePermission();

        // 2. If permission is explicitly denied, guide the user on how to enable it without triggering a failed prompt
        if (permState === 'denied') {
            const deniedMsg = 'Microphone permission is blocked in your browser site settings. ' +
                              'To enable: click the padlock or settings icon in your browser address bar, ' +
                              'change Microphone to "Allow", and reload the page.';
            this.setRecordingBannerState('error', deniedMsg);
            showToast(deniedMsg, 'warning');
            this.updateVoiceStatusUI('VOICE INPUT PERMISSION DENIED', 'permission_denied');
            return;
        }

        try {
            // 3. Check if an active, live audioStream is already available to reuse
            let stream = null;
            const isStreamReusable = this.state.audioStream &&
                                     this.state.audioStream.active &&
                                     this.state.audioStream.getAudioTracks().length > 0 &&
                                     this.state.audioStream.getAudioTracks().some(track => track.readyState === 'live');

            if (isStreamReusable) {
                stream = this.state.audioStream;
            } else {
                // Request microphone access.
                // If permission was already granted, the browser immediately returns the stream without popup.
                // If permission is 'prompt', this displays the browser's standard one-time permission prompt.
                stream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        channelCount: 1,
                        echoCancellation: true,
                        noiseSuppression: true
                    }
                });

                this.state.audioStream = stream;
                this.state.micPermissionState = 'granted';
                try {
                    localStorage.setItem('astra_care_mic_permission', 'granted');
                } catch (e) {}

                // Attach track ended listeners for automatic stream invalidation
                stream.getAudioTracks().forEach(track => {
                    track.onended = () => {
                        if (this.state.audioStream === stream) {
                            this.state.audioStream = null;
                        }
                    };
                });
            }

            this.state.audioChunks = [];

            let mimeType = '';
            if (typeof MediaRecorder !== 'undefined') {
                if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) mimeType = 'audio/webm;codecs=opus';
                else if (MediaRecorder.isTypeSupported('audio/webm')) mimeType = 'audio/webm';
                else if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) mimeType = 'audio/ogg;codecs=opus';
                else if (MediaRecorder.isTypeSupported('audio/wav')) mimeType = 'audio/wav';
            }

            const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
            recorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) {
                    this.state.audioChunks.push(event.data);
                }
            };

            recorder.onstop = async () => {
                // Now that MediaRecorder has gathered all frames, cleanly stop audio tracks
                if (this.state.audioStream) {
                    try {
                        this.state.audioStream.getTracks().forEach(track => {
                            track.stop();
                        });
                    } catch (e) {}
                    this.state.audioStream = null;
                }
                await this.processRecordedAudio();
            };

            this.state.mediaRecorder = recorder;
            recorder.start();
            this.state.isListening = true;
            this.setRecordingBannerState('listening');
        } catch (err) {
            console.error('[ASTRA CARE] Microphone access error:', err);
            let errMsg = 'Could not access microphone.';

            if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                this.state.micPermissionState = 'denied';
                try {
                    localStorage.setItem('astra_care_mic_permission', 'denied');
                } catch (e) {}
                errMsg = 'Microphone permission was denied. Click the lock/settings icon in the browser address bar to allow microphone access.';
                this.updateVoiceStatusUI('VOICE INPUT PERMISSION DENIED', 'permission_denied');
            } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
                errMsg = 'No microphone device was detected on your system. Please connect an audio input device.';
                this.updateVoiceStatusUI('VOICE INPUT UNAVAILABLE', 'input_unavailable');
            } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
                errMsg = 'Microphone is already in use by another application or OS service. Please close other audio apps and try again.';
                this.updateVoiceStatusUI('VOICE INPUT UNAVAILABLE', 'input_unavailable');
            } else if (err.name === 'OverconstrainedError') {
                errMsg = 'Requested audio settings not supported. Attempting basic microphone fallback...';
                try {
                    const fallbackStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    this.state.audioStream = fallbackStream;
                    this.state.micPermissionState = 'granted';
                    try {
                        localStorage.setItem('astra_care_mic_permission', 'granted');
                    } catch (e) {}
                    return this.startVoiceRecording();
                } catch (fbErr) {
                    errMsg = 'Microphone constraints cannot be satisfied by the hardware.';
                    this.updateVoiceStatusUI('VOICE INPUT UNAVAILABLE', 'input_unavailable');
                }
            } else if (err.name === 'SecurityError') {
                errMsg = 'Microphone access is restricted by browser security policies. Please access ASTRA CARE over localhost or HTTPS.';
                this.updateVoiceStatusUI('VOICE INPUT UNAVAILABLE', 'input_unavailable');
            }

            showToast(errMsg, 'error');
            this.setRecordingBannerState('error', errMsg);
            this.state.isListening = false;
        }
    },

    /**
     * Stops listening to microphone, flushes recording data, and stops audio tracks cleanly.
     */
    async stopVoiceRecording() {
        if (!this.state.isListening) {
            return;
        }
        this.state.isListening = false;

        if (this.state.mediaRecorder && this.state.mediaRecorder.state !== 'inactive') {
            try {
                if (this.state.mediaRecorder.state === 'recording') {
                    this.state.mediaRecorder.requestData();
                }
                this.state.mediaRecorder.stop();
            } catch (recErr) {
                console.warn('[ASTRA CARE] Error stopping mediaRecorder:', recErr);
            }
        } else {
            // Stop microphone tracks properly if recorder was already stopped
            if (this.state.audioStream) {
                try {
                    this.state.audioStream.getTracks().forEach(track => {
                        track.stop();
                    });
                } catch (streamErr) {
                    console.warn('[ASTRA CARE] Error stopping audio tracks:', streamErr);
                }
                this.state.audioStream = null;
            }
        }
    },

    /**
     * Alias for stopVoiceRecording to prevent callsite mismatch.
     */
    stopVoiceRecognition() {
        return this.stopVoiceRecording();
    },

    /**
     * Processes captured audio, converts to 16 kHz WAV, and sends to Vosk STT.
     */
    async processRecordedAudio() {
        if (!this.state.audioChunks || this.state.audioChunks.length === 0) {
            this.setRecordingBannerState('idle');
            return;
        }

        this.state.isProcessingAudio = true;
        this.setRecordingBannerState('processing');

        try {
            const rawBlob = new Blob(this.state.audioChunks, {
                type: this.state.mediaRecorder?.mimeType || 'audio/webm'
            });

            // Convert in browser to standard 16 kHz mono 16-bit PCM WAV
            let wavBlob;
            try {
                wavBlob = await this.convertBlobTo16kWav(rawBlob);
            } catch (convErr) {
                console.error('[ASTRA CARE] Audio conversion error:', convErr);
                throw new Error('Audio conversion failed. Please try speaking again.');
            }

            const formData = new FormData();
            formData.append('file', wavBlob, 'recording.wav');

            const endpoint = (typeof CONFIG !== 'undefined' && CONFIG.ENDPOINTS && CONFIG.ENDPOINTS.VOICE_TO_TEXT)
                ? CONFIG.ENDPOINTS.VOICE_TO_TEXT
                : '/api/assistant/voice-to-text';

            const url = getAssistantApiUrl(endpoint);

            const response = await fetch(url, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                const msg = errData?.detail?.message || errData?.detail?.error || `Server error (HTTP ${response.status})`;
                throw new Error(msg);
            }

            const data = await response.json();
            const recognizedText = data.text ? data.text.trim() : '';

            if (recognizedText) {
                this.setRecordingBannerState('complete');
                const inputEl = document.getElementById('assistant-chat-input');
                if (inputEl) {
                    inputEl.value = recognizedText;
                    inputEl.focus();
                }
                showToast('Speech recognized. You may review and edit before sending.', 'success');
            } else {
                this.setRecordingBannerState('error', 'No clear speech detected. Please speak clearly into the microphone.');
                showToast('No clear speech was detected. Please try speaking again.', 'info');
            }
        } catch (err) {
            console.error('Offline STT error:', err);
            this.setRecordingBannerState('error', `Offline voice input error: ${err.message}`);
            showToast(`Offline voice recognition failed: ${err.message}`, 'error');
        } finally {
            this.state.isProcessingAudio = false;
            this.state.audioChunks = [];
        }
    },

    /**
     * Converts an audio blob into a 16 kHz mono 16-bit PCM WAV blob via Web Audio API.
     */
    async convertBlobTo16kWav(blob) {
        const arrayBuffer = await blob.arrayBuffer();
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) {
            return blob;
        }

        const audioCtx = new AudioContextClass();
        try {
            const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
            const targetSampleRate = 16000;
            const targetDuration = audioBuffer.duration;
            const targetLength = Math.max(1, Math.ceil(targetDuration * targetSampleRate));

            // Use native browser OfflineAudioContext for studio-grade, anti-aliased sinc resampling to 16 kHz
            const OfflineCtxClass = window.OfflineAudioContext || window.webkitOfflineAudioContext;
            let monoData;

            if (OfflineCtxClass) {
                const offlineCtx = new OfflineCtxClass(1, targetLength, targetSampleRate);
                const source = offlineCtx.createBufferSource();
                source.buffer = audioBuffer;
                source.connect(offlineCtx.destination);
                source.start(0);
                const rendered = await offlineCtx.startRendering();
                monoData = rendered.getChannelData(0);
            } else {
                // Fallback manual downmix and linear interpolation if OfflineAudioContext unavailable
                const numChannels = audioBuffer.numberOfChannels;
                const length = audioBuffer.length;
                const origRate = audioBuffer.sampleRate;
                const tempMono = new Float32Array(length);
                for (let c = 0; c < numChannels; c++) {
                    const chData = audioBuffer.getChannelData(c);
                    for (let i = 0; i < length; i++) {
                        tempMono[i] += chData[i] / numChannels;
                    }
                }
                if (origRate === targetSampleRate) {
                    monoData = tempMono;
                } else {
                    const ratio = origRate / targetSampleRate;
                    const newLength = Math.round(length / ratio);
                    monoData = new Float32Array(newLength);
                    for (let i = 0; i < newLength; i++) {
                        const origIndex = i * ratio;
                        const floor = Math.floor(origIndex);
                        const ceil = Math.min(floor + 1, length - 1);
                        const frac = origIndex - floor;
                        monoData[i] = tempMono[floor] * (1 - frac) + tempMono[ceil] * frac;
                    }
                }
            }

            const numSamples = monoData.length;

            // Audio Preprocessing: Remove DC offset
            let sum = 0;
            for (let i = 0; i < numSamples; i++) {
                sum += monoData[i];
            }
            const dcOffset = numSamples > 0 ? (sum / numSamples) : 0;

            let maxAbs = 0;
            for (let i = 0; i < numSamples; i++) {
                const sample = monoData[i] - dcOffset;
                const abs = Math.abs(sample);
                if (abs > maxAbs) maxAbs = abs;
            }

            // Normalization gain: gently boost quiet microphone input (up to ~3.5x boost, targeting ~0.85 peak)
            let gain = 1.0;
            if (maxAbs > 0.01 && maxAbs < 0.70) {
                gain = Math.min(3.5, 0.85 / maxAbs);
            }

            // Build standard 16 kHz 16-bit Mono PCM WAV
            const buffer = new ArrayBuffer(44 + numSamples * 2);
            const view = new DataView(buffer);

            const writeString = (view, offset, str) => {
                for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
            };

            writeString(view, 0, 'RIFF');
            view.setUint32(4, 36 + numSamples * 2, true);
            writeString(view, 8, 'WAVE');
            writeString(view, 12, 'fmt ');
            view.setUint32(16, 16, true);
            view.setUint16(20, 1, true); // PCM format
            view.setUint16(22, 1, true); // 1 Channel (Mono)
            view.setUint32(24, targetSampleRate, true); // 16000 Hz
            view.setUint32(28, targetSampleRate * 2, true); // Byte rate (16000 * 2)
            view.setUint16(32, 2, true); // Block align (1 * 16/8)
            view.setUint16(34, 16, true); // 16 bits per sample
            writeString(view, 36, 'data');
            view.setUint32(40, numSamples * 2, true);

            let offset = 44;
            for (let i = 0; i < numSamples; i++) {
                const centered = (monoData[i] - dcOffset) * gain;
                const s = Math.max(-1.0, Math.min(1.0, centered));
                view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
                offset += 2;
            }

            return new Blob([buffer], { type: 'audio/wav' });
        } finally {
            try {
                await audioCtx.close();
            } catch (e) {}
        }
    },

    /**
     * Updates Recording Banner UI across states: Listening, Processing, Complete, Error.
     */
    setRecordingBannerState(state, customText) {
        const banner = document.getElementById('assistant-voice-listening-banner');
        const iconEl = document.getElementById('voice-banner-state-icon');
        const textEl = document.getElementById('voice-banner-text');
        const micBtn = document.getElementById('btn-assistant-voice-input');

        if (!banner) return;

        banner.className = '';
        if (state === 'listening') {
            banner.style.display = 'flex';
            banner.classList.add('state-listening');
            if (iconEl) iconEl.textContent = '🎙️ LISTENING:';
            if (textEl) textEl.textContent = customText || 'Speak your question clearly... Click mic button when finished.';
            if (micBtn) {
                micBtn.classList.add('listening-active');
                micBtn.title = 'Stop recording speech';
            }
        } else if (state === 'processing') {
            banner.style.display = 'flex';
            banner.classList.add('state-processing');
            if (iconEl) iconEl.textContent = '⏳ PROCESSING:';
            if (textEl) textEl.textContent = customText || 'Transcribing audio with local Vosk speech model...';
            if (micBtn) {
                micBtn.classList.remove('listening-active');
                micBtn.title = 'Processing audio...';
            }
        } else if (state === 'complete') {
            banner.style.display = 'flex';
            banner.classList.add('state-complete');
            if (iconEl) iconEl.textContent = '✅ COMPLETE:';
            if (textEl) textEl.textContent = customText || 'Transcription complete. Review or edit your question before sending.';
            if (micBtn) {
                micBtn.classList.remove('listening-active');
                micBtn.title = 'Speak your question (Microphone)';
            }
            setTimeout(() => {
                if (!this.state.isListening && !this.state.isProcessingAudio) {
                    banner.style.display = 'none';
                }
            }, 3500);
        } else if (state === 'error') {
            banner.style.display = 'flex';
            banner.classList.add('state-error');
            if (iconEl) iconEl.textContent = '⚠️ NOTICE:';
            if (textEl) textEl.textContent = customText || 'Voice recognition encountered an issue.';
            if (micBtn) {
                micBtn.classList.remove('listening-active');
                micBtn.title = 'Speak your question (Microphone)';
            }
            setTimeout(() => {
                if (!this.state.isListening && !this.state.isProcessingAudio) {
                    banner.style.display = 'none';
                }
            }, 4000);
        } else {
            banner.style.display = 'none';
            if (micBtn) {
                micBtn.classList.remove('listening-active');
                micBtn.title = 'Speak your question (Microphone)';
            }
        }
    },

    /**
     * Speaks assistant text response aloud using offline pyttsx3 Windows SAPI5 TTS.
     */
    async speakText(messageId, fullText, buttonEl) {
        if (!this.state.ttsSupported) {
            showToast('Offline text-to-speech is currently unavailable.', 'warning');
            return;
        }

        // Toggle pause / play if this exact message is currently active
        if (this.state.currentlyPlayingId === messageId && this.state.audioPlayer) {
            if (!this.state.audioPlayer.paused) {
                this.pauseSpeech();
                return;
            } else if (this.state.audioPlayer.paused && this.state.audioPlayer.currentTime > 0) {
                this.resumeSpeech();
                return;
            }
        }

        // Clean text: strip markdown bullets, bolding, and technical disclaimers
        const cleanText = fullText
            .replace(/[•\-\*\_]/g, ' ')
            .replace(/Scientific Note:.*$/i, '')
            .replace(/Operational Reminder:.*$/i, '')
            .replace(/\s+/g, ' ')
            .trim();

        if (!cleanText) return;

        // Stop any current audio
        this.stopSpeech();

        // Update button state to loading
        if (buttonEl) {
            buttonEl.classList.add('playing');
            const span = buttonEl.querySelector('span');
            if (span) span.textContent = 'Loading...';
        }

        try {
            const endpoint = (typeof CONFIG !== 'undefined' && CONFIG.ENDPOINTS && CONFIG.ENDPOINTS.TEXT_TO_SPEECH)
                ? CONFIG.ENDPOINTS.TEXT_TO_SPEECH
                : '/api/assistant/text-to-speech';

            const url = getAssistantApiUrl(endpoint);

            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: cleanText,
                    rate: 175
                })
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                const msg = errData?.detail?.message || `Server error (HTTP ${response.status})`;
                throw new Error(msg);
            }

            const audioBlob = await response.blob();
            if (this.state.currentAudioUrl) {
                URL.revokeObjectURL(this.state.currentAudioUrl);
            }
            this.state.currentAudioUrl = URL.createObjectURL(audioBlob);

            if (!this.state.audioPlayer) {
                this.state.audioPlayer = new Audio();
            }
            this.state.audioPlayer.src = this.state.currentAudioUrl;
            this.state.currentlyPlayingId = messageId;
            this.state.isPaused = false;

            this.state.audioPlayer.onended = () => {
                this.resetTTSState();
            };
            this.state.audioPlayer.onerror = (e) => {
                console.warn('Audio playback error:', e);
                this.resetTTSState();
                showToast('Could not play synthesized audio.', 'error');
            };

            await this.state.audioPlayer.play();

            if (buttonEl) {
                const span = buttonEl.querySelector('span');
                if (span) span.textContent = 'Pause';
            }
            this.updateTTSGlobalControls(true, false);
        } catch (err) {
            console.error('Offline TTS error:', err);
            this.resetTTSState();
            showToast(`Offline voice output failed: ${err.message}`, 'warning');
        }
    },

    /**
     * Pauses current offline speech playback.
     */
    pauseSpeech() {
        if (this.state.audioPlayer && !this.state.audioPlayer.paused) {
            this.state.audioPlayer.pause();
            this.state.isPaused = true;
            this.updateTTSGlobalControls(true, true);
            const activeBtn = document.querySelector(`.chat-message-row#${this.state.currentlyPlayingId} .btn-msg-speak span`);
            if (activeBtn) activeBtn.textContent = 'Resume';
        }
    },

    /**
     * Resumes paused offline speech playback.
     */
    resumeSpeech() {
        if (this.state.audioPlayer && this.state.audioPlayer.paused) {
            this.state.audioPlayer.play().catch(e => console.warn(e));
            this.state.isPaused = false;
            this.updateTTSGlobalControls(true, false);
            const activeBtn = document.querySelector(`.chat-message-row#${this.state.currentlyPlayingId} .btn-msg-speak span`);
            if (activeBtn) activeBtn.textContent = 'Pause';
        }
    },

    /**
     * Stops offline speech playback immediately.
     */
    stopSpeech() {
        if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
            window.speechSynthesis.cancel();
        }
        if (this.state.audioPlayer) {
            this.state.audioPlayer.pause();
            this.state.audioPlayer.currentTime = 0;
        }
        if (this.state.currentAudioUrl) {
            URL.revokeObjectURL(this.state.currentAudioUrl);
            this.state.currentAudioUrl = null;
        }
        this.resetTTSState();
    },

    /**
     * Resets speech synthesis state and UI controls.
     */
    resetTTSState() {
        this.state.currentlyPlayingId = null;
        this.state.isPaused = false;

        document.querySelectorAll('.btn-msg-speak').forEach(btn => {
            btn.classList.remove('playing');
            const span = btn.querySelector('span');
            if (span) span.textContent = 'Listen';
        });

        this.updateTTSGlobalControls(false);
    },

    /**
     * Toggles visibility of global TTS floating controller bar.
     */
    updateTTSGlobalControls(isActive, isPaused = false) {
        const bar = document.getElementById('assistant-tts-global-bar');
        const pauseBtn = document.getElementById('btn-tts-pause');
        const resumeBtn = document.getElementById('btn-tts-resume');

        if (!bar) return;

        if (isActive) {
            bar.style.display = 'flex';
            if (pauseBtn) pauseBtn.style.display = isPaused ? 'none' : 'inline-flex';
            if (resumeBtn) resumeBtn.style.display = isPaused ? 'inline-flex' : 'none';
        } else {
            bar.style.display = 'none';
        }
    },

    /**
     * Checks offline voice status (Vosk STT & SAPI5 TTS) from backend.
     */
    async fetchVoiceStatus() {
        const badge = document.getElementById('assistant-voice-badge');
        if (!badge) return;

        try {
            const endpoint = (typeof CONFIG !== 'undefined' && CONFIG.ENDPOINTS && CONFIG.ENDPOINTS.VOICE_STATUS)
                ? CONFIG.ENDPOINTS.VOICE_STATUS
                : '/api/assistant/voice/status';
            const url = getAssistantApiUrl(endpoint);

            const res = await fetch(url);
            if (res.ok) {
                const data = await res.json();
                this.state.voiceStatus = data;
                this.updateVoiceStatusUI(data.indicator_text, data.status);
                if (data.network_indicator) {
                    this.updateNetworkStatusUI(data.network_indicator, data.is_online ?? true);
                }
            } else {
                this.updateVoiceStatusUI('VOICE INPUT UNAVAILABLE', 'input_unavailable');
            }
        } catch (err) {
            this.updateVoiceStatusUI('VOICE INPUT UNAVAILABLE', 'input_unavailable');
        }
    },

    /**
     * Updates Voice Status Indicator Badge.
     */
    updateVoiceStatusUI(indicatorText, statusKey) {
        const badge = document.getElementById('assistant-voice-badge');
        if (!badge) return;

        badge.textContent = indicatorText || 'OFFLINE VOICE READY';

        if (statusKey === 'ready' || indicatorText === 'OFFLINE VOICE READY') {
            badge.className = 'badge-tag normal';
            badge.title = 'Local Vosk Speech-to-Text and Windows SAPI5 TTS operational (100% Offline)';
            this.state.speechSupported = true;
            this.state.ttsSupported = true;
        } else if (statusKey === 'permission_denied' || indicatorText === 'VOICE INPUT PERMISSION DENIED') {
            badge.className = 'badge-tag danger';
            badge.title = 'Microphone permission denied. Enable microphone access in browser site settings.';
            this.state.speechSupported = false;
        } else if (statusKey === 'setup_required' || indicatorText === 'INITIAL SETUP REQUIRED') {
            badge.className = 'badge-tag warning';
            badge.title = 'Vosk speech model not installed. Initial setup required.';
            this.state.speechSupported = false;
        } else if (statusKey === 'output_unavailable' || indicatorText === 'VOICE OUTPUT UNAVAILABLE') {
            badge.className = 'badge-tag warning';
            badge.title = 'Local TTS voice unavailable.';
            this.state.ttsSupported = false;
        } else {
            badge.className = 'badge-tag danger';
            badge.title = 'Offline voice service unavailable.';
            this.state.speechSupported = false;
        }
    },

    /**
     * Checks local AI assistant connection status from backend.
     */
    async fetchAssistantStatus() {
        const badge = document.getElementById('assistant-connection-badge');
        if (!badge) return;
        try {
            const endpoint = (typeof CONFIG !== 'undefined' && CONFIG.ENDPOINTS && CONFIG.ENDPOINTS.ASSISTANT_STATUS)
                ? CONFIG.ENDPOINTS.ASSISTANT_STATUS
                : '/api/assistant/status';
            const url = getAssistantApiUrl(endpoint);
            const res = await fetch(url);
            if (res.ok) {
                const data = await res.json();
                badge.textContent = data.indicator_text || 'LOCAL FALLBACK MODE';
                if (data.status === 'connected') {
                    badge.className = 'badge-tag normal';
                    badge.title = `Local AI Model: ${data.model} (Ollama 100% Offline)`;
                } else if (data.status === 'fallback') {
                    badge.className = 'badge-tag warning';
                    badge.title = 'Running on local deterministic Python telemetry engine';
                } else {
                    badge.className = 'badge-tag danger';
                    badge.title = 'Local AI service unavailable';
                }
                if (data.network_indicator) {
                    this.updateNetworkStatusUI(data.network_indicator, data.is_online ?? true);
                }
            } else {
                badge.textContent = 'LOCAL FALLBACK MODE';
                badge.className = 'badge-tag warning';
            }
        } catch (err) {
            badge.textContent = 'LOCAL FALLBACK MODE';
            badge.className = 'badge-tag warning';
        }
    },

    /**
     * Checks network connectivity status (Online vs Offline mode).
     * Distinguishes ONLINE – INTERNET AVAILABLE from OFFLINE – LOCAL SERVICES ACTIVE.
     */
    async fetchNetworkStatus() {
        const badge = document.getElementById('assistant-network-badge');
        if (!badge) return;

        try {
            const endpoint = (typeof CONFIG !== 'undefined' && CONFIG.ENDPOINTS && CONFIG.ENDPOINTS.NETWORK_STATUS)
                ? CONFIG.ENDPOINTS.NETWORK_STATUS
                : '/api/system/network-status';
            const url = getAssistantApiUrl(endpoint);

            const res = await fetch(url);
            if (res.ok) {
                const data = await res.json();
                this.state.isOnline = !!data.is_online;
                this.state.networkStatus = data;
                this.updateNetworkStatusUI(data.indicator_text, data.is_online);
            } else {
                const isOnline = navigator.onLine !== false;
                this.updateNetworkStatusUI(
                    isOnline ? 'ONLINE – INTERNET AVAILABLE' : 'OFFLINE – LOCAL SERVICES ACTIVE',
                    isOnline
                );
            }
        } catch (err) {
            const isOnline = navigator.onLine !== false;
            this.updateNetworkStatusUI(
                isOnline ? 'ONLINE – INTERNET AVAILABLE' : 'OFFLINE – LOCAL SERVICES ACTIVE',
                isOnline
            );
        }
    },

    /**
     * Updates Network Status Indicator Badge with exact required aerospace labels:
     * - 'ONLINE – INTERNET AVAILABLE'
     * - 'OFFLINE – LOCAL SERVICES ACTIVE'
     */
    updateNetworkStatusUI(indicatorText, isOnline) {
        const badge = document.getElementById('assistant-network-badge');
        if (!badge) return;

        const text = indicatorText || (isOnline ? 'ONLINE – INTERNET AVAILABLE' : 'OFFLINE – LOCAL SERVICES ACTIVE');
        badge.textContent = text;

        if (isOnline) {
            badge.className = 'badge-tag normal';
            badge.title = 'External internet available: NASA RadLab live sync & online services active';
        } else {
            badge.className = 'badge-tag info';
            badge.title = 'Offline airgapped mode: 100% local Vosk STT, Windows SAPI5 TTS, and local AI active';
        }
    },

    /**
     * Clears all messages from chat history.
     */
    clearChat() {
        this.stopSpeech();
        this.stopVoiceRecognition();

        this.state.messages = [];
        const messagesContainer = document.getElementById('assistant-chat-messages');
        if (messagesContainer) {
            messagesContainer.innerHTML = '';
        }

        // Welcome back message
        this.addAssistantMessage({
            answer: "Chat cleared. What aspect of your radiation exposure or vital signs would you like to review?",
            source: "knowledge_base",
            status: "success",
            data_context: null
        });

        showToast('Chat history cleared.', 'info');
    },

    /**
     * Smoothly scrolls chat feed to latest message.
     */
    scrollToBottom() {
        const messagesContainer = document.getElementById('assistant-chat-messages');
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }
};

// Export to window for global access
window.AssistantModule = AssistantModule;
