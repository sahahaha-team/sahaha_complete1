"""Small synthetic contract probe, never an administrative accuracy score."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from langchain_core.messages import HumanMessage
from chatbot.llm_runtime import create_llm
from chatbot.grounded_planner import PROMPT
from chatbot.local_inference import invoke_selection


def main():
    schema = {'oneOf': [{'type': 'object', 'properties': {
        'mode': {'type': 'string', 'enum': ['answer', 'clarify', 'unavailable']},
        'source': {'type': 'integer', 'enum': [i]},
        'units': {'type': 'array', 'items': {'type': 'integer', 'enum': [0]}, 'maxItems': 3}},
        'required': ['mode', 'source', 'units'], 'additionalProperties': False} for i in range(2)]}
    llm = create_llm().model_copy(update={'format': schema, 'temperature': 0, 'num_predict': 100})
    prompt = PROMPT.format(question='정화조 청소 주기는?', context=(
        '자료 0: 정화조 청소\n[0] 정화조 청소는 연 1회 실시해야 합니다.\n\n'
        '자료 1: 다른 교육\n[0] 교육은 월 2회 실시합니다.'))
    params = llm._chat_params([HumanMessage(content=prompt)], stream=False)
    started = time.perf_counter()
    response = invoke_selection(llm, prompt)
    result = {'at': datetime.now(timezone.utc).isoformat(), 'model': llm.model,
              'protocol': 'Synthetic source-ID selection only; not resident answer accuracy.',
              'request_contract': {k: params[k] for k in ('model', 'stream', 'think', 'options', 'format')},
              'seconds': time.perf_counter() - started, 'content': response.content,
              'metadata': response.response_metadata,
              'thinking_returned': bool(response.additional_kwargs.get('reasoning_content'))}
    target = Path(sys.argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('model', 'seconds', 'content', 'thinking_returned')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
