
if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py (git-interactive-rebase-gui-tool)")
    sys.exit(1)

import os

# pyrefly: ignore [missing-import]
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QListWidget,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QListWidgetItem,
    QMenu,
    QDialog,
    QTextEdit,
    QPlainTextEdit,
    QPushButton,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QLineEdit,
    QSplitter,
    QProgressBar,
    QScrollArea,
    QFrame,
    QCheckBox,
    QSizePolicy,
    QToolButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QSpinBox,
    QComboBox,
    QFileDialog,
)
# pyrefly: ignore [missing-import]
from PySide6.QtCore import (
    Qt,
    QSize,
    QSettings,
    QTimer,
    Signal,
    QRect,
    QEvent,
    QObject,
)
# pyrefly: ignore [missing-import]
from PySide6.QtGui import (
    QFont,
    QFontMetrics,
    QSyntaxHighlighter,
    QTextCharFormat,
    QColor,
    QAction,
    QShortcut,
    QKeySequence,
    QPainter,
    QTextCursor,
    QTextDocument,
)
# pyrefly: ignore [missing-import]
from PySide6.QtWidgets import (
    QStyledItemDelegate,
    QStyle,
    QTableWidget,
    QHeaderView,
    QTableWidgetItem,
)

from lib.git_helpers import (
    get_file_diff_only_in_commit,
    get_commit_metadata_and_message,
    get_revert_commit_message,
    get_commit_file_stats,
    get_file_diff_between,
    get_unstaged_diff,
    get_unstaged_file_stats,
    get_unstaged_file_diff,
    get_staged_file_diff,
    get_current_branch,
    get_full_head_sha,
    classify_tracked_changes,
    get_branch_names,
    get_rename_diff_in_commit,
    get_commit_diff,
    get_commit_files_with_status,
    build_file_tree,
)
from lib.utils import get_theme_colors
from lib.widgets import (
    BrowseDimOverlay,
    DiffHighlighter,
    DiffSearchBar,
    DiffView,
    FILE_ENTRY_ROLE,
    StatsItemDelegate,
    TreeStatsDelegate,
)
from .hunk_file_dialogs import open_blame_window
from lib.app_window.helpers import add_open_with_system_default_action, is_editable_branch, _get_head_sha


def _find_main_window(widget):
    """Walk up the widget tree to find the main QMainWindow."""
    w = widget
    while w:
        if isinstance(w, QMainWindow):
            return w
        w = w.parent()
    return None


class DiffViewerDialog(QDialog):
    """Base dialog for viewing diffs with centered buttons."""
    def __init__(self, title, sha, diff_text, font_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(800, 600)
        self.font_size = font_size

        self.layout = QVBoxLayout(self)

        # Header info
        self.setup_header(sha)

        # Full diff view
        self.diff_view = DiffView()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(QFont("Courier New", self.font_size))
        self.diff_view.setPlainText(diff_text)

        # Determine highlighting colors based on parent theme or default to dark
        app = QApplication.instance()
        main_win = parent if isinstance(parent, QMainWindow) else None
        if main_win and hasattr(main_win, 'current_theme_colors'):
             colors = main_win.current_theme_colors
        else:
             # Default dark-ish colors if not found
             colors = {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef"}

        self.highlighter = DiffHighlighter(self.diff_view.document(), 
                                           added_color=colors["added"],
                                           removed_color=colors["removed"],
                                           header_color=colors["header"])

        self.diff_view.set_separator_color(colors.get("separator", "#444444"))

        # Wrap search and diff view so they appear as one item in self.layout
        diff_container = QWidget()
        diff_container_layout = QVBoxLayout(diff_container)
        diff_container_layout.setContentsMargins(0, 0, 0, 0)
        diff_container_layout.setSpacing(0)

        self.search_bar = DiffSearchBar(target_view=self.diff_view, parent=diff_container)
        diff_container_layout.addWidget(self.search_bar)

        diff_container_layout.addWidget(self.diff_view)

        self.layout.addWidget(diff_container)

        # Connect Ctrl+F explicitly just in case focus escapes
        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self.search_bar.show_and_focus)

        # Buttons
        self.btn_layout = QHBoxLayout()
        self.btn_layout.addStretch() # Center spacer left
        self.setup_buttons()
        self.btn_layout.addStretch() # Center spacer right
        self.layout.addLayout(self.btn_layout)

    def setup_header(self, sha):
        pass # To be overridden

    def setup_buttons(self):
        pass # To be overridden


class ViewCommitDialog(DiffViewerDialog):
    def __init__(self, sha, commit_message, commit_meta, diff_text, font_size=10, parent=None):
        self._commit_message = commit_message
        self._commit_meta = commit_meta
        super().__init__(f"View Commit: {sha}", sha, diff_text, font_size, parent)

        # Convert fixed layout into a QSplitter
        label = self.layout.itemAt(0).widget()
        msg_box = self.layout.itemAt(1).widget()
        diff_view = self.layout.itemAt(2).widget()

        self.layout.removeWidget(label)
        self.layout.removeWidget(msg_box)
        self.layout.removeWidget(diff_view)

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(label)
        top_layout.addWidget(msg_box)

        splitter.addWidget(top_widget)
        splitter.addWidget(diff_view)

        self.layout.insertWidget(0, splitter)
        splitter.setSizes([150, 450])

    def setup_header(self, sha):
        label = QLabel(f"Showing changes for commit: <b>{sha}</b>  <span style='color:gray;'>({self._commit_meta})</span>")
        label.setTextFormat(Qt.RichText)
        self.layout.addWidget(label)

        # Commit message box
        msg_box = QTextEdit()
        msg_box.setReadOnly(True)
        msg_box.setPlainText(self._commit_message)
        msg_box.setFont(QFont("Courier New", self.font_size))
        msg_box.setLineWrapMode(QTextEdit.WidgetWidth)
        msg_box.setProperty("class", "commit-msg-view")
        self.layout.addWidget(msg_box)

    def setup_buttons(self):
        ok_btn = QPushButton("Ok")
        ok_btn.setMinimumWidth(100)
        ok_btn.setProperty("class", "dialog-btn")
        ok_btn.clicked.connect(self.accept)
        self.btn_layout.addWidget(ok_btn)


class BranchDiffDialog(QDialog):
    """Window replicating the right-side diff pane (Plain Diff + Filewise Diff tabs)
    for the combined diff between two commits (consolidated diff / PR preview)."""
    def __init__(self, repo_path, start_sha, end_sha, num_commits, diff_text, files, file_stats, font_size=10, parent=None, colors=None, title=None, description=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.start_sha = start_sha
        self.end_sha = end_sha
        self.font_size = font_size
        title = title or "Consolidated Diff"
        self.setWindowTitle(f"{title} — {start_sha[:8]} → {end_sha[:8]}")
        self.setMinimumSize(860, 620)

        # Diff colors: optional pre-resolved colors, else from the parent theme
        if colors is None:
            main_win = parent if isinstance(parent, QMainWindow) else None
            if main_win and hasattr(main_win, 'current_theme_colors'):
                colors = main_win.current_theme_colors
            else:
                colors = {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef", "separator": "#444444"}
        self.colors = colors

        layout = QVBoxLayout(self)

        # Header
        header_text = (
            f"<b>{title}</b><br>"
            f"<b>{start_sha[:8]}</b> → <b>{end_sha[:8]}</b> - {num_commits} commits"
        )
        if description:
            header_text += f"<br><span style='color:#888888'>{description}</span>"
        header = QLabel(header_text)
        header.setTextFormat(Qt.RichText)
        self.header_label = header
        layout.addWidget(header)

        # Diff Tab Widget
        self.tab_widget = QTabWidget()

        # Tab 0: Plain Diff
        plain_widget = QWidget()
        plain_layout = QVBoxLayout(plain_widget)
        plain_layout.setContentsMargins(0, 0, 0, 0)
        plain_layout.setSpacing(0)

        self.side_diff_view = DiffView()
        self.side_diff_view.setReadOnly(True)
        self.side_diff_view.setFont(QFont("Courier New", font_size))
        self.side_diff_view.setPlainText(diff_text)
        self.plain_highlighter = DiffHighlighter(
            self.side_diff_view.document(),
            added_color=colors["added"],
            removed_color=colors["removed"],
            header_color=colors["header"]
        )
        self.side_diff_view.set_separator_color(colors.get("separator", "#444444"))

        self.plain_diff_search = DiffSearchBar(target_view=self.side_diff_view, parent=plain_widget)
        plain_layout.addWidget(self.plain_diff_search)
        plain_layout.addWidget(self.side_diff_view)

        self.tab_widget.addTab(plain_widget, "Plain Diff")

        # Tab 1: Filewise Diff
        filewise_widget = QWidget()
        filewise_layout = QVBoxLayout(filewise_widget)
        filewise_layout.setContentsMargins(0, 0, 0, 0)
        filewise_layout.setSpacing(0)

        self.filewise_splitter = QSplitter(Qt.Vertical)

        # File list
        self.filewise_file_list = QListWidget()
        self.filewise_file_list.setMinimumHeight(60)
        self.filewise_file_list.setFont(QFont("Courier New", font_size))
        stats_delegate = StatsItemDelegate(
            added_color=colors.get("added", "#22863a"),
            removed_color=colors.get("removed", "#cb2431"),
            parent=self.filewise_file_list
        )
        self.filewise_file_list.setItemDelegate(stats_delegate)
        self.filewise_file_list.itemChanged.connect(self._on_filewise_item_changed)
        self.filewise_splitter.addWidget(self.filewise_file_list)

        # File diff view + search
        file_right_widget = QWidget()
        file_right_layout = QVBoxLayout(file_right_widget)
        file_right_layout.setContentsMargins(0, 0, 0, 0)
        file_right_layout.setSpacing(0)

        self.filewise_diff_view = DiffView()
        self.filewise_diff_view.setReadOnly(True)
        self.filewise_diff_view.setMinimumHeight(100)
        self.filewise_diff_view.setFont(QFont("Courier New", font_size))
        self.filewise_diff_view.setPlaceholderText("Select a file above to view its diff...")
        self.filewise_highlighter = DiffHighlighter(
            self.filewise_diff_view.document(),
            added_color=colors["added"],
            removed_color=colors["removed"],
            header_color=colors["header"]
        )

        self.filewise_diff_search = DiffSearchBar(target_view=self.filewise_diff_view, parent=file_right_widget)
        file_right_layout.addWidget(self.filewise_diff_search)
        file_right_layout.addWidget(self.filewise_diff_view)

        self.filewise_splitter.addWidget(file_right_widget)
        self.filewise_splitter.setSizes([150, 350])
        filewise_layout.addWidget(self.filewise_splitter)

        self.tab_widget.addTab(filewise_widget, "\u25BC Filewise Diff")
        self._filewise_tab_idx = self.tab_widget.indexOf(filewise_widget)

        # Tab 2: Tree-wise Diff
        treewise_widget = QWidget()
        treewise_layout = QVBoxLayout(treewise_widget)
        treewise_layout.setContentsMargins(0, 0, 0, 0)
        treewise_layout.setSpacing(0)

        self.treewise_splitter = QSplitter(Qt.Vertical)

        self.treewise_tree = QTreeWidget()
        self.treewise_tree.setHeaderLabels(["Name", "Stats"])
        self.treewise_tree.setColumnCount(2)
        self.treewise_tree.header().setDefaultAlignment(Qt.AlignRight)
        self.treewise_tree.header().setStretchLastSection(False)
        self.treewise_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.treewise_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.treewise_tree.setMinimumHeight(60)
        self.treewise_tree.setFont(QFont("Courier New", font_size))
        self.treewise_tree.setAnimated(True)
        self.treewise_tree.setItemDelegateForColumn(1, TreeStatsDelegate())
        self.treewise_tree.itemChanged.connect(self._on_treewise_item_changed)
        self.treewise_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.treewise_tree.customContextMenuRequested.connect(self.show_treewise_context_menu)
        self.treewise_splitter.addWidget(self.treewise_tree)

        treewise_right_widget = QWidget()
        treewise_right_layout = QVBoxLayout(treewise_right_widget)
        treewise_right_layout.setContentsMargins(0, 0, 0, 0)
        treewise_right_layout.setSpacing(0)

        self.treewise_diff_view = DiffView()
        self.treewise_diff_view.setReadOnly(True)
        self.treewise_diff_view.setMinimumHeight(100)
        self.treewise_diff_view.setFont(QFont("Courier New", font_size))
        self.treewise_diff_view.setPlaceholderText("Select a file or folder above to view its diff...")
        self.treewise_highlighter = DiffHighlighter(
            self.treewise_diff_view.document(),
            added_color=colors["added"],
            removed_color=colors["removed"],
            header_color=colors["header"]
        )
        self.treewise_diff_search = DiffSearchBar(target_view=self.treewise_diff_view, parent=treewise_right_widget)
        treewise_right_layout.addWidget(self.treewise_diff_search)
        treewise_right_layout.addWidget(self.treewise_diff_view)

        self.treewise_splitter.addWidget(treewise_right_widget)
        self.treewise_splitter.setSizes([150, 350])
        treewise_layout.addWidget(self.treewise_splitter)

        self.tab_widget.addTab(treewise_widget, "\u25BC Tree-wise Diff")
        self._treewise_tab_idx = self.tab_widget.indexOf(treewise_widget)

        layout.addWidget(self.tab_widget)

        # Populate the file list (block signals to avoid premature load)
        self.filewise_file_list.blockSignals(True)
        for f in files:
            item = QListWidgetItem(f)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, file_stats.get(f))
            # Store entry tuple so tree↔file sync can match by FILE_ENTRY_ROLE
            item.setData(FILE_ENTRY_ROLE, ('M', f, ''))
            self.filewise_file_list.addItem(item)
        self.filewise_file_list.blockSignals(False)

        # Context menu for the file list
        self.filewise_file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.filewise_file_list.customContextMenuRequested.connect(self.show_filewise_context_menu)

        # Populate tree-wise tab (BranchDiffDialog uses plain file strings, not status tuples)
        self._populate_treewise_from_files(files, file_stats)

        # Ctrl+F focuses the search bar of the active tab
        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self._focus_active_search)

        # Refresh diff when switching tabs
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.tabBar().tabBarClicked.connect(self._on_tab_bar_clicked)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("Close")
        ok_btn.setMinimumWidth(100)
        ok_btn.setProperty("class", "dialog-btn")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _focus_active_search(self):
        idx = self.tab_widget.currentIndex()
        if idx == 0:
            self.plain_diff_search.show_and_focus()
        elif idx == 1:
            self.filewise_diff_search.show_and_focus()
        elif idx == 2:
            self.treewise_diff_search.show_and_focus()

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

    def _toggle_filewise_file_list(self):
        visible = self.filewise_file_list.isVisible()
        self.filewise_file_list.setVisible(not visible)
        arrow = "\u25B6" if visible else "\u25BC"
        self.tab_widget.setTabText(self._filewise_tab_idx,
                                   f"{arrow} Filewise Diff")
        if visible:
            self.filewise_splitter.setSizes([0, 1000])
        else:
            self.filewise_splitter.setSizes([150, 350])

    def _toggle_treewise_file_list(self):
        visible = self.treewise_tree.isVisible()
        self.treewise_tree.setVisible(not visible)
        arrow = "\u25B6" if visible else "\u25BC"
        self.tab_widget.setTabText(self._treewise_tab_idx,
                                   f"{arrow} Tree-wise Diff")
        if visible:
            self.treewise_splitter.setSizes([0, 1000])
        else:
            self.treewise_splitter.setSizes([150, 350])

    def _populate_treewise_from_files(self, files, file_stats):
        """Build tree from plain file list (BranchDiffDialog uses file strings, not status tuples)."""
        self.treewise_tree.blockSignals(True)
        self.treewise_tree.clear()
        if not files:
            self.treewise_tree.blockSignals(False)
            return
        entries = [('M', f, '') for f in files]
        tree = build_file_tree(entries, file_stats)
        added_color = self.colors.get("added", "#22863a")
        removed_color = self.colors.get("removed", "#cb2431")
        self._add_tree_children(None, tree["children"], added_color, removed_color)
        self.treewise_tree.blockSignals(False)
        for i in range(self.treewise_tree.topLevelItemCount()):
            self.treewise_tree.topLevelItem(i).setExpanded(True)

    def _add_tree_children(self, parent_item, children_dict, added_color="#22863a", removed_color="#cb2431"):
        """Recursively add folder/file nodes to the QTreeWidget."""
        from lib.git_helpers.commits import format_tree_node_stats
        folders = sorted(((k, v) for k, v in children_dict.items() if v["children"]),
                         key=lambda x: x[0].lower())
        files = sorted(((k, v) for k, v in children_dict.items() if not v["children"]),
                       key=lambda x: x[0].lower())
        for name, node in folders + files:
            item = QTreeWidgetItem()
            if node["children"]:
                item.setText(0, f"\U0001f4c1 {name}")
                item.setData(0, Qt.UserRole + 10, {"type": "folder", "node": node})
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Unchecked)
                stats_text = format_tree_node_stats(node)
                if stats_text:
                    item.setText(1, stats_text)
                    item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
                if parent_item:
                    parent_item.addChild(item)
                else:
                    self.treewise_tree.addTopLevelItem(item)
                self._add_tree_children(item, node["children"], added_color, removed_color)
            else:
                entry = node["entries"][0] if node["entries"] else None
                filepath = entry[1] if entry else name
                item.setText(0, name)
                item.setData(0, Qt.UserRole + 10, {"type": "file", "entry": entry, "filepath": filepath})
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Unchecked)
                stats_text = format_tree_node_stats(node)
                if stats_text:
                    item.setText(1, stats_text)
                    item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
                if parent_item:
                    parent_item.addChild(item)
                else:
                    self.treewise_tree.addTopLevelItem(item)

    def on_treewise_item_clicked(self, item, column):
        """Handle click on tree-wise item."""
        item_data = item.data(0, Qt.UserRole + 10)
        if not item_data:
            return
        try:
            if item_data["type"] == "file":
                entry = item_data.get("entry")
                filepath = entry[2] if entry and entry[0] == 'R' else (entry[1] if entry else "")
                diff = get_file_diff_between(self.repo_path, self.start_sha, self.end_sha, filepath)
                self.treewise_diff_view.setPlainText(diff)
            else:
                diffs = []
                self._collect_folder_diffs(item_data["node"], diffs)
                self.treewise_diff_view.setPlainText("\n".join(diffs))
            self.treewise_diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.treewise_diff_search._perform_search()
        except Exception as e:
            self.treewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def _collect_folder_diffs(self, node, diffs):
        """Recursively collect diffs for all leaf files under a folder node."""
        for child in node["children"].values():
            if child["children"]:
                self._collect_folder_diffs(child, diffs)
            else:
                for entry in child["entries"]:
                    try:
                        filepath = entry[2] if entry[0] == 'R' and entry[2] else entry[1]
                        diff = get_file_diff_between(self.repo_path, self.start_sha, self.end_sha, filepath)
                        diffs.append(diff)
                    except Exception:
                        pass

    def show_treewise_context_menu(self, pos):
        """Context menu for tree-wise file items in BranchDiffDialog."""
        item = self.treewise_tree.itemAt(pos)
        if not item:
            return
        item_data = item.data(0, Qt.UserRole + 10)
        if not item_data or item_data["type"] != "file":
            return
        filepath = item_data.get("filepath", "")
        if not filepath:
            return
        menu = QMenu(self)
        head = _get_head_sha(self.repo_path)
        add_open_with_system_default_action(menu, filepath, self, sha=self.end_sha,
            is_head=self.end_sha == head or head.startswith(self.end_sha))
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=filepath: open_blame_window(self, text, branch=self.end_sha))
        menu.addAction(blame_action)

        diff_ref_action = QAction("Diff against a different version of this file", self)
        diff_ref_action.triggered.connect(lambda checked=False, text=filepath: self.handle_diff_file_at_ref(text, self.end_sha))
        menu.addAction(diff_ref_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=filepath: QApplication.clipboard().setText(text))
        menu.addAction(copy_action)

        menu.addSeparator()
        browse_action = QAction("Browse file log", self)
        browse_action.setToolTip("Open a read-only viewer of this file's history.")
        browse_action.triggered.connect(lambda checked=False, text=filepath: self.browse_file_log(text))
        menu.addAction(browse_action)
        menu.exec(self.treewise_tree.mapToGlobal(pos))

    def on_filewise_file_selected(self, filepath):
        if not filepath:
            self.filewise_diff_view.clear()
            return
        try:
            diff = get_file_diff_between(self.repo_path, self.start_sha, self.end_sha, filepath)
            self.filewise_diff_view.setPlainText(diff)
            self.filewise_diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.filewise_diff_search._perform_search()
        except Exception as e:
            self.filewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def show_filewise_context_menu(self, pos):
        """Context menu for the file list: copy filename or browse the file log."""
        item = self.filewise_file_list.itemAt(pos)
        if not item:
            return
        target_path = item.text()
        menu = QMenu(self)
        head = _get_head_sha(self.repo_path)
        add_open_with_system_default_action(menu, target_path, self, sha=self.end_sha,
            is_head=self.end_sha == head or head.startswith(self.end_sha))
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=target_path: open_blame_window(self, text, branch=self.end_sha))
        menu.addAction(blame_action)

        diff_ref_action = QAction("Diff against a different version of this file", self)
        diff_ref_action.triggered.connect(lambda checked=False, text=target_path: self.handle_diff_file_at_ref(text, self.end_sha))
        menu.addAction(diff_ref_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=target_path: self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)

        menu.addSeparator()
        browse_action = QAction("Browse file log", self)
        browse_action.setToolTip("Open a read-only viewer of this file's history.")
        browse_action.triggered.connect(lambda checked=False, text=target_path: self.browse_file_log(text))
        menu.addAction(browse_action)
        menu.exec(self.filewise_file_list.mapToGlobal(pos))

    def browse_file_log(self, filepath):
        main_win = _find_main_window(self)
        if main_win and hasattr(main_win, 'open_file_log_for'):
            main_win.open_file_log_for(filepath)

    def copy_filename_to_clipboard(self, filename):
        QApplication.clipboard().setText(filename)
        QMessageBox.information(self, "Copied", f"Copied '{filename}' to clipboard.")

    def handle_diff_file_at_ref(self, filepath, current_sha):
        from lib.dialogs.history_branch_dialogs import DiffFileAtRefDialog
        from lib.git_helpers import run_configured_difftool, run_difftool_direct
        head_sha = _get_head_sha(self.repo_path)
        dialog = DiffFileAtRefDialog(self.repo_path, filepath, current_sha, head_sha, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        ref_sha = dialog.resolved_sha
        target_file = dialog.selected_file
        if not ref_sha or not target_file:
            return
        source_sha = head_sha if dialog.src_head_radio.isChecked() else current_sha
        is_head_source = dialog.src_head_radio.isChecked() or source_sha == head_sha
        if dialog.use_direct:
            print(f"[diff] Running direct: {source_sha[:8]} {ref_sha[:8]} -- {target_file} (head_src={is_head_source})")
            ok, err = run_difftool_direct(self.repo_path, source_sha, target_file, ref_sha, target_file,
                                          source_is_head=is_head_source)
        else:
            print(f"[diff] Running configured: difftool {source_sha[:8]} {ref_sha[:8]} -- {target_file}")
            ok, err = run_configured_difftool(self.repo_path, source_sha, target_file, ref_sha, target_file)
        if not ok:
            QMessageBox.critical(self, "Difftool Failed", f"Could not run difftool: {err}")

    def _get_file_diff(self, filepath):
        """Get diff for a single file. Subclasses override for different scopes."""
        return get_file_diff_between(self.repo_path, self.start_sha, self.end_sha, filepath)

    def _on_filewise_item_changed(self, item):
        """Handle checkbox change in filewise list: sync to tree and refresh diff."""
        checked = item.checkState() == Qt.Checked
        entry = item.data(FILE_ENTRY_ROLE)
        if entry:
            filepath = entry[2] if entry[0] == 'R' else entry[1]
        else:
            filepath = item.text()
        for i in range(self.treewise_tree.topLevelItemCount()):
            self._sync_file_to_tree(self.treewise_tree.topLevelItem(i), filepath, checked)
        self._refresh_filewise_diff()
        self._refresh_treewise_diff()

    def _sync_file_to_tree(self, parent_item, filepath, checked):
        """Recursively find and sync a file's check state in the tree."""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            child_data = child.data(0, Qt.UserRole + 10)
            if not child_data:
                continue
            if child_data["type"] == "folder":
                self._sync_file_to_tree(child, filepath, checked)
            elif child_data.get("filepath") == filepath:
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
        item_data = item.data(0, Qt.UserRole + 10)
        if not item_data:
            return
        checked = item.checkState(0) == Qt.Checked
        if item_data["type"] == "folder":
            self._set_tree_children_checked(item, checked)
            self._sync_tree_checked_to_file_list()
            p = item.parent()
            while p:
                self._update_folder_check_state(p)
                p = p.parent()
        else:
            filepath = item_data.get("filepath", "")
            entry = item_data.get("entry")
            for i in range(self.filewise_file_list.count()):
                list_item = self.filewise_file_list.item(i)
                list_entry = list_item.data(FILE_ENTRY_ROLE)
                if list_entry and list_entry == entry:
                    self.filewise_file_list.blockSignals(True)
                    list_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                    self.filewise_file_list.blockSignals(False)
                    break
            p = item.parent()
            while p:
                self._update_folder_check_state(p)
                p = p.parent()
        self._refresh_treewise_diff()
        self._refresh_filewise_diff()

    def _set_tree_children_checked(self, item, checked):
        """Recursively set check state for all children."""
        self.treewise_tree.blockSignals(True)
        self._set_tree_children_checked_impl(item, checked)
        self.treewise_tree.blockSignals(False)

    def _set_tree_children_checked_impl(self, item, checked):
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
            child_data = child.data(0, Qt.UserRole + 10)
            if child_data and child_data["type"] == "folder":
                self._set_tree_children_checked_impl(child, checked)

    def _sync_tree_checked_to_file_list(self):
        self.filewise_file_list.blockSignals(True)

        def sync_item(parent_item):
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                child_data = child.data(0, Qt.UserRole + 10)
                if not child_data:
                    continue
                if child_data["type"] == "folder":
                    sync_item(child)
                else:
                    entry = child_data.get("entry")
                    if not entry:
                        continue
                    for j in range(self.filewise_file_list.count()):
                        li = self.filewise_file_list.item(j)
                        li_entry = li.data(FILE_ENTRY_ROLE)
                        if li_entry and li_entry == entry:
                            li.setCheckState(Qt.Checked if child.checkState(0) == Qt.Checked else Qt.Unchecked)
                            break

        sync_item(self.treewise_tree.invisibleRootItem())
        self.filewise_file_list.blockSignals(False)

    def _update_folder_check_state(self, folder_item):
        """Update folder checkbox based on children check states."""
        if folder_item.childCount() == 0:
            return
        all_checked = True
        has_checked = False
        for i in range(folder_item.childCount()):
            child = folder_item.child(i)
            child_data = child.data(0, Qt.UserRole + 10)
            if child_data and child_data["type"] == "folder":
                self._update_folder_check_state(child)
                if child.checkState(0) == Qt.Checked:
                    has_checked = True
                else:
                    all_checked = False
            else:
                if child.checkState(0) == Qt.Checked:
                    has_checked = True
                else:
                    all_checked = False
        self.treewise_tree.blockSignals(True)
        if all_checked:
            folder_item.setCheckState(0, Qt.Checked)
        elif has_checked:
            folder_item.setCheckState(0, Qt.PartiallyChecked)
        else:
            folder_item.setCheckState(0, Qt.Unchecked)
        self.treewise_tree.blockSignals(False)

    def _checked_filewise_files(self):
        """Return list of checked file paths in the filewise list."""
        result = []
        for i in range(self.filewise_file_list.count()):
            item = self.filewise_file_list.item(i)
            if item.checkState() == Qt.Checked:
                entry = item.data(FILE_ENTRY_ROLE)
                if entry:
                    result.append(entry[2] if entry[0] == 'R' else entry[1])
                else:
                    result.append(item.text())
        return result

    def _refresh_filewise_diff(self):
        """Show combined diff of all checked files in the filewise diff pane."""
        checked = self._checked_filewise_files()
        if not checked:
            self.filewise_diff_view.clear()
            return
        try:
            parts = []
            for f in checked:
                d = self._get_file_diff(f).rstrip("\n")
                if d:
                    parts.append(d)
            text = "\n\n".join(parts) + ("\n" if parts else "")
            self.filewise_diff_view.setPlainText(text)
            self.filewise_diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.filewise_diff_search._perform_search()
        except Exception as e:
            self.filewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def _refresh_treewise_diff(self):
        """Show combined diff of all checked tree items."""
        checked = self._checked_treewise_files()
        if not checked:
            self.treewise_diff_view.clear()
            return
        try:
            parts = []
            for f in checked:
                d = self._get_file_diff(f).rstrip("\n")
                if d:
                    parts.append(d)
            text = "\n\n".join(parts) + ("\n" if parts else "")
            self.treewise_diff_view.setPlainText(text)
            self.treewise_diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.treewise_diff_search._perform_search()
        except Exception as e:
            self.treewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def _checked_treewise_files(self):
        """Return list of checked file paths from the tree widget."""
        files = []
        self._collect_checked_tree_files(self.treewise_tree.invisibleRootItem(), files)
        return files

    def _collect_checked_tree_files(self, parent_item, files):
        """Recursively collect checked file paths from tree."""
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            if item.checkState(0) == Qt.Unchecked:
                continue
            item_data = item.data(0, Qt.UserRole + 10)
            if not item_data:
                continue
            if item_data["type"] == "folder":
                self._collect_checked_tree_files(item, files)
            else:
                filepath = item_data.get("filepath", "")
                if filepath and filepath not in files:
                    files.append(filepath)


class CollapsibleSplitterFilter(QObject):
    """Event filter that blocks mouse events on a QSplitter handle,
    preventing the user from dragging to resize a collapsed pane."""

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                            QEvent.MouseMove, QEvent.MouseButtonDblClick):
            return True
        return super().eventFilter(obj, event)


class CollapsibleCommitHeader(QWidget):
    """Clickable header with a disclosure arrow that toggles visibility of a
    target widget (typically the commit message)."""

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
        self._arrow.setText("\u25BC" if self._expanded else "\u25B6")  # ▼ / ▶
        self.toggled.emit(self._expanded)

    def set_text(self, text):
        self._label.setText(text)


class SingleCommitViewDialog(QDialog):
    """Single-commit viewer replicating the app's right-side pane: commit
    message on top, with Plain Diff and File-wise Diff tabs below."""

    def __init__(self, repo_path, sha, font_size=10, parent=None, colors=None, editable=False):
        super().__init__(parent)
        self.repo_path = repo_path
        self.sha = sha
        self.font_size = font_size
        self.editable = editable
        self.setWindowTitle(f"View Commit: {sha}")
        self.setMinimumSize(860, 620)

        # Ctrl+Q closes the window (consistent with main app)
        from PySide6.QtGui import QShortcut, QKeySequence
        ctrl_q = QShortcut(QKeySequence("Ctrl+Q"), self)
        ctrl_q.setContext(Qt.WindowShortcut)
        ctrl_q.activated.connect(self.close)

        # Diff colors: optional pre-resolved colors, else from the parent theme
        if colors is None:
            main_win = parent if isinstance(parent, QMainWindow) else None
            if main_win and hasattr(main_win, 'current_theme_colors'):
                colors = main_win.current_theme_colors
            else:
                colors = {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef", "separator": "#444444"}
        self.colors = colors

        # Commit metadata + message
        try:
            commit_meta, commit_msg = get_commit_metadata_and_message(repo_path, sha)
        except Exception:
            commit_meta = "Unknown"
            commit_msg = "Could not fetch message"

        layout = QVBoxLayout(self)

        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)

        # Top: commit header + message
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        header_text = f"Commit: <b>{sha}</b> <span style='color:gray;'>({commit_meta})</span>"
        self.msg_view = QTextEdit()
        self.msg_view.setReadOnly(True)
        self.msg_view.setPlainText(commit_msg)
        self.msg_view.setFont(QFont("Courier New", font_size))
        header = CollapsibleCommitHeader(header_text, self.msg_view)
        header.toggled.connect(self._on_commit_header_toggled)
        top_layout.addWidget(header)
        top_layout.addWidget(self.msg_view)
        self.main_splitter.addWidget(top_widget)

        # Bottom: Plain Diff + File-wise Diff tabs
        self.tab_widget = QTabWidget()

        plain_widget = QWidget()
        plain_layout = QVBoxLayout(plain_widget)
        plain_layout.setContentsMargins(0, 0, 0, 0)
        plain_layout.setSpacing(0)
        self.side_diff_view = DiffView()
        self.side_diff_view.setReadOnly(True)
        self.side_diff_view.setFont(QFont("Courier New", font_size))
        try:
            self.side_diff_view.setPlainText(get_commit_diff(repo_path, sha))
        except Exception as e:
            self.side_diff_view.setPlainText(f"Error loading diff: {e}")
        self.plain_highlighter = DiffHighlighter(
            self.side_diff_view.document(),
            added_color=colors["added"],
            removed_color=colors["removed"],
            header_color=colors["header"]
        )
        self.side_diff_view.set_separator_color(colors.get("separator", "#444444"))
        self.plain_diff_search = DiffSearchBar(target_view=self.side_diff_view, parent=plain_widget)
        plain_layout.addWidget(self.plain_diff_search)
        plain_layout.addWidget(self.side_diff_view)
        self.tab_widget.addTab(plain_widget, "Plain Diff")

        filewise_widget = QWidget()
        filewise_layout = QVBoxLayout(filewise_widget)
        filewise_layout.setContentsMargins(0, 0, 0, 0)
        filewise_layout.setSpacing(0)

        self.filewise_splitter = QSplitter(Qt.Vertical)

        self.filewise_file_list = QListWidget()
        self.filewise_file_list.setMinimumHeight(60)
        self.filewise_file_list.setFont(QFont("Courier New", font_size))
        stats_delegate = StatsItemDelegate(
            added_color=colors.get("added", "#22863a"),
            removed_color=colors.get("removed", "#cb2431"),
            parent=self.filewise_file_list
        )
        self.filewise_file_list.setItemDelegate(stats_delegate)
        self.filewise_file_list.itemChanged.connect(self._on_filewise_item_changed)
        self.filewise_file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.filewise_file_list.customContextMenuRequested.connect(self.show_filewise_context_menu)
        self.filewise_splitter.addWidget(self.filewise_file_list)

        file_right_widget = QWidget()
        file_right_layout = QVBoxLayout(file_right_widget)
        file_right_layout.setContentsMargins(0, 0, 0, 0)
        file_right_layout.setSpacing(0)

        self.filewise_diff_view = DiffView()
        self.filewise_diff_view.setReadOnly(True)
        self.filewise_diff_view.setMinimumHeight(100)
        self.filewise_diff_view.setFont(QFont("Courier New", font_size))
        self.filewise_diff_view.setPlaceholderText("Select a file above to view its diff...")
        self.filewise_highlighter = DiffHighlighter(
            self.filewise_diff_view.document(),
            added_color=colors["added"],
            removed_color=colors["removed"],
            header_color=colors["header"]
        )
        self.filewise_diff_search = DiffSearchBar(target_view=self.filewise_diff_view, parent=file_right_widget)
        file_right_layout.addWidget(self.filewise_diff_search)
        file_right_layout.addWidget(self.filewise_diff_view)

        self.filewise_splitter.addWidget(file_right_widget)
        self.filewise_splitter.setSizes([150, 350])
        filewise_layout.addWidget(self.filewise_splitter)

        self.tab_widget.addTab(filewise_widget, "\u25BC Filewise Diff")
        self._filewise_tab_idx = self.tab_widget.indexOf(filewise_widget)

        # Tab 2: Tree-wise Diff
        treewise_widget = QWidget()
        treewise_layout = QVBoxLayout(treewise_widget)
        treewise_layout.setContentsMargins(0, 0, 0, 0)
        treewise_layout.setSpacing(0)

        self.treewise_splitter = QSplitter(Qt.Vertical)

        self.treewise_tree = QTreeWidget()
        self.treewise_tree.setHeaderLabels(["Name", "Stats"])
        self.treewise_tree.setColumnCount(2)
        self.treewise_tree.header().setDefaultAlignment(Qt.AlignRight)
        self.treewise_tree.header().setStretchLastSection(False)
        self.treewise_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.treewise_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.treewise_tree.setMinimumHeight(60)
        self.treewise_tree.setFont(QFont("Courier New", font_size))
        self.treewise_tree.setAnimated(True)
        self.treewise_tree.setItemDelegateForColumn(1, TreeStatsDelegate())
        self.treewise_tree.itemChanged.connect(self._on_treewise_item_changed)
        self.treewise_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.treewise_tree.customContextMenuRequested.connect(self.show_treewise_context_menu)
        self.treewise_splitter.addWidget(self.treewise_tree)

        treewise_right_widget = QWidget()
        treewise_right_layout = QVBoxLayout(treewise_right_widget)
        treewise_right_layout.setContentsMargins(0, 0, 0, 0)
        treewise_right_layout.setSpacing(0)

        self.treewise_diff_view = DiffView()
        self.treewise_diff_view.setReadOnly(True)
        self.treewise_diff_view.setMinimumHeight(100)
        self.treewise_diff_view.setFont(QFont("Courier New", font_size))
        self.treewise_diff_view.setPlaceholderText("Select a file or folder above to view its diff...")
        self.treewise_highlighter = DiffHighlighter(
            self.treewise_diff_view.document(),
            added_color=colors["added"],
            removed_color=colors["removed"],
            header_color=colors["header"]
        )
        self.treewise_diff_search = DiffSearchBar(target_view=self.treewise_diff_view, parent=treewise_right_widget)
        treewise_right_layout.addWidget(self.treewise_diff_search)
        treewise_right_layout.addWidget(self.treewise_diff_view)

        self.treewise_splitter.addWidget(treewise_right_widget)
        self.treewise_splitter.setSizes([150, 350])
        treewise_layout.addWidget(self.treewise_splitter)

        self.tab_widget.addTab(treewise_widget, "\u25BC Tree-wise Diff")
        self._treewise_tab_idx = self.tab_widget.indexOf(treewise_widget)

        self.main_splitter.addWidget(self.tab_widget)
        self.main_splitter.setSizes([150, 450])
        layout.addWidget(self.main_splitter)

        # Populate the file list (block signals to avoid premature load)
        self._files = []
        try:
            self._files = get_commit_files_with_status(repo_path, sha)
        except Exception:
            self._files = []
        self._file_stats = {}
        try:
            self._file_stats = get_commit_file_stats(repo_path, sha)
        except Exception:
            self._file_stats = {}
        self.filewise_file_list.blockSignals(True)
        for entry in self._files:
            status, path1, path2 = entry
            if status == 'R':
                display = f"{path1} => {path2}"
            else:
                display = path1
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, self._file_stats.get(path1))
            item.setData(FILE_ENTRY_ROLE, entry)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.filewise_file_list.addItem(item)
        self.filewise_file_list.blockSignals(False)

        # Populate tree-wise tab
        self._populate_treewise_tree(self._files, self._file_stats)

        # Ctrl+F focuses the search bar of the active tab
        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self._focus_active_search)

        # Refresh diff when switching tabs
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.tabBar().tabBarClicked.connect(self._on_tab_bar_clicked)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("Close")
        ok_btn.setMinimumWidth(100)
        ok_btn.setProperty("class", "dialog-btn")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _focus_active_search(self):
        idx = self.tab_widget.currentIndex()
        if idx == 0:
            self.plain_diff_search.show_and_focus()
        elif idx == 1:
            self.filewise_diff_search.show_and_focus()
        elif idx == 2:
            self.treewise_diff_search.show_and_focus()

    def _on_commit_header_toggled(self, expanded):
        splitter = self.main_splitter
        handle = splitter.handle(1)
        if expanded:
            if hasattr(self, '_splitter_filter'):
                handle.removeEventFilter(self._splitter_filter)
                self._splitter_filter = None
            splitter.setCollapsible(0, False)
            splitter.setSizes([150, 450])
        else:
            splitter.setCollapsible(0, True)
            header_height = splitter.widget(0).sizeHint().height()
            splitter.setSizes([header_height, 1000])
            self._splitter_filter = CollapsibleSplitterFilter(splitter)
            handle.installEventFilter(self._splitter_filter)

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

    def _toggle_filewise_file_list(self):
        visible = self.filewise_file_list.isVisible()
        self.filewise_file_list.setVisible(not visible)
        arrow = "\u25B6" if visible else "\u25BC"
        self.tab_widget.setTabText(self._filewise_tab_idx,
                                   f"{arrow} Filewise Diff")
        if visible:
            self.filewise_splitter.setSizes([0, 1000])
        else:
            self.filewise_splitter.setSizes([150, 350])

    def _toggle_treewise_file_list(self):
        visible = self.treewise_tree.isVisible()
        self.treewise_tree.setVisible(not visible)
        arrow = "\u25B6" if visible else "\u25BC"
        self.tab_widget.setTabText(self._treewise_tab_idx,
                                   f"{arrow} Tree-wise Diff")
        if visible:
            self.treewise_splitter.setSizes([0, 1000])
        else:
            self.treewise_splitter.setSizes([150, 350])

    def _get_file_diff(self, filepath):
        """Get diff for a single file in this commit."""
        try:
            item = None
            for i in range(self.filewise_file_list.count()):
                li = self.filewise_file_list.item(i)
                li_entry = li.data(FILE_ENTRY_ROLE)
                if li_entry:
                    li_path = li_entry[2] if li_entry[0] == 'R' else li_entry[1]
                    if li_path == filepath:
                        item = li
                        break
                elif li.text() == filepath:
                    item = li
                    break
            entry = item.data(FILE_ENTRY_ROLE) if item else None
            if entry and entry[0] == 'R':
                return get_rename_diff_in_commit(self.repo_path, self.sha, entry[1], entry[2])
            elif entry:
                return get_file_diff_only_in_commit(self.repo_path, self.sha, entry[1])
            else:
                return get_file_diff_only_in_commit(self.repo_path, self.sha, filepath)
        except Exception as e:
            return f"Error loading diff: {e}"

    def _on_filewise_item_changed(self, item):
        """Handle checkbox change in filewise list: sync to tree and refresh diff."""
        checked = item.checkState() == Qt.Checked
        entry = item.data(FILE_ENTRY_ROLE)
        if entry:
            filepath = entry[2] if entry[0] == 'R' else entry[1]
        else:
            filepath = item.text()
        for i in range(self.treewise_tree.topLevelItemCount()):
            self._sync_file_to_tree(self.treewise_tree.topLevelItem(i), filepath, checked)
        self._refresh_filewise_diff()
        self._refresh_treewise_diff()

    def _sync_file_to_tree(self, parent_item, filepath, checked):
        """Recursively find and sync a file's check state in the tree."""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            child_data = child.data(0, Qt.UserRole + 10)
            if not child_data:
                continue
            if child_data["type"] == "folder":
                self._sync_file_to_tree(child, filepath, checked)
            elif child_data.get("entry"):
                entry = child_data["entry"]
                child_path = entry[2] if entry[0] == 'R' else entry[1]
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
        item_data = item.data(0, Qt.UserRole + 10)
        if not item_data:
            return
        checked = item.checkState(0) == Qt.Checked
        if item_data["type"] == "folder":
            self._set_tree_children_checked(item, checked)
            self._sync_tree_checked_to_file_list()
            p = item.parent()
            while p:
                self._update_folder_check_state(p)
                p = p.parent()
        else:
            entry = item_data.get("entry")
            if entry:
                filepath = entry[2] if entry[0] == 'R' else entry[1]
                for i in range(self.filewise_file_list.count()):
                    list_item = self.filewise_file_list.item(i)
                    list_entry = list_item.data(FILE_ENTRY_ROLE)
                    if list_entry and list_entry == entry:
                        self.filewise_file_list.blockSignals(True)
                        list_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                        self.filewise_file_list.blockSignals(False)
                        break
            p = item.parent()
            while p:
                self._update_folder_check_state(p)
                p = p.parent()
        self._refresh_treewise_diff()
        self._refresh_filewise_diff()

    def _set_tree_children_checked(self, item, checked):
        """Recursively set check state for all children."""
        self.treewise_tree.blockSignals(True)
        self._set_tree_children_checked_impl(item, checked)
        self.treewise_tree.blockSignals(False)

    def _set_tree_children_checked_impl(self, item, checked):
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
            child_data = child.data(0, Qt.UserRole + 10)
            if child_data and child_data["type"] == "folder":
                self._set_tree_children_checked_impl(child, checked)

    def _sync_tree_checked_to_file_list(self):
        self.filewise_file_list.blockSignals(True)

        def sync_item(parent_item):
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                child_data = child.data(0, Qt.UserRole + 10)
                if not child_data:
                    continue
                if child_data["type"] == "folder":
                    sync_item(child)
                else:
                    entry = child_data.get("entry")
                    if not entry:
                        continue
                    for j in range(self.filewise_file_list.count()):
                        li = self.filewise_file_list.item(j)
                        li_entry = li.data(FILE_ENTRY_ROLE)
                        if li_entry and li_entry == entry:
                            li.setCheckState(Qt.Checked if child.checkState(0) == Qt.Checked else Qt.Unchecked)
                            break

        sync_item(self.treewise_tree.invisibleRootItem())
        self.filewise_file_list.blockSignals(False)

    def _update_folder_check_state(self, folder_item):
        """Update folder checkbox based on children check states."""
        if folder_item.childCount() == 0:
            return
        all_checked = True
        has_checked = False
        for i in range(folder_item.childCount()):
            child = folder_item.child(i)
            child_data = child.data(0, Qt.UserRole + 10)
            if child_data and child_data["type"] == "folder":
                self._update_folder_check_state(child)
                if child.checkState(0) == Qt.Checked:
                    has_checked = True
                else:
                    all_checked = False
            else:
                if child.checkState(0) == Qt.Checked:
                    has_checked = True
                else:
                    all_checked = False
        self.treewise_tree.blockSignals(True)
        if all_checked:
            folder_item.setCheckState(0, Qt.Checked)
        elif has_checked:
            folder_item.setCheckState(0, Qt.PartiallyChecked)
        else:
            folder_item.setCheckState(0, Qt.Unchecked)
        self.treewise_tree.blockSignals(False)

    def _checked_filewise_files(self):
        """Return list of checked file paths in the filewise list."""
        result = []
        for i in range(self.filewise_file_list.count()):
            item = self.filewise_file_list.item(i)
            if item.checkState() == Qt.Checked:
                entry = item.data(FILE_ENTRY_ROLE)
                if entry:
                    result.append(entry[2] if entry[0] == 'R' else entry[1])
                else:
                    result.append(item.text())
        return result

    def _refresh_filewise_diff(self):
        """Show combined diff of all checked files in the filewise diff pane."""
        checked = self._checked_filewise_files()
        if not checked:
            self.filewise_diff_view.clear()
            return
        try:
            parts = []
            for f in checked:
                d = self._get_file_diff(f).rstrip("\n")
                if d:
                    parts.append(d)
            text = "\n\n".join(parts) + ("\n" if parts else "")
            self.filewise_diff_view.setPlainText(text)
            self.filewise_diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.filewise_diff_search._perform_search()
        except Exception as e:
            self.filewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def _refresh_treewise_diff(self):
        """Show combined diff of all checked tree items."""
        checked = self._checked_treewise_files()
        if not checked:
            self.treewise_diff_view.clear()
            return
        try:
            parts = []
            for f in checked:
                d = self._get_file_diff(f).rstrip("\n")
                if d:
                    parts.append(d)
            text = "\n\n".join(parts) + ("\n" if parts else "")
            self.treewise_diff_view.setPlainText(text)
            self.treewise_diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.treewise_diff_search._perform_search()
        except Exception as e:
            self.treewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def _checked_treewise_files(self):
        """Return list of checked file paths from the tree widget."""
        files = []
        self._collect_checked_tree_files(self.treewise_tree.invisibleRootItem(), files)
        return files

    def _collect_checked_tree_files(self, parent_item, files):
        """Recursively collect checked file paths from tree."""
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            if item.checkState(0) == Qt.Unchecked:
                continue
            item_data = item.data(0, Qt.UserRole + 10)
            if not item_data:
                continue
            if item_data["type"] == "folder":
                self._collect_checked_tree_files(item, files)
            else:
                entry = item_data.get("entry")
                if entry:
                    filepath = entry[2] if entry[0] == 'R' else entry[1]
                    if filepath and filepath not in files:
                        files.append(filepath)

    def _populate_treewise_tree(self, file_entries, file_stats):
        """Build and display the tree-wise file tree from commit file entries."""
        self.treewise_tree.blockSignals(True)
        self.treewise_tree.clear()
        if not file_entries:
            self.treewise_tree.blockSignals(False)
            return
        tree = build_file_tree(file_entries, file_stats)
        self._add_tree_children(None, tree["children"])
        self.treewise_tree.blockSignals(False)
        for i in range(self.treewise_tree.topLevelItemCount()):
            self.treewise_tree.topLevelItem(i).setExpanded(True)

    def _add_tree_children(self, parent_item, children_dict):
        """Recursively add folder/file nodes to the QTreeWidget."""
        from lib.git_helpers.commits import format_tree_node_stats
        folders = sorted(((k, v) for k, v in children_dict.items() if v["children"]),
                         key=lambda x: x[0].lower())
        files = sorted(((k, v) for k, v in children_dict.items() if not v["children"]),
                       key=lambda x: x[0].lower())
        for name, node in folders + files:
            item = QTreeWidgetItem()
            if node["children"]:
                item.setText(0, f"\U0001f4c1 {name}")
                item.setData(0, Qt.UserRole + 10, {"type": "folder", "node": node})
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Unchecked)
                stats_text = format_tree_node_stats(node)
                if stats_text:
                    item.setText(1, stats_text)
                    item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
                if parent_item:
                    parent_item.addChild(item)
                else:
                    self.treewise_tree.addTopLevelItem(item)
                self._add_tree_children(item, node["children"])
            else:
                entry = node["entries"][0] if node["entries"] else None
                status = entry[0] if entry else ''
                if status == 'R':
                    display = f"{entry[1]} => {entry[2]}"
                elif status == 'D':
                    display = f"{name} (Deleted)"
                elif status == 'A':
                    display = f"{name} (Added new file)"
                else:
                    display = name
                item.setText(0, display)
                item.setData(0, Qt.UserRole + 10, {"type": "file", "entry": entry})
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Unchecked)
                stats_text = format_tree_node_stats(node)
                if stats_text:
                    item.setText(1, stats_text)
                    item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
                if parent_item:
                    parent_item.addChild(item)
                else:
                    self.treewise_tree.addTopLevelItem(item)

    def _collect_folder_diffs(self, node, diffs):
        """Recursively collect diffs for all leaf files under a folder node."""
        for child in node["children"].values():
            if child["children"]:
                self._collect_folder_diffs(child, diffs)
            else:
                for entry in child["entries"]:
                    try:
                        if entry[0] == 'R':
                            diffs.append(get_rename_diff_in_commit(self.repo_path, self.sha, entry[1], entry[2]))
                        else:
                            diffs.append(get_file_diff_only_in_commit(self.repo_path, self.sha, entry[1]))
                    except Exception:
                        pass

    def show_treewise_context_menu(self, pos):
        """Context menu for tree-wise file items — mirrors the file-wise context menu."""
        item = self.treewise_tree.itemAt(pos)
        if not item:
            return
        item_data = item.data(0, Qt.UserRole + 10)
        if not item_data or item_data["type"] != "file":
            return
        entry = item_data.get("entry")
        target_path = entry[2] if entry and entry[0] == 'R' else (entry[1] if entry else "")
        if not target_path:
            return

        menu = QMenu(self)
        head = _get_head_sha(self.repo_path)
        add_open_with_system_default_action(menu, target_path, self, sha=self.sha,
            is_head=self.sha == head or head.startswith(self.sha))
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=target_path: open_blame_window(self, text, branch=self.sha))
        menu.addAction(blame_action)

        diff_ref_action = QAction("Diff against a different version of this file", self)
        diff_ref_action.triggered.connect(lambda checked=False, text=target_path: self.handle_diff_file_at_ref(text, self.sha))
        menu.addAction(diff_ref_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=target_path: self.copy_filename_to_clipboard(target_path))
        menu.addAction(copy_action)

        if self.editable and is_editable_branch(self):
            is_only_file = self.filewise_file_list.count() <= 1

            move_action = QAction("Move file changes out of this commit", self)
            move_action.triggered.connect(lambda checked=False, text=target_path: self.move_file_out(text))
            move_action.setEnabled(not is_only_file)
            menu.addAction(move_action)

            drop_action = QAction("Drop file changes from this commit", self)
            drop_action.triggered.connect(lambda checked=False, text=target_path: self.drop_file(text))
            drop_action.setEnabled(not is_only_file)
            menu.addAction(drop_action)

            remove_onwards_action = QAction("Remove file from this commit onwards", self)
            remove_onwards_action.triggered.connect(lambda checked=False, text=target_path: self.remove_file_onwards(text))
            menu.addAction(remove_onwards_action)

            menu.addSeparator()
            refine_action = QAction("Refine/Edit changes in selected file", self)
            refine_action.triggered.connect(lambda checked=False, text=target_path: self.refine_file(text))
            menu.addAction(refine_action)

        menu.addSeparator()
        browse_log_action = QAction("Browse file log", self)
        browse_log_action.setToolTip("Open a read-only viewer of this file's history.")
        browse_log_action.triggered.connect(lambda checked=False, text=target_path: self.browse_file_log(text))
        menu.addAction(browse_log_action)
        menu.exec(self.treewise_tree.mapToGlobal(pos))

    def show_filewise_context_menu(self, pos):
        """Context menu for the file list. If the viewed commit is known to be in
        the current branch's list (editable=True, opened from a list item), the
        full edit options are offered. Otherwise the commit may be an arbitrary
        SHA outside the branch, so only safe actions (copy, browse log) appear."""
        item = self.filewise_file_list.itemAt(pos)
        if not item:
            return
        entry = item.data(FILE_ENTRY_ROLE)
        target_path = entry[2] if entry and entry[0] == 'R' else (entry[1] if entry else item.text())
        menu = QMenu(self)
        head = _get_head_sha(self.repo_path)
        add_open_with_system_default_action(menu, target_path, self, sha=self.sha,
            is_head=self.sha == head or head.startswith(self.sha))
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=target_path: open_blame_window(self, text, branch=self.sha))
        menu.addAction(blame_action)

        diff_ref_action = QAction("Diff against a different version of this file", self)
        diff_ref_action.triggered.connect(lambda checked=False, text=target_path: self.handle_diff_file_at_ref(text, self.sha))
        menu.addAction(diff_ref_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=target_path: self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)

        if self.editable and is_editable_branch(self):
            is_only_file = self.filewise_file_list.count() <= 1

            move_action = QAction("Move file changes out of this commit", self)
            move_action.triggered.connect(lambda checked=False, text=target_path: self.move_file_out(text))
            move_action.setEnabled(not is_only_file)
            menu.addAction(move_action)

            drop_action = QAction("Drop file changes from this commit", self)
            drop_action.triggered.connect(lambda checked=False, text=target_path: self.drop_file(text))
            drop_action.setEnabled(not is_only_file)
            menu.addAction(drop_action)

            remove_onwards_action = QAction("Remove file from this commit onwards", self)
            remove_onwards_action.triggered.connect(lambda checked=False, text=target_path: self.remove_file_onwards(text))
            menu.addAction(remove_onwards_action)

            menu.addSeparator()
            refine_action = QAction("Refine/Edit changes in selected file", self)
            refine_action.triggered.connect(lambda checked=False, text=target_path: self.refine_file(text))
            menu.addAction(refine_action)

        menu.addSeparator()
        browse_log_action = QAction("Browse file log", self)
        browse_log_action.setToolTip("Open a read-only viewer of this file's history.")
        browse_log_action.triggered.connect(lambda checked=False, text=target_path: self.browse_file_log(text))
        menu.addAction(browse_log_action)
        menu.exec(self.filewise_file_list.mapToGlobal(pos))

    def move_file_out(self, filepath):
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        if main_win and hasattr(main_win, 'perform_move_file_out'):
            self.accept()
            QTimer.singleShot(0, lambda: main_win.perform_move_file_out(self.sha, filepath))

    def drop_file(self, filepath):
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        if main_win and hasattr(main_win, 'perform_drop_file_from_commit'):
            self.accept()
            QTimer.singleShot(0, lambda: main_win.perform_drop_file_from_commit(self.sha, filepath))

    def remove_file_onwards(self, filepath):
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        if main_win and hasattr(main_win, 'perform_remove_file_from_commit_onwards'):
            self.accept()
            QTimer.singleShot(0, lambda: main_win.perform_remove_file_from_commit_onwards(self.sha, filepath))

    def refine_file(self, filepath):
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        if main_win and hasattr(main_win, 'perform_refine_changes'):
            self.accept()
            QTimer.singleShot(0, lambda: main_win.perform_refine_changes(self.sha, filepath))

    def browse_file_log(self, filepath):
        main_win = _find_main_window(self)
        if main_win and hasattr(main_win, 'open_file_log_for'):
            main_win.open_file_log_for(filepath)

    def copy_filename_to_clipboard(self, filename):
        QApplication.clipboard().setText(filename)
        QMessageBox.information(self, "Copied", f"Copied '{filename}' to clipboard.")

    def handle_diff_file_at_ref(self, filepath, current_sha):
        from lib.dialogs.history_branch_dialogs import DiffFileAtRefDialog
        from lib.git_helpers import run_configured_difftool, run_difftool_direct
        head_sha = _get_head_sha(self.repo_path)
        dialog = DiffFileAtRefDialog(self.repo_path, filepath, current_sha, head_sha, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        ref_sha = dialog.resolved_sha
        target_file = dialog.selected_file
        if not ref_sha or not target_file:
            return
        source_sha = head_sha if dialog.src_head_radio.isChecked() else current_sha
        is_head_source = dialog.src_head_radio.isChecked() or source_sha == head_sha
        if dialog.use_direct:
            print(f"[diff] Running direct: {source_sha[:8]} {ref_sha[:8]} -- {target_file} (head_src={is_head_source})")
            ok, err = run_difftool_direct(self.repo_path, source_sha, target_file, ref_sha, target_file,
                                          source_is_head=is_head_source)
        else:
            print(f"[diff] Running configured: difftool {source_sha[:8]} {ref_sha[:8]} -- {target_file}")
            ok, err = run_configured_difftool(self.repo_path, source_sha, target_file, ref_sha, target_file)
        if not ok:
            QMessageBox.critical(self, "Difftool Failed", f"Could not run difftool: {err}")


class UnstagedDiffDialog(BranchDiffDialog):
    """Read-only window identical to the PR diff viewer (View PR Diff), but
    showing only the unstaged (worktree vs index) changes. No edits allowed."""
    def __init__(self, repo_path, files, diff_text, file_stats, branch, head_sha, font_size=10, parent=None, colors=None):
        if colors is None:
            main_win = parent if isinstance(parent, QMainWindow) else None
            if main_win and hasattr(main_win, 'current_theme_colors'):
                colors = main_win.current_theme_colors
            else:
                theme_name = QSettings("git-interactive-rebase-gui-tool", "settings").value("theme", "light", type=str)
                colors = get_theme_colors(theme_name)

        super().__init__(
            repo_path, branch, head_sha, len(files), diff_text,
            files, file_stats, font_size, parent, colors=colors
        )
        self.setWindowTitle("Unstaged Changes")
        self.header_label.setText(
            f"Unstaged Changes: <b>{branch}</b> - {len(files)} file{'s' if len(files) != 1 else ''}"
        )

    def _get_file_diff(self, filepath):
        return get_unstaged_file_diff(self.repo_path, filepath)

    def on_filewise_file_selected(self, filepath):
        if not filepath:
            self.filewise_diff_view.clear()
            return
        try:
            diff = get_unstaged_file_diff(self.repo_path, filepath)
            self.filewise_diff_view.setPlainText(diff)
            self.filewise_diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.filewise_diff_search._perform_search()
        except Exception as e:
            self.filewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def on_treewise_item_clicked(self, item, column):
        """Handle click on tree-wise item for unstaged changes."""
        item_data = item.data(0, Qt.UserRole + 10)
        if not item_data:
            return
        try:
            if item_data["type"] == "file":
                filepath = item_data.get("filepath", "")
                if filepath:
                    diff = get_unstaged_file_diff(self.repo_path, filepath)
                    self.treewise_diff_view.setPlainText(diff)
            else:
                diffs = []
                self._collect_folder_diffs_unstaged(item_data["node"], diffs)
                self.treewise_diff_view.setPlainText("\n".join(diffs))
            self.treewise_diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.treewise_diff_search._perform_search()
        except Exception as e:
            self.treewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def _collect_folder_diffs_unstaged(self, node, diffs):
        """Recursively collect unstaged diffs for all leaf files under a folder node."""
        for child in node["children"].values():
            if child["children"]:
                self._collect_folder_diffs_unstaged(child, diffs)
            else:
                for entry in child["entries"]:
                    try:
                        filepath = entry[1] if entry else ""
                        if filepath:
                            diff = get_unstaged_file_diff(self.repo_path, filepath)
                            diffs.append(diff)
                    except Exception:
                        pass


class StagedDiffDialog(BranchDiffDialog):
    """Read-only window showing staged (index vs HEAD) changes with 3 tabs:
    Plain Diff, File-wise Diff, Tree-wise Diff."""
    def __init__(self, repo_path, files, diff_text, file_stats, branch, head_sha, font_size=10, parent=None, colors=None):
        if colors is None:
            main_win = parent if isinstance(parent, QMainWindow) else None
            if main_win and hasattr(main_win, 'current_theme_colors'):
                colors = main_win.current_theme_colors
            else:
                theme_name = QSettings("git-interactive-rebase-gui-tool", "settings").value("theme", "light", type=str)
                colors = get_theme_colors(theme_name)

        super().__init__(
            repo_path, branch, head_sha, len(files), diff_text,
            files, file_stats, font_size, parent, colors=colors
        )
        self.setWindowTitle("Staged Changes")
        self.header_label.setText(
            f"Staged Changes: <b>{branch}</b> - {len(files)} file{'s' if len(files) != 1 else ''}"
        )

    def _get_file_diff(self, filepath):
        return get_staged_file_diff(self.repo_path, filepath)

    def on_filewise_file_selected(self, filepath):
        if not filepath:
            self.filewise_diff_view.clear()
            return
        try:
            diff = get_staged_file_diff(self.repo_path, filepath)
            self.filewise_diff_view.setPlainText(diff)
            self.filewise_diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.filewise_diff_search._perform_search()
        except Exception as e:
            self.filewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def on_treewise_item_clicked(self, item, column):
        """Handle click on tree-wise item for staged changes."""
        item_data = item.data(0, Qt.UserRole + 10)
        if not item_data:
            return
        try:
            if item_data["type"] == "file":
                filepath = item_data.get("filepath", "")
                if filepath:
                    diff = get_staged_file_diff(self.repo_path, filepath)
                    self.treewise_diff_view.setPlainText(diff)
            else:
                diffs = []
                self._collect_folder_diffs_staged(item_data["node"], diffs)
                self.treewise_diff_view.setPlainText("\n".join(diffs))
            self.treewise_diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.treewise_diff_search._perform_search()
        except Exception as e:
            self.treewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def _collect_folder_diffs_staged(self, node, diffs):
        """Recursively collect staged diffs for all leaf files under a folder node."""
        for child in node["children"].values():
            if child["children"]:
                self._collect_folder_diffs_staged(child, diffs)
            else:
                for entry in child["entries"]:
                    try:
                        filepath = entry[1] if entry else ""
                        if filepath:
                            diff = get_staged_file_diff(self.repo_path, filepath)
                            diffs.append(diff)
                    except Exception:
                        pass


class FileWiseViewDialog(QDialog):
    """Dialog for viewing changes in a commit file by file."""
    def __init__(self, repo_path, sha, files, font_size=10, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.sha = sha
        self.font_size = font_size
        self.setWindowTitle(f"View Commit File-wise: {sha}")
        self.setMinimumSize(860, 620)

        main_win = parent if isinstance(parent, QMainWindow) else None
        if main_win and hasattr(main_win, 'current_theme_colors'):
            colors = main_win.current_theme_colors
        else:
            colors = {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef", "separator": "#444444"}
        self.colors = colors

        # Fetch per-file edit stats for display
        try:
            self.file_stats = get_commit_file_stats(repo_path, sha)
        except:
            self.file_stats = {}

        # Fetch commit details
        try:
            meta, msg = get_commit_metadata_and_message(repo_path, sha)
        except:
            meta = "Unknown"
            msg = "Could not fetch message"

        layout = QVBoxLayout(self)

        # Main Vertical Splitter
        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)

        # Row 1: Commit Message (Resizable)
        msg_widget = QWidget()
        msg_layout = QVBoxLayout(msg_widget)
        msg_layout.setContentsMargins(0, 0, 0, 0)

        msg_header = QLabel(f"Commit: <b>{sha}</b> <span style='color:gray;'>({meta})</span>")
        msg_header.setTextFormat(Qt.RichText)
        msg_layout.addWidget(msg_header)

        self.msg_view = QTextEdit()
        self.msg_view.setReadOnly(True)
        self.msg_view.setPlainText(msg)
        self.msg_view.setFont(QFont("Courier New", font_size))
        msg_layout.addWidget(self.msg_view)

        self.main_splitter.addWidget(msg_widget)

        # Row 2: File List
        file_widget = QWidget()
        file_layout = QVBoxLayout(file_widget)
        file_layout.setContentsMargins(0, 5, 0, 0)
        file_layout.addWidget(QLabel("<b>Select a file</b> to view its changes:"))

        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(60)
        self.file_list.setFont(QFont("Courier New", font_size))
        for entry in files:
            status, path1, path2 = entry
            if status == 'R':
                display = f"{path1} => {path2}"
            else:
                display = path1
            item = QListWidgetItem(display)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, self.file_stats.get(display))
            item.setData(FILE_ENTRY_ROLE, entry)
            self.file_list.addItem(item)
        stats_delegate = StatsItemDelegate(
            added_color=colors.get("added", "#22863a"),
            removed_color=colors.get("removed", "#cb2431"),
            parent=self.file_list
        )
        self.file_list.setItemDelegate(stats_delegate)
        self.file_list.itemChanged.connect(self._on_file_item_changed)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self.show_file_context_menu)
        file_layout.addWidget(self.file_list)

        self.main_splitter.addWidget(file_widget)

        # Row 3: Diff View
        diff_widget = QWidget()
        diff_layout = QVBoxLayout(diff_widget)
        diff_layout.setContentsMargins(0, 5, 0, 0)
        diff_layout.addWidget(QLabel("<b>File Diff:</b>"))

        self.diff_view = DiffView()
        self.diff_view.setMinimumHeight(100)
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(QFont("Courier New", font_size))
        self.diff_view.setPlaceholderText("Select a file above to view its diff...")
        self.highlighter = DiffHighlighter(
            self.diff_view.document(),
            added_color=colors["added"],
            removed_color=colors["removed"],
            header_color=colors["header"]
        )

        self.search_bar = DiffSearchBar(target_view=self.diff_view, parent=diff_widget)
        diff_layout.addWidget(self.search_bar)
        diff_layout.addWidget(self.diff_view)

        # Connect Ctrl+F explicitly
        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self.search_bar.show_and_focus)

        self.main_splitter.addWidget(diff_widget)

        # Initial sizes for [Message, File List, Diff View]
        self.main_splitter.setSizes([100, 150, 350])
        layout.addWidget(self.main_splitter)

        # Buttons
        btn_layout = QHBoxLayout()
        self.counter_label = QLabel()
        self.counter_label.setTextFormat(Qt.RichText)
        btn_layout.addWidget(self.counter_label)
        btn_layout.addStretch()
        select_all_btn = QPushButton("Select All")
        select_all_btn.setProperty("class", "dialog-btn")
        select_all_btn.clicked.connect(lambda: self._set_all(True))
        btn_layout.addWidget(select_all_btn)
        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.setProperty("class", "dialog-btn-secondary")
        deselect_all_btn.clicked.connect(lambda: self._set_all(False))
        btn_layout.addWidget(deselect_all_btn)
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
        item = self.file_list.itemAt(pos)
        if not item:
            return
        entry = item.data(FILE_ENTRY_ROLE)
        target_path = entry[2] if entry and entry[0] == 'R' else (entry[1] if entry else item.text())
        menu = QMenu(self)
        head = _get_head_sha(self.repo_path)
        add_open_with_system_default_action(menu, target_path, self, sha=self.sha,
            is_head=self.sha == head or head.startswith(self.sha))
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=target_path: open_blame_window(self, text, branch=self.sha))
        menu.addAction(blame_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=target_path: self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)

        is_only_file = self.file_list.count() <= 1

        move_action = QAction("Move file changes out of this commit", self)
        move_action.triggered.connect(lambda checked=False, text=target_path: self.move_file_out(text))
        move_action.setEnabled(not is_only_file)
        menu.addAction(move_action)

        drop_action = QAction("Drop file changes from this commit", self)
        drop_action.triggered.connect(lambda checked=False, text=target_path: self.drop_file(text))
        drop_action.setEnabled(not is_only_file)
        menu.addAction(drop_action)

        remove_onwards_action = QAction("Remove file from this commit onwards", self)
        remove_onwards_action.triggered.connect(lambda checked=False, text=target_path: self.remove_file_onwards(text))
        menu.addAction(remove_onwards_action)

        menu.addSeparator()
        refine_action = QAction("Refine/Edit changes in selected file", self)
        refine_action.triggered.connect(lambda checked=False, text=target_path: self.refine_file(text))
        menu.addAction(refine_action)

        menu.addSeparator()
        browse_log_action = QAction("Browse file log", self)
        browse_log_action.setToolTip("Open a read-only viewer of this file's history.")
        browse_log_action.triggered.connect(lambda checked=False, text=target_path: self.browse_file_log(text))
        menu.addAction(browse_log_action)

        menu.exec(self.file_list.mapToGlobal(pos))

    def browse_file_log(self, filepath):
        main_win = _find_main_window(self)
        if main_win and hasattr(main_win, 'open_file_log_for'):
            main_win.open_file_log_for(filepath)

    def move_file_out(self, filepath):
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        if main_win and hasattr(main_win, 'perform_move_file_out'):
            self.accept()
            QTimer.singleShot(0, lambda: main_win.perform_move_file_out(self.sha, filepath))

    def drop_file(self, filepath):
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        if main_win and hasattr(main_win, 'perform_drop_file_from_commit'):
            self.accept()
            QTimer.singleShot(0, lambda: main_win.perform_drop_file_from_commit(self.sha, filepath))

    def remove_file_onwards(self, filepath):
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        if main_win and hasattr(main_win, 'perform_remove_file_from_commit_onwards'):
            self.accept()
            QTimer.singleShot(0, lambda: main_win.perform_remove_file_from_commit_onwards(self.sha, filepath))

    def refine_file(self, filepath):
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        if main_win and hasattr(main_win, 'perform_refine_changes'):
            self.accept()
            QTimer.singleShot(0, lambda: main_win.perform_refine_changes(self.sha, filepath))

    def copy_filename_to_clipboard(self, filename):
        QApplication.clipboard().setText(filename)
        QMessageBox.information(self, "Copied", f"Copied '{filename}' to clipboard.")

    def on_file_selected(self, filepath):
        if not filepath:
            return
        try:
            item = self.file_list.currentItem()
            entry = item.data(FILE_ENTRY_ROLE) if item else None
            if entry and entry[0] == 'R':
                diff = get_rename_diff_in_commit(self.repo_path, self.sha, entry[1], entry[2])
            elif entry:
                diff = get_file_diff_only_in_commit(self.repo_path, self.sha, entry[1])
            else:
                diff = get_file_diff_only_in_commit(self.repo_path, self.sha, filepath)
            self.diff_view.setPlainText(diff)
            self.diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.search_bar._perform_search()
        except Exception as e:
            self.diff_view.setPlainText(f"Error loading diff: {e}")

    def _on_file_item_changed(self, item):
        """Handle checkbox change: update counter and refresh combined diff."""
        self._update_counter()
        self._refresh_diff()

    def _update_counter(self):
        checked = self._checked_files()
        total = self.file_list.count()
        self.counter_label.setText(f"<b>{len(checked)}</b> / {total} files selected")

    def _checked_files(self):
        return [self.file_list.item(i).text()
                for i in range(self.file_list.count())
                if self.file_list.item(i).checkState() == Qt.Checked]

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
            parts = []
            for display_name in checked:
                item = None
                for i in range(self.file_list.count()):
                    if self.file_list.item(i).text() == display_name:
                        item = self.file_list.item(i)
                        break
                entry = item.data(FILE_ENTRY_ROLE) if item else None
                if entry and entry[0] == 'R':
                    d = get_rename_diff_in_commit(self.repo_path, self.sha, entry[1], entry[2])
                elif entry:
                    d = get_file_diff_only_in_commit(self.repo_path, self.sha, entry[1])
                else:
                    d = get_file_diff_only_in_commit(self.repo_path, self.sha, display_name)
                d = d.rstrip("\n")
                if d:
                    parts.append(d)
            text = "\n\n".join(parts) + ("\n" if parts else "")
            self.diff_view.setPlainText(text)
            self.diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.search_bar._perform_search()
        except Exception as e:
            self.diff_view.setPlainText(f"Error loading diff: {e}")
