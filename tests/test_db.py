import os
import tempfile
import unittest

import tests._pathsetup  # noqa: F401
from utils import db


class DbTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, 'test.db')
        db.init_db(self.db_path)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_init_db_creates_tables(self):
        conn = db._connect(self.db_path)
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        self.assertTrue({'access_stats', 'ip_visits', 'endpoint_visits', 'feedback'}.issubset(tables))

    def test_flush_and_load_stats_roundtrip(self):
        stats = {
            'total_visits': 5,
            'user_visits': {'1.2.3.4': 3, '5.6.7.8': 2},
            'endpoint_visits': {'/graph/query': 4, '/': 1},
        }
        db.flush_stats(self.db_path, stats)
        loaded = db.load_stats(self.db_path)
        self.assertEqual(loaded['total_visits'], 5)
        self.assertEqual(loaded['user_visits']['1.2.3.4'], 3)
        self.assertEqual(loaded['endpoint_visits']['/graph/query'], 4)

    def test_save_and_list_feedback(self):
        db.save_feedback(self.db_path, '192.168.1.1', 'a@b.com', 'hello world')
        db.save_feedback(self.db_path, '192.168.1.2', None, 'no email here')
        entries = db.list_feedback(self.db_path, limit=10)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]['message'], 'no email here')  # most recent first
        self.assertIsNone(entries[0]['email'])
        self.assertEqual(entries[1]['client_ip'], '192.168.1.1')

    def test_record_visit_creates_and_increments(self):
        db.record_visit(self.db_path, '10.0.0.1', '/graph/query')
        loaded = db.load_stats(self.db_path)
        self.assertEqual(loaded['user_visits']['10.0.0.1'], 1)
        self.assertEqual(loaded['endpoint_visits']['/graph/query'], 1)

        db.record_visit(self.db_path, '10.0.0.1', '/graph/query')
        loaded = db.load_stats(self.db_path)
        self.assertEqual(loaded['user_visits']['10.0.0.1'], 2)
        self.assertEqual(loaded['endpoint_visits']['/graph/query'], 2)


if __name__ == '__main__':
    unittest.main()
