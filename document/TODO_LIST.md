# TODO LIST - 사하구청 AI 상담사 개선 사항

> 코드 분석 기반 개선 목록 (2026-04-16 작성, 2026-05-14 일괄 패치)

---

## 1. 보안 취약점 (Security)

### [심각도: 높음]

- [x] **벡터 검색 전체 테이블 풀스캔 제거**
  - 파일: `database_db/vector_store.py`
  - 변경: `match_documents()` Supabase RPC로 전환하여 서버사이드 pgvector 검색 수행. 클라이언트는 query embedding만 전송.

- [x] **`/api/stats` 인증 없이 노출**
  - 파일: `app.py`
  - 변경: `@require_admin` 데코레이터로 `X-Admin-Key` 헤더 인증 강제. `ADMIN_API_KEY` 미설정 시 503 반환.

- [x] **`/api/stats` 에러 메시지 원본 노출**
  - 파일: `app.py`
  - 변경: 클라이언트에는 "시스템 오류가 발생했습니다"만 반환, 상세는 서버 로그에만 기록.

- [x] **Supabase RLS(Row Level Security) 점검**
  - 파일: `setup_supabase.sql`
  - 변경: 모든 테이블 RLS 활성화. anon은 documents/processed_chunks SELECT + conversation_logs INSERT/SELECT/DELETE만 허용. 관리 작업은 service_role 키로 분리.

### [심각도: 중간]

- [x] **Secret Key 하드코딩 기본값**
  - 파일: `config.py`
  - 변경: `SECRET_KEY` 환경변수 미설정 시 `ValueError`로 서버 시작 차단.

- [x] **CORS/CSP 헤더 미설정**
  - 파일: `app.py`
  - 변경: `flask-cors`로 허용 출처 제한, `X-Frame-Options`/`CSP frame-ancestors`로 클릭재킹 방지.

- [x] **Rate Limiting 없음**
  - 파일: `app.py`
  - 변경: `flask-limiter` 적용. `/api/chat`은 분당 10회(`RATE_LIMIT_CHAT` env로 조정 가능).

---

## 2. 성능 문제 (Performance)

- [x] **`/api/stats`에서 Database/VectorStore 매번 새 인스턴스 생성**
  - 파일: `app.py`
  - 변경: `get_db()`/`get_vector_store()` 싱글턴으로 재사용. VectorStore는 챗봇이 로딩한 인스턴스를 공유.

- [x] **Supabase 클라이언트 연결 중복 생성**
  - 파일: `database_db/__init__.py` (신규)
  - 변경: `get_supabase(admin=...)` 공유 팩토리. Database/VectorStore가 동일 클라이언트 재사용. admin 키 사용 시 RLS 우회 가능.

- [x] **BFS 큐가 list.pop(0) 사용**
  - 파일: `crawler/saha_crawler.py`
  - 변경: `collections.deque`로 교체 → `popleft()` O(1).

- [x] **메타데이터 태깅 속도 개선**
  - 파일: `processor/metadata_tagger.py`
  - 변경: 5청크 단위 1회 LLM 호출로 배치 처리. JSON 파싱 실패 시 단건 폴백.

---

## 3. 기능/로직 개선 (Feature)

- [x] **대화 이력 만료 정책 없음**
  - 파일: `database_db/database.py`, `main.py`
  - 변경: `cleanup_old_conversations(ttl_days)` 메서드 + APScheduler 매일 04:00 정리 작업 등록. TTL은 `CONVERSATION_TTL_DAYS` env(기본 30일).

- [x] **LLM 응답에 대한 개인정보 필터링 누락**
  - 파일: `chatbot/conversation.py`
  - 변경: `mask_personal_info()` 헬퍼로 응답 출력단에서도 PII를 `[MASKED:<유형>]`으로 치환. 카드번호 패턴 추가.

- [x] **역질문 감지 방식 개선**
  - 파일: `chatbot/conversation.py`
  - 변경: 시스템 프롬프트에 `[CLARIFICATION]` 토큰 추가 → LLM 응답의 태그로 판단. 누락 시 키워드 휴리스틱 폴백.

- [x] **중복 감지가 인스턴스 레벨**
  - 파일: `processor/data_cleaner.py`
  - 변경: 생성자에서 DB의 기존 `chunk_id` 전수 조회 후 일치 청크는 임베딩 단계까지 진입하지 않도록 차단.

- [x] **크롤러 robots.txt 미확인**
  - 파일: `crawler/saha_crawler.py`
  - 변경: `urllib.robotparser`로 시작 시 robots.txt 로딩. 각 URL 페치 전 `can_fetch()` 검사.

---

## 4. 코드 품질 (Code Quality)

- [ ] **에러 삼킴(silent failure) 개선**
  - 파일: `processor/metadata_tagger.py`, `chatbot/retriever.py` 등
  - 부분 개선: 배치 태깅 실패 → 단건 폴백, RPC 실패 시 로그 + 빈 결과. 추가로 사용자 안내 문구는 차주 작업.

- [ ] **글로벌 챗봇 인스턴스 thread-safety**
  - 파일: `app.py`
  - 보류: 현재 단일 프로세스라 보류. gunicorn/FastAPI 전환 시 `threading.Lock` 적용 예정.

- [x] **LangChain 호환성 경고 해결**
  - 파일: `database_db/vector_store.py`
  - 변경: `langchain-huggingface` 우선 import + `langchain-community` 폴백.

---

## 우선순위 요약 (2026-05-14 완료 상태)

| 순위 | 항목 | 분류 | 상태 |
|:----:|------|:----:|:----:|
| 1 | 벡터 검색 → `match_documents()` RPC 전환 | 보안+성능 | 완료 |
| 2 | `/api/stats` 인증 + 에러 마스킹 | 보안 | 완료 |
| 3 | Rate Limiting 추가 | 보안 | 완료 |
| 4 | Secret Key 강제 환경변수 | 보안 | 완료 |
| 5 | 대화 이력 TTL 정리 | 기능 | 완료 |
| 6 | CORS/CSP 헤더 설정 | 보안 | 완료 |
| 7 | DB 인스턴스 재사용 | 성능 | 완료 |
| 8 | LLM 응답 개인정보 필터링 | 기능 | 완료 |
| 9 | 역질문 감지 방식 개선 | 기능 | 완료 |
| 10 | 메타데이터 태깅 배치 처리 | 성능 | 완료 |
| 11 | RLS 정책 분리 (anon/service role) | 보안 | 완료 |
| 12 | BFS deque + robots.txt | 코드 품질 | 완료 |
| 13 | 중복 감지 DB 기반 | 성능 | 완료 |
| 14 | langchain-huggingface 마이그레이션 | 코드 품질 | 완료 |

## 잔여 작업 (다음 단계)

- thread-safety 적용 (Flask → FastAPI 전환과 함께)
- silent failure를 사용자 안내 메시지로 노출
- NER 기반 비정형 PII 탐지 추가
- 하이브리드 검색 BM25 + 벡터 가중치 최적화 실험
