import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from worker_recovery import RefreshCoordinator, RefreshTask, process_lock


class WorkerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.json'
        self.now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)

    def coordinator(self, callbacks):
        return RefreshCoordinator([RefreshTask(name, cb) for name, cb in callbacks], self.path, now=lambda: self.now)

    def test_restart_and_long_sleep_recover_successfully_without_repeating_fresh_jobs(self):
        first, second = Mock(return_value={'verified_pages': 2}), Mock()
        c = self.coordinator([('staff', first), ('pages', second)])
        self.assertEqual(c.check_overdue(), 'succeeded')
        self.assertEqual(self.coordinator([('staff', first)]).check_overdue(), 'current')
        self.assertEqual(c.check_overdue(), 'succeeded')
        first.assert_called_once()
        second.assert_called_once()
        self.now += timedelta(days=2)
        self.assertEqual(c.check_overdue(), 'succeeded')
        self.assertEqual(first.call_count, 2)

    def test_failure_keeps_last_success_and_backs_off_while_other_jobs_continue(self):
        failing = Mock(side_effect=TimeoutError)
        next_job = Mock()
        c = self.coordinator([('staff', failing), ('pages', next_job)])
        old = (self.now - timedelta(days=2)).isoformat()
        c._write({'jobs': {'staff': {'last_success_at': old}}})
        self.assertEqual(c.check_overdue(), 'failed')
        self.assertEqual(c._read()['jobs']['staff']['last_success_at'], old)
        self.assertEqual(c.check_overdue(), 'succeeded')
        self.assertEqual(c.run('staff'), 'current')
        failing.assert_called_once()
        self.now += timedelta(minutes=31)
        self.assertEqual(c.run('staff'), 'failed')

    def test_partial_refresh_is_not_reported_as_success(self):
        c = self.coordinator([('pages', Mock(return_value={'verified_pages': 98, 'failed_pages': 2, 'errors': 0}))])
        self.assertEqual(c.check_overdue(), 'partial')
        row = c._read()['jobs']['pages']
        self.assertNotIn('last_success_at', row)
        self.assertEqual(row['last_result']['failed_pages'], 2)

    def test_second_worker_cannot_run_same_job_concurrently(self):
        callback = Mock()
        c = self.coordinator([('pages', callback)])
        with process_lock(c.lock_path) as acquired:
            self.assertTrue(acquired)
            self.assertEqual(c.run('pages'), 'busy')
        callback.assert_not_called()
        self.assertEqual(c.run('pages'), 'succeeded')

    def test_interrupted_running_state_or_future_success_is_retried(self):
        callback = Mock()
        c = self.coordinator([('pages', callback)])
        c._write({'jobs': {'pages': {'status': 'running', 'last_success_at': (self.now + timedelta(days=5)).isoformat()}}})
        self.assertEqual(c.check_overdue(), 'succeeded')

    def test_corrupt_state_is_recovered_and_write_is_atomic(self):
        self.path.write_text('{broken', encoding='utf-8')
        c = self.coordinator([('pages', Mock())])
        self.assertEqual(c.check_overdue(), 'succeeded')
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['jobs']['pages']['status'], 'succeeded')
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_forced_cron_failure_retries_even_after_a_recent_success(self):
        callback = Mock(return_value={'verified_pages': 1})
        c = self.coordinator([('pages', callback)])
        self.assertEqual(c.run('pages'), 'succeeded')
        callback.side_effect = TimeoutError
        self.assertEqual(c.run('pages', force=True), 'failed')
        self.assertEqual(c.check_overdue(), 'current')
        self.now += timedelta(minutes=31)
        self.assertEqual(c.check_overdue(), 'failed')


class SnapshotSafetyTests(unittest.TestCase):
    def test_changed_wording_cannot_bypass_the_dynamic_source_age_limit(self):
        from chatbot.freshness import source_max_age_days
        from config import SOURCE_DYNAMIC_MAX_AGE_DAYS
        for query in ('희망도서 월별 신청 한도', '희망도서 몇 권 신청할 수 있어?',
                      '여권 재발급 준비물', '자격증 응시료 지원 대상', '보건소 주소는?'):
            self.assertEqual(source_max_age_days(query), SOURCE_DYNAMIC_MAX_AGE_DAYS)

    def test_missing_stale_and_future_staff_snapshots_never_start_a_chat_crawl(self):
        from chatbot.dept_directory import _load_directory
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'staff.json'
            with patch('chatbot.dept_directory.STAFF_DIRECTORY_PATH', path), patch('chatbot.dept_directory.refresh_directory') as refresh:
                self.assertEqual(_load_directory()['rows'], [])
                for delta in (timedelta(days=-8), timedelta(days=1)):
                    path.write_text(json.dumps({'rows': [{'department': '공식부서'}],
                        'generated_at': (datetime.now(timezone.utc) + delta).isoformat()}), encoding='utf-8')
                    self.assertEqual(_load_directory()['rows'], [])
                refresh.assert_not_called()

    def test_future_timestamp_does_not_verify_a_fact_or_contact(self):
        from chatbot.verified_facts import _fresh
        from chatbot.contact_directory import fresh
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.assertIsNone(_fresh(future))
        self.assertFalse(fresh(future))

    def test_staff_crawl_timeout_preserves_the_saved_snapshot(self):
        from crawler.staff_directory import StaffDirectoryCrawler
        crawler = StaffDirectoryCrawler()
        html = '<table class="tableSt_list"><tbody><tr><td>부서</td><td>직위</td><td>220-1111</td><td>업무</td></tr></tbody></table>Page 1 / 2 Total 2'
        try:
            with patch.object(crawler, 'fetch_page', return_value=html) as fetch, patch('crawler.staff_directory.time.monotonic', side_effect=[0, 601]):
                with self.assertRaises(RuntimeError):
                    crawler.crawl(timeout_seconds=600)
                fetch.assert_called_once_with(1)
        finally:
            crawler.session.close()
