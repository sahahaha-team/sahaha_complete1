"""Export a human-reviewed HTTP audit; never infer correctness from status 200."""
from __future__ import annotations
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--reviews', type=Path, required=True)
    parser.add_argument('--metrics-log', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit = json.loads(args.results.read_text(encoding='utf-8'))
    reviews = json.loads(args.reviews.read_text(encoding='utf-8'))
    assert audit.get('finished_at'), 'Interrupted runs cannot be final evaluations'
    assert audit.get('code_unchanged'), 'Evaluation code changed during the run'
    records = audit['records']
    keys = [f"{r['id']}:{r['turn']}" for r in records]
    assert set(keys) == set(reviews['turns']), 'Every observed turn needs an explicit review'
    metrics = {}
    for line in args.metrics_log.read_text(encoding='utf-8', errors='replace').splitlines():
        if 'consultation_metrics ' in line:
            value = json.loads(line.split('consultation_metrics ', 1)[1])
            metrics[value['request_id']] = value
    durations = sorted(r['seconds'] for r in records)
    grades = Counter()
    model_calls = []
    missing_metrics = []
    lines = ['# 실제 상담 질문 및 검수 내역', '',
             '개발 AI가 공식 원문과 대조한 개발 평가입니다. 담당자·주민 독립 정답률이 아닙니다.', '',
             'S 충분 / C 필요한 확인 / P 부분 / I 타당한 근거 부족 / R 불필요 거절 / W 오안내 / E 실행 오류.', '',
             f"실행: {audit['started_at']} ~ {audit['finished_at']} (UTC)", '']
    for record, key in zip(records, keys):
        review = reviews['turns'][key]
        assert review['grade'] in 'SCPI RWE'.replace(' ', '')
        assert review['reason'] and review['source_check']
        grades[review['grade']] += 1
        metric = metrics.get(record['request_id'])
        if metric is None:
            missing_metrics.append(key)
        else:
            model_calls.extend(metric.get('model_calls', []))
        sources = record['response'].get('sources', [])
        links = ', '.join(f"[{s.get('title') or '공식 원문'}]({s['url']})" for s in sources if s.get('url')) or '없음'
        lines += [f"## {record['id']} / {record['turn']}턴 — {review['grade']}", '',
                  '**질문:** ' + record['question'], '',
                  '**실제 답변:**', '', record['response'].get('answer', '(응답 없음)'), '',
                  '**검수:** ' + review['reason'], '', '**원문 대조:** ' + review['source_check'], '',
                  '**출처:** ' + links, '', f"**응답 시간:** {record['seconds']}초", '']
    summary = {'started_at': audit['started_at'], 'finished_at': audit['finished_at'],
               'assessment': 'developer_AI_review_not_independent_accuracy',
               'turns': len(records), 'scenarios': len(set(r['id'] for r in records)),
               'unique_question_strings': len(set(r['question'] for r in records)),
               'grades': dict(grades), 'latency_seconds': {'median': statistics.median(durations),
               'p95_nearest_rank': durations[math.ceil(len(durations)*.95)-1], 'max': max(durations)},
               'http_status': dict(Counter(str(r['status']) for r in records)),
               'metrics_missing': missing_metrics, 'model_call_count': len(model_calls),
               'model_calls': model_calls, 'code_unchanged': audit['code_unchanged']}
    args.output.with_suffix('.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    args.output.with_suffix('.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
