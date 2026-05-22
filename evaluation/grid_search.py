"""
하이브리드 검색 가중치 그리드 서치 평가 스크립트

evaluation/testset.json 의 쿼리들을 벡터+BM25 후보 풀로 검색한 뒤,
가중치(0.3~1.0, 0.1 단위)를 바꿔가며 Recall@k(k=1,3,5)와 MRR을 측정한다.

판정 규칙:
    검색된 상위 k개 문서의 (content + metadata.title) 안에
    testset의 expected_keywords 중 하나 이상이 포함되면 정답으로 본다.

사용법:
    python -m evaluation.grid_search

결과:
    표준 출력 + evaluation/results.md 에 표 형태로 저장.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (스크립트 직접 실행 호환)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chatbot.retriever import HybridRetriever, _normalize_scores  # noqa: E402
from config import HYBRID_BM25_TOP_N  # noqa: E402

TESTSET_PATH = ROOT / "evaluation" / "testset.json"
RESULTS_PATH = ROOT / "evaluation" / "results.md"

VECTOR_WEIGHTS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
K_VALUES = [1, 3, 5]
TOP_K = max(K_VALUES)
CANDIDATE_POOL = 20  # 벡터 검색에서 가져올 후보 수


def load_testset() -> list[dict]:
    with open(TESTSET_PATH, encoding="utf-8") as f:
        return json.load(f)["queries"]


def is_relevant(doc: dict, expected_keywords: list[str]) -> bool:
    """문서가 정답인지 판정 (키워드 기반)"""
    title = (doc.get("metadata") or {}).get("title", "") or ""
    content = doc.get("content", "") or ""
    haystack = (title + " " + content)
    return any(kw in haystack for kw in expected_keywords)


def collect_candidates(retriever: HybridRetriever, query: str) -> tuple[list[dict], list[dict]]:
    """쿼리당 벡터/BM25 후보를 한 번만 모은다 (가중치 조합마다 재호출 안 함)"""
    try:
        vec_results = retriever.vs.similarity_search(query, k=CANDIDATE_POOL)
    except Exception as e:
        print(f"  [warn] vector search failed: {e}")
        vec_results = []

    if retriever.bm25 and retriever.bm25.enabled:
        try:
            bm25_results = retriever.bm25.search(query, top_n=HYBRID_BM25_TOP_N)
        except Exception as e:
            print(f"  [warn] BM25 search failed: {e}")
            bm25_results = []
    else:
        bm25_results = []

    return vec_results, bm25_results


def hybrid_rerank(
    vec_results: list[dict],
    bm25_results: list[dict],
    vector_weight: float,
    bm25_weight: float,
    k: int,
) -> list[dict]:
    """주어진 가중치로 후보를 재랭킹하여 상위 k개 반환"""
    candidates: dict[str, dict] = {}
    for r in vec_results:
        candidates[r["id"]] = {**r, "bm25_score": 0.0}
    for r in bm25_results:
        if r["id"] in candidates:
            candidates[r["id"]]["bm25_score"] = r["bm25_score"]
        else:
            candidates[r["id"]] = {
                "id": r["id"],
                "content": r.get("content", ""),
                "metadata": r.get("metadata", {}),
                "similarity": 0.0,
                "bm25_score": r["bm25_score"],
            }

    if not candidates:
        return []

    vec_norm = _normalize_scores([(cid, c["similarity"]) for cid, c in candidates.items()])
    bm25_norm = _normalize_scores([(cid, c["bm25_score"]) for cid, c in candidates.items()])

    for cid, c in candidates.items():
        c["hybrid_score"] = (
            vector_weight * vec_norm.get(cid, 0)
            + bm25_weight * bm25_norm.get(cid, 0)
        )

    return sorted(candidates.values(), key=lambda x: x["hybrid_score"], reverse=True)[:k]


def evaluate(
    queries: list[dict],
    cached_candidates: dict[str, tuple[list[dict], list[dict]]],
    vector_weight: float,
) -> dict:
    """주어진 가중치에서 전체 평가셋의 Recall@k, MRR 계산"""
    bm25_weight = round(1.0 - vector_weight, 2)
    recall_hits = {k: 0 for k in K_VALUES}
    reciprocal_ranks: list[float] = []

    for q in queries:
        vec_results, bm25_results = cached_candidates[q["id"]]
        ranked = hybrid_rerank(vec_results, bm25_results, vector_weight, bm25_weight, TOP_K)

        first_hit_rank: int | None = None
        for rank, doc in enumerate(ranked, start=1):
            if is_relevant(doc, q["expected_keywords"]):
                first_hit_rank = rank
                break

        for k in K_VALUES:
            if first_hit_rank is not None and first_hit_rank <= k:
                recall_hits[k] += 1

        reciprocal_ranks.append(1.0 / first_hit_rank if first_hit_rank else 0.0)

    n = len(queries)
    return {
        "vector_weight": vector_weight,
        "bm25_weight": bm25_weight,
        "recall@1": recall_hits[1] / n,
        "recall@3": recall_hits[3] / n,
        "recall@5": recall_hits[5] / n,
        "mrr": sum(reciprocal_ranks) / n,
    }


def render_markdown(rows: list[dict], out_path: Path) -> None:
    """결과를 markdown 표로 저장"""
    header = (
        "# 하이브리드 검색 가중치 그리드 서치 결과\n\n"
        f"- 테스트셋: `evaluation/testset.json` ({len(rows[0].get('_n_queries', '?'))} 쿼리 가정)\n"
        f"- 후보 풀: 벡터 {CANDIDATE_POOL}건 + BM25 {HYBRID_BM25_TOP_N}건의 합집합\n"
        f"- 정답 판정: expected_keywords가 (title + content)에 포함되면 정답\n\n"
        "| vec:bm25 | Recall@1 | Recall@3 | Recall@5 | MRR |\n"
        "|----------|---------:|---------:|---------:|----:|\n"
    )
    body_lines = []
    for r in rows:
        body_lines.append(
            f"| {r['vector_weight']:.1f}:{r['bm25_weight']:.1f} "
            f"| {r['recall@1']:.3f} | {r['recall@3']:.3f} | {r['recall@5']:.3f} "
            f"| {r['mrr']:.3f} |"
        )
    out_path.write_text(header + "\n".join(body_lines) + "\n", encoding="utf-8")


def main() -> None:
    print("=== 하이브리드 가중치 그리드 서치 시작 ===")
    queries = load_testset()
    print(f"테스트셋: {len(queries)} 쿼리")

    print("HybridRetriever 초기화 중 (BM25 인덱스 + 임베딩 모델 로딩)...")
    retriever = HybridRetriever()

    print("쿼리별 후보 풀 수집 중 (벡터 + BM25)...")
    cached: dict[str, tuple[list[dict], list[dict]]] = {}
    for i, q in enumerate(queries, start=1):
        cached[q["id"]] = collect_candidates(retriever, q["query"])
        if i % 10 == 0:
            print(f"  {i}/{len(queries)} 수집 완료")

    print("\n가중치별 평가 진행...")
    rows: list[dict] = []
    for vw in VECTOR_WEIGHTS:
        result = evaluate(queries, cached, vw)
        rows.append(result)
        print(
            f"  vec:bm25 = {result['vector_weight']:.1f}:{result['bm25_weight']:.1f}  "
            f"R@1={result['recall@1']:.3f}  R@3={result['recall@3']:.3f}  "
            f"R@5={result['recall@5']:.3f}  MRR={result['mrr']:.3f}"
        )

    render_markdown(rows, RESULTS_PATH)
    print(f"\n결과 저장: {RESULTS_PATH.relative_to(ROOT)}")

    best_mrr = max(rows, key=lambda r: r["mrr"])
    best_r5 = max(rows, key=lambda r: r["recall@5"])
    print("\n=== 최적 가중치 ===")
    print(
        f"MRR 기준    : vec:bm25 = {best_mrr['vector_weight']:.1f}:{best_mrr['bm25_weight']:.1f} "
        f"(MRR={best_mrr['mrr']:.3f})"
    )
    print(
        f"Recall@5 기준: vec:bm25 = {best_r5['vector_weight']:.1f}:{best_r5['bm25_weight']:.1f} "
        f"(R@5={best_r5['recall@5']:.3f})"
    )


if __name__ == "__main__":
    main()
