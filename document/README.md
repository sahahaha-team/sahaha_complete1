# 사하구청 AI 상담사

부산광역시 사하구청 홈페이지 공식 정보를 기반으로, 주민의 질문에 자연어로 답변하는 RAG 기반 AI 챗봇 시스템입니다.

2026-2학기 수행계획서의 개발 방향과 현재 변경 사항은
[프로젝트 개발 맥락](project_context.md)을 참고하세요.

## 프로젝트 개요

### 왜 만들었나?

사하구청 홈페이지는 메뉴가 복잡하여 원하는 정보를 찾기 어렵습니다. 주민이 "맨홀 뚜껑이 깨졌어"라고 자연어로 질문하면, AI가 관련 부서와 연락처를 즉시 안내하는 시스템을 구축했습니다.

### 핵심 차별점

- **단순 챗봇이 아닌 데이터 파이프라인**: 크롤링 → 정제 → 태깅 → 벡터화까지 자동화
- **하이브리드 검색**: 메타데이터 필터링 + 벡터 검색 + BM25 재랭킹으로 정확도 향상
- **환각 방지**: 사하구청 공식 데이터만 사용, 모르는 건 모른다고 답변
- **개인정보 보호**: 주민등록번호, 전화번호 등 입력 시 LLM 전달 전 차단
- **자동 데이터 갱신**: 상담 Web과 분리된 Worker가 매일 증분 크롤링 실행

## 기술 스택

| 분류 | 기술 |
|------|------|
| 언어 | Python 3.12 |
| 웹 서버 | FastAPI + Uvicorn |
| LLM | 로컬 Ollama (`gemma2:2b`, 환경변수로 변경 가능) |
| 임베딩 | HuggingFace sentence-transformers (MiniLM-L12-v2) |
| 벡터 DB | Supabase PostgreSQL + pgvector |
| 크롤링 | requests + BeautifulSoup (Selenium fallback) |
| 스케줄러 | 별도 APScheduler Worker (증분 크롤링 자동화, 매일 03:00) |
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
    (3) LLM 메타데이터 태깅 (로컬 Ollama)
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
    (B) 하이브리드 검색 (메타데이터 + 벡터 + BM25 + 직원업무안내)
        |
    (C) 공식 근거의 최신성·질문 의도 확인
        |
    (D) Gemma가 질문에 맞는 근거 항목·대상·예외 선택 (기본)
        |  └─ 검증된 원문 항목으로 짧게 표시, 모델 실패 시 원문 발췌
        |
    (E) 핵심 답변 + 접힌 공식 원문 + 출처 카드
```

화재 신고는 공식 긴급 안내를, 부서·전화번호는 로컬 전용 파일을 먼저 사용합니다.
범위가 넓으면 검색 전에 한 가지 확인 질문을 하고, 비용·배출요일 등 지원하는 항목은
공식 표를 직접 읽습니다. 이 경로에서는 Ollama로 답변을 생성하지 않습니다.

## 디렉토리 구조

```
sahahaha/
├── app.py                 # FastAPI 웹 서버
├── main.py                # 실행 진입점 (crawl/process/embed/web/worker)
├── worker.py              # 웹과 분리된 증분 크롤링 Worker
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
│   ├── retriever.py       # 하이브리드 검색 + 근거 신뢰도 판정
│   ├── crawled_pages.py   # 전체 크롤링 원문 검색 (청크 누락 보강)
│   ├── answer_goal.py     # 서비스 주제와 요청 항목 구분
│   ├── evidence.py        # 외부 의존성 없는 검색 근거 게이트
│   ├── contact_directory.py # 로컬 공식 업무·연락처 조회
│   ├── emergency_guidance.py # 화재 신고 즉시 안내
│   ├── grounded_planner.py   # Gemma 근거·조건 선택 및 원문 검증
│   ├── reference_answers.py # 공식 페이지·현황도·첨부파일 확인 경로 안내
│   ├── verified_facts.py  # 공식 표의 금액·배출요일 조회
│   ├── source_answers.py  # 질문과 일치하는 공식 원문 구간 선택
│   ├── concise_answers.py # 짧은 핵심 답변 + 접힌 원문
│   ├── answer_completion.py # 문장 완결성·조건·예외 검사
│   ├── question_intent.py # 시간·장소 질문 구분
│   ├── vaccination.py    # 백신별 접종 장소와 사업 범위 구분
│   ├── response_helpers.py # 역질문·후속 질문 UX 로직
│   └── conversation.py    # 멀티턴 대화 + 개인정보 필터링
│
├── data/
│   ├── department_contacts.json # Git에 포함된 공식 연락처 파일
│   └── official_sources/ # 담당자 제공 원본 파일 (Git 제외, 별도 준비)
│
├── scripts/
│   ├── ingest_official_materials.py # 담당자 자료·공식 URL 적재 및 갱신
│   └── build_contact_directory.py   # 공식 연락처 파일 갱신
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
    ├── presentation.md    # 발표 대본
    └── project_context.md # 수행계획서와 현재 개발 방향·변경 기록
