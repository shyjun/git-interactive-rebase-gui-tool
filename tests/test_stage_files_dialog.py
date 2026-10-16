import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from PySide6.QtCore import Qt
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
    """Works both as QMessageBox(self) instance and QMessageBox.information()."""
    events = []
    Information = 1
    Warning = 2
    Critical = 3

    def __init__(self, *a, **k):
        self._title = ""
        self._text = ""

    def setIcon(self, *a):
        pass

    def setWindowTitle(self, title):
        self._title = title

    def setTextFormat(self, *a):
        pass

    def setText(self, text):
        self._text = text

    def exec(self):
        type(self).events.append(("information", self._title, self._text))

    @classmethod
    def information(cls, parent, title, text, *a, **k):
        cls.events.append(("information", title, text))

    @classmethod
    def warning(cls, parent, title, text, *a, **k):
        cls.events.append(("warning", title, text))

    @classmethod
    def critical(cls, parent, title, text, *a, **k):
        cls.events.append(("critical", title, text))


class _FakeMessageDialog:
    """Stands in for NewCommitMessageDialog with a scripted outcome."""
    message = "typed message"
    accepted = True

    def __init__(self, *a, **k):
        pass

    def exec(self):
        return QDialog.Accepted if type(self).accepted else QDialog.Rejected

    def get_message(self):
        return type(self).message


class _FakeProgressDialog:
    def __init__(self, *a, **k):
        pass

    def show(self):
        pass

    def close(self):
        pass


