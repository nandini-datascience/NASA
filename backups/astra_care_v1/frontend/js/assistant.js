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
 *    - Web Speech API (SpeechSynthesis / SpeechSynthesisUtterance).
 *    - Per-message speaker button and global speech control toolbar (Pause, Resume, Stop).
 *    - Prevents overlapping audio (cancels previous utterance).
 *    - Strips markdown and technical metadata, speaking only clean conversational text.
 */

const AssistantModule = {
    // Component State
    state: {
        messages: [],
        isListening: false,
        recognition: null,
        speechSupported: false,
        ttsSupported: false,
        synth: null,
        currentUtterance: null,
        currentVoice: null,
        currentlyPlayingId: null,
        isPaused: false,
        isLoading: false,
        selectedAstronautId: 'AST-01'
    },

    // Suggested Questions for Space Crew
    suggestedQuestions: [
        "Explain my latest radiation reading",
        "What is absorbed dose?",
        "What is dose equivalent?",
        "Why is space radiation dangerous?",
        "Explain my health measurements",
        "What does this alert mean?",
        "What should I do when an abnormal alert appears?",
        "Explain the difference between GCR and SPE",
        "Summarize my recent monitoring data"
    ],

    /**
     * Initializes the AI Assistant UI, speech recognition, and speech synthesis.
     */
    init() {
        console.log('Initializing ASTRA CARE AI Health & Voice Assistant...');

        // 1. Check Web Speech API Support
        this.initSpeechRecognition();
        this.initSpeechSynthesis();

        // 2. Bind DOM Event Listeners
        this.bindEvents();

        // 3. Render Suggested Questions Chips
        this.renderSuggestedQuestions();

        // 4. Initial Welcome Message
        if (this.state.messages.length === 0) {
            this.addAssistantMessage({
                answer: "Greetings, crew member. I am your ASTRA CARE AI Health and Radiation Assistant.\n\n" +
                        "I can explain your radiation dosimetry, vital signs, telemetry statuses, and active alerts " +
                        "in plain language. You can type your questions or use the microphone to speak.",
                source: "knowledge_base",
                status: "success",
                data_context: null
            });
        }

        console.log('AI Health Assistant initialized.');
    },

    /**
     * Configures Web Speech API SpeechRecognition (Voice Input).
     */
    initSpeechRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            this.state.speechSupported = true;
            try {
                const recognition = new SpeechRecognition();
                recognition.continuous = false;
                recognition.interimResults = true;
                recognition.lang = 'en-US';

                recognition.onstart = () => {
                    this.state.isListening = true;
                    this.updateVoiceInputUI(true);
                };

                recognition.onresult = (event) => {
                    let interimTranscript = '';
                    let finalTranscript = '';

                    for (let i = event.resultIndex; i < event.results.length; ++i) {
                        const transcript = event.results[i][0].transcript;
                        if (event.results[i].isFinal) {
                            finalTranscript += transcript;
                        } else {
                            interimTranscript += transcript;
                        }
                    }

                    const inputEl = document.getElementById('assistant-chat-input');
                    if (inputEl) {
                        // Place recognized speech into the input field for user review and editing
                        const recognizedText = finalTranscript || interimTranscript;
                        inputEl.value = recognizedText;
                        inputEl.focus();
                    }
                };

                recognition.onerror = (event) => {
                    console.warn('SpeechRecognition error:', event.error);
                    this.state.isListening = false;
                    this.updateVoiceInputUI(false);

                    let errMsg = 'Voice recognition encountered an issue.';
                    if (event.error === 'not-allowed') {
                        errMsg = 'Microphone permission was denied. Please allow microphone access in your browser settings to speak.';
                    } else if (event.error === 'no-speech') {
                        errMsg = 'No speech was detected. Please try speaking again.';
                    }
                    showToast(errMsg, 'error');
                };

                recognition.onend = () => {
                    this.state.isListening = false;
                    this.updateVoiceInputUI(false);
                };

                this.state.recognition = recognition;
            } catch (err) {
                console.warn('SpeechRecognition initialization error:', err);
                this.state.speechSupported = false;
            }
        } else {
            this.state.speechSupported = false;
            console.log('Web SpeechRecognition API not supported in this browser environment.');
        }
    },

    /**
     * Configures Web Speech API SpeechSynthesis (Voice Output).
     */
    initSpeechSynthesis() {
        if ('speechSynthesis' in window) {
            this.state.ttsSupported = true;
            this.state.synth = window.speechSynthesis;

            const setBestVoice = () => {
                const voices = this.state.synth.getVoices();
                if (voices && voices.length > 0) {
                    // Prefer natural-sounding English voices
                    const preferred = voices.find(v => v.lang.startsWith('en') && (
                        v.name.includes('Natural') || 
                        v.name.includes('Google') || 
                        v.name.includes('Samantha') || 
                        v.name.includes('David') || 
                        v.name.includes('Daniel')
                    )) || voices.find(v => v.lang.startsWith('en')) || voices[0];
                    this.state.currentVoice = preferred;
                }
            };

            setBestVoice();
            if (this.state.synth.onvoiceschanged !== undefined) {
                this.state.synth.onvoiceschanged = setBestVoice;
            }
        } else {
            this.state.ttsSupported = false;
            console.log('Web SpeechSynthesis API not supported in this browser environment.');
        }
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
     * Toggles Voice Input (SpeechRecognition).
     */
    toggleVoiceRecognition() {
        if (!this.state.speechSupported) {
            showToast('Voice speech recognition is not supported in this browser. You can still type questions normally.', 'info');
            return;
        }

        if (this.state.isListening) {
            this.stopVoiceRecognition();
        } else {
            this.startVoiceRecognition();
        }
    },

    /**
     * Starts listening to user microphone.
     */
    startVoiceRecognition() {
        if (!this.state.recognition) return;

        // Stop any active text-to-speech output first
        this.stopSpeech();

        try {
            this.state.recognition.start();
        } catch (err) {
            console.warn('Could not start SpeechRecognition:', err);
        }
    },

    /**
     * Stops listening to microphone.
     */
    stopVoiceRecognition() {
        if (this.state.recognition) {
            try {
                this.state.recognition.stop();
            } catch (err) {
                // Ignore if already stopped
            }
        }
        this.state.isListening = false;
        this.updateVoiceInputUI(false);
    },

    /**
     * Updates Microphone UI (glowing red animation when listening).
     * 
     * @param {boolean} isListening 
     */
    updateVoiceInputUI(isListening) {
        const micBtn = document.getElementById('btn-assistant-voice-input');
        const listeningBanner = document.getElementById('assistant-voice-listening-banner');

        if (micBtn) {
            if (isListening) {
                micBtn.classList.add('listening-active');
                micBtn.title = 'Stop listening';
            } else {
                micBtn.classList.remove('listening-active');
                micBtn.title = 'Speak your question (Microphone)';
            }
        }

        if (listeningBanner) {
            listeningBanner.style.display = isListening ? 'flex' : 'none';
        }
    },

    /**
     * Speaks the assistant text aloud via SpeechSynthesis.
     * Prevents overlapping audio, cleans markdown, and provides pause/stop controls.
     * 
     * @param {string} messageId 
     * @param {string} fullText 
     * @param {HTMLElement} buttonEl 
     */
    speakText(messageId, fullText, buttonEl) {
        if (!this.state.ttsSupported || !this.state.synth) {
            showToast('Speech synthesis (Voice Output) is not supported in this browser.', 'warning');
            return;
        }

        // If this exact message is currently speaking:
        if (this.state.currentlyPlayingId === messageId) {
            if (this.state.synth.speaking && !this.state.synth.paused) {
                this.pauseSpeech();
                return;
            } else if (this.state.synth.paused) {
                this.resumeSpeech();
                return;
            }
        }

        // Cancel any active speech to prevent simultaneous speech
        this.stopSpeech();

        // Clean text: strip markdown bullets, bolding, and technical disclaimers
        const cleanText = fullText
            .replace(/[•\-\*\_]/g, ' ')
            .replace(/Scientific Note:.*$/i, '')
            .replace(/Operational Reminder:.*$/i, '')
            .replace(/\s+/g, ' ')
            .trim();

        if (!cleanText) return;

        const utterance = new SpeechSynthesisUtterance(cleanText);
        if (this.state.currentVoice) {
            utterance.voice = this.state.currentVoice;
        }
        utterance.rate = 1.0;
        utterance.pitch = 1.0;

        utterance.onstart = () => {
            this.state.currentlyPlayingId = messageId;
            this.state.isPaused = false;
            this.updateTTSGlobalControls(true);
            if (buttonEl) {
                buttonEl.classList.add('playing');
                buttonEl.querySelector('span').textContent = 'Pause';
            }
        };

        utterance.onpause = () => {
            this.state.isPaused = true;
            this.updateTTSGlobalControls(true, true);
            if (buttonEl) {
                buttonEl.querySelector('span').textContent = 'Resume';
            }
        };

        utterance.onresume = () => {
            this.state.isPaused = false;
            this.updateTTSGlobalControls(true, false);
            if (buttonEl) {
                buttonEl.querySelector('span').textContent = 'Pause';
            }
        };

        utterance.onend = () => {
            this.resetTTSState();
        };

        utterance.onerror = (e) => {
            console.warn('SpeechSynthesis error:', e);
            this.resetTTSState();
        };

        this.state.currentUtterance = utterance;
        this.state.synth.speak(utterance);
    },

    /**
     * Pauses current speech synthesis.
     */
    pauseSpeech() {
        if (this.state.synth && this.state.synth.speaking) {
            this.state.synth.pause();
            this.state.isPaused = true;
            this.updateTTSGlobalControls(true, true);
        }
    },

    /**
     * Resumes paused speech synthesis.
     */
    resumeSpeech() {
        if (this.state.synth && this.state.synth.paused) {
            this.state.synth.resume();
            this.state.isPaused = false;
            this.updateTTSGlobalControls(true, false);
        }
    },

    /**
     * Stops speech synthesis immediately.
     */
    stopSpeech() {
        if (this.state.synth) {
            this.state.synth.cancel();
        }
        this.resetTTSState();
    },

    /**
     * Resets speech synthesis state and UI.
     */
    resetTTSState() {
        this.state.currentlyPlayingId = null;
        this.state.currentUtterance = null;
        this.state.isPaused = false;

        document.querySelectorAll('.btn-msg-speak').forEach(btn => {
            btn.classList.remove('playing');
            btn.querySelector('span').textContent = 'Listen';
        });

        this.updateTTSGlobalControls(false);
    },

    /**
     * Toggles visibility of global TTS floating controller bar.
     * 
     * @param {boolean} isActive 
     * @param {boolean} isPaused 
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
