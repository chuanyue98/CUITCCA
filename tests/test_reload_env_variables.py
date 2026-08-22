import os
import tempfile
import unittest
from unittest.mock import patch

import configs.load_env as env_config

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)


class ReloadEnvVariablesOverrideTest(unittest.TestCase):
    def test_updates_an_already_set_env_var(self):
        """load_dotenv() defaults to override=False, so once OPENAI_API_KEY is set
        at process startup, a later /manage/env update that rewrites the .env file
        and calls reload_env_variables() would silently keep serving the old key --
        this must actually pick up the new value."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = os.path.join(tmp_dir, '.env')
            with open(env_path, 'w') as f:
                f.write("OPENAI_API_KEY=new-key-from-file\n")

            with patch.dict(os.environ, {'OPENAI_API_KEY': 'stale-key-already-in-environ'}), \
                 patch.object(env_config, 'ENV_PATH', env_path):
                env_config.reload_env_variables()

                self.assertEqual(os.environ['OPENAI_API_KEY'], 'new-key-from-file')
                self.assertEqual(env_config.openai_api_key, 'new-key-from-file')


if __name__ == '__main__':
    unittest.main()
