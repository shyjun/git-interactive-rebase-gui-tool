import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Import lib.app_window first, matching the app's import order: importing
# lib.git_helpers first hits a package-init cycle (git_helpers -> core ->
# app_window.helpers -> app_window.__init__ -> init_mixin -> git_helpers).
import lib.app_window.helpers  # noqa: F401
from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QListWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
)
from PySide6.QtCore import Qt
from lib.widgets import (
    FILTER_MATCH_ROLE,
    FileListFilter,
    filter_match_ranges,
    list_filter_hidden,
    tree_filter_sets,
)

app = QApplication.instance() or QApplication([])


class TestFilterMatchRanges(unittest.TestCase):

    def test_basic_match(self):
        self.assertEqual(filter_match_ranges("src/gui/main.c", "gui"), [(4, 7)])

    def test_case_insensitive(self):
        self.assertEqual(filter_match_ranges("SRC/GUI/main.c", "gui"), [(4, 7)])

    def test_multiple_occurrences(self):
        self.assertEqual(filter_match_ranges("gui/gui.c", "gui"),
                         [(0, 3), (4, 7)])

    def test_no_match(self):
        self.assertEqual(filter_match_ranges("src/core.c", "gui"), [])

    def test_empty_inputs(self):
        self.assertEqual(filter_match_ranges("a.c", ""), [])
        self.assertEqual(filter_match_ranges("", "a"), [])


class TestListFilterHidden(unittest.TestCase):

    def test_hides_non_matching(self):
        hidden = list_filter_hidden(["gui.c", "core.c", "GUI.h"], "gui")
        self.assertEqual(hidden, [False, True, False])

    def test_empty_term_keeps_all(self):
        self.assertEqual(list_filter_hidden(["a", "b"], ""), [False, False])


class TestTreeFilterSets(unittest.TestCase):

    def test_matching_files_and_ancestor_folders(self):
        files = ["src/gui/a.c", "src/gui/b.c", "lib/c.c"]
        visible_files, visible_folders = tree_filter_sets(files, "gui")
        self.assertEqual(visible_files, {"src/gui/a.c", "src/gui/b.c"})
        self.assertEqual(visible_folders, {"src", "src/gui"})

    def test_folder_name_matches_descendants(self):
        files = ["gui/main.c", "other.c"]
        visible_files, visible_folders = tree_filter_sets(files, "gui")
        self.assertEqual(visible_files, {"gui/main.c"})
        self.assertEqual(visible_folders, {"gui"})

    def test_no_match(self):
        files = ["src/a.c"]
        visible_files, visible_folders = tree_filter_sets(files, "zzz")
        self.assertEqual(visible_files, set())
        self.assertEqual(visible_folders, set())

    def test_empty_term_shows_everything(self):
        files = ["src/a.c", "b.c"]
        visible_files, _ = tree_filter_sets(files, "")
        self.assertEqual(visible_files, set(files))


def _make_list(paths):
    lw = QListWidget()
    lw.show()
    for p in paths:
        item = QListWidgetItem(p)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        lw.addItem(item)
    return lw


