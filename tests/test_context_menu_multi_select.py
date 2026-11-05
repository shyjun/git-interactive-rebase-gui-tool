"""Static (AST) coverage for multi-select guards in file context menus.

Every file-context menu offers single-file actions (Blame, Diff-ref, Copy
filename/fullpath, Rename/Remove onwards, Refine, Browse file log) that must
be greyed out when more than one file is checked.  These tests parse the
menu methods and assert that

  1. the known inventory of 13 menu methods is intact (a renamed or newly
     added menu must be registered here on purpose), and
  2. each menu computes ``multi_select`` from its checked-file helpers, and
  3. every single-file QAction is disabled via ``setEnabled(not multi_select)``.

Multi-file actions (Move/Drop) are explicitly allowlisted and exempt.
"""

import ast
import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")

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
    """Yield (class_name, function_node, source_segment) for menu methods."""
    tree = ast.parse(src)
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        for fn in [n for n in cls.body if isinstance(n, ast.FunctionDef)]:
            if "context_menu" in fn.name:
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


if __name__ == "__main__":
    unittest.main()
