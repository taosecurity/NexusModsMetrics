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
        self.assertEqual(build.local_dir("  out  ", {}), os.path.abspath("out"))   # a pasted folder with spaces around it
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

    def test_folders_inside_the_repo_are_refused(self):
        # In-process: the refusal comes from argparse before git pull or the build, and nothing else is called.
        import contextlib
        import io
        from unittest import mock
        for folder in (build.SITE, REPO, os.path.join(REPO, "data")):
            err = io.StringIO()
            with mock.patch.object(build.subprocess, "run", side_effect=AssertionError("git pull ran")), \
                    contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                build.main(["--local", folder])
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("is inside this repo", err.getvalue())

    def test_inside(self):
        self.assertTrue(build.inside(REPO, REPO))
        self.assertTrue(build.inside(build.SITE, REPO))
        self.assertFalse(build.inside(os.path.dirname(REPO), REPO))
        self.assertFalse(build.inside(REPO + "-other", REPO))


if __name__ == "__main__":
    unittest.main()
