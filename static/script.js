// DOM Elements
const chatMessages = document.getElementById('chatMessages');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const micBtn = document.getElementById('micBtn');
const voiceBtn = document.getElementById('voiceBtn');
const clearBtn = document.getElementById('clearBtn');
const settingsBtn = document.getElementById('settingsBtn');
const settingsPanel = document.getElementById('settingsPanel');
const closeSettings = document.getElementById('closeSettings');
const voiceWave = document.getElementById('voiceWave');
const statusIndicator = document.getElementById('statusIndicator');
const statusText = document.getElementById('statusText');
const voiceMode = document.getElementById('voiceMode');
const voiceSpeed = document.getElementById('voiceSpeed');
const speedValue = document.getElementById('speedValue');
const aiProvider = document.getElementById('aiProvider');
const modelName = document.getElementById('modelName');
const systemStatus = document.getElementById('systemStatus');
const featuresList = document.getElementById('featuresList');
const weatherBadge = document.getElementById('weatherBadge');
const newsBadge = document.getElementById('newsBadge');
const toast = document.getElementById('toast');

// State
let isListening = false;
let voiceOutput = true;
let isProcessing = false;
let mediaRecorder = null;
let audioChunks = [];
let speechSynthesis = window.speechSynthesis;
let recognition = null;
let currentAudio = null;
let messageQueue = [];

// Initialize speech recognition if available
if ('webkitSpeechRecognition' in window) {
    recognition = new webkitSpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
    recognition.maxAlternatives = 1;
    
    recognition.onstart = () => {
        isListening = true;
        micBtn.classList.add('listening');
        voiceWave.classList.add('active');
        updateStatus('Listening...', 'warning');
        showToast('Listening... Speak now', 'info');
    };
    
    recognition.onresult = (event) => {
        const text = event.results[0][0].transcript;
        userInput.value = text;
        showToast(`Heard: "${text}"`, 'success');
        setTimeout(() => sendMessage(), 500);
    };
    
    recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        isListening = false;
        micBtn.classList.remove('listening');
        voiceWave.classList.remove('active');
        updateStatus('Error', 'error');
        
        let errorMessage = 'Speech recognition error';
        switch(event.error) {
            case 'no-speech':
                errorMessage = 'No speech detected. Please try again.';
                break;
            case 'audio-capture':
                errorMessage = 'No microphone found. Please check your microphone.';
                break;
            case 'not-allowed':
                errorMessage = 'Microphone access denied. Please allow microphone access.';
                break;
            default:
                errorMessage = `Error: ${event.error}`;
        }
        showToast(errorMessage, 'error');
        addMessage(errorMessage, 'system');
    };
    
    recognition.onend = () => {
        isListening = false;
        micBtn.classList.remove('listening');
        voiceWave.classList.remove('active');
        updateStatus('Ready', 'success');
    };
} else {
    micBtn.style.display = 'none';
    addMessage('Speech recognition not supported in this browser. Please use Chrome, Edge, or Safari.', 'system');
    showToast('Speech recognition not supported', 'error');
}

// Initialize
checkStatus();
loadHistory();
loadSettings();

// Event Listeners
sendBtn.addEventListener('click', sendMessage);
userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

micBtn.addEventListener('click', toggleListening);
voiceBtn.addEventListener('click', toggleVoiceOutput);
clearBtn.addEventListener('click', clearChat);
settingsBtn.addEventListener('click', () => {
    settingsPanel.classList.add('open');
    updateSettingsDisplay();
});
closeSettings.addEventListener('click', () => settingsPanel.classList.remove('open'));

// Voice speed change
voiceSpeed.addEventListener('input', (e) => {
    const speed = e.target.value;
    speedValue.textContent = speed;
    
    // Save to localStorage
    localStorage.setItem('voiceSpeed', speed);
    
    // Update server settings
    fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice_speed: parseInt(speed) })
    }).catch(err => console.error('Error saving settings:', err));
});

// Voice mode change
voiceMode.addEventListener('change', (e) => {
    localStorage.setItem('voiceMode', e.target.value);
});

