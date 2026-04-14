# 프론트엔드 설명

이 문서는 사하구청 AI 상담사의 프론트엔드 구조를 설명합니다.

---

## 전체 구조

프론트엔드는 별도의 프레임워크(React, Vue 등) 없이 **Vanilla HTML/CSS/JS**로 구현되어 있습니다.

```
templates/
├── index.html    # 메인 챗봇 페이지
└── widget.html   # iframe 임베딩용 위젯

static/
├── css/style.css # 반응형 스타일시트
└── js/chat.js    # 채팅 클라이언트 로직
```

**왜 Vanilla JS인가?**
- 챗봇 UI는 단일 페이지로 구조가 단순
- React/Vue 등의 빌드 과정 없이 바로 Flask에서 서빙 가능
- 추가 의존성 없이 가볍고 빠름

---

## 1. 페이지 구조 (index.html)

### 레이아웃

```
┌─────────────────────────────────┐
│  헤더 (chat-header)              │  ← 로고, 제목, 초기화 버튼
├─────────────────────────────────┤
│                                 │
│  채팅 영역 (chat-messages)       │  ← 메시지 목록 (스크롤)
│  - 환영 메시지                    │
│  - 빠른 버튼 (구청위치, 복지 등)   │
│  - 사용자/봇 메시지들              │
│  - 출처 카드                     │
│                                 │
├─────────────────────────────────┤
│  입력 영역 (chat-input-area)     │  ← 텍스트 입력 + 전송 버튼
│  "개인정보를 입력하지 마세요"       │
└─────────────────────────────────┘
```

### 주요 요소

**환영 메시지**: 페이지 첫 로딩 시 표시되는 인사말 + 빠른 질문 버튼 4개
```html
<button class="quick-btn" data-msg="사하구청 위치와 연락처 알려줘">구청 위치/연락처</button>
<button class="quick-btn" data-msg="복지 지원 서비스 종류 알려줘">복지 서비스</button>
<button class="quick-btn" data-msg="민원 서류 발급 방법 알려줘">민원 발급</button>
<button class="quick-btn" data-msg="쓰레기 분리수거 방법 알려줘">분리수거 안내</button>
```

빠른 버튼을 누르면 `data-msg` 속성의 텍스트가 자동으로 전송됩니다.

---

## 2. 채팅 클라이언트 (chat.js)

### 즉시실행함수(IIFE) 패턴

```javascript
(function () {
    // 모든 변수와 함수가 이 안에서만 존재
    // 전역 변수 오염 방지
})();
```

### 메시지 전송 흐름

```
사용자가 Enter 또는 전송 버튼 클릭
  → sendMessage(text) 호출
  → 사용자 메시지 화면에 표시
  → 타이핑 인디케이터(점 3개 애니메이션) 표시
  → fetch("/api/chat", { message: text }) 호출
  → 응답 수신
  → 타이핑 인디케이터 제거
  → 봇 메시지 + 출처 카드 화면에 표시
  → 자동 스크롤
```

### 핵심 함수들

| 함수 | 역할 |
|------|------|
| `sendMessage(text)` | API 호출 + 메시지 렌더링 |
| `createMessageEl(role, content, sources)` | 메시지 DOM 요소 생성 |
| `formatBotMessage(text)` | 마크다운 → HTML 변환 (볼드, 이탤릭, 줄바꿈) |
| `createSourcesEl(sources)` | 출처 카드 목록 생성 |
| `showTypingIndicator()` | 로딩 애니메이션 표시 |
| `clearChat()` | 대화 초기화 (서버 + UI 모두) |
| `autoResizeInput()` | 입력창 높이 자동 조절 (최대 120px) |

### 메시지 렌더링 구조

```html
<!-- 봇 메시지 -->
<div class="message bot-message">
  <div class="message-avatar">🤖 (SVG 아이콘)</div>
  <div class="message-content">
    <div class="message-bubble">답변 텍스트</div>
    <!-- 출처가 있을 때만 표시 -->
    <div class="sources-container">
      <div class="sources-label">참고 출처</div>
      <a class="source-card" href="URL" target="_blank">
        <span class="source-icon">🔗</span>
        <span class="source-title">페이지 제목</span>
        <span class="source-badge">서비스유형</span>
      </a>
    </div>
  </div>
</div>

<!-- 사용자 메시지 -->
<div class="message user-message">
  <div class="message-content">
    <div class="message-bubble">사용자가 입력한 텍스트</div>
  </div>
  <div class="message-avatar">👤 (SVG 아이콘)</div>
</div>
```

### 봇 메시지 포맷팅

