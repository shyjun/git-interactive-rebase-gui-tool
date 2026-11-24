if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py (git-interactive-rebase-gui-tool)")
    sys.exit(1)

# pyrefly: ignore [missing-import]
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
# pyrefly: ignore [missing-import]
from PySide6.QtCore import (
    QEvent,
    QObject,
    Qt,
    QTimer,
    Signal,
)
# pyrefly: ignore [missing-import]
from PySide6.QtGui import (
    QAction,
    QKeySequence,
    QShortcut,
)

from lib.git_helpers import (
    build_file_tree,
    get_commit_diff,
    get_commit_file_stats,
    get_commit_files_with_status,
    get_commit_metadata_and_message,
    get_file_diff_between,
    get_file_diff_only_in_commit,
    get_rename_diff_in_commit,
    get_staged_file_diff,
    get_unstaged_file_diff,
    parse_commit_mode_changes,
)
from lib.utils import get_theme_colors
from lib.app_window.helpers import (
    PLAIN_DIFF_LINE_CAP,
    clean_binary_diff_lines,
    _log,
    _get_head_sha,
    add_open_with_system_default_action,
    is_editable_branch,
    mono_font,
)
from lib.settings_store import tool_settings
from lib.widgets import (
    DiffHighlighter,
    DiffSearchBar,
    DiffView,
    FILE_ENTRY_ROLE,
    FileListFilter,
    StatsItemDelegate,
    TreeStatsDelegate,
)
from lib.tree_utils import (
    set_tree_children_checked,
    update_folder_check_state,
)
from .hunk_file_dialogs import open_blame_window


def _find_main_window(widget):
    """Walk up the widget tree to find the main QMainWindow."""
    w = widget
    while w:
        if isinstance(w, QMainWindow):
            return w
        w = w.parent()
    return None


class CollapsibleSplitterFilter(QObject):
    """Event filter blocking mouse events on a QSplitter handle when collapsed."""

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                            QEvent.MouseMove, QEvent.MouseButtonDblClick):
            return True
        return super().eventFilter(obj, event)


class CollapsibleCommitHeader(QWidget):
    """Clickable header with a disclosure arrow toggling target visibility."""

    toggled = Signal(bool)

    def __init__(self, text, target, parent=None):
        super().__init__(parent)
        self._target = target
        self._expanded = True

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._arrow = QLabel("\u25BC")  # ▼
        self._arrow.setFixedWidth(20)
        self._arrow.setAlignment(Qt.AlignCenter)
        self._arrow.setStyleSheet("QLabel { font-size: 14px; }")
        self._arrow.setCursor(Qt.PointingHandCursor)

        self._label = QLabel(text)
        self._label.setTextFormat(Qt.RichText)
        self._label.setStyleSheet("QLabel { padding: 4px 0; font-size: 13px; }")

        layout.addWidget(self._arrow)
        layout.addWidget(self._label, 1)

        self.setCursor(Qt.PointingHandCursor)
        self.mousePressEvent = self._on_mouse_press

    def _on_mouse_press(self, event):
        self.toggle()

    def toggle(self):
        self._expanded = not self._expanded
        self._target.setVisible(self._expanded)
        self._arrow.setText("\u25BC" if self._expanded else "\u25B6")
        self.toggled.emit(self._expanded)

    def set_text(self, text):
        self._label.setText(text)


class CommitDiffDialogBase(QDialog):
    """Common base class for diff dialogs providing theme colors, metadata loading,
    standard layouts, diff views, tab management, and file-tree synchronization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.colors = {}
        self.font_size = 10
        self.font_family = None
        self._full_diff_text = ""
        self._splitter_filter = None

    @staticmethod
    def setup_colors(parent=None, colors=None, use_settings_fallback=False):
        """Resolve theme colors from parent, settings, or default fallback."""
        if colors is not None:
            return colors
        main_win = parent if isinstance(parent, QMainWindow) else None
        if main_win and hasattr(main_win, 'current_theme_colors'):
            return main_win.current_theme_colors
        if use_settings_fallback:
            return get_theme_colors(tool_settings().value("theme", "light", type=str))
        return {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef", "separator": "#444444"}

    @staticmethod
    def load_commit_metadata(repo_path, sha):
        """Fetch (meta, msg, file_stats, diff_text) for a commit with safety fallbacks."""
        try:
            meta, msg = get_commit_metadata_and_message(repo_path, sha)
        except Exception:
            meta, msg = "Unknown", "Could not fetch message"
        try:
            file_stats = get_commit_file_stats(repo_path, sha)
        except Exception:
            file_stats = {}
        try:
            diff_text = get_commit_diff(repo_path, sha)
        except Exception as e:
            diff_text = f"Error loading diff: {e}"
        return meta, msg, file_stats, diff_text

    @staticmethod
    def merge_mode_changes(file_stats, diff_text):
        """Enrich file_stats with mode changes from diff_text if present."""
        if not diff_text or not (mode_map := parse_commit_mode_changes(diff_text)):
            return file_stats
        res = dict(file_stats) if file_stats else {}
        for f, m in mode_map.items():
            s = res.get(f)
            res[f] = (s[0], s[1], s[2] if len(s) > 2 else 0, s[3] if len(s) > 3 else 0, m[0], m[1]) if s else (0, 0, 0, 0, m[0], m[1])
        return res

    def setup_common_ui(self, title, min_width=860, min_height=620):
        """Configure standard window properties and Ctrl+Q shortcut."""
        self.setWindowTitle(title)
        self.setMinimumSize(min_width, min_height)
        ctrl_q = QShortcut(QKeySequence("Ctrl+Q"), self)
        ctrl_q.setContext(Qt.WindowShortcut)
        ctrl_q.activated.connect(self.close)

    def build_header(self, sha, meta, msg, collapsible=False, on_toggled=None):
        """Build standard commit header with metadata label and read-only message view."""
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        header_text = f"Commit: <b>{sha}</b> <span style='color:gray;'>({meta})</span>"
        self.msg_view = QTextEdit()
        self.msg_view.setReadOnly(True)
        self.msg_view.setPlainText(msg)
        self.msg_view.setFont(mono_font(self.font_size, family=self.font_family))
        self.msg_view.setLineWrapMode(QTextEdit.WidgetWidth)
        self.msg_view.setProperty("class", "commit-msg-view")

        if collapsible:
            self.commit_header = CollapsibleCommitHeader(header_text, self.msg_view)
            if on_toggled:
                self.commit_header.toggled.connect(on_toggled)
        else:
            self.commit_header = QLabel(header_text)
            self.commit_header.setTextFormat(Qt.RichText)

        top_layout.addWidget(self.commit_header)
        top_layout.addWidget(self.msg_view)
        return top_widget

    def build_splitter(self, top_widget, bottom_widget, sizes=None):
        """Create a vertical splitter holding top and bottom widgets."""
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_widget)
        splitter.setSizes(sizes or [150, 450])
        return splitter

    def _build_close_button_layout(self, label="Close", slot=None):
        """Build standard bottom layout with a centered close button."""
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn = QPushButton(label)
        btn.setMinimumWidth(100)
        btn.setProperty("class", "dialog-btn")
        btn.clicked.connect(slot or self.accept)
        btn_layout.addWidget(btn)
        btn_layout.addStretch()
        return btn_layout

    def _create_diff_pane(self, placeholder=None, min_height=100, diff_text=""):
        """Create a DiffView paired with DiffSearchBar and DiffHighlighter."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        view = DiffView()
        view.setReadOnly(True)
        if min_height:
            view.setMinimumHeight(min_height)
        view.setFont(mono_font(self.font_size, family=self.font_family))
        if placeholder:
            view.setPlaceholderText(placeholder)
        if diff_text:
            view.setPlainText(diff_text)
        view.set_separator_color(self.colors.get("separator", "#444444"))

        highlighter = DiffHighlighter(
            view.document(),
            added_color=self.colors.get("added", "#22863a"),
            removed_color=self.colors.get("removed", "#cb2431"),
            header_color=self.colors.get("header", "#66d9ef"),
        )
        search_bar = DiffSearchBar(target_view=view, parent=container)
        layout.addWidget(search_bar)
        layout.addWidget(view)
        # Ensure the container itself has a minimum height so the splitter
        # cannot collapse the diff pane completely.
        if min_height:
            container.setMinimumHeight(min_height)
        return container, view, highlighter, search_bar

    def _create_truncation_banner(self):
        """Create the truncation indicator banner."""
        banner = QWidget()
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)
        label = QLabel()
        label.setStyleSheet("color: #888; font-size: 11px;")
        btn = QPushButton("Show Full Diff")
        btn.setFlat(True)
        btn.setStyleSheet("color: #5599cc; font-size: 11px; border: none; text-decoration: underline;")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self._show_full_diff)
        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(btn)
        banner.setVisible(False)
        return banner, label, btn

    def _create_split_tab(self, top_widget, bottom_container, title, expanded):
        """Build a tab layout containing a vertical splitter."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_container)
        if expanded:
            splitter.setSizes([150, 350])
            tab_title = f"\u25BC {title}"
        else:
            top_widget.setVisible(False)
            splitter.setCollapsible(0, True)
            splitter.setSizes([0, 1000])
            splitter.handle(1).setEnabled(False)
            tab_title = f"\u25B6 {title}"
        layout.addWidget(splitter)
        self.tab_widget.addTab(widget, tab_title)
        return splitter, self.tab_widget.indexOf(widget)

    def build_diff_tabs(self, diff_text, file_stats=None, filewise_expanded=True, treewise_expanded=True):
        """Build 3-tab diff widget (Plain Diff, Filewise Diff, Tree-wise Diff)."""
        self.tab_widget = QTabWidget()

        # Tab 0: Plain Diff
        plain_widget = QWidget()
        plain_layout = QVBoxLayout(plain_widget)
        plain_layout.setContentsMargins(0, 0, 0, 0)
        plain_layout.setSpacing(0)

        self.side_diff_view = DiffView()
        self.side_diff_view.setReadOnly(True)
        self.side_diff_view.setFont(mono_font(self.font_size, family=self.font_family))
        self.plain_highlighter = DiffHighlighter(
            self.side_diff_view.document(),
            added_color=self.colors.get("added", "#22863a"),
            removed_color=self.colors.get("removed", "#cb2431"),
            header_color=self.colors.get("header", "#66d9ef"),
        )
        self.side_diff_view.set_separator_color(self.colors.get("separator", "#444444"))
        self.plain_diff_search = DiffSearchBar(target_view=self.side_diff_view, parent=plain_widget)
        self._truncation_banner, self._truncation_label, self._btn_show_full = self._create_truncation_banner()
        for w in (self.plain_diff_search, self._truncation_banner, self.side_diff_view):
            plain_layout.addWidget(w)
        self._apply_plain_diff_text(diff_text)
        self.tab_widget.addTab(plain_widget, "Plain Diff")

        # Tab 1: Filewise Diff
        self.filewise_file_list = QListWidget()
        self.filewise_file_list.setMinimumHeight(60 if filewise_expanded else 0)
        self.filewise_file_list.setFont(mono_font(self.font_size, family=self.font_family))
        self.filewise_file_list.setItemDelegate(StatsItemDelegate(
            added_color=self.colors.get("added", "#22863a"),
            removed_color=self.colors.get("removed", "#cb2431"),
            parent=self.filewise_file_list,
        ))
        self.filewise_file_list.itemChanged.connect(self._on_filewise_item_changed)
        self.filewise_file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.filewise_file_list.customContextMenuRequested.connect(self.show_filewise_context_menu)
        self.filewise_file_list_filter = FileListFilter(self.filewise_file_list, on_set_all=self._set_all)

        file_right, self.filewise_diff_view, self.filewise_highlighter, self.filewise_diff_search = (
            self._create_diff_pane(placeholder="Select a file above to view its diff...", min_height=100)
        )
        self.filewise_splitter, self._filewise_tab_idx = self._create_split_tab(
            self.filewise_file_list, file_right, "Filewise Diff", filewise_expanded
        )

        # Tab 2: Tree-wise Diff
        self.treewise_tree = QTreeWidget()
        self.treewise_tree.setHeaderLabels(["Name", "Stats"])
        self.treewise_tree.setColumnCount(2)
        self.treewise_tree.header().setDefaultAlignment(Qt.AlignRight)
        self.treewise_tree.header().setStretchLastSection(False)
        self.treewise_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.treewise_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.treewise_tree.setMinimumHeight(60 if treewise_expanded else 0)
        self.treewise_tree.setFont(mono_font(self.font_size, family=self.font_family))
        self.treewise_tree.setAnimated(True)
        self.treewise_tree.setItemDelegateForColumn(1, TreeStatsDelegate(parent=self.treewise_tree))
        self.treewise_tree.itemChanged.connect(self._on_treewise_item_changed)
        self.treewise_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.treewise_tree.customContextMenuRequested.connect(self.show_treewise_context_menu)
        self.treewise_tree_filter = FileListFilter(self.treewise_tree, on_set_all=self._set_all)

        tree_right, self.treewise_diff_view, self.treewise_highlighter, self.treewise_diff_search = (
            self._create_diff_pane(placeholder="Select a file or folder above to view its diff...", min_height=100)
        )
        self.treewise_splitter, self._treewise_tab_idx = self._create_split_tab(
            self.treewise_tree, tree_right, "Tree-wise Diff", treewise_expanded
        )

        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self._focus_active_search)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.tabBar().tabBarClicked.connect(self._on_tab_bar_clicked)

        return self.tab_widget, self.side_diff_view, self.filewise_diff_view

    def _apply_plain_diff_text(self, raw_diff):
        """Clean binary diff lines and apply truncation limit to plain diff view."""
        self._full_diff_text = clean_binary_diff_lines(raw_diff) if raw_diff else ""
        lines = self._full_diff_text.split('\n')
        total_lines = len(lines)
        if total_lines > PLAIN_DIFF_LINE_CAP:
            self.side_diff_view.setPlainText('\n'.join(lines[:PLAIN_DIFF_LINE_CAP]))
            self._truncation_label.setText(
                f"Diff truncated \u2014 {total_lines:,} lines. Showing first {PLAIN_DIFF_LINE_CAP:,}."
            )
            self._truncation_banner.setVisible(True)
        else:
            self.side_diff_view.setPlainText(self._full_diff_text)
            self._truncation_banner.setVisible(False)

    def _show_full_diff(self):
        """Expand full diff text when user clicks Show Full Diff on truncation banner."""
        self.side_diff_view.setPlainText(self._full_diff_text)
        self._truncation_banner.setVisible(False)
        self.side_diff_view.set_separator_color(self.colors.get("separator", "#444444"))
        if hasattr(self, 'plain_diff_search') and self.plain_diff_search.isVisible():
            self.plain_diff_search._perform_search()
        elif hasattr(self, 'search_bar') and self.search_bar.isVisible():
            self.search_bar._perform_search()

    def _focus_active_search(self):
        """Focus the search bar corresponding to the active view/tab."""
        if not hasattr(self, 'tab_widget'):
            if hasattr(self, 'search_bar'):
                self.search_bar.show_and_focus()
            return
        idx = self.tab_widget.currentIndex()
        bars = [getattr(self, 'plain_diff_search', None), getattr(self, 'filewise_diff_search', None), getattr(self, 'treewise_diff_search', None)]
        if 0 <= idx < len(bars) and bars[idx]:
            bars[idx].show_and_focus()

    def _on_tab_changed(self, idx):
        """Refresh diff pane when switching tabs."""
        if idx == 1:
            self._refresh_filewise_diff()
        elif idx == 2:
            self._refresh_treewise_diff()

    def _on_tab_bar_clicked(self, idx):
        if idx == self.tab_widget.currentIndex():
            if idx == getattr(self, '_filewise_tab_idx', -1):
                self._toggle_filewise_file_list()
            elif idx == getattr(self, '_treewise_tab_idx', -1):
                self._toggle_treewise_file_list()
        else:
            if idx == getattr(self, '_filewise_tab_idx', -1) and not self.filewise_file_list.isVisible():
                self._toggle_filewise_file_list()
            elif idx == getattr(self, '_treewise_tab_idx', -1) and not self.treewise_tree.isVisible():
                self._toggle_treewise_file_list()

    def _toggle_pane_list(self, list_widget, splitter, tab_idx, tab_name):
        visible = list_widget.isVisible()
        list_widget.setVisible(not visible)
        self.tab_widget.setTabText(tab_idx, f"{('▶' if visible else '▼')} {tab_name}")
        list_widget.setMinimumHeight(0 if visible else 60)
        splitter.setCollapsible(0, visible)
        splitter.setSizes([0, 1000] if visible else [150, 350])
        splitter.handle(1).setEnabled(not visible)

    def _toggle_filewise_file_list(self):
        self._toggle_pane_list(self.filewise_file_list, self.filewise_splitter, self._filewise_tab_idx, "Filewise Diff")

    def _toggle_treewise_file_list(self):
        self._toggle_pane_list(self.treewise_tree, self.treewise_splitter, self._treewise_tab_idx, "Tree-wise Diff")

    def _get_file_diff(self, filepath):
        """Get diff for a single file. Subclasses override for their diff strategy."""
        return ""

    def on_filewise_file_selected(self, filepath):
        if not filepath:
            if hasattr(self, 'filewise_diff_view'):
                self.filewise_diff_view.clear()
            return
        try:
            diff = self._get_file_diff(filepath)
            self.filewise_diff_view.setPlainText(diff)
            self.filewise_diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.filewise_diff_search._perform_search()
        except Exception as e:
            self.filewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def on_treewise_item_clicked(self, item, column):
        if not (item_data := item.data(0, Qt.UserRole + 10)):
            return
        try:
            if item_data["type"] == "file":
                entry = item_data.get("entry")
                filepath = item_data.get("filepath") or (entry[2] if entry and entry[0] == 'R' else (entry[1] if entry else ""))
                diff = self._get_file_diff(filepath)
                self.treewise_diff_view.setPlainText(diff)
            else:
                diffs = []
                self._collect_folder_diffs(item_data["node"], diffs)
                self.treewise_diff_view.setPlainText("\n".join(diffs))
            self.treewise_diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.treewise_diff_search._perform_search()
        except Exception as e:
            self.treewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def _on_filewise_item_changed(self, item):
        """Handle checkbox change in filewise list: sync to tree and refresh diff."""
        checked = item.checkState() == Qt.Checked
        entry = item.data(FILE_ENTRY_ROLE)
        filepath = (entry[2] if entry[0] == 'R' else entry[1]) if entry else item.text()
        for i in range(self.treewise_tree.topLevelItemCount()):
            self._sync_file_to_tree(self.treewise_tree.topLevelItem(i), filepath, checked)
        self._refresh_filewise_diff()
        self._refresh_treewise_diff()

    def _sync_file_to_tree(self, parent_item, filepath, checked):
        """Recursively find and sync a file's check state in the tree."""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if not (child_data := child.data(0, Qt.UserRole + 10)):
                continue
            if child_data["type"] == "folder":
                self._sync_file_to_tree(child, filepath, checked)
            else:
                entry = child_data.get("entry")
                child_path = child_data.get("filepath") or (entry[2] if entry and entry[0] == 'R' else (entry[1] if entry else ""))
                if child_path == filepath:
                    self.treewise_tree.blockSignals(True)
                    child.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
                    self.treewise_tree.blockSignals(False)
                    p = child.parent()
                    while p:
                        self._update_folder_check_state(p)
                        p = p.parent()
                    return

    def _on_treewise_item_changed(self, item, column):
        """Handle checkbox change in tree: sync to file list and refresh diff."""
        if not (item_data := item.data(0, Qt.UserRole + 10)):
            return
        checked = item.checkState(0) == Qt.Checked
        if item_data["type"] == "folder":
            self._set_tree_children_checked(item, checked)
            self._sync_tree_checked_to_file_list()
        else:
            filepath, entry = item_data.get("filepath", ""), item_data.get("entry")
            self.filewise_file_list.blockSignals(True)
            for i in range(self.filewise_file_list.count()):
                li = self.filewise_file_list.item(i)
                li_entry = li.data(FILE_ENTRY_ROLE)
                if (li_entry and entry and li_entry == entry) or (filepath and li.text() == filepath):
                    li.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                    break
            self.filewise_file_list.blockSignals(False)
        p = item.parent()
        while p:
            self._update_folder_check_state(p)
            p = p.parent()
        self._refresh_treewise_diff()
        self._refresh_filewise_diff()

    def _set_all(self, state):
        """Bulk check/uncheck (floating strip all/none): one refresh, not N."""
        target = Qt.Checked if state else Qt.Unchecked
        self.filewise_file_list.blockSignals(True)
        for i in range(self.filewise_file_list.count()):
            self.filewise_file_list.item(i).setCheckState(target)
        self.filewise_file_list.blockSignals(False)

        self.treewise_tree.blockSignals(True)
        for i in range(self.treewise_tree.topLevelItemCount()):
            item = self.treewise_tree.topLevelItem(i)
            item.setCheckState(0, target)
            set_tree_children_checked(item, state)
        self.treewise_tree.blockSignals(False)
        self._refresh_filewise_diff()
        self._refresh_treewise_diff()

    def _set_tree_children_checked(self, item, checked):
        """Recursively set check state for all children."""
        self.treewise_tree.blockSignals(True)
        set_tree_children_checked(item, checked)
        self.treewise_tree.blockSignals(False)

    def _sync_tree_checked_to_file_list(self):
        self.filewise_file_list.blockSignals(True)

        def sync_item(parent_item):
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                if not (child_data := child.data(0, Qt.UserRole + 10)):
                    continue
                if child_data["type"] == "folder":
                    sync_item(child)
                else:
                    entry, filepath = child_data.get("entry"), child_data.get("filepath")
                    for j in range(self.filewise_file_list.count()):
                        li = self.filewise_file_list.item(j)
                        li_entry = li.data(FILE_ENTRY_ROLE)
                        if (li_entry and entry and li_entry == entry) or (filepath and li.text() == filepath):
                            li.setCheckState(Qt.Checked if child.checkState(0) == Qt.Checked else Qt.Unchecked)
                            break

        sync_item(self.treewise_tree.invisibleRootItem())
        self.filewise_file_list.blockSignals(False)

    def _update_folder_check_state(self, folder_item):
        """Update folder checkbox based on children check states."""
        self.treewise_tree.blockSignals(True)
        update_folder_check_state(folder_item)
        self.treewise_tree.blockSignals(False)

    def _checked_filewise_files(self):
        """Return list of checked file paths in the filewise list."""
        return [
            ((entry[2] if entry[0] == 'R' else entry[1]) if (entry := item.data(FILE_ENTRY_ROLE)) else item.text())
            for i in range(self.filewise_file_list.count())
            if (item := self.filewise_file_list.item(i)).checkState() == Qt.Checked
        ]

    def _refresh_diff_view(self, checked_files, diff_view, search_bar):
        if not checked_files:
            diff_view.clear()
            return
        try:
            parts = [d_clean for f in checked_files if (d := self._get_file_diff(f)) and (d_clean := d.rstrip("\n"))]
            diff_view.setPlainText("\n\n".join(parts) + ("\n" if parts else ""))
            diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            search_bar._perform_search()
        except Exception as e:
            diff_view.setPlainText(f"Error loading diff: {e}")

    def _refresh_filewise_diff(self):
        """Show combined diff of all checked files in the filewise diff pane."""
        self._refresh_diff_view(self._checked_filewise_files(), self.filewise_diff_view, self.filewise_diff_search)

    def _refresh_treewise_diff(self):
        """Show combined diff of all checked tree items."""
        self._refresh_diff_view(self._checked_treewise_files(), self.treewise_diff_view, self.treewise_diff_search)

    def _checked_treewise_files(self):
        """Return list of checked file paths from the tree widget."""
        files = []
        self._collect_checked_tree_files(self.treewise_tree.invisibleRootItem(), files)
        return files

    def _collect_checked_tree_files(self, parent_item, files):
        """Recursively collect checked file paths from tree."""
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            if item.checkState(0) == Qt.Unchecked or not (item_data := item.data(0, Qt.UserRole + 10)):
                continue
            if item_data["type"] == "folder":
                self._collect_checked_tree_files(item, files)
            elif (filepath := item_data.get("filepath", "")) and filepath not in files:
                files.append(filepath)

    def populate_filewise_list(self, files, file_stats=None, target_list=None):
        """Populate a file list widget supporting both plain paths and status tuples."""
        lst = target_list or self.filewise_file_list
        file_stats = file_stats or {}
        lst.blockSignals(True)
        lst.clear()
        for f in files:
            if isinstance(f, (list, tuple)):
                status, path1, path2 = f
                display = f"{path1} => {path2}" if status == 'R' else f"{path1} (Deleted)" if status == 'D' else f"{path1} (Added new file)" if status == 'A' else path1
                tooltip, stats_key, entry = path1, (display if status == 'R' else path1), f
            else:
                display = tooltip = stats_key = f
                entry = ('M', f, '')
            item = QListWidgetItem(display)
            item.setToolTip(tooltip)
            item.setData(Qt.UserRole, file_stats.get(stats_key))
            item.setData(FILE_ENTRY_ROLE, entry)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            lst.addItem(item)
        lst.blockSignals(False)

    def _populate_treewise_tree(self, files, file_stats=None):
        """Build and display the tree-wise file tree from file list or entries."""
        file_stats = file_stats or {}
        self.treewise_tree.blockSignals(True)
        self.treewise_tree.clear()
        if not files:
            self.treewise_tree.blockSignals(False)
            return
        entries = [f if isinstance(f, (list, tuple)) else ('M', f, '') for f in files]
        tree = build_file_tree(entries, file_stats)
        self._add_tree_children(None, tree["children"])
        self.treewise_tree.blockSignals(False)
        for i in range(self.treewise_tree.topLevelItemCount()):
            self.treewise_tree.topLevelItem(i).setExpanded(True)

    def _populate_treewise_from_files(self, files, file_stats=None):
        """Backwards-compatible alias for BranchDiffDialog."""
        self._populate_treewise_tree(files, file_stats)

    def _add_tree_children(self, parent_item, children_dict, added_color=None, removed_color=None):
        """Recursively add folder/file nodes to the QTreeWidget."""
        from lib.git_helpers.commits import format_tree_node_stats
        nodes = sorted(((k, v) for k, v in children_dict.items() if v["children"]), key=lambda x: x[0].lower()) + \
                sorted(((k, v) for k, v in children_dict.items() if not v["children"]), key=lambda x: x[0].lower())
        for name, node in nodes:
            item = QTreeWidgetItem()
            if node["children"]:
                item.setText(0, f"\U0001f4c1 {name}")
                item.setData(0, Qt.UserRole + 10, {"type": "folder", "node": node})
            else:
                entry = node["entries"][0] if node["entries"] else None
                status = entry[0] if entry else ''
                suffix = {"R": f"{entry[1]} => {entry[2]}", "D": f"{name} (Deleted)", "A": f"{name} (Added new file)"} if entry else {}
                display = suffix.get(status, name)
                filepath = (entry[2] if status == 'R' else entry[1]) if entry else name
                item.setText(0, display)
                item.setData(0, Qt.UserRole + 10, {"type": "file", "entry": entry, "filepath": filepath})
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Unchecked)
            if stats_text := format_tree_node_stats(node):
                item.setText(1, stats_text)
                item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            parent_item.addChild(item) if parent_item else self.treewise_tree.addTopLevelItem(item)
            if node["children"]:
                self._add_tree_children(item, node["children"], added_color, removed_color)

    def _collect_folder_diffs(self, node, diffs):
        """Recursively collect diffs for all leaf files under a folder node."""
        for child in node["children"].values():
            if child["children"]:
                self._collect_folder_diffs(child, diffs)
            else:
                for entry in child["entries"]:
                    try:
                        filepath = entry[2] if entry[0] == 'R' and entry[2] else entry[1]
                        diffs.append(self._get_file_diff(filepath))
                    except Exception:
                        pass

    def _get_commit_file_diff(self, entry, filepath):
        """Helper to get diff for a commit file or rename."""
        if entry and entry[0] == 'R':
            return get_rename_diff_in_commit(self.repo_path, self.sha, entry[1], entry[2])
        if entry:
            return get_file_diff_only_in_commit(self.repo_path, self.sha, entry[1])
        return get_file_diff_only_in_commit(self.repo_path, self.sha, filepath)

    def copy_filename_to_clipboard(self, filename):
        QApplication.clipboard().setText(filename)
        QMessageBox.information(self, "Copied", f"Copied '{filename}' to clipboard.")

    def browse_file_log(self, filepath):
        main_win = _find_main_window(self)
        if main_win and hasattr(main_win, 'open_file_log_for'):
            main_win.open_file_log_for(filepath)

    def handle_diff_file_at_ref(self, filepath, current_sha):
        from lib.dialogs.history_branch_dialogs import DiffFileAtRefDialog
        from lib.git_helpers import run_configured_difftool, run_difftool_direct
        head_sha = _get_head_sha(self.repo_path)
        dialog = DiffFileAtRefDialog(self.repo_path, filepath, current_sha, head_sha, parent=self)
        if dialog.exec() != QDialog.Accepted or not (ref_sha := dialog.resolved_sha) or not (target_file := dialog.selected_file):
            return
        source_sha = head_sha if dialog.src_head_radio.isChecked() else current_sha
        is_head_source = dialog.src_head_radio.isChecked() or source_sha == head_sha
        if dialog.use_direct:
            _log(f"[diff] Running direct: {source_sha[:8]} {ref_sha[:8]} -- {target_file} (head_src={is_head_source})")
            ok, err = run_difftool_direct(self.repo_path, source_sha, target_file, ref_sha, target_file, source_is_head=is_head_source)
        else:
            _log(f"[diff] Running configured: difftool {source_sha[:8]} {ref_sha[:8]} -- {target_file}")
            ok, err = run_configured_difftool(self.repo_path, source_sha, target_file, ref_sha, target_file)
        if not ok:
            QMessageBox.critical(self, "Difftool Failed", f"Could not run difftool: {err}")

    def _dispatch_main_action(self, method_name, *args):
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        if main_win and (fn := getattr(main_win, method_name, None)):
            self.accept()
            QTimer.singleShot(0, lambda: fn(*args))

    def move_file_out(self, filepath, checked_files=None):
        self._dispatch_main_action('perform_move_file_out', self.sha, checked_files or [filepath])

    def drop_file(self, filepath, checked_files=None):
        self._dispatch_main_action('perform_drop_file_from_commit', self.sha, checked_files or [filepath])

    def remove_file_onwards(self, filepath):
        self._dispatch_main_action('perform_remove_file_from_commit_onwards', self.sha, filepath)

    def rename_file_onwards(self, filepath):
        self._dispatch_main_action('perform_rename_file_from_commit_onwards', self.sha, filepath)

    def refine_file(self, filepath):
        self._dispatch_main_action('perform_refine_changes', self.sha, filepath)

    def update_font(self):
        """Re-apply the current font to all widgets in this dialog."""
        f = mono_font(self.font_size, family=self.font_family)
        for attr in ('msg_view', 'side_diff_view', 'filewise_file_list', 'filewise_diff_view',
                     'treewise_tree', 'treewise_diff_view', 'diff_view', 'file_list'):
            if (w := getattr(self, attr, None)) is not None:
                w.setFont(f)


class DiffViewerDialog(CommitDiffDialogBase):
    """Base dialog for viewing diffs with centered buttons."""
    def __init__(self, title, sha, diff_text, font_size=10, font_family=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(800, 600)
        self.font_size, self.font_family = font_size, font_family
        self.colors = self.setup_colors(parent)

        self.layout = QVBoxLayout(self)
        self.content_layout = self.layout
        self.setup_header(sha)

        diff_container, self.diff_view, self.highlighter, self.search_bar = self._create_diff_pane()
        self.side_diff_view = self.diff_view
        self._truncation_banner, self._truncation_label, self._btn_show_full = self._create_truncation_banner()
        diff_container.layout().insertWidget(1, self._truncation_banner)

        self.layout.addWidget(diff_container)
        self._apply_plain_diff_text(diff_text)

        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self.search_bar.show_and_focus)

        self.btn_layout = QHBoxLayout()
        self.btn_layout.addStretch()
        self.setup_buttons()
        self.btn_layout.addStretch()
        self.layout.addLayout(self.btn_layout)

    def setup_header(self, sha):
        pass

    def setup_buttons(self):
        pass


class ViewCommitDialog(DiffViewerDialog):
    def __init__(self, sha, commit_message, commit_meta, diff_text, font_size=10, font_family=None, parent=None):
        self._commit_message, self._commit_meta = commit_message, commit_meta
        super().__init__(f"View Commit: {sha}", sha, diff_text, font_size, font_family, parent)

    def setup_header(self, sha):
        label = QLabel(f"Showing changes for commit: <b>{sha}</b>  <span style='color:gray;'>({self._commit_meta})</span>")
        label.setTextFormat(Qt.RichText)
        self.content_layout.addWidget(label)

        msg_box = QTextEdit()
        msg_box.setReadOnly(True)
        msg_box.setPlainText(self._commit_message)
        msg_box.setFont(mono_font(self.font_size, family=self.font_family))
        msg_box.setLineWrapMode(QTextEdit.WidgetWidth)
        msg_box.setProperty("class", "commit-msg-view")
        self.content_layout.addWidget(msg_box)

    def setup_buttons(self):
        ok_btn = QPushButton("Ok")
        ok_btn.setMinimumWidth(100)
        ok_btn.setProperty("class", "dialog-btn")
        ok_btn.clicked.connect(self.accept)
        self.btn_layout.addWidget(ok_btn)


class BranchDiffDialog(CommitDiffDialogBase):
    """Window replicating the right-side diff pane (Plain Diff + Filewise Diff tabs)
    for the combined diff between two commits (consolidated diff / PR preview)."""
    def __init__(self, repo_path, start_sha, end_sha, num_commits, diff_text, files, file_stats,
                 font_size=10, font_family=None, parent=None, colors=None, title=None,
                 description=None, display_start_sha=None):
        super().__init__(parent)
        self.repo_path, self.start_sha, self.end_sha = repo_path, start_sha, end_sha
        self.font_size, self.font_family = font_size, font_family
        title = title or "Consolidated Diff"
        display_start = display_start_sha or start_sha
        self.setup_common_ui(f"{title} — {display_start[:8]} → {end_sha[:8]}")
        self.colors = self.setup_colors(parent, colors)
        file_stats = self.merge_mode_changes(file_stats, diff_text)

        layout = QVBoxLayout(self)
        header_text = f"<b>{title}</b><br><b>{display_start[:8]}</b> → <b>{end_sha[:8]}</b> - {num_commits} commits"
        if description:
            header_text += f"<br><span style='color:#888888'>{description}</span>"
        self.header_label = QLabel(header_text)
        self.header_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.header_label)

        self.build_diff_tabs(diff_text, file_stats, filewise_expanded=True, treewise_expanded=True)
        layout.addWidget(self.tab_widget)

        self.populate_filewise_list(files, file_stats)
        self._populate_treewise_tree(files, file_stats)
        layout.addLayout(self._build_close_button_layout())

    def _get_file_diff(self, filepath):
        return get_file_diff_between(self.repo_path, self.start_sha, self.end_sha, filepath)

    def show_treewise_context_menu(self, pos):
        item = self.treewise_tree.itemAt(pos)
        if not item or not (item_data := item.data(0, Qt.UserRole + 10)) or item_data.get("type") != "file":
            return
        if not (filepath := item_data.get("filepath", "")):
            return
        menu = QMenu(self)
        head = _get_head_sha(self.repo_path)
        checked_files = self._checked_treewise_files()
        multi_select = len(checked_files) > 1

        add_open_with_system_default_action(menu, filepath, self, sha=self.end_sha,
            is_head=self.end_sha == head or head.startswith(self.end_sha), enabled=not multi_select)

        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, t=filepath: open_blame_window(self, t, branch=self.end_sha))
        blame_action.setEnabled(not multi_select)
        menu.addAction(blame_action)

        diff_ref_action = QAction("Diff against a different version of this file", self)
        diff_ref_action.triggered.connect(lambda checked=False, t=filepath: self.handle_diff_file_at_ref(t, self.end_sha))
        diff_ref_action.setEnabled(not multi_select)
        menu.addAction(diff_ref_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, t=filepath: QApplication.clipboard().setText(t))
        copy_action.setEnabled(not multi_select)
        menu.addAction(copy_action)

        menu.addSeparator()
        browse_action = QAction("Browse file log", self)
        browse_action.setToolTip("Open a read-only viewer of this file's history.")
        browse_action.triggered.connect(lambda checked=False, t=filepath: self.browse_file_log(t))
        browse_action.setEnabled(not multi_select)
        menu.addAction(browse_action)
        menu.exec(self.treewise_tree.mapToGlobal(pos))

    def show_filewise_context_menu(self, pos):
        if not (item := self.filewise_file_list.itemAt(pos)):
            return
        target_path = item.text()
        menu = QMenu(self)
        head = _get_head_sha(self.repo_path)
        checked_files = self._checked_filewise_files()
        multi_select = len(checked_files) > 1

        add_open_with_system_default_action(menu, target_path, self, sha=self.end_sha,
            is_head=self.end_sha == head or head.startswith(self.end_sha), enabled=not multi_select)

        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, t=target_path: open_blame_window(self, t, branch=self.end_sha))
        blame_action.setEnabled(not multi_select)
        menu.addAction(blame_action)

        diff_ref_action = QAction("Diff against a different version of this file", self)
        diff_ref_action.triggered.connect(lambda checked=False, t=target_path: self.handle_diff_file_at_ref(t, self.end_sha))
        diff_ref_action.setEnabled(not multi_select)
        menu.addAction(diff_ref_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, t=target_path: self.copy_filename_to_clipboard(t))
        copy_action.setEnabled(not multi_select)
        menu.addAction(copy_action)

        menu.addSeparator()
        browse_action = QAction("Browse file log", self)
        browse_action.setToolTip("Open a read-only viewer of this file's history.")
        browse_action.triggered.connect(lambda checked=False, t=target_path: self.browse_file_log(t))
        browse_action.setEnabled(not multi_select)
        menu.addAction(browse_action)
        menu.exec(self.filewise_file_list.mapToGlobal(pos))


class SingleCommitViewDialog(CommitDiffDialogBase):
    """Single-commit viewer replicating the app's right-side pane: commit
    message on top, with Plain Diff and File-wise Diff tabs below."""

    def __init__(self, repo_path, sha, font_size=10, font_family=None, parent=None, colors=None, editable=False):
        super().__init__(parent)
        self.repo_path, self.sha, self.font_size, self.font_family, self.editable = repo_path, sha, font_size, font_family, editable
        self.setup_common_ui(f"View Commit: {sha}")
        self.colors = self.setup_colors(parent, colors)

        commit_meta, commit_msg, file_stats, diff_text = self.load_commit_metadata(repo_path, sha)
        self._file_stats = file_stats

        layout = QVBoxLayout(self)
        top_widget = self.build_header(sha, commit_meta, commit_msg, collapsible=True, on_toggled=self._on_commit_header_toggled)
        self.build_diff_tabs(diff_text, file_stats, filewise_expanded=False, treewise_expanded=False)
        self.main_splitter = self.build_splitter(top_widget, self.tab_widget, sizes=[150, 450])
        layout.addWidget(self.main_splitter)

        try:
            self._files = get_commit_files_with_status(repo_path, sha)
        except Exception:
            self._files = []

        self.populate_filewise_list(self._files, self._file_stats)
        self._populate_treewise_tree(self._files, self._file_stats)
        layout.addLayout(self._build_close_button_layout())

    def _on_commit_header_toggled(self, expanded):
        splitter = self.main_splitter
        handle = splitter.handle(1)
        if expanded:
            if getattr(self, '_splitter_filter', None):
                handle.removeEventFilter(self._splitter_filter)
                self._splitter_filter = None
            splitter.setCollapsible(0, False)
            splitter.setSizes([150, 450])
        else:
            splitter.setCollapsible(0, True)
            header = splitter.widget(0).layout().itemAt(0).widget()
            splitter.setSizes([header.sizeHint().height(), 1000])
            self._splitter_filter = CollapsibleSplitterFilter(splitter)
            handle.installEventFilter(self._splitter_filter)

    def _get_file_diff(self, filepath):
        """Get diff for a single file in this commit."""
        try:
            for i in range(self.filewise_file_list.count()):
                li = self.filewise_file_list.item(i)
                entry = li.data(FILE_ENTRY_ROLE)
                if (entry and (entry[2] if entry[0] == 'R' else entry[1]) == filepath) or li.text() == filepath:
                    return self._get_commit_file_diff(entry, filepath)
            return self._get_commit_file_diff(None, filepath)
        except Exception as e:
            return f"Error loading diff: {e}"

    def show_treewise_context_menu(self, pos):
        item = self.treewise_tree.itemAt(pos)
        if not item or not (item_data := item.data(0, Qt.UserRole + 10)) or item_data.get("type") != "file":
            return
        entry = item_data.get("entry")
        target_path = entry[2] if entry and entry[0] == 'R' else (entry[1] if entry else "")
        if not target_path:
            return

        menu = QMenu(self)
        head = _get_head_sha(self.repo_path)
        checked_files = self._checked_treewise_files()
        multi_select = len(checked_files) > 1

        add_open_with_system_default_action(menu, target_path, self, sha=self.sha,
            is_head=self.sha == head or head.startswith(self.sha), enabled=not multi_select)

        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, t=target_path: open_blame_window(self, t, branch=self.sha))
        blame_action.setEnabled(not multi_select)
        menu.addAction(blame_action)

        diff_ref_action = QAction("Diff against a different version of this file", self)
        diff_ref_action.triggered.connect(lambda checked=False, t=target_path: self.handle_diff_file_at_ref(t, self.sha))
        diff_ref_action.setEnabled(not multi_select)
        menu.addAction(diff_ref_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, t=target_path: self.copy_filename_to_clipboard(t))
        copy_action.setEnabled(not multi_select)
        menu.addAction(copy_action)

        if self.editable and is_editable_branch(self):
            is_only_file = self.filewise_file_list.count() <= 1
            n = len(checked_files)
            move_label = "Move selected files changes out of this commit" if n > 1 else ("Move selected file changes out of this commit" if n == 1 else "Move file changes out of this commit")
            move_action = QAction(move_label, self)
            move_action.triggered.connect(lambda checked=False, t=target_path, f=checked_files: self.move_file_out(t, f))
            move_action.setEnabled(not is_only_file)
            menu.addAction(move_action)

            drop_label = "Drop selected files changes from this commit" if n > 1 else ("Drop selected file changes from this commit" if n == 1 else "Drop file changes from this commit")
            drop_action = QAction(drop_label, self)
            drop_action.triggered.connect(lambda checked=False, t=target_path, f=checked_files: self.drop_file(t, f))
            drop_action.setEnabled(not is_only_file)
            menu.addAction(drop_action)

            menu.addSeparator()
            rename_onwards_action = QAction("Rename file from this commit onwards", self)
            rename_onwards_action.triggered.connect(lambda checked=False, t=target_path: self.rename_file_onwards(t))
            rename_onwards_action.setEnabled(not multi_select)
            menu.addAction(rename_onwards_action)

            remove_onwards_action = QAction("Remove file from this commit onwards", self)
            remove_onwards_action.triggered.connect(lambda checked=False, t=target_path: self.remove_file_onwards(t))
            remove_onwards_action.setEnabled(not multi_select)
            menu.addAction(remove_onwards_action)

            menu.addSeparator()
            refine_action = QAction("Refine/Edit changes in selected file", self)
            refine_action.triggered.connect(lambda checked=False, t=target_path: self.refine_file(t))
            refine_action.setEnabled(not multi_select)
            menu.addAction(refine_action)

        menu.addSeparator()
        browse_log_action = QAction("Browse file log", self)
        browse_log_action.setToolTip("Open a read-only viewer of this file's history.")
        browse_log_action.triggered.connect(lambda checked=False, t=target_path: self.browse_file_log(t))
        browse_log_action.setEnabled(not multi_select)
        menu.addAction(browse_log_action)
        menu.exec(self.treewise_tree.mapToGlobal(pos))

    def show_filewise_context_menu(self, pos):
        if not (item := self.filewise_file_list.itemAt(pos)):
            return
        entry = item.data(FILE_ENTRY_ROLE)
        target_path = entry[2] if entry and entry[0] == 'R' else (entry[1] if entry else item.text())
        menu = QMenu(self)
        head = _get_head_sha(self.repo_path)
        checked_files = self._checked_filewise_files()
        multi_select = len(checked_files) > 1

        add_open_with_system_default_action(menu, target_path, self, sha=self.sha,
            is_head=self.sha == head or head.startswith(self.sha), enabled=not multi_select)

        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, t=target_path: open_blame_window(self, t, branch=self.sha))
        blame_action.setEnabled(not multi_select)
        menu.addAction(blame_action)

        diff_ref_action = QAction("Diff against a different version of this file", self)
        diff_ref_action.triggered.connect(lambda checked=False, t=target_path: self.handle_diff_file_at_ref(t, self.sha))
        diff_ref_action.setEnabled(not multi_select)
        menu.addAction(diff_ref_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, t=target_path: self.copy_filename_to_clipboard(t))
        copy_action.setEnabled(not multi_select)
        menu.addAction(copy_action)

        if self.editable and is_editable_branch(self):
            is_only_file = self.filewise_file_list.count() <= 1
            n = len(checked_files)
            move_label = "Move selected files changes out of this commit" if n > 1 else ("Move selected file changes out of this commit" if n == 1 else "Move file changes out of this commit")
            move_action = QAction(move_label, self)
            move_action.triggered.connect(lambda checked=False, t=target_path, f=checked_files: self.move_file_out(t, f))
            move_action.setEnabled(not is_only_file)
            menu.addAction(move_action)

            drop_label = "Drop selected files changes from this commit" if n > 1 else ("Drop selected file changes from this commit" if n == 1 else "Drop file changes from this commit")
            drop_action = QAction(drop_label, self)
            drop_action.triggered.connect(lambda checked=False, t=target_path, f=checked_files: self.drop_file(t, f))
            drop_action.setEnabled(not is_only_file)
            menu.addAction(drop_action)

            menu.addSeparator()
            rename_onwards_action = QAction("Rename file from this commit onwards", self)
            rename_onwards_action.triggered.connect(lambda checked=False, t=target_path: self.rename_file_onwards(t))
            rename_onwards_action.setEnabled(not multi_select)
            menu.addAction(rename_onwards_action)

            remove_onwards_action = QAction("Remove file from this commit onwards", self)
            remove_onwards_action.triggered.connect(lambda checked=False, t=target_path: self.remove_file_onwards(t))
            remove_onwards_action.setEnabled(not multi_select)
            menu.addAction(remove_onwards_action)

            menu.addSeparator()
            refine_action = QAction("Refine/Edit changes in selected file", self)
            refine_action.triggered.connect(lambda checked=False, t=target_path: self.refine_file(t))
            refine_action.setEnabled(not multi_select)
            menu.addAction(refine_action)

        menu.addSeparator()
        browse_log_action = QAction("Browse file log", self)
        browse_log_action.setToolTip("Open a read-only viewer of this file's history.")
        browse_log_action.triggered.connect(lambda checked=False, t=target_path: self.browse_file_log(t))
        browse_log_action.setEnabled(not multi_select)
        menu.addAction(browse_log_action)
        menu.exec(self.filewise_file_list.mapToGlobal(pos))


class UnstagedDiffDialog(BranchDiffDialog):
    """Read-only window identical to the PR diff viewer (View PR Diff), but
    showing only the unstaged (worktree vs index) changes. No edits allowed."""
    def __init__(self, repo_path, files, diff_text, file_stats, branch, head_sha, font_size=10, font_family=None, parent=None, colors=None):
        colors = self.setup_colors(parent, colors, use_settings_fallback=True)
        super().__init__(
            repo_path, branch, head_sha, len(files), diff_text,
            files, file_stats, font_size, font_family=font_family, parent=parent, colors=colors
        )
        self.setWindowTitle("Unstaged Changes")
        self.header_label.setText(f"Unstaged Changes: <b>{branch}</b> - {len(files)} file{'s' if len(files) != 1 else ''}")
        for v in (self.side_diff_view, self.filewise_diff_view, self.treewise_diff_view):
            v.setMinimumHeight(200)
        for w in (self.filewise_file_list, self.treewise_tree):
            w.setMinimumHeight(60)
        for s in (self.filewise_splitter, self.treewise_splitter):
            s.setCollapsible(0, False)
            s.setCollapsible(1, False)

    def _on_tab_bar_clicked(self, idx):
        """Clicking a tab label must not collapse the file list / tree pane."""
        return

    def _get_file_diff(self, filepath):
        return get_unstaged_file_diff(self.repo_path, filepath)

    def _collect_folder_diffs_unstaged(self, node, diffs):
        self._collect_folder_diffs(node, diffs)


class StagedDiffDialog(BranchDiffDialog):
    """Read-only window showing staged (index vs HEAD) changes with 3 tabs:
    Plain Diff, File-wise Diff, Tree-wise Diff."""
    def __init__(self, repo_path, files, diff_text, file_stats, branch, head_sha, font_size=10, font_family=None, parent=None, colors=None):
        colors = self.setup_colors(parent, colors, use_settings_fallback=True)
        super().__init__(
            repo_path, branch, head_sha, len(files), diff_text,
            files, file_stats, font_size, font_family=font_family, parent=parent, colors=colors
        )
        self.setWindowTitle("Staged Changes")
        self.header_label.setText(f"Staged Changes: <b>{branch}</b> - {len(files)} file{'s' if len(files) != 1 else ''}")

    def _get_file_diff(self, filepath):
        return get_staged_file_diff(self.repo_path, filepath)

    def _collect_folder_diffs_staged(self, node, diffs):
        self._collect_folder_diffs(node, diffs)


class FileWiseViewDialog(CommitDiffDialogBase):
    """Dialog for viewing changes in a commit file by file."""
    def __init__(self, repo_path, sha, files, font_size=10, font_family=None, parent=None):
        super().__init__(parent)
        self.repo_path, self.sha, self.font_size, self.font_family = repo_path, sha, font_size, font_family
        self.setup_common_ui(f"View Commit File-wise: {sha}")
        self.colors = self.setup_colors(parent)

        meta, msg, self.file_stats, _ = self.load_commit_metadata(repo_path, sha)

        layout = QVBoxLayout(self)
        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self.build_header(sha, meta, msg, collapsible=False))

        file_widget = QWidget()
        file_layout = QVBoxLayout(file_widget)
        file_layout.setContentsMargins(0, 5, 0, 0)
        file_layout.addWidget(QLabel("<b>Select a file</b> to view its changes:"))

        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(60)
        self.file_list.setFont(mono_font(font_size, family=self.font_family))
        self.populate_filewise_list(files, self.file_stats, target_list=self.file_list)
        self.file_list.setItemDelegate(StatsItemDelegate(
            added_color=self.colors.get("added", "#22863a"),
            removed_color=self.colors.get("removed", "#cb2431"),
            parent=self.file_list,
        ))
        self.file_list.itemChanged.connect(self._on_file_item_changed)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self.show_file_context_menu)
        self.file_list_filter = FileListFilter(self.file_list, on_set_all=self._set_all)
        file_layout.addWidget(self.file_list)
        file_widget.setMinimumHeight(80)  # label + 60px file list
        self.main_splitter.addWidget(file_widget)

        diff_widget = QWidget()
        diff_layout = QVBoxLayout(diff_widget)
        diff_layout.setContentsMargins(0, 5, 0, 0)
        diff_layout.addWidget(QLabel("<b>File Diff:</b>"))

        diff_pane, self.diff_view, self.highlighter, self.search_bar = (
            self._create_diff_pane(placeholder="Select a file above to view its diff...", min_height=100)
        )
        diff_layout.addWidget(diff_pane)

        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self.search_bar.show_and_focus)

        diff_widget.setMinimumHeight(120)  # label + 100px diff pane
        self.main_splitter.addWidget(diff_widget)
        self.main_splitter.setSizes([100, 150, 350])
        layout.addWidget(self.main_splitter)

        btn_layout = QHBoxLayout()
        self.counter_label = QLabel()
        self.counter_label.setTextFormat(Qt.RichText)
        btn_layout.addWidget(self.counter_label)
        btn_layout.addStretch()
        for text, state, cls in [("Select All", True, "dialog-btn"), ("Deselect All", False, "dialog-btn-secondary")]:
            btn = QPushButton(text)
            btn.setProperty("class", cls)
            btn.clicked.connect(lambda checked=False, s=state: self._set_all(s))
            btn_layout.addWidget(btn)
        btn_layout.addSpacing(20)
        cancel_btn = QPushButton("Close")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.setProperty("class", "dialog-btn-secondary")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self._update_counter()
        self._refresh_diff()

    def show_file_context_menu(self, pos):
        if not (item := self.file_list.itemAt(pos)):
            return
        entry = item.data(FILE_ENTRY_ROLE)
        target_path = entry[2] if entry and entry[0] == 'R' else (entry[1] if entry else item.text())
        menu = QMenu(self)
        head = _get_head_sha(self.repo_path)
        checked_files = self._checked_files()
        multi_select = len(checked_files) > 1

        add_open_with_system_default_action(menu, target_path, self, sha=self.sha,
            is_head=self.sha == head or head.startswith(self.sha), enabled=not multi_select)

        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, t=target_path: open_blame_window(self, t, branch=self.sha))
        blame_action.setEnabled(not multi_select)
        menu.addAction(blame_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, t=target_path: self.copy_filename_to_clipboard(t))
        copy_action.setEnabled(not multi_select)
        menu.addAction(copy_action)

        is_only_file = self.file_list.count() <= 1

        move_action = QAction("Move selected file changes out of this commit", self)
        move_action.triggered.connect(lambda checked=False, t=target_path: self.move_file_out(t))
        move_action.setEnabled(not is_only_file)
        menu.addAction(move_action)

        drop_action = QAction("Drop file changes from this commit", self)
        drop_action.triggered.connect(lambda checked=False, t=target_path: self.drop_file(t))
        drop_action.setEnabled(not is_only_file)
        menu.addAction(drop_action)

        menu.addSeparator()
        rename_onwards_action = QAction("Rename file from this commit onwards", self)
        rename_onwards_action.triggered.connect(lambda checked=False, t=target_path: self.rename_file_onwards(t))
        rename_onwards_action.setEnabled(not multi_select)
        menu.addAction(rename_onwards_action)

        remove_onwards_action = QAction("Remove file from this commit onwards", self)
        remove_onwards_action.triggered.connect(lambda checked=False, t=target_path: self.remove_file_onwards(t))
        remove_onwards_action.setEnabled(not multi_select)
        menu.addAction(remove_onwards_action)

        menu.addSeparator()
        refine_action = QAction("Refine/Edit changes in selected file", self)
        refine_action.triggered.connect(lambda checked=False, t=target_path: self.refine_file(t))
        refine_action.setEnabled(not multi_select)
        menu.addAction(refine_action)

        menu.addSeparator()
        browse_log_action = QAction("Browse file log", self)
        browse_log_action.setToolTip("Open a read-only viewer of this file's history.")
        browse_log_action.triggered.connect(lambda checked=False, t=target_path: self.browse_file_log(t))
        browse_log_action.setEnabled(not multi_select)
        menu.addAction(browse_log_action)
        menu.exec(self.file_list.mapToGlobal(pos))

    def refine_file(self, filepath):
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        if main_win and hasattr(main_win, 'perform_refine_changes'):
            self.accept()
            QTimer.singleShot(0, lambda: main_win.perform_refine_changes(self.sha, filepath))

    def on_file_selected(self, filepath):
        if not filepath:
            return
        try:
            item = self.file_list.currentItem()
            entry = item.data(FILE_ENTRY_ROLE) if item else None
            diff = self._get_commit_file_diff(entry, filepath)
            self.diff_view.setPlainText(diff)
            self.diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.search_bar._perform_search()
        except Exception as e:
            self.diff_view.setPlainText(f"Error loading diff: {e}")

    def _on_file_item_changed(self, item):
        self._update_counter()
        self._refresh_diff()

    def _update_counter(self):
        self.counter_label.setText(f"<b>{len(self._checked_files())}</b> / {self.file_list.count()} files selected")

    def _checked_files(self):
        return [self.file_list.item(i).text() for i in range(self.file_list.count()) if self.file_list.item(i).checkState() == Qt.Checked]

    def _set_all(self, state):
        self.file_list.blockSignals(True)
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(Qt.Checked if state else Qt.Unchecked)
        self.file_list.blockSignals(False)
        self._update_counter()
        self._refresh_diff()

    def _refresh_diff(self):
        checked = self._checked_files()
        if not checked:
            self.diff_view.clear()
            return
        try:
            parts = [
                d for i in range(self.file_list.count())
                if (item := self.file_list.item(i)).text() in checked
                and (d := self._get_commit_file_diff(item.data(FILE_ENTRY_ROLE), item.text()).rstrip("\n"))
            ]
            self.diff_view.setPlainText("\n\n".join(parts) + ("\n" if parts else ""))
            self.diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.search_bar._perform_search()
        except Exception as e:
            self.diff_view.setPlainText(f"Error loading diff: {e}")
