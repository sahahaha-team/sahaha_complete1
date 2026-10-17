"""Exercise the real optional tagging transport without writing a document."""
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from processor.metadata_tagger import MetadataTagger


def main():
    chunk = SimpleNamespace(url='https://www.saha.go.kr/synthetic-transport-probe',
        title='합성 전송 검사', content='이 문서는 합성 검사입니다. 주민 신청에 필요한 서류를 안내합니다.',
        category='민원', sub_category='', chunk_index=0, total_chunks=1,
        chunk_id='synthetic-transport-probe', department_hint='')
    tagger = MetadataTagger()
    chain = tagger.single_chain
    captured = {}
    class Capture:
        def invoke(self, values):
            response = chain.invoke(values)
            captured['metadata'] = response.response_metadata
            captured['content'] = response.content
            return response
    tagger.single_chain = Capture()
    started = time.perf_counter()
    result = tagger.tag(chunk)
    report = {'at': datetime.now(timezone.utc).isoformat(), 'seconds': time.perf_counter() - started,
        'protocol': 'Synthetic optional-tag transport only; no DB writes or administrative accuracy claim.',
        'model': tagger.llm.model, 'captured': captured, 'result': result,
        'source_identity_preserved': all(result[k] == getattr(chunk, k) for k in
                                       ('url', 'title', 'category', 'chunk_index', 'total_chunks'))}
    Path(sys.argv[1]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('seconds', 'source_identity_preserved')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
