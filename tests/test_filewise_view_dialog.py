"""Regression tests for FileWiseViewDialog handler methods.

54a47ee ("Add 'Rename file from this commit onwards' feature") reshuffled
the methods at the end of FileWiseViewDialog and

  - dropped ``copy_filename_to_clipboard`` entirely (menu click ->
    AttributeError), and
  - gave ``refine_file`` the clipboard body (menu click -> silently copies
    the filename instead of opening Refine Changes).

e0d2ac3 only silenced the resulting NameError (``filename`` -> ``filepath``),
so both menu items stayed broken while the suite stayed green.  These tests
pin the two behaviours so the shuffle cannot regress unnoticed.
"""

import ast
import os
import time
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")

try:
    from unittest import mock

    from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False


def _method_source(class_name, method_name):
    path = os.path.join(ROOT, "lib", "dialogs", "diff_dialogs.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        if cls.name == class_name:
            for fn in [n for n in cls.body if isinstance(n, ast.FunctionDef)]:
                if fn.name == method_name:
                    return ast.get_source_segment(src, fn)
    raise AssertionError(f"{class_name}.{method_name} not found")


@unittest.skipUnless(HAS_PYSIDE, "PySide6 not available")
class TestFileWiseViewDialogCopyFilename(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])

    def test_copy_filename_to_clipboard_exists(self):
        from lib.dialogs.diff_dialogs import FileWiseViewDialog
        self.assertTrue(
            hasattr(FileWiseViewDialog, "copy_filename_to_clipboard"),
            "FileWiseViewDialog must provide copy_filename_to_clipboard "
            "(lost in 54a47ee's method shuffle)",
        )

    def test_copy_filename_to_clipboard_copies(self):
        from lib.dialogs.diff_dialogs import FileWiseViewDialog

        class _Stub:
            pass

        with mock.patch.object(QMessageBox, "information", return_value=0):
            FileWiseViewDialog.copy_filename_to_clipboard(_Stub(),
                                                          "foo/bar.py")
        self.assertEqual(QApplication.clipboard().text(), "foo/bar.py")

    def test_copy_body_matches_intact_reference(self):
        from lib.dialogs.diff_dialogs import (
            FileWiseViewDialog,
            SingleCommitViewDialog,
        )
        self.assertEqual(
            FileWiseViewDialog.copy_filename_to_clipboard.__code__.co_code,
            SingleCommitViewDialog.copy_filename_to_clipboard.__code__.co_code,
            "FileWiseViewDialog.copy_filename_to_clipboard must behave like "
            "the intact SingleCommitViewDialog one",
        )


@unittest.skipUnless(HAS_PYSIDE, "PySide6 not available")
class TestFileWiseViewDialogRefineFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])

    def _run_refine(self, filepath):
        from lib.dialogs.diff_dialogs import FileWiseViewDialog

        class _MainWindow(QMainWindow):
            def __init__(self):
                super().__init__()
                self.calls = []

            def perform_refine_changes(self, sha, path):
                self.calls.append((sha, path))

        class _FakeDialog:
            """Provides exactly the surface refine_file uses."""

            def __init__(self, main_win):
                self._main_win = main_win
                self.sha = "abc1234567890"
                self.accepted = False

            def parent(self):
                return self._main_win

            def accept(self):
                self.accepted = True

        win = _MainWindow()
        dlg = _FakeDialog(win)
        # Patch the info box too: if the clipboard body ever comes back it
        # would pop a modal dialog and hang the suite.
        with mock.patch.object(QMessageBox, "information", return_value=0):
            FileWiseViewDialog.refine_file(dlg, filepath)
            deadline = time.time() + 2.0
            while not win.calls and time.time() < deadline:
                QApplication.processEvents()
                time.sleep(0.001)
        win.close()
        return dlg, win.calls

    def test_refine_file_opens_refine_changes(self):
        dlg, calls = self._run_refine("docs/x.py")
        self.assertTrue(dlg.accepted, "refine must close the dialog first")
        self.assertEqual(
            calls, [("abc1234567890", "docs/x.py")],
            "refine_file must delegate to perform_refine_changes",
        )

    def test_refine_file_does_not_touch_clipboard(self):
        QApplication.clipboard().setText("sentinel")
        self._run_refine("docs/x.py")
        self.assertEqual(
            QApplication.clipboard().text(), "sentinel",
            "refine_file must not copy anything to the clipboard "
            "(54a47ee regression)",
        )

    def test_refine_body_delegates_not_copies(self):
        body = _method_source("FileWiseViewDialog", "refine_file")
        self.assertIn("perform_refine_changes", body)
        self.assertNotIn("clipboard", body)
        self.assertNotIn("QMessageBox", body)


if __name__ == "__main__":
    unittest.main()
