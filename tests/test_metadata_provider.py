import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from processor.metadata_tagger import MetadataTagger, ensure_metadata
from chatbot.llm_runtime import VLLMSelector


def chunk(i=0):
    return SimpleNamespace(url='https://www.saha.go.kr/fixture',title='공식 원문',
         content='공식 안내에 신청 절차가 있습니다.',category='민원',sub_category='',
         chunk_index=i,total_chunks=2,chunk_id='fixture'+str(i),department_hint='')


class TaggingProviderTests(unittest.TestCase):
    def test_vllm_single_and_batch_use_provider_schema_without_ollama(self):
        model=VLLMSelector('http://127.0.0.1:8000/v1','served-gemma4')
        reply=Mock(status_code=200)
        meta={'service_type':'민원','department':None,'target_audience':[],
              'keywords':['신청'],'summary':'신청 안내','has_deadline':False,'has_contact_info':False}
        reply.json.side_effect=[{'choices':[{'message':{'content':json.dumps(meta)},'finish_reason':'stop'}]},
             {'choices':[{'message':{'content':json.dumps([meta,meta])},'finish_reason':'stop'}]}]
        with patch('processor.metadata_tagger.create_llm',return_value=model), \
             patch('chatbot.llm_runtime.requests.post',return_value=reply) as post:
            tagger=MetadataTagger()
            single=tagger.tag(chunk())
            batch=tagger.tag_batch([chunk(),chunk(1)])
        self.assertEqual(single['url'],chunk().url)
        self.assertEqual(len(batch),2)
        calls=post.call_args_list
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0].kwargs['json']['response_format']['json_schema']['schema']['type'],'object')
        self.assertEqual(calls[1].kwargs['json']['response_format']['json_schema']['schema']['type'],'array')
        self.assertEqual(calls[0].kwargs['json']['max_tokens'],1000)
        self.assertFalse(calls[0].kwargs['json']['chat_template_kwargs']['enable_thinking'])

    def test_tags_cannot_override_source_identity(self):
        original=chunk()
        tagged=ensure_metadata({'url':'https://wrong.invalid','title':'invented',
             'chunk_index':99,'total_chunks':99,'category':'invented','unknown':'invented'},original)
        for key in ('url','title','category','chunk_index','total_chunks'):
            self.assertEqual(tagged[key],getattr(original,key))
        self.assertNotIn('unknown',tagged)

    def test_unavailable_model_preserves_raw_metadata_and_keywords(self):
        with patch('processor.metadata_tagger.create_llm',side_effect=ValueError('fixture-secret')):
            with self.assertLogs('processor.metadata_tagger',level='WARNING') as logs:
                tagger=MetadataTagger()
            result=tagger.tag(chunk())
        self.assertNotIn('fixture-secret',' '.join(logs.output))
        self.assertEqual(result['url'],chunk().url)
        self.assertTrue(result['keywords'])

    def test_backend_error_uses_raw_fallback_without_auth_log(self):
        model=Mock()
        model.model_copy.return_value=model
        model.invoke.side_effect=RuntimeError('fixture-secret')
        with patch('processor.metadata_tagger.create_llm',return_value=model):
            tagger=MetadataTagger()
            with self.assertLogs('processor.metadata_tagger',level='WARNING') as logs:
                result=tagger.tag(chunk())
        self.assertNotIn('fixture-secret',' '.join(logs.output))
        self.assertEqual(result['url'],chunk().url)


if __name__=='__main__':unittest.main()
