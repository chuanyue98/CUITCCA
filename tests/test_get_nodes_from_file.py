import os
import tempfile
import unittest

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)

import utils.llama as llama_utils


class GetNodesFromFileTest(unittest.TestCase):
    def test_loads_nodes_from_a_single_file_path(self):
        """get_nodes_from_file is called with a path to one uploaded file (e.g. from
        insert_into_index), not a directory. SimpleDirectoryReader's first
        positional/keyword arg is input_dir though -- passing a file path there
        makes it try to list a directory that doesn't exist and fail with
        'Directory <file path> does not exist.', exactly as reported against
        /index/{name}/uploadFile."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, 'note.txt')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("图书馆每天早上8点到晚上10点开放。")

            nodes = llama_utils.get_nodes_from_file(file_path)

        self.assertTrue(nodes)
        self.assertIn("图书馆", nodes[0].get_content())


if __name__ == '__main__':
    unittest.main()
