import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "desk365_mcp" / "config.py"


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.dotenv = patch("dotenv.load_dotenv")
        self.load_dotenv = self.dotenv.start()
        self.addCleanup(self.dotenv.stop)

    def load_config(self):
        # Execute import-time initialization without caching config in sys.modules.
        return runpy.run_path(str(CONFIG_PATH))

    def test_import_initializes_config_from_environment(self):
        os.environ.update(API_KEY="test-api-key", UNRELATED="excluded")

        config = self.load_config()

        self.assertEqual(config["ENV_CONFIG"], {"API_KEY": "test-api-key"})
        self.load_dotenv.assert_called_once_with()

    def test_missing_api_key_raises_with_setup_guidance(self):
        with self.assertRaises(ValueError) as error:
            self.load_config()

        message = str(error.exception)
        self.assertIn("Missing required environment variables: API_KEY", message)
        self.assertIn(str(PROJECT_ROOT / ".env"), message)
        self.assertIn("or as explicit environment variables.", message)

    def test_empty_api_key_is_rejected(self):
        os.environ["API_KEY"] = ""

        with self.assertRaisesRegex(ValueError, "Missing required environment variables: API_KEY"):
            self.load_config()

    def test_dotenv_is_loaded_before_validation(self):
        def populate_environment():
            os.environ["API_KEY"] = "dotenv-api-key"

        self.load_dotenv.side_effect = populate_environment

        config = self.load_config()

        self.assertEqual(config["ENV_CONFIG"], {"API_KEY": "dotenv-api-key"})
        self.load_dotenv.assert_called_once_with()

    def test_function_reads_current_environment_on_each_call(self):
        os.environ["API_KEY"] = "initial-api-key"
        config = self.load_config()
        os.environ["API_KEY"] = "updated-api-key"

        result = config["_get_env_config"]()

        self.assertEqual(result, {"API_KEY": "updated-api-key"})
        self.assertEqual(config["ENV_CONFIG"], {"API_KEY": "initial-api-key"})
        self.assertEqual(self.load_dotenv.call_count, 2)

    def test_reports_all_missing_required_variables(self):
        os.environ["API_KEY"] = "test-api-key"
        config = self.load_config()
        config["REQUIRED_ENV_VARS"].append("SECOND_REQUIRED_VAR")
        del os.environ["API_KEY"]

        with self.assertRaisesRegex(
            ValueError,
            "Missing required environment variables: API_KEY, SECOND_REQUIRED_VAR",
        ):
            config["_get_env_config"]()


if __name__ == "__main__":
    unittest.main()