```

## 실행 방법

명령은 저장소 루트에서 실행합니다. 이 PC의 작업 폴더는 `C:\sahahaha`이며,
`document` 폴더 안에서 실행하지 않습니다. 이미 환경과 DB를 구성했다면
[웹 서버 실행](#4-웹-서버)으로 이동하세요.

### 1. 환경 설정

Python 3.12와 Ollama를 준비합니다. 새 PC에서 Python 가상환경을 만드는 예시입니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

이미 Python 환경이 준비되어 있다면 가상환경 생성은 생략합니다. 이 작업 PC의
Python 경로는 `.\.venv\python.exe`이므로, 아래 `python` 명령 대신 이 경로를
사용할 수 있습니다. 패키지 설치와 최초 데이터 적재·웹 실행 때는 임베딩 모델·
형태소 분석기 다운로드를 위한 인터넷 연결이 필요합니다.

최초 설정 시 루트의 `.env.example`을 `.env`로 복사하고 값을 채웁니다.
기존 `.env`가 있으면 해당 파일의 설정을 수정합니다.

```ini
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma2:2b
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_SERVICE_KEY=your_supabase_service_key
SECRET_KEY=your_random_secret_at_least_32_chars
ADMIN_API_KEY=your_random_admin_api_key
SOURCE_ONLY_ANSWERS=false
PERSIST_CONVERSATIONS=false
FLASK_HOST=127.0.0.1
FLASK_PORT=5000
```

위 값은 예시입니다. URL과 두 Supabase 키는 같은 프로젝트의 값으로 설정합니다.
`SUPABASE_SERVICE_KEY`는 **기본 공식 원문 답변의 원본 조회**, 크롤링·임베딩·Worker에
필요합니다. `raw_pages`는 anon 접근을 허용하지 않으므로 공개 키만으로는 기본 상담의
원문을 확인할 수 없습니다. service 키는 서버의 `.env`에서만 사용하고 Git·브라우저에
넣지 않습니다. 현재 저장·검색은 Supabase PostgreSQL을 사용하므로 MySQL 설정은 필요 없습니다.

`SECRET_KEY`는 32자 이상의 임의 문자열로 바꾸고, 관리자 API를 사용하려면
`ADMIN_API_KEY`도 별도 임의 문자열로 설정합니다. 웹 서버는 FastAPI + Uvicorn이며,
주소·포트 환경변수는 기존 호환 이름인 `FLASK_HOST`, `FLASK_PORT`를 사용합니다.

로컬 Gemma에는 Groq·Google API 키가 필요하지 않습니다. **데이터 정제·태깅 전에**
Ollama 서비스를 실행하고 모델을 준비합니다.

```powershell
# Ollama 서비스가 실행되지 않은 경우 별도 터미널에서 실행하고 유지
ollama serve
```

```powershell
# 다른 터미널에서 최초 1회 모델 다운로드 후 설치 목록 확인
ollama pull gemma2:2b
ollama list
```

Ollama 앱이나 서비스가 이미 실행 중이면 `ollama serve`는 생략합니다.
모델을 교체할 때는 새 모델을 내려받고 `.env`의 `OLLAMA_MODEL`을 바꾼 뒤
웹 서버와 Worker를 재시작합니다.

### 2. DB 초기화

Supabase Dashboard > SQL Editor에서 `setup_supabase.sql`을 실행합니다.

팀 `main`의 FAQ·HTML 수집 기능을 병합한 기존 DB에는
`scripts/migration_official_faq_and_html.sql`을 한 번 적용하면 원본 HTML과
FAQ 관리용 테이블을 저장할 수 있습니다. 미적용 DB에서도 웹 상담과 기존 텍스트
크롤링은 동작하며, HTML 컬럼이 없으면 텍스트 저장으로 이어집니다.

```bash
# 선택: FAQ 초안을 DB 관리용 테이블에 동기화 (마이그레이션 적용 후)
python scripts/sync_official_faq.py --apply
python scripts/check_migration.py

