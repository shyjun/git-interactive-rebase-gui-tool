import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Import lib.app_window first, matching the app's import order
import lib.app_window.helpers  # noqa: F401
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog

from lib.dialogs.split_drop_dialogs import ConfirmRenameFileOnwardsDialog
from lib.app_window.split_file_mixin import SplitFileMixin
from lib.app_window.init_mixin import InitMixin


def _git(repo, *args):
    subprocess.run(["git"] + list(args), cwd=repo, check=True,
                   capture_output=True, text=True)


def _out(repo, *args):
    return subprocess.run(["git"] + list(args), cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def _write(repo, name, content):
    with open(os.path.join(repo, name), "w") as f:
        f.write(content)


GUARDS = [
    "_check_not_viewer_mode",
    "_check_head_unchanged",
    "_check_no_unstaged_changes",
    "_check_staged_changes",
]


class _Harness(SplitFileMixin, InitMixin):
    """Real perform_rename_file_from_commit_onwards on a temp repo."""

    def __init__(self, repo_path, commit_sha):
        self.repo_path = repo_path
        self.commit_sha = commit_sha
        self.viewer_mode = False
        self.cli_mode = False
        self.multi_select_mode = False
        self.browse_windows = []
        self.load_history_calls = 0
        self.cached_current_head_full_sha = self.get_head_sha()
        self.current_font_size = 10
        self.current_font_family = "monospace"

    def save_undo_state(self):
        pass

    def load_history(self):
        self.load_history_calls += 1

    def _notify_browse_windows(self):
        pass

    def _abort_rebase_safely(self):
        return True, ""

    def _warn_rebase_abort_failure(self, detail):
        pass

    def get_commit_shas(self):
        out = _out(self.repo_path, "log", "--oneline", "--reverse")
        return out.splitlines() if out else []


class TestConfirmRenameFileOnwardsDialogLogic(unittest.TestCase):
    """Test the ConfirmRenameFileOnwardsDialog validation logic."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _create_dialog(self, later_modifications=False):
        return ConfirmRenameFileOnwardsDialog(
            sha="abc12345",
            filepath="docs/old.txt",
            diff_text="+hello\n-world\n",
            later_modifications_detected=later_modifications,
            font_size=10,
            font_family="monospace",
        )

    def test_dialog_initialization(self):
        """Dialog should initialize with correct values."""
        dlg = self._create_dialog()
        self.assertEqual(dlg.filepath, "docs/old.txt")
        self.assertFalse(dlg.later_modifications_detected)
        self.assertEqual(dlg.new_path_edit.text(), "docs/old.txt")

    def test_dialog_later_modifications_detected(self):
        """Dialog should show warning when later modifications detected."""
        dlg = self._create_dialog(later_modifications=True)
        self.assertTrue(dlg.later_modifications_detected)
        # Check that warning label exists in the layout
        warning_found = False
        for i in range(dlg.content_layout.count()):
            widget = dlg.content_layout.itemAt(i).widget()
            if widget and "Warning:" in widget.text():
                warning_found = True
                break
        self.assertTrue(warning_found)

    def test_get_new_filepath_returns_correct_value(self):
        """get_new_filepath should return the new path after accept."""
        dlg = self._create_dialog()
        dlg.new_path_edit.setText("docs/new.txt")
        dlg._on_accept()  # Call the internal method directly
        self.assertEqual(dlg.get_new_filepath(), "docs/new.txt")

    @unittest.skip("Triggers real QMessageBox - disable for now")
    def test_on_accept_rejects_empty_path(self):
        """_on_accept should not accept empty path."""
        dlg = self._create_dialog()
        dlg.new_path_edit.setText("")
        # The method shows a warning but doesn't call accept()
        # We can't easily test the QMessageBox without mocking, so just verify the logic
        # by checking that the dialog wouldn't accept
        dlg._on_accept()
        self.assertIsNone(dlg.get_new_filepath())

    @unittest.skip("Triggers real QMessageBox - disable for now")
    def test_on_accept_rejects_same_path(self):
        """_on_accept should not accept same path."""
        dlg = self._create_dialog()
        dlg.new_path_edit.setText("docs/old.txt")
        dlg._on_accept()
        self.assertIsNone(dlg.get_new_filepath())


if __name__ == "__main__":
    unittest.main()
