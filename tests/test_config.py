import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from desk365_mcp import config
from desk365_mcp.main import parse_args


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.dotenv = patch.object(config, "load_dotenv")
        self.load_dotenv = self.dotenv.start()
        self.addCleanup(self.dotenv.stop)

    def test_reads_config_from_environment(self):
        os.environ.update(API_KEY="test-api-key", UNRELATED="excluded")

        result = config.get_env_config()

        self.assertEqual(result, {"API_KEY": "test-api-key"})

    def test_no_stage_loads_bare_env_file(self):
        os.environ["API_KEY"] = "test-api-key"

        config.get_env_config()

        self.load_dotenv.assert_called_once_with(config.PROJECT_ROOT / ".env")

    def test_stage_loads_stage_env_file(self):
        os.environ["API_KEY"] = "test-api-key"
        with tempfile.TemporaryDirectory() as tmp, patch.object(config, "PROJECT_ROOT", Path(tmp)):
            (Path(tmp) / "dev.env").touch()

            config.get_env_config("dev")

            self.load_dotenv.assert_called_once_with(Path(tmp) / "dev.env")

    def test_missing_stage_env_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(config, "PROJECT_ROOT", Path(tmp)):
            with self.assertRaisesRegex(FileNotFoundError, 'stage "beta"'):
                config.get_env_config("beta")

        self.load_dotenv.assert_not_called()

    def test_missing_api_key_raises_with_setup_guidance(self):
        with self.assertRaises(ValueError) as error:
            config.get_env_config()

        message = str(error.exception)
        self.assertIn("Missing required environment variables: API_KEY.", message)
        self.assertIn(str(config.PROJECT_ROOT / ".env"), message)
        self.assertIn("or as explicit environment variables.", message)

    def test_empty_api_key_is_rejected(self):
        os.environ["API_KEY"] = ""

        with self.assertRaisesRegex(ValueError, "Missing required environment variables: API_KEY"):
            config.get_env_config()

    def test_dotenv_is_loaded_before_validation(self):
        def populate_environment(_path):
            os.environ["API_KEY"] = "dotenv-api-key"

        self.load_dotenv.side_effect = populate_environment

        self.assertEqual(config.get_env_config(), {"API_KEY": "dotenv-api-key"})

    def test_reports_all_missing_required_variables(self):
        with patch.object(config, "REQUIRED_ENV_VARS", ["API_KEY", "SECOND_REQUIRED_VAR"]):
            with self.assertRaisesRegex(
                ValueError,
                "Missing required environment variables: API_KEY, SECOND_REQUIRED_VAR",
            ):
                config.get_env_config()


class ParseArgsTests(unittest.TestCase):
    def test_stage_defaults_to_none(self):
        self.assertIsNone(parse_args([]).stage)

    def test_stage_is_parsed(self):
        self.assertEqual(parse_args(["--stage", "dev"]).stage, "dev")


if __name__ == "__main__":
    unittest.main()
