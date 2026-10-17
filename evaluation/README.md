# 챗봇 평가 (Evaluation)

## 2026-10-16 평가 기준 정정

아래의 기존 `grid_search.py`·`accuracy_eval.py`는 키워드가 하나라도 있는지 보는
개발 보조 검사다. 다른 사업이나 잘못된 조건이 같은 핵심어를 포함해도 통과할 수
있으므로 그 점수를 실제 답변 정답률·환각률·출처 적합률로 발표하지 않는다.
고정 정답 문서/청크에 따른 검색 평가와 최종 답변의 근거 검수도 구분한다.

정확도 우선 업그레이드에서는 `scripts/audit_chat_accuracy.py`로 실제 HTTP 응답을
기록하고 업무·요청 항목·대상·예외·숫자·출처·확인일을 문항별로 수기 검수한다.
결과와 재현 조건은 `document/accuracy_final_review_20261016.md`,
`evaluation/results/accuracy_review_20261016.json`을 따른다.
`accuracy_final_validation_ae_20261017.json`의 AE22는 U 이후 응답 관찰 전에 고정한 최종 검증 질문이다.
10/17 최종 실행은 동일 서비스 코드 `b1a7812`의140턴(138개 질문 문자열)이며,
질문별 실제 답변·판정 이유는 [최종 검수 기록](results/accuracy_cases_20261017.md)에 있다.
수기 판정은 `results/accuracy_labels_20261016.json`의 응답 해시와 연결하며,
`package_accuracy_review_20261016.py`는 원래 로컬 HTTP 기록과 연결된 판정을 검증해
집계만 한다. 새 실행은 응답이 달라지면 다시 검수해야 한다. 필요한 확인/부분 답변/
근거 부족을 충분 답변 정답률에 합산하지 않는다.
`accuracy_final_validation_ad_20261016.json`의 AD22는 U 공통 해석 보강에 사용되어 개발셋으로 재분류했다.
`accuracy_final_validation_ac_20261016.json`의 AC22는 T 필드/첨부 보강에 사용되어 개발셋으로 재분류했다.
`accuracy_final_validation_ab_20261016.json`의 AB22는 S 요청 항목 수정에 사용되어 개발셋으로 재분류했다.
`accuracy_final_validation_aa_20261016.json`의 AA22는 R 거절 경로 수정에 사용되어 개발셋으로 재분류했다.
`accuracy_final_validation_z_20261016.json`의 Z22는 Q의 항목 누락 수정에 사용되어 개발셋으로 재분류했다.
`accuracy_final_validation_y_20261016.json`의 Y22도 P 수정에 사용되어 개발셋으로 재분류했다.
`accuracy_final_validation_x_20261016.json`의 X22도 O 수정에 사용되어 개발셋으로 재분류했다.
`accuracy_final_validation_w_20261016.json`의 W22도 N 수정에 사용되어 개발셋으로 재분류했다.
`accuracy_validation_20261016.json`의 U22는 M 수정에 사용되어 개발셋으로 재분류했다.
`accuracy_untouched_20261016.json`의 V22, 이전 `heldout`10개와
`accuracy_final_independent_cases.json`36개는 이미 수정에 사용되어 개발셋이다.

두 종류의 정량 평가를 제공한다.

| 평가 | 무엇을 보는가 | 스크립트 / 테스트셋 |
|------|--------------|--------------------|
| **검색 평가** | 관련 문서를 잘 찾는가 (Recall@k·MRR) | `grid_search.py` / `testset.json` |
| **답변 정답률** | 최종 답변이 실제로 맞는가 (end-to-end accuracy) | `accuracy_eval.py` / `answer_testset.json` |

---

# 1. 하이브리드 검색 평가 (Hybrid Retrieval Evaluation)

벡터:BM25 가중치(`HYBRID_VECTOR_WEIGHT` : `HYBRID_BM25_WEIGHT`)의
적정값을 정량 데이터로 확인하기 위한 그리드 서치 평가셋과 스크립트.

## 구성

| 파일 | 내용 |
|------|------|
| `testset.json` | 사하구청 도메인 50개 질의 + 정답 키워드 라벨 (수기 작성) |
| `grid_search.py` | 가중치 0.3~1.0 (0.1 단위) 그리드 서치 + Recall@k / MRR 계산 |
| `results.md` | 스크립트 실행 시 자동 생성되는 결과 표 |

## 판정 규칙

검색 결과 상위 k개 문서의 `(title + content)` 안에 해당 쿼리의
`expected_keywords` 중 하나 이상이 포함되면 정답으로 본다.

- chunk_id 단위 라벨링은 Supabase에 적재된 청크가 갱신될 때마다
  라벨도 함께 갱신해야 해서 유지 비용이 크다.
