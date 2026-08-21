import unittest
import sys
import os
import tempfile
import shutil
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.git_helpers import _run_capture, get_tags_map


class TestGitTag(unittest.TestCase):
    """Verifies git tag creation via _run_capture."""

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self._git("init", "-q")
        self._git("config", "user.email", "t@t.com")
        self._git("config", "user.name", "t")
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write("line1\n")
        self._git("add", ".")
        self._git("commit", "-qm", "initial commit")
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo,
                                capture_output=True, text=True)
        self.sha = result.stdout.strip()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _git(self, *args):
        subprocess.run(["git"] + list(args), cwd=self.repo, check=True,
                       capture_output=True, text=True)

    def _tag_exists(self, tag):
        result = subprocess.run(["git", "tag", "-l", tag], cwd=self.repo,
                                capture_output=True, text=True)
        return tag in result.stdout

    def test_lightweight_tag(self):
        ok, stdout, stderr = _run_capture(self.repo, ["git", "tag", "v1.0", self.sha])
        self.assertTrue(ok)
        self.assertTrue(self._tag_exists("v1.0"))

    def test_annotated_tag(self):
        ok, stdout, stderr = _run_capture(
            self.repo, ["git", "tag", "-a", "v1.1", "-m", "release 1.1", self.sha])
        self.assertTrue(ok)
        self.assertTrue(self._tag_exists("v1.1"))
        result = subprocess.run(["git", "tag", "-n1", "v1.1"], cwd=self.repo,
                                capture_output=True, text=True)
        self.assertIn("release 1.1", result.stdout)

    def test_tag_bad_name_fails(self):
        ok, stdout, stderr = _run_capture(self.repo, ["git", "tag", ""])
        self.assertFalse(ok)

    def test_duplicate_tag_fails(self):
        ok, _, _ = _run_capture(self.repo, ["git", "tag", "v1.0", self.sha])
        self.assertTrue(ok)
        ok2, _, _ = _run_capture(self.repo, ["git", "tag", "v1.0", self.sha])
        self.assertFalse(ok2)


class TestGetTagsMap(unittest.TestCase):
    """Verifies get_tags_map returns correct SHA-to-tag mappings."""

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self._git("init", "-q")
        self._git("config", "user.email", "t@t.com")
        self._git("config", "user.name", "t")
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write("line1\n")
        self._git("add", ".")
        self._git("commit", "-qm", "initial commit")
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.repo,
                                capture_output=True, text=True)
        self.short_sha = result.stdout.strip()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _git(self, *args):
        subprocess.run(["git"] + list(args), cwd=self.repo, check=True,
                       capture_output=True, text=True)

    def test_lightweight_tag_mapped(self):
        self._git("tag", "v1.0", self.short_sha)
        tag_map = get_tags_map(self.repo)
        self.assertIn(self.short_sha, tag_map)
        self.assertIn("v1.0", tag_map[self.short_sha])

    def test_annotated_tag_mapped_to_commit(self):
        self._git("tag", "-a", "v2.0", "-m", "release", self.short_sha)
        tag_map = get_tags_map(self.repo)
        self.assertIn(self.short_sha, tag_map)
        self.assertIn("v2.0", tag_map[self.short_sha])

    def test_no_tags(self):
        tag_map = get_tags_map(self.repo)
        self.assertEqual(tag_map, {})


if __name__ == "__main__":
    unittest.main()
