import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.git_helpers import merge_would_conflict


def _git(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    )


class TestMergeWouldConflict(unittest.TestCase):
    """merge_would_conflict previews git pull conflicts via merge-tree."""

    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="mwc_")
        _git(self.repo, "init", "-b", "main")
        with open(os.path.join(self.repo, "base.txt"), "w") as f:
            f.write("base\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-m", "base")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _branch(self, name):
        _git(self.repo, "checkout", "-b", name)

    def _checkout(self, name):
        _git(self.repo, "checkout", name)

    def _edit(self, name, text):
        with open(os.path.join(self.repo, name), "w") as f:
            f.write(text)
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-m", f"edit {name}")

    def test_clean_merge_reports_no_conflict(self):
        self._branch("feature")
        self._edit("feature.txt", "feature work\n")
        self._checkout("main")
        self._edit("main.txt", "main work\n")
        conflict, files = merge_would_conflict(self.repo, "main", "feature")
        self.assertFalse(conflict)
        self.assertEqual(files, [])

    def test_same_file_conflict_detected(self):
        self._branch("feature")
        self._edit("base.txt", "feature version\n")
        self._checkout("main")
        self._edit("base.txt", "main version\n")
        conflict, files = merge_would_conflict(self.repo, "main", "feature")
        self.assertTrue(conflict)
        self.assertIn("base.txt", files)

    def test_add_add_conflict_detected(self):
        self._branch("feature")
        self._edit("same.txt", "mine\n")
        self._checkout("main")
        self._edit("same.txt", "theirs\n")
        conflict, files = merge_would_conflict(self.repo, "main", "feature")
        self.assertTrue(conflict)
        self.assertIn("same.txt", files)

    def test_identical_change_is_not_a_conflict(self):
        self._branch("feature")
        self._edit("base.txt", "same change\n")
        self._checkout("main")
        self._edit("base.txt", "same change\n")
        conflict, _files = merge_would_conflict(self.repo, "main", "feature")
        self.assertFalse(conflict)

    def test_unrelated_histories_reported_as_risky(self):
        other = tempfile.mkdtemp(prefix="mwc_other_")
        try:
            _git(other, "init", "-b", "main")
            with open(os.path.join(other, "x.txt"), "w") as f:
                f.write("x\n")
            _git(other, "add", ".")
            _git(other, "commit", "-m", "other base")
            conflict, _files = merge_would_conflict(self.repo, "main", other)
            self.assertTrue(conflict)
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_invalid_ref_reports_conservative_conflict(self):
        conflict, _files = merge_would_conflict(self.repo, "main", "no-such-ref")
        self.assertTrue(conflict)


if __name__ == "__main__":
    unittest.main()
