import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from PySide6.QtWidgets import QApplication, QDialog, QPushButton
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False


def _git(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    )


class _FakeMessageBox:
    events = []
    Information = 1
    Warning = 2
    Critical = 3

    @classmethod
    def information(cls, parent, title, text, *a, **k):
        cls.events.append(("information", title))

    @classmethod
    def warning(cls, parent, title, text, *a, **k):
        cls.events.append(("warning", title))

    @classmethod
    def critical(cls, parent, title, text, *a, **k):
        cls.events.append(("critical", title))


class _FakeProgressDialog:
    def __init__(self, *a, **k):
        self.label = mock.Mock()

    def show(self):
        pass

    def close(self):
        pass

    def exec(self):
        pass


class _FakeUnstagedDialog:
    """Scripted stand-in for UnstagedChangesDialog, carrying the real result ids."""
    Accepted = 1
    CommitEachResult = 2
    BulkCommitResult = 3
    AmendResult = 4
    SelectiveCommitResult = 5
    MergeResult = 6
    DiscardResult = 7
    ViewerModeResult = 8
    result = None
    events = None  # set to the Win's events list so ordering is observable

    def __init__(self, *a, **k):
        pass

    def exec(self):
        if type(self).events is not None:
            type(self).events.append("dialog")
        return type(self).result


class TestRescanRefreshFirst(unittest.TestCase):
    """handle_rescan_repo must refresh history first, then run the rescan checks,
    and only reload again when a dialog action actually mutated the repo."""

    @classmethod
    def setUpClass(cls):
        if HAS_PYSIDE and not QApplication.instance():
            cls.app = QApplication([])

    def setUp(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        from lib.app_window import rescan_mixin
        self.rescan_mixin = rescan_mixin
        _FakeMessageBox.events = []
        _FakeUnstagedDialog.result = _FakeUnstagedDialog.ViewerModeResult
        _FakeUnstagedDialog.events = None
        for target, fake in (
            ("QMessageBox", _FakeMessageBox),
            ("ProgressDialog", _FakeProgressDialog),
            ("UnstagedChangesDialog", _FakeUnstagedDialog),
        ):
            patcher = mock.patch.object(rescan_mixin, target, fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.repo = tempfile.mkdtemp(prefix="rescanflow_")
        self.addCleanup(shutil.rmtree, self.repo, True)
        _git(self.repo, "init", "-qb", "main")
        _git(self.repo, "config", "user.email", "t@t")
        _git(self.repo, "config", "user.name", "t")
        with open(os.path.join(self.repo, "base.txt"), "w") as fh:
            fh.write("base\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "base")

    def _win(self):
        from lib.app_window.rescan_mixin import RescanMixin

        class _Win(RescanMixin):
            def __init__(self, repo_path):
                self.repo_path = repo_path
                self.browse_mode = False
                self.viewer_mode = False
                self.current_font_size = 10
                self.current_font_family = None
                self.app_managed_stash_sha = None
                self.repo_btn = QPushButton()
                self.events = []

            def load_history(self):
                self.events.append("load_history")

            def load_browse_history_async(self):
                self.events.append("load_browse_history_async")

            def _update_stash_btn_visibility(self):
                pass

            def _flash_pop_stash_btn(self):
                pass

            def save_undo_state(self):
                self.events.append("save_undo_state")

            def get_head_sha(self):
                return _git(self.repo_path, "rev-parse", "HEAD").stdout.strip()

        win = _Win(self.repo)
        _FakeUnstagedDialog.events = win.events
        return win

    def _modify(self, name="base.txt", content="modified\n"):
        with open(os.path.join(self.repo, name), "w") as fh:
            fh.write(content)

    def test_clean_repo_single_refresh_no_dialog(self):
        win = self._win()
        win.handle_rescan_repo()
        self.assertEqual(win.events, ["load_history"],
                         "clean repo: exactly one refresh, no dialog")
        self.assertFalse(_FakeMessageBox.events)

    def test_unstaged_cancel_refreshes_once_then_dialog(self):
        self._modify()
        _FakeUnstagedDialog.result = 0  # none of the constants -> Cancel branch
        win = self._win()
        win.handle_rescan_repo()
        self.assertEqual(win.events, ["load_history", "dialog"],
                         "cancel: refresh first, dialog second, no second reload")

    def test_refresh_runs_before_dialog(self):
        self._modify()
        _FakeUnstagedDialog.result = 0
        win = self._win()
        win.handle_rescan_repo()
        self.assertLess(win.events.index("load_history"),
                        win.events.index("dialog"))

    def test_stash_success_reloads_again(self):
        self._modify()
        _FakeUnstagedDialog.result = _FakeUnstagedDialog.Accepted
        win = self._win()
        win.handle_rescan_repo()
        self.assertEqual(win.events, ["load_history", "dialog", "load_history"],
                         "stash success mutates: second reload at the end")
        self.assertIsNotNone(win.app_managed_stash_sha)
        # Worktree is clean again after the stash
        status = _git(self.repo, "status", "--porcelain").stdout
        self.assertEqual(status, "")

    def test_stash_nothing_reloads_only_once(self):
        # Dialog opened for untracked-only noise is not possible here
        # (get_unstaged_files sees only tracked changes), so simulate the
        # "nothing to stash" outcome by stashing between dialog open and act:
        # simplest real case — remove the modification before Accepted runs.
        self._modify()
        _FakeUnstagedDialog.result = _FakeUnstagedDialog.Accepted
        # Make the change vanish before the handler's stash call by restoring
        # the file inside the scripted dialog exec.
        real_repo = self.repo

        def _exec(self):
            with open(os.path.join(real_repo, "base.txt"), "w") as fh:
                fh.write("base\n")
            if _FakeUnstagedDialog.events is not None:
                _FakeUnstagedDialog.events.append("dialog")
            return _FakeUnstagedDialog.Accepted

        with mock.patch.object(_FakeUnstagedDialog, "exec", _exec):
            win = self._win()
            win.handle_rescan_repo()
        infos = [e for e in _FakeMessageBox.events if e[0] == "information"]
        self.assertTrue(any("No Changes Stashed" in e[1] for e in infos))
        self.assertEqual(win.events, ["load_history", "dialog"],
                         "nothing stashed: no second reload, no mutation")

    def test_commit_each_reloads_again(self):
        self._modify(content="committed one by one\n")
        _FakeUnstagedDialog.result = _FakeUnstagedDialog.CommitEachResult
        win = self._win()
        win.handle_rescan_repo()
        self.assertEqual(win.events[0], "load_history",
                         "refresh must run first")
        self.assertIn("dialog", win.events)
        self.assertEqual(win.events[-1], "load_history",
                         "commit-each mutates: final reload runs")
        self.assertIn("save_undo_state", win.events)
        self.assertEqual(
            _git(self.repo, "log", "-1", "--format=%s").stdout.strip(),
            "changes in base.txt")
        self.assertEqual(_git(self.repo, "status", "--porcelain").stdout, "")


if __name__ == "__main__":
    unittest.main()
