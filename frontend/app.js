const state = {
    isProcessing: false,
    isSpeaking: false,
    isListening: false,
    isMicEnabled: false,  // デフォルトでマイクOFF
    lastAudios: [],
    currentAudio: null,
    pendingImageId: null,
    ttsMode: "LOCAL"
};

// Elements Cache
const elements = {
    mioMessage: document.getElementById('mio-message'),
    userInput: document.getElementById('user-input'),
    talkBtn: document.getElementById('talk-btn'),
    systemStatusText: document.getElementById('system-status-text'),
    visualCore: document.querySelector('.visual-core'),
    micToggle: document.getElementById('mic-toggle'),
    logsBtn: document.getElementById('logs-btn'),
    logsModal: document.getElementById('logs-modal'),
    logsContent: document.getElementById('logs-content'),
    closeLogs: document.getElementById('close-logs'),
    compactBtn: document.getElementById('compact-btn'),
    compactModal: document.getElementById('compact-modal'),
    confirmCompact: document.getElementById('confirm-compact'),
    cancelCompact: document.getElementById('cancel-compact'),
    camBtn: document.getElementById('cam-btn')
};

// --- Show Full Image (Global) ---
window.showFullImage = (src) => {
    const modal = document.getElementById('image-modal');
    const img = document.getElementById('full-image');
    if (modal && img) {
        img.src = src;
        modal.style.display = 'flex';
    }
};

// --- Audio Queue Helper ---
const audioQueue = [];
let isPlayingAudio = false;

function playNextAudio() {
    if (isPlayingAudio || audioQueue.length === 0) {
        if (audioQueue.length === 0 && elements.visualCore) {
            elements.visualCore.classList.remove('talking');
        }
        return;
    }

    isPlayingAudio = true;
    if (elements.visualCore) elements.visualCore.classList.add('talking');

    const base64 = audioQueue.shift();
    const audio = new Audio("data:audio/wav;base64," + base64);

    const volSlider = document.getElementById('volume-slider');
    if (volSlider) audio.volume = volSlider.value;
    state.currentAudio = audio;

    audio.onended = () => {
        isPlayingAudio = false;
        state.currentAudio = null;
        if (audioQueue.length > 0) {
            playNextAudio();
        } else {
            if (elements.visualCore) elements.visualCore.classList.remove('talking');
            if (state.isMicEnabled && recognition && !state.isProcessing) {
                try { recognition.start(); } catch (e) { }
            }
        }
    };
    audio.play().catch(e => {
        console.error("Audio Play Error:", e);
        isPlayingAudio = false;
        playNextAudio();
    });
}

// --- TTS Logic ---
async function speakText(text) {
    if (!text) return;
    state.isSpeaking = true;
    if (elements.visualCore) elements.visualCore.classList.add('talking');

    const volSlider = document.getElementById('volume-slider');
    const volume = volSlider ? parseFloat(volSlider.value) : 0.5;

    try {
        const res = await fetch('/api/speak', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text, mode: state.ttsMode })
        });
        const data = await res.json();

        if (data.status === 'ok' && data.audio) {
            const audio = new Audio("data:audio/wav;base64," + data.audio);
            audio.volume = volume;
            state.currentAudio = audio;

            audio.onended = () => {
                state.isSpeaking = false;
                if (elements.visualCore) elements.visualCore.classList.remove('talking');
                state.currentAudio = null;
                if (state.isMicEnabled && recognition && !state.isProcessing) {
                    try { recognition.start(); } catch (e) { }
                }
            };
            await audio.play();
        }
    } catch (e) {
        console.error("TTS Error:", e);
        state.isSpeaking = false;
        if (elements.visualCore) elements.visualCore.classList.remove('talking');
    }
}

// Make speakText globally accessible for history playback
window.speakText = speakText;

// --- STT ---
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition;

