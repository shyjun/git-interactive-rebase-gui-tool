"""Coverage for the Git Diff toolbar button and the unstaged-diff handler.

The main toolbar offers a "Git Diff" button that sits immediately *before*
the existing "Git Status" button and opens the rendered UnstagedDiffDialog
on demand (mid-session), instead of only from the startup/rescan warning
dialog.

The static (AST) tests assert that

  1. ui_mixin creates ``git_diff_btn`` ("Git Diff") before ``git_status_btn``
     and wires it to ``handle_view_unstaged_diff`` with a *no-arg* callable
     (``clicked`` emits a checked bool that must not be bound to the
     handler's ``unstaged`` parameter),
  2. the button is added to ``controls_layout`` and given the browse-mode
     visibility rule immediately before the Git Status button,
  3. toolbar_mixin ships the icon trio (``_set_git_diff_icon`` /
     ``_refresh_toolbar_icons`` entry / ``_draw_git_diff``) in the same
     order as the Git Status trio,
  4. StashMixin defines ``handle_view_unstaged_diff`` mirroring the staged
     twin (gather -> empty check -> UnstagedDiffDialog), and
  5. the warning dialog's ``show_unstaged_changes`` delegates to that
     handler instead of building its own dialog copy.
"""

import ast
import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _parse(relpath):
    with open(os.path.join(ROOT, relpath), encoding="utf-8") as fh:
        return ast.parse(fh.read(), filename=relpath)


