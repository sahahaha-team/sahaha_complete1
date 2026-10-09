# 사하구청 AI 상담사 고우니

사하구청 공식 홈페이지와 연결 사이트의 공개 자료를 수집하고, 질문에 맞는 원문·담당 부서·연락처를 안내하는 졸업작품 프로토타입입니다. FastAPI, Supabase/pgvector, 한국어 BM25 및 Ollama `gemma2:2b`를 사용합니다.

## 이번 브랜치의 변경

- 문화관광·보건소·도서관·을숙도문화회관·통합예약 등 공식 연결 사이트 탐색, 중단 수집 재개 및 실패 재시도
- 첨부문서와 Windows 한국어 OCR 처리, 사업별 제목·표·조건을 보존하는 원문 검색
- 질문 목적에 맞는 항목 선택, 시작 메뉴 4종과 짧은 후속 응답, 요청 실패 안내 개선
- 대량 DB 조회 누락과 저장 시간 초과 대응, 수집 현황 표시 및 예약 Worker 보완

다운로드한 버전 `07b6329` 이후의 작업은 [업데이트 내역](document/updates_after_download_20261009.md)에 정리했습니다. 전체 공개자료 수집은 진행 중이며 모든 홈페이지 정보의 수집이나 모든 질문의 정답을 보장하지 않습니다.

## 조원 실행 방법: 기존 팀 DB 공동 사용

코드만 내려받아서는 수집된 DB와 모델이 복사되지 않습니다. 팀원의 기존 Supabase 프로젝트에 연결하면 이미 적재된 공식 자료를 함께 조회하므로 처음부터 다시 수집할 필요가 없습니다.

Windows PowerShell에서 프로젝트 폴더를 열고 실행합니다. Python 3.12 환경과 Ollama 설치가 필요합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
ollama pull gemma2:2b
```

`.env`에서 다음 값을 설정합니다.

| 항목 | 설정 방법 |
|---|---|
| `SUPABASE_URL` | 팀에서 사용하는 동일 프로젝트 URL |
| `SUPABASE_KEY` | 해당 프로젝트의 anon 키 |
| `SUPABASE_SERVICE_KEY` | 해당 프로젝트의 service_role 키, 신뢰하는 팀원에게 비공개 전달 |
| `OLLAMA_BASE_URL` | 로컬 기본값 `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | `gemma2:2b` |
| `SOURCE_ONLY_ANSWERS` | 검증된 원문 안내 모드 `true` |
| `SECRET_KEY` | 각 컴퓨터에서 별도로 생성한 임의의 긴 값 |
| `ADMIN_API_KEY` | 각 컴퓨터에서 별도로 생성한 관리자 인증 값 |

무작위 값은 아래 명령을 실행할 때마다 새로 생성됩니다. `SECRET_KEY`와 `ADMIN_API_KEY`에 서로 다른 값을 사용합니다.

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

현재 원문 검색은 `raw_pages`를 읽으므로 서버용 키도 필요합니다. service_role 키는 DB 수정·삭제 권한을 가지며 `.env`, 채팅 기록 및 비밀번호를 저장소에 올리지 않습니다. 키를 HTML·JavaScript에 넣지 않습니다.

Ollama 앱을 실행한 상태에서 웹 서버를 시작합니다.

```powershell
.\.venv\Scripts\python.exe -X utf8 main.py --mode web
```

- 상담 화면: <http://127.0.0.1:5000/>
- 운영 상태: <http://127.0.0.1:5000/system>
- 최초 실행은 임베딩 모델 다운로드와 검색 인덱스 구축 때문에 시간이 걸릴 수 있습니다.
- 기존 팀 DB를 사용한다면 DB 초기화 SQL이나 최초 전체 수집을 다시 실행하지 않습니다.
- 동일 코드·DB·모델·답변 설정은 같은 자료 기준을 제공합니다. 자유 생성 모드를 켜면 답변 문장까지 동일하다고 보장하지 않습니다.

연락처 안내는 각 컴퓨터의 `data/department_contacts.json`을 사용합니다. DB 공동 사용만으로 다른 컴퓨터의 이 파일이 갱신되지는 않습니다. 공식 연락처의 기본 유효 기간은 7일이며, 필요한 경우 해당 컴퓨터에서 갱신합니다.

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/build_contact_directory.py --refresh
```

## 데이터 갱신 담당 컴퓨터

같은 DB의 전체 크롤링 Worker는 팀에서 지정한 컴퓨터 한 곳에서 실행합니다.

```powershell
python -X utf8 main.py --mode worker
```

한국 시간 03:00 전체 탐색·갱신, 04:15 중단 수집 재개, 04:45 로컬 연락처 갱신을 예약합니다. 컴퓨터와 Worker가 켜져 있어야 하며 절전 중에는 실행되지 않습니다. 홈페이지 변경 즉시 반영되는 구조가 아니고 수집·정제·검색 적재가 성공한 뒤 반영됩니다. 수집 목록·첨부 캐시·현황 파일은 Worker 컴퓨터에 저장됩니다.

새 Supabase 프로젝트를 만들면 기존 팀 DB의 데이터가 자동으로 복사되지 않습니다. 별도 DB 최초 구축과 수집·재개 방법은 [상세 실행 안내](document/README.md)를 확인하세요. 현재 DB 백업 배포·복원 스크립트는 포함하지 않습니다.

## 검증 기록

2026-10-09, 실제 Supabase와 `SOURCE_ONLY_ANSWERS=true` 조건에서 구청 제공 100문항을 질문별 독립 세션으로 검사했습니다. 기본 답변의 수동 검토 결과는 핵심 충족 98개, 공식 기준 충돌 1개, 운영중단 공지로 별도 확인한 문항 1개입니다. 같은 질문으로 개선한 결과이며, 새로운 모든 질문에 대한 98% 정답률을 의미하지 않습니다.

실제 HTTP 상담 31턴 및 회귀 테스트 219개를 확인했습니다. 질문별 응답·판정 기준·실행 시점·제한 사항은 [평가 결과](evaluation/results/20261009_council_faq_fixed_review.md)에 보관합니다.

```powershell
python -X utf8 -m unittest discover -s tests -v
```

## 문서

- [상세 실행 안내](document/README.md)
- [다운로드 이후 업데이트 내역](document/updates_after_download_20261009.md)
- [개발 방향과 현재 상태](document/project_context.md)
- [구청 제공 보고서 검토](document/council_reports_review_20261009.md)
- [평가 방법](evaluation/README.md)
