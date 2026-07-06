import unittest

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)

import utils.llama as llama_utils


class ExtractContentAfterBackslashTest(unittest.TestCase):
    def test_strips_windows_style_backslash_paths(self):
        """Existing case: some browsers report file.filename as a full Windows
        path like C:\\fakepath\\file.txt."""
        self.assertEqual(
            llama_utils.extract_content_after_backslash("C:\\fakepath\\转专业政策.txt"),
            "转专业政策.txt",
        )

    def test_strips_posix_style_forward_slash_paths(self):
        """get_nodes_from_file assigns doc.id_ to the absolute file path on disk,
        which on Linux uses forward slashes -- the old implementation only split
        on backslash, so on Linux doc_id ended up as the full absolute path
        instead of just the filename."""
        self.assertEqual(
            llama_utils.extract_content_after_backslash(
                "/home/cy/github/chuanyue98/CUITCCA/backend/app/../../data/temp/转专业政策.txt"
            ),
            "转专业政策.txt",
        )

    def test_plain_filename_is_unchanged(self):
        self.assertEqual(llama_utils.extract_content_after_backslash("note.txt"), "note.txt")


if __name__ == '__main__':
    unittest.main()
