import unittest
import sys
import os
import tempfile
import shutil
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.git_helpers import get_file_history


class TestGetFileHistoryRef(unittest.TestCase):
    """Verifies that get_file_history can scope history to a specific branch."""

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self._git("init", "-q")
        self._git("config", "user.email", "t@t.com")
        self._git("config", "user.name", "t")
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write("base\n")
        self._git("add", ".")
        self._git("commit", "-qm", "base commit")
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write("base\nmaster\n")
        self._git("add", ".")
        self._git("commit", "-qm", "master second")
        self._git("branch", "feature")
        self._git("switch", "-q", "feature")
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write("base\nmaster\nfeature\n")
        self._git("add", ".")
        self._git("commit", "-qm", "feature change")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _git(self, *args):
        subprocess.run(["git"] + list(args), cwd=self.repo, check=True,
                       capture_output=True, text=True)

    def _subjects(self, entries):
        return [e["message"] for e in entries]

    def test_ref_scopes_to_branch(self):
        master = self._subjects(get_file_history(self.repo, "f.txt", ref="master"))
        self.assertIn("master second", master)
        self.assertNotIn("feature change", master)

    def test_ref_includes_branch_commits(self):
        feature = self._subjects(get_file_history(self.repo, "f.txt", ref="feature"))
        self.assertIn("feature change", feature)
        self.assertIn("master second", feature)

    def test_no_ref_uses_head(self):
        # HEAD is on the feature branch in this test.
        head = self._subjects(get_file_history(self.repo, "f.txt"))
        self.assertIn("feature change", head)


if __name__ == "__main__":
    unittest.main()