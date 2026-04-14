# 사하구청 AI 상담사

부산광역시 사하구청 홈페이지 공식 정보를 기반으로, 주민의 질문에 자연어로 답변하는 RAG 기반 AI 챗봇 시스템입니다.

## 프로젝트 개요

### 왜 만들었나?

사하구청 홈페이지는 메뉴가 복잡하여 원하는 정보를 찾기 어렵습니다. 주민이 "맨홀 뚜껑이 깨졌어"라고 자연어로 질문하면, AI가 관련 부서와 연락처를 즉시 안내하는 시스템을 구축했습니다.

### 핵심 차별점

- **단순 챗봇이 아닌 데이터 파이프라인**: 크롤링 → 정제 → 태깅 → 벡터화까지 자동화
- **하이브리드 검색**: 메타데이터 필터링 + 벡터 유사도 검색을 결합하여 정확도 향상
- **환각 방지**: 사하구청 공식 데이터만 사용, 모르는 건 모른다고 답변
- **개인정보 보호**: 주민등록번호, 전화번호 등 입력 시 LLM 전달 전 차단

## 기술 스택

| 분류 | 기술 |
|------|------|
| 언어 | Python 3.12 |
| 웹 서버 | Flask |
| LLM | Groq (Llama 3.3 70B) |
| 임베딩 | HuggingFace sentence-transformers (MiniLM-L12-v2) |
| 벡터 DB | Supabase PostgreSQL + pgvector |
| 크롤링 | requests + BeautifulSoup (Selenium fallback) |
| 프론트엔드 | HTML/CSS/JS (Vanilla) |
| 프레임워크 | LangChain |

## 시스템 아키텍처

```
[사하구청 홈페이지]
        |
    (1) 크롤링 (requests + BeautifulSoup)
        |
    (2) 텍스트 정제 (DataCleaner)
        |
    (3) LLM 메타데이터 태깅 (Groq)
        |
    (4) 벡터 임베딩 (MiniLM-L12-v2)
        |
    (5) Supabase pgvector 저장
        |
    ────────────────────────────
        |
[사용자 질문]
        |
    (A) 개인정보 필터링 (정규식)
        |
    (B) 하이브리드 검색 (메타데이터 + 벡터)
        |
    (C) LLM 답변 생성 (Groq)
        |
    (D) 출처 카드와 함께 응답 반환
```

## 디렉토리 구조

```
sahahaha/
├── app.py                 # Flask 웹 서버
├── main.py                # 실행 진입점 (crawl/process/embed/web)
├── config.py              # 환경 설정
├── quick_pipeline.py      # 경량 파이프라인 (태깅 생략)
├── setup_supabase.sql     # DB 스키마 초기화
├── requirements.txt       # Python 의존성
│
├── crawler/
│   └── saha_crawler.py    # 사하구청 홈페이지 크롤러
│
├── processor/
│   ├── data_cleaner.py    # 텍스트 정제 + 청크 분할
│   └── metadata_tagger.py # LLM 기반 메타데이터 자동 태깅
│
├── chatbot/
│   ├── retriever.py       # 하이브리드 검색 (메타+벡터)
│   └── conversation.py    # 멀티턴 대화 + 개인정보 필터링
│
├── database_db/
│   ├── database.py        # Supabase DB CRUD
│   └── vector_store.py    # 벡터 임베딩 + 유사도 검색
│
├── templates/
│   ├── index.html         # 메인 챗봇 UI
│   └── widget.html        # iframe 임베딩용 위젯
│
├── static/
│   ├── css/style.css      # 반응형 UI 스타일
│   └── js/chat.js         # 채팅 클라이언트
│
└── document/              # 프로젝트 문서
    ├── README.md          # 이 파일
    ├── algorithm.md       # 알고리즘 설명
    ├── backend.md         # 백엔드 설명
    ├── frontend.md        # 프론트엔드 설명
    └── presentation.md    # 발표 대본
```

## 실행 방법

### 1. 환경 설정

```bash
pip install -r requirements.txt
```

`.env` 파일을 생성하고 아래 키를 설정합니다:

```
GROQ_API_KEY=your_groq_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
```

### 2. DB 초기화

Supabase Dashboard > SQL Editor에서 `setup_supabase.sql`을 실행합니다.

### 3. 데이터 파이프라인

```bash
# 전체 파이프라인 (크롤링 → 정제 → 임베딩)
python main.py --mode all

# 각 단계별 실행
python main.py --mode crawl         # 크롤링
python main.py --mode process       # 정제 + 태깅
python main.py --mode embed         # 벡터 임베딩

# 증분 크롤링 (변경된 페이지만)
python main.py --mode incremental

# 경량 파이프라인 (태깅 생략, API 할당량 부족 시)
python quick_pipeline.py
```

### 4. 웹 서버

```bash
python main.py --mode web
# http://127.0.0.1:5000 에서 접속
```

## 상세 문서

- [알고리즘 설명](algorithm.md) - RAG, 하이브리드 검색, 벡터 유사도 등 핵심 알고리즘
- [백엔드 설명](backend.md) - 서버, DB, 데이터 파이프라인, API
- [프론트엔드 설명](frontend.md) - UI/UX, 채팅 클라이언트, 반응형 디자인
- [발표 대본](presentation.md) - 프로젝트 발표용 대본

## 팀 정보

- 프로젝트: SW중심대학사업 2026학년도 실증적 SW/AI 프로젝트
- 기업: 부산광역시 사하구청
- 멘토교수: 김현석 (hertzkim@dau.ac.kr)
