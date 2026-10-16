"""Private host configuration is shared by worktrees, not by projects."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import dev_config as config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "settings.json"
        self.key = sorted(config.ALLOWED_KEYS)[0]
        env = patch.dict(os.environ, {"DEV_CONFIG_FILE": str(self.path)}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding="utf-8")
        self.path.chmod(0o600)

    def test_load_and_environment_override(self):
        self.write({self.key: "private-value"})
        config.load_config()
        self.assertEqual(os.environ[self.key], "private-value")
        os.environ[self.key] = "explicit-override"
        config.load_config()
        self.assertEqual(os.environ[self.key], "explicit-override")

    def test_missing_default_optional_but_explicit_required(self):
        with self.assertRaises(config.ConfigError):
            config.load_config()
        os.environ.pop("DEV_CONFIG_FILE")
        os.environ["XDG_CONFIG_HOME"] = str(self.root)
        self.assertEqual(config.read_config()[1], {})

    def test_default_is_project_scoped(self):
        os.environ.pop("DEV_CONFIG_FILE")
        os.environ["XDG_CONFIG_HOME"] = str(self.root)
        folder = self.root / "project-dev"
        folder.mkdir(mode=0o700)
        other = folder / "unrelated-project.json"
        other.write_text(json.dumps({self.key: "other-secret"}))
        other.chmod(0o600)
        self.assertEqual(config.read_config()[1], {})
        self.path = folder / (config.PROJECT + ".json")
        self.write({self.key: "this-project"})
        self.assertEqual(config.read_config()[1], {self.key: "this-project"})

    def test_invalid_values_rejected_without_value_disclosure(self):
        for values in ({self.key: 42}, {"FLASK_ENV": "production"}, ["secret-sentinel"], {self.key: "a\0b"}):
            with self.subTest(values=type(values).__name__):
                self.write(values)
                with self.assertRaises(config.ConfigError) as error:
                    config.load_config()
                self.assertNotIn("secret-sentinel", str(error.exception))
                self.assertNotIn(self.key, os.environ)

    def test_invalid_json_does_not_echo_secret(self):
        self.path.write_text('{"secret-sentinel":', encoding="utf-8")
        self.path.chmod(0o600)
        with self.assertRaises(config.ConfigError) as error:
            config.load_config()
        self.assertNotIn("secret-sentinel", str(error.exception))

    def test_permissions_and_symlinks_rejected(self):
        self.write({self.key: "secret-sentinel"})
        self.path.chmod(0o644)
        with self.assertRaises(config.ConfigError):
            config.load_config()
        self.path.chmod(0o600)
        link = self.root / "link.json"
        link.symlink_to(self.path)
        os.environ["DEV_CONFIG_FILE"] = str(link)
        with self.assertRaises(config.ConfigError):
            config.load_config()

    def test_disabled_does_not_read_invalid_config(self):
        os.environ["DEV_CONFIG_DISABLED"] = "1"
        self.assertEqual(config.load_config(), (None, []))

    def test_check_redacts_and_run_receives_config(self):
        self.write({self.key: "secret-sentinel"})
        script = str(Path(config.__file__).resolve())
        result = subprocess.run([sys.executable, script, "check"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.key, result.stdout)
        self.assertNotIn("secret-sentinel", result.stdout + result.stderr)
        result = subprocess.run([sys.executable, script, "run", "--", sys.executable, "-c",
                                 f"import os; assert os.environ[{self.key!r}] == 'secret-sentinel'"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
