"""Provider selection without changing the evidence-only answer contract."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import SimpleNamespace
from urllib.parse import urlsplit

import requests

import config
from chatbot.ollama_runtime import get_ollama_status


def vllm_base_url(value: str) -> str:
    parts = urlsplit(value)
    if (parts.scheme not in ('http', 'https') or not parts.hostname or
            parts.username or parts.password or parts.query or parts.fragment):
        raise ValueError('VLLM_BASE_URL에 인증정보 없는 http(s) API 주소를 설정하세요')
    base = value.rstrip('/')
    return base if base.endswith('/v1') else base + '/v1'


@dataclass(frozen=True, repr=False)
class VLLMSelector:
    """Small OpenAI-compatible transport; it selects source IDs, never facts.

    Match the existing planner's model_copy/invoke contract. Ollama's format
    and num_predict are explicitly translated to vLLM's JSON schema and token
    limit, rather than silently dropping those safety/latency controls.
    """
    base_url: str
    model: str
    api_key: str = field(default='', repr=False)
    timeout: float = 120
    temperature: float = 0
    num_predict: int = 100
    format: dict | None = None
    provider: str = field(default='vllm', init=False)

    def __post_init__(self):
        object.__setattr__(self, 'base_url', vllm_base_url(self.base_url))
        if not self.model.strip():
            raise ValueError('VLLM_MODEL에 실제 서버 모델 ID를 설정하세요')

    @property
    def cache_identity(self):
        return ('vllm', self.base_url, self.model, self.temperature,
                self.num_predict, False)

    def model_copy(self, *, update):
        return replace(self, **update)

    def invoke(self, prompt: str, *, stream=False):
        if stream or not isinstance(prompt, str) or not self.format:
            raise ValueError('근거 선택에는 단일 JSON 스키마 응답이 필요합니다')
        payload = {
            'model': self.model, 'messages': [{'role': 'user', 'content': prompt}],
            'stream': False, 'temperature': self.temperature,
            'max_tokens': self.num_predict,
            'chat_template_kwargs': {'enable_thinking': False},
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': 'evidence_selection', 'schema': self.format}},
        }
        headers = {'Authorization': 'Bearer ' + self.api_key} if self.api_key else {}
        response = requests.post(self.base_url + '/chat/completions', json=payload,
                                 headers=headers, timeout=(5, self.timeout),
                                 allow_redirects=False)
        if response.status_code != 200:
            # No backend body/URL/authentication text in application exceptions.
            raise RuntimeError('vLLM 근거 선택 요청 실패')
        body = response.json()
        choice = body['choices'][0]
        message = choice['message']
        content = message.get('content')
        if message.get('refusal') or message.get('tool_calls') or not isinstance(content, str):
            raise ValueError('vLLM 근거 선택 응답 형식 오류')
        usage = body.get('usage') or {}
        return SimpleNamespace(content=content, response_metadata={
            'done_reason': choice.get('finish_reason'),
            'prompt_eval_count': usage.get('prompt_tokens', 0),
            'eval_count': usage.get('completion_tokens', 0),
        })


def create_llm():
    if config.LLM_PROVIDER == 'vllm':
        return VLLMSelector(config.VLLM_BASE_URL, config.VLLM_MODEL,
                            config.VLLM_API_KEY, config.VLLM_TIMEOUT)
    from langchain_ollama import ChatOllama
    options = dict(base_url=config.OLLAMA_BASE_URL, model=config.OLLAMA_MODEL,
                   temperature=config.CHATBOT_TEMPERATURE,
                   num_predict=config.CHATBOT_MAX_TOKENS,
                   num_ctx=config.OLLAMA_NUM_CTX,
                   client_kwargs={'timeout': config.OLLAMA_TIMEOUT},
                   keep_alive=config.OLLAMA_KEEP_ALIVE)
    if config.OLLAMA_MODEL.split(':')[0].split('/')[-1] == 'gemma4':
        # Current langchain-ollama maps reasoning=False to Ollama think=False.
        options['reasoning'] = False
    return ChatOllama(**options)


def get_llm_status(timeout: float = 2.0) -> dict:
    if config.LLM_PROVIDER == 'ollama':
        return {'provider': 'ollama', **get_ollama_status(timeout)}
    state = {'provider': 'vllm', 'available': False, 'model_ready': False,
             'model': config.VLLM_MODEL, 'installed_models': []}
    try:
        base = vllm_base_url(config.VLLM_BASE_URL)
        headers = {'Authorization': 'Bearer ' + config.VLLM_API_KEY} if config.VLLM_API_KEY else {}
        response = requests.get(base + '/models', headers=headers, timeout=timeout,
                                allow_redirects=False)
        if response.status_code != 200:
            raise ValueError('모델 조회 실패')
        names = sorted({item['id'] for item in response.json()['data']})
        ready = bool(config.VLLM_MODEL and config.VLLM_MODEL in names)
        return {**state, 'available': True, 'model_ready': ready,
                'installed_models': names,
                'message': 'ready' if ready else '서버 모델 ID와 VLLM_MODEL을 확인하세요'}
    except Exception:
        return {**state, 'message': 'vLLM 연결 또는 설정 확인 필요'}
