
# pyrefly: ignore [missing-import]
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
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
    Qt,
    QTimer,
)
# pyrefly: ignore [missing-import]
from PySide6.QtGui import (
    QAction,
    QKeySequence,
    QShortcut,
)

from lib.git_helpers import (
    build_file_tree,
    get_commit_file_stats,
    get_commit_files_with_status,
    get_commit_metadata_and_message,
    get_file_diff_only_in_commit,
    get_rename_diff_in_commit,
)
from lib.widgets import (
    FILE_ENTRY_ROLE,
    DiffHighlighter,
    DiffSearchBar,
    DiffView,
    StatsItemDelegate,
    TreeStatsDelegate,
)
from .hunk_file_dialogs import open_blame_window
from .diff_viewer_dialog import DiffViewerDialog
from lib.app_window.helpers import (
    _get_head_sha,
    add_open_with_system_default_action,
    is_editable_branch,
    mono_font,
)


class SplitCommitDialog(QDialog):
    """Dialog for moving file(s) changes out of a commit.

    Provides filewise and treewise tabs with checkboxes, diff preview,
    and bidirectional sync — mirroring the commit viewer's UX."""
    def __init__(self, repo_path, sha, files, font_size=10, font_family=None, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.sha = sha
        self.font_size = font_size
        self.font_family = font_family
        self.setWindowTitle(f"Move Files Out of Commit: {sha}")
        self.setMinimumSize(900, 680)

        # Diff colors from parent theme
        main_win = parent if isinstance(parent, QMainWindow) else None
        if main_win and hasattr(main_win, 'current_theme_colors'):
            colors = main_win.current_theme_colors
        else:
            colors = {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef", "separator": "#444444"}
        self.colors = colors

        # Fetch per-file edit stats for display
        try:
            self.file_stats = get_commit_file_stats(repo_path, sha)
        except Exception:
            self.file_stats = {}

        # Fetch commit details
        try:
            meta, msg = get_commit_metadata_and_message(repo_path, sha)
        except Exception:
            meta = "Unknown"
            msg = "Could not fetch message"

        # Fetch file entries with status (Added/Deleted/Renamed/etc.)
        self._files = []
        try:
            self._files = get_commit_files_with_status(repo_path, sha)
        except Exception:
            self._files = []

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
        self.msg_view.setFont(mono_font(font_size, family=self.font_family))
        msg_layout.addWidget(self.msg_view)

        self.main_splitter.addWidget(msg_widget)

        # Row 2: Tab Widget (Filewise + Treewise) with Diff Pane
        self.tab_widget = QTabWidget()

        # --- Tab 0: Filewise Diff ---
        filewise_widget = QWidget()
        filewise_layout = QVBoxLayout(filewise_widget)
        filewise_layout.setContentsMargins(0, 0, 0, 0)
        filewise_layout.setSpacing(0)

        self.filewise_splitter = QSplitter(Qt.Vertical)

        self.filewise_file_list = QListWidget()
        self.filewise_file_list.setMinimumHeight(60)
        self.filewise_file_list.setFont(mono_font(font_size, family=self.font_family))
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
        self.filewise_diff_view.setFont(mono_font(font_size, family=self.font_family))
        self.filewise_diff_view.setPlaceholderText("Check files above to preview the consolidated diff...")
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

        # --- Tab 1: Tree-wise Diff ---
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
        self.treewise_tree.setFont(mono_font(font_size, family=self.font_family))
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
        self.treewise_diff_view.setFont(mono_font(font_size, family=self.font_family))
        self.treewise_diff_view.setPlaceholderText("Check files or folders above to preview their diff...")
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

        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.tabBar().tabBarClicked.connect(self._on_tab_bar_clicked)

        self.main_splitter.addWidget(self.tab_widget)
        self.main_splitter.setSizes([100, 500])
        layout.addWidget(self.main_splitter, 1)

        # Buttons (always visible at bottom)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.move_btn = QPushButton("Move Out of Commit")
        self.move_btn.setMinimumWidth(160)
        self.move_btn.setEnabled(False)
        self.move_btn.setProperty("class", "dialog-btn")
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.setProperty("class", "dialog-btn-secondary")
        self.move_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.move_btn)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Ctrl+F shortcut
        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self._focus_active_search)

        # Populate the file list
        self.filewise_file_list.blockSignals(True)
        for entry in self._files:
            status, path1, path2 = entry
            if status == 'R':
                display = f"{path1} => {path2}"
            elif status == 'D':
                display = f"{path1} (Deleted)"
            elif status == 'A':
                display = f"{path1} (Added new file)"
            else:
                display = path1
            item = QListWidgetItem(display)
            item.setToolTip(path1)
            item.setData(Qt.UserRole, self.file_stats.get(path1))
            item.setData(FILE_ENTRY_ROLE, entry)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.filewise_file_list.addItem(item)
        self.filewise_file_list.blockSignals(False)

        # Populate tree-wise tab
        self._populate_treewise_tree(self._files, self.file_stats)

    def _focus_active_search(self):
        idx = self.tab_widget.currentIndex()
        if idx == self._filewise_tab_idx:
            self.filewise_diff_search.show_and_focus()
        elif idx == self._treewise_tab_idx:
            self.treewise_diff_search.show_and_focus()

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
        self._update_move_button()

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
        self._update_move_button()

    def _set_tree_children_checked(self, item, checked):
        """Recursively set check state for all children."""
        from lib.tree_utils import set_tree_children_checked
        self.treewise_tree.blockSignals(True)
        set_tree_children_checked(item, checked)
        self.treewise_tree.blockSignals(False)

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
        from lib.tree_utils import update_folder_check_state
        self.treewise_tree.blockSignals(True)
        update_folder_check_state(folder_item)
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
        from lib.git_helpers.commits import format_tree_node_stats
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

    def _update_move_button(self):
        """Enable/disable move button based on whether any files are checked."""
        self.move_btn.setEnabled(len(self._checked_filewise_files()) > 0)

    def _toggle_filewise_file_list(self):
        visible = self.filewise_file_list.isVisible()
        self.filewise_file_list.setVisible(not visible)
        arrow = "\u25B6" if visible else "\u25BC"
        self.tab_widget.setTabText(self._filewise_tab_idx,
                                   f"{arrow} Filewise Diff")
        if visible:
            self.filewise_file_list.setMinimumHeight(0)
            self.filewise_splitter.setCollapsible(0, True)
            self.filewise_splitter.setSizes([0, 1000])
            self.filewise_splitter.handle(0).setEnabled(False)
        else:
            self.filewise_file_list.setMinimumHeight(60)
            self.filewise_splitter.setCollapsible(0, False)
            self.filewise_splitter.setSizes([150, 350])
            self.filewise_splitter.handle(0).setEnabled(True)

    def _toggle_treewise_file_list(self):
        visible = self.treewise_tree.isVisible()
        self.treewise_tree.setVisible(not visible)
        arrow = "\u25B6" if visible else "\u25BC"
        self.tab_widget.setTabText(self._treewise_tab_idx,
                                   f"{arrow} Tree-wise Diff")
        if visible:
            self.treewise_tree.setMinimumHeight(0)
            self.treewise_splitter.setCollapsible(0, True)
            self.treewise_splitter.setSizes([0, 1000])
            self.treewise_splitter.handle(0).setEnabled(False)
        else:
            self.treewise_tree.setMinimumHeight(60)
            self.treewise_splitter.setCollapsible(0, False)
            self.treewise_splitter.setSizes([150, 350])
            self.treewise_splitter.handle(0).setEnabled(True)

    def _on_tab_changed(self, idx):
        if idx == self._filewise_tab_idx and not self.filewise_file_list.isVisible():
            self._toggle_filewise_file_list()
        elif idx == self._treewise_tab_idx and not self.treewise_tree.isVisible():
            self._toggle_treewise_file_list()

    def _on_tab_bar_clicked(self, idx):
        if idx == self.tab_widget.currentIndex():
            if idx == self._filewise_tab_idx:
                self._toggle_filewise_file_list()
            elif idx == self._treewise_tab_idx:
                self._toggle_treewise_file_list()

    def show_filewise_context_menu(self, pos):
        item = self.filewise_file_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        head = _get_head_sha(self.repo_path)
        entry = item.data(FILE_ENTRY_ROLE)
        filepath = entry[1] if entry else item.text()
        add_open_with_system_default_action(menu, filepath, self, sha=self.sha,
            is_head=self.sha == head or head.startswith(self.sha))
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=filepath: open_blame_window(self, text, branch=self.sha))
        menu.addAction(blame_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=filepath: self._copy_filename(text))
        menu.addAction(copy_action)

        menu.exec(self.filewise_file_list.mapToGlobal(pos))

    def show_treewise_context_menu(self, pos):
        item = self.treewise_tree.itemAt(pos)
        if not item:
            return
        item_data = item.data(0, Qt.UserRole + 10)
        if not item_data or item_data["type"] != "file":
            return
        entry = item_data.get("entry")
        if not entry:
            return
        filepath = entry[2] if entry[0] == 'R' else entry[1]
        menu = QMenu(self)
        head = _get_head_sha(self.repo_path)
        add_open_with_system_default_action(menu, filepath, self, sha=self.sha,
            is_head=self.sha == head or head.startswith(self.sha))
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=filepath: open_blame_window(self, text, branch=self.sha))
        menu.addAction(blame_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=filepath: self._copy_filename(text))
        menu.addAction(copy_action)

        menu.exec(self.treewise_tree.mapToGlobal(pos))

    def _copy_filename(self, filename):
        QApplication.clipboard().setText(filename)
        QMessageBox.information(self, "Copied", f"Copied '{filename}' to clipboard.")

    def get_selected_files(self):
        """Return list of checked file paths."""
        return self._checked_filewise_files()

    def get_selected_file(self):
        """Return the first checked file (for backward compatibility)."""
        files = self._checked_filewise_files()
        return files[0] if files else None


