"""Model/provider switches must preserve structured evidence selection."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock

from chatbot import llm_runtime as runtime
from chatbot.model_plan_cache import plan_key


SCHEMA = {'type': 'object', 'properties': {'mode': {'enum': ['answer']}},
          'required': ['mode'], 'additionalProperties': False}


class ModelRuntimeTests(unittest.TestCase):
    def selector(self, **kwargs):
        return runtime.VLLMSelector('http://127.0.0.1:8000/v1', 'served-gemma4',
                                     api_key='fixture-secret', **kwargs)

    def test_translation_preserves_schema_tokens_nonstream_and_no_thought(self):
        base = self.selector()
        selector = base.model_copy(update={'format': SCHEMA, 'num_predict': 100, 'temperature': 0})
        reply = Mock(status_code=200)
        reply.json.return_value = {'choices': [{'finish_reason': 'stop', 'message': {
            'content': '{"mode":"answer"}', 'reasoning': 'not factual output'}}],
            'usage': {'prompt_tokens': 18, 'completion_tokens': 6}}
        with patch.object(runtime.requests, 'post', return_value=reply) as post:
            result = selector.invoke('choose source IDs', stream=False)
        args, opts = post.call_args
        self.assertEqual(args[0], 'http://127.0.0.1:8000/v1/chat/completions')
        body = opts['json']
        self.assertEqual(body['response_format']['json_schema']['schema'], SCHEMA)
        self.assertEqual(body['max_tokens'], 100)
        self.assertFalse(body['stream'])
        self.assertFalse(body['chat_template_kwargs']['enable_thinking'])
        self.assertNotIn('format', body)
        self.assertNotIn('num_predict', body)
        self.assertEqual(opts['timeout'], (5, 120))
        self.assertFalse(opts['allow_redirects'])
        self.assertEqual(opts['headers']['Authorization'], 'Bearer fixture-secret')
        self.assertEqual(result.content, '{"mode":"answer"}')
        self.assertEqual(result.response_metadata['eval_count'], 6)
        self.assertIsNone(base.format)
        self.assertNotIn('fixture-secret', repr(selector))

    def test_length_finish_is_preserved_for_planner_to_reject(self):
        reply = Mock(status_code=200)
        reply.json.return_value = {'choices': [{'finish_reason': 'length',
                                    'message': {'content': '{"mode":'}}]}
        with patch.object(runtime.requests, 'post', return_value=reply):
            result = self.selector(format=SCHEMA).invoke('fixture')
        self.assertEqual(result.response_metadata['done_reason'], 'length')

    def test_backend_error_body_never_in_application_exception(self):
        reply = Mock(status_code=401, text='fixture-secret')
        with patch.object(runtime.requests, 'post', return_value=reply):
            with self.assertRaisesRegex(RuntimeError, '^vLLM 근거 선택 요청 실패$'):
                self.selector(format=SCHEMA).invoke('fixture')

    def test_tool_or_reasoning_only_output_is_not_a_fact(self):
        for message in ({'content': None, 'reasoning': 'invented'},
                        {'content': '{}', 'tool_calls': [{'id': 'x'}]},
                        {'content': '{}', 'refusal': 'refused'}):
            reply = Mock(status_code=200)
            reply.json.return_value = {'choices': [{'message': message}]}
            with patch.object(runtime.requests, 'post', return_value=reply):
                with self.assertRaises(ValueError):
                    self.selector(format=SCHEMA).invoke('fixture')

    def test_missing_schema_never_sends_unconstrained_prompt(self):
        with patch.object(runtime.requests, 'post') as post:
            with self.assertRaises(ValueError):
                self.selector().invoke('fixture')
        post.assert_not_called()

    def test_url_configuration_rejects_embedded_credentials(self):
        for url in ('', 'file:///x', 'http://user:pass@host/v1',
                    'https://host/v1?api_key=secret', 'https://host/v1#secret'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                runtime.vllm_base_url(url)
        self.assertEqual(runtime.vllm_base_url('http://host:8000/'), 'http://host:8000/v1')

    def test_vllm_factory_and_status_never_need_ollama(self):
        reply = Mock(status_code=200)
        reply.json.return_value = {'data': [{'id': 'served-gemma4'}]}
        with patch.multiple(runtime.config, LLM_PROVIDER='vllm',
                            VLLM_BASE_URL='http://127.0.0.1:8000/v1',
                            VLLM_MODEL='served-gemma4', VLLM_API_KEY='fixture-secret'):
            with patch.object(runtime, 'get_ollama_status') as ollama, \
                 patch.object(runtime.requests, 'get', return_value=reply):
                self.assertIsInstance(runtime.create_llm(), runtime.VLLMSelector)
                status = runtime.get_llm_status()
                ollama.assert_not_called()
        self.assertTrue(status['model_ready'])
        self.assertNotIn('fixture-secret', json.dumps(status))

    def test_wrong_model_and_auth_failure_are_not_ready(self):
        for code in (200, 401, 307):
            reply = Mock(status_code=code)
            reply.json.return_value = {'data': [{'id': 'different-model'}]}
            with patch.multiple(runtime.config, LLM_PROVIDER='vllm',
                                VLLM_BASE_URL='http://host/v1', VLLM_MODEL='expected'):
                with patch.object(runtime.requests, 'get', return_value=reply):
                    self.assertFalse(runtime.get_llm_status()['model_ready'])

    def test_provider_endpoint_and_model_switch_invalidate_plan_cache(self):
        a = runtime.VLLMSelector('http://a/v1', 'gemma4')
        b = runtime.VLLMSelector('http://b/v1', 'gemma4')
        c = runtime.VLLMSelector('http://a/v1', 'gemma2')
        keys = [plan_key('same', [], set(), m, 'same') for m in (a, b, c)]
        self.assertEqual(len(set(keys)), 3)

    def test_local_gemma4_requests_no_thinking_and_configured_context(self):
        with patch.multiple(runtime.config, LLM_PROVIDER='ollama', OLLAMA_MODEL='gemma4:e4b'):
            llm = runtime.create_llm()
        self.assertFalse(llm.reasoning)
        self.assertEqual(llm.num_ctx, runtime.config.OLLAMA_NUM_CTX)


if __name__ == '__main__':
    unittest.main()
