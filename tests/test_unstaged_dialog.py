import ast
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
        the same.  In this dialog the pane keeps a 60px floor, the splitters
        refuse to collapse either side, and tab-label clicks never reach the
        toggles.
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
        self.assertGreaterEqual(dlg.filewise_file_list.minimumHeight(), 60)
        self.assertGreaterEqual(dlg.treewise_tree.minimumHeight(), 60)
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


class TestShowUnstagedChangesWithoutMainWindow(unittest.TestCase):
    """At startup the warning dialog has no parent main window yet.

    The entry point builds it (git_interactive_rebase.py) before
    GitInteractiveRebaseApp exists, so 'Show unstaged changes' must close the
    dialog with ViewUnstagedResult - letting startup defer the viewer to when
    the window is up - instead of popping 'The main window is not available.'
    """

    @classmethod
    def setUpClass(cls):
        if HAS_PYSIDE and not QApplication.instance():
            cls.app = QApplication([])

    def _dialog(self, **kwargs):
        from lib.dialogs.unstaged_dialogs import UnstagedChangesDialog
        return UnstagedChangesDialog(2, font_size=10, **kwargs)

    def test_parentless_dialog_returns_view_result(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")

        from PySide6.QtWidgets import QMessageBox
        from lib.dialogs.unstaged_dialogs import UnstagedChangesDialog

        dlg = self._dialog(repo_path=os.getcwd())
        self.assertIsNone(dlg.parent(), "startup dialog must have no parent")

        warnings = []
        original = QMessageBox.warning
        QMessageBox.warning = lambda *a, **k: warnings.append(a)
        try:
            dlg.show_unstaged_changes()
        finally:
            QMessageBox.warning = original

        self.assertEqual(
            dlg.result(), UnstagedChangesDialog.ViewUnstagedResult,
            "startup click must report the deferred-view result to the entry point",
        )
        self.assertEqual(warnings, [], "no 'main window is not available' popup")

    def test_result_code_does_not_collide(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")

        from lib.dialogs.unstaged_dialogs import UnstagedChangesDialog

        codes = [
            UnstagedChangesDialog.CommitEachResult,
            UnstagedChangesDialog.BulkCommitResult,
            UnstagedChangesDialog.AmendResult,
            UnstagedChangesDialog.ViewerModeResult,
            UnstagedChangesDialog.DiscardResult,
            UnstagedChangesDialog.MergeResult,
            UnstagedChangesDialog.SelectiveCommitResult,
            UnstagedChangesDialog.ViewUnstagedResult,
        ]
        self.assertEqual(len(codes), len(set(codes)), "result codes must be unique")

    def test_parent_with_handler_still_delegates(self):
        """The rescan path (parent = main window) must keep delegating."""
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")

        from PySide6.QtWidgets import QWidget
        from lib.dialogs.unstaged_dialogs import UnstagedChangesDialog

        class _StubMain(QWidget):
            def __init__(self):
                super().__init__()
                self.calls = []

            def handle_view_unstaged_diff(self, parent=None):
                self.calls.append(parent)

        stub = _StubMain()
        try:
            dlg = self._dialog(repo_path=os.getcwd(), parent=stub)
            dlg.show_unstaged_changes()
            self.assertEqual(stub.calls, [dlg],
                             "handler must be called with the dialog as parent")
            self.assertNotEqual(dlg.result(),
                                UnstagedChangesDialog.ViewUnstagedResult)
        finally:
            stub.close()
            stub.deleteLater()


class TestStartupDeferralWiring(unittest.TestCase):
    """git_interactive_rebase.py must defer the viewer until the window exists.

    The startup warning dialog runs before GitInteractiveRebaseApp is built, so
    its ViewUnstagedResult has to be carried across to a deferred
    handle_view_unstaged_diff call after window.show().
    """

    @classmethod
    def setUpClass(cls):
        path = os.path.join(os.path.dirname(__file__), "..", "git_interactive_rebase.py")
        with open(path, encoding="utf-8") as fh:
            cls.tree = ast.parse(fh.read())

    def test_flag_initialized_before_use(self):
        flags = [
            n for n in ast.walk(self.tree)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "deferred_view_unstaged"
                    for t in n.targets)
            and isinstance(n.value, ast.Constant) and n.value.value is False
        ]
        self.assertTrue(flags, "deferred_view_unstaged must be initialised to False")

    def test_view_result_sets_flag(self):
        found = False
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
                continue
            if not any(isinstance(c, ast.Attribute) and c.attr == "ViewUnstagedResult"
                       for c in ast.walk(node.test)):
                continue
            for stmt in node.body:
                for sub in ast.walk(stmt):
                    if (isinstance(sub, ast.Assign)
                            and any(isinstance(t, ast.Name) and t.id == "deferred_view_unstaged"
                                    for t in sub.targets)
                            and isinstance(sub.value, ast.Constant)
                            and sub.value.value is True):
                        found = True
        self.assertTrue(found,
                        "the ViewUnstagedResult branch must set deferred_view_unstaged")

    def test_flag_defers_viewer_call(self):
        found = False
        for node in ast.walk(self.tree):
            if (isinstance(node, ast.If)
                    and isinstance(node.test, ast.Name)
                    and node.test.id == "deferred_view_unstaged"):
                dump = ast.dump(node)
                if "singleShot" in dump and "handle_view_unstaged_diff" in dump:
                    found = True
        self.assertTrue(
            found,
            "deferred_view_unstaged must gate a singleShot that opens the viewer",
        )


if __name__ == "__main__":
    unittest.main()
