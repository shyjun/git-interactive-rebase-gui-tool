import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from PySide6.QtWidgets import QApplication, QDialog, QRadioButton
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False


class TestPullDialog(unittest.TestCase):
    """Widget-level behavior of the Pull strategy-chooser dialog."""

    @classmethod
    def setUpClass(cls):
        if HAS_PYSIDE and not QApplication.instance():
            cls.app = QApplication([])

    def setUp(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        from lib.dialogs.pull_dialog import PullDialog
        self.dlg = PullDialog(branch="main")

    def test_default_option_is_merge(self):
        self.assertEqual(self.dlg.get_selected_option(), "merge")
        self.assertTrue(self.dlg.merge_radio.isChecked())
        self.assertFalse(self.dlg.fetch_radio.isChecked())
        self.assertFalse(self.dlg.rebase_radio.isChecked())

    def test_radio_labels(self):
        self.assertEqual(self.dlg.fetch_radio.text(),
                         "Fetch only  (git fetch)")
        self.assertEqual(self.dlg.merge_radio.text(),
                         "Fetch and merge  (git pull --no-rebase)")
        self.assertEqual(self.dlg.rebase_radio.text(),
                         "Fetch and rebase  (git pull --rebase)")

    def test_git_command_mapping(self):
        cases = [
            ("merge", ["git", "pull", "--no-rebase"], "git pull"),
            ("rebase", ["git", "pull", "--rebase"], "git pull --rebase"),
            ("fetch", ["git", "fetch"], "git fetch"),
        ]
        radios = {"merge": self.dlg.merge_radio,
                  "rebase": self.dlg.rebase_radio,
                  "fetch": self.dlg.fetch_radio}
        for option, cmd, label in cases:
            radios[option].setChecked(True)
            self.assertEqual(self.dlg.get_selected_option(), option)
            self.assertEqual(self.dlg.get_git_command(), (cmd, label))

    def test_action_button_relabels_for_fetch(self):
        self.assertEqual(self.dlg.pull_btn.text(), "Pull")
        self.dlg.fetch_radio.setChecked(True)
        self.assertEqual(self.dlg.pull_btn.text(), "Fetch")
        self.dlg.merge_radio.setChecked(True)
        self.assertEqual(self.dlg.pull_btn.text(), "Pull")
        self.dlg.rebase_radio.setChecked(True)
        self.assertEqual(self.dlg.pull_btn.text(), "Pull")

    def test_action_button_is_default_and_cancel_rejects(self):
        self.assertTrue(self.dlg.pull_btn.isDefault())
        self.dlg.reject()
        self.assertEqual(self.dlg.result(), QDialog.Rejected)

    def test_dialog_is_modal_with_pull_title(self):
        self.assertEqual(self.dlg.windowTitle(), "Pull")
        self.assertTrue(self.dlg.isModal())

    def test_subtitle_names_upstream(self):
        from PySide6.QtWidgets import QLabel
        labels = [l for l in self.dlg.findChildren(QLabel)
                  if "origin/main" in l.text()]
        self.assertTrue(labels, "subtitle must name origin/<branch>")

    def test_only_three_radios_in_group(self):
        radios = self.dlg.button_group.buttons()
        self.assertEqual(len(radios), 3)


if __name__ == "__main__":
    unittest.main()
