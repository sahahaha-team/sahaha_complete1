import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, patch

from chatbot import local_inference as local
from chatbot.model_plan_cache import plan_key
from chatbot.request_metrics import request_metrics, record_model, model_failure_reason
from worker_recovery import process_lock


class LocalInferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lock = Path(self.tmp.name) / 'model.lock'
        self.params = {'model': 'gemma4:e4b', 'stream': False, 'think': False,
                       'format': {'type': 'object'}, 'options': {'num_ctx': 4096, 'num_predict': 100}}
        self.llm = SimpleNamespace(base_url='http://127.0.0.1:11434',
                                   _chat_params=Mock(return_value=self.params))

    def client(self, post):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post = post
        return client

    def test_exact_payload_and_structured_metadata_are_kept(self):
        response = Mock()
        response.json.return_value = {'done': True, 'message': {'content': '{}', 'thinking': 'not an answer'},
                                      'done_reason': 'stop', 'prompt_eval_count': 100}
        client = self.client(AsyncMock(return_value=response))
        with patch.object(local, 'MODEL_LOCK', self.lock), patch.object(local, 'is_local_chat_model', return_value=True), \
             patch.object(local.httpx, 'AsyncClient', return_value=client):
            result = local.invoke_selection(self.llm, 'synthetic')
        self.assertEqual(client.post.call_args.kwargs['json'], self.params)
        self.assertEqual(result.content, '{}')
        self.assertIsNone(result.response_metadata['load_duration'])
        self.assertEqual(result.response_metadata['prompt_eval_count'], 100)
        self.assertFalse(result.additional_kwargs)

    def test_timeout_cancels_pending_await_closes_client_and_releases_slot(self):
        cancelled = []
        async def slow(*args, **kwargs):
            try:
                await asyncio.sleep(30)
            finally:
                cancelled.append(True)
        client = self.client(AsyncMock(side_effect=slow))
        with patch.object(local, 'MODEL_LOCK', self.lock), patch.object(local, 'is_local_chat_model', return_value=True), \
             patch.object(local.httpx, 'AsyncClient', return_value=client):
            with self.assertRaises(TimeoutError):
                local.invoke_selection(self.llm, 'synthetic', timeout=.01)
        self.assertEqual(cancelled, [True])
        client.__aexit__.assert_awaited_once()
        with process_lock(self.lock) as acquired:
            self.assertTrue(acquired)
        with patch.object(local, 'MODEL_LOCK', self.lock), patch.object(local, 'is_local_chat_model', return_value=True), \
             patch.object(local.httpx, 'AsyncClient') as client:
            with self.assertRaises(local.ModelBusy):
                local.invoke_selection(self.llm, 'another request')
            client.assert_not_called()

    def test_busy_model_is_not_submitted_to_backend_queue(self):
        with process_lock(self.lock) as acquired:
            self.assertTrue(acquired)
            with patch.object(local, 'MODEL_LOCK', self.lock), patch.object(local, 'is_local_chat_model', return_value=True), \
                 patch.object(local.httpx, 'AsyncClient') as client:
                with self.assertRaises(local.ModelBusy):
                    local.invoke_selection(self.llm, 'synthetic')
                client.assert_not_called()

    def test_model_weight_change_and_unknown_revision_do_not_reuse_selection(self):
        llm = SimpleNamespace(model='gemma4:e4b', base_url='http://local')
        with patch.object(local, 'is_local_chat_model', return_value=True), \
             patch.object(local, 'local_model_revision', side_effect=['old', 'new', None]):
            before = plan_key('same', [], set(), llm, 'same')
            after = plan_key('same', [], set(), llm, 'same')
            unknown = plan_key('same', [], set(), llm, 'same')
        self.assertNotEqual(before, after)
        self.assertIsNone(unknown)

    def test_operational_failure_is_not_reported_as_missing_source(self):
        for error, expected in [(TimeoutError(), 'processing_timeout'), (local.ModelBusy(), 'model_busy')]:
            with request_metrics():
                record_model(.1, outcome='error', error=error)
                self.assertEqual(model_failure_reason(), expected)
