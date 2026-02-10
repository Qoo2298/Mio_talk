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

// --- SVG Icons ---
const ICON_SEND = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"></path><path d="M22 2L15 22L11 13L2 9L22 2Z"></path></svg>';
const ICON_STOP = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"></rect></svg>';

// TTS Mode Icons (SVG)
const ICON_TTS_LOCAL = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5L6 9H2v6h4l5 4V5z"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>';
const ICON_TTS_API = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"></path></svg>';
const ICON_TTS_SILENT = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5L6 9H2v6h4l5 4V5z"></path><line x1="23" y1="9" x2="17" y2="15"></line><line x1="17" y1="9" x2="23" y2="15"></line></svg>';

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
    if (state.ttsMode === "SILENT") return; // 無言モード
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
// --- Main Chat Function ---
function updateStatus(text) {
    if (elements.systemStatusText) elements.systemStatusText.textContent = text;
}

function processMessage(text, imageId = null) {
    if (state.isProcessing && state.currentEventSource) {
        // --- 中断処理 (Stop) ---
        console.log("Aborting current request...");
        state.currentEventSource.close();
        state.currentEventSource = null;
        state.isProcessing = false;

        // UIリセット
        if (elements.talkBtn) {
            elements.talkBtn.classList.remove('loading');
            elements.talkBtn.innerHTML = ICON_SEND;
        }
        if (elements.visualCore) elements.visualCore.classList.remove('thinking');
        updateStatus("Aborted");
        return;
    }

    if (!text && !imageId) return;
    if (state.isProcessing) return; // 既に処理中（二重起動防止）

    // --- 開始処理 (Start) ---
    state.isProcessing = true;
    updateStatus("考え中...");

    // ボタンを「× (停止)」に変更
    if (elements.talkBtn) {
        elements.talkBtn.classList.add('loading');
        elements.talkBtn.innerHTML = ICON_STOP;
    }
    if (elements.visualCore) elements.visualCore.classList.add('thinking');

    try {
        const mode = state.ttsMode;
        let url = `/api/stream_chat?text=${encodeURIComponent(text)}&mode=${mode}`;
        if (imageId) url += `&image_id=${imageId}`;

        const eventSource = new EventSource(url);
        state.currentEventSource = eventSource; // 参照を保持して中断可能に

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
                } else if (data.type === "usage" && data.data) {
                    const usage = data.data;
                    const tokenEl = document.getElementById('token-usage');
                    if (tokenEl && usage) {
                        // コスト計算 (Input $0.50/1M, Output $3.00/1M)
                        const inputCost = (usage.prompt_token_count / 1000000) * 0.50;
                        const outputCost = (usage.candidates_token_count / 1000000) * 3.00;
                        const totalUSD = inputCost + outputCost;
                        const totalJPY = totalUSD * 155; // 概算レート
                        tokenEl.style.display = 'block';
                        tokenEl.innerHTML = `📊 In:${usage.prompt_token_count} Out:${usage.candidates_token_count} | 💰 $${totalUSD.toFixed(5)} (¥${totalJPY.toFixed(3)})`;
                    }
                } else if (data.type === "end") {
                    eventSource.close();
                    state.currentEventSource = null;
                    state.isProcessing = false;

                    // UIリセット
                    if (elements.talkBtn) {
                        elements.talkBtn.classList.remove('loading');
                        elements.talkBtn.innerHTML = ICON_SEND;
                    }
                    if (elements.visualCore) elements.visualCore.classList.remove('thinking');
                    updateStatus("Online");

                    if (mode !== "SILENT" && mode === "LOCAL" && fullResponse && audioQueue.length === 0) {
                        speakText(fullResponse);
                    }
                }
            } catch (e) {
                console.error("SSE Parse Error:", e, event.data);
            }
        };

        eventSource.onerror = () => {
            console.error("SSE Error occurred.");
            eventSource.close();
            state.currentEventSource = null;
            state.isProcessing = false;

            updateStatus("Error");
            if (elements.talkBtn) {
                elements.talkBtn.classList.remove('loading');
                elements.talkBtn.innerHTML = ICON_SEND;
            }
            if (elements.visualCore) elements.visualCore.classList.remove('thinking');
        };

    } catch (e) {
        console.error(e);
        state.isProcessing = false;
        state.currentEventSource = null;
    }
}

// --- History Logic (会話履歴 - セリフ欄クリック用) ---
async function showHistory() {
    if (!elements.logsModal || !elements.logsContent) return;
    elements.logsModal.style.display = 'flex';

    // Update modal title for conversation history
    const modalHeader = elements.logsModal.querySelector('.modal-header h3');
    if (modalHeader) modalHeader.textContent = '会話履歴';

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
        // Reverse to show oldest first (Top) -> newest last (Bottom)
        // API returns [newest, ..., oldest] usually, so reverse needed for chronological order
        const logs = [...data.logs].reverse();

        logs.forEach(log => {
            const isMio = log.role === 'assistant';
            const escapedContent = log.content.replace(/'/g, "\\'").replace(/\n/g, ' ');

            html += `
                <div class="history-item ${isMio ? 'assistant' : 'user'}">
                    <span class="history-text">${log.content}</span>
                    ${isMio ? `<button class="history-play" onclick="speakText('${escapedContent}')" title="再生">▶</button>` : ''}
                </div>
            `;
        });

        elements.logsContent.innerHTML = html;

        // Scroll to bottom
        setTimeout(() => {
            elements.logsContent.scrollTop = elements.logsContent.scrollHeight;
        }, 100);

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
    if (modalHeader) modalHeader.textContent = '記憶コンパクション履歴';

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
                updatesHtml += `<div class="compact-update"><strong>User:</strong> ${updates.user_updates.join(", ")}</div>`;
            }
            if (updates.identity_updates && updates.identity_updates.length > 0) {
                updatesHtml += `<div class="compact-update"><strong>Identity:</strong> ${updates.identity_updates.join(", ")}</div>`;
            }
            if (updates.memory_updates && updates.memory_updates.length > 0) {
                updatesHtml += `<div class="compact-update"><strong>Memory:</strong> ${updates.memory_updates.join(", ")}</div>`;
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
                ttsBtn.innerHTML = ICON_TTS_API;
                ttsBtn.classList.remove('active');
                ttsBtn.title = "音声: クラウド";
            } else if (state.ttsMode === "API") {
                state.ttsMode = "SILENT";
                ttsBtn.innerHTML = ICON_TTS_SILENT;
                ttsBtn.classList.remove('active');
                ttsBtn.title = "音声: 無言";
            } else {
                state.ttsMode = "LOCAL";
                ttsBtn.innerHTML = ICON_TTS_LOCAL;
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
    // Camera Menu Logic
    const cameraMenu = document.getElementById('camera-menu');
    const camUploadBtn = document.getElementById('cam-upload-btn');
    const camTapoBtn = document.getElementById('cam-tapo-btn');
    const fileInput = document.getElementById('file-input');

    if (elements.camBtn) {
        elements.camBtn.onclick = (e) => {
            e.stopPropagation(); // バブリング防止
            if (cameraMenu) {
                const isVisible = cameraMenu.style.display === 'flex';
                cameraMenu.style.display = isVisible ? 'none' : 'flex';
            }
        };
    }

    // 画面外クリックでメニューを閉じる
    document.addEventListener('click', (e) => {
        if (cameraMenu && cameraMenu.style.display === 'flex' && !cameraMenu.contains(e.target) && e.target !== elements.camBtn) {
            cameraMenu.style.display = 'none';
        }
    });

    // 1. 画像アップロード処理
    if (camUploadBtn && fileInput) {
        camUploadBtn.onclick = () => {
            fileInput.click();
            if (cameraMenu) cameraMenu.style.display = 'none';
        };

        fileInput.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            updateStatus("読み込み中...");
            const reader = new FileReader();

            reader.onload = async (e) => {
                const base64Data = e.target.result.split(',')[1]; // data:image/jpeg;base64,... のスキームを除く

                try {
                    updateStatus("アップロード中...");
                    const upRes = await fetch('/api/upload_image', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ image: base64Data })
                    });
                    const upData = await upRes.json();
                    if (upData.status !== "ok") throw new Error("Upload failed");

                    state.pendingImageId = upData.image_id;
                    updateImagePreview(base64Data);
                    updateStatus("画像準備OK");

                    // Inputをクリア（同じファイルを再選択できるように）
                    fileInput.value = "";

                } catch (err) {
                    console.error(err);
                    updateStatus("Error");
                    alert("アップロード失敗: " + err.message);
                }
            };
            reader.readAsDataURL(file);
        };
    }

    // 2. Tapoカメラ処理 (既存ロジックの移植)
    if (camTapoBtn) {
        camTapoBtn.onclick = async () => {
            if (cameraMenu) cameraMenu.style.display = 'none';

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
                if (state.isProcessing) {
                    // 処理中の場合は中断のみ行う
                    processMessage(null);
                    elements.userInput.focus(); // フォーカス戻す
                } else if (text || state.pendingImageId) {
                    elements.userInput.value = "";
                    processMessage(text, state.pendingImageId);
                    updateImagePreview(null);
                }
            }
        };
    }

    if (elements.talkBtn) {
        elements.talkBtn.onclick = () => {
            // 処理中の場合は中断
            if (state.isProcessing) {
                processMessage(null);
                return;
            }
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
