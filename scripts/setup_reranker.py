"""Install the public local reranker once; web requests never download weights."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import RAG_RERANK_MODEL, RAG_RERANK_CACHE_DIR


def main():
    parser = argparse.ArgumentParser(description='로컬 의미 재정렬 모델 준비')
    parser.add_argument('--download', action='store_true', help='공개 모델을 한 번 내려받습니다')
    args = parser.parse_args()
    from huggingface_hub import snapshot_download
    try:
        snapshot_download(RAG_RERANK_MODEL, cache_dir=RAG_RERANK_CACHE_DIR, token=False,
                          local_files_only=not args.download,
                          allow_patterns=['*.json', '*.safetensors', '*.txt', '*.model'])
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        AutoTokenizer.from_pretrained(RAG_RERANK_MODEL, cache_dir=RAG_RERANK_CACHE_DIR,
                                      local_files_only=True, trust_remote_code=False)
        AutoModelForSequenceClassification.from_pretrained(RAG_RERANK_MODEL,
            cache_dir=RAG_RERANK_CACHE_DIR, local_files_only=True,
            trust_remote_code=False, use_safetensors=True)
    except Exception as exc:
        print('모델 준비 실패:', type(exc).__name__)
        print('--download로 모델을 준비하거나 RAG_RERANK_ENABLED=false로 기존 검색을 사용하세요.')
        return 1
    print('로컬 의미 재정렬 모델 준비 완료:', RAG_RERANK_MODEL)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
