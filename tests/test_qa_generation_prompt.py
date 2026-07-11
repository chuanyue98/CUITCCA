import unittest

import utils.llama as llama_utils

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)


class BuildQaGenerationPromptTest(unittest.TestCase):
    def test_custom_prompt_is_used_as_is(self):
        result = llama_utils.build_qa_generation_prompt("只生成关于奖学金的问答对")
        self.assertEqual(result, "只生成关于奖学金的问答对")

    def test_falls_back_to_a_default_instruction_when_no_custom_prompt(self):
        result = llama_utils.build_qa_generation_prompt(None)
        self.assertTrue(result)
        self.assertIsInstance(result, str)

    def test_never_embeds_document_content(self):
        """The old behavior formatted the *entire uploaded file* into the prompt
        via _SAFE_PROMPT_TEMPLATE.format(contents), which generate_qa_batched then
        prepended to every single chunk's LLM call -- resending the whole document
        once per chunk. build_qa_generation_prompt must only ever return an
        instruction, never document content, regardless of input."""
        huge_document_text = "招生简章内容 " * 5000
        result = llama_utils.build_qa_generation_prompt(None)
        self.assertNotIn(huge_document_text, result)
        self.assertLess(len(result), 200)


if __name__ == '__main__':
    unittest.main()