def _find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _dotted(node):
    """Dotted source name for Name/Attribute chains ('self.git_diff_btn')."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    else:
        return ""
    return ".".join(reversed(parts))


def _calls(func, dotted=None):
    """All Call nodes in *func* (optionally filtered by dotted name)."""
    out = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted(node.func)
        if dotted is None or name == dotted:
            out.append((node.lineno, name, node))
    return sorted(out)


def _assigns_to(func, dotted_name):
    """Assignments whose target is *dotted_name*, as (lineno, node) pairs."""
    out = []
    for node in ast.walk(func):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(_dotted(t) == dotted_name for t in targets):
            out.append((node.lineno, node))
    return sorted(out)


class UiMixinButtonTests(unittest.TestCase):
    """Button creation, wiring, layout order and visibility in ui_mixin."""

    @classmethod
    def setUpClass(cls):
        cls.tree = _parse("lib/app_window/ui_mixin.py")

    def test_git_diff_btn_created_before_git_status_btn(self):
        diff = _assigns_to(self.tree, "self.git_diff_btn")
        status = _assigns_to(self.tree, "self.git_status_btn")
        self.assertEqual(len(diff), 1, "expected exactly one git_diff_btn assignment")
        self.assertEqual(len(status), 1, "expected exactly one git_status_btn assignment")
        self.assertLess(diff[0][0], status[0][0], "Git Diff button must be created first")
        # Labelled "Git Diff" so it is not confused with the status button.
        labels = [
            arg.value
            for arg in ast.walk(diff[0][1])
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
        ]
        self.assertIn("Git Diff", labels)

    def test_button_connected_to_unstaged_handler_without_args(self):
        connects = [
            (lineno, node)
            for lineno, name, node in _calls(self.tree, "self.git_diff_btn.clicked.connect")
        ]
        self.assertEqual(len(connects), 1, "git_diff_btn must be connected exactly once")
        _, node = connects[0]
        self.assertEqual(len(node.args), 1, "connect() takes the slot as its only argument")
        slot = node.args[0]
        # clicked(bool) must not leak into handle_view_unstaged_diff(unstaged=...)
        self.assertIsInstance(slot, ast.Lambda, "wrap the handler in a no-arg callable")
        self.assertEqual(len(slot.args.args), 0, "the slot must take no arguments")
        called = [
            _dotted(n.func)
            for n in ast.walk(slot)
            if isinstance(n, ast.Call)
        ]
        self.assertIn("self.handle_view_unstaged_diff", called)

    def test_added_to_controls_layout_before_git_status_btn(self):
        calls = _calls(self.tree, "controls_layout.addWidget")
        diff = [ln for ln, _, n in calls if _dotted(n.args[0]) == "self.git_diff_btn"]
        status = [ln for ln, _, n in calls if _dotted(n.args[0]) == "self.git_status_btn"]
        self.assertEqual(len(diff), 1, "git_diff_btn must be added to controls_layout once")
        self.assertEqual(len(status), 1)
        self.assertLess(diff[0], status[0], "Git Diff must precede Git Status in the layout")

    def test_hidden_in_browse_mode_like_git_status_btn(self):
        calls = _calls(self.tree, "self.git_diff_btn.setVisible")
        self.assertEqual(len(calls), 1, "git_diff_btn visibility must be set exactly once")
        lineno, _, node = calls[0]
        # setVisible(not self.browse_mode)
        self.assertIsInstance(node.args[0], ast.UnaryOp)
        self.assertIsInstance(node.args[0].op, ast.Not)
        self.assertEqual(_dotted(node.args[0].operand), "self.browse_mode")
        status = _calls(self.tree, "self.git_status_btn.setVisible")
        self.assertEqual(len(status), 1)
        self.assertLess(lineno, status[0][0], "Git Diff visibility mirrors Git Status")


class ToolbarIconTests(unittest.TestCase):
    """Icon plumbing in toolbar_mixin must mirror the Git Status trio."""

    @classmethod
    def setUpClass(cls):
        cls.tree = _parse("lib/app_window/toolbar_mixin.py")

    def test_set_git_diff_icon_exists(self):
        func = _find_func(self.tree, "_set_git_diff_icon")
        self.assertIsNotNone(func, "_set_git_diff_icon must be defined")
        calls = _calls(func, "self._apply_toolbar_icon")
        self.assertEqual(len(calls), 1)
        self.assertEqual(_dotted(calls[0][2].args[1]), "self._draw_git_diff")

    def test_refresh_toolbar_icons_includes_git_diff_before_git_status(self):
        func = _find_func(self.tree, "_refresh_toolbar_icons")
        self.assertIsNotNone(func)
        diff = _calls(func, "self._set_git_diff_icon")
        status = _calls(func, "self._set_git_status_icon")
        self.assertEqual(len(diff), 1, "theme refresh must repaint the Git Diff icon")
        self.assertEqual(len(status), 1)
        self.assertEqual(_dotted(diff[0][2].args[0]), "self.git_diff_btn")
        self.assertLess(diff[0][0], status[0][0], "refresh order mirrors creation order")

    def test_draw_git_diff_exists(self):
        func = _find_func(self.tree, "_draw_git_diff")
        self.assertIsNotNone(func, "_draw_git_diff must be defined")
        self.assertEqual([a.arg for a in func.args.args], ["self", "painter", "color"])


class UnstagedHandlerTests(unittest.TestCase):
    """The main-window handler mirrors handle_view_staged_diff."""

    @classmethod
    def setUpClass(cls):
        cls.tree = _parse("lib/app_window/stash_mixin.py")

    def test_handler_defined_with_unstaged_and_parent(self):
        func = _find_func(self.tree, "handle_view_unstaged_diff")
        self.assertIsNotNone(func, "handle_view_unstaged_diff must be defined")
        self.assertEqual(
            [a.arg for a in func.args.args],
            ["self", "unstaged", "parent"],
            "unstaged is optional; parent lets modal callers keep the viewer on top",
        )

    def test_handler_gathers_and_opens_unstaged_dialog(self):
        func = _find_func(self.tree, "handle_view_unstaged_diff")
        names = {
            _dotted(n.func) for n in ast.walk(func) if isinstance(n, ast.Call)
        } | {n.id for n in ast.walk(func) if isinstance(n, ast.Name)}
        for required in (
            "get_unstaged_files",
            "get_unstaged_diff",
            "get_unstaged_file_stats",
            "UnstagedDiffDialog",
        ):
            self.assertIn(required, names, f"handler must use {required}")

    def test_handler_empty_case_informs_user(self):
        func = _find_func(self.tree, "handle_view_unstaged_diff")
        strings = {
            n.value for n in ast.walk(func)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
        self.assertIn("No Unstaged Changes", strings)
        # Staged twin wording stays distinct from the unstaged one.
        staged = _find_func(self.tree, "handle_view_staged_diff")
        staged_strings = {
            n.value for n in ast.walk(staged)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
        self.assertIn("No Staged Changes", staged_strings)


class WarningDialogDelegationTests(unittest.TestCase):
    """The warning dialog must reuse the main-window handler."""

    @classmethod
    def setUpClass(cls):
        cls.tree = _parse("lib/dialogs/unstaged_dialogs.py")
        cls.func = _find_func(cls.tree, "show_unstaged_changes")
        if cls.func is None:
            raise AssertionError("show_unstaged_changes must exist")

    def test_delegates_to_main_window_handler(self):
        calls = {
            _dotted(n.func): n for n in ast.walk(self.func) if isinstance(n, ast.Call)
        }
        self.assertIn(
            "handler", calls,
            "the dialog must look up handle_view_unstaged_diff on its parent",
        )
        # getattr(main_win, "handle_view_unstaged_diff", None) -> string literal
        names = {n.id for n in ast.walk(self.func) if isinstance(n, ast.Name)}
        strings = {
            n.value for n in ast.walk(self.func)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
        self.assertIn("handle_view_unstaged_diff", names | strings)

    def test_handler_called_with_dialog_as_parent(self):
        handler_calls = [
            n for n in ast.walk(self.func)
            if isinstance(n, ast.Call) and _dotted(n.func) == "handler"
        ]
        self.assertEqual(len(handler_calls), 1)
        kwargs = {kw.arg: kw.value for kw in handler_calls[0].keywords}
        self.assertIn("parent", kwargs, "viewer must stay above the modal warning dialog")
        self.assertEqual(_dotted(kwargs["parent"]), "self")

    def test_no_duplicate_dialog_construction(self):
        constructed = [
            n for n in ast.walk(self.func)
            if isinstance(n, ast.Call) and _dotted(n.func) == "UnstagedDiffDialog"
        ]
        self.assertEqual(
            constructed, [],
            "show_unstaged_changes must delegate, not build a second copy",
        )


if __name__ == "__main__":
    unittest.main()
