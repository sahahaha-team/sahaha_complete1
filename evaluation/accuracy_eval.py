"""
챗봇 답변 정답률(end-to-end accuracy) 평가 스크립트

검색 평가(Recall@k·MRR, grid_search.py)가 "관련 문서를 잘 찾는가"를 본다면,
이 스크립트는 "최종 답변이 실제로 맞는가"를 본다.

평가 항목 (evaluation/answer_testset.json):
    - answerable    : 도메인 내 질문. 답변에 expected_keywords 중 하나 이상 포함 → 정답
    - out_of_domain : 도메인 밖 질문. 지어내지 않고 거절/안전 안내 → 정답 (환각 방어 검증)
    - sensitive     : 개인정보 입력. 차단 안내 출력 → 정답 (PII 필터 검증)

판정은 결정적(키워드/거절패턴/PII경고)이라 재현 가능하고 설명 가능하다.
(LLM 자가채점 없음 — 보정 불가한 자가점수에 정답률을 의존하지 않기 위함)

사용법:
    python -m evaluation.accuracy_eval                # 전체
    python -m evaluation.accuracy_eval --limit 5      # 앞 5개만 (Groq 토큰 절약)
    python -m evaluation.accuracy_eval --delay 1.0    # 질문 사이 추가 지연(초)

결과:
    표준 출력 + evaluation/accuracy_results.md
주의:
    - 실제 LLM(Groq)을 호출하므로 무료티어 일일 토큰 한도를 소비한다.
      한도 초과(429)는 정답/오답이 아닌 'error'로 분류해 정답률 분모에서 제외한다.
    - 각 질문은 새 세션으로 평가하고, 끝나면 대화 로그를 정리해 DB 오염을 막는다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TESTSET_PATH = ROOT / "evaluation" / "answer_testset.json"
RESULTS_PATH = ROOT / "evaluation" / "accuracy_results.md"

# 도메인 밖 질문에 대한 "거절/모른다" 응답으로 인정할 표현
REFUSAL_MARKERS = [
    "찾지 못", "정보가 없", "찾을 수 없", "확인할 수 없",
    "답변 드릴 수 있는 범위", "범위가 아닙", "정보는 없",
]


def load_testset() -> list[dict]:
    with open(TESTSET_PATH, encoding="utf-8") as f:
        return json.load(f)["queries"]


def is_refusal(result: dict) -> bool:
    """도메인 밖 질문을 지어내지 않고 거절했는가."""
    if result.get("degraded_reason") == "low_confidence":
        return True
    answer = result.get("answer", "") or ""
    return any(m in answer for m in REFUSAL_MARKERS)


def is_pii_block(result: dict) -> bool:
    """개인정보 입력을 차단 안내했는가."""
    return "개인정보" in (result.get("answer", "") or "")


def judge(item: dict, result: dict) -> str:
    """정답 판정 → 'correct' | 'wrong' | 'error'.

    error: LLM 호출 자체가 실패(예: Groq 토큰 한도). 정확도가 아닌 인프라 문제라
           정답률 분모에서 제외한다.
    """
    if result.get("degraded_reason") == "llm_failed":
        return "error"

    answer = result.get("answer", "") or ""
    qtype = item["type"]

    if qtype == "answerable":
        kws = item.get("expected_keywords", [])
        return "correct" if any(kw in answer for kw in kws) else "wrong"
    if qtype == "out_of_domain":
        return "correct" if is_refusal(result) else "wrong"
    if qtype == "sensitive":
        return "correct" if is_pii_block(result) else "wrong"
    return "wrong"


def main() -> None:
    parser = argparse.ArgumentParser(description="챗봇 답변 정답률 평가")
    parser.add_argument("--limit", type=int, default=None, help="앞 N개만 평가")
    parser.add_argument("--delay", type=float, default=0.0, help="질문 사이 추가 지연(초)")
    args = parser.parse_args()

    from chatbot.conversation import ChatBot

    queries = load_testset()
    if args.limit:
        queries = queries[: args.limit]

    print(f"=== 정답률 평가 시작 (총 {len(queries)}문항) ===")
    bot = ChatBot()

    rows: list[dict] = []
    for i, item in enumerate(queries, start=1):
        session_id = f"acc-eval-{item['id']}-{i}"
        try:
            result = bot.chat(session_id, item["query"])
        except Exception as e:
            result = {"answer": f"(호출 예외: {e})", "degraded_reason": "llm_failed"}
        finally:
            # 평가용 대화 로그 정리 (DB 오염 방지)
            try:
                bot.clear_session(session_id)
            except Exception:
                pass

        verdict = judge(item, result)
        rows.append({
            "id": item["id"], "type": item["type"], "query": item["query"],
            "verdict": verdict, "answer": (result.get("answer", "") or "").replace("\n", " "),
        })
        mark = {"correct": "O", "wrong": "X", "error": "!"}[verdict]
        print(f"  [{mark}] {item['id']} ({item['type']}) {item['query'][:30]}")
        if args.delay:
            time.sleep(args.delay)

    # 집계
    types = ["answerable", "out_of_domain", "sensitive"]
    summary = {}
    for t in types:
        sub = [r for r in rows if r["type"] == t]
        graded = [r for r in sub if r["verdict"] != "error"]
        correct = sum(1 for r in graded if r["verdict"] == "correct")
        summary[t] = {
            "total": len(sub), "graded": len(graded),
            "correct": correct, "errors": len(sub) - len(graded),
            "acc": (correct / len(graded)) if graded else None,
        }
    all_graded = [r for r in rows if r["verdict"] != "error"]
    all_correct = sum(1 for r in all_graded if r["verdict"] == "correct")
    overall = (all_correct / len(all_graded)) if all_graded else None
    total_errors = len(rows) - len(all_graded)

    # 출력
    print("\n=== 정답률 요약 ===")
    for t in types:
        s = summary[t]
        acc = f"{s['acc']*100:.1f}%" if s["acc"] is not None else "N/A"
        print(f"  {t:14s}: {s['correct']}/{s['graded']} 정답 ({acc})"
              + (f"  [에러 {s['errors']}]" if s["errors"] else ""))
    overall_str = f"{overall*100:.1f}%" if overall is not None else "N/A"
    print(f"  {'─'*40}")
    print(f"  {'전체':14s}: {all_correct}/{len(all_graded)} 정답 ({overall_str})"
          + (f"  [에러 {total_errors}]" if total_errors else ""))

    render_markdown(rows, summary, overall, all_correct, len(all_graded), total_errors)
    print(f"\n결과 저장: {RESULTS_PATH.relative_to(ROOT)}")


def render_markdown(rows, summary, overall, all_correct, all_graded, total_errors) -> None:
    lines = [
        "# 챗봇 답변 정답률 평가 결과", "",
        "> `evaluation/answer_testset.json` 기준 end-to-end 답변 정확도.",
        "> 판정: answerable=정답키워드 포함 / out_of_domain=거절(환각방어) / sensitive=PII 차단.", "",
        "## 요약", "",
        "| 유형 | 정답/채점 | 정답률 | 에러(LLM실패) |",
        "|------|:--------:|:------:|:-------------:|",
    ]
    label = {"answerable": "도메인 내 답변", "out_of_domain": "환각 방어(거절)", "sensitive": "개인정보 차단"}
    for t in ["answerable", "out_of_domain", "sensitive"]:
        s = summary[t]
        acc = f"{s['acc']*100:.1f}%" if s["acc"] is not None else "N/A"
        lines.append(f"| {label[t]} | {s['correct']}/{s['graded']} | {acc} | {s['errors']} |")
    overall_str = f"{overall*100:.1f}%" if overall is not None else "N/A"
    lines.append(f"| **전체** | **{all_correct}/{all_graded}** | **{overall_str}** | {total_errors} |")

    lines += ["", "## 문항별 상세", "",
              "| ID | 유형 | 질문 | 판정 | 답변(요약) |",
              "|----|------|------|:----:|------------|"]
    mark = {"correct": "✅", "wrong": "❌", "error": "⚠️"}
    for r in rows:
        ans = r["answer"][:60].replace("|", "/")
        lines.append(f"| {r['id']} | {r['type']} | {r['query'][:24]} | {mark[r['verdict']]} | {ans} |")

    lines += ["", "## 판정 규칙 / 한계", "",
              "- **결정적 판정**: 키워드 포함·거절 패턴·PII 경고로 판정 → 재현 가능, 설명 가능.",
              "- **키워드 판정 한계**: 의미는 맞지만 표현이 달라 키워드가 빠지면 오답 처리될 수 있음(보수적).",
              "- **에러(⚠️)**: Groq 토큰 한도 등 LLM 호출 실패. 정확도가 아니므로 분모에서 제외.",
              "- 표본이 작으므로(수십 문항) 점수는 **상대 비교·회귀 점검용**이며, 표본을 늘리면 신뢰도 상승."]
    RESULTS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