class DropFileFromCommitDialog(QDialog):
    """Dialog for dropping a single file's changes from a commit."""
    def __init__(self, repo_path, sha, files, font_size=10, font_family=None, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.sha = sha
        self.font_size = font_size
        self.font_family = font_family
        self.selected_file = None
        self.setWindowTitle(f"Drop File From Commit: {sha}")
        self.setMinimumSize(860, 620)

        # Diff colors from parent theme
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
        self.msg_view.setFont(mono_font(font_size, family=self.font_family))
        msg_layout.addWidget(self.msg_view)

        self.main_splitter.addWidget(msg_widget)

        # Row 2: File List
        file_widget = QWidget()
        file_layout = QVBoxLayout(file_widget)
        file_layout.setContentsMargins(0, 5, 0, 0)
        file_layout.addWidget(QLabel("<b>Select a file</b> to drop from this commit:"))

        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(60)
        self.file_list.setFont(mono_font(font_size, family=self.font_family))
        for f in files:
            item = QListWidgetItem(f)
            item.setData(Qt.UserRole, self.file_stats.get(f))
            self.file_list.addItem(item)
        stats_delegate = StatsItemDelegate(
            added_color=colors.get("added", "#22863a"),
            removed_color=colors.get("removed", "#cb2431"),
            parent=self.file_list
        )
        self.file_list.setItemDelegate(stats_delegate)
        self.file_list.currentTextChanged.connect(self.on_file_selected)
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
        self.diff_view.setFont(mono_font(font_size, family=self.font_family))
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

        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self.search_bar.show_and_focus)

        self.main_splitter.addWidget(diff_widget)

        # Initial sizes for [Message, File List, Diff View]
        self.main_splitter.setSizes([100, 150, 350])
        layout.addWidget(self.main_splitter)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.drop_btn = QPushButton("Drop selected file changes from this commit")
        self.drop_btn.setMinimumWidth(160)
        self.drop_btn.setEnabled(False)  # only enabled when a file is selected
        self.drop_btn.setProperty("class", "dialog-btn")
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.setProperty("class", "dialog-btn-secondary")
        self.drop_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.drop_btn)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Auto-select first file
        if files:
            self.file_list.setCurrentRow(0)

    def show_file_context_menu(self, pos):
        item = self.file_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        head = _get_head_sha(self.repo_path)
        add_open_with_system_default_action(menu, item.text(), self, sha=self.sha,
            is_head=self.sha == head or head.startswith(self.sha))
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=item.text(): open_blame_window(self, text, branch=self.sha))
        menu.addAction(blame_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=item.text(): self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)

        if is_editable_branch(self):
            drop_action = QAction("Drop file changes from this commit", self)
            drop_action.triggered.connect(lambda checked=False, text=item.text(): self.drop_file(text))
            menu.addAction(drop_action)

            remove_onwards_action = QAction("Remove file from this commit onwards", self)
            remove_onwards_action.triggered.connect(lambda checked=False, text=item.text(): self.remove_file_onwards(text))
            menu.addAction(remove_onwards_action)

        menu.exec(self.file_list.mapToGlobal(pos))

    def drop_file(self, filepath):
        self.selected_file = filepath
        self.accept()

    def remove_file_onwards(self, filepath):
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        if main_win and hasattr(main_win, 'perform_remove_file_from_commit_onwards'):
            self.accept()
            QTimer.singleShot(0, lambda: main_win.perform_remove_file_from_commit_onwards(self.sha, filepath))

    def copy_filename_to_clipboard(self, filename):
        QApplication.clipboard().setText(filename)
        QMessageBox.information(self, "Copied", f"Copied '{filename}' to clipboard.")

    def on_file_selected(self, filepath):
        if not filepath:
            return
        self.selected_file = filepath
        self.drop_btn.setEnabled(True)
        try:
            diff = get_file_diff_only_in_commit(self.repo_path, self.sha, filepath)
            self.diff_view.setPlainText(diff)
            self.diff_view.set_separator_color(self.colors.get("separator", "#444444"))
        except Exception as e:
            self.diff_view.setPlainText(f"Error loading diff: {e}")

    def get_selected_file(self):
        return self.selected_file


