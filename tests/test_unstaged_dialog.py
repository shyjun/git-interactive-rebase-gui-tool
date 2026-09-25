import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from PySide6.QtWidgets import QApplication
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False


class TestUnstagedDialogImport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if HAS_PYSIDE:
            if not QApplication.instance():
                cls.app = QApplication([])

    def test_dialog_imports_without_circular_dependency(self):
        """Verify that importing dialog modules before or alongside git_helpers causes no circular import error."""
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")

        # Import dialog modules directly
        from lib.dialogs.unstaged_dialogs import UnstagedChangesDialog
        from lib.dialogs.diff_dialogs import UnstagedDiffDialog

        self.assertIsNotNone(UnstagedChangesDialog)
        self.assertIsNotNone(UnstagedDiffDialog)

    def test_unstaged_diff_dialog_instantiation(self):
        """Verify UnstagedDiffDialog constructs cleanly with mock data."""
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")

        from lib.dialogs.diff_dialogs import UnstagedDiffDialog

        dlg = UnstagedDiffDialog(
            repo_path=os.getcwd(),
            files=["src/version.c"],
            diff_text="diff --git a/src/version.c b/src/version.c\n--- a/src/version.c\n+++ b/src/version.c\n",
            file_stats={"src/version.c": (1, 0, 100, 101)},
            branch="master",
            head_sha="760e813eefef620f1412fe7ec7439bb06ff2a92a",
            font_size=10,
            font_family=None,
            parent=None
        )
        self.assertEqual(dlg.windowTitle(), "Unstaged Changes")


if __name__ == "__main__":
    unittest.main()
