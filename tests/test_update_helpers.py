import unittest
import sys
import os
import tempfile
import shutil
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.git_helpers import build_update_command, perform_self_update


class TestBuildUpdateCommand(unittest.TestCase):

    def test_pip_install_command(self):
        self.assertEqual(build_update_command("/some/dir", is_pip=True),
                         "git_interactive_rebase --update")

    def test_git_install_command(self):
        self.assertEqual(
            build_update_command("/path/to/tool", is_pip=False),
            "python3 /path/to/tool/git_interactive_rebase.py --update")


class TestPerformSelfUpdate(unittest.TestCase):
    """Exercises the git-clone update path using a bare remote."""

    def setUp(self):
        # Bare repo acts as the remote origin.
        self.remote = tempfile.mkdtemp()
        self._git(self.remote, "init", "--bare", "-q")

        # The tool lives in a clone of that remote.
        self.tool = tempfile.mkdtemp()
        subprocess.run(["git", "clone", "-q", self.remote, self.tool],
                       check=True, capture_output=True, text=True)
        for repo in (self.remote, self.tool):
            subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo,
                           check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=repo,
                           check=True, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.remote, ignore_errors=True)
        shutil.rmtree(self.tool, ignore_errors=True)

    def _git(self, repo, *args):
        subprocess.run(["git"] + list(args), cwd=repo, check=True,
                       capture_output=True, text=True)

    def _publish_first_commit(self):
        """Commits an initial version in the tool clone and pushes it."""
        with open(os.path.join(self.tool, "file.txt"), "w") as f:
            f.write("one\n")
        self._git(self.tool, "add", ".")
        self._git(self.tool, "commit", "-qm", "first")
        self._git(self.tool, "push", "-q", "origin", "master")

    def _publish_new_commit(self):
        """Publishes a newer commit on the remote via a scratch clone."""
        scratch = tempfile.mkdtemp()
        try:
            subprocess.run(["git", "clone", "-q", self.remote, scratch],
                           check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=scratch,
                           check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=scratch,
                           check=True, capture_output=True)
            with open(os.path.join(scratch, "file.txt"), "w") as f:
                f.write("one\ntwo\n")
            self._git(scratch, "add", ".")
            self._git(scratch, "commit", "-qm", "second")
            self._git(scratch, "push", "-q", "origin", "master")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_clean_tree_behind_remote_updates(self):
        self._publish_first_commit()
        self._publish_new_commit()

        ok, message = perform_self_update(self.tool)
        self.assertTrue(ok, message)
        self.assertIn("Update complete", message)
        with open(os.path.join(self.tool, "file.txt")) as f:
            self.assertIn("two", f.read())

    def test_dirty_tree_aborts_without_changes(self):
        self._publish_first_commit()
        self._publish_new_commit()

        with open(os.path.join(self.tool, "file.txt"), "w") as f:
            f.write("LOCAL EDIT\n")

        ok, message = perform_self_update(self.tool)
        self.assertFalse(ok)
        self.assertIn("uncommitted changes", message)
        with open(os.path.join(self.tool, "file.txt")) as f:
            self.assertIn("LOCAL EDIT", f.read())

    def test_up_to_date_reports_latest(self):
        self._publish_first_commit()

        ok, message = perform_self_update(self.tool)
        self.assertTrue(ok)
        self.assertIn("latest version", message)


if __name__ == "__main__":
    unittest.main()