# 백엔드 설명

이 문서는 사하구청 AI 상담사의 백엔드 구조를 설명합니다.

---

## 전체 구조

백엔드는 크게 3가지 역할을 합니다:

1. **데이터 파이프라인** - 사하구청 홈페이지 데이터를 수집하고 가공
2. **챗봇 엔진** - 사용자 질문에 대한 검색 + 답변 생성
3. **웹 서버** - API 제공 및 프론트엔드 서빙

```
[데이터 파이프라인]                    [챗봇 엔진]
crawler/ → processor/ → database_db/  →  chatbot/ → app.py
(크롤링)   (정제+태깅)   (DB+벡터저장)    (검색+답변)  (API서버)
```

---

## 1. 데이터 파이프라인

### 1-1. 크롤링 (crawler/saha_crawler.py)

사하구청 홈페이지(www.saha.go.kr)에서 페이지를 수집합니다.

**크롤링 대상 메뉴 (config.py):**
| 메뉴 | 경로 |
|------|------|
| 분야별정보 | /portal/contents.do?mId=0401000000 |
| 사하복지 | /portal/contents.do?mId=0501000000 |
| 전자민원 | /portal/contents.do?mId=0100000000 |
| 정보공개 | /portal/contents.do?mId=0300000000 |
| 구민참여 | /portal/contents.do?mId=0200000000 |
| 사하소개 | /portal/contents.do?mId=0600000000 |

**크롤링 방식: BFS(너비 우선 탐색)**

```
시작 URL → HTML 가져오기 → 파싱 → 하위 링크 추출 → 큐에 추가 → 반복
```

1. `requests`로 HTTP 요청 (실패 시 최대 3회 재시도)
2. `BeautifulSoup`으로 HTML 파싱
3. 본문 영역 추출 (`.cont_area`, `#contents` 등 우선순위 셀렉터)
4. 사하구청 도메인 내부 링크만 큐에 추가
5. 메뉴당 최대 50페이지, 요청 간 1초 대기

**Selenium fallback**: 본문 텍스트가 200자 미만이면 JS 렌더링이 필요하다고 판단하여 Selenium으로 재시도

**증분 크롤링 (main.py > run_incremental)**:
- 페이지 내용의 MD5 해시(content_hash)를 DB에 저장
- 다음 크롤링 시 해시 비교로 변경/신규/삭제 페이지를 감지
- 변경된 페이지만 재처리하여 서버 부하 최소화

**자동 스케줄링 (APScheduler)**:
- 웹 서버 실행 시 백그라운드 스케줄러가 함께 시작
- 매일 새벽 3시에 `run_incremental()`을 자동 실행
- 별도의 cron 설정 없이 서버 프로세스 하나로 운영

### 1-2. 정제 (processor/data_cleaner.py)

크롤링된 원본 텍스트를 정리합니다.

**정제 과정:**
```
원본 텍스트
  → 연속 공백/줄바꿈 정리
  → 특수문자 제거 (한글, 영문, 숫자, 기본 문장부호만 유지)
  → 반복 문자 제거 ("ㅋㅋㅋㅋㅋ" → "ㅋㅋ")
  → 네비게이션 잔재 제거 ("홈 >", "사이트맵" 등)
  → 유효성 검사 (50자 미만, 한글 10자 미만이면 폐기)
  → 중복 검사 (MD5 해시로 동일 콘텐츠 제거)
  → 청크 분할 (500자 단위, 50자 겹침)
```

**청크 분할 결과물 (CleanedChunk):**
```python
@dataclass
class CleanedChunk:
    chunk_id: str       # MD5(url + index) - 고유 식별자
    url: str            # 원본 페이지 URL
    title: str          # 페이지 제목
    content: str        # 정제된 텍스트 (최대 500자)
    category: str       # 메뉴 카테고리 (예: "사하복지")
    sub_category: str   # 브레드크럼 경로
    chunk_index: int    # 해당 페이지에서 몇 번째 청크인지
    total_chunks: int   # 해당 페이지의 총 청크 수
```

### 1-3. 메타데이터 태깅 (processor/metadata_tagger.py)

Groq LLM(Llama 3.3 70B)을 사용하여 각 청크에 메타데이터를 자동 부여합니다.

**태깅 결과 예시:**
```json
{
  "service_type": "환경",
  "target_audience": ["전체시민"],
  "keywords": ["쓰레기", "분리수거", "재활용", "수거일"],
  "has_deadline": false,
  "has_contact_info": true,
  "summary": "사하구 쓰레기 분리수거 요일 및 방법 안내"
}
```

**Rate Limit 대응:**
- Groq 무료 티어는 분당 호출 제한이 있음
- 청크 간 25초 간격으로 호출 (분당 2~3회)
- API 할당량이 부족할 때를 대비한 `quick_pipeline.py` 제공 (태깅 생략)

### 1-4. 벡터 임베딩 (database_db/vector_store.py)

정제된 청크를 384차원 벡터로 변환하여 Supabase에 저장합니다.

```
청크 텍스트 → HuggingFace MiniLM-L12-v2 → 384차원 벡터 → Supabase documents 테이블
```

- 배치 처리: 50개씩 묶어서 upsert
- 임베딩 모델은 로컬 CPU에서 실행 (외부 API 호출 없음, 비용 없음)

---

## 2. 데이터베이스 (database_db/database.py)

### Supabase PostgreSQL

모든 데이터는 Supabase(클라우드 PostgreSQL)에 저장됩니다.

**테이블 구조:**