- 키워드 판정의 상대 순위도 정답 문서 라벨과 대조해야 한다. 항목·조건을 구분하지
  못하는 점수만으로 검색 가중치의 우열을 확정하지 않는다.

## 실행

`.env` 가 정상 설정된 상태에서 (Supabase + Ollama 모델 + Kiwi 모델 준비됨):

```bash
python -m evaluation.grid_search
```

처리 흐름:

1. `testset.json` 로딩
2. 쿼리당 벡터 후보 20건 + BM25 후보 30건을 **한 번만** 수집해 캐시
3. 캐시 위에서 가중치 조합 8개에 대해 재랭킹/평가 → 50쿼리 × 8조합

후보 풀을 재사용하기 때문에 가중치 조합이 늘어나도 추가 비용은 거의
산술 연산뿐이다 (벡터 RPC·BM25 토큰화는 쿼리당 1회).

## 결과 활용

- `results.md` 의 표를 발표 자료의 "가중치 선택 근거" 슬라이드에 부착.
- `MRR` 또는 `Recall@5`가 최대인 가중치를 새 기본값으로 `.env`의
  `HYBRID_VECTOR_WEIGHT` / `HYBRID_BM25_WEIGHT`에 반영.

## 한계

- 50건은 통계적으로 견고하지 않다. 실제 운영 후 사용자 질의로
  150건 이상 확장하면 더 안정적인 비교가 가능하다.
- 정답 청크 직접 라벨과의 오차 크기는 실제 대조 전에는 알 수 없다. 과거 문서의
  `1~2%` 추정은 검증 수치가 아니므로 평가 결과로 사용하지 않는다.

---

# 2. 답변 정답률 평가 (Answer Accuracy Evaluation)

검색 평가가 "문서를 잘 찾는가"를 본다면, 이 평가는 **최종 답변이 실제로 맞는가**를 본다.
교수님 피드백("정답률 90%를 어떻게 측정·검증할 것인가, 테스트셋이 있는가")에 대응하는 체계.

## 구성

| 파일 | 내용 |
|------|------|
| `answer_testset.json` | 유형별 라벨이 달린 질의 세트 (answerable / out_of_domain / sensitive) |
| `accuracy_eval.py` | 각 질의를 실제 챗봇에 통과시켜 정답률 측정 |
| `accuracy_results.md` | 실행 시 자동 생성되는 결과(유형별·전체 정답률 + 문항별 상세) |

## 평가 유형과 정답 기준 (결정적 판정)

| 유형 | 의미 | 정답 조건 |
|------|------|-----------|
| `answerable` | 도메인 내 질문 | 답변에 `expected_keywords` 중 **하나 이상 포함** |
| `out_of_domain` | 도메인 밖 질문 | 지어내지 않고 **거절/안전 안내**(환각 방어) |
| `sensitive` | 개인정보 입력 | **차단 안내** 출력(PII 필터) |

> **왜 결정적 판정인가**: 키워드 포함·거절 패턴·PII 경고로 판정하므로 **재현 가능하고
> 설명 가능**하다. LLM 자가채점(self-confidence)은 보정(calibration)이 안 돼 정답률의
> 근거로 삼기 어렵기 때문에 사용하지 않는다.

## 실행

```bash
python -m evaluation.accuracy_eval              # 전체
python -m evaluation.accuracy_eval --limit 5    # 앞 5개만 빠르게 점검
python -m evaluation.accuracy_eval --delay 1.0  # 질문 사이 추가 지연
```

- 각 질의는 **새 세션**으로 평가하고(이전 대화 오염 방지), 끝나면 대화 로그를 정리한다.
- 실제 로컬 Ollama 모델을 호출하므로 **Ollama 서버와 설정 모델이 실행 중**이어야 한다. 연결 실패는
  정답/오답이 아닌 `error`로 분류해 **정답률 분모에서 제외**한다.

## 결과 활용

- `accuracy_results.md`의 자동 점수는 키워드 회귀 참고로만 사용한다. 발표 성능 표에는
  실제 근거를 검수한 결과와 표본·분류·시점·조건을 함께 제시한다.
- 코드 수정 후 재실행해 **회귀(정답률 하락) 점검**에 사용.

## 한계

- 표본이 작으므로(수십 문항) 점수는 **상대 비교·회귀 점검용**이다. 실사용 로그로
  테스트셋을 확장할수록(예: 150건+) 신뢰도가 올라간다.
- 키워드 판정은 올바른 표현을 놓칠 수도 있고, 잘못된 업무·숫자·조건을 통과시킬 수도
  있다. 과소평가 방향이라는 보장은 없으며 그 자체로 사실성을 입증하지 못한다.
- `expected_keywords`는 도메인 지식 기반 수기 라벨이므로, 실제 크롤링 데이터와 맞는지
  주기적으로 검토·보정이 필요하다.
