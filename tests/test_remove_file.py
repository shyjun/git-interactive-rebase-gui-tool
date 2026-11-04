import unittest
import sys
import os
import tempfile
import shutil
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Import lib.app_window first, matching the app's import order: importing
# lib.git_helpers first hits a package-init cycle (git_helpers -> core ->
# app_window.helpers -> app_window.__init__ -> init_mixin -> git_helpers).
import lib.app_window.helpers  # noqa: F401
from lib.git_helpers import (
    amend_with_head,
    bulk_commit_all,
    path_is_dirty,
    remove_file_path,
)


def _git(cwd, *args):
    return subprocess.run(["git"] + list(args), cwd=cwd, check=True,
                          capture_output=True, text=True)


class RemoveFileRepoFixture(unittest.TestCase):
    """Temp repo with a tracked file (docs/old.txt) and a tracked folder
    (src/pkg/mod.py), plus a second commit so HEAD has a parent."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "main")
        os.makedirs(self.repo)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t.com")
        _git(self.repo, "config", "user.name", "t")
        os.makedirs(os.path.join(self.repo, "docs"))
        with open(os.path.join(self.repo, "docs", "old.txt"), "w") as f:
            f.write("hello\n")
        os.makedirs(os.path.join(self.repo, "src", "pkg"))
        with open(os.path.join(self.repo, "src", "pkg", "mod.py"), "w") as f:
            f.write("x = 1\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "initial")
        # A second commit so amend tests have a parent to compare against.
        with open(os.path.join(self.repo, "other.txt"), "w") as f:
            f.write("other\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "second")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _exists(self, rel):
        return os.path.exists(os.path.join(self.repo, rel))

    def _write(self, rel, text):
        with open(os.path.join(self.repo, rel), "w") as f:
            f.write(text)

    def _status(self):
        return _git(self.repo, "status", "--porcelain").stdout

    def _cached_name_status(self):
        return _git(self.repo, "diff", "--cached", "--name-status").stdout

    def _log_name_status(self):
        return _git(self.repo, "log", "--name-status", "-1").stdout


class TestRemoveFilePath(RemoveFileRepoFixture):

    def test_remove_file_and_stage(self):
        ok, detail = remove_file_path(self.repo, "docs/old.txt")
        self.assertTrue(ok, detail)
        self.assertFalse(self._exists("docs/old.txt"))
        # git rm stages the deletion itself — no separate git add needed.
        self.assertIn("D\tdocs/old.txt", self._cached_name_status())
        self.assertIn("D  docs/old.txt", self._status())

    def test_remove_file_and_commit(self):
        ok, detail = remove_file_path(self.repo, "docs/old.txt")
        self.assertTrue(ok, detail)
        ok, detail = bulk_commit_all(
            self.repo, "remove old", ["docs/old.txt"])
        self.assertTrue(ok, detail)
        log = self._log_name_status()
        self.assertIn("D\tdocs/old.txt", log)
        self.assertNotIn("other.txt", log)
        self.assertFalse(self._exists("docs/old.txt"))
        self.assertEqual(self._status(), "")

    def test_remove_and_amend_with_message(self):
        ok, detail = remove_file_path(self.repo, "docs/old.txt")
        self.assertTrue(ok, detail)
        ok, detail = amend_with_head(
            self.repo, ["docs/old.txt"], message="amended removal")
        self.assertTrue(ok, detail)
        self.assertEqual(
            _git(self.repo, "log", "-1", "--format=%B").stdout.strip(),
            "amended removal")
        self.assertIn("D\tdocs/old.txt", self._log_name_status())
        self.assertFalse(self._exists("docs/old.txt"))
        self.assertEqual(self._status(), "")

    def test_remove_folder_recursive(self):
        ok, detail = remove_file_path(self.repo, "src/pkg")
        self.assertTrue(ok, detail)
        self.assertFalse(self._exists("src/pkg/mod.py"))
        self.assertFalse(self._exists("src/pkg"))
        self.assertIn("D\tsrc/pkg/mod.py", self._cached_name_status())

    def test_backslashes_are_normalized(self):
        ok, detail = remove_file_path(self.repo, "docs\\old.txt")
        self.assertTrue(ok, detail)
        self.assertFalse(self._exists("docs/old.txt"))

    def test_missing_path(self):
        ok, detail = remove_file_path(self.repo, "docs/nope.txt")
        self.assertFalse(ok)
        self.assertIn("does not exist", detail)

    def test_outside_repository(self):
        with open(os.path.join(self.tmp, "evil.txt"), "w") as f:
            f.write("x\n")
        ok, detail = remove_file_path(self.repo, "../evil.txt")
        self.assertFalse(ok)
        self.assertIn("inside the repository", detail)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "evil.txt")))

    def test_inside_git_dir(self):
        ok, detail = remove_file_path(self.repo, ".git/config")
        self.assertFalse(ok)
        self.assertIn(".git/", detail)

    def test_repo_root(self):
        ok, detail = remove_file_path(self.repo, ".")
        self.assertFalse(ok)
        self.assertIn("repository root", detail)

    def test_empty_path(self):
        ok, detail = remove_file_path(self.repo, "")
        self.assertFalse(ok)
        self.assertIn("provide a path", detail)

    def test_untracked_file_rejected(self):
        self._write("loose.txt", "untracked\n")
        ok, detail = remove_file_path(self.repo, "loose.txt")
        self.assertFalse(ok)
        self.assertIn("Not tracked", detail)
        # Nothing was deleted: an untracked path has no history to restore.
        self.assertTrue(self._exists("loose.txt"))

    def test_dirty_file_refused_without_force(self):
        self._write("docs/old.txt", "modified, unstaged\n")
        self.assertTrue(path_is_dirty(self.repo, "docs/old.txt"))
        ok, detail = remove_file_path(self.repo, "docs/old.txt")
        self.assertFalse(ok)
        self.assertIn("Uncommitted changes", detail)
        self.assertTrue(self._exists("docs/old.txt"))
        self.assertEqual(self._status(), " M docs/old.txt\n")

    def test_dirty_file_removed_with_force(self):
        self._write("docs/old.txt", "modified, unstaged\n")
        ok, detail = remove_file_path(self.repo, "docs/old.txt", force=True)
        self.assertTrue(ok, detail)
        self.assertFalse(self._exists("docs/old.txt"))
        self.assertIn("D  docs/old.txt", self._status())

    def test_untracked_folder_rejected(self):
        os.makedirs(os.path.join(self.repo, "loose-dir"))
        self._write("loose-dir/a.txt", "untracked\n")
        ok, detail = remove_file_path(self.repo, "loose-dir")
        self.assertFalse(ok)
        self.assertIn("Not tracked", detail)
        self.assertTrue(self._exists("loose-dir/a.txt"))


class TestPathIsDirty(RemoveFileRepoFixture):

    def test_clean_tracked_file(self):
        self.assertFalse(path_is_dirty(self.repo, "docs/old.txt"))

    def test_modified_tracked_file(self):
        self._write("docs/old.txt", "changed\n")
        self.assertTrue(path_is_dirty(self.repo, "docs/old.txt"))

    def test_untracked_file(self):
        self._write("loose.txt", "untracked\n")
        self.assertTrue(path_is_dirty(self.repo, "loose.txt"))

    def test_empty_path_is_not_dirty(self):
        self.assertFalse(path_is_dirty(self.repo, ""))


class TestRemoveFileDialogSmoke(unittest.TestCase):
    """Constructs the dialog offscreen and checks its defaults."""

    @classmethod
    def setUpClass(cls):
        try:
            from PySide6.QtWidgets import QApplication
            cls.HAS_PYSIDE = True
        except ImportError:
            cls.HAS_PYSIDE = False
            return
        if not QApplication.instance():
            cls.app = QApplication([])

    def test_dialog_defaults(self):
        if not self.HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        from lib.dialogs import RemoveFileDialog
        dlg = RemoveFileDialog("/tmp", font_size=10, parent=None)
        self.assertEqual(dlg.action, RemoveFileDialog.StageAction)
        self.assertEqual(dlg.path, "")
        self.assertEqual(dlg.path_edit.text(), "")
        for btn in (dlg.stage_btn, dlg.commit_btn, dlg.amend_btn):
            self.assertIsNotNone(btn)
        self.assertTrue(dlg.commit_btn.isDefault())
        self.assertEqual(dlg.commit_btn.text(), "Commit the Removal")
        self.assertEqual(dlg.amend_btn.text(), "commit --amend the removal")
        self.assertEqual(dlg.stage_btn.text(), "Stage the Removal")
        dlg.reject()


if __name__ == "__main__":
    unittest.main()