```
raw_pages (크롤링 원본)
├── id (serial PK)
├── url (unique)
├── title, content
├── category, sub_category
├── content_hash (MD5 - 변경 감지용)
└── crawled_at, updated_at

processed_chunks (정제 청크)
├── chunk_id (text PK)
├── url, title, content
├── category, sub_category
├── chunk_index, total_chunks
├── service_type, target_audience, keywords
├── has_deadline, has_contact_info, summary
├── embedded (boolean - 임베딩 완료 여부)
└── created_at

documents (벡터 저장소)
├── id (text PK)
├── content
├── embedding (vector(384))
├── metadata (jsonb)
└── created_at

conversation_logs (대화 이력)
├── id (serial PK)
├── session_id
├── role ("user" | "assistant")
├── content
├── sources
└── created_at
```

**인덱스:**
- `documents.embedding`: HNSW 인덱스 (벡터 검색 성능 최적화)
- `documents.metadata`: GIN 인덱스 (JSONB 메타데이터 필터링)
- `conversation_logs`: session_id + created_at 복합 인덱스

---

## 3. 챗봇 엔진

### 3-1. 하이브리드 검색 (chatbot/retriever.py)

사용자 질문이 들어오면 2단계로 관련 문서를 찾습니다.

```
질문 → detect_category()로 카테고리/서비스유형 감지
     → hybrid_search()로 메타데이터 필터 + 벡터 검색
     → 결과 부족 시 similarity_search()로 전체 범위 폴백
     → format_context()로 LLM 컨텍스트 + 출처 생성
```

**출처 관련성 필터링:**
- 질문의 키워드가 문서 제목/내용에 실제로 포함되어 있는지 확인
- 불용어("알려줘", "어떻게" 등)를 제외한 핵심 키워드만 사용
- 이를 통해 관련 없는 문서가 출처로 표시되는 것을 방지

### 3-2. 대화 처리 (chatbot/conversation.py)

전체 대화 흐름:

```
1. 개인정보 체크 → 감지 시 경고 반환, LLM 전달 안 함
2. 대화 이력 조회 → 최근 10개 대화
3. 검색어 구성 → 이전 대화 + 현재 질문 합치기
4. 하이브리드 검색 → 관련 문서 5개 조회
5. LLM 답변 생성 → Groq API 호출 (4초 간격 Rate Limit)
6. 역질문 감지 → 특정 키워드로 판단
7. 대화 이력 저장 → Supabase에 user/assistant 메시지 저장
8. 응답 반환 → {answer, sources, is_clarification}
```

**LLM 설정:**
- 모델: Groq Llama 3.3 70B Versatile
- Temperature: 0.3 (낮게 설정하여 일관된 답변)
- 시스템 프롬프트: 6가지 규칙 (사실 기반, 모호한 질문 역질문, 출처 명시, 개인정보 보호, 정보 부족 시 안내, 답변 형식)

---

## 4. 웹 서버 (app.py)

### Flask API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/` | 메인 챗봇 페이지 |
| POST | `/api/chat` | 챗봇 대화 API |
| POST | `/api/clear` | 대화 초기화 |
| GET | `/api/stats` | 시스템 통계 |
| GET | `/widget` | iframe 임베딩용 위젯 |

### `/api/chat` 요청/응답

요청:
```json
{
  "message": "사하구청 위치가 어디야?"
}
```

응답:
```json
{
  "answer": "사하구청은 부산광역시 사하구 낙동대로 398번길...",
  "sources": [
    {
      "title": "구청 오시는 길",
      "url": "https://www.saha.go.kr/...",
      "category": "사하소개",
      "service_type": "기타"
    }
  ],
  "is_clarification": false
}
```

### 세션 관리

- Flask `session`에 UUID 기반 `session_id` 저장
- session_id로 대화 이력을 구분 (멀티턴 지원)
- 대화 초기화 시 새 session_id 발급

---

## 5. Quick Pipeline (quick_pipeline.py)

Gemini/Groq API 할당량 문제를 우회하기 위한 경량 파이프라인입니다.

**일반 파이프라인 vs Quick Pipeline:**

| 단계 | 일반 파이프라인 | Quick Pipeline |
|------|---------------|----------------|
| 크롤링 | O (main.py) | X (이미 크롤링된 데이터 사용) |
| 정제 | O | O |
| LLM 태깅 | O (API 호출 필요) | **X (생략)** |
| 메타데이터 | LLM이 추출 | 기본값 사용 (service_type="기타") |
| 벡터 임베딩 | O | O |

**왜 만들었나:**
- 개발 중 Gemini API 할당량(Rate Limit)에 걸려 파이프라인이 중단됨
- LLM 태깅은 청크마다 API를 호출하므로 할당량 소모가 큼
- 태깅 없이도 벡터 검색은 가능하므로, 임베딩까지만 완료하는 경량 버전을 제작
- 나중에 할당량이 확보되면 다시 정상 파이프라인으로 태깅 가능

---

## 6. 설정 (config.py)

| 설정 | 값 | 설명 |
|------|------|------|
| GROQ_LLM_MODEL | llama-3.3-70b-versatile | LLM 모델 |
| CHUNK_SIZE | 500 | 청크 최대 글자 수 |
| CHUNK_OVERLAP | 50 | 청크 간 겹침 |
| MAX_CONVERSATION_HISTORY | 10 | 멀티턴 기억 범위 |
| MAX_RETRIEVAL_RESULTS | 5 | 검색 결과 수 |
| CHATBOT_TEMPERATURE | 0.3 | LLM 응답 일관성 |
| CRAWL_DELAY | 1.0초 | 크롤링 요청 간격 |
| MAX_PAGES_PER_MENU | 50 | 메뉴당 최대 크롤링 수 |