class TestStageFilesDialogButtons(unittest.TestCase):
    """Dialog-level behavior of the 'git commit selected files' button."""

    @classmethod
    def setUpClass(cls):
        if HAS_PYSIDE and not QApplication.instance():
            cls.app = QApplication([])

    def setUp(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        self.repo = tempfile.mkdtemp(prefix="stagefiles_")
        self.addCleanup(shutil.rmtree, self.repo, True)
        _git(self.repo, "init", "-qb", "main")
        with open(os.path.join(self.repo, "base.txt"), "w") as fh:
            fh.write("base\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "base")
        with open(os.path.join(self.repo, "new_a.txt"), "w") as fh:
            fh.write("a\n")
        with open(os.path.join(self.repo, "new_b.txt"), "w") as fh:
            fh.write("b\n")

    def _dialog(self):
        from lib.dialogs.unstaged_dialogs import StageFilesDialog
        return StageFilesDialog(
            self.repo, ["new_a.txt", "new_b.txt"],
            {"new_a.txt": (1, 0, 1, 1), "new_b.txt": (1, 0, 1, 1)})

    @staticmethod
    def _bottom_row_texts(dlg):
        """Labels of the widgets in the bottom button row, in order."""
        lay = dlg.layout()
        for i in range(lay.count()):
            item = lay.itemAt(i)
            sub = item.layout()
            if sub is None:
                continue
            texts = [sub.itemAt(j).widget().text()
                     for j in range(sub.count())
                     if sub.itemAt(j).widget() is not None]
            if "Add/Stage Selected Files" in texts:
                return texts
        return None

    def _check(self, dlg, index):
        dlg.file_list.item(index).setCheckState(Qt.Checked)

    def test_commit_button_exists_with_exact_label(self):
        dlg = self._dialog()
        texts = self._bottom_row_texts(dlg)
        self.assertIsNotNone(texts)
        self.assertIn("git commit selected files", texts)

    def test_button_order_commit_amend_stage_cancel(self):
        dlg = self._dialog()
        texts = self._bottom_row_texts(dlg)
        self.assertLess(texts.index("git commit selected files"),
                        texts.index("git commit --amend selected files"))
        self.assertLess(texts.index("git commit --amend selected files"),
                        texts.index("Add/Stage Selected Files"))
        self.assertLess(texts.index("Add/Stage Selected Files"),
                        texts.index("Cancel"))

    def test_commit_button_disabled_until_something_checked(self):
        dlg = self._dialog()
        self.assertFalse(dlg.commit_btn.isEnabled())
        self.assertFalse(dlg.amend_btn.isEnabled())
        self._check(dlg, 0)
        self.assertTrue(dlg.commit_btn.isEnabled())
        self.assertTrue(dlg.amend_btn.isEnabled())
        dlg.file_list.item(0).setCheckState(Qt.Unchecked)
        self.assertFalse(dlg.commit_btn.isEnabled())
        self.assertFalse(dlg.amend_btn.isEnabled())

    def test_stage_button_stays_default(self):
        dlg = self._dialog()
        btns = {b.text(): b for b in dlg.findChildren(QPushButton)}
        self.assertTrue(btns["Add/Stage Selected Files"].isDefault())
        self.assertFalse(dlg.commit_btn.isDefault())
        self.assertFalse(dlg.amend_btn.isDefault())

    def test_commit_click_sets_action_and_selection(self):
        dlg = self._dialog()
        self._check(dlg, 0)
        self._check(dlg, 1)
        dlg.commit_btn.click()
        self.assertEqual(dlg.action, "commit")
        self.assertEqual(sorted(dlg.selected_files),
                         ["new_a.txt", "new_b.txt"])
        self.assertEqual(dlg.result(), QDialog.Accepted)

    def test_amend_click_sets_action_and_selection(self):
        dlg = self._dialog()
        self._check(dlg, 1)
        dlg.amend_btn.click()
        self.assertEqual(dlg.action, "amend")
        self.assertEqual(dlg.selected_files, ["new_b.txt"])
        self.assertEqual(dlg.result(), QDialog.Accepted)

    def test_cancel_keeps_stage_action(self):
        dlg = self._dialog()
        dlg.reject()
        self.assertEqual(dlg.action, "stage")
        self.assertEqual(dlg.result(), QDialog.Rejected)


class TestHandleStageFilesCommitFlow(unittest.TestCase):
    """handle_stage_files end-to-end: real git, faked dialogs."""

    @classmethod
    def setUpClass(cls):
        if HAS_PYSIDE and not QApplication.instance():
            cls.app = QApplication([])

    def setUp(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        from lib.app_window import stash_mixin
        self.stash_mixin = stash_mixin
        _FakeMessageBox.events = []
        _FakeMessageDialog.accepted = True
        _FakeMessageDialog.message = "commit the new files"
        for target, fake in (
            ("QMessageBox", _FakeMessageBox),
            ("NewCommitMessageDialog", _FakeMessageDialog),
            ("ProgressDialog", _FakeProgressDialog),
        ):
            patcher = mock.patch.object(stash_mixin, target, fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.repo = tempfile.mkdtemp(prefix="stagecommit_")
        self.addCleanup(shutil.rmtree, self.repo, True)
        _git(self.repo, "init", "-qb", "main")
        with open(os.path.join(self.repo, "base.txt"), "w") as fh:
            fh.write("base\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "base")
        with open(os.path.join(self.repo, "new_a.txt"), "w") as fh:
            fh.write("a\n")
        with open(os.path.join(self.repo, "new_b.txt"), "w") as fh:
            fh.write("b\n")

    def _run(self, action):
        """Drive handle_stage_files with StageFilesDialog scripted: all files
        checked, then the real handler for the requested action clicked."""
        from lib.app_window.stash_mixin import StashMixin

        class _Win(StashMixin):
            def __init__(self, repo_path):
                self.repo_path = repo_path
                self.current_font_size = 10
                self.current_font_family = None
                self.calls = []
                self.last_head = None
                self.repo_btn = QPushButton()

            def _check_not_viewer_mode(self):
                return True

            def _check_head_unchanged(self):
                return True

            def save_undo_state(self):
                self.calls.append("save_undo_state")
                self.last_head = _git(self.repo_path, "rev-parse",
                                      "HEAD").stdout.strip()

            def load_history(self):
                self.calls.append("load_history")

            def get_head_sha(self):
                return _git(self.repo_path, "rev-parse", "HEAD").stdout.strip()

        from lib.dialogs.unstaged_dialogs import StageFilesDialog
        orig_init = StageFilesDialog.__init__

        def scripted_init(dlg, *a, **k):
            k["parent"] = None  # _Win is a plain object, not a QWidget
            orig_init(dlg, *a, **k)
            for i in range(dlg.file_list.count()):
                dlg.file_list.item(i).setCheckState(Qt.Checked)

        def scripted_exec(dlg):
            if action == "stage":
                dlg._on_stage()          # real handler: git add + accept
            elif action == "commit":
                dlg._on_commit_selected()  # real handler: set action + accept
            elif action == "amend":
                dlg._on_amend_selected()   # real handler: set action + accept
            else:
                dlg.action = action
                dlg.accept()
            return dlg.result()

        with mock.patch.object(StageFilesDialog, "__init__", scripted_init), \
             mock.patch.object(StageFilesDialog, "exec", scripted_exec):
            win = _Win(self.repo)
            win.handle_stage_files()
        return win

    def _status(self):
        return _git(self.repo, "status", "--porcelain").stdout

    def _head(self):
        return _git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def test_commit_lands_only_checked_files(self):
        pre_head = self._head()
        win = self._run("commit")
        self.assertNotEqual(self._head(), pre_head)
        shown = [ln for ln in _git(
            self.repo, "show", "--name-only", "--format=%s",
            "HEAD").stdout.splitlines() if ln]
        self.assertEqual(shown[0], "commit the new files")
        self.assertEqual(sorted(shown[1:]), ["new_a.txt", "new_b.txt"])
        self.assertNotIn("new_", self._status(),
                         "committed files must leave the untracked set")
        self.assertIn("save_undo_state", win.calls)
        self.assertEqual(win.last_head, pre_head,
                         "undo must snapshot the pre-commit HEAD")
        self.assertIn("load_history", win.calls)
        infos = [e for e in _FakeMessageBox.events if e[0] == "information"]
        self.assertTrue(any("Commit Successful" in e[1] for e in infos))

    def test_pre_staged_other_file_not_swept_in(self):
        with open(os.path.join(self.repo, "base.txt"), "w") as fh:
            fh.write("staged elsewhere\n")
        _git(self.repo, "add", "base.txt")
        pre_head = self._head()
        self._run("commit")
        committed = _git(self.repo, "show", "--name-only", "--format=",
                         "HEAD").stdout.splitlines()
        self.assertNotIn("base.txt", committed)
        self.assertIn("M  base.txt", self._status(),
                      "pre-staged change must stay staged, untouched")
        self.assertNotEqual(self._head(), pre_head)

    def test_message_cancel_stages_nothing(self):
        _FakeMessageDialog.accepted = False
        pre_head = self._head()
        win = self._run("commit")
        self.assertEqual(self._head(), pre_head)
        self.assertEqual(self._status().count("??"), 2,
                         "both files must remain untracked")
        self.assertNotIn("save_undo_state", win.calls)

    def test_stage_action_unchanged_still_stages_only(self):
        pre_head = self._head()
        win = self._run("stage")
        status = self._status()
        self.assertIn("A  new_a.txt", status)
        self.assertIn("A  new_b.txt", status)
        self.assertEqual(self._head(), pre_head)
        self.assertIn("load_history", win.calls)
        self.assertNotIn("save_undo_state", win.calls)
        infos = [e for e in _FakeMessageBox.events if e[0] == "information"]
        self.assertTrue(any("Files Added" in e[1] for e in infos))

    def test_amend_replaces_head_message_and_keeps_parent(self):
        pre_head = self._head()
        win = self._run("amend")
        self.assertNotEqual(self._head(), pre_head)
        self.assertEqual(
            _git(self.repo, "rev-list", "--count", "HEAD").stdout.strip(), "1",
            "amend must replace HEAD, not add a commit on top")
        shown = [ln for ln in _git(
            self.repo, "show", "--name-only", "--format=%s",
            "HEAD").stdout.splitlines() if ln]
        self.assertEqual(shown[0], "commit the new files")
        self.assertEqual(sorted(shown[1:]),
                         ["base.txt", "new_a.txt", "new_b.txt"])
        self.assertNotIn("new_", self._status(),
                         "amended files must leave the untracked set")
        self.assertIn("save_undo_state", win.calls)
        self.assertEqual(win.last_head, pre_head,
                         "undo must snapshot the pre-amend HEAD")
        infos = [e for e in _FakeMessageBox.events if e[0] == "information"]
        self.assertTrue(any("Amend Successful" in e[1] for e in infos))

    def test_amend_not_swept_pre_staged_other(self):
        with open(os.path.join(self.repo, "base.txt"), "w") as fh:
            fh.write("staged elsewhere\n")
        _git(self.repo, "add", "base.txt")
        self._run("amend")
        in_head = _git(self.repo, "show", "HEAD:base.txt").stdout
        self.assertEqual(in_head, "base\n",
                         "pre-staged base.txt change must not be swept into "
                         "the amend")
        self.assertIn("M  base.txt", self._status(),
                      "pre-staged change must stay staged, untouched")

    def test_amend_message_cancel_stages_nothing(self):
        _FakeMessageDialog.accepted = False
        pre_head = self._head()
        win = self._run("amend")
        self.assertEqual(self._head(), pre_head)
        self.assertEqual(self._status().count("??"), 2,
                         "both files must remain untracked")
        self.assertNotIn("save_undo_state", win.calls)


if __name__ == "__main__":
    unittest.main()