// Click outside to close settings
document.addEventListener('click', (e) => {
    if (settingsPanel.classList.contains('open') && 
        !settingsPanel.contains(e.target) && 
        !settingsBtn.contains(e.target)) {
        settingsPanel.classList.remove('open');
    }
});

// Functions
function toggleListening() {
    if (!recognition) {
        showToast('Speech recognition not supported', 'error');
        return;
    }
    
    if (isListening) {
        recognition.stop();
    } else {
        try {
            recognition.start();
        } catch (error) {
            console.error('Failed to start recognition:', error);
            showToast('Failed to start microphone', 'error');
        }
    }
}

function toggleVoiceOutput() {
    voiceOutput = !voiceOutput;
    voiceBtn.classList.toggle('active', voiceOutput);
    localStorage.setItem('voiceOutput', voiceOutput);
    showToast(voiceOutput ? 'Voice output enabled' : 'Voice output disabled', 'info');
}

async function sendMessage() {
    const message = userInput.value.trim();
    if (!message || isProcessing) return;
    
    // Clear input
    userInput.value = '';
    
    // Add user message to chat
    addMessage(message, 'user');
    
    // Show typing indicator
    showTypingIndicator();
    
    // Disable input
    setInputDisabled(true);
    updateStatus('Processing...', 'warning');
    
    try {
        isProcessing = true;
        
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        
        const data = await response.json();
        
        // Remove typing indicator
        hideTypingIndicator();
        
        if (data.success) {
            // Add assistant response
            addMessage(data.response, 'assistant');
            
            // Speak response if voice output is enabled
            if (voiceOutput) {
                speakText(data.response);
            }
        } else {
            addMessage(`Error: ${data.error || 'Unknown error'}`, 'system');
            showToast('Error getting response', 'error');
        }
        
    } catch (error) {
        console.error('Error:', error);
        hideTypingIndicator();
        addMessage('Sorry, an error occurred. Please check your connection and try again.', 'system');
        showToast('Connection error', 'error');
    } finally {
        isProcessing = false;
        setInputDisabled(false);
        updateStatus('Ready', 'success');
        userInput.focus();
    }
}

function addMessage(text, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;
    
    const now = new Date();
    const timeString = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    let avatar = '';
    if (sender === 'user') avatar = '👤';
    else if (sender === 'assistant') avatar = '🤖';
    else avatar = '⚙️';
    
    // Escape HTML to prevent XSS
    const escapedText = escapeHtml(text);
    
    messageDiv.innerHTML = `
        <div class="avatar">${avatar}</div>
        <div class="message-content">
            <p>${escapedText.replace(/\n/g, '<br>')}</p>
            <div class="message-time">${timeString}</div>
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showTypingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'message assistant';
    indicator.id = 'typingIndicator';
    indicator.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="typing-indicator">
            <span></span>
            <span></span>
            <span></span>
        </div>
    `;
    chatMessages.appendChild(indicator);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function hideTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) indicator.remove();
}

function setInputDisabled(disabled) {
    userInput.disabled = disabled;
    sendBtn.disabled = disabled;
    micBtn.disabled = disabled;
}

async function speakText(text) {
    const mode = voiceMode.value;
    
    try {
        const response = await fetch('/api/voice-output', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, mode })
        });
        
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Voice output failed');
        }
    } catch (error) {
        console.error('Voice output error:', error);
        
        // Fallback to browser's speech synthesis
        if (speechSynthesis) {
            try {
                speechSynthesis.cancel(); // Cancel any ongoing speech
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.rate = parseInt(voiceSpeed.value) / 175;
                utterance.pitch = 1;
                utterance.volume = 1;
                speechSynthesis.speak(utterance);
            } catch (e) {
                console.error('Browser TTS failed:', e);
            }
        }
    }
}

async function clearChat() {
    if (!confirm('Are you sure you want to clear all messages?')) return;
    
    try {
        const response = await fetch('/api/clear-history', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            chatMessages.innerHTML = `
                <div class="message assistant">
                    <div class="avatar">🤖</div>
                    <div class="message-content">
                        <p>Chat cleared. How can I help you?</p>
                        <div class="message-time">Just now</div>
                    </div>
                </div>
            `;
            showToast('Chat cleared', 'success');
        }
    } catch (error) {
        console.error('Error clearing chat:', error);
        showToast('Failed to clear chat', 'error');
    }
}

