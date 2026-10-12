import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from lib.app_window.cherry_pick_mixin import CherryPickMixin
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False


class _FakeBrowseWindow(CherryPickMixin):
    """Minimal browse-window stand-in for cherry-pick flow tests.

    Records the refresh/load side effects a cherry-pick is expected to trigger
    and stubs out everything that needs a real window, repo or message box."""

    def __init__(self, success=True):
        self.calls = []
        self.success = success
        self._browse_load_post_action = None

    def _check_head_unchanged(self):
        return True

    def _check_no_unstaged_changes(self):
        return True

    def save_undo_state(self):
        self.calls.append("save_undo_state")

    def _run_cherry_pick(self, sha):
        self.calls.append("run_cherry_pick")
        return (True, "") if self.success else (False, "boom")

    def _sync_cached_head(self):
        self.calls.append("sync_cached_head")

    def load_history(self):
        self.calls.append("load_history")

    def _refresh_parent_main_window(self):
        self.calls.append("refresh_parent")

    def _show_cherry_pick_result(self, *args):
        self.calls.append("show_result")


class _FakeDetachedWindow(_FakeBrowseWindow):
    """Exercises the real _refresh_parent_main_window guard: a browse window
    with no main window behind it must not raise after a successful pick."""

    def parent(self):
        return None

    def _refresh_parent_main_window(self):
        self.calls.append("refresh_parent")
        CherryPickMixin._refresh_parent_main_window(self)


class TestCherryPickRefresh(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if HAS_PYSIDE and not hasattr(cls, "app"):
            try:
                from PySide6.QtWidgets import QApplication
                if not QApplication.instance():
                    cls.app = QApplication([])
            except Exception:
                pass

    def test_single_success_refreshes_main_window(self):
        """A successful single cherry-pick from the browse window must refresh
        the parent main window before the success box is shown, so its commit
        list and cached HEAD are never left stale."""
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        win = _FakeBrowseWindow(success=True)
        win._cherry_pick_single("abc1234")
        self.assertEqual(
            win.calls,
            ["save_undo_state", "run_cherry_pick", "sync_cached_head",
             "load_history", "refresh_parent", "show_result"],
        )
        self.assertIsNotNone(win._browse_load_post_action)

    def test_success_without_parent_skips_refresh(self):
        """_refresh_parent_main_window is a no-op when there is no main window
        (detached browse window); the pick itself must still complete."""
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        win = _FakeDetachedWindow(success=True)
        win._cherry_pick_single("abc1234")
        self.assertIn("refresh_parent", win.calls)
        self.assertIn("show_result", win.calls)


if __name__ == "__main__":
    unittest.main()
