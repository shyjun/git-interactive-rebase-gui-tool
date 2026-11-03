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
    rename_move_path,
    stage_files,
)


def _git(cwd, *args):
    return subprocess.run(["git"] + list(args), cwd=cwd, check=True,
                          capture_output=True, text=True)


class RenameMoveRepoFixture(unittest.TestCase):
    """Temp repo with a tracked file (docs/old.txt) and a tracked folder
    (src/pkg/mod.py), plus an untracked file for parent-creation tests."""

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
        # A second commit so HEAD has a parent: amend tests then exercise
        # rename detection (amending the root commit has no parent to
        # compare against, and git log --name-status would show plain adds).
        with open(os.path.join(self.repo, "other.txt"), "w") as f:
            f.write("other\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "second")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _exists(self, rel):
        return os.path.exists(os.path.join(self.repo, rel))

    def _status(self):
        return _git(self.repo, "status", "--porcelain").stdout

    def _cached_name_status(self):
        return _git(self.repo, "diff", "--cached", "--name-status", "-M").stdout

    def _log_name_status(self):
        return _git(self.repo, "log", "--name-status", "-M", "-1").stdout


class TestRenameMovePath(RenameMoveRepoFixture):

    def test_rename_file_and_stage(self):
        ok, detail = rename_move_path(self.repo, "docs/old.txt", "docs/new.txt")
        self.assertTrue(ok, detail)
        self.assertFalse(self._exists("docs/old.txt"))
        self.assertTrue(self._exists("docs/new.txt"))
        self.assertTrue(stage_files(self.repo, ["docs/old.txt", "docs/new.txt"]))
        # Staged rename: git reports R (old -> new) from the index.
        self.assertIn("R", self._cached_name_status())
        self.assertIn("docs/old.txt", self._cached_name_status())
        self.assertIn("docs/new.txt", self._cached_name_status())

    def test_rename_file_and_commit(self):
        ok, detail = rename_move_path(self.repo, "docs/old.txt", "docs/new.txt")
        self.assertTrue(ok, detail)
        # Stage both sides first (mirrors the dialog flow): git commit --only
        # needs every pathspec to be known to git.
        self.assertTrue(stage_files(self.repo, ["docs/old.txt", "docs/new.txt"]))
        ok, detail = bulk_commit_all(
            self.repo, "rename old -> new",
            ["docs/old.txt", "docs/new.txt"])
        self.assertTrue(ok, detail)
        # The commit contains exactly the rename, nothing else.
        log = self._log_name_status()
        self.assertIn("R", log)
        self.assertIn("docs/old.txt", log)
        self.assertIn("docs/new.txt", log)
        self.assertTrue(self._exists("docs/new.txt"))
        self.assertEqual(self._status(), "")

    def test_rename_and_amend_with_message(self):
        ok, detail = rename_move_path(self.repo, "docs/old.txt", "docs/new.txt")
        self.assertTrue(ok, detail)
        self.assertTrue(stage_files(self.repo, ["docs/old.txt", "docs/new.txt"]))
        ok, detail = amend_with_head(
            self.repo, ["docs/old.txt", "docs/new.txt"],
            message="amended rename")
        self.assertTrue(ok, detail)
        self.assertEqual(
            _git(self.repo, "log", "-1", "--format=%B").stdout.strip(),
            "amended rename")
        log = self._log_name_status()
        self.assertIn("R", log)
        self.assertIn("docs/new.txt", log)
        self.assertTrue(self._exists("docs/new.txt"))

    def test_move_folder_recursive(self):
        ok, detail = rename_move_path(self.repo, "src/pkg", "lib/pkg")
        self.assertTrue(ok, detail)
        self.assertFalse(self._exists("src/pkg"))
        self.assertTrue(self._exists("lib/pkg/mod.py"))

    def test_missing_destination_parent_is_created(self):
        ok, detail = rename_move_path(self.repo, "docs/old.txt", "a/b/old.txt")
        self.assertTrue(ok, detail)
        self.assertTrue(self._exists("a/b/old.txt"))
        self.assertFalse(self._exists("docs/old.txt"))

    def test_backslashes_are_normalized(self):
        ok, detail = rename_move_path(self.repo, "docs\\old.txt", "docs\\new.txt")
        self.assertTrue(ok, detail)
        self.assertTrue(self._exists("docs/new.txt"))

    def test_missing_source(self):
        ok, detail = rename_move_path(self.repo, "docs/nope.txt", "docs/x.txt")
        self.assertFalse(ok)
        self.assertIn("does not exist", detail)

    def test_destination_exists(self):
        ok, detail = rename_move_path(self.repo, "docs/old.txt", "src/pkg/mod.py")
        self.assertFalse(ok)
        self.assertIn("already exists", detail)

    def test_outside_repository(self):
        ok, detail = rename_move_path(self.repo, "../evil.txt", "docs/x.txt")
        self.assertFalse(ok)
        self.assertIn("inside the repository", detail)

    def test_inside_git_dir(self):
        ok, detail = rename_move_path(self.repo, ".git/config", "docs/x.txt")
        self.assertFalse(ok)
        self.assertIn(".git/", detail)

    def test_same_path(self):
        ok, detail = rename_move_path(self.repo, "docs/old.txt", "docs/old.txt")
        self.assertFalse(ok)
        self.assertIn("same path", detail)

    def test_move_folder_into_itself(self):
        ok, detail = rename_move_path(self.repo, "src", "src/sub")
        self.assertFalse(ok)
        self.assertIn("into itself", detail)

    def test_empty_paths(self):
        ok, detail = rename_move_path(self.repo, "", "docs/x.txt")
        self.assertFalse(ok)
        self.assertIn("source and a destination", detail)

    def test_repo_root(self):
        ok, detail = rename_move_path(self.repo, ".", "docs/x.txt")
        self.assertFalse(ok)
        self.assertIn("repository root", detail)


class TestRenameMoveDialogSmoke(unittest.TestCase):
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
        from lib.dialogs import RenameMoveDialog
        dlg = RenameMoveDialog("/tmp", font_size=10, parent=None)
        self.assertEqual(dlg.action, RenameMoveDialog.StageAction)
        self.assertEqual(dlg.src_path, "")
        self.assertEqual(dlg.dst_path, "")
        for btn in (dlg.stage_btn, dlg.commit_btn, dlg.amend_btn):
            self.assertIsNotNone(btn)
        self.assertEqual(dlg._norm("./docs//old.txt/"), "docs/old.txt")
        dlg.reject()


if __name__ == "__main__":
    unittest.main()
