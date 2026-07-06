import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)

import utils.llama as llama_utils


class GenerateQaBatchedUsesConfiguredLlmTest(unittest.TestCase):
    def test_uses_settings_llm_instead_of_a_hardcoded_openai_client(self):
        """generate_qa_batched used to call `OpenAI().acomplete(...)` directly,
        which always talks to the real OpenAI API (default model, default base_url)
        regardless of what OPENAI_API_BASE/OPENAI_MODEL are configured to. It must
        go through Settings.llm so switching providers (e.g. to SenseNova) actually
        takes effect here too."""
        fake_splitter = MagicMock()
        fake_splitter.split_text.return_value = ['chunk-1']

        fake_response = MagicMock(text='Q: foo\nA: bar')
        fake_llm = MagicMock()
        fake_llm.acomplete = AsyncMock(return_value=fake_response)

        with patch.object(llama_utils, 'SentenceSplitter', return_value=fake_splitter), \
             patch.object(llama_utils, 'Settings') as mock_settings:
            mock_settings.llm = fake_llm
            result = self._run(llama_utils.generate_qa_batched('some long text'))

        fake_llm.acomplete.assert_awaited_once()
        self.assertEqual(result, ['Q: foo\nA: bar'])

    @staticmethod
    def _run(coro):
        import asyncio
        return asyncio.run(coro)


if __name__ == '__main__':
    unittest.main()
