import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from database_db.raw_pages import read_raw_pages
from chatbot.crawled_pages import CrawledPageIndex

class SourceReadRecoveryTests(unittest.TestCase):
    def client(self,effects):
        query=Mock();query.select.return_value=query;query.eq.return_value=query
        query.execute.side_effect=effects
        return SimpleNamespace(table=lambda _:query),query

    def error(self,code):
        exc=RuntimeError('private response body must not be logged');exc.code=code
        return exc

    def test_transient_get_rechecks_current_data_once(self):
        c,q=self.client([self.error(521),SimpleNamespace(data=[{'content':'current'}])])
        with patch('database_db.raw_pages.time.sleep') as pause:
            self.assertEqual(read_raw_pages(c,'content',url='official'),[{'content':'current'}])
        self.assertEqual(q.execute.call_count,2);pause.assert_called_once_with(.15)

    def test_exhausted_or_nontransient_read_still_fails_closed(self):
        for code,attempts in ((521,2),(401,1),(403,1),(400,1),('PGRST204',1)):
            c,q=self.client([self.error(code)]*3)
            with patch('database_db.raw_pages.time.sleep'),self.assertRaises(RuntimeError):
                read_raw_pages(c,'content')
            self.assertEqual(q.execute.call_count,attempts)

    def test_failed_startup_recovery_does_not_block_or_claim_freshness(self):
        index=CrawledPageIndex(Mock());index._retry_at=1
        with patch('chatbot.crawled_pages.threading.Thread') as thread:
            self.assertEqual(index._snapshot(),[])
            self.assertEqual(index._snapshot(),[])
        self.assertIsNone(index._loaded_at)
        thread.assert_called_once();thread.return_value.start.assert_called_once()
