import unittest
from unittest.mock import Mock
from database_db.database import Database


class PageReadRetryTests(unittest.TestCase):
    def test_timeout_retries_the_same_offset_without_losing_rows(self):
        db = object.__new__(Database)
        db.client = Mock()
        query = db.client.table.return_value.select.return_value.order.return_value
        query.range.return_value.execute.side_effect = [
            RuntimeError('canceling statement due to statement timeout'),
            Mock(data=[{'url': str(i)} for i in range(500)]),
            Mock(data=[{'url': 'last'}]),
        ]
        rows = db._all_rows('raw_pages', 'url')
        self.assertEqual(len(rows), 501)
        self.assertEqual([call.args for call in query.range.call_args_list], [(0, 999), (0, 499), (500, 999)])

    def test_permission_errors_are_not_retried(self):
        db = object.__new__(Database)
        db.client = Mock()
        query = db.client.table.return_value.select.return_value.order.return_value
        query.range.return_value.execute.side_effect = RuntimeError('permission denied')
        with self.assertRaises(RuntimeError):
            db._all_rows('raw_pages', 'url')
        self.assertEqual(query.range.call_count, 1)
