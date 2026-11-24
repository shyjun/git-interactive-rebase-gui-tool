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


    def test_filewise_tree_tabs_expandable_on_open(self):
        """Regression: set_diff_layout_mode must NOT clobber the user-collapsed state.

        SingleCommitViewDialog opens with filewise_expanded=False, so both
        the Filewise Diff and Tree-wise Diff tabs start collapsed.  Calling
        set_diff_layout_mode("horiz") during init must leave that collapsed
        state untouched so the user can expand the panes by clicking the tab.
        """
        from lib.dialogs.diff_dialogs import SingleCommitViewDialog

        dlg = SingleCommitViewDialog(
            repo_path=os.getcwd(),
            sha="18dd7c0f6",
            font_size=10,
            font_family=None,
            parent=None,
        )
        # Both file-list panes start hidden (▶ collapsed)
        self.assertTrue(dlg.filewise_file_list.isHidden(),
                        "filewise file list must start collapsed")
        self.assertTrue(dlg.treewise_tree.isHidden(),
                        "treewise tree must start collapsed")
        # The splitter handle must NOT be enabled while the pane is hidden
        self.assertFalse(dlg.filewise_splitter.handle(1).isEnabled(),
                         "filewise splitter handle must stay disabled when collapsed")
        self.assertFalse(dlg.treewise_splitter.handle(1).isEnabled(),
                         "treewise splitter handle must stay disabled when collapsed")

        # Simulate user clicking the ▶ Filewise Diff tab label to expand it
        dlg._toggle_filewise_file_list()
        self.assertFalse(dlg.filewise_file_list.isHidden(),
                         "filewise file list must be visible after toggle")
        self.assertTrue(dlg.filewise_splitter.handle(1).isEnabled(),
                        "filewise splitter handle must be enabled after expanding")

        # Clicking again collapses it
        dlg._toggle_filewise_file_list()
        self.assertTrue(dlg.filewise_file_list.isHidden(),
                        "filewise file list must be hidden after second toggle")
        self.assertFalse(dlg.filewise_splitter.handle(1).isEnabled(),
                         "filewise splitter handle must be disabled after collapsing")

    def test_vertical_mode_expands_file_and_tree_lists(self):
        """In vertical mode there is no bottom diff pane, so file/tree lists must be expanded."""
        from lib.dialogs.diff_dialogs import SingleCommitViewDialog

        dlg = SingleCommitViewDialog(
            repo_path=os.getcwd(),
            sha="18dd7c0f6",
            font_size=10,
            font_family=None,
            parent=None,
        )
        self.assertTrue(dlg.filewise_file_list.isHidden())
        self.assertTrue(dlg.treewise_tree.isHidden())

        # Switch to vertical mode: both filewise and treewise lists must become visible
        dlg.radio_diff_vert.setChecked(True)
        self.assertFalse(dlg.filewise_file_list.isHidden(),
                         "filewise file list must be visible in vertical mode")
        self.assertFalse(dlg.treewise_tree.isHidden(),
                         "treewise tree must be visible in vertical mode")
        self.assertIn("\u25BC", dlg.tab_widget.tabText(dlg._filewise_tab_idx))
        self.assertIn("\u25BC", dlg.tab_widget.tabText(dlg._treewise_tab_idx))

    def test_vertical_to_horiz_restores_collapse_state(self):
        """Switching back from vertical to horiz must respect the tab-expand state."""
        from lib.dialogs.diff_dialogs import SingleCommitViewDialog

        dlg = SingleCommitViewDialog(
            repo_path=os.getcwd(),
            sha="18dd7c0f6",
            font_size=10,
            font_family=None,
            parent=None,
        )
        # Start collapsed, switch to vert then back to horiz
        dlg.radio_diff_vert.setChecked(True)
        dlg.radio_diff_horiz.setChecked(True)

        # File list should still be collapsed (user never manually expanded it)
        self.assertTrue(dlg.filewise_file_list.isHidden(),
                        "filewise file list should remain collapsed after vert→horiz cycle")
        self.assertTrue(dlg.treewise_tree.isHidden(),
                        "treewise tree should remain collapsed after vert→horiz cycle")
        # But toggling should still work
        dlg._toggle_filewise_file_list()
        self.assertFalse(dlg.filewise_file_list.isHidden(),
                         "filewise file list must expand after toggle post-cycle")


if __name__ == "__main__":
    unittest.main()
