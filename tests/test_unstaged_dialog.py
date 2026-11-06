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

    def test_unstaged_diff_panes_have_minimum_heights(self):
        """Plain Diff, Filewise and Tree-wise panes must each keep a floor.

        The plain diff view inherited no minimum from BranchDiffDialog and
        the two splitter panes bottomed out at 100px of diff text, so a
        small window or a dragged splitter handle could leave no room to
        read the diff.
        """
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
        for name in ("side_diff_view", "filewise_diff_view", "treewise_diff_view"):
            pane = getattr(dlg, name)
            self.assertGreaterEqual(
                pane.minimumHeight(), 200,
                f"{name} must keep at least 200px, got {pane.minimumHeight()}",
            )

    def test_unstaged_list_and_tree_panes_never_collapse(self):
        """The filewise list and treewise tree must stay on screen.

        Clicking the already-active tab label used to hide the pane outright
        (BranchDiffDialog._on_tab_bar_clicked -> setVisible(False) +
        setSizes([0, 1000])), and both splitters allowed a handle drag to do
        the same.  In this dialog the pane keeps a 150px floor, the
        splitters refuse to collapse either side, and tab-label clicks never
        reach the toggles.
        """
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

        # Tab-label clicks must not reach the base-class collapse toggles.
        toggled = []
        dlg._toggle_filewise_file_list = lambda: toggled.append("filewise")
        dlg._toggle_treewise_file_list = lambda: toggled.append("treewise")
        dlg._on_tab_bar_clicked(1)
        dlg._on_tab_bar_clicked(2)
        self.assertEqual(toggled, [])

        # Neither pane is ever explicitly hidden.
        self.assertFalse(dlg.filewise_file_list.isHidden())
        self.assertFalse(dlg.treewise_tree.isHidden())

        # Floors and non-collapsible splitters.
        self.assertGreaterEqual(dlg.filewise_file_list.minimumHeight(), 150)
        self.assertGreaterEqual(dlg.treewise_tree.minimumHeight(), 150)
        for splitter in (dlg.filewise_splitter, dlg.treewise_splitter):
            self.assertFalse(splitter.isCollapsible(0))
            self.assertFalse(splitter.isCollapsible(1))

    def _assert_tree_stats_delegate_owned_by_tree(self, tree):
        """The column-1 TreeStatsDelegate must be owned by the tree itself.

        A parentless temporary delegate loses its Python wrapper right after
        the construction statement; on PySide6 6.9.0 shiboken then destroys
        the C++ delegate while the view keeps a dangling pointer, and the
        first layout timer after show() segfaults in
        QTreeView::indexRowSizeHint (the 'Show unstaged changes' crash).
        Parenting the delegate to the tree keeps it alive on every version.
        """
        import gc

        delegate = tree.itemDelegateForColumn(1)
        self.assertIsNotNone(delegate)
        self.assertIs(delegate.parent(), tree)
        # Simulate wrapper collection, then verify the C++ object survived.
        gc.collect()
        delegate = tree.itemDelegateForColumn(1)
        self.assertIsNotNone(delegate)
        self.assertIs(delegate.parent(), tree)

    def test_unstaged_diff_dialog_tree_delegate_owned_by_tree(self):
        """Regression: UnstagedDiffDialog's stats delegate must outlive GC."""
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
        self._assert_tree_stats_delegate_owned_by_tree(dlg.treewise_tree)

    def test_commit_selectively_dialog_tree_delegate_owned_by_tree(self):
        """Same ownership invariant for the dialog built by 'Commit Selectively'."""
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")

        from lib.dialogs.unstaged_dialogs import CommitSelectivelyDialog

        dlg = CommitSelectivelyDialog(
            repo_path=os.getcwd(),
            files=["src/version.c"],
            file_stats={"src/version.c": (1, 0, 100, 101)},
            font_size=10,
            font_family=None,
        )
        self._assert_tree_stats_delegate_owned_by_tree(dlg.treewise_tree)


class TestExitButtonLabel(unittest.TestCase):
    """Startup shows 'Exit' (rejecting quits the tool); Rescan shows 'Close'
    (rejecting just closes the dialog and the tool keeps running)."""

    @classmethod
    def setUpClass(cls):
        if HAS_PYSIDE and not QApplication.instance():
            cls.app = QApplication([])

    def _dialog(self, **kwargs):
        from lib.dialogs.unstaged_dialogs import UnstagedChangesDialog
        return UnstagedChangesDialog(2, font_size=10, **kwargs)

    def test_startup_dialog_shows_exit(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        dlg = self._dialog(from_rescan=False)
        self.assertEqual(dlg.exit_btn.text(), "Exit")
        self.assertEqual(dlg.exit_btn.toolTip(), "Exit the application.")

    def test_rescan_dialog_shows_close(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        dlg = self._dialog(from_rescan=True)
        self.assertEqual(dlg.exit_btn.text(), "Close")
        self.assertEqual(dlg.exit_btn.toolTip(), "Close this dialog and return to the tool.")

    def test_default_is_startup_exit(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        dlg = self._dialog()
        self.assertEqual(dlg.exit_btn.text(), "Exit")


if __name__ == "__main__":
    unittest.main()