# 직원 자료를 팀의 경량 인덱스 형식으로 내보내기
python scripts/build_department_contacts.py

# 100문항 질문/URL 매칭 검사 (전체 상담 정답률과는 다름)
python scripts/evaluate_official_faq.py
```

`resources/official_faq.json`과 `resources/priority_services.json`의 질문·유사 표현을
공식 페이지 검색에 활용합니다. 파일에 있는 예상 답변과 수동 확인일은 현재 행정정보의
근거로 바로 사용하지 않으며, 상담 답변은 최근 확인된 크롤링 원문에서 검증합니다.
원본 엑셀이 없는 새 PC에서도 JSON의 질문·URL 목록을 이용할 수 있습니다.
`scripts/ingest_official_materials.py --pages-only`와 Worker의 공식 페이지 갱신은
이 JSON 목록 및 우선 서비스의 추가 URL도 수집합니다. 유효 본문이 없는 URL은
답변 근거로 사용하지 않습니다.
제목·표 구조는 원본 HTML에서 검색 청크로 만들고, 전체 원문 텍스트도 함께 유지하여
기존 수수료·요일 표 조회와 조건 검증을 보존합니다.

`scripts/build_department_contacts.py`는 팀의 `resources/department_contacts.json`을
내보내는 도구입니다. 실제 주민 상담용 번호와 공식 대표번호를 갱신할 때는
아래의 `scripts/build_contact_directory.py --refresh`를 사용합니다.

기존 운영 DB를 갱신할 때는 `scripts/migration_crawl_audit_and_security.sql`을
한 번 실행합니다. 이 마이그레이션은 대화 로그의 anon 접근을 차단하고
증분 크롤링 실행 이력 및 페이지 마지막 확인 시각을 추가합니다.

### 3. 데이터 파이프라인

```bash
# 전체 파이프라인 (크롤링 → 정제·Ollama 태깅 → 임베딩)
python main.py --mode all

# 각 단계별 실행
python main.py --mode crawl         # 크롤링
python main.py --mode process       # 정제 + 태깅
python main.py --mode embed         # 벡터 임베딩

# 증분 크롤링 (변경된 페이지만)
python main.py --mode incremental

# 처리 청크/벡터/키워드 정합성 점검 및 복구
python scripts/reconcile_vector_store.py
python scripts/reconcile_vector_store.py --apply

# 기존 크롤링 원문의 정제·임베딩만 실행 (Ollama 태깅 생략)
python quick_pipeline.py

