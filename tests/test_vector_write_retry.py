import unittest
from database_db.vector_store import upsert_vectors


class VectorWriteRetryTests(unittest.TestCase):
    def test_timeout_splits_without_losing_or_reassigning_ids(self):
        class TimeoutError(Exception):
            code = '57014'
        class Client:
            def __init__(self): self.saved = []; self.calls = []
            def table(self, name): return self
            def upsert(self, rows): self.rows = rows; return self
            def execute(self):
                self.calls.append(len(self.rows))
                if len(self.rows) > 2: raise TimeoutError('statement timeout')
                self.saved.extend(r['id'] for r in self.rows)
        client = Client()
        upsert_vectors(client, [{'id': i} for i in range(7)])
        self.assertEqual(client.saved, list(range(7)))
        self.assertGreater(len(client.calls), 1)

    def test_permission_error_is_not_retried(self):
        class Client:
            def table(self, name): return self
            def upsert(self, rows): return self
            def execute(self): raise PermissionError('not authorized')
        with self.assertRaises(PermissionError):
            upsert_vectors(Client(), [{'id': 1}])


if __name__ == '__main__':
    unittest.main()
