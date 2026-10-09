"""Run supplied council questions through the real chatbot, without training on answers.

Input is a read-only extracted JSON list. Each question uses a separate memory
session. Evidence-status counts are diagnostic counts, never correctness scores.
"""
import argparse
import json
import logging
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run(inputs: Path, output: Path, *, bot=None):
    from config import SOURCE_ONLY_ANSWERS, OLLAMA_MODEL, PERSIST_CONVERSATIONS
    from chatbot.conversation import ChatBot
    from chatbot.faq_targets import WORKBOOK
    from database_db.database import Database
    if PERSIST_CONVERSATIONS:
        raise RuntimeError("Evaluation requires memory-only conversations")
    if WORKBOOK.exists():
        raise RuntimeError("Remove evaluation-question URL routing before measuring general retrieval")
    questions = json.loads(inputs.read_text(encoding="utf-8"))
    bot = bot or ChatBot()
    run_tag = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d_%H%M%S")
    report = {"started_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
              "question_count": len(questions), "model": OLLAMA_MODEL,
              "source_only": SOURCE_ONLY_ANSWERS, "method": "real ChatBot.chat backend; independent memory sessions; no HTTP rate-limit test",
              "question_url_shortcut": False, "draft_answers_indexed": False,
              "db_counts_before": Database(admin=True).stats(), "results": []}
    for i, question in enumerate(questions, 1):
        started = time.monotonic()
        try:
            answer = bot.chat(f"council_audit_{run_tag}_{i}", question["question"])
        except Exception as exc:
            answer = {"answer": "", "error_type": type(exc).__name__, "evidence": {"status": "error"}, "sources": []}
        report["results"].append({**question, **answer, "elapsed_seconds": round(time.monotonic()-started, 2),
                                  "topic_keywords": sorted(bot.retriever._content_keywords(question['question'])),
                                  "evaluated_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
                                  "manual_verdict": "not_reviewed"})
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if i % 10 == 0:
            print("Evaluated", i, "/", len(questions), flush=True)
    report["finished_at"] = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    report["db_counts_after"] = Database(admin=True).stats()
    report["evidence_counts"] = dict(Counter(r.get("evidence", {}).get("status", "missing") for r in report["results"]))
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    def cell(value): return str(value or "").replace("|", "\\|").replace("\n", "<br>")
    lines = ["# 구청 예상 질문 상담 실행 기록", "", "- 실행: " + report["started_at"],
             "- 질문 수: " + str(len(questions)), "- 조건: 실제 Supabase, 독립 메모리 세션, 홈페이지 근거 발췌 답변, 예상답변 미적재, 질문-URL 매핑 미사용",
             "- 아래 근거 상태는 정답률이 아니다. 조건·금액·시점·누락 및 공식 원문과의 일치를 별도 검토해야 한다.",
             "- HTTP/UI 및 후속 대화 평가는 포함하지 않는다.", "", "근거 상태: " + json.dumps(report["evidence_counts"],ensure_ascii=False),
             "", "| 번호 | 질문 | 구청 예상답변 | 실제 핵심 답변 | 근거 상태 |", "|---|---|---|---|---|"]
    for r in report["results"]:
        lines.append("|" + "|".join(cell(v) for v in (r["number"], r["question"], r["expected_answer"], r["answer"], r.get("evidence",{}).get("status"))) + "|")
    output.with_suffix(".md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps(report["evidence_counts"],ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=Path("data/faq_audit_inputs.json"))
    parser.add_argument("--output", type=Path, default=Path("data/council_faq_actual_results.json"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.CRITICAL, force=True)
    run(args.inputs, args.output)
