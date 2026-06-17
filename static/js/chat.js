/**
 * 사하구청 AI 상담사 - 채팅 통합 스크립트 클라이언트 (TTS + STT 음성인식 통합 버전)
 */
(function () {
    const messagesEl = document.getElementById("chat-messages");
    const inputEl = document.getElementById("user-input");
    const sendBtn = document.getElementById("btn-send");
    const clearBtn = document.getElementById("btn-clear");
    const micBtn = document.getElementById("btn-mic"); // 🎯 마이크 버튼 엘리먼트 추가

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

    // ===== STT (음성 인식) 웹 표준 API 설정 =====
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;
    let isListeningSTT = false; // 마이크 작동 상태 플래그

    // 🎯 디자인 일관성을 위한 SVG 아이콘 정의 (스피커 & 마이크)
    const ICON_PLAY = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5L6 9H2v6h4l5 4V5z"></path><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>`;
    const ICON_STOP = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"></rect></svg>`;
    
    // 🎤 마이크 기본 아이콘 및 녹음 중(네모/정지) 아이콘
    const ICON_MIC_READY = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>`;
    const ICON_MIC_LISTENING = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" fill="currentColor"></rect></svg>`;

    // 브라우저가 음성 인식을 지원하는지 확인 후 초기화
    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.continuous = false;     // 한 문장만 인식 후 자동 종료
        recognition.interimResults = false;  // 중간 중간 웅얼거리는 건 무시하고 최종 결과만 추출
        recognition.lang = 'ko-KR';          // 대한민국 한국어 설정

        // 음성 인식 시작 시
        recognition.onstart = function() {
            isListeningSTT = true;
            if (micBtn) {
                micBtn.innerHTML = ICON_MIC_LISTENING;
                micBtn.classList.add("listening");
                micBtn.setAttribute("title", "음성 인식 중지");
            }
        };

        // 음성 인식 성공 시 결과 처리
        recognition.onresult = function(event) {
            const speechToText = event.results[0][0].transcript;
            if (inputEl) {
                // 기존에 쓰던 글이 있다면 이어서 붙여줌
                inputEl.value = (inputEl.value + " " + speechToText).trim();
                updateSendButton();
                autoResizeInput();
                inputEl.focus();
            }
        };

        // 음성 인식 종료 시 (에러가 나든 정상 종료되든 무조건 실행)
        recognition.onend = function() {
            stopListening();
        };

        // 에러 발생 시 처리
        recognition.onerror = function(event) {
            console.error("STT 에러 발생: ", event.error);
            stopListening();
        };
    } else {
        // 브라우저가 STT를 지원하지 않는 경우 마이크 버튼 숨김 처리
        if (micBtn) micBtn.style.display = 'none';
        console.warn("이 브라우저는 웹 표준 음성 인식(STT)을 지원하지 않습니다.");
    }

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

    // 설정 톱니바퀴 토글
    if (btnSettings && settingsMenu) {
        btnSettings.addEventListener("click", function(e) {
            e.preventDefault();
            e.stopPropagation();
            settingsMenu.classList.toggle("hidden");
        });

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
        // 🎯 TTS 켜질 때 마이크(STT)가 켜져 있으면 꺼버림 (하울링/루프 방지)
        stopListening();

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

    // ===== STT 음성 인식 제어 함수 =====
    function startListening() {
        if (!recognition || isLoading) return;
        
        // 🎯 마이크 켜기 전, AI가 말하고 있었다면 TTS 목소리를 끕니다.
        stopSpeaking();

        try {
            recognition.start();
        } catch (e) {
            console.error("음성 인식 시작 실패:", e);
        }
    }

    function stopListening() {
        isListeningSTT = false;
        if (recognition) {
            try { recognition.stop(); } catch(e) {}
        }
        if (micBtn) {
            micBtn.innerHTML = ICON_MIC_READY;
            micBtn.classList.remove("listening");
            micBtn.setAttribute("title", "음성으로 말하기");
        }
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

        function normalizeDeptName(value) {
            return String(value || "").replace(/\s+/g, "");
        }

        function findMatchedDeptSource(sourceList, text) {
            const normalizedText = normalizeDeptName(text);
            const deptSources = (sourceList || []).filter(function (src) {
                return src && src.department;
            });

            for (const src of deptSources) {
                const dept = normalizeDeptName(src.department);
                if (dept && normalizedText.includes(dept)) {
                    return src;
                }
            }

            return null;
        }

        if (role === "user") {
            bubble.textContent = content;
        } else {
            bubble.innerHTML = formatBotMessage(content);
            
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = bubble.innerHTML;
            plainTextContent = tempDiv.textContent || tempDiv.innerText;

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
            bubble.appendChild(ttsControls); 

            if (sources && sources.length > 0) {
                const deptSrc = findMatchedDeptSource(sources, content);
                if (deptSrc && deptSrc.department) {
                    const phone = deptSrc.contact || "";
                    const guide = document.createElement("div");
                    guide.className = "bubble-contact bubble-contact-highlight";
                    guide.innerHTML = `담당부서 <b>${escapeHtml(deptSrc.department)}</b> · 연락처 ${phone ? `<a href="tel:${phone.replace(/[^0-9]/g, "")}">${escapeHtml(phone)}</a>` : "안내 없음"}`;
                    bubble.appendChild(guide);
                }
            }
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
        const lines = String(text)
            .replace(/\r\n/g, "\n")
            .split("\n")
            .map(line => line.trim())
            .filter((line, index, arr) => line !== "" || (index > 0 && arr[index - 1] !== ""));

        const compactLines = [];
        for (const line of lines) {
            if (compactLines.length === 0 || compactLines[compactLines.length - 1] !== line) {
                compactLines.push(line);
            }
        }

        const escape = (value) => escapeHtml(value);
        const renderInline = (value) => {
            return escape(value)
                .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
                .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
                .replace(/\*(.+?)\*/g, "<em>$1</em>");
        };

        const highlightPrefixes = [
            "핵심",
            "중요",
            "결론",
            "요약",
            "먼저",
            "우선",
            "필수",
            "가장 필요한 정보",
            "바로 해야 할 일",
        ];

        const chunks = [];
        let listType = null;
        let listItems = [];
        let paragraphCount = 0;

        const flushList = () => {
            if (!listType || listItems.length === 0) return;
            const tag = listType === "ol" ? "ol" : "ul";
            chunks.push(`<${tag}>${listItems.map(item => `<li>${renderInline(item)}</li>`).join("")}</${tag}>`);
            listType = null;
            listItems = [];
        };

        for (const rawLine of compactLines) {
            const bulletMatch = rawLine.match(/^(?:[-*]\s+)(.+)$/);
            const numberMatch = rawLine.match(/^(\d+)[.)]\s+(.+)$/);

            if (bulletMatch) {
                if (listType && listType !== "ul") flushList();
                listType = "ul";
                listItems.push(bulletMatch[1]);
                continue;
            }

            if (numberMatch) {
                if (listType && listType !== "ol") flushList();
                listType = "ol";
                listItems.push(numberMatch[2]);
                continue;
            }

            flushList();
            if (rawLine) {
                const shouldHighlight = paragraphCount === 0 || highlightPrefixes.some(prefix => rawLine.startsWith(prefix));
                const className = shouldHighlight ? ' class="answer-highlight"' : "";
                chunks.push(`<p${className}>${renderInline(rawLine)}</p>`);
                paragraphCount += 1;
            }
        }

        flushList();
        return chunks.join("");
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

            const deptLine = src.department
                ? `<span class="source-dept">🏛️ 담당: ${escapeHtml(src.department)}</span>`
                : "";

            card.innerHTML = `
                <span class="source-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></span>
                <span class="source-body">
                    <span class="source-title">${escapeHtml(src.title)}</span>
                    ${deptLine}
                </span>
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

    // 스크롤 제어
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
        const addressRegex = /[가-힣]{1,20}(?:동|읍|면|리)\s*\d{1,4}(?:-\d{1,4})?(?:\s*(?:번지|호|층))?|[가-힣]{1,20}(?:로|길)\s*\d{1,4}(?:-\d{1,4})?(?:\s*(?:번지|호|층))?/;
        const emailRegex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;
        return rrnRegex.test(text) || phoneRegex.test(text) || addressRegex.test(text) || emailRegex.test(text);
    }

    // 서버 송신 처리
    async function sendMessage(text) {
        if (isLoading || !text.trim()) return;
        isLoading = true;
        sendBtn.disabled = true;

        stopSpeaking();   // 전송 시 기존 말 정지
        stopListening();  // 전송 시 마이크 무조건 종료

        const userMsg = createMessageEl("user", text);
        messagesEl.appendChild(userMsg);
        scrollToBottom();

        if (checkFrontPrivacy(text)) {
            const warnText = "⚠️ 입력하신 내용에 개인정보가 포함되어 있습니다.\n\n개인정보 보호를 위해 채팅창에 주민등록번호, 전화번호, 이메일, 상세주소를 입력하지 말아주세요.";
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
        stopListening(); // 초기화 시 마이크 정지

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

    // ===== 이벤트 리스너 세팅 =====

    // 🎯 마이크 버튼 클릭 핸들러 추가
    if (micBtn) {
        micBtn.addEventListener("click", function(e) {
            e.preventDefault();
            if (isLoading) return;
            
            if (isListeningSTT) {
                stopListening(); // 녹음 중이었으면 수동 중지
            } else {
                startListening(); // 대기 중이었으면 녹음 시작
            }
        });
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
    
    // 페이지 로드 시 마이크 버튼 모양 초기 세팅
    if (micBtn && SpeechRecognition) {
        micBtn.innerHTML = ICON_MIC_READY;
        micBtn.setAttribute("title", "음성으로 말하기");
    }

    inputEl.focus();
})();