class ConfirmDropFileDialog(DiffViewerDialog):
    """Confirmation dialog showing file diff before dropping file changes from a commit."""
    def __init__(self, sha, filepath, diff_text, font_size=10, font_family=None, parent=None):
        self.filepath = filepath
        super().__init__(f"Confirm Drop File Changes: {sha}", sha, diff_text, font_size, font_family, parent)

    def setup_header(self, sha):
        label = QLabel(f"Are you sure you want to drop changes of <b>{self.filepath}</b> from commit: <b>{sha}</b>?")
        label.setWordWrap(True)
        # Use theme-aware warning color
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        warning_color = "#f92672"
        if main_win and hasattr(main_win, 'current_theme_colors'):
            warning_color = main_win.current_theme_colors["removed"]
        label.setStyleSheet(f"color: {warning_color};")
        self.content_layout.addWidget(label)

    def setup_buttons(self):
        self.yes_btn = QPushButton("Yes, Drop this file's changes")
        self.no_btn = QPushButton("No, Cancel")

        self.yes_btn.setMinimumWidth(180)
        self.no_btn.setMinimumWidth(120)

        self.yes_btn.setProperty("class", "dialog-btn")
        self.no_btn.setProperty("class", "dialog-btn")

        self.yes_btn.clicked.connect(self.accept)
        self.no_btn.clicked.connect(self.reject)

        self.btn_layout.addWidget(self.yes_btn)
        self.btn_layout.addWidget(self.no_btn)


class ConfirmMoveFileDialog(DiffViewerDialog):
    """Confirmation dialog showing file diff before moving file changes out of a commit."""
    def __init__(self, sha, filepath, diff_text, font_size=10, font_family=None, parent=None):
        self.filepath = filepath
        super().__init__(f"Confirm Move File Out: {sha}", sha, diff_text, font_size, font_family, parent)

    def setup_header(self, sha):
        label = QLabel(f"Are you sure you want to move changes of <b>{self.filepath}</b> out of commit: <b>{sha}</b>?")
        label.setWordWrap(True)
        self.content_layout.addWidget(label)

    def setup_buttons(self):
        self.yes_btn = QPushButton("Yes, Move this file out")
        self.no_btn = QPushButton("No, Cancel")

        self.yes_btn.setMinimumWidth(180)
        self.no_btn.setMinimumWidth(120)

        self.yes_btn.setProperty("class", "dialog-btn")
        self.no_btn.setProperty("class", "dialog-btn")

        self.yes_btn.clicked.connect(self.accept)
        self.no_btn.clicked.connect(self.reject)

        self.btn_layout.addWidget(self.yes_btn)
        self.btn_layout.addWidget(self.no_btn)


class ConfirmRemoveFileOnwardsDialog(DiffViewerDialog):
    """Confirmation dialog for removing a file from a commit and all subsequent commits."""
    def __init__(self, sha, filepath, diff_text, later_modifications_detected=False, font_size=10, font_family=None, parent=None):
        self.filepath = filepath
        self.later_modifications_detected = later_modifications_detected
        super().__init__("Remove File from This Commit Onwards?", sha, diff_text, font_size, font_family, parent)

    def setup_header(self, sha):
        msg = (
            f"<b>File:</b><br>{self.filepath}<br><br>"
            f"This will remove the file from:<br><br>"
            f"✓ Selected commit ({sha})"
        )
        if self.later_modifications_detected:
            msg += "<br>✓ All following commits that modify it"

        label = QLabel(msg)
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)
        self.content_layout.addWidget(label)

        if self.later_modifications_detected:
            # Use theme-aware warning color
            main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
            warning_color = "#f92672"
            if main_win and hasattr(main_win, 'current_theme_colors'):
                warning_color = main_win.current_theme_colors["removed"]
            warning_label = QLabel(
                "<b>Warning:</b><br>"
                "This file is modified in later commits.<br><br>"
                "The operation may fail or stop during rebase and require manual conflict resolution."
            )
            warning_label.setWordWrap(True)
            warning_label.setTextFormat(Qt.RichText)
            warning_label.setStyleSheet(f"color: {warning_color}; padding: 6px; border: 1px solid {warning_color}; border-radius: 4px;")
            self.content_layout.addWidget(warning_label)

    def setup_buttons(self):
        if self.later_modifications_detected:
            self.yes_btn = QPushButton("Yes, Remove from Future Commits Too")
            self.no_btn = QPushButton("Cancel")

            # Make the yes button red to indicate destructive action
            # We use an inline style that mimics dialog-btn but overrides colors
            main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
            warning_color = "#f92672" # default red
            if main_win and hasattr(main_win, 'current_theme_colors'):
                warning_color = main_win.current_theme_colors.get("removed", "#f92672")

            self.yes_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {warning_color};
                    border: 1px solid {warning_color};
                    border-radius: 4px;
                    padding: 8px 16px;
                }}
                QPushButton:hover {{
                    background-color: rgba(249, 38, 114, 0.1);
                }}
            """)
            self.no_btn.setProperty("class", "dialog-btn")
        else:
            self.yes_btn = QPushButton("Yes, Remove from this commit onwards")
            self.no_btn = QPushButton("No, Cancel")
            self.yes_btn.setProperty("class", "dialog-btn")
            self.no_btn.setProperty("class", "dialog-btn")

        self.yes_btn.setMinimumWidth(260)
        self.no_btn.setMinimumWidth(120)

        self.yes_btn.clicked.connect(self.accept)
        self.no_btn.clicked.connect(self.reject)

        self.btn_layout.addWidget(self.yes_btn)
        self.btn_layout.addWidget(self.no_btn)


class AggressiveRemoveConfirmationDialog(QDialog):
    """
    Second confirmation dialog when a user chooses to remove a file from history
    and that file is modified in future commits.
    """
    def __init__(self, filepath, commits_modifying_file, has_empty_commits=False, font_size=10, font_family=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Proceed with aggressive file removal?")
        self.setMinimumSize(600, 480)
        self.font_size = font_size
        self.font_family = font_family
        self.has_empty_commits = has_empty_commits

        layout = QVBoxLayout(self)

        label_file = QLabel(f"<b>File:</b><br>{filepath}<br>")
        label_file.setTextFormat(Qt.RichText)
        layout.addWidget(label_file)

        label_desc = QLabel("The following commits modify this file and will also be updated:")
        layout.addWidget(label_desc)

        # List of future commits
        commit_list = QTextEdit()
        commit_list.setReadOnly(True)
        commit_list.setFont(mono_font(self.font_size, family=self.font_family))

        # Display each commit
        commits_text = ""
        for sha, msg in commits_modifying_file:
            commits_text += f"{sha[:8]}  {msg.splitlines()[0] if msg else ''}\n"
        commit_list.setPlainText(commits_text)
        layout.addWidget(commit_list)

        label_explain = QLabel(
            "<br><b>This operation will:</b><br><br>"
            "✓ Remove file changes from the above commits<br>"
            "✓ Remove file changes from currently selected commit<br>"
            "✓ Rewrite commit history<br>"
        )
        label_explain.setTextFormat(Qt.RichText)
        layout.addWidget(label_explain)

        main_win = parent if isinstance(parent, QMainWindow) else None
        warning_color = "#f92672"
        if main_win and hasattr(main_win, 'current_theme_colors'):
            warning_color = main_win.current_theme_colors.get("removed", "#f92672")

        label_warning = QLabel("Do this only if you understand the implications of rewriting commit history.")
        label_warning.setStyleSheet(f"color: {warning_color}; font-weight: bold;")
        layout.addWidget(label_warning)

        self.drop_empty_checkbox = QCheckBox("Drop commits that become empty")
        self.drop_empty_checkbox.setToolTip("Commits containing only changes to the selected file will be removed if they become empty.")
        if self.has_empty_commits:
            self.drop_empty_checkbox.setChecked(True)
        else:
            self.drop_empty_checkbox.setChecked(False)
            self.drop_empty_checkbox.setEnabled(False)
            self.drop_empty_checkbox.setStyleSheet("color: gray;")

        check_layout = QHBoxLayout()
        check_layout.addStretch()
        check_layout.addWidget(self.drop_empty_checkbox)
        check_layout.addStretch()
        layout.addLayout(check_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.proceed_btn = QPushButton("Proceed Anyway")
        self.cancel_btn = QPushButton("Cancel")

        self.proceed_btn.setMinimumWidth(160)
        self.cancel_btn.setMinimumWidth(100)

        self.proceed_btn.setProperty("class", "dialog-btn")
        self.cancel_btn.setProperty("class", "dialog-btn-secondary")

        self.proceed_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.proceed_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)


class RefineFileSelectDialog(SplitCommitDialog):
    """File-selection dialog for Refine Changes. Reuses SplitCommitDialog layout."""
    def __init__(self, repo_path, sha, files, font_size=10, font_family=None, parent=None):
        super().__init__(repo_path, sha, files, font_size, font_family, parent)
        self.setWindowTitle(f"Refine Changes: {sha}")
        self.move_btn.setText("Refine changes in selected file")
        self._refine_file = None

    def show_filewise_context_menu(self, pos):
        item = self.filewise_file_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        head = _get_head_sha(self.repo_path)
        entry = item.data(FILE_ENTRY_ROLE)
        filepath = entry[1] if entry else item.text()
        add_open_with_system_default_action(menu, filepath, self, sha=self.sha,
            is_head=self.sha == head or head.startswith(self.sha))
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=filepath: open_blame_window(self, text, branch=self.sha))
        menu.addAction(blame_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=filepath: self._copy_filename(text))
        menu.addAction(copy_action)

        if is_editable_branch(self):
            refine_action = QAction("Refine changes in selected file", self)
            refine_action.triggered.connect(lambda checked=False, text=filepath: self._select_and_accept(text))
            menu.addAction(refine_action)
        menu.exec(self.filewise_file_list.mapToGlobal(pos))

    def show_treewise_context_menu(self, pos):
        item = self.treewise_tree.itemAt(pos)
        if not item:
            return
        item_data = item.data(0, Qt.UserRole + 10)
        if not item_data or item_data["type"] != "file":
            return
        entry = item_data.get("entry")
        if not entry:
            return
        filepath = entry[2] if entry[0] == 'R' else entry[1]
        menu = QMenu(self)
        head = _get_head_sha(self.repo_path)
        add_open_with_system_default_action(menu, filepath, self, sha=self.sha,
            is_head=self.sha == head or head.startswith(self.sha))
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=filepath: open_blame_window(self, text, branch=self.sha))
        menu.addAction(blame_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=filepath: self._copy_filename(text))
        menu.addAction(copy_action)

        if is_editable_branch(self):
            refine_action = QAction("Refine changes in selected file", self)
            refine_action.triggered.connect(lambda checked=False, text=filepath: self._select_and_accept(text))
            menu.addAction(refine_action)
        menu.exec(self.treewise_tree.mapToGlobal(pos))

    def _select_and_accept(self, filepath):
        self._refine_file = filepath
        self.accept()

    def get_selected_file(self):
        return self._refine_file
