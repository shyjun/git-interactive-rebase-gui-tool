import unittest
import sys
import os
import tempfile
import shutil
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.git_helpers import apply_patch_file, _parse_patch_commit_message


class TestApplyPatchFile(unittest.TestCase):
    """Verifies apply_patch_file applies patches, optionally committing them."""

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.patch_dir = tempfile.mkdtemp()
        self._git("init", "-q")
        self._git("config", "user.email", "t@t.com")
        self._git("config", "user.name", "t")
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write("base\n")
        self._git("add", ".")
        self._git("commit", "-qm", "base commit")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        shutil.rmtree(self.patch_dir, ignore_errors=True)

    def _git(self, *args):
        subprocess.run(["git"] + list(args), cwd=self.repo, check=True,
                       capture_output=True, text=True)

    def _write_patch(self, name, content):
        path = os.path.join(self.patch_dir, name)
        with open(path, "w") as f:
            f.write(content)
        return path

    def _unified_patch(self, subject=None):
        header = ""
        if subject:
            header = f"From: t@t.com\nDate: Thu, 1 Jan 1970 00:00:00 +0000\nSubject: [PATCH] {subject}\n\n"
        return header + (
            "diff --git a/f.txt b/f.txt\n"
            "index 4ea5d6c..5b5f6c6 100644\n"
            "--- a/f.txt\n"
            "+++ b/f.txt\n"
            "@@ -1 +1,2 @@\n"
            " base\n"
            "+patched\n"
        )

    def _commit_count(self):
        return int(subprocess.run(
            ["git", "rev-list", "--count", "HEAD"], cwd=self.repo,
            capture_output=True, text=True, check=True).stdout.strip())

    def _working_tree_diff(self):
        return subprocess.run(
            ["git", "diff", "--", "f.txt"], cwd=self.repo,
            capture_output=True, text=True, check=True).stdout

    def test_commit_wanted_creates_commit_with_patch_message(self):
        patch = self._write_patch("c.patch", self._unified_patch("Add patched line"))
        ok, detail = apply_patch_file(self.repo, patch, commit_wanted=True)
        self.assertTrue(ok)
        self.assertEqual(self._commit_count(), 2)
        subject = self._git_capture("log", "-1", "--format=%s")
        self.assertEqual(subject, "Add patched line")
        self.assertEqual(self._working_tree_diff(), "")

    def test_unstaged_leaves_changes_in_working_tree(self):
        patch = self._write_patch("u.patch", self._unified_patch("Add patched line"))
        ok, detail = apply_patch_file(self.repo, patch, commit_wanted=False)
        self.assertTrue(ok)
        self.assertEqual(self._commit_count(), 1)
        self.assertIn("+patched", self._working_tree_diff())

    def test_failing_patch_returns_error_and_leaves_repo_unchanged(self):
        before = self._commit_count()
        stale = self._unified_patch("Stale")
        stale = stale.replace(" base\n+patched", " base\npatched\n+other")
        patch = self._write_patch("bad.patch", stale)
        ok, detail = apply_patch_file(self.repo, patch, commit_wanted=True)
        self.assertFalse(ok)
        self.assertTrue(detail)
        self.assertEqual(self._commit_count(), before)
        self.assertEqual(self._working_tree_diff(), "")

    def test_missing_patch_file_returns_error(self):
        ok, detail = apply_patch_file(self.repo, os.path.join(self.patch_dir, "nope.patch"),
                                      commit_wanted=False)
        self.assertFalse(ok)
        self.assertTrue(detail)

    def _git_capture(self, *args):
        return subprocess.run(
            ["git"] + list(args), cwd=self.repo, capture_output=True, text=True,
            check=True).stdout.strip()


class TestParsePatchCommitMessage(unittest.TestCase):
    def setUp(self):
        self.patch_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.patch_dir, ignore_errors=True)

    def _write(self, content):
        path = os.path.join(self.patch_dir, "p.patch")
        with open(path, "w") as f:
            f.write(content)
        return path

    def test_subject_header_used_and_patch_prefix_stripped(self):
        path = self._write(
            "From: t@t.com\nSubject: [PATCH] Fix the thing\n\nBody text here.\n"
            "---\ndiff --git a/x b/x\n")
        subject, body = _parse_patch_commit_message(path)
        self.assertEqual(subject, "Fix the thing")
        self.assertIn("Body text here.", body)

    def test_multiline_body_preserved(self):
        path = self._write(
            "Subject: Add feature\n\nFirst line.\nSecond line.\n"
            "---\ndiff --git a/x b/x\n")
        subject, body = _parse_patch_commit_message(path)
        self.assertEqual(subject, "Add feature")
        self.assertEqual(body, "First line.\nSecond line.")

    def test_no_subject_falls_back_to_default(self):
        path = self._write("diff --git a/x b/x\n@@ -1 +1 @@\n")
        subject, body = _parse_patch_commit_message(path)
        self.assertEqual(subject, "Apply patch")
        self.assertEqual(body, "")


if __name__ == "__main__":
    unittest.main()