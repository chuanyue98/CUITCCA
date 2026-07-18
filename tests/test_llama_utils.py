import unittest
from unittest.mock import MagicMock, patch

import utils.llama as llama_utils

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)


class ExtractContentAfterBackslashTest(unittest.TestCase):
    def test_strips_windows_style_backslash_paths(self):
        self.assertEqual(
            llama_utils.extract_content_after_backslash("C:\\fakepath\\转专业政策.txt"),
            "转专业政策.txt",
        )

    def test_strips_posix_style_forward_slash_paths(self):
        self.assertEqual(
            llama_utils.extract_content_after_backslash(
                "/home/user/data/转专业政策.txt"
            ),
            "转专业政策.txt",
        )

    def test_plain_filename_is_unchanged(self):
        self.assertEqual(llama_utils.extract_content_after_backslash("note.txt"), "note.txt")

    def test_mixed_separators_returns_last_segment(self):
        self.assertEqual(
            llama_utils.extract_content_after_backslash("a/b\\c/d.txt"),
            "d.txt",
        )

    def test_empty_string_returns_empty_string(self):
        self.assertEqual(llama_utils.extract_content_after_backslash(""), "")

    def test_root_path_returns_empty(self):
        self.assertEqual(llama_utils.extract_content_after_backslash("/"), "")


class FormattedPairsTest(unittest.TestCase):
    def test_extracts_qa_pairs_from_single_entry(self):
        result = llama_utils.formatted_pairs(["Q: 学校几点开门？\nA: 早上8点。"])
        self.assertEqual(result, ["学校几点开门？", "早上8点。"])

    def test_extracts_multiple_qa_pairs(self):
        result = llama_utils.formatted_pairs([
            "Q: 问题1\nA: 答案1\nQ: 问题2\nA: 答案2"
        ])
        self.assertEqual(result, ["问题1", "答案1", "问题2", "答案2"])

    def test_handles_multiple_list_entries(self):
        result = llama_utils.formatted_pairs([
            "Q: 问题1\nA: 答案1",
            "Q: 问题2\nA: 答案2",
        ])
        self.assertEqual(result, ["问题1", "答案1", "问题2", "答案2"])

    def test_returns_empty_list_for_empty_input(self):
        result = llama_utils.formatted_pairs([])
        self.assertEqual(result, [])

    def test_handles_whitespace_only_content(self):
        result = llama_utils.formatted_pairs(["Q:   \nA:   "])
        self.assertEqual(result, [])

    def test_handles_no_q_a_prefix(self):
        result = llama_utils.formatted_pairs(["plain text without prefix"])
        self.assertEqual(result, ["plain text without prefix"])


class BuildQaGenerationPromptTest(unittest.TestCase):
    def test_custom_prompt_is_used_as_is(self):
        result = llama_utils.build_qa_generation_prompt("只生成关于奖学金的问答对")
        self.assertEqual(result, "只生成关于奖学金的问答对")

    def test_falls_back_to_default_instruction_when_none(self):
        result = llama_utils.build_qa_generation_prompt(None)
        self.assertIn("请根据以下内容生成尽可能多的问答对", result)

    def test_falls_back_to_default_instruction_when_empty_string(self):
        result = llama_utils.build_qa_generation_prompt("")
        self.assertIn("请根据以下内容生成尽可能多的问答对", result)


class GetNodesFromFileTest(unittest.TestCase):
    @patch('utils.llama.SimpleDirectoryReader')
    @patch('utils.llama.SentenceSplitter')
    def test_returns_nodes_from_file(self, mock_splitter_cls, mock_reader_cls):
        mock_doc = MagicMock()
        mock_doc.id_ = '/path/to/file.txt'
        mock_reader = MagicMock()
        mock_reader.load_data.return_value = [mock_doc]
        mock_reader_cls.return_value = mock_reader

        mock_splitter = MagicMock()
        fake_nodes = [MagicMock(), MagicMock()]
        mock_splitter.get_nodes_from_documents.return_value = fake_nodes
        mock_splitter_cls.from_defaults.return_value = mock_splitter

        result = llama_utils.get_nodes_from_file('/path/to/file.txt')

        mock_reader_cls.assert_called_once_with(
            input_files=['/path/to/file.txt'], filename_as_id=True
        )
        mock_splitter.get_nodes_from_documents.assert_called_once_with([mock_doc])
        self.assertEqual(result, fake_nodes)
        self.assertEqual(mock_doc.id_, 'file.txt')


class GenerateQueryEngineToolsTest(unittest.TestCase):
    def test_creates_tools_from_indexes(self):
        index1 = MagicMock()
        index1.as_query_engine.return_value = MagicMock()
        index1.summary = 'Index 1 summary'

        index2 = MagicMock()
        index2.as_query_engine.return_value = MagicMock()
        index2.summary = 'Index 2 summary'

        with patch('utils.llama.QueryEngineTool') as mock_tool_cls:
            result = llama_utils.generate_query_engine_tools([index1, index2])

        self.assertEqual(len(result), 2)
        self.assertEqual(mock_tool_cls.from_defaults.call_count, 2)

    def test_returns_empty_list_for_no_indexes(self):
        result = llama_utils.generate_query_engine_tools([])
        self.assertEqual(result, [])

    def test_falls_back_to_index_id_when_summary_attribute_missing(self):
        # A freshly created index (create_empty_index) never gets a .summary
        # attribute set until loadAllIndexes()/set_summary() runs, so a plain
        # object without that attribute reproduces the real gap -- MagicMock
        # would auto-vivify .summary and hide the bug.
        class BareIndex:
            def __init__(self):
                self.index_id = 'bare-index'
                self.vector_store = MagicMock()

            def as_query_engine(self, **kwargs):
                return MagicMock()

            def as_retriever(self, **kwargs):
                return MagicMock()

        index = BareIndex()

        with patch('utils.llama.QueryEngineTool') as mock_tool_cls:
            llama_utils.generate_query_engine_tools([index])

        _, kwargs = mock_tool_cls.from_defaults.call_args
        self.assertEqual(kwargs['description'], '知识库索引: bare-index')

    def test_passes_correct_arguments_to_query_engine(self):
        index = MagicMock()
        index.summary = 'Test summary'

        with patch('utils.llama.Prompts') as mock_prompts:
            mock_prompts.QA_PROMPT.value = 'qa prompt'
            mock_prompts.REFINE_PROMPT.value = 'refine prompt'
            with patch('utils.llama.QueryEngineTool'), \
                 patch('utils.llama.RetrieverQueryEngine') as mock_retriever_query_engine:
                llama_utils.generate_query_engine_tools([index])

        # HYBRID_RETRIEVAL_ENABLED 默认关闭：build_retriever_for_index 直接
        # 退化成 index.as_retriever(similarity_top_k=...)。
        index.as_retriever.assert_called_once_with(similarity_top_k=5)
        mock_retriever_query_engine.from_args.assert_called_once_with(
            retriever=index.as_retriever.return_value,
            streaming=False,
            text_qa_template='qa prompt',
            refine_template='refine prompt',
            node_postprocessors=[],
        )


if __name__ == '__main__':
    unittest.main()
