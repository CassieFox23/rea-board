import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import conf  # noqa: E402

PULL = os.path.join(HERE, "pull.py")


class ConfTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="rea-conf-")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.file = os.path.join(self.d, "over.json")

    def use(self, text=None):
        if text is not None:
            with open(self.file, "w", encoding="utf-8") as fh:
                fh.write(text)
        env = mock.patch.dict(os.environ, {"REA_BOARD_CONFIG": self.file})
        env.start()
        self.addCleanup(env.stop)

    def test_with_no_config_file_the_defaults_apply(self):
        self.use()
        self.assertEqual(conf.repo(), "morluto/rea")
        self.assertEqual(conf.maintainers(), ["morluto", "N0zoM1z0", "kaoru0822-kitauji", "baron"])
        self.assertEqual(conf.bot_names(), ["coderabbitai", "github-actions", "chatgpt-codex-connector", "greptile-apps", "cubic-dev-ai"])
        self.assertEqual(conf.plan_authors(), ["matbrgz"])
        self.assertEqual(conf.unsorted_labels(), ["triage"])
        self.assertEqual(conf.data_dir(), os.path.join(HERE, "data"))
        self.assertIsNone(conf.mirror())

    def test_main_since_defaults_to_ninety_days_back(self):
        self.use()

        class Fixed(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)

        with mock.patch.object(conf, "datetime", Fixed):
            self.assertEqual(conf.main_since(), "2026-08-16")

    def test_a_file_overrides_what_it_names_and_leaves_the_rest(self):
        self.use('{"maintainers": ["ann"], "plan_authors": [], "unsorted_labels": ["new"], '
                 '"bot_names": ["robo"], "mirror": "/srv/rea.git", "main_since": "2026-01-02", "data_dir": "/srv/data"}')
        self.assertEqual(conf.maintainers(), ["ann"])
        self.assertEqual(conf.plan_authors(), [])
        self.assertEqual(conf.unsorted_labels(), ["new"])
        self.assertEqual(conf.bot_names(), ["robo"])
        self.assertEqual(conf.mirror(), "/srv/rea.git")
        self.assertEqual(conf.main_since(), "2026-01-02")
        self.assertEqual(conf.data_dir(), "/srv/data")
        self.use('{"maintainers": ["ann"]}')
        self.assertEqual(conf.repo(), "morluto/rea")
        self.assertEqual(conf.bot_names(), ["coderabbitai", "github-actions", "chatgpt-codex-connector", "greptile-apps", "cubic-dev-ai"])

    def test_a_null_value_means_the_default_and_an_unknown_key_is_ignored(self):
        self.use('{"maintainers": null, "mirror": null, "data_dir": null, "main_since": null, "colour": "red"}')
        self.assertEqual(conf.maintainers(), ["morluto", "N0zoM1z0", "kaoru0822-kitauji", "baron"])
        self.assertIsNone(conf.mirror())
        self.assertEqual(conf.data_dir(), os.path.join(HERE, "data"))

    def test_a_relative_data_folder_is_in_the_repo_and_a_home_one_is_expanded(self):
        self.use('{"data_dir": "out/board"}')
        self.assertEqual(conf.data_dir(), os.path.join(HERE, "out", "board"))
        self.use('{"data_dir": "~/board-data", "mirror": "~/rea.git"}')
        with mock.patch.dict(os.environ, {"HOME": self.d}):
            self.assertEqual(conf.data_dir(), os.path.join(self.d, "board-data"))
            self.assertEqual(conf.mirror(), os.path.join(self.d, "rea.git"))

    def test_a_repo_setting_stops_it_since_the_board_is_for_rea_only(self):
        self.use('{"repo": "someone/else"}')
        with self.assertRaises(SystemExit) as cm:
            conf.repo()
        self.assertIn("morluto/rea only", str(cm.exception))

    def test_a_value_of_the_wrong_type_stops_with_a_message(self):
        for text, word in (('{"maintainers": "alice"}', "list of names"), ('{"bot_names": [1]}', "list of names"),
                           ('{"data_dir": 5}', "must be text"), ('{"data_dir": ""}', "must not be empty"),
                           ('{"mirror": ["x"]}', "must be text"), ('{"main_since": "last week"}', "a date like")):
            self.use(text)
            with self.assertRaises(SystemExit) as cm:
                conf.settings()
            self.assertIn(word, str(cm.exception), text)

    def test_an_empty_mirror_is_no_mirror(self):
        self.use('{"mirror": ""}')
        self.assertIsNone(conf.mirror())

    def test_the_env_variable_names_the_file_in_place_of_the_one_at_the_repo_root(self):
        root = os.path.join(self.d, "root")
        os.mkdir(root)
        with open(os.path.join(root, "config.json"), "w", encoding="utf-8") as fh:
            fh.write('{"main_since": "2020-01-01"}')
        with open(self.file, "w", encoding="utf-8") as fh:
            fh.write('{"main_since": "2021-01-01"}')
        with mock.patch.object(conf, "CODE", root), mock.patch.dict(os.environ):
            os.environ.pop("REA_BOARD_CONFIG", None)
            self.assertEqual(conf.main_since(), "2020-01-01")
            self.assertEqual(conf.data_dir(), os.path.join(root, "data"))
            os.environ["REA_BOARD_CONFIG"] = self.file
            self.assertEqual(conf.main_since(), "2021-01-01")
            os.environ["REA_BOARD_CONFIG"] = os.path.join(self.d, "none.json")
            self.assertEqual(conf.settings(), conf.DEFAULTS)

    def test_with_neither_a_root_file_nor_the_env_variable_the_defaults_apply(self):
        with mock.patch.object(conf, "CODE", self.d), mock.patch.dict(os.environ):
            os.environ.pop("REA_BOARD_CONFIG", None)
            self.assertEqual(conf.repo(), "morluto/rea")
            self.assertEqual(conf.data_dir(), os.path.join(self.d, "data"))

    def test_a_file_that_is_not_json_is_a_one_line_error(self):
        self.use("{not json")
        with self.assertRaises(SystemExit) as cm:
            conf.repo()
        msg = str(cm.exception)
        self.assertEqual(msg.count("\n"), 0)
        self.assertTrue(msg.startswith("conf: "))
        self.assertIn(self.file, msg)
        self.assertIn("not valid JSON", msg)

    def test_a_file_that_is_json_but_not_an_object_is_a_one_line_error(self):
        for text in ("[]", '"x"', "3"):
            self.use(text)
            with self.assertRaises(SystemExit) as cm:
                conf.repo()
            self.assertEqual(str(cm.exception).count("\n"), 0)
            self.assertIn("JSON object", str(cm.exception))

    def test_a_script_stops_with_that_one_line_and_no_traceback(self):
        self.use("{not json")
        r = subprocess.run([sys.executable, "-I", PULL, "--help"], capture_output=True, text=True, stdin=subprocess.DEVNULL, env=dict(os.environ))
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)
        self.assertIn("is not valid JSON", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_the_example_config_is_json_with_only_the_machine_overrides(self):
        with open(os.path.join(HERE, "config.example.json"), encoding="utf-8") as fh:
            ex = json.load(fh)
        self.assertEqual(sorted(ex), ["data_dir", "mirror"])
        self.use(json.dumps(ex))
        self.assertEqual(conf.data_dir(), os.path.join(conf.CODE, "data"))
        self.assertIsNone(conf.mirror())


if __name__ == "__main__":
    unittest.main()
