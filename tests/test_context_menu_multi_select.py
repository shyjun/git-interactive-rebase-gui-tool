"""Coverage for multi-select guards in file context menus.

Every file-context menu offers single-file actions (Blame, Diff-ref, Copy
filename/fullpath, Rename/Remove onwards, Refine, Browse file log, Open with
system default app) that must be greyed out when more than one file is
checked.  The static (AST) tests parse the menu methods and assert that

  1. the known inventory of 13 menu methods is intact (a renamed or newly
     added menu must be registered here on purpose), and
  2. each menu computes ``multi_select`` from its checked-file helpers
     *before* building the menu, and
  3. every single-file QAction and the Open submenu are disabled via
     ``setEnabled(not multi_select)`` / ``enabled=not multi_select``.

Multi-file actions (Move/Drop) are explicitly allowlisted and exempt.

The runtime tests cover the two behaviours the guards rely on:
  - context-menu Drop drops every checked file (not just the clicked one),
  - add_open_with_system_default_action honours enabled=False.
"""

import ast
import os
import time
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")

try:
    from PySide6.QtWidgets import (
        QApplication,
        QMainWindow,
        QMenu,
        QWidget,
    )
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False

SOURCE_FILES = [
    "lib/app_window/diff_mixin.py",
    "lib/dialogs/diff_dialogs.py",
    "lib/dialogs/split_drop_dialogs.py",
]

# The full inventory of file-context menu methods that offer single-file
# actions.  Keys are source files, values are (class, method) pairs.
EXPECTED_MENUS = {
    "lib/app_window/diff_mixin.py": [
        ("DiffMixin", "show_filewise_context_menu"),
        ("DiffMixin", "show_treewise_context_menu"),
    ],
    "lib/dialogs/diff_dialogs.py": [
        ("BranchDiffDialog", "show_treewise_context_menu"),
        ("BranchDiffDialog", "show_filewise_context_menu"),
        ("SingleCommitViewDialog", "show_treewise_context_menu"),
        ("SingleCommitViewDialog", "show_filewise_context_menu"),
        ("FileWiseViewDialog", "show_file_context_menu"),
    ],
    "lib/dialogs/split_drop_dialogs.py": [
        ("SplitCommitDialog", "show_filewise_context_menu"),
        ("SplitCommitDialog", "show_treewise_context_menu"),
        ("DropFileFromCommitDialog", "show_filewise_context_menu"),
        ("DropFileFromCommitDialog", "show_treewise_context_menu"),
        ("RefineFileSelectDialog", "show_filewise_context_menu"),
        ("RefineFileSelectDialog", "show_treewise_context_menu"),
    ],
}

# QAction labels that legitimately operate on the whole checked selection.
MULTI_FILE_LABELS = {
    "Move file changes out of this commit",
    "Move selected file changes out of this commit",
    "Move selected files changes out of this commit",
    "Drop file changes from this commit",
}

# Actions whose label is built dynamically (``move_label`` / ``drop_label``);
# these are the multi-file Move/Drop entries.
MULTI_FILE_VARIABLES = {"move_action", "drop_action"}

# Every single-file action label that must be guarded when present.
SINGLE_FILE_LABELS = {
    "Blame file",
    "Diff against a different version of this file",
    "Copy filename to clipboard",
    "Copy fullpath to clipboard",
    "Rename file from this commit onwards",
    "Remove file from this commit onwards",
    "Refine/Edit changes in selected file",
    "Refine changes in selected file",
    "Browse file log",
}

PREAMBLE = "multi_select = len(checked_files) > 1"


def _read(relpath):
    with open(os.path.join(ROOT, relpath), encoding="utf-8") as f:
        return f.read()


def _iter_menus(src):
    """Yield (class_name, function_node, source_segment) for menu methods.

    Discovery rule: ``show_*context_menu*`` methods — deliberately narrow so
    helpers like ``_drop_from_context_menu`` are not mistaken for menus.
    """
    tree = ast.parse(src)
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        for fn in [n for n in cls.body if isinstance(n, ast.FunctionDef)]:
            if fn.name.startswith("show_") and "context_menu" in fn.name:
                yield cls.name, fn, ast.get_source_segment(src, fn)


