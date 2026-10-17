import asyncio
import json
import unittest

from chatbot.request_metrics import request_metrics, measure, decision, record_model


class RequestMetricsTests(unittest.TestCase):
    def test_thread_work_is_attributed_without_question_or_session_text(self):
        async def work():
            def synchronous():
                with measure('model'):
                    decision('structured_source')
                    record_model(.1, {'prompt_eval_count': 30}, outcome='validated')
            with request_metrics() as metrics:
                await asyncio.to_thread(synchronous)
            return metrics
        metrics = asyncio.run(work())
        self.assertIn('model;dur=', metrics.server_timing())
        self.assertEqual(metrics.model_calls[0]['prompt_eval_count'], 30)
        self.assertIsNone(metrics.model_calls[0]['load_duration_seconds'])
        self.assertEqual(metrics.decisions, ['structured_source'])
        self.assertNotIn('question', json.dumps(metrics.summary()))

    def test_concurrent_requests_and_failure_keep_separate_measurements(self):
        async def request(label, fail):
            with request_metrics() as metrics:
                try:
                    with measure('search'):
                        await asyncio.sleep(.001)
                        decision(label)
                        if fail:
                            raise TimeoutError('must not log credentials or body')
                except TimeoutError as error:
                    record_model(.2, outcome='error', error=error)
            return metrics
        async def run():
            return await asyncio.gather(request('a', True), request('b', False))
        a, b = asyncio.run(run())
        self.assertNotEqual(a.request_id, b.request_id)
        self.assertEqual(a.decisions, ['a'])
        self.assertEqual(b.decisions, ['b'])
        self.assertGreater(a.timings['search'], 0)
        self.assertEqual(b.model_calls, [])
        self.assertNotIn('credentials', json.dumps(a.summary()))
        self.assertEqual(a.model_calls[0]['error_type'], 'TimeoutError')