# 저장된 원문·청크·벡터 개수 확인
python main.py --mode stats
```

새 DB에는 크롤링·정제·임베딩 또는 아래 담당자 자료 적재를 먼저 실행합니다.
이미 데이터가 있는 DB를 다시 사용할 때는 전체 파이프라인을 반복할 필요가 없으며,
변경 자료는 증분 크롤링과 공식 자료 갱신 명령으로 반영합니다.

### 담당자 제공 자료 반영

`data/official_sources/`에 아래 세 파일을 두고 실행합니다. 이 원본 폴더는 Git에서
제외되므로 새 PC에서는 담당자에게 받은 파일을 별도로 복사해야 합니다.

- `2026년 정보공개청구 민원 데이터 분석 결과보고.pdf`
- `사하구 홈페이지 방문자 및 검색 통계 분석 결과 보고.pdf`
- `사하구 홈페이지_100개 질문.xlsx`

```bash
python scripts/ingest_official_materials.py
```

이 명령은 PDF 본문을 **페이지와 자료 기준 기간**별로 적재합니다. 표지 요약은
본문의 분석 기간과 충돌할 수 있어 제외합니다. 엑셀의 예상답변은 사실 자료로
적재하지 않습니다. 엑셀에 적힌 공식 URL 100곳의 **현재 본문**을 다시 받아
질문의 범위를 보강합니다. 확인되지 않은 URL은 적재하지 않고, 기존 검색
자료도 최신 근거로 사용하지 않습니다. 실행 결과의 `verified_pages`,
`failed_pages`, `errors`를 확인하세요.
질문 목록과 일치하는 질문은 해당 공식 페이지를 우선 검색하되, 엑셀의
예상답변 문장은 답변 근거로 사용하지 않습니다.
일반 질문에는 `raw_pages`에 저장된 **전체 사하구청 크롤링 원문**도 검색합니다.
벡터 청크나 질문 목록에 없는 본문 항목도 활용할 수 있으며, 원문 검색 캐시는 5분마다
갱신됩니다. 새 크롤링 자료도 이 경로로 반영됩니다. 답변 직전에는 DB의 원문과 확인일을
다시 조회하여 관련성·최신성을 검사합니다.
`무료/무상`, `온라인/인터넷` 같은 표현 차이를 보정하고, `전입신고`, `주민등록등본`
같은 서비스명을 유지합니다. 신청 방법·대상·비용·주기·제공 서비스는 답변 항목으로
구분하며, 다른 사업의 구비서류에 등장한 증명서를 그 증명서의 발급 안내로 사용하지 않습니다.
같은 URL의 청크가 검색 후보를 차지하지 않도록 여러 공식 페이지를 비교하고, 요청한
항목을 짧게 설명할 수 있는 원문을 선택합니다. 명확한 질문에 같은 항목을 다시 묻지 않습니다.
`어디에서 확인`, `현황도·지도 링크`처럼 확인 경로를 묻는 질문은 공식 페이지와 첨부 링크를
직접 안내합니다. 홍보 문구를 답변으로 고르지 않으며, 지도만 제공되는 페이지는 현황도
첨부자료를 연결합니다. 본문에 없는 도로 길이나 현재 상태를 추측하지 않습니다.
첨부파일은 공식 URL 재수집 → 원본 → 청크 → 벡터 메타데이터까지 유지합니다.
본문이 같아도 첨부 링크가 바뀌면 갱신하며, 연도가 들어 있는 파일명은 문서 작성일과
구분해 표시합니다. 웹 페이지의 최근 확인일이 첨부 지도 자체의 최신성을 보장하지 않습니다.
담당 부서·담당자 질문은 직원업무안내의 실제 업무와 직위를 우선 검색합니다.
`AI`와 `인공지능`은 같은 용어로 처리하며, 전산·정보화 업무만 있는 직원을
AI 담당으로 추정하지 않습니다. 실제 업무가 일치하지 않으면 답변을 보류하고,
공지사항 목록의 `담당부서` 열이나 검색·페이지 이동 메뉴는 답변 근거에서 제외합니다.

웹 출처는 기본적으로 마지막 확인 후 30일이 지나면 답변에서 제외됩니다.
수수료·금액·운영시간·지원대상·연락처 등 변동 가능한 질문은 7일 기준을
사용합니다. 필요하면 `.env`의 `SOURCE_MAX_AGE_DAYS`,
`SOURCE_DYNAMIC_MAX_AGE_DAYS`로 조절할 수 있습니다. Worker는 매일 04:15에
엑셀의 URL을 다시 확인하고 04:45에 직원업무안내를 갱신합니다. PDF 통계는
과거 자료로 표시하며 현재 행정서비스의 근거로 쓰지 않습니다.
기본값 `SOURCE_ONLY_ANSWERS=false`에서는 Gemma가 질문과 공식 본문의 주변 조건을 읽고,
질문에 맞는 근거 항목을 JSON 번호로 선택합니다. 코드가 항목 번호·핵심 업무·문장 완결성·
대상·예외를 검사한 후 **원문의 확인된 항목**을 짧게 표시합니다. 모델이 새 장소·금액·
전화번호를 만들어 출력하는 자유 생성 방식은 사용하지 않습니다. 모델 장애나 잘못된 선택은
원문 발췌 경로로 이어집니다. 긴 원문은 **공식 원문 자세히 보기**에 접어서 제공합니다.
`SOURCE_ONLY_ANSWERS=true`로 설정하면 일반 상담도 모델 없이 원문 발췌만 사용합니다.

지역명이나 `신고·신청·방법` 같은 공통 표현, BM25·벡터 점수만으로는 근거를
인정하지 않습니다. 개별 문서의 핵심 업무가 질문과 일치해야 하며, 원문과 최종
발췌 구간도 다시 확인합니다. 여권 신규 발급 서류와 불법주정차 주민신고는
해당 안내 구간을 선택해 다른 업무·FAQ가 섞이지 않도록 합니다.
발췌가 길어 일부를 생략하면 `[…]`로 표시하고 실제 사용한 출처만 표시합니다.
출산지원금·보건증·무인민원발급기 수수료처럼 금액이 혼동되기 쉬운 항목은 공식 표의
해당 행을 직접 읽고, 표가 바뀌면 답변을 보류합니다.
예정·미정인 장소와 일정은 확정 정보로 안내하지 않습니다. 교육처럼 대상이 한정된
사업은 대상 조건을 함께 확인하고, 범위가 불명확하면 한 가지 질문을 먼저 합니다.
서로 다른 교육의 장소를 합치지 않으며, `네`/`아니요` 답변을 확인한 대상 문맥에 연결합니다.
크롤링 확인일은 문서 작성일이나 행사 일정이 아닙니다. 공식 자료 자체의 오류나
갱신 전 변경 사항까지 알 수는 없으므로 출처의 기준 기간과 전체 조건을 확인하세요.

일반 상담은 로컬 CPU에서 모델 추론 시간이 추가됩니다. 화재 신고·연락처·검증된 표 조회는
기존의 빠른 경로를 유지합니다. 모델을 사용한다고 전체 질문의 정답률이 보장되지는 않습니다.

### 짧은 답변과 재질문

- 넓은 질문은 자료 전체를 출력하지 않고 한 가지 조건을 먼저 묻습니다.
- `여권 준비물`은 성인/미성년 여부와 신규/재발급, `복지 지원`은 대상·지원 종류,
  `대형폐기물 수수료`는 품목·규격을 확인합니다.
- `성인이야`, `처음이야` 같은 짧은 답과 선택 버튼을 이전 문의에 연결합니다.
  새 주제와 새 대화는 이전 재질문과 섞이지 않도록 처리합니다.
- 재질문에는 아직 답변 근거를 확정하지 않았으므로 출처를 붙이지 않습니다.
- 핵심 답변은 짧게 표시하고, 조건·유료 예외·기존 여권 지참 등 중요한 제한은 남깁니다.
- 줄바꿈된 원문 문장은 끝까지 연결하고, 미완성 조건·괄호·생략 경계의 문장은
  핵심 답변으로 사용하지 않습니다. 조건을 포함해 짧게 답할 수 없으면 재질문합니다.
- 요일별 분리수거 질문은 공식 생활폐기물 배출표의 월~일 항목을 검증해 바로 안내합니다.
  표 구조가 바뀌거나 확인일이 지나면 추측하지 않습니다.
- 모델 출력이 토큰 제한으로 종료되거나 문장이 미완성인 경우, 추가 장문 생성 대신
  질문 범위를 좁힙니다. 미완성 부분에 임의로 문장 끝을 붙이지 않습니다.
- 시간 질문은 시설명만 일치하는 주소·소개 문장을 답으로 쓰지 않고, 실제 운영·진료시간을
  확인합니다. `여는 시간`, `몇 시에 열어`, `몇 시까지`도 운영시간 의도로 처리합니다.
  항목명 다음 줄의 `09:00`처럼 콜론이 있는 값도 항목에 연결하고 관련 제한을 유지합니다.
- 일반 보건소 운영시간은 공식 보건소 안내를 사용하며 마을건강센터·예방접종·검사 등
  개별 시설·업무의 시간과 구분합니다. 시간 질문의 웹 근거에는 7일 확인 기준을 적용합니다.
- 장소 질문에는 실제 장소·주소 항목이 있는 근거를 사용합니다. 접종 이력·대상 조건에서
  병원이 언급된 문장을 접종 장소로 선택하지 않습니다.
- `백신 접종 하는곳`처럼 종류가 없는 질문에는 백신 종류를 한 번 묻고, `독감` 등의
  짧은 답을 장소 문의에 연결합니다. 확인된 백신별 공식 항목에서 장소를 먼저 안내하며,
  사업 대상·보건소 접종 미운영·지역 제한·연도별 지정기관 확인 안내를 함께 유지합니다.
  다른 백신·연령·제품의 안내로 대체하지 않으며 장소 질문에도 7일 확인 기준을 적용합니다.
- 재질문 문맥은 서버 메모리에 최대 30분 동안 유지되며 대화 초기화 시 삭제됩니다.

### 담당 부서·전화번호 전용 파일

화재 신고·대피 질문은 연락처 조회보다 먼저 [사하구청 공식 화재 행동요령](https://www.saha.go.kr/portal/contents.do?mId=0410020200)을
바탕으로 대피·119 신고 방법을 즉시 안내합니다. `화제 신고`는 문맥에 맞춰
`화재 신고`로 해석합니다. 이 경로는 모델·DB를 호출하지 않으며 입력 내용을
되풀이하거나 대화 이력에 저장하지 않습니다. 예방 교육·피해 지원금·통계는
일반 행정 질문으로 처리하고, 공식 근거가 없으면 답변을 보류합니다.

`data/department_contacts.json`에는 공식 부서별 **대표번호 41개**와 직원별
**업무·직위·직통번호 1,117건**을 정리했습니다. 팩스번호와 직원 이름은 넣지 않습니다.
전화번호·담당 부서 질문은 웹 API에서 이 로컬 파일을 먼저 조회하므로
Ollama, 임베딩, Supabase 검색을 호출하지 않습니다.

- `건축과 전화번호` → 공식 부서 대표번호
- `대형폐기물 담당 부서와 연락처` → 해당 업무 담당자의 직통번호와 실제 업무
- 지역별 담당자가 있으면 업무·지역을 함께 표시합니다. 부서가 겹치면 확인 질문을 합니다.
- 실제 업무가 일치하지 않거나 확인일이 7일을 지난 자료는 답변 근거로 쓰지 않습니다.
- 대화 후 `그 업무 전화번호는?`을 물으면 이전 문의 업무를 이어서 조회합니다.

Worker가 매일 04:45에 직원업무안내와 대표전화 표를 받아 전용 파일을 갱신합니다.
크롤링 중 일부 페이지가 실패하면 기존 파일을 유지합니다. 파일은 원자적으로 교체되고
웹 서버는 변경된 파일을 자동으로 읽습니다. 수동으로 새로 만들려면:

```bash
python scripts/build_contact_directory.py --refresh
```

현재 직원업무안내 캐시로 다시 만들려면 `--refresh`를 생략합니다.
담당 부서 질문에서는 추측해서 부서를 연결하지 않으므로, 업무가 상세할수록 정확히 찾습니다.

### 4. 웹 서버

환경 설정·DB 초기화·데이터 적재를 마친 뒤 **서로 다른 터미널**에서 실행합니다.
Ollama 서비스도 실행 상태로 유지합니다.

```bash
# 터미널 1: 주민 상담 전용 웹 서버
python main.py --mode web