def _qactions(fn):
    """Yield (variable_name, label_expression_ast) for each QAction assign."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if ast.unparse(node.value.func) == "QAction" and node.value.args:
                yield ast.unparse(node.targets[0]), node.value.args[0]


class TestContextMenuInventory(unittest.TestCase):
    def test_expected_menu_inventory(self):
        """The 13 known menus exist; no menu silently appears or vanishes."""
        found = {}
        for relpath in SOURCE_FILES:
            found[relpath] = [
                (cls, fn.name)
                for cls, fn, _ in _iter_menus(_read(relpath))
            ]
        self.assertEqual(found, EXPECTED_MENUS)


class TestMultiSelectGuards(unittest.TestCase):
    def test_every_menu_computes_multi_select(self):
        for relpath in SOURCE_FILES:
            for cls, fn, segment in _iter_menus(_read(relpath)):
                with self.subTest(menu=f"{relpath}::{cls}.{fn.name}"):
                    self.assertIn(
                        "checked_files = self._checked_", segment,
                        f"{cls}.{fn.name} must read the checked files via "
                        f"the class _checked_* helper",
                    )
                    self.assertIn(
                        PREAMBLE, segment,
                        f"{cls}.{fn.name} must compute multi_select",
                    )

    def test_open_with_submenu_disabled_on_multi_select(self):
        """The Open > With System Default App submenu is single-file too."""
        for relpath in SOURCE_FILES:
            for cls, fn, _ in _iter_menus(_read(relpath)):
                with self.subTest(menu=f"{relpath}::{cls}.{fn.name}"):
                    calls = [
                        n for n in ast.walk(fn)
                        if isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Name)
                        and n.func.id == "add_open_with_system_default_action"
                    ]
                    self.assertEqual(
                        len(calls), 1,
                        f"{cls}.{fn.name} must add exactly one Open submenu",
                    )
                    call = calls[0]
                    kwargs = {k.arg: ast.unparse(k.value) for k in call.keywords}
                    self.assertEqual(
                        kwargs.get("enabled"), "not multi_select",
                        f"{cls}.{fn.name}: Open submenu must pass "
                        f"enabled=not multi_select",
                    )
                    preamble_lines = [
                        n.lineno for n in ast.walk(fn)
                        if isinstance(n, ast.Assign)
                        and any(
                            isinstance(t, ast.Name) and t.id == "multi_select"
                            for t in n.targets
                        )
                    ]
                    self.assertTrue(
                        preamble_lines and preamble_lines[0] < call.lineno,
                        f"{cls}.{fn.name}: multi_select must be computed "
                        f"before the Open submenu is added",
                    )

    def test_single_file_actions_are_guarded(self):
        for relpath in SOURCE_FILES:
            for cls, fn, segment in _iter_menus(_read(relpath)):
                for var, label_node in _qactions(fn):
                    if isinstance(label_node, ast.Constant):
                        label = label_node.value
                        if label in MULTI_FILE_LABELS:
                            continue
                        self.assertIn(
                            label, SINGLE_FILE_LABELS,
                            f"{cls}.{fn.name}: QAction {label!r} is not "
                            f"classified — add it to SINGLE_FILE_LABELS (and "
                            f"guard it) or MULTI_FILE_LABELS if it acts on "
                            f"the whole selection",
                        )
                        expected = f"{var}.setEnabled(not multi_select)"
                        with self.subTest(
                            menu=f"{relpath}::{cls}.{fn.name}", action=label
                        ):
                            self.assertIn(
                                expected, segment,
                                f"{cls}.{fn.name}: single-file action "
                                f"{label!r} must be disabled with "
                                f"'{expected}'",
                            )
                    else:
                        # Dynamically labelled action: only Move/Drop may be
                        # multi-file, everything else must be guarded.
                        with self.subTest(
                            menu=f"{relpath}::{cls}.{fn.name}", action=var
                        ):
                            if var not in MULTI_FILE_VARIABLES:
                                expected = f"{var}.setEnabled(not multi_select)"
                                self.assertIn(
                                    expected, segment,
                                    f"{cls}.{fn.name}: dynamically labelled "
                                    f"action '{var}' must either be guarded "
                                    f"with '{expected}' or allowlisted in "
                                    f"MULTI_FILE_VARIABLES",
                                )

    def test_every_labelled_single_file_action_is_in_the_contract(self):
        """Labels found in menus and in SINGLE_FILE_LABELS stay in sync."""
        seen = set()
        for relpath in SOURCE_FILES:
            for _, fn, _ in _iter_menus(_read(relpath)):
                for _, label_node in _qactions(fn):
                    if isinstance(label_node, ast.Constant):
                        label = label_node.value
                        if label in SINGLE_FILE_LABELS:
                            seen.add(label)
        self.assertEqual(
            seen, SINGLE_FILE_LABELS,
            "SINGLE_FILE_LABELS must list exactly the single-file action "
            f"labels present in the menus; stale: {SINGLE_FILE_LABELS - seen}, "
            f"missing: {seen - SINGLE_FILE_LABELS}",
        )


@unittest.skipUnless(HAS_PYSIDE, "PySide6 not available")
class TestContextMenuDropChecksAllFiles(unittest.TestCase):
    """Context-menu Drop must drop every checked file, like the main button."""

    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])

    def _run_drop(self, checked_files, clicked):
        from lib.dialogs.split_drop_dialogs import DropFileFromCommitDialog

        class _MainWindow(QMainWindow):
            def __init__(self):
                super().__init__()
                self.calls = []

            def perform_drop_file_from_commit(self, sha, files):
                self.calls.append((sha, files))

        class _FakeDialog:
            """Provides exactly the surface _drop_from_context_menu uses."""

            def __init__(self, main_win, checked):
                self._main_win = main_win
                self._checked = checked
                self.sha = "abc1234567890"
                self.accepted = False

            def parent(self):
                return self._main_win

            def accept(self):
                self.accepted = True

            def _checked_filewise_files(self):
                return list(self._checked)

        win = _MainWindow()
        dlg = _FakeDialog(win, checked_files)
        DropFileFromCommitDialog._drop_from_context_menu(dlg, clicked)
        self.assertTrue(
            dlg.accepted,
            "context-menu drop must close the dialog before dropping",
        )
        # The drop is deferred via QTimer.singleShot(0, ...); spin the event
        # loop until it fires.
        deadline = time.time() + 2.0
        while not win.calls and time.time() < deadline:
            QApplication.processEvents()
            time.sleep(0.001)
        win.close()
        return win.calls

    def test_drops_all_checked_files(self):
        calls = self._run_drop(["a.py", "b.py", "c.py"], clicked="b.py")
        self.assertEqual(
            calls, [("abc1234567890", ["a.py", "b.py", "c.py"])],
            "context-menu Drop must drop the whole checked selection, "
            "not only the right-clicked file",
        )

    def test_falls_back_to_clicked_file_when_nothing_checked(self):
        calls = self._run_drop([], clicked="z.py")
        self.assertEqual(calls, [("abc1234567890", ["z.py"])])

    def test_only_checked_files_dropped_not_the_untouched_rest(self):
        calls = self._run_drop(["b.py"], clicked="b.py")
        self.assertEqual(calls, [("abc1234567890", ["b.py"])])


@unittest.skipUnless(HAS_PYSIDE, "PySide6 not available")
class TestOpenWithSubmenuEnabledFlag(unittest.TestCase):
    """add_open_with_system_default_action must honour enabled=False."""

    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])

    def _submenu(self, **kwargs):
        from lib.app_window.helpers import add_open_with_system_default_action
        parent = QWidget()
        menu = QMenu(parent)
        add_open_with_system_default_action(menu, "foo.py", parent, sha=None,
                                            **kwargs)
        action = menu.actions()[0]
        submenu = action.menu()
        # Keep the Qt parent chain alive for the duration of the assertion;
        # dropping the action wrapper lets PySide delete the submenu.
        self._keepalive = (parent, menu, action)
        self.assertIsNotNone(submenu, "Open submenu must be present")
        return submenu

    def test_disabled_when_enabled_false(self):
        submenu = self._submenu(enabled=False)
        self.assertFalse(submenu.isEnabled())

    def test_enabled_by_default(self):
        submenu = self._submenu()
        self.assertTrue(submenu.isEnabled())


if __name__ == "__main__":
    unittest.main()
