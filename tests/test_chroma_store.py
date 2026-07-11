import tempfile
import unittest

import tests._pathsetup  # noqa: F401


class ChromaStoreBasicTest(unittest.TestCase):
    def setUp(self):
        import chromadb
        self._tmp_dir = tempfile.mkdtemp()
        self.client = chromadb.PersistentClient(path=self._tmp_dir)

    def tearDown(self):
        self.client.clear_system_cache()

    def test_create_and_list_collections(self):
        self.client.get_or_create_collection('test-col')
        names = [c.name for c in self.client.list_collections()]
        self.assertIn('test-col', names)

    def test_delete_collection(self):
        self.client.get_or_create_collection('to-delete')
        self.client.delete_collection('to-delete')
        names = [c.name for c in self.client.list_collections()]
        self.assertNotIn('to-delete', names)

    def test_metadata_on_collection(self):
        col = self.client.get_or_create_collection('meta-test')
        col.modify(metadata={"summary": "test summary"})
        col_loaded = self.client.get_collection('meta-test')
        self.assertEqual(col_loaded.metadata, {"summary": "test summary"})


if __name__ == '__main__':
    unittest.main()
