/**
 * 사하구청 AI 상담사 - 채팅 클라이언트
 */
(function () {
    const messagesEl = document.getElementById("chat-messages");
    const inputEl = document.getElementById("user-input");
    const sendBtn = document.getElementById("btn-send");
    const clearBtn = document.getElementById("btn-clear");

    let isLoading = false;

    // ===== 메시지 렌더링 =====

    function createMessageEl(role, content, sources) {
        const msg = document.createElement("div");
        msg.className = `message ${role === "user" ? "user-message" : "bot-message"}`;

        const avatar = document.createElement("div");
        avatar.className = "message-avatar";

        if (role === "user") {
            avatar.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" fill="#fff"/>
            </svg>`;
        } else {
            avatar.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" fill="#0066CC"/>
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" fill="#fff"/>
            </svg>`;
        }

        const contentDiv = document.createElement("div");
        contentDiv.className = "message-content";

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";

        if (role === "user") {
            bubble.textContent = content;
        } else {
            bubble.innerHTML = formatBotMessage(content);
        }

        contentDiv.appendChild(bubble);

        // 출처 카드 추가
        if (sources && sources.length > 0) {
            const sourcesDiv = createSourcesEl(sources);
            contentDiv.appendChild(sourcesDiv);
        }

        msg.appendChild(avatar);
        msg.appendChild(contentDiv);
        return msg;
    }

    function formatBotMessage(text) {
        // 마크다운 기본 변환
        let html = text
            .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
            .replace(/\*(.*?)\*/g, "<em>$1</em>")
            .replace(/\n{2,}/g, "</p><p>")
            .replace(/\n/g, "<br>");

        // 번호 목록 변환
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
                <span class="source-icon">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0066CC" stroke-width="2">
                        <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
                        <polyline points="15 3 21 3 21 9"/>
                        <line x1="10" y1="14" x2="21" y2="3"/>
                    </svg>
                </span>
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
            <div class="message-avatar">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" fill="#0066CC"/>
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" fill="#fff"/>
                </svg>
            </div>
            <div class="message-content">
                <div class="message-bubble">
                    <div class="typing-indicator">
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                    </div>
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

    // ===== API 통신 =====

    async function sendMessage(text) {
        if (isLoading || !text.trim()) return;
        isLoading = true;
        sendBtn.disabled = true;

        // 사용자 메시지 표시
        const userMsg = createMessageEl("user", text);
        messagesEl.appendChild(userMsg);
        scrollToBottom();

        // 로딩 표시
        showTypingIndicator();

        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text }),
            });

            const data = await response.json();

            removeTypingIndicator();

            // 봇 답변 표시
            const botMsg = createMessageEl("bot", data.answer, data.sources);
            messagesEl.appendChild(botMsg);

        } catch (err) {
            removeTypingIndicator();

            const errorMsg = createMessageEl(
                "bot",
                "죄송합니다. 네트워크 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
            );
            messagesEl.appendChild(errorMsg);
        }

        scrollToBottom();
        isLoading = false;
        updateSendButton();
    }

    async function clearChat() {
        if (isLoading) return;

        try {
            await fetch("/api/clear", { method: "POST" });
        } catch (e) {
            // ignore
        }

        // 채팅 영역 초기화 (환영 메시지만 남김)
        const welcome = messagesEl.querySelector(".welcome-message");
        messagesEl.innerHTML = "";
        if (welcome) {
            messagesEl.appendChild(welcome);
            // 빠른 버튼 이벤트 재연결
            bindQuickButtons();
        }
    }

    // ===== 입력 처리 =====

    function updateSendButton() {
        sendBtn.disabled = !inputEl.value.trim() || isLoading;
    }

    function autoResizeInput() {
        inputEl.style.height = "auto";
        inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + "px";
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
        if (confirm("대화를 초기화하시겠습니까?")) {
            clearChat();
        }
    });

    // ===== 빠른 버튼 =====

    function bindQuickButtons() {
        document.querySelectorAll(".quick-btn").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var msg = this.getAttribute("data-msg");
                if (msg && !isLoading) {
                    sendMessage(msg);
                }
            });
        });
    }

    bindQuickButtons();

    // 초기 포커스
    inputEl.focus();
})();
