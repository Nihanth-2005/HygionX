// Chat functionality for HygionX Health Assistant

class ChatInterface {
    constructor() {
        this.messagesContainer = document.getElementById('messagesContainer');
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.voiceButton = document.getElementById('voiceButton');
        this.typingIndicator = document.getElementById('typingIndicator');

        this.isTyping = false;
        this.messages = [];

        // ── Conversation memory (fixes the loop bug) ──────────────────────
        this.previousSymptoms = [];   // symptoms accumulated across turns
        this.followupCount = 0;       // how many follow-up questions asked so far
        this.MAX_FOLLOWUPS = 4;       // stop asking after this many follow-ups
        // ─────────────────────────────────────────────────────────────────

        this.initializeEventListeners();
        this.loadChatHistory();
    }

    initializeEventListeners() {

        this.sendButton.addEventListener('click', () => this.sendMessage());

        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        this.messageInput.addEventListener('input', () => {
            this.messageInput.style.height = 'auto';
            this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 120) + 'px';
        });

        if (this.voiceButton) {
            this.voiceButton.addEventListener('click', () => this.toggleVoiceInput());
        }

        document.querySelectorAll('.sidebar-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleSidebarNavigation(item);
            });
        });

        const logoutBtn = document.querySelector('button:has(.fa-sign-out-alt)');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => this.signOut());
        }
    }

    async sendMessage() {

        const message = this.messageInput.value.trim();
        if (!message || this.isTyping) return;

        // Remove any existing follow-up option buttons so they don't pile up
        this._removeFollowupOptions();

        this.addMessage(message, 'user');

        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';

        this.showTypingIndicator();

        try {

            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: message,
                    session_id: this.getSessionId(),
                    // ── Send accumulated symptoms back so backend remembers context ──
                    previous_symptoms: this.previousSymptoms,
                    followup_count: this.followupCount,
                    force_triage: this.followupCount >= this.MAX_FOLLOWUPS
                    // ─────────────────────────────────────────────────────────────────
                })
            });

            if (!response.ok) {
                throw new Error('Failed to send message');
            }

            const data = await response.json();

            this.hideTypingIndicator();

            // ── Save any newly detected symptoms ──────────────────────────
            if (data.symptoms && Array.isArray(data.symptoms)) {
                this._mergeSymptoms(data.symptoms);
            }
            // ─────────────────────────────────────────────────────────────

            // FOLLOW-UP MODE
            if (data.type === 'followup') {

                // ── Guard: too many follow-ups → force a triage response ──
                if (this.followupCount >= this.MAX_FOLLOWUPS) {
                    this.addMessage(
                        "Based on what you've told me so far, let me give you an assessment. " +
                        "You can continue to describe any other symptoms in the chat.",
                        'assistant'
                    );
                    // Don't increment or show more follow-up buttons; let the next message go to triage
                    return;
                }
                // ─────────────────────────────────────────────────────────

                this.followupCount++;

                // ── Bug fix: backend returns `question` (string), not `questions` ──
                const questionText = data.question ||
                    (Array.isArray(data.questions) && data.questions[0]) ||
                    'Can you describe your symptoms in more detail?';
                // ──────────────────────────────────────────────────────────────────

                this.addMessage(questionText, 'assistant');

                // ── Bug fix: pass the full data object which has answer_type & options ──
                this.renderFollowupOptions(data);
                // ─────────────────────────────────────────────────────────────────────

                return;
            }

            // Reset follow-up counter once we reach a triage/emergency response
            this.followupCount = 0;

            // EMERGENCY RESPONSE
            if (data.type === 'emergency') {
                this.addMessage(
                    data.message || data.response || 'Please seek immediate medical attention.',
                    'assistant',
                    null,
                    'high'
                );
                return;
            }

            // NORMAL TRIAGE RESPONSE
            this.addMessage(
                data.response || data.explanation || data.assessment || data.message,
                'assistant',
                data.confidence,
                data.urgency
            );

            this.updateSessionSummary(data.session_summary);
            this.updateConfidenceScore(data.confidence);

            if (data.red_flag) {
                this.updateRedFlagIndicator(data.red_flag);
            }

        } catch (error) {

            console.error('Error sending message:', error);
            this.hideTypingIndicator();
            this.addMessage(
                'Sorry, I encountered an error. Please try again.',
                'assistant',
                0
            );
        }
    }

    // ── Merge new symptoms into accumulated list (deduplication) ──────────
    _mergeSymptoms(newSymptoms) {
        const existing = new Set(this.previousSymptoms.map(s => s.toLowerCase().trim()));
        newSymptoms.forEach(s => {
            const key = (s || '').toLowerCase().trim();
            if (key && !existing.has(key)) {
                this.previousSymptoms.push(s);
                existing.add(key);
            }
        });
    }

    // ── Remove old follow-up option buttons before showing new ones ───────
    _removeFollowupOptions() {
        const old = this.messagesContainer.querySelector('.followup-options');
        if (old) old.remove();
    }
    // ─────────────────────────────────────────────────────────────────────

    addMessage(content, sender, confidence = null, urgency = null) {

        const messageDiv = document.createElement('div');
        messageDiv.className = `flex items-start space-x-3 ${sender === 'user' ? 'justify-end' : ''}`;

        const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        if (sender === 'user') {

            messageDiv.innerHTML = `
                <div class="message-bubble max-w-lg">
                    <div class="bg-blue-600 text-white rounded-lg shadow-sm p-4">
                        <p>${this.escapeHtml(content)}</p>
                    </div>
                    <p class="text-xs text-gray-500 mt-1 text-right">${timestamp}</p>
                </div>
                <div class="w-8 h-8 bg-gray-300 rounded-full flex items-center justify-center flex-shrink-0">
                    <i class="fas fa-user text-gray-600 text-sm"></i>
                </div>
            `;

        } else {

            messageDiv.innerHTML = `
                <div class="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
                    <i class="fas fa-robot text-blue-600 text-sm"></i>
                </div>
                <div class="message-bubble max-w-lg">
                    <div class="bg-white rounded-lg shadow-sm p-4">
                        <p>${this.escapeHtml(content)}</p>
                        ${confidence ? `<div class="mt-2 text-xs text-gray-500">Confidence: ${Math.round(confidence * 100)}%</div>` : ''}
                        ${urgency ? `<div class="mt-1 text-xs ${urgency === 'high' ? 'text-red-600' : urgency === 'moderate' ? 'text-yellow-600' : 'text-green-600'}">Urgency: ${urgency}</div>` : ''}
                    </div>
                    <p class="text-xs text-gray-500 mt-1">${timestamp}</p>
                </div>
            `;
        }

        this.messagesContainer.appendChild(messageDiv);
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;

        this.messages.push({ content, sender, timestamp, confidence, urgency });
        this.saveChatHistory();
    }

    /* FOLLOW-UP BUTTON RENDERER */

    renderFollowupOptions(data) {

        // ── Determine answer_type and options from the data object ────────
        const answerType = data.answer_type || 'text';
        const options = Array.isArray(data.options) ? data.options : [];
        const allowCustom = data.allow_custom_answer !== false; // default true
        // ─────────────────────────────────────────────────────────────────

        const container = document.createElement('div');
        container.className = 'followup-options flex flex-wrap gap-3 mt-3 ml-11';

        if (answerType === 'yes_no') {
            ['Yes', 'No'].forEach(opt => {
                container.appendChild(this.createOptionButton(opt));
            });

        } else if (answerType === 'multiple_choice' && options.length > 0) {
            options.forEach(opt => {
                container.appendChild(this.createOptionButton(opt));
            });

        } else if (answerType === 'scale_1_10') {
            for (let i = 1; i <= 10; i++) {
                container.appendChild(this.createOptionButton(i.toString()));
            }
        }

        // Always show a "None of these / describe" hint if no options or text type
        if (allowCustom && answerType === 'text') {
            const hint = document.createElement('p');
            hint.className = 'text-xs text-gray-400 w-full mt-1';
            hint.textContent = 'Type your answer below and press Enter.';
            container.appendChild(hint);
        }

        this.messagesContainer.appendChild(container);
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    createOptionButton(text) {

        const btn = document.createElement('button');
        btn.className = 'px-4 py-2 rounded-full border border-blue-200 bg-white text-blue-700 text-sm font-medium shadow-sm transition duration-200 hover:bg-blue-600 hover:text-white hover:shadow-md';
        btn.innerText = text;
        btn.style.cursor = 'pointer';

        btn.onclick = () => {
            this.sendCustomAnswer(text);
        };

        btn.addEventListener('mousedown', () => { btn.style.transform = 'scale(0.96)'; });
        btn.addEventListener('mouseup', () => { btn.style.transform = 'scale(1)'; });

        return btn;
    }

    sendCustomAnswer(answer) {
        this.messageInput.value = answer;
        this.sendMessage();
    }

    showTypingIndicator() {
        this.isTyping = true;
        if (this.typingIndicator) {
            this.typingIndicator.classList.remove('hidden');
            this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        }
    }

    hideTypingIndicator() {
        this.isTyping = false;
        if (this.typingIndicator) {
            this.typingIndicator.classList.add('hidden');
        }
    }

    toggleVoiceInput() {
        alert('Voice input coming soon.');
    }

    updateSessionSummary(summary) {
        const summaryCard = document.querySelector('.bg-blue-50');
        if (summaryCard && summary) {
            summaryCard.innerHTML = `
            <div class="flex items-center justify-between">
                <div>
                    <h3 class="text-sm font-semibold text-blue-900">Session Summary</h3>
                    <p class="text-xs text-blue-700 mt-1">${summary}</p>
                </div>
            </div>`;
        }
    }

    updateConfidenceScore(confidence) {
        const confidenceElement = document.querySelector('.text-blue-700');
        if (confidenceElement && confidence) {
            confidenceElement.textContent = `Confidence: ${Math.round(confidence * 100)}%`;
        }
    }

    updateRedFlagIndicator(redFlag) {
        const redFlagElement = document.querySelector('.pulse-red');
        if (redFlagElement) {
            if (redFlag) {
                redFlagElement.classList.remove('hidden');
                redFlagElement.querySelector('span').textContent = redFlag;
            } else {
                redFlagElement.classList.add('hidden');
            }
        }
    }

    getSessionId() {
        let sessionId = localStorage.getItem('sessionId');
        if (!sessionId) {
            sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            localStorage.setItem('sessionId', sessionId);
        }
        return sessionId;
    }

    saveChatHistory() {
        localStorage.setItem('chatHistory', JSON.stringify(this.messages));
    }

    loadChatHistory() {
        const saved = localStorage.getItem('chatHistory');
        if (saved) {
            try {
                this.messages = JSON.parse(saved);
            } catch (e) {
                console.error('Error loading chat history:', e);
            }
        }
    }

    signOut() {
        if (confirm('Are you sure you want to sign out?')) {
            localStorage.clear();
            window.location.href = '/login';
        }
    }

    handleSidebarNavigation(item) {
        // Add sidebar navigation logic here if needed
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.chatInterface = new ChatInterface();
});