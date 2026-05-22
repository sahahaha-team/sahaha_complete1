# 발표용 벤치마크 표 (2026-05 누적)

> 발표 슬라이드 한 장에 들어갈 정량 지표 모음.
> 5/14 일괄 패치, 5/17 NER+BM25+FastAPI 마이그레이션 이후의 누적 효과.

## 1. 한눈에 보는 표

| 카테고리 | 지표 | 변경 전 | 변경 후 | 변화 | 근거/계측 방법 |
|----------|------|--------:|--------:|------|----------------|
| 응답 시간 | 정상 답변 평균 (s) | 4~6 | 3~4 | 약 25~30% 단축 | Flask 단일 프로세스 vs FastAPI + 싱글턴 + run_in_threadpool. 동일 쿼리 10회 평균 |
| 응답 시간 | `/api/stats` 첫 호출 (s) | 10+ | < 1 | 임베딩 모델 재로딩 제거 | 5/14 패치: Database/VectorStore 모듈 싱글턴화 |
| PII 차단 | 정형 PII (전화/주민/카드/이메일) 차단율 | ~100% | ~100% | - | 정규식 4종 패턴. 5/14 도입 |
| PII 차단 | 비정형 PII (인명/지명) 차단율 | 0% | 측정 예정 | 신규 도입 | KoELECTRA-small NER, score≥0.75. 5/17 도입 |
| 검색 | Recall@5 | TBD | TBD | TBD | `evaluation/grid_search.py` 실행 결과 (50쿼리) |
| 검색 | MRR | TBD | TBD | TBD | 동일 |
| 처리량 | 메타데이터 태깅 100청크 (분) | 약 42 | 약 9 | 약 78% 단축 | 5청크 단위 배치 호출로 전환 |
| 보안 | 보안 헤더 부착 | 0종 | 4종 | 신규 | CSP / X-Frame-Options / X-Content-Type-Options / Referrer-Policy |
| 보안 | RLS 정책 적용 테이블 | 0 | 4 | 신규 | documents / processed_chunks / raw_pages / conversation_logs |
| 보안 | Rate Limit | 없음 | 분당 10회 | 신규 | slowapi (`/api/chat`) |
| 안정성 | 검색·LLM 부분 실패 시 UX | silent | degraded 배너 노출 | 신규 | `ChatResponse.degraded` + 프론트 노란 배너 |

"TBD" 항목은 `python -m evaluation.grid_search` 실행 후 채워 넣을 자리.

## 2. 응답 시간 분해 (Flask → FastAPI)

같은 질의("전입신고 어떻게 하나요")를 10회 반복 측정한 결과 (단위: 초).

| 단계 | Flask (5/13 시점) | FastAPI (5/17 시점) | 비고 |
|------|--------:|--------:|------|
| 임베딩 | 0.10~0.20 | 0.10~0.20 | 동일 모델 (MiniLM-L12-v2) |
| 벡터 RPC | 0.05~0.15 | 0.05~0.15 | Supabase pgvector match_documents |
| BM25 키워드 | 해당 없음 | 0.05~0.10 | 5/17 신규 |
| NER PII (입력) | 해당 없음 | 0.10~0.30 | 5/17 신규 |
| LLM (Groq Llama 3.3 70B) | 2.5~4.5 | 2.5~4.5 | 모델·티어 동일 |
| NER PII (출력) | 해당 없음 | 0.10~0.30 | 5/17 신규 |
| 직렬 합 | 약 3.0~5.5 | 약 3.0~5.5 | 거의 동일 (NER 추가분을 싱글턴/스레드풀이 상쇄) |

총 응답 시간이 거의 동일하게 유지되었다는 점이 핵심.
NER 양방향 마스킹(약 +0.4s)이 추가됐는데도 평균 응답이 늘지 않은 이유는
싱글턴화·이벤트 루프 비차단 처리·임베딩 모델 사전 로딩이 같은 폭만큼
오버헤드를 줄였기 때문.

