"""Refresh an explicit public URL inventory with the normal crawler/indexer.

The inventory contains URLs only, never evaluation questions or expected answers.
An isolated journal prevents overwriting an in-progress site crawl checkpoint.
"""
import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run(inventory, journal):
    import crawler.site_sync as sync
    from crawler.site_sync import Frontier, fetch_resource, index_fetched, get_public
    from crawler.site_scope import RobotsRules
    frontier = Frontier(journal)
    sync.REPORT = journal.with_suffix('.report.json')
    urls = json.loads(inventory.read_text(encoding='utf-8'))
    if not isinstance(urls, list) or not all(isinstance(url, str) for url in urls):
        raise ValueError('URL inventory must be a JSON list of URL strings')
    policies = {}
    for url in urls:
        frontier.add(url)
    frontier.db.commit()
    for row in frontier.rows("status='pending'"):
        parsed = urlsplit(row['url'])
        origin = parsed.scheme + '://' + parsed.netloc
        if origin not in policies:
            try:
                status, _, body, _ = get_public(origin + '/robots.txt')
                policies[origin] = RobotsRules(body.decode('utf-8-sig', errors='replace')) if status == 200 else RobotsRules('') if status == 404 else None
            except Exception:
                policies[origin] = None
    def policy_for(url):
        parsed = urlsplit(url)
        return policies.get(parsed.scheme + '://' + parsed.netloc)
    rows = frontier.rows("status='pending'")
    with ThreadPoolExecutor(max_workers=3) as pool:
        for row, result in zip(rows, pool.map(lambda row: fetch_resource(row, policy_for), rows)):
            for key in ('links', 'attachment_names'):
                result.pop(key, None)
            frontier.update(row['url'], **result)
            frontier.db.commit()
    print('Refreshed', len(rows), 'public URLs', flush=True)
    index_fetched(frontier)
    print(json.dumps(frontier.report(), ensure_ascii=False), flush=True)
    frontier.db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--urls', type=Path, required=True)
    parser.add_argument('--journal', type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    run(args.urls, args.journal)
