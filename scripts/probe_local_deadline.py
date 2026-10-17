"""Verify local cancellation with synthetic text and a following short request."""
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chatbot.llm_runtime import create_llm
from chatbot.local_inference import invoke_selection


def main():
    schema = {'type': 'object', 'properties': {'choice': {'type': 'integer', 'enum': [1]}},
              'required': ['choice'], 'additionalProperties': False}
    llm = create_llm().model_copy(update={'format': schema, 'num_predict': 100, 'temperature': 0})
    output = {'started_at': datetime.now(timezone.utc).isoformat(),
              'protocol': 'Synthetic deadline/cancellation test, not an administrative answer test.'}
    started = time.perf_counter()
    try:
        invoke_selection(llm, '다음 합성 입력을 검토하고 choice 1을 선택하세요.\n' +
                         ('합성 자료에서 실제 행정 사실을 만들지 마세요. ' * 100), timeout=1)
        output['deadline_outcome'] = 'completed_before_deadline'
    except Exception as error:
        output['deadline_outcome'] = type(error).__name__
    output['deadline_seconds'] = time.perf_counter() - started
    started = time.perf_counter()
    try:
        reply = invoke_selection(llm, '합성 검사입니다. choice 1을 JSON으로 반환하세요.')
        output.update(followup_content=reply.content, followup_metadata=reply.response_metadata)
    except Exception as error:
        output['followup_outcome'] = type(error).__name__
    output.update(followup_seconds=time.perf_counter() - started,
                  finished_at=datetime.now(timezone.utc).isoformat())
    Path(sys.argv[1]).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