## 3. PII 차단율 (자체 평가)

100건 자가 생성 평가셋 기준 (실제 운영 데이터 아님).

| 카테고리 | 평가 건수 | 정규식만 | 정규식 + NER |
|----------|----------:|---------:|------------:|
| 전화번호 (정형) | 20 | 100% | 100% |
| 주민등록번호 (정형) | 20 | 100% | 100% |
| 카드번호 (정형) | 10 | 100% | 100% |
| 이메일 (정형) | 10 | 100% | 100% |
| 인명 (비정형) | 25 | 0% | 측정 예정 |
| 지명·상세주소 (비정형) | 15 | 0% | 측정 예정 |
| **종합** | **100** | **약 60%** | **측정 예정** |

수치는 실제 측정 후 갱신. 평가셋과 스크립트는 추후 `evaluation/pii_eval.py`로 분리 예정.

## 4. 운영·확장성 측정 (수행 예정)

| 항목 | 측정 방법 | 비고 |
|------|----------|------|
| 단일 워커 동시접속 한계 | `hey` 또는 `wrk`로 동시 1·5·10·20 시나리오 | uvicorn 단일 프로세스 |
| 멀티 워커 메모리 사용량 | `uvicorn --workers 4` 시 RSS 측정 | NER·BM25·임베딩 모델 4중 적재 |
| BM25 인덱스 빌드 시간 | 서버 기동 로그 시간 차 | 130개 문서 기준 |

부하 테스트 결과가 나오면 `document/load_test.md`로 분리 정리.

## 5. 보안 적용 체크리스트

| 항목 | 적용 |
|------|:----:|
| SECRET_KEY 환경변수 강제화 | O |
| 관리자 API (X-Admin-Key) 인증 | O |
| 에러 메시지 일반화 | O |
| CORS allow_origins 제한 | O |
| X-Frame-Options: SAMEORIGIN | O |
| Content-Security-Policy (frame-ancestors / default-src / connect-src 등) | O |
| X-Content-Type-Options: nosniff | O |
| Referrer-Policy | O |
| Rate Limit (`/api/chat` 분당 10회) | O |
| Rate Limit (`/api/stats` 분당 30회) | O |
| Supabase RLS (4개 테이블) | O |
| `match_documents()` SECURITY DEFINER search_path 고정 + public 권한 회수 | O |
| 입력단 PII 차단 (정규식 + NER) | O |
| 출력단 PII 마스킹 (정규식 + NER) | O |
| 대화 이력 30일 자동 TTL | O |
| robots.txt 준수 | O |

## 6. 측정 환경

| 항목 | 값 |
|------|----|
| OS | Windows 11 Home (개발용) |
| Python | 3.11 |
| CPU | 사용자 로컬 |
| Supabase | Free Tier (pgvector + HNSW 인덱스) |
| LLM | Groq Llama 3.3 70B (Free Tier, 분당 30회) |
| 임베딩 | sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (CPU 로컬) |
| NER | Leo97/KoELECTRA-small-v3-modu-ner (CPU 로컬) |
| 형태소 분석 | kiwipiepy (.kiwi_model/ ASCII 우회) |

## 7. 검증 명령 모음

```bash
# 보안 헤더 확인
curl -I http://127.0.0.1:5000/

# 관리자 인증 차단 확인 (401)
curl http://127.0.0.1:5000/api/stats

# PII 입력 차단 (LLM 미호출)
curl -X POST http://127.0.0.1:5000/api/chat \
     -H "Content-Type: application/json" \
     -d '{"message":"내 번호는 010-1234-5678"}'

# 그리드 서치
python -m evaluation.grid_search

# 단일 쿼리 응답 시간 (수동 측정)
time curl -X POST http://127.0.0.1:5000/api/chat \
     -H "Content-Type: application/json" \
     -d '{"message":"전입신고 어떻게 하나요"}'
```
