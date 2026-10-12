import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from PySide6.QtWidgets import QApplication
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False


class TestPushDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if HAS_PYSIDE:
            if not QApplication.instance():
                cls.app = QApplication([])

    def test_warning_pixmap_generation(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        from lib.dialogs.push_dialog import create_warning_pixmap

        pixmap = create_warning_pixmap(44)
        self.assertFalse(pixmap.isNull())
        self.assertEqual(pixmap.width(), 44)
        self.assertEqual(pixmap.height(), 44)

    def test_default_selection_is_normal_push(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        from lib.dialogs.push_dialog import PushDialog

        dlg = PushDialog(is_dark=False, remote="origin")
        self.assertEqual(dlg.get_selected_option(), PushDialog.OPTION_NORMAL)
        cmd, label = dlg.get_git_command()
        self.assertEqual(cmd, ["git", "push"])
        self.assertEqual(label, "git push")
        self.assertTrue(dlg.normal_radio.isChecked())
        self.assertFalse(dlg.force_radio.isChecked())
        self.assertFalse(dlg.lease_radio.isChecked())

    def test_select_force_push(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        from lib.dialogs.push_dialog import PushDialog

        dlg = PushDialog(is_dark=False)
        dlg.force_radio.setChecked(True)
        self.assertEqual(dlg.get_selected_option(), PushDialog.OPTION_FORCE)
        cmd, label = dlg.get_git_command()
        self.assertEqual(cmd, ["git", "push", "--force"])
        self.assertEqual(label, "git push --force")

    def test_select_force_with_lease_push(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        from lib.dialogs.push_dialog import PushDialog

        dlg = PushDialog(is_dark=False)
        dlg.lease_radio.setChecked(True)
        self.assertEqual(dlg.get_selected_option(), PushDialog.OPTION_FORCE_WITH_LEASE)
        cmd, label = dlg.get_git_command()
        self.assertEqual(cmd, ["git", "push", "--force-with-lease"])
        self.assertEqual(label, "git push --force-with-lease")

    def test_custom_remote_in_header(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        from lib.dialogs.push_dialog import PushDialog

        dlg = PushDialog(is_dark=True, remote="upstream")
        self.assertIn("upstream", dlg.header_subtitle.text())

    def test_dialog_push_button_is_default(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        from lib.dialogs.push_dialog import PushDialog

        dlg = PushDialog(is_dark=False)
        self.assertTrue(dlg.push_btn.isDefault())


if __name__ == "__main__":
    unittest.main()