if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'ja-JP';
    recognition.interimResults = true;
    recognition.continuous = true;

    recognition.onresult = (event) => {
        if (state.isProcessing || state.isSpeaking) return;
        let finalTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
                finalTranscript += event.results[i][0].transcript;
            }
        }
        if (finalTranscript) {
            if (elements.userInput) elements.userInput.value = finalTranscript;
            processMessage(finalTranscript, state.pendingImageId);
            updateImagePreview(null);
        }
    };
    recognition.onend = () => {
        if (state.isMicEnabled && !state.isProcessing && !state.isSpeaking) {
            try { recognition.start(); } catch (e) { }
        }
    };
} else {
    console.warn("Speech Recognition API not supported.");
}

// --- Image Preview ---
const imagePreviewArea = document.getElementById('image-preview-area');
const clearImageBtn = document.getElementById('clear-image-btn');
const previewThumb = document.getElementById('preview-thumb');

function updateImagePreview(base64Img) {
    if (imagePreviewArea) {
        if (base64Img) {
            imagePreviewArea.style.display = 'flex';
            if (previewThumb) previewThumb.src = "data:image/jpeg;base64," + base64Img;
        } else {
            imagePreviewArea.style.display = 'none';
            state.pendingImageId = null;
            if (previewThumb) previewThumb.src = "";
        }
    }
}
if (clearImageBtn) {
    clearImageBtn.onclick = () => updateImagePreview(null);
}

// --- Main Chat Function ---
function updateStatus(text) {
    if (elements.systemStatusText) elements.systemStatusText.textContent = text;
}

function processMessage(text, imageId = null) {
    if (!text && !imageId) return;
    if (state.isProcessing) return;

    state.isProcessing = true;
    updateStatus("考え中...");
    if (elements.talkBtn) elements.talkBtn.classList.add('loading');
    if (elements.visualCore) elements.visualCore.classList.add('thinking');

    try {
        const mode = state.ttsMode;
        let url = `/api/stream_chat?text=${encodeURIComponent(text)}&mode=${mode}`;
        if (imageId) url += `&image_id=${imageId}`;

        const eventSource = new EventSource(url);
        let fullResponse = "";

        const messageContent = elements.mioMessage.querySelector('.message-content') || elements.mioMessage;

        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                if (data.type === "start") {
                    fullResponse = "";
                    messageContent.textContent = "";
                    audioQueue.length = 0;
                } else if (data.type === "chunk") {
                    fullResponse += data.content;
                    messageContent.textContent = fullResponse;
                } else if (data.type === "audio") {
                    audioQueue.push(data.content);
                    playNextAudio();
                } else if (data.type === "usage" || data.usage) {
                    const usage = data.usage || data.content;
                    const tokenEl = document.getElementById('token-usage');
                    if (tokenEl && usage) {
                        tokenEl.style.display = 'block';
                        tokenEl.textContent = `In ${usage.prompt_token_count} / Out ${usage.candidates_token_count}`;
                    }
                } else if (data.type === "end") {
                    eventSource.close();
                    state.isProcessing = false;
                    if (elements.talkBtn) elements.talkBtn.classList.remove('loading');
                    if (elements.visualCore) elements.visualCore.classList.remove('thinking');
                    updateStatus("Online");

                    if (mode === "LOCAL" && fullResponse && audioQueue.length === 0) {
                        speakText(fullResponse);
                    }
                }
            } catch (e) {
                console.error("SSE Parse Error:", e, event.data);
            }
        };

        eventSource.onerror = () => {
            eventSource.close();
            state.isProcessing = false;
            updateStatus("Error");
            if (elements.talkBtn) elements.talkBtn.classList.remove('loading');
            if (elements.visualCore) elements.visualCore.classList.remove('thinking');
        };

    } catch (e) {
        console.error(e);
        state.isProcessing = false;
    }
}

