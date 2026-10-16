# Gemma 4 실행 환경 전환

## 사용자에게 확인한 운영 환경

- 내부망 운영 서버: 담당자 안내 기준 vLLM 0.25.1 / Gemma4-26B.
- 학교 서버 주소와 접속 방법은 현재 제공되지 않았다. 운영 서버 접속·26B 답변 품질은 여기서 검증하지 않았다. 모델 이름은 서버 별칭일 수 있으므로 임의로 Google 모델 ID와 동일하다고 단정하지 않는다.
- 개발 PC: RAM 약16GB, AMD Radeon 내장 그래픽. 로컬 CPU 실행용 소형 모델을 검증한다.

## 비용과 공식 배포 확인

- [Google Gemma 4 모델 카드](https://ai.google.dev/gemma/docs/core/model_card_4): Apache 2.0으로 배포된다. 가중치 다운로드·자체 실행에 모델 사용료를 부과하는 API가 필수인 것은 아니다. 하드웨어·전기·외부 호스팅 비용은 별도다. 배포 시 라이선스·고지 조건을 따른다.
- [Ollama 공식 Gemma 4 목록](https://ollama.com/library/gemma4): E2B/E4B 등 로컬 실행용 모델을 제공한다. 로컬 모델을 선택하며 cloud 태그를 사용하지 않는다.
- [vLLM 0.25.1 지원 모델](https://docs.vllm.ai/en/v0.25.1/models/supported_models/): Gemma 4 지원을 확인했다. 26B A4B는 전체와 활성 파라미터 수가 다르며 E4B와 같은 모델이 아니다. 로컬 결과를 운영26B의 성능으로 발표하지 않는다.

## 설정

로컬 개발:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma4:e4b
OLLAMA_NUM_CTX=4096
```

모델 준비는 `ollama pull gemma4:e4b`다. 이 프로젝트에 포함된 실행 파일은 `.local/ollama/ollama.exe`이며 기존 Gemma2 가중치는 보존한다. 메모리 부족 시 E2B를 별도 검증하고 모델명을 명시한다. 설치된 모델 목록은 준비 여부이고 추론 성공 보장은 아니므로 실제 JSON 선택과 상담 API도 실행한다.

내부망 운영 전환:

```dotenv
LLM_PROVIDER=vllm
VLLM_BASE_URL=http://실제-내부망-주소:포트/v1
VLLM_MODEL=실제-served-model-ID
VLLM_API_KEY=
VLLM_TIMEOUT=120
```

`/v1/models`의 ID를 담당자에게 확인해서 설정한다. 키가 필요하면 운영 서버의 비공개 환경변수에 저장하며 Git·로그·화면에 노출하지 않는다. vLLM 모드에서는 Ollama 생성/상태 점검을 호출하지 않으며 장애 때 외부 API로 전환하지 않는다. 빈 주소·잘못된 모델은 준비되지 않은 상태로 표시한다. 설정 변경 후 웹 프로세스를 다시 시작한다.

## 답변 안전성과 속도

- 모델은 공식 원문의 번호만 JSON으로 선택한다. 모델 자체가 작성한 금액·연락처·서술을 행정 사실로 출력하지 않는다. JSON 선택 후에도 업무·필드·조건·시점 검사를 수행한다.
- [vLLM 구조화 응답](https://docs.vllm.ai/en/v0.25.1/features/structured_outputs/)의 JSON Schema로 기존 Ollama 형식 제약을 전달한다. 출력 토큰 제한과 타임아웃을 전달하며 실패·잘림·잘못된 선택은 기존 검증된 원문 경로로 처리한다. 제약 없는 자유 생성으로 재시도하지 않는다.
- Gemma4의 thinking은 이 짧은 근거 선택에서는 끈다. [vLLM 공식 Gemma4 가이드](https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html), [Ollama chat API](https://docs.ollama.com/api/chat)의 옵션에 따라 공급자별로 전달하며 내부 추론을 주민 답변이나 대화 이력에 넣지 않는다.
- 선택 캐시는 모델·공급자·서버 주소·설정·프롬프트·원문에 결합한다. 현재 자료와 조건의 재검사는 유지한다. 더 큰 모델로 바꾸었다는 사실만으로 정확도 향상을 주장하지 않는다.

## 검증 기록

전체 회귀476개가2026-10-16 17:54 KST에 통과했다(11.116초). 단위 검사는 vLLM 요청/오류/모델ID/토큰/JSON/생각 출력 분리 계약과 기존 정확성 검사를 포함한다. 학교 vLLM 실제 추론 검증과 구분한다. 로컬 실제 모델·상담 API 결과는 준비 완료 후 아래에 추가한다.

- 로컬 Ollama 0.40.0에 `gemma4:e4b`를 설치하고 비공개 `.env`의 공급자/모델만 변경했다. Gemma2는 삭제하지 않았다. 설치된 가중치의 digest·양자화·모델 정보는 실제 API 결과의 health_before에 남겼다.
- 최초 모델 적재87.512초, 짧은 단독 요청 총96.033초. 초기 단독 시험에서 모델이 빈 항목을 골랐으며 이는 유효한 행정 답으로 인정할 수 없다. 실제 상담과 동일한 PROMPT/스키마를 사용한 추가2건은 올바른 항목을 선택했다(9.096/8.314초, thinking 없음). 앞선 실패는 삭제하거나 성공으로 계산하지 않는다. 원자료는 `gemma4_runtime_probe.json`, `gemma4_planner_probe.json`이다.
- 실제 상담 API10턴은2026-10-16 18:01~18:03 KST, HTTP200, 코드·자료 설정 해시 불변. `gemma4_api_probe.json`에서 신규 순서·미성년 재발급·예약 후속·온라인 발급 조건·복용량 보류·소송 제외·긴급 가스 안내·첨부자료 연도 주의를 검수했다. 짧은 답과 출처는 H의 Gemma2 실행과 동일하며 전체 정확도 향상으로 계산하지 않는다. 최대20.939초.
- Windows에서 처음5000번 포트 bind가 거절되어 이10턴은5001번으로 실행했다. 이후 직접 포트 점검에서5000번 사용이 다시 가능해졌다. 최종 서비스는 원래 포트로 재적용한다. 서버 초기화·다운로드·별도 모델 단독 시험은 상담 속도 통계와 분리했다.
