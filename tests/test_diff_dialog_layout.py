"""Unit tests for horizontal vs vertical (right-pane) layout options in diff dialogs."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from PySide6.QtWidgets import QApplication
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False


@unittest.skipUnless(HAS_PYSIDE, "PySide6 not available")
class TestDiffDialogLayoutOptions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])

    def test_single_commit_view_dialog_has_radio_buttons(self):
        from lib.dialogs.diff_dialogs import SingleCommitViewDialog

        dlg = SingleCommitViewDialog(
            repo_path=os.getcwd(),
            sha="18dd7c0f6",
            font_size=10,
            font_family=None,
            parent=None,
        )
        self.assertTrue(hasattr(dlg, "radio_diff_horiz"))
        self.assertTrue(hasattr(dlg, "radio_diff_vert"))
        self.assertEqual(dlg.radio_diff_horiz.text(), "diff at horiz")
        self.assertEqual(dlg.radio_diff_vert.text(), "diff at vertical")

    def test_toggle_to_vertical_shows_right_pane_and_hides_tab_diffs(self):
        from lib.dialogs.diff_dialogs import SingleCommitViewDialog

        dlg = SingleCommitViewDialog(
            repo_path=os.getcwd(),
            sha="18dd7c0f6",
            font_size=10,
            font_family=None,
            parent=None,
        )
        # Default is horiz
        self.assertEqual(dlg._diff_layout_mode, "horiz")
        self.assertTrue(dlg.v_diff_container.isHidden())
        self.assertFalse(dlg.filewise_diff_container.isHidden())
        self.assertFalse(dlg.treewise_diff_container.isHidden())

        # Toggle to vertical
        dlg.radio_diff_vert.setChecked(True)
        self.assertEqual(dlg._diff_layout_mode, "vertical")
        self.assertFalse(dlg.v_diff_container.isHidden())
        self.assertTrue(dlg.filewise_diff_container.isHidden())
        self.assertTrue(dlg.treewise_diff_container.isHidden())

        # Toggle back to horiz
        dlg.radio_diff_horiz.setChecked(True)
        self.assertEqual(dlg._diff_layout_mode, "horiz")
        self.assertTrue(dlg.v_diff_container.isHidden())
        self.assertFalse(dlg.filewise_diff_container.isHidden())
        self.assertFalse(dlg.treewise_diff_container.isHidden())

    def test_branch_diff_dialog_has_layout_toggle(self):
        from lib.dialogs.diff_dialogs import BranchDiffDialog

        dlg = BranchDiffDialog(
            repo_path=os.getcwd(),
            start_sha="11111111",
            end_sha="22222222",
            num_commits=1,
            diff_text="diff --git a/foo.c b/foo.c\n+test\n",
            files=["foo.c"],
            file_stats={"foo.c": (1, 0, 10, 11)},
            parent=None,
        )
        self.assertTrue(hasattr(dlg, "radio_diff_horiz"))
        self.assertTrue(hasattr(dlg, "radio_diff_vert"))

        # Default is horiz
        self.assertEqual(dlg._diff_layout_mode, "horiz")
        self.assertTrue(dlg.v_diff_container.isHidden())

        # Switch to vertical mode
        dlg.radio_diff_vert.setChecked(True)
        self.assertEqual(dlg._diff_layout_mode, "vertical")
        self.assertFalse(dlg.v_diff_container.isHidden())
        self.assertTrue(dlg.filewise_diff_container.isHidden())


if __name__ == "__main__":
    unittest.main()