# 터미널 2: 증분 크롤링 및 데이터 처리 전용 Worker
python main.py --mode worker
```

**이미 설정한 이 PC에서 재실행할 때**는 PowerShell에서 `C:\sahahaha`로 이동한 뒤
아래 실행 파일 경로를 사용할 수 있습니다. `.venv`와 `.local`은 Git에서 제외되므로
새 PC에는 Python·Ollama 설치가 먼저 필요합니다.

| 터미널 | 명령 |
|---|---|
| Ollama (이미 실행 중이면 생략) | `.\.local\ollama\ollama.exe serve` |
| 웹 서버 | `.\.venv\python.exe main.py --mode web` |
| Worker | `.\.venv\python.exe main.py --mode worker` |

- 상담 화면: [http://127.0.0.1:5000/](http://127.0.0.1:5000/)
- 운영 상태 화면: [http://127.0.0.1:5000/system](http://127.0.0.1:5000/system)
- 모델 상태 확인: [http://127.0.0.1:5000/api/health](http://127.0.0.1:5000/api/health)
- 주소·포트를 바꿨다면 접속 URL도 해당 값으로 변경합니다.
- 웹 서버와 Worker를 분리했으므로 크롤링 중에도 주민 상담 요청이 영향을 덜 받습니다.
- `.env`를 수정하면 웹 서버와 Worker를 재시작합니다. 연락처 전용 JSON 갱신은
  웹 서버가 파일 변경을 읽으므로 서버 재시작이 필요하지 않습니다.

Worker는 `Asia/Seoul` 시간대에서 실행하며 해당 시각에 프로세스가 켜져 있어야 합니다.

| 기본 시각 | 작업 |
|---|---|
| 03:00 | 증분 크롤링·정제·태깅·임베딩 (`CRAWL_HOUR`, `CRAWL_MINUTE`로 변경) |
| 04:00 | 대화 로그 보관 기간에 따른 정리 (`CLEANUP_HOUR`, `CLEANUP_MINUTE`로 변경) |
| 04:15 | 질문 엑셀 또는 JSON 목록 및 우선 서비스의 공식 URL 갱신 |
| 04:45 | 직원업무안내·대표전화와 연락처 전용 파일 갱신 |

`WORKER_RUN_ON_START=true`이면 시작 직후 증분 크롤링도 실행합니다. 기본값은
`false`이므로 Worker를 켜는 것만으로 즉시 모든 자료가 갱신되지는 않습니다.
새로 설치한 PC에서는 필요에 따라 아래 명령으로 자료를 먼저 갱신할 수 있습니다.

```bash
python main.py --mode incremental
python scripts/ingest_official_materials.py --pages-only
python scripts/build_contact_directory.py --refresh
```

대화 문맥은 기본적으로 서버 메모리에만 유지되어 Supabase에 영구 저장되지 않습니다.
운영상 저장이 반드시 필요한 경우에만 `PERSIST_CONVERSATIONS=true`를 설정하고,
위 보안 마이그레이션을 먼저 적용해야 합니다.

### 5. 실행 확인

1. `/api/health`에서 `ollama.available`과 `ollama.model_ready`가 `true`인지 확인합니다.
2. 상담 화면에서 `보건소 여는시간 알려줘`, `보건소 위치 알려줘`를 각각 물어
   시간과 주소가 구분되어 나오는지 확인합니다.
3. `백신 접종 하는곳 알려줘` → `독감`으로 답해 장소 문의가 이어지는지 확인합니다.
4. `건축과 전화번호 알려줘`로 연락처 파일 조회를 확인합니다. 오래된 파일은 갱신합니다.

코드의 단위·회귀 테스트는 저장소 루트에서 실행합니다. 실제 서비스의 모든 질문에 대한
정답률과는 다른 검사이며, 최신 실제 상담 검증 조건은 [개발 맥락](project_context.md)에 기록합니다.

```bash
python -m unittest discover -s tests -q
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
