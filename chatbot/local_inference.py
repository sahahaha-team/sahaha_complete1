"""Bound local model work across the web and ingestion processes."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
import httpx

from chatbot.request_metrics import add_duration
from worker_recovery import process_lock

MODEL_LOCK = Path(__file__).resolve().parents[1] / '.local' / 'model_inference.lock'


class ModelBusy(RuntimeError):
    pass


def is_local_chat_model(llm):
    return type(llm).__module__.startswith('langchain_ollama.')


def local_model_revision(llm):
    """Resolve the current tag on cache access; an unknown revision is no hit."""
    try:
        import requests
        response = requests.get(llm.base_url.rstrip('/') + '/api/tags', timeout=1,
                                allow_redirects=False)
        response.raise_for_status()
        expected = {llm.model, llm.model + ':latest'}
        return next((row['digest'] for row in response.json().get('models', [])
                     if (row.get('name') or row.get('model')) in expected and row.get('digest')), None)
    except Exception:
        return None


def invoke_selection(llm, prompt, *, background=False, timeout=None):
    """Use the installed adapter's exact payload with a cancellable total wait.

    No executor thread is left running after an HTTP deadline. Ollama can
    finish its current prefill batch after disconnect, so a shared recovery
    interval prevents immediately submitting more work after a timeout.
    """
    if not is_local_chat_model(llm):
        return llm.invoke(prompt, stream=False)
    import config
    from langchain_core.messages import HumanMessage
    budget = timeout if timeout is not None else (config.OLLAMA_TIMEOUT if background
                                                   else config.CHATBOT_SELECTION_TIMEOUT)
    params = llm._chat_params([HumanMessage(content=prompt)], stream=False)
    if not params.get('format'):
        raise ValueError('근거·메타데이터 선택에는 JSON 스키마가 필요합니다')

    async def request():
        async with httpx.AsyncClient(timeout=httpx.Timeout(budget, connect=min(3, budget)),
                                     trust_env=False, follow_redirects=False) as client:
            try:
                async with asyncio.timeout(budget):
                    response = await client.post(llm.base_url.rstrip('/') + '/api/chat', json=params)
                    response.raise_for_status()
                    body = response.json()
            except httpx.TimeoutException as error:
                raise TimeoutError('로컬 모델 처리시간 초과') from error
        message = body.get('message') or {}
        if (not body.get('done') or not isinstance(message.get('content'), str)
                or message.get('tool_calls') or body.get('error')):
            raise ValueError('로컬 모델 선택 응답 형식 오류')
        return SimpleNamespace(content=message['content'], response_metadata={
            key: body.get(key) for key in ('done_reason', 'total_duration', 'load_duration',
                'prompt_eval_count', 'prompt_eval_duration', 'eval_count', 'eval_duration')},
                additional_kwargs={})

    started = time.perf_counter()
    with process_lock(MODEL_LOCK) as acquired:
        add_duration('model_gate', time.perf_counter() - started)
        if not acquired:
            raise ModelBusy('로컬 모델 사용 중')
        recovery = MODEL_LOCK.with_suffix('.recovery')
        try:
            until = float(recovery.read_text(encoding='ascii')) if recovery.exists() else 0
        except (OSError, ValueError):
            raise ModelBusy('로컬 모델 복구 상태 확인 필요')
        if time.time() < until:
            raise ModelBusy('로컬 모델 복구 대기 중')
        # Sequential bounded requests, not another unbounded Ollama queue.
        try:
            return asyncio.run(request())
        except TimeoutError:
            temporary = recovery.with_suffix('.tmp')
            temporary.write_text(str(time.time() + config.CHATBOT_MODEL_RECOVERY_SECONDS), encoding='ascii')
            temporary.replace(recovery)
            raise
