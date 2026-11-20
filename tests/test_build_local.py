"""Tests for build.py's --local option (no network, no build, nothing written).

Run from the repo folder:  python -m unittest discover -s tests
"""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
import build  # noqa: E402


class LocalDirTest(unittest.TestCase):
    def test_no_local_option(self):
        self.assertIsNone(build.local_dir(None, {build.LOCAL_ENV: "x"}))

    def test_folder_given(self):
        self.assertEqual(build.local_dir("out", {build.LOCAL_ENV: "env"}), os.path.abspath("out"))

    def test_env_var_used_when_folder_left_out(self):
        self.assertEqual(build.local_dir("", {build.LOCAL_ENV: "env"}), os.path.abspath("env"))

    def test_spaces_and_home_folder(self):
        self.assertEqual(build.local_dir("  out  ", {}), os.path.abspath("out"))
        self.assertEqual(build.local_dir(" ", {build.LOCAL_ENV: "env"}), os.path.abspath("env"))
        self.assertEqual(build.local_dir(os.path.join("~", "x"), {}), os.path.abspath(os.path.expanduser(os.path.join("~", "x"))))

    def test_no_folder_anywhere(self):
        self.assertIsNone(build.local_dir("", {}))
        self.assertIsNone(build.local_dir("  ", {build.LOCAL_ENV: "  "}))


class LocalErrorTest(unittest.TestCase):
    def test_local_without_folder_is_a_clear_error(self):
        env = {k: v for k, v in os.environ.items() if k != build.LOCAL_ENV}
        r = subprocess.run([sys.executable, "-I", os.path.join(REPO, "build.py"), "--local"],
                           capture_output=True, text=True, env=env, cwd=REPO)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--local needs a folder", r.stderr)
        self.assertIn(build.LOCAL_ENV, r.stderr)
        self.assertNotIn("build:", r.stdout)  # stopped before git pull and the build

    def test_site_folder_is_refused(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(REPO, "build.py"), "--local", build.SITE],
                           capture_output=True, text=True, cwd=REPO)
        self.assertEqual(r.returncode, 2)
        self.assertIn("is the site folder", r.stderr)
        self.assertNotIn("build:", r.stdout)


if __name__ == "__main__":
    unittest.main()