async function loadHistory() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();
        
        if (data.success && data.history && data.history.length > 0) {
            // Clear existing messages (keep first welcome message)
            chatMessages.innerHTML = '';
            
            // Add history messages
            data.history.forEach(msg => {
                addMessage(msg.content, msg.role === 'user' ? 'user' : 'assistant');
            });
        }
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

async function checkStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        if (data.success) {
            aiProvider.textContent = data.ai_provider.charAt(0).toUpperCase() + data.ai_provider.slice(1);
            modelName.textContent = data.model_name || 'Unknown';
            systemStatus.textContent = data.ai_configured ? '✅ Connected' : '❌ Not Connected';
            
            // Update status indicator
            if (data.ai_configured) {
                statusIndicator.className = 'status-indicator';
            } else {
                statusIndicator.className = 'status-indicator error';
                addMessage('⚠️ AI service not fully configured. Using fallback responses.', 'system');
            }
            
            // Update features
            if (data.features) {
                updateFeaturesDisplay(data.features);
            }
        }
    } catch (error) {
        console.error('Status check error:', error);
        systemStatus.textContent = '❌ Offline';
        statusIndicator.className = 'status-indicator error';
    }
}

function updateFeaturesDisplay(features) {
    const featuresHtml = [];
    
    if (features.weather) {
        featuresHtml.push('<span class="feature-tag active">🌤️ Weather</span>');
        weatherBadge.title = 'Weather feature available';
    } else {
        weatherBadge.title = 'Weather API not configured';
    }
    
    if (features.news) {
        featuresHtml.push('<span class="feature-tag active">📰 News</span>');
        newsBadge.title = 'News feature available';
    } else {
        newsBadge.title = 'News API not configured';
    }
    
    featuresList.innerHTML = featuresHtml.join(' ');
}

function loadSettings() {
    // Load from localStorage
    const savedVoiceOutput = localStorage.getItem('voiceOutput');
    if (savedVoiceOutput !== null) {
        voiceOutput = savedVoiceOutput === 'true';
        voiceBtn.classList.toggle('active', voiceOutput);
    }
    
    const savedVoiceMode = localStorage.getItem('voiceMode');
    if (savedVoiceMode) {
        voiceMode.value = savedVoiceMode;
    }
    
    const savedVoiceSpeed = localStorage.getItem('voiceSpeed');
    if (savedVoiceSpeed) {
        voiceSpeed.value = savedVoiceSpeed;
        speedValue.textContent = savedVoiceSpeed;
    }
}

function updateSettingsDisplay() {
    // Update settings panel with current values
    document.getElementById('voiceMode').value = localStorage.getItem('voiceMode') || 'online';
    document.getElementById('voiceSpeed').value = localStorage.getItem('voiceSpeed') || '175';
    speedValue.textContent = document.getElementById('voiceSpeed').value;
}

function updateStatus(text, type = 'success') {
    statusText.textContent = text;
    statusIndicator.className = `status-indicator ${type}`;
}

function showToast(message, type = 'info') {
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.style.display = 'block';
    
    setTimeout(() => {
        toast.style.display = 'none';
    }, 3000);
}

// Add weather and news commands info
weatherBadge.addEventListener('click', () => {
    addMessage('Try: "weather in London" or "weather in New York"', 'system');
});

newsBadge.addEventListener('click', () => {
    addMessage('Try: "news technology" or "news business" or just "news"', 'system');
});

// Handle window focus/blur for microphone
window.addEventListener('blur', () => {
    if (isListening && recognition) {
        recognition.stop();
    }
});

// Handle visibility change
document.addEventListener('visibilitychange', () => {
    if (document.hidden && isListening && recognition) {
        recognition.stop();
    }
});

// Auto-resize textarea if needed (convert input to textarea for multi-line)
// Not implemented as we're using input field