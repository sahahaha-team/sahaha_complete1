/**
 * 사하구청 AI 상담사 - 채팅 통합 스크립트 클라이언트 (TTS 스피커 완벽 고정 버전)
 */
(function () {
    const messagesEl = document.getElementById("chat-messages");
    const inputEl = document.getElementById("user-input");
    const sendBtn = document.getElementById("btn-send");
    const clearBtn = document.getElementById("btn-clear");

    // 테마 및 환경 설정 엘리먼트 정의
    const btnSettings = document.getElementById("btn-settings");
    const settingsMenu = document.getElementById("settings-menu");
    const themeToggle = document.getElementById("theme-toggle");
    const btnFontInc = document.getElementById("btn-font-inc");
    const btnFontDec = document.getElementById("btn-font-dec");
    const fontSizeDisplay = document.getElementById("font-size-display");

    let isLoading = false;
    const ROBOT_IMAGES = {
        neutral: '/static/images/mascot_neutral.png',
        thinking: '/static/images/mascot_thinking.png',
        warning: '/static/images/mascot_warning.png'
    };

    // ===== TTS (읽어주기) 웹 표준 API 설정 =====
    const synth = window.speechSynthesis;
    let currentUtterance = null; 
    let activeTtsButton = null;   

    // 🎯 직관적인 스피커 아이콘(소리 재생) 및 네모(중지) 아이콘으로 전면 변경
    const ICON_PLAY = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5L6 9H2v6h4l5 4V5z"></path><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>`;
    const ICON_STOP = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"></rect></svg>`;


    // ===== 사용자 설정 로드 및 적용 =====
    function applyUserPreferences() {
        if (localStorage.getItem("theme") === "dark") {
            document.body.classList.add("dark-mode");
            if (themeToggle) themeToggle.checked = true;
        }
        let savedSize = parseFloat(localStorage.getItem("fontSize")) || 14.5;
        updateFontSize(savedSize);
    }

    function updateFontSize(size) {
        if (size > 20) size = 20;
        if (size < 12) size = 12;

        document.documentElement.style.setProperty('--msg-font-size', `${size}px`);
        localStorage.setItem("fontSize", size);

        if (!fontSizeDisplay) return;
        if (size === 14.5) {
            fontSizeDisplay.textContent = "기본";
        } else if (size > 14.5) {
            fontSizeDisplay.textContent = `+${Math.round((size - 14.5) * 2)}`;
        } else {
            fontSizeDisplay.textContent = `${Math.round((size - 14.5) * 2)}`;
        }
    }

    // 설정 톱니바퀴 토글 (위젯 모드에는 설정 UI가 없을 수 있어 가드)
    if (btnSettings && settingsMenu) {
        btnSettings.addEventListener("click", function(e) {
            e.preventDefault();
            e.stopPropagation();
            settingsMenu.classList.toggle("hidden");
        });

        // 바깥 누르면 설정창 닫기
        document.addEventListener("click", function(e) {
            if (!btnSettings.contains(e.target) && !settingsMenu.contains(e.target)) {
                settingsMenu.classList.add("hidden");
            }
        });
    }

    // 다크모드 토글
    if (themeToggle) {
        themeToggle.addEventListener("change", function(e) {
            if (e.target.checked) {
                document.body.classList.add("dark-mode");
                localStorage.setItem("theme", "dark");
            } else {
                document.body.classList.remove("dark-mode");
                localStorage.setItem("theme", "light");
            }
        });
    }

    // 글씨 가감 버튼
    if (btnFontInc) {
        btnFontInc.addEventListener("click", function() {
            let currentSize = parseFloat(localStorage.getItem("fontSize")) || 14.5;
            updateFontSize(currentSize + 0.5);
        });
    }
    if (btnFontDec) {
        btnFontDec.addEventListener("click", function() {
            let currentSize = parseFloat(localStorage.getItem("fontSize")) || 14.5;
            updateFontSize(currentSize - 0.5);
        });
    }

    // ===== TTS 재생/중지 제어 엔진 =====
    function stopSpeaking() {
        if (synth.speaking || synth.pending) {
            synth.cancel(); 
        }
        if (activeTtsButton) {
            activeTtsButton.innerHTML = ICON_PLAY;
            activeTtsButton.classList.remove("speaking");
            activeTtsButton.setAttribute("title", "읽어주기");
            activeTtsButton = null;
        }
        currentUtterance = null;
    }

    function speakText(text, buttonEl) {
        if (synth.speaking || synth.pending) {
            if (activeTtsButton === buttonEl) {
                stopSpeaking();
                return;
            }
            stopSpeaking();
        }

        if (!text) return;

        currentUtterance = new SpeechSynthesisUtterance(text);
        currentUtterance.lang = 'ko-KR'; 
        currentUtterance.rate = 1.0;     

        activeTtsButton = buttonEl;
        activeTtsButton.innerHTML = ICON_STOP;
        activeTtsButton.classList.add("speaking");
        activeTtsButton.setAttribute("title", "읽기 중지");

        currentUtterance.onend = function() {
            stopSpeaking();
        };
        currentUtterance.onerror = function() {
            stopSpeaking();
        };

        synth.speak(currentUtterance);
    }


    // ===== 메시지 UI 조립 팩토리 =====
    function createMessageEl(role, content, sources, degraded, degradedReason) {
        const msg = document.createElement("div");
        msg.className = `message ${role === "user" ? "user-message" : "bot-message"}`;

        const avatar = document.createElement("div");
        avatar.className = "message-avatar";

        if (role === "user") {
            avatar.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" fill="#fff"/></svg>`;
        } else {
            let isWarning = content && (content.includes('⚠️') || content.includes('개인정보가 포함되어 있습니다'));
            const currentImg = isWarning ? ROBOT_IMAGES.warning : ROBOT_IMAGES.neutral;
            avatar.innerHTML = `<img src="${currentImg}" class="bot-avatar-img" alt="로봇">`;
        }

        const contentDiv = document.createElement("div");
        contentDiv.className = "message-content";

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";

        let plainTextContent = '';

        if (role === "user") {
            bubble.textContent = content;
        } else {
            bubble.innerHTML = formatBotMessage(content);
            
            // 🎯 임시 div를 통해 퓨어한 한국어 텍스트 문장만 추출 (HTML 태그 제거용)
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = bubble.innerHTML;
            plainTextContent = tempDiv.textContent || tempDiv.innerText;

            // 🎯 TTS 컨트롤 스피커 버튼을 생성하여 말풍선 내부 우측상단에 부착
            const ttsControls = document.createElement('div');
            ttsControls.className = 'tts-controls';
            
            const ttsBtn = document.createElement('button');
            ttsBtn.className = 'tts-btn';
            ttsBtn.setAttribute('title', '읽어주기');
            ttsBtn.innerHTML = ICON_PLAY; 
            
            ttsBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                speakText(plainTextContent, ttsBtn);
            });

            ttsControls.appendChild(ttsBtn);
            bubble.appendChild(ttsControls); // 🎯 기존 바깥쪽이 아니라 말풍선('bubble') 내부에 직접 넣어서 가둠
        }

        contentDiv.appendChild(bubble);

        if (sources && sources.length > 0) {
            contentDiv.appendChild(createSourcesEl(sources));
        }

        msg.appendChild(avatar);
        msg.appendChild(contentDiv);
        return msg;
    }

    function formatBotMessage(text) {
        if (!text) return "";
        let html = text
            .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
            .replace(/\*(.*?)\*/g, "<em>$1</em>")
            .replace(/\n{2,}/g, "</p><p>")
            .replace(/\n/g, "<br>");
        html = html.replace(/(\d+)\)\s/g, "<br>$1) ");
        return `<p>${html}</p>`;
    }

    function createSourcesEl(sources) {
        const container = document.createElement("div");
        container.className = "sources-container";
        const label = document.createElement("div");
        label.className = "sources-label";
        label.textContent = "참고 출처";
        container.appendChild(label);

        sources.forEach(function (src) {
            const card = document.createElement("a");
            card.className = "source-card";
            card.href = src.url;
            card.target = "_blank";
            card.rel = "noopener noreferrer";

            card.innerHTML = `
                <span class="source-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></span>
                <span class="source-title">${escapeHtml(src.title)}</span>
                ${src.service_type ? `<span class="source-badge">${escapeHtml(src.service_type)}</span>` : ""}
            `;
            container.appendChild(card);
        });
        return container;
    }

    function showTypingIndicator() {
        const msg = document.createElement("div");
        msg.className = "message bot-message";
        msg.id = "typing-indicator";
        msg.innerHTML = `
            <div class="message-avatar"><img src="${ROBOT_IMAGES.thinking}" class="bot-avatar-img" alt="생각중"></div>
            <div class="message-content">
                <div class="message-bubble">
                    <div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>
                </div>
            </div>
        `;
        messagesEl.appendChild(msg);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        const el = document.getElementById("typing-indicator");
        if (el) el.remove();
    }

    function scrollToBottom() {
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    function checkFrontPrivacy(text) {
        const rrnRegex = /\d{6}-[1-4]\d{6}|\d{6}[1-4]\d{6}/;
        const phoneRegex = /01[016789]-\d{3,4}-\d{4}|01[016789]\d{7,8}|0[2-6]:?\d{1,2}-\d{3,4}-\d{4}/;
        return rrnRegex.test(text) || phoneRegex.test(text);
    }

    // 서버 송신 처리
    async function sendMessage(text) {
        if (isLoading || !text.trim()) return;
        isLoading = true;
        sendBtn.disabled = true;

        stopSpeaking(); // 전송 시 기존 말 정지

        const userMsg = createMessageEl("user", text);
        messagesEl.appendChild(userMsg);
        scrollToBottom();

        if (checkFrontPrivacy(text)) {
            const warnText = "⚠️ <strong>입력하신 내용에 개인정보가 포함되어 있습니다.</strong><br><br>개인정보 보호를 위해 채팅창에 주민등록번호나 전화번호를 입력하지 말아주세요.";
            const botMsg = createMessageEl("bot", warnText, null, false, null);
            messagesEl.appendChild(botMsg);
            scrollToBottom();
            isLoading = false;
            updateSendButton();
            return;
        }

        showTypingIndicator();

        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text }),
            });
            const data = await response.json();
            removeTypingIndicator();

            const botMsg = createMessageEl("bot", data.answer, data.sources, Boolean(data.degraded), data.degraded_reason);
            messagesEl.appendChild(botMsg);
        } catch (err) {
            removeTypingIndicator();
            const errorMsg = createMessageEl("bot", "죄송합니다. 네트워크 통신 오류가 발생했습니다.");
            messagesEl.appendChild(errorMsg);
        }
        scrollToBottom();
        isLoading = false;
        updateSendButton();
    }

    async function clearChat() {
        if (isLoading) return;
        stopSpeaking();

        try { await fetch("/api/clear", { method: "POST" }); } catch (e) {}

        const welcome = messagesEl.querySelector(".welcome-message");
        messagesEl.innerHTML = "";
        if (welcome) {
            messagesEl.appendChild(welcome);
            bindQuickButtons(welcome);
        }
    }

    function updateSendButton() {
        sendBtn.disabled = !inputEl.value.trim() || isLoading;
    }

    function autoResizeInput() {
        inputEl.style.height = "auto";
        inputEl.style.height = Math.min(inputEl.scrollHeight, 100) + "px";
    }

    inputEl.addEventListener("input", function () {
        updateSendButton();
        autoResizeInput();
    });

    inputEl.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!sendBtn.disabled) {
                const text = inputEl.value.trim();
                inputEl.value = "";
                inputEl.style.height = "auto";
                updateSendButton();
                sendMessage(text);
            }
        }
    });

    sendBtn.addEventListener("click", function () {
        const text = inputEl.value.trim();
        if (text) {
            inputEl.value = "";
            inputEl.style.height = "auto";
            updateSendButton();
            sendMessage(text);
        }
    });

    clearBtn.addEventListener("click", function () {
        if (confirm("대화 내역을 모두 삭제하고 초기화하시겠습니까?")) {
            clearChat();
        }
    });

    function bindQuickButtons(container = document) {
        container.querySelectorAll(".quick-btn").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var msg = this.getAttribute("data-msg");
                if (msg && !isLoading) {
                    sendMessage(msg);
                }
            });
        });
    }

    applyUserPreferences();
    bindQuickButtons();
    inputEl.focus();
})();