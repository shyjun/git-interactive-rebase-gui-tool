import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Import lib.app_window first, matching the app's import order: importing
# lib.git_helpers first hits a package-init cycle (git_helpers -> core ->
# app_window.helpers -> app_window.__init__ -> init_mixin -> git_helpers).
import lib.app_window.helpers  # noqa: F401
from lib.app_window.helpers import get_theme_stylesheet, mono_font
from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QPoint, Qt
from lib.widgets import (
    FILTER_MATCH_ROLE,
    FileListFilter,
    _accent_from_stylesheet,
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


class TestScrollPinning(unittest.TestCase):
    """The bar and hover button are docked to the widget, not the viewport.

    QAbstractScrollArea::scrollContentsBy moves viewport children by the
    scroll delta; widget children stay pinned, so scrolling (wheel,
    scrollbar, scrollToItem after next-match navigation) must never move
    the overlays."""

    def setUp(self):
        self.lw = QListWidget()
        self.lw.resize(240, 160)
        self.lw.show()
        for i in range(60):
            self.lw.addItem(QListWidgetItem(f"file{i:02d}.c"))
        self.flt = FileListFilter(self.lw)

    def tearDown(self):
        self.lw.close()
        self.lw.deleteLater()

    def _want(self):
        off = self.flt.viewport.mapTo(self.lw, QPoint(0, 0))
        bar = (off.x() + 4, off.y() + 4)
        btn = (off.x() + self.flt.viewport.width()
               - self.flt.button.width() - 4, off.y() + 4)
        return bar, btn

    def test_bar_pinned_while_scrolling(self):
        self.flt.open_bar()
        app.processEvents()
        want_bar, _ = self._want()
        self.assertTrue(self.flt.bar.isVisible())
        self.assertEqual((self.flt.bar.x(), self.flt.bar.y()), want_bar)

        self.lw.verticalScrollBar().setValue(80)
        app.processEvents()
        self.assertTrue(self.flt.bar.isVisible())
        self.assertEqual((self.flt.bar.x(), self.flt.bar.y()), want_bar)

        self.lw.setCurrentRow(50)  # the scrollToItem path used by navigation
        app.processEvents()
        self.assertTrue(self.flt.bar.isVisible())
        self.assertEqual((self.flt.bar.x(), self.flt.bar.y()), want_bar)

    def test_button_pinned_while_scrolling(self):
        self.flt._hover = True
        self.flt._position_button()
        self.flt.button.show()
        app.processEvents()
        _, want_btn = self._want()
        self.assertEqual((self.flt.button.x(), self.flt.button.y()), want_btn)

        self.lw.verticalScrollBar().setValue(99)
        app.processEvents()
        self.assertEqual((self.flt.button.x(), self.flt.button.y()), want_btn)

    def test_navigation_keeps_bar_pinned(self):
        # User report: pressing next-match repeatedly scrolled the pane and
        # the bar went out of view.
        self.flt.open_bar()
        self.flt.input.setText(".c")
        self.flt._apply()
        for _ in range(6):
            self.flt.next_match()
        app.processEvents()
        want_bar, _ = self._want()
        self.assertTrue(self.flt.bar.isVisible())
        self.assertEqual((self.flt.bar.x(), self.flt.bar.y()), want_bar)

    def test_tree_bar_stays_below_header(self):
        tw = QTreeWidget()
        tw.resize(240, 160)
        tw.show()
        tw.setHeaderLabels(["Name", "Stats"])
        root = QTreeWidgetItem(["src", ""])
        tw.addTopLevelItem(root)
        for i in range(40):
            root.addChild(QTreeWidgetItem([f"file{i:02d}.c", "+1 -1"]))
        flt = FileListFilter(tw)
        flt.open_bar()
        app.processEvents()
        off = flt.viewport.mapTo(tw, QPoint(0, 0))
        want = (off.x() + 4, off.y() + 4)
        self.assertGreater(off.y(), 0)  # header pushes the viewport down
        tw.verticalScrollBar().setValue(50)
        app.processEvents()
        self.assertTrue(flt.bar.isVisible())
        self.assertEqual((flt.bar.x(), flt.bar.y()), want)
        tw.close()
        tw.deleteLater()


class TestDockedBar(unittest.TestCase):
    """The bar docks as a real row above the list (splitter/layout parents)
    so it never covers file rows; hiding it collapses the row."""

    def _make(self, widget, extra=None):
        splitter = QSplitter()
        splitter.addWidget(widget)
        splitter.addWidget(extra if extra is not None else QWidget())
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.addWidget(splitter)
        host.resize(420, 320)
        host.show()
        app.processEvents()
        return host, splitter

    def test_docks_into_splitter_and_covers_no_rows(self):
        lw = QListWidget()
        for name in ("src/charset.c", "src/drawline.c", "src/ex_cmds.c"):
            lw.addItem(QListWidgetItem(name))
        host, splitter = self._make(lw)
        flt = FileListFilter(lw)

        def vp_top():
            # Host-local, not global: a real window manager can reposition
            # the window between measurements, which would invalidate
            # global coordinates.
            return lw.mapTo(host, QPoint(0, 0)).y()

        y_before = vp_top()
        flt.open_bar()
        app.processEvents()
        self.assertIsNotNone(flt._container)
        self.assertIs(splitter.widget(0), flt._container)
        self.assertIs(lw.parentWidget(), flt._container)
        self.assertIs(flt.bar.parentWidget(), flt._container)
        self.assertTrue(flt.bar.isVisible())
        self.assertGreater(vp_top(), y_before)  # list pushed below the row

        lw.setCurrentRow(0)  # the user-reported case: selection must show
        app.processEvents()
        rect = lw.visualItemRect(lw.item(0))
        row_top = lw.viewport().mapToGlobal(rect.topLeft()).y()
        bar_bottom = flt.bar.mapToGlobal(flt.bar.rect().bottomLeft()).y()
        self.assertGreaterEqual(row_top, bar_bottom)

        # bar is layout-managed: scrolling cannot move or unpin it
        geo = flt.bar.geometry()
        lw.verticalScrollBar().setValue(50)
        app.processEvents()
        self.assertEqual(flt.bar.geometry(), geo)

        # closing collapses the row: viewport returns to its original place
        self.assertGreater(vp_top(), y_before)
        flt.close_bar()
        app.processEvents()
        self.assertFalse(flt.bar.isVisible())
        self.assertEqual(vp_top(), y_before)

        host.close()
        host.deleteLater()

    def test_docks_into_plain_layout(self):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        lw = QListWidget()
        lw.addItem(QListWidgetItem("a.c"))
        page_layout.addWidget(lw)
        host = QWidget()
        host_layout = QVBoxLayout(host)
        host_layout.addWidget(page)
        host.resize(300, 200)
        host.show()
        app.processEvents()
        flt = FileListFilter(lw)

        def vp_top():
            # Host-local (see comment in the splitter test): WM-safe.
            return lw.mapTo(host, QPoint(0, 0)).y()

        y_before = vp_top()
        flt.open_bar()
        app.processEvents()
        self.assertIsNotNone(flt._container)
        self.assertTrue(flt.bar.isVisible())
        self.assertGreater(vp_top(), y_before)
        flt.close_bar()
        app.processEvents()
        self.assertEqual(vp_top(), y_before)

        host.close()
        host.deleteLater()

    def test_tree_bar_docks_above_header(self):
        tw = QTreeWidget()
        tw.setHeaderLabels(["Name", "Stats"])
        root = QTreeWidgetItem(["src", ""])
        tw.addTopLevelItem(root)
        root.addChild(QTreeWidgetItem(["a.c", "+1 -1"]))
        host, _ = self._make(tw)
        flt = FileListFilter(tw)

        flt.open_bar()
        app.processEvents()
        self.assertIsNotNone(flt._container)
        bar_bottom = flt.bar.mapToGlobal(flt.bar.rect().bottomLeft()).y()
        header_top = tw.header().mapToGlobal(
            tw.header().rect().topLeft()).y()
        self.assertLessEqual(bar_bottom, header_top)

        host.close()
        host.deleteLater()

    def test_parentless_falls_back_to_overlay(self):
        lw = QListWidget()
        lw.resize(200, 120)
        lw.show()
        lw.addItem(QListWidgetItem("x.c"))
        flt = FileListFilter(lw)
        flt.open_bar()
        app.processEvents()
        self.assertIsNone(flt._container)
        self.assertTrue(flt.bar.isVisible())
        lw.close()
        lw.deleteLater()


class TestAccentFromStylesheet(unittest.TestCase):

    def test_dark_theme(self):
        sheet = "QPushButton { background-color: #007acc; }"
        self.assertEqual(_accent_from_stylesheet(sheet), "#007acc")

    def test_light_theme(self):
        sheet = "QListWidget::item:selected { background-color: #007aff; }"
        self.assertEqual(_accent_from_stylesheet(sheet), "#007aff")

    def test_unknown_and_empty(self):
        self.assertIsNone(_accent_from_stylesheet("QWidget { color: red; }"))
        self.assertIsNone(_accent_from_stylesheet(""))
        self.assertIsNone(_accent_from_stylesheet(None))


class TestHoverButtonAppearance(unittest.TestCase):

    def test_button_is_28_with_icon(self):
        lw = QListWidget()
        lw.resize(200, 120)
        lw.show()
        lw.addItem(QListWidgetItem("a.c"))
        flt = FileListFilter(lw)
        self.assertEqual(flt.button.size().toTuple(), (28, 28))
        self.assertFalse(flt.button.icon().pixmap(1, 1).isNull())
        flt._refresh_button_icon()
        self.assertFalse(flt.button.icon().pixmap(1, 1).isNull())
        lw.close()
        lw.deleteLater()


class TestFontPreservation(unittest.TestCase):
    """Docking the bar must not reset the list/tree font.

    Reparenting through the parentless container in _dock_bar re-polishes
    the widget under the app stylesheet, which drops its explicit setFont
    (the bug where clicking the magnifier shrank the right-pane lists to
    the default 9pt font)."""

    def setUp(self):
        self._old_sheet = app.styleSheet()
        app.setStyleSheet(get_theme_stylesheet("light"))

    def tearDown(self):
        app.setStyleSheet(self._old_sheet)

    def _dock_fonts(self, widget):
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Vertical)
        layout.addWidget(split)
        split.addWidget(widget)
        host.resize(300, 200)
        host.show()
        app.processEvents()
        # The app applies fonts while the window already exists (setup_ui /
        # zoom / theme paths); post-show setFont is what the polish during
        # the dock wrap used to clobber.
        widget.setFont(mono_font(14))
        app.processEvents()
        flt = FileListFilter(widget)
        before = (widget.font(), widget.viewport().font())
        flt.open_bar()
        app.processEvents()
        after = (widget.font(), widget.viewport().font())
        host.close()
        host.deleteLater()
        return before, after

    def _assert_fonts_equal(self, before, after):
        for b, a in zip(before, after):
            self.assertEqual(a.family(), b.family())
            self.assertEqual(a.pointSize(), b.pointSize())
            self.assertEqual(a.bold(), b.bold())

    def test_list_font_survives_dock(self):
        lw = QListWidget()
        lw.addItem(QListWidgetItem("a.c"))
        before, after = self._dock_fonts(lw)
        self.assertEqual(before[0].pointSize(), 14)
        self._assert_fonts_equal(before, after)
        self.assertEqual(after[0].pointSize(), 14)

    def test_tree_font_survives_dock(self):
        tree = QTreeWidget()
        tree.addTopLevelItem(QTreeWidgetItem(["a.c"]))
        before, after = self._dock_fonts(tree)
        self.assertEqual(before[0].pointSize(), 14)
        self._assert_fonts_equal(before, after)
        self.assertEqual(after[0].pointSize(), 14)


class TestSignalSilence(unittest.TestCase):
    """Filter mutations must not emit itemChanged.

    The dialogs treat itemChanged as a checkbox change and walk the whole
    tree + rebuild both diff panes per item — on a 16k-file commit that
    froze the UI (O(N^2) per keystroke)."""

    def _counting_list(self):
        lw = QListWidget()
        for name in ("src/gui.c", "src/core.c", "lib/util.c"):
            lw.addItem(QListWidgetItem(name))
        lw.resize(240, 160)
        lw.show()
        app.processEvents()
        hits = []
        lw.itemChanged.connect(lambda *_: hits.append(1))
        return lw, hits

    def test_unblocked_setdata_still_emits(self):
        # Sanity: proves the counters below would catch a regression.
        lw, hits = self._counting_list()
        lw.item(0).setData(FILTER_MATCH_ROLE, [(0, 3)])
        self.assertEqual(len(hits), 1)
        lw.close()
        lw.deleteLater()

    def test_list_apply_clear_close_are_silent(self):
        lw, hits = self._counting_list()
        flt = FileListFilter(lw)
        flt.open_bar()
        flt.input.setText("gui")
        flt._apply()
        self.assertEqual(hits, [])
        self.assertFalse(lw.signalsBlocked())
        self.assertEqual([r for r in range(3) if lw.isRowHidden(r)], [1, 2])
        # Retyp exercises _clear_tagged's setData(None) storm path.
        flt.input.setText("core")
        flt._apply()
        self.assertEqual(hits, [])
        self.assertEqual([r for r in range(3) if lw.isRowHidden(r)], [0, 2])
        flt.input.setText("")
        flt._apply()
        self.assertEqual(hits, [])
        self.assertEqual([r for r in range(3) if lw.isRowHidden(r)], [])
        flt.close_bar()
        self.assertEqual(hits, [])
        self.assertFalse(lw.signalsBlocked())
        lw.close()
        lw.deleteLater()

    def _counting_tree(self):
        tree = QTreeWidget()
        tree.setHeaderLabels(["Name"])
        src = QTreeWidgetItem(["src"])
        tree.addTopLevelItem(src)
        QTreeWidgetItem(src, ["gui.c"])
        QTreeWidgetItem(src, ["core.c"])
        lib = QTreeWidgetItem(["lib"])
        tree.addTopLevelItem(lib)
        QTreeWidgetItem(lib, ["util.c"])
        tree.resize(240, 160)
        tree.show()
        app.processEvents()
        hits = []
        tree.itemChanged.connect(lambda *_: hits.append(1))
        return tree, hits

    def test_unblocked_tree_setdata_emits(self):
        tree, hits = self._counting_tree()
        tree.topLevelItem(0).setData(0, FILTER_MATCH_ROLE, [(0, 3)])
        self.assertEqual(len(hits), 1)
        tree.close()
        tree.deleteLater()

    def test_tree_apply_clear_close_are_silent(self):
        tree, hits = self._counting_tree()
        flt = FileListFilter(tree)
        flt.open_bar()
        flt.input.setText("gui")
        flt._apply()
        self.assertEqual(hits, [])
        self.assertFalse(tree.signalsBlocked())
        self.assertFalse(tree.topLevelItem(0).child(0).isHidden())
        self.assertTrue(tree.topLevelItem(0).child(1).isHidden())
        self.assertTrue(tree.topLevelItem(1).isHidden())
        flt.input.setText("")
        flt._apply()
        self.assertEqual(hits, [])
        self.assertFalse(tree.topLevelItem(1).isHidden())
        flt.close_bar()
        self.assertEqual(hits, [])
        self.assertFalse(tree.signalsBlocked())
        tree.close()
        tree.deleteLater()


if __name__ == "__main__":
    unittest.main()
