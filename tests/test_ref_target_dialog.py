import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from PySide6.QtWidgets import QApplication
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False


def _git(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    )


class TestRefTargetDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if HAS_PYSIDE:
            if not QApplication.instance():
                cls.app = QApplication([])

    def setUp(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        self.repo = tempfile.mkdtemp(prefix="ref_target_")
        self.addCleanup(shutil.rmtree, self.repo, True)
        _git(self.repo, "init", "-qb", "main")
        with open(os.path.join(self.repo, "a.txt"), "w") as fh:
            fh.write("one\n")
        _git(self.repo, "add", "a.txt")
        _git(self.repo, "commit", "-qm", "first commit")
        _git(self.repo, "checkout", "-qb", "feature")
        with open(os.path.join(self.repo, "b.txt"), "w") as fh:
            fh.write("two\n")
        _git(self.repo, "add", "b.txt")
        _git(self.repo, "commit", "-qm", "second commit")
        _git(self.repo, "checkout", "-q", "main")

    def _dialog(self, **kwargs):
        from lib.dialogs import RefTargetDialog
        kwargs.setdefault("title", "Test")
        kwargs.setdefault("label_text", "Pick a ref:")
        return RefTargetDialog(self.repo, **kwargs)

    def test_combo_excludes_current_branch(self):
        dlg = self._dialog(exclude_current=True)
        items = [dlg.ref_combo.itemText(i)
                 for i in range(dlg.ref_combo.count())]
        self.assertIn("feature", items)
        self.assertNotIn("main", items)

    def test_combo_includes_current_branch_when_not_excluded(self):
        dlg = self._dialog(exclude_current=False)
        items = [dlg.ref_combo.itemText(i)
                 for i in range(dlg.ref_combo.count())]
        self.assertIn("main", items)
        self.assertIn("feature", items)

    def test_empty_input_disables_ok(self):
        dlg = self._dialog()
        self.assertFalse(dlg.ok_btn.isEnabled())
        self.assertIn("Type or pick", dlg.detail_label.text())

    def test_invalid_ref_disables_ok(self):
        dlg = self._dialog()
        dlg.ref_combo.setEditText("no-such-ref-xyz")
        dlg._validate()
        self.assertFalse(dlg.ok_btn.isEnabled())
        self.assertIn("not a valid ref", dlg.detail_label.text())

    def test_valid_ref_enables_ok_and_shows_detail(self):
        dlg = self._dialog()
        dlg.ref_combo.setEditText("feature")
        dlg._validate()
        self.assertTrue(dlg.ok_btn.isEnabled())
        detail = dlg.detail_label.text()
        self.assertIn("second commit", detail)
        short = _git(self.repo, "rev-parse", "--short",
                     "feature").stdout.strip()
        self.assertIn(short, detail)

    def test_head_sha_accepted(self):
        dlg = self._dialog()
        full = _git(self.repo, "rev-parse", "HEAD").stdout.strip()
        dlg.ref_combo.setEditText(full)
        dlg._validate()
        self.assertTrue(dlg.ok_btn.isEnabled())

    def test_ref_property_strips_whitespace(self):
        dlg = self._dialog()
        dlg.ref_combo.setEditText("  feature  ")
        self.assertEqual(dlg.ref, "feature")

    def test_ok_button_label_customizable(self):
        dlg = self._dialog(ok_text="Rebase")
        self.assertEqual(dlg.ok_btn.text(), "Rebase")

    def test_accept_blocked_while_invalid(self):
        from PySide6.QtWidgets import QDialog
        dlg = self._dialog()
        dlg.ref_combo.setEditText("no-such-ref-xyz")
        dlg.accept()
        self.assertNotEqual(dlg.result(), QDialog.Accepted)

    def test_current_branch_detail_says_matches_tip(self):
        dlg = self._dialog(exclude_current=False)
        dlg.ref_combo.setEditText("main")
        dlg._validate()
        self.assertTrue(dlg.ok_btn.isEnabled())
        self.assertIn("matches current branch tip", dlg.detail_label.text())


if __name__ == "__main__":
    unittest.main()
