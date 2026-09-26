import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QLabel, QLineEdit, QListWidget,
        QListWidgetItem, QToolButton,
    )
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False

if HAS_PYSIDE:
    from lib.app_window import _diff_search_matches
    from lib.commit_filter_controller import CommitFilterController
    MATCH_ROLE = Qt.UserRole + 7
    LOAD_MORE_ROLE = Qt.UserRole + 9


class TestCommitMatchNav(unittest.TestCase):
    """< / > next/previous matching-commit navigation buttons."""

    @classmethod
    def setUpClass(cls):
        if HAS_PYSIDE:
            if not QApplication.instance():
                cls.app = QApplication([])

    def setUp(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")

        self.list_widget = QListWidget()
        self.search_edit = QLineEdit()
        self.cb_files = QCheckBox()
        self.cb_diff = QCheckBox()
        self.cb_author = QCheckBox()
        self.prev_btn = QToolButton()
        self.next_btn = QToolButton()
        self.status_label = QLabel()
        self.showing_label = QLabel()
        self.sep_merge = QLabel()
        self.merge_label = QLabel()

        self.controller = CommitFilterController(
            None, self.list_widget, {}, os.getcwd(),
            self.search_edit, self.cb_files, self.cb_diff, self.cb_author,
            self.prev_btn, self.next_btn,
            self.status_label, self.showing_label, self.sep_merge,
            self.merge_label, MATCH_ROLE, _diff_search_matches,
            lambda path, sha: [], lambda path, sha: "",
            None, lambda key: key)

    def _add(self, text, match=False, load_more=False, hidden=False):
        item = QListWidgetItem(text)
        if load_more:
            item.setData(LOAD_MORE_ROLE, "load_more")
        self.list_widget.addItem(item)
        item.setHidden(hidden)
        if match:
            item.setData(MATCH_ROLE, True)
        return item

    def _filter(self, term):
        self.search_edit.setText(term)
        self.controller.filter_commits(term)

    def test_buttons_disabled_with_no_search(self):
        self.assertFalse(self.prev_btn.isEnabled())
        self.assertFalse(self.next_btn.isEnabled())

    def test_filtering_enables_buttons_and_click_selects_first_match(self):
        self._add("aaaa fix login")
        self._add("bbbb other work")
        self._add("cccc fix parser")
        self._filter("fix")
        self.assertTrue(self.prev_btn.isEnabled())
        self.assertTrue(self.next_btn.isEnabled())
        self.next_btn.click()
        self.assertEqual(self.list_widget.currentRow(), 0)

    def test_next_walks_forward_and_wraps(self):
        self._add("aaaa fix login")
        self._add("bbbb other work")
        self._add("cccc fix parser")
        self._filter("fix")
        self.controller.goto_next_match()
        self.assertEqual(self.list_widget.currentRow(), 0)
        self.controller.goto_next_match()
        self.assertEqual(self.list_widget.currentRow(), 2)
        self.controller.goto_next_match()
        self.assertEqual(self.list_widget.currentRow(), 0)

    def test_prev_walks_backward_and_wraps(self):
        self._add("aaaa fix login")
        self._add("bbbb other work")
        self._add("cccc fix parser")
        self._filter("fix")
        # No current selection: prev starts at the last match.
        self.controller.goto_prev_match()
        self.assertEqual(self.list_widget.currentRow(), 2)
        self.controller.goto_prev_match()
        self.assertEqual(self.list_widget.currentRow(), 0)
        self.controller.goto_prev_match()
        self.assertEqual(self.list_widget.currentRow(), 2)

    def test_navigation_skips_non_matching_rows(self):
        self._add("aaaa fix login")
        self._add("bbbb other work")
        self._add("cccc fix parser")
        self._add("dddd more work")
        self._filter("fix")
        self.list_widget.setCurrentRow(1)  # a non-matching row
        self.controller.goto_next_match()
        self.assertEqual(self.list_widget.currentRow(), 2)
        self.controller.goto_prev_match()
        self.assertEqual(self.list_widget.currentRow(), 0)

    def test_load_more_row_is_never_a_match_target(self):
        self._add("aaaa fix login", match=True)
        self._add("Load 100 more...", match=True, load_more=True)
        self._add("cccc fix parser", match=True)
        self.controller.goto_next_match()
        self.assertEqual(self.list_widget.currentRow(), 0)
        self.controller.goto_next_match()
        self.assertEqual(self.list_widget.currentRow(), 2)

    def test_hidden_flagged_rows_are_skipped(self):
        self._add("aaaa fix login", match=True)
        self._add("bbbb fix hidden", match=True, hidden=True)
        self._add("cccc fix parser", match=True)
        self.controller.goto_next_match()
        self.assertEqual(self.list_widget.currentRow(), 0)
        self.controller.goto_next_match()
        self.assertEqual(self.list_widget.currentRow(), 2)

    def test_clearing_search_disables_buttons(self):
        self._add("aaaa fix login")
        self._filter("fix")
        self.assertTrue(self.next_btn.isEnabled())
        self._filter("")
        self.assertFalse(self.prev_btn.isEnabled())
        self.assertFalse(self.next_btn.isEnabled())

    def test_goto_is_noop_without_matches(self):
        self._add("aaaa no match here")
        self.controller.goto_next_match()
        self.assertEqual(self.list_widget.currentRow(), -1)
        self.controller.goto_prev_match()
        self.assertEqual(self.list_widget.currentRow(), -1)

    def test_display_only_mode_navigates_visible_matches(self):
        self.controller.set_search_options(False, False, True)
        self._add("aaaa fix login")
        self._add("bbbb other work")
        self._add("cccc fix parser")
        self._filter("fix")
        self.assertTrue(self.list_widget.item(1).isHidden())
        self.controller.goto_next_match()
        self.assertEqual(self.list_widget.currentRow(), 0)
        self.controller.goto_next_match()
        self.assertEqual(self.list_widget.currentRow(), 2)

    def test_filename_filter_matches_are_navigable(self):
        self.cb_files.setChecked(True)
        item = self._add("aaaa other work")
        item.setData(Qt.UserRole + 6, "")  # message without the term
        self.controller._commit_cache["aaaa"] = {
            "files": [("M", "lib/fix_engine.py", None)]}
        item2 = self._add("bbbb unrelated")
        self.controller._commit_cache["bbbb"] = {
            "files": [("M", "lib/other.py", None)]}
        self._filter("fix")
        self.assertTrue(self.next_btn.isEnabled())
        self.controller.goto_next_match()
        self.assertEqual(self.list_widget.currentRow(), 0)


if __name__ == "__main__":
    unittest.main()
