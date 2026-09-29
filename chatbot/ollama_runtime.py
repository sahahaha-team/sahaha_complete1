"""로컬 Ollama 서버 및 모델 준비 상태 점검."""

from __future__ import annotations

import requests

from config import OLLAMA_BASE_URL, OLLAMA_MODEL


def get_ollama_status(timeout: float = 2.0) -> dict:
    base_url = OLLAMA_BASE_URL.rstrip("/")
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        names = {
            str(item.get("name") or item.get("model") or "")
            for item in payload.get("models", [])
        }
        # Ollama는 `model`과 `model:latest`를 같은 로컬 모델로 표시할 수 있다.
        expected = {OLLAMA_MODEL}
        if ":" not in OLLAMA_MODEL:
            expected.add(f"{OLLAMA_MODEL}:latest")
        ready = bool(names & expected)
        return {
            "available": True,
            "model_ready": ready,
            "model": OLLAMA_MODEL,
            "base_url": base_url,
            "installed_models": sorted(name for name in names if name),
            "message": "ready" if ready else f"ollama pull {OLLAMA_MODEL} 실행 필요",
        }
    except Exception as exc:
        return {
            "available": False,
            "model_ready": False,
            "model": OLLAMA_MODEL,
            "base_url": base_url,
            "installed_models": [],
            "message": f"Ollama 연결 실패: {exc}",
        }
