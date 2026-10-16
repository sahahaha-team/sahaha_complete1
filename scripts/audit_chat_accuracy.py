"""Repeatable real HTTP audit. Outputs observations, never automatic accuracy.

Run only synthetic/public questions. Response time excludes pacing/rate-limit
waits. One cookie session per scenario, preserved for its follow-up turns.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]


def save_report(path, report):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def code_hashes():
    files = [ROOT / 'app.py', ROOT / 'config.py']
    for folder in ('chatbot', 'database_db', 'crawler'):
        files.extend((ROOT / folder).glob('*.py'))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', type=Path, default=ROOT / 'evaluation/accuracy_upgrade_cases.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--split', choices=['development', 'heldout', 'all'], default='development')
    parser.add_argument('--base-url', default='http://127.0.0.1:5000')
    parser.add_argument('--only', default='')
    parser.add_argument('--ready-timeout', type=float, default=90)
    args = parser.parse_args()
    deadline = time.monotonic() + args.ready_timeout
    while True:
        try:
            ready = requests.get(args.base_url + '/api/health', timeout=3)
            if ready.status_code == 200 and ready.json().get('status') == 'ok':
                break
        except requests.RequestException:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError('Server is not ready; no evaluation was started')
        time.sleep(1)
    raw = args.cases.read_bytes()
    cases = json.loads(raw)
    scenarios = []
    for family in cases['families']:
        queries = family['queries'] if args.split != 'heldout' else []
        if args.split != 'development':
            queries = [*queries, family['heldout']]
        for i, q in enumerate(queries):
            scenarios.append({'id': f"{family['id']}_{i}", 'turns': [q], 'criterion': family['criterion']})
    if args.split != 'heldout':
        scenarios.extend(cases['scenarios'])
    if args.only:
        prefixes = args.only.split(',')
        scenarios = [s for s in scenarios if any(s['id'].startswith(p) for p in prefixes)]
    hashes = code_hashes()
    report = {'started_at': datetime.now(timezone.utc).isoformat(),
              'commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'case_sha256': hashlib.sha256(raw).hexdigest(), 'code_hashes': hashes,
              'health_before': ready.json(), 'python': sys.version,
              'split': args.split, 'protocol': cases['protocol'], 'records': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    next_start = 0
    for scenario in scenarios:
        with requests.Session() as session:
            for turn, query in enumerate(scenario['turns'], 1):
                attempts = []
                # Respect production 10/min; do not disable its limiter.
                while True:
                    time.sleep(max(0, next_start - time.monotonic()))
                    start = time.perf_counter()
                    next_start = time.monotonic() + 6.5
                    try:
                        response = session.post(args.base_url + '/api/chat', json={'message': query}, timeout=160)
                        elapsed = time.perf_counter() - start
                        status = response.status_code
                        body = response.json()
                        error = None
                        timing = response.headers.get('Server-Timing', '')
                    except Exception as exc:
                        elapsed = time.perf_counter() - start
                        status, body, timing, error = None, {}, '', type(exc).__name__
                    attempts.append({'status': status, 'seconds': round(elapsed, 3)})
                    if status != 429 or len(attempts) >= 4:
                        break
                    next_start = time.monotonic() + 30
                record = {'id': scenario['id'], 'turn': turn, 'question': query,
                          'criterion': scenario['criterion'], 'seconds': round(elapsed,3),
                          'server_timing': timing, 'status': status, 'error': error,
                          'attempts': attempts, 'response': body}
                report['records'].append(record)
                report['code_unchanged'] = hashes == code_hashes()
                save_report(args.output, report)
                print(json.dumps({k: record[k] for k in ('id','turn','seconds','status')}, ensure_ascii=False), flush=True)
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    save_report(args.output, report)


if __name__ == '__main__':
    main()
