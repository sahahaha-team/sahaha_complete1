"""구청 공식 100문항이 검색되고 LLM 답변에 사실대로 반영되는지 검사한다."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib import request

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chatbot.official_faq import OfficialFAQIndex


def _normalized_text(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", (value or "").lower())


def _bigrams(value: str) -> set[str]:
    normalized = _normalized_text(value)
    return {normalized[index:index + 2] for index in range(max(0, len(normalized) - 1))}


def answer_alignment(expected: str, actual: str) -> tuple[bool, float, list[str]]:
    """문장 복사 여부가 아니라 내용 유사도와 숫자 사실 보존 여부를 평가한다."""
    expected_grams = _bigrams(expected)
    actual_grams = _bigrams(actual)
    score = (
        len(expected_grams & actual_grams) / len(expected_grams)
        if expected_grams else 0.0
    )

    expected_facts = {
        re.sub(r"\D", "", value)
        for value in re.findall(r"\d[\d\s:,.~\-]*\d|\d+", expected or "")
    }
    actual_digits = re.sub(r"\D", "", actual or "")
    missing_facts = sorted(fact for fact in expected_facts if fact and fact not in actual_digits)
    return score >= 0.35 and not missing_facts, round(score, 4), missing_facts


def _post_chat(base_url: str, question: str) -> dict:
    payload = json.dumps({"message": question}, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--faq", type=Path, default=ROOT / "resources" / "official_faq.json")
    parser.add_argument("--live-url", help="예: http://127.0.0.1:5000")
    parser.add_argument("--in-process", action="store_true", help="HTTP 제한 없이 ChatBot 객체를 직접 검사")
    parser.add_argument("--limit", type=int, help="라이브 점검 시 앞에서부터 검사할 문항 수")
    args = parser.parse_args()

    index = OfficialFAQIndex(args.faq)
    bot = None
    if args.in_process:
        from chatbot.conversation import ChatBot
        bot = ChatBot()
    failures = []
    items = index.items[:args.limit] if args.limit else index.items
    for item in items:
        match = index.find_best(item["question"], min_score=0.88)
        if not match or match.get("id") != item.get("id") or match.get("url") != item.get("url"):
            failures.append({"id": item.get("id"), "stage": "local_match"})
            continue
        if bot is not None:
            result = bot.chat(f"official-faq-eval-{item['id']}", item["question"])
            urls = {source.get("url") for source in result.get("sources", [])}
            aligned, score, missing_facts = answer_alignment(
                item["answer"], result.get("answer", "")
            )
            if item["url"] not in urls or not aligned:
                failures.append({
                    "id": item.get("id"),
                    "stage": "in_process_chat",
                    "alignment": score,
                    "missing_facts": missing_facts,
                })
        elif args.live_url:
            result = _post_chat(args.live_url, item["question"])
            urls = {source.get("url") for source in result.get("sources", [])}
            aligned, score, missing_facts = answer_alignment(
                item["answer"], result.get("answer", "")
            )
            if item["url"] not in urls or not aligned:
                failures.append({
                    "id": item.get("id"),
                    "stage": "live_chat",
                    "alignment": score,
                    "missing_facts": missing_facts,
                })

    passed = len(items) - len(failures)
    print(json.dumps({"total": len(items), "passed": passed, "failed": failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