// --- History Logic (会話履歴 - セリフ欄クリック用) ---
async function showHistory() {
    if (!elements.logsModal || !elements.logsContent) return;
    elements.logsModal.style.display = 'flex';

    // Update modal title for conversation history
    const modalHeader = elements.logsModal.querySelector('.modal-header h3');
    if (modalHeader) modalHeader.textContent = '💬 会話履歴';

    elements.logsContent.innerHTML = '<p style="text-align:center; color:#9ca3af; padding:40px;">読み込み中...</p>';

    try {
        const res = await fetch('/api/history?limit=50');
        const data = await res.json();

        if (data.status !== "ok") throw new Error(data.message);

        if (data.logs.length === 0) {
            elements.logsContent.innerHTML = '<p style="text-align:center; color:#9ca3af; padding:40px;">履歴がありません</p>';
            return;
        }

        let html = '';
        // Reverse to show oldest first
        const logs = [...data.logs].reverse();

        logs.forEach(log => {
            const isMio = log.role === 'assistant';
            const icon = isMio ? '🤖' : '👤';
            const escapedContent = log.content.replace(/'/g, "\\'").replace(/\n/g, ' ');

            html += `
                <div class="history-item ${isMio ? 'assistant' : 'user'}">
                    <span class="history-icon">${icon}</span>
                    <span class="history-text">${log.content}</span>
                    ${isMio ? `<button class="history-play" onclick="speakText('${escapedContent}')" title="再生">▶</button>` : ''}
                </div>
            `;
        });

        elements.logsContent.innerHTML = html;

    } catch (e) {
        elements.logsContent.innerHTML = `<p style="text-align:center; color:#ef4444; padding:40px;">エラー: ${e.message}</p>`;
    }
}

// --- Compaction Logs (📜ボタン用) ---
async function showCompactionLogs() {
    if (!elements.logsModal || !elements.logsContent) return;
    elements.logsModal.style.display = 'flex';

    // Update modal title
    const modalHeader = elements.logsModal.querySelector('.modal-header h3');
    if (modalHeader) modalHeader.textContent = '🧠 記憶コンパクション履歴';

    elements.logsContent.innerHTML = '<p style="text-align:center; color:#9ca3af; padding:40px;">読み込み中...</p>';

    try {
        const res = await fetch('/api/memory/compaction_logs?limit=10');
        const data = await res.json();

        if (data.status !== "ok") throw new Error(data.message);

        if (data.logs.length === 0) {
            elements.logsContent.innerHTML = '<p style="text-align:center; color:#9ca3af; padding:40px;">コンパクション履歴がありません</p>';
            return;
        }

        let html = '';
        data.logs.forEach(log => {
            const date = new Date(log.timestamp * 1000).toLocaleString('ja-JP');
            let updatesHtml = "";
            let updates = {};
            try { updates = JSON.parse(log.added_memories || "{}"); } catch (e) { }

            if (updates.user_updates && updates.user_updates.length > 0) {
                updatesHtml += `<div class="compact-update"><strong>👤 User:</strong> ${updates.user_updates.join(", ")}</div>`;
            }
            if (updates.identity_updates && updates.identity_updates.length > 0) {
                updatesHtml += `<div class="compact-update"><strong>🤖 Identity:</strong> ${updates.identity_updates.join(", ")}</div>`;
            }
            if (updates.memory_updates && updates.memory_updates.length > 0) {
                updatesHtml += `<div class="compact-update"><strong>🧠 Memory:</strong> ${updates.memory_updates.join(", ")}</div>`;
            }

            html += `
                <div class="compaction-item">
                    <div class="compaction-header">
                        <span class="compaction-date">${date}</span>
                        <span class="compaction-tokens">Tokens: ${log.token_usage}</span>
                    </div>
                    <div class="compaction-summary">${log.summary}</div>
                    <div class="compaction-updates">
                        ${updatesHtml || '<span style="color:#9ca3af;">(長期記憶への追加なし)</span>'}
                    </div>
                </div>
            `;
        });

        elements.logsContent.innerHTML = html;

    } catch (e) {
        elements.logsContent.innerHTML = `<p style="text-align:center; color:#ef4444; padding:40px;">エラー: ${e.message}</p>`;
    }
}

// --- Init Listeners ---
window.onload = () => {
    // Volume
    const volSlider = document.getElementById('volume-slider');
    if (volSlider) {
        const savedVol = localStorage.getItem('mio_volume');
        if (savedVol) volSlider.value = savedVol;
        volSlider.oninput = () => {
            localStorage.setItem('mio_volume', volSlider.value);
            if (state.currentAudio) state.currentAudio.volume = volSlider.value;
        };
    }

    // TTS Mode Toggle
    const ttsBtn = document.getElementById('tts-mode-btn');
    if (ttsBtn) {
        ttsBtn.onclick = () => {
            if (state.ttsMode === "LOCAL") {
                state.ttsMode = "API";
                ttsBtn.textContent = "☁️";
                ttsBtn.classList.remove('active');
                ttsBtn.title = "音声: クラウド";
            } else {
                state.ttsMode = "LOCAL";
                ttsBtn.textContent = "🏠";
                ttsBtn.classList.add('active');
                ttsBtn.title = "音声: ローカル";
            }
        };
    }

    // Click on message bubble -> Show History
    if (elements.mioMessage) {
        elements.mioMessage.onclick = showHistory;
        elements.mioMessage.title = "クリックで履歴を表示";
    }

    // Camera
    if (elements.camBtn) {
        elements.camBtn.onclick = async () => {
            updateStatus("撮影中...");
            try {
                const snapRes = await fetch('/api/camera/snapshot');
                const snapData = await snapRes.json();
                if (snapData.status !== "ok") throw new Error(snapData.message);

                const base64Img = snapData.image;

                updateStatus("アップロード中...");
                const upRes = await fetch('/api/upload_image', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image: base64Img })
                });
                const upData = await upRes.json();
                if (upData.status !== "ok") throw new Error("Upload failed");

                state.pendingImageId = upData.image_id;
                updateImagePreview(base64Img);
                updateStatus("画像準備OK");

            } catch (e) {
                console.error(e);
                alert("カメラエラー: " + e.message);
                updateStatus("Error");
            }
        };
    }

    // Input
    if (elements.userInput) {
        elements.userInput.onkeydown = (e) => {
            if (e.key === 'Enter') {
                const text = elements.userInput.value.trim();
                if (text || state.pendingImageId) {
                    elements.userInput.value = "";
                    processMessage(text, state.pendingImageId);
                    updateImagePreview(null);
                }
            }
        };
    }

    if (elements.talkBtn) {
        elements.talkBtn.onclick = () => {
            const text = elements.userInput.value.trim();
            if (text || state.pendingImageId) {
                elements.userInput.value = "";
                processMessage(text, state.pendingImageId);
                updateImagePreview(null);
            } else {
                if (recognition) recognition.start();
            }
        };
    }

    // Mic Toggle
    if (elements.micToggle) {
        // 初期状態を反映（デフォルトOFF）
        elements.micToggle.style.opacity = state.isMicEnabled ? "1" : "0.4";

        elements.micToggle.onclick = () => {
            state.isMicEnabled = !state.isMicEnabled;
            elements.micToggle.style.opacity = state.isMicEnabled ? "1" : "0.4";
            if (!state.isMicEnabled && recognition) recognition.stop();
            else if (state.isMicEnabled && recognition && !state.isProcessing && !state.isSpeaking) {
                try { recognition.start(); } catch (e) { }
            }
        };
    }

    // Overlay
    const overlay = document.getElementById('start-overlay');
    if (overlay) {
        overlay.onclick = () => {
            overlay.style.display = 'none';
            // Unlock audio context
            const audio = new Audio();
            audio.play().catch(() => { });
        };
    }

    // Modal Controls
    // logs button -> show compaction history (📜)
    if (elements.logsBtn) elements.logsBtn.onclick = showCompactionLogs;
    if (elements.closeLogs) elements.closeLogs.onclick = () => elements.logsModal.style.display = 'none';
    if (elements.compactBtn) elements.compactBtn.onclick = () => elements.compactModal.style.display = 'flex';
    if (elements.cancelCompact) elements.cancelCompact.onclick = () => elements.compactModal.style.display = 'none';
    if (elements.confirmCompact) elements.confirmCompact.onclick = async () => {
        elements.compactModal.style.display = 'none';
        updateStatus("整理中...");
        try {
            const res = await fetch('/api/memory/compact', { method: 'POST' });
            const data = await res.json();
            if (data.status === 'ok') {
                updateStatus("完了!");
                setTimeout(() => updateStatus("Online"), 2000);
            } else {
                updateStatus("Error");
            }
        } catch (e) {
            console.error(e);
            updateStatus("Error");
        }
    };
};