class TestListWidgetFilter(unittest.TestCase):

    PATHS = ["src/gui_gtk4.c", "src/gui/main.c", "lib/core.c"]

    def setUp(self):
        self.lw = _make_list(self.PATHS)
        self.flt = FileListFilter(self.lw)

    def tearDown(self):
        self.lw.close()
        self.lw.deleteLater()

    def _filter(self, term):
        self.flt.open_bar()
        self.flt.input.setText(term)
        self.flt._apply()

    def test_filters_rows(self):
        self._filter("gui")
        hidden = [self.lw.item(i).isHidden() for i in range(self.lw.count())]
        self.assertEqual(hidden, [False, False, True])
        self.assertEqual(self.flt.counter.text(), "1/2")

    def test_check_states_preserved_on_hidden_rows(self):
        self.lw.item(2).setCheckState(Qt.Unchecked)
        self._filter("gui")
        self.assertTrue(self.lw.item(2).isHidden())
        self.assertEqual(self.lw.item(2).checkState(), Qt.Unchecked)

    def test_match_ranges_set_and_cleared(self):
        self._filter("gui")
        self.assertEqual(self.lw.item(1).data(FILTER_MATCH_ROLE), [(4, 7)])
        self.flt.input.setText("")
        self.flt._apply()
        self.assertIsNone(self.lw.item(1).data(FILTER_MATCH_ROLE))
        self.assertFalse(any(self.lw.item(i).isHidden()
                             for i in range(self.lw.count())))

    def test_navigation_wraps(self):
        self._filter("gui")
        self.assertEqual(self.flt.counter.text(), "1/2")
        self.flt.next_match()
        self.assertEqual(self.flt.counter.text(), "2/2")
        self.assertEqual(self.lw.currentRow(), 1)
        self.flt.next_match()
        self.assertEqual(self.flt.counter.text(), "1/2")

    def test_model_reset_closes_bar_and_restores_list(self):
        self._filter("gui")
        self.assertTrue(self.flt.bar.isVisible())
        self.lw.clear()
        self.assertFalse(self.flt.bar.isVisible())
        self.assertEqual(self.flt.counter.text(), "0/0")
        self.lw.addItem("fresh.c")
        self.assertFalse(self.lw.isRowHidden(0))


def _make_tree():
    tw = QTreeWidget()
    tw.show()
    tw.setHeaderLabels(["Name", "Stats"])

    def top(name):
        item = QTreeWidgetItem([name, ""])
        tw.addTopLevelItem(item)
        return item

    def child(parent, name):
        item = QTreeWidgetItem([name, ""])
        parent.addChild(item)
        return item

    src = top("src")
    gui = child(src, "gui")
    items = {
        "src": src,
        "gui": gui,
        "mw": child(gui, "main_window.c"),
        "dlg": child(gui, "dialogs.c"),
        "core": child(src, "core.c"),
        "lib": top("lib"),
    }
    items["util"] = child(items["lib"], "util.c")
    return tw, items


class TestTreeWidgetFilter(unittest.TestCase):

    def setUp(self):
        self.tw, self.items = _make_tree()
        self.flt = FileListFilter(self.tw)

    def tearDown(self):
        self.tw.close()
        self.tw.deleteLater()

    def _filter(self, term):
        self.flt.open_bar()
        self.flt.input.setText(term)
        self.flt._apply()

    def test_folder_filter_shows_descendants_only(self):
        self._filter("gui")
        self.assertFalse(self.items["mw"].isHidden())
        self.assertFalse(self.items["dlg"].isHidden())
        self.assertTrue(self.items["core"].isHidden())
        self.assertTrue(self.items["lib"].isHidden())
        self.assertTrue(self.items["util"].isHidden())
        self.assertFalse(self.items["gui"].isHidden())
        self.assertTrue(self.items["gui"].isExpanded())
        self.assertEqual(self.flt.counter.text(), "1/2")

    def test_folder_name_highlighted(self):
        self._filter("gui")
        self.assertEqual(self.items["gui"].data(0, FILTER_MATCH_ROLE), [(0, 3)])

    def test_leaf_name_filter(self):
        self._filter("main_window")
        self.assertFalse(self.items["mw"].isHidden())
        self.assertTrue(self.items["dlg"].isHidden())
        self.assertEqual(self.items["mw"].data(0, FILTER_MATCH_ROLE), [(0, 11)])

    def test_close_bar_restores_all(self):
        self._filter("gui")
        self.flt.close_bar()
        for key in ("mw", "dlg", "core", "lib", "util"):
            self.assertFalse(self.items[key].isHidden(), key)

    def test_model_reset_closes_bar(self):
        self._filter("gui")
        self.tw.clear()
        self.assertFalse(self.flt.bar.isVisible())


if __name__ == "__main__":
    unittest.main()