LLM이 반환하는 텍스트에 마크다운이 포함될 수 있어서, 기본적인 변환을 수행합니다:

```javascript
function formatBotMessage(text) {
    let html = text
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")  // **볼드**
        .replace(/\*(.*?)\*/g, "<em>$1</em>")              // *이탤릭*
        .replace(/\n{2,}/g, "</p><p>")                     // 문단 구분
        .replace(/\n/g, "<br>");                           // 줄바꿈
    html = html.replace(/(\d+)\)\s/g, "<br>$1) ");        // 번호 목록
    return `<p>${html}</p>`;
}
```

### 입력 처리

- **Enter**: 메시지 전송
- **Shift + Enter**: 줄바꿈 (전송 안 됨)
- 최대 500자 제한 (`maxlength="500"`)
- 빈 메시지 전송 불가 (`sendBtn.disabled` 제어)
- 입력 중 전송 버튼 활성화/비활성화 자동 전환

### XSS 방지

사용자 입력이나 서버 응답을 DOM에 삽입할 때 `escapeHtml()` 함수로 HTML 이스케이프 처리합니다:

```javascript
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;  // 텍스트로 설정 (HTML 해석 안 됨)
    return div.innerHTML;    // 이스케이프된 HTML 반환
}
```

이를 통해 `<script>alert('XSS')</script>` 같은 입력이 실행되지 않습니다.

---

## 3. 스타일시트 (style.css)

### CSS 변수 (커스텀 프로퍼티)

```css
:root {
    --primary: #0066CC;       /* 사하구청 블루 */
    --primary-dark: #004C99;
    --primary-light: #E8F0FE;
    --bg: #F5F7FA;            /* 배경색 */
    --text: #1A1A2E;          /* 텍스트 */
    --bot-bubble: #FFFFFF;    /* 봇 메시지 배경 */
    --user-bubble: #0066CC;   /* 사용자 메시지 배경 */
}
```

### 반응형 디자인

**PC (768px 이상):**
```css
@media (min-width: 768px) {
    #chat-app {
        height: 90vh;
        max-height: 800px;
        max-width: 800px;     /* 가운데 정렬된 카드 형태 */
        border-radius: 16px;
    }
    .message { max-width: 75%; }
}
```

**모바일 (767px 이하):**
```css
@media (max-width: 767px) {
    #chat-app {
        border-radius: 0;    /* 전체 화면 */
        max-width: 100%;
    }
    .message { max-width: 90%; }
    .message-bubble { font-size: 13px; }
}
```

### 다크모드

OS 설정에 따라 자동으로 다크모드가 적용됩니다:

```css
@media (prefers-color-scheme: dark) {
    :root {
        --bg: #1A1A2E;
        --white: #16213E;
        --text: #E0E0E0;
        --bot-bubble: #16213E;
        --primary-light: #1A2744;
    }
}
```

사용자가 별도로 토글하는 것이 아닌, 시스템 설정을 따르는 방식입니다.

### 애니메이션

**메시지 등장 애니메이션:**
```css
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}
.message { animation: fadeInUp 0.3s ease; }
```

**타이핑 인디케이터 (점 3개 바운스):**
```css
@keyframes typingBounce {
    0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
    30% { transform: translateY(-6px); opacity: 1; }
}
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
```

---

## 4. 위젯 모드 (widget.html)

사하구청 홈페이지에 iframe으로 임베딩할 수 있는 별도 페이지입니다.

**메인 페이지와의 차이점:**
- 테두리(border-radius)와 그림자(box-shadow) 제거
- 전체 높이(100vh) 사용
- 헤더 서브타이틀 제거 (더 컴팩트)
- 빠른 버튼 3개로 축소

**사하구청 홈페이지에 임베딩하는 방법:**
```html
<iframe src="http://서버주소:5000/widget"
        width="400" height="600"
        style="border: none; border-radius: 12px;">
</iframe>
```

---

## 5. API 통신 정리

프론트엔드에서 호출하는 API:

| 동작 | 메서드 | URL | 요청 바디 | 응답 |
|------|--------|-----|----------|------|
| 메시지 전송 | POST | `/api/chat` | `{ message: "질문" }` | `{ answer, sources, is_clarification }` |
| 대화 초기화 | POST | `/api/clear` | 없음 | `{ status: "ok" }` |

에러 처리:
- 네트워크 오류 → "네트워크 오류가 발생했습니다" 표시
- 서버 500 에러 → "일시적인 오류가 발생했습니다" 표시
- 빈 메시지/500자 초과 → 서버에서 400 에러 반환
