"""Windows resume and interrupted-collection scheduling regressions."""
import json
import unittest
from unittest.mock import patch

from worker import ResumeAwareScheduler, incremental_job


class WorkerScheduleTests(unittest.TestCase):
    def test_sleep_resume_does_not_wait_several_hours_to_recheck_wall_clock(self):
        scheduler = ResumeAwareScheduler(timezone='Asia/Seoul')
        for original, expected in ((None, 30), (7200, 30), (5, 5), (0, 0)):
            with patch('apscheduler.schedulers.blocking.BlockingScheduler._process_jobs', return_value=original):
                self.assertEqual(scheduler._process_jobs(), expected)

    def test_nightly_run_resumes_only_incomplete_initial_collection(self):
        for report, expected in (({'counts': {'pending': 10}}, True),
                                 ({'counts': {}, 'pending_index': 2}, True),
                                 ({'counts': {'failed': 2, 'pending': 0}, 'pending_index': 0}, False)):
            with patch('worker.Path.read_text', return_value=json.dumps(report)), patch('crawler.site_sync.run_site_sync') as sync:
                incremental_job()
                sync.assert_called_once_with(resume=expected)


if __name__ == '__main__':
    unittest.main()
