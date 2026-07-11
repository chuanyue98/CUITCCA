import unittest
from unittest.mock import patch

import configs.llm_predictor as llm_predictor
import configs.load_env as env_config
from llama_index.llms.openai_like import OpenAILike

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)


class BuildLlmTest(unittest.TestCase):
    def test_reads_current_env_config_values_at_call_time(self):
        with patch.object(env_config, 'openai_api_key', 'sk-test'), \
             patch.object(env_config, 'openai_api_base', 'https://example.test/v1'), \
             patch.object(env_config, 'openai_model', 'sensenova-6.7-flash-lite'):
            llm = llm_predictor.build_llm()

        self.assertIsInstance(llm, OpenAILike)
        self.assertEqual(llm.model, 'sensenova-6.7-flash-lite')
        self.assertEqual(llm.api_base, 'https://example.test/v1')
        self.assertEqual(llm.api_key, 'sk-test')
        self.assertTrue(llm.is_chat_model)
        self.assertGreater(llm.context_window, 0)

    def test_picks_up_updated_config_on_a_fresh_call(self):
        """build_llm must read live config, not a value captured once at import time
        (the existing openai_api_key `from x import y` pattern goes stale after
        /manage/env updates configs.load_env's globals -- build_llm must not repeat that)."""
        with patch.object(env_config, 'openai_model', 'model-one'):
            llm1 = llm_predictor.build_llm()
        with patch.object(env_config, 'openai_model', 'model-two'):
            llm2 = llm_predictor.build_llm()

        self.assertEqual(llm1.model, 'model-one')
        self.assertEqual(llm2.model, 'model-two')

    def test_unknown_model_gets_a_safe_default_context_window(self):
        with patch.object(env_config, 'openai_model', 'some-unreleased-model'):
            llm = llm_predictor.build_llm()
        self.assertGreater(llm.context_window, 0)


if __name__ == '__main__':
    unittest.main()
