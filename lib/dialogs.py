
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
    get_current_branch,
    get_full_head_sha,
    classify_tracked_changes,
    get_branch_names,
    get_rename_diff_in_commit,
    get_commit_diff,
    get_commit_files_with_status,
)
from lib.utils import get_theme_colors
from lib.widgets import BrowseDimOverlay


def open_blame_window(parent, filename, branch=None):
    """Open the Blame viewer for *filename* at the given *branch*/ref.

    Parameters
    ----------
    parent : QWidget
        Parent widget (used to locate the repo_path and as dialog parent).
    filename : str
        Path of the file that was right-clicked.
    branch : str | None, optional
        Branch/SHA to blame at (default: HEAD).
    """
    repo_path = getattr(parent, "repo_path", None)
    if not repo_path:
        QMessageBox.critical(parent, "Error", "Repository path not available.")
        return
    font_size = getattr(parent, "current_font_size", 10)
    dlg = BlameDialog(repo_path, filename, ref=branch, font_size=font_size, parent=parent)
    dlg.exec()


class BlameDialog(QDialog):
    """Read-only blame viewer showing per-line commit attribution in a table.

    Layout follows the same greyish pattern as other browse windows:
    - Search bar + Search Options ▼ dropdown
    - Filter: checkboxes (Author, Subject, Code)
    - 6-column table (Commit, Author, Date, Subject, Line, Code)
    - Bottom bar: Always On Top, Show Author/Date/Subject, Refresh, Exit
    """

    _PALETTE = [
        "#4ec9b0", "#f48771", "#569cd6", "#dcdcaa",
        "#c586c0", "#ce9178", "#b5cea8", "#9cdcfe",
    ]

    def __init__(self, repo_path, filename, ref=None, font_size=10, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.filename = filename
        self.ref = ref
        self.font_size = font_size
        self._records = []
        self._sha_color = {}
        self._next_color_idx = 0
        self.is_dark_theme = False

        if parent and hasattr(parent, "is_dark_theme"):
            self.is_dark_theme = parent.is_dark_theme

        self.setWindowTitle(f"Browse Blame: {filename} (blame at {ref or 'HEAD'})")
        self.setMinimumSize(1100, 650)

        self._setup_ui()

        self._browse_overlay = BrowseDimOverlay(self, self.is_dark_theme)
        self._browse_overlay.raise_()

        self._load()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        monospace = "Monospace"

        # Search / Filter bar — same pattern as main app window
        search_row = QHBoxLayout()
        search_row.setSpacing(4)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search (in this file) ...")
        self.search_edit.setToolTip("Search blame output.")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        search_row.addWidget(self.search_edit, 1)

        self.search_opts_btn = QToolButton()
        self.search_opts_btn.setText("Search Options ▼")
        self.search_opts_btn.setToolTip("Search across: Author, Subject, Code")
        self.search_opts_btn.setPopupMode(QToolButton.InstantPopup)
        self.search_opts_btn.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0px; }")
        opts_menu = QMenu(self)
        self.filter_author_cb = QAction("Author", self)
        self.filter_author_cb.setCheckable(True)
        self.filter_author_cb.setChecked(True)
        self.filter_subject_cb = QAction("Subject", self)
        self.filter_subject_cb.setCheckable(True)
        self.filter_subject_cb.setChecked(True)
        self.filter_code_cb = QAction("Code", self)
        self.filter_code_cb.setCheckable(True)
        self.filter_code_cb.setChecked(True)
        opts_menu.addAction(self.filter_author_cb)
        opts_menu.addAction(self.filter_subject_cb)
        opts_menu.addAction(self.filter_code_cb)
        self.filter_author_cb.triggered.connect(self._apply_filter)
        self.filter_subject_cb.triggered.connect(self._apply_filter)
        self.filter_code_cb.triggered.connect(self._apply_filter)
        self.search_opts_btn.setMenu(opts_menu)
        search_row.addWidget(self.search_opts_btn)

        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("font-size: 11px; color: gray;")
        search_row.addWidget(filter_label)

        self.filter_by_author_cb = QCheckBox("Author")
        self.filter_by_author_cb.setChecked(True)
        self.filter_by_author_cb.toggled.connect(self._apply_filter)
        search_row.addWidget(self.filter_by_author_cb)

        self.filter_by_subject_cb = QCheckBox("Subject")
        self.filter_by_subject_cb.setChecked(True)
        self.filter_by_subject_cb.toggled.connect(self._apply_filter)
        search_row.addWidget(self.filter_by_subject_cb)

        self.filter_by_code_cb = QCheckBox("Code")
        self.filter_by_code_cb.setChecked(True)
        self.filter_by_code_cb.toggled.connect(self._apply_filter)
        search_row.addWidget(self.filter_by_code_cb)

        root.addLayout(search_row)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Commit", "Author", "Date", "Subject", "Line", "Code"])
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setFont(QFont(monospace, max(8, self.font_size - 1)))
        self.table.setSortingEnabled(False)
        root.addWidget(self.table, 1)

        # Bottom bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(12)

        self.always_on_top_cb = QCheckBox("Always On Top")
        self.always_on_top_cb.toggled.connect(self._on_always_on_top_toggled)
        bottom_bar.addWidget(self.always_on_top_cb)

        sep1 = QLabel("|")
        sep1.setStyleSheet("color: gray;")
        bottom_bar.addWidget(sep1)

        self.show_author_cb = QCheckBox("Show Author")
        self.show_author_cb.setChecked(True)
        self.show_author_cb.toggled.connect(self._refresh_table)
        bottom_bar.addWidget(self.show_author_cb)

        self.show_date_cb = QCheckBox("Show Date")
        self.show_date_cb.setChecked(True)
        self.show_date_cb.toggled.connect(self._refresh_table)
        bottom_bar.addWidget(self.show_date_cb)

        self.show_subject_cb = QCheckBox("Show Subject")
        self.show_subject_cb.setChecked(True)
        self.show_subject_cb.toggled.connect(self._refresh_table)
        bottom_bar.addWidget(self.show_subject_cb)

        bottom_bar.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Re-run git blame and reload.")
        refresh_btn.clicked.connect(self._load)
        bottom_bar.addWidget(refresh_btn)

        exit_btn = QPushButton("Exit")
        exit_btn.setToolTip("Close this blame window.")
        exit_btn.clicked.connect(self.close)
        exit_btn.setStyleSheet("color: red; font-weight: bold;")
        bottom_bar.addWidget(exit_btn)

        root.addLayout(bottom_bar)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, '_browse_overlay', None) is not None:
            self._browse_overlay.setGeometry(self.rect())

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, '_browse_overlay', None) is not None:
            self._browse_overlay.setGeometry(self.rect())
            self._browse_overlay.raise_()

    def _on_always_on_top_toggled(self, checked):
        flags = self.windowFlags()
        if checked:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        self.show()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _load(self):
        from lib.git_helpers import get_git_blame
        try:
            self._records = get_git_blame(self.repo_path, self.filename, self.ref)
        except Exception as e:
            QMessageBox.critical(self, "Blame failed", str(e))
            self._records = []
        self._assign_colors()
        self._refresh_table()

    def _assign_colors(self):
        self._sha_color.clear()
        self._next_color_idx = 0
        for rec in self._records:
            sha = rec["sha"]
            if sha not in self._sha_color:
                self._sha_color[sha] = QColor(self._PALETTE[self._next_color_idx % len(self._PALETTE)])
                self._next_color_idx += 1

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------

    def _refresh_table(self):
        self.table.setRowCount(0)
        filtered = self._get_filtered_records()
        self.table.setRowCount(len(filtered))

        for row_idx, rec in enumerate(filtered):
            sha_short = rec["sha"][:7]
            code = rec.get("code", "")
            line_no = str(rec.get("line_no", ""))
            author = rec.get("author", "")
            date = rec.get("date", "")
            subject = rec.get("summary", "")

            colour = self._sha_color.get(rec["sha"], QColor("#888888"))

            commit_item = QTableWidgetItem(sha_short)
            commit_item.setForeground(colour)
            f = commit_item.font()
            f.setBold(True)
            commit_item.setFont(f)
            commit_item.setToolTip(rec["sha"])
            self.table.setItem(row_idx, 0, commit_item)

            a = QTableWidgetItem(author)
            a.setForeground(colour)
            self.table.setItem(row_idx, 1, a)

            d = QTableWidgetItem(date)
            d.setForeground(colour)
            self.table.setItem(row_idx, 2, d)

            s = QTableWidgetItem(subject)
            s.setForeground(colour)
            self.table.setItem(row_idx, 3, s)

            li = QTableWidgetItem(line_no)
            li.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 4, li)

            ci = QTableWidgetItem(code)
            ci.setFont(QFont("Monospace", max(8, self.font_size - 1)))
            self.table.setItem(row_idx, 5, ci)

        self.table.setColumnHidden(1, not self.show_author_cb.isChecked())
        self.table.setColumnHidden(2, not self.show_date_cb.isChecked())
        self.table.setColumnHidden(3, not self.show_subject_cb.isChecked())
        self.table.resizeRowsToContents()

    # ------------------------------------------------------------------
    # Filter
    # ------------------------------------------------------------------

    def _get_filtered_records(self):
        term = self.search_edit.text().strip().lower()
        if not term:
            return self._records

        hits = []
        for rec in self._records:
            if self.filter_by_author_cb.isChecked() and term in rec.get("author", "").lower():
                hits.append(rec)
            elif self.filter_by_subject_cb.isChecked() and term in rec.get("summary", "").lower():
                hits.append(rec)
            elif self.filter_by_code_cb.isChecked() and term in rec.get("code", "").lower():
                hits.append(rec)
        return hits

    def _apply_filter(self):
        self._refresh_table()


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

class SplitCommitDialog(QDialog):
    """Dialog for moving a single file's changes out of a commit."""
    def __init__(self, repo_path, sha, files, font_size=10, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.sha = sha
        self.font_size = font_size
        self.selected_file = None
        self.setWindowTitle(f"Split Commit: {sha}")
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
        self.msg_view.setFont(QFont("Courier New", font_size))
        msg_layout.addWidget(self.msg_view)
        
        self.main_splitter.addWidget(msg_widget)

        # Row 2: File List
        file_widget = QWidget()
        file_layout = QVBoxLayout(file_widget)
        file_layout.setContentsMargins(0, 5, 0, 0)
        file_layout.addWidget(QLabel("<b>Select a file</b> to move out of this commit:"))
        
        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(60)
        self.file_list.setFont(QFont("Courier New", font_size))
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
        
        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self.search_bar.show_and_focus)

        self.main_splitter.addWidget(diff_widget)

        # Initial sizes for [Message, File List, Diff View]
        self.main_splitter.setSizes([100, 150, 350])
        layout.addWidget(self.main_splitter)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.move_btn = QPushButton("Move Out of Commit")
        self.move_btn.setMinimumWidth(160)
        self.move_btn.setEnabled(False)  # only enabled when a file is selected
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

        # Auto-select first file
        if files:
            self.file_list.setCurrentRow(0)

    def show_file_context_menu(self, pos):
        item = self.file_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=item.text(): self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)

        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=item.text(): open_blame_window(self, text))
        menu.addAction(blame_action)

        move_action = QAction("Move file changes out of this commit", self)
        move_action.triggered.connect(lambda checked=False, text=item.text(): self.move_file_out(text))
        menu.addAction(move_action)

        menu.exec(self.file_list.mapToGlobal(pos))

    def move_file_out(self, filepath):
        self.selected_file = filepath
        self.accept()

    def copy_filename_to_clipboard(self, filename):
        QApplication.clipboard().setText(filename)
        QMessageBox.information(self, "Copied", f"Copied '{filename}' to clipboard.")

    def on_file_selected(self, filepath):
        if not filepath:
            return
        self.selected_file = filepath
        self.move_btn.setEnabled(True)
        try:
            diff = get_file_diff_only_in_commit(self.repo_path, self.sha, filepath)
            self.diff_view.setPlainText(diff)
            self.diff_view.set_separator_color(self.colors.get("separator", "#444444"))
        except Exception as e:
            self.diff_view.setPlainText(f"Error loading diff: {e}")

    def get_selected_file(self):
        return self.selected_file

class DropFileFromCommitDialog(QDialog):
    """Dialog for dropping a single file's changes from a commit."""
    def __init__(self, repo_path, sha, files, font_size=10, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.sha = sha
        self.font_size = font_size
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
        self.msg_view.setFont(QFont("Courier New", font_size))
        msg_layout.addWidget(self.msg_view)
        
        self.main_splitter.addWidget(msg_widget)

        # Row 2: File List
        file_widget = QWidget()
        file_layout = QVBoxLayout(file_widget)
        file_layout.setContentsMargins(0, 5, 0, 0)
        file_layout.addWidget(QLabel("<b>Select a file</b> to drop from this commit:"))
        
        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(60)
        self.file_list.setFont(QFont("Courier New", font_size))
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
        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=item.text(): self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)

        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=item.text(): open_blame_window(self, text))
        menu.addAction(blame_action)

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
        self.filewise_file_list.currentTextChanged.connect(self.on_filewise_file_selected)
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

        self.tab_widget.addTab(filewise_widget, "Filewise Diff")

        layout.addWidget(self.tab_widget)

        # Populate the file list (block signals to avoid premature load)
        self.filewise_file_list.blockSignals(True)
        for f in files:
            item = QListWidgetItem(f)
            item.setData(Qt.UserRole, file_stats.get(f))
            self.filewise_file_list.addItem(item)
        self.filewise_file_list.blockSignals(False)
        if files:
            self.filewise_file_list.setCurrentRow(0)

        # Context menu for the file list
        self.filewise_file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.filewise_file_list.customContextMenuRequested.connect(self.show_filewise_context_menu)

        # Ctrl+F focuses the search bar of the active tab
        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self._focus_active_search)

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
        if self.tab_widget.currentIndex() == 0:
            self.plain_diff_search.show_and_focus()
        else:
            self.filewise_diff_search.show_and_focus()

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
        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=target_path: self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)

        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=target_path: open_blame_window(self, text))
        menu.addAction(blame_action)

        menu.addSeparator()
        browse_action = QAction("Browse file log", self)
        browse_action.setToolTip("Open a read-only viewer of this file's history.")
        browse_action.triggered.connect(lambda checked=False, text=target_path: self.browse_file_log(text))
        menu.addAction(browse_action)
        menu.exec(self.filewise_file_list.mapToGlobal(pos))

    def browse_file_log(self, filepath):
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        if main_win and hasattr(main_win, 'open_file_log_for'):
            main_win.open_file_log_for(filepath)

    def copy_filename_to_clipboard(self, filename):
        QApplication.clipboard().setText(filename)
        QMessageBox.information(self, "Copied", f"Copied '{filename}' to clipboard.")


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
        header = QLabel(f"Commit: <b>{sha}</b> <span style='color:gray;'>({commit_meta})</span>")
        header.setTextFormat(Qt.RichText)
        top_layout.addWidget(header)
        self.msg_view = QTextEdit()
        self.msg_view.setReadOnly(True)
        self.msg_view.setPlainText(commit_msg)
        self.msg_view.setFont(QFont("Courier New", font_size))
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
        self.filewise_file_list.currentTextChanged.connect(self.on_filewise_file_selected)
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

        self.tab_widget.addTab(filewise_widget, "Filewise Diff")

        self.main_splitter.addWidget(self.tab_widget)
        self.main_splitter.setSizes([150, 450])
        layout.addWidget(self.main_splitter)

        # Populate the file list (block signals to avoid premature load)
        self._files = []
        try:
            self._files = get_commit_files_with_status(repo_path, sha)
        except Exception:
            self._files = []
        self.filewise_file_list.blockSignals(True)
        for entry in self._files:
            status, path1, path2 = entry
            if status == 'R':
                display = f"{path1} => {path2}"
            else:
                display = path1
            item = QListWidgetItem(display)
            item.setData(FILE_ENTRY_ROLE, entry)
            self.filewise_file_list.addItem(item)
        self.filewise_file_list.blockSignals(False)
        if self._files:
            self.filewise_file_list.setCurrentRow(0)

        # Ctrl+F focuses the search bar of the active tab
        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self._focus_active_search)

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
        if self.tab_widget.currentIndex() == 0:
            self.plain_diff_search.show_and_focus()
        else:
            self.filewise_diff_search.show_and_focus()

    def on_filewise_file_selected(self, filepath):
        if not filepath:
            self.filewise_diff_view.clear()
            return
        try:
            item = self.filewise_file_list.currentItem()
            entry = item.data(FILE_ENTRY_ROLE) if item else None
            if entry and entry[0] == 'R':
                diff = get_rename_diff_in_commit(self.repo_path, self.sha, entry[1], entry[2])
            elif entry:
                diff = get_file_diff_only_in_commit(self.repo_path, self.sha, entry[1])
            else:
                diff = get_file_diff_only_in_commit(self.repo_path, self.sha, filepath)
            self.filewise_diff_view.setPlainText(diff)
            self.filewise_diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.filewise_diff_search._perform_search()
        except Exception as e:
            self.filewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def show_filewise_context_menu(self, pos):
        """Context menu for the file list. If the viewed commit is known to be in
        the current branch's list (editable=True, opened from a list item), the
        full edit options are offered. Otherwise the commit may be an arbitrary
        SHA outside the branch, so only safe actions (copy, browse log) appear."""
        item = self.filewise_file_list.itemAt(pos)
        if not item:
            return
        entry = item.data(FILE_ENTRY_ROLE)
        target_path = entry[2] if entry and entry[0] == 'R' else item.text()
        menu = QMenu(self)
        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=target_path: self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)

        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=target_path: open_blame_window(self, text))
        menu.addAction(blame_action)

        if self.editable:
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
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        if main_win and hasattr(main_win, 'open_file_log_for'):
            main_win.open_file_log_for(filepath)

    def copy_filename_to_clipboard(self, filename):
        QApplication.clipboard().setText(filename)
        QMessageBox.information(self, "Copied", f"Copied '{filename}' to clipboard.")


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
            item.setData(Qt.UserRole, self.file_stats.get(display))
            item.setData(FILE_ENTRY_ROLE, entry)
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
        btn_layout.addStretch()
        cancel_btn = QPushButton("Close")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.setProperty("class", "dialog-btn-secondary")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        if files:
            self.file_list.setCurrentRow(0)

    def show_file_context_menu(self, pos):
        item = self.file_list.itemAt(pos)
        if not item:
            return
        entry = item.data(FILE_ENTRY_ROLE)
        target_path = entry[2] if entry and entry[0] == 'R' else item.text()
        menu = QMenu(self)
        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=target_path: self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)

        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=target_path: open_blame_window(self, text))
        menu.addAction(blame_action)
        
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
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
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

class DropDialog(DiffViewerDialog):
    def __init__(self, sha, diff_text, font_size=10, parent=None):
        super().__init__("Confirm Drop Commit", sha, diff_text, font_size, parent)

    def setup_header(self, sha):
        label = QLabel(f"Are you sure you want to drop the commit: <b>{sha}</b>?")
        # Use theme-aware warning color
        app = QApplication.instance()
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        warning_color = "#f92672" # Default red
        if main_win and hasattr(main_win, 'current_theme_colors'):
             warning_color = main_win.current_theme_colors["removed"]
             
        label.setStyleSheet(f"color: {warning_color};") 
        self.layout.addWidget(label)

    def setup_buttons(self):
        self.yes_btn = QPushButton("Yes, Drop it")
        self.no_btn = QPushButton("No, Cancel")
        
        self.yes_btn.setMinimumWidth(120)
        self.no_btn.setMinimumWidth(120)
        
        self.yes_btn.setProperty("class", "dialog-btn")
        self.no_btn.setProperty("class", "dialog-btn")
        
        self.yes_btn.clicked.connect(self.accept)
        self.no_btn.clicked.connect(self.reject)
        
        self.btn_layout.addWidget(self.yes_btn)
        self.btn_layout.addWidget(self.no_btn)

class ConfirmDropFileDialog(DiffViewerDialog):
    """Confirmation dialog showing file diff before dropping file changes from a commit."""
    def __init__(self, sha, filepath, diff_text, font_size=10, parent=None):
        self.filepath = filepath
        super().__init__(f"Confirm Drop File Changes: {sha}", sha, diff_text, font_size, parent)

    def setup_header(self, sha):
        label = QLabel(f"Are you sure you want to drop changes of <b>{self.filepath}</b> from commit: <b>{sha}</b>?")
        label.setWordWrap(True)
        # Use theme-aware warning color
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        warning_color = "#f92672"
        if main_win and hasattr(main_win, 'current_theme_colors'):
            warning_color = main_win.current_theme_colors["removed"]
        label.setStyleSheet(f"color: {warning_color};")
        self.layout.addWidget(label)

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
    def __init__(self, sha, filepath, diff_text, font_size=10, parent=None):
        self.filepath = filepath
        super().__init__(f"Confirm Move File Out: {sha}", sha, diff_text, font_size, parent)

    def setup_header(self, sha):
        label = QLabel(f"Are you sure you want to move changes of <b>{self.filepath}</b> out of commit: <b>{sha}</b>?")
        label.setWordWrap(True)
        self.layout.addWidget(label)

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
    def __init__(self, sha, filepath, diff_text, later_modifications_detected=False, font_size=10, parent=None):
        self.filepath = filepath
        self.later_modifications_detected = later_modifications_detected
        super().__init__("Remove File from This Commit Onwards?", sha, diff_text, font_size, parent)

    def setup_header(self, sha):
        msg = (
            f"<b>File:</b><br>{self.filepath}<br><br>"
            f"This will remove the file from:<br><br>"
            f"✓ Selected commit ({sha})"
        )
        if self.later_modifications_detected:
            msg += f"<br>✓ All following commits that modify it"
        
        label = QLabel(msg)
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)
        self.layout.addWidget(label)

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
            self.layout.addWidget(warning_label)

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
    def __init__(self, filepath, commits_modifying_file, has_empty_commits=False, font_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Proceed with aggressive file removal?")
        self.setMinimumSize(600, 480)
        self.font_size = font_size
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
        commit_list.setFont(QFont("Courier New", self.font_size))
        
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

class RephraseDialog(QDialog):
    """Dialog for editing commit message."""
    def __init__(self, sha, current_message, font_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Rephrase Commit: {sha}")
        self.setMinimumSize(600, 400)
        self.font_size = font_size
        
        layout = QVBoxLayout(self)
        
        label = QLabel(f"Edit commit message for: <b>{sha}</b>")
        layout.addWidget(label)
        
        self.message_edit = QTextEdit()
        self.message_edit.setFont(QFont("Courier New", self.font_size))
        self.message_edit.setPlainText(current_message)
        layout.addWidget(self.message_edit)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.apply_btn = QPushButton("Apply")
        self.discard_btn = QPushButton("Discard")
        
        for btn in [self.apply_btn, self.discard_btn]:
            btn.setMinimumWidth(120)
            btn.setMinimumHeight(40)
            btn.setProperty("class", "dialog-btn")
            
        self.apply_btn.clicked.connect(self.accept)
        self.discard_btn.clicked.connect(self.reject)
        
        self.message_edit.textChanged.connect(self.on_text_changed)
        self.on_text_changed()
        
        btn_layout.addWidget(self.apply_btn)
        btn_layout.addWidget(self.discard_btn)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)

    def get_message(self):
        return self.message_edit.toPlainText().strip()
        
    def on_text_changed(self):
        self.apply_btn.setEnabled(bool(self.message_edit.toPlainText().strip()))


class NewCommitMessageDialog(QDialog):
    """Dialog for entering a new commit message (e.g. during Move Hunks)."""
    def __init__(self, title, label_text, default_message="", font_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(600, 400)
        self.font_size = font_size
        
        layout = QVBoxLayout(self)
        
        self.label = QLabel(label_text)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        
        self.message_edit = QTextEdit()
        self.message_edit.setFont(QFont("Courier New", self.font_size))
        self.message_edit.setPlainText(default_message)
        layout.addWidget(self.message_edit)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.proceed_btn = QPushButton("Proceed")
        self.cancel_btn = QPushButton("Cancel")
        
        for btn in [self.proceed_btn, self.cancel_btn]:
            btn.setMinimumWidth(120)
            btn.setMinimumHeight(40)
            btn.setProperty("class", "dialog-btn")
            
        self.proceed_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        
        self.message_edit.textChanged.connect(self.on_text_changed)
        self.on_text_changed()
        
        btn_layout.addWidget(self.proceed_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)

    def get_message(self):
        return self.message_edit.toPlainText().strip()
        
    def on_text_changed(self):
        self.proceed_btn.setEnabled(bool(self.message_edit.toPlainText().strip()))

class CherryPickDialog(QDialog):
    """Dialog for entering a commit SHA to cherry-pick."""
    def __init__(self, font_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cherry-pick Commit")
        self.setFixedSize(600, 180)
        self.font_size = font_size
        self.chosen = None

        layout = QVBoxLayout(self)

        self.label = QLabel("Enter the commit SHA.")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

        self.sha_edit = QLineEdit()
        self.sha_edit.setPlaceholderText("Commit SHA")
        self.sha_edit.setFont(QFont("Courier New", self.font_size))
        self.sha_edit.setMinimumHeight(36)
        layout.addWidget(self.sha_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cherry_pick_btn = QPushButton("Cherry-pick")
        self.no_commit_btn = QPushButton("Cherry-pick (--no-commit)")
        self.cancel_btn = QPushButton("Cancel")

        for btn in [self.cherry_pick_btn, self.no_commit_btn, self.cancel_btn]:
            btn.setMinimumWidth(120)
            btn.setMinimumHeight(40)
            btn.setProperty("class", "dialog-btn")

        self.cherry_pick_btn.clicked.connect(lambda: self._choose("normal"))
        self.no_commit_btn.clicked.connect(lambda: self._choose("no_commit"))
        self.cancel_btn.clicked.connect(self.reject)

        self.sha_edit.textChanged.connect(self.on_text_changed)
        self.on_text_changed()

        btn_layout.addWidget(self.cherry_pick_btn)
        btn_layout.addWidget(self.no_commit_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    def _choose(self, choice):
        self.chosen = choice
        self.accept()

    def get_sha(self):
        return self.sha_edit.text().strip()

    def on_text_changed(self):
        has_text = bool(self.sha_edit.text().strip())
        self.cherry_pick_btn.setEnabled(has_text)
        self.no_commit_btn.setEnabled(has_text)

class RevertCommitDialog(QDialog):
    """Dialog for editing the commit message before reverting a commit."""
    def __init__(self, sha, revert_message, font_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Revert Commit: {sha}")
        self.setMinimumSize(600, 300)
        self.font_size = font_size

        layout = QVBoxLayout(self)

        label = QLabel(
            f"Reverting commit <b>{sha}</b>. "
            "Edit the revert commit message below:"
        )
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)

        self.message_edit = QTextEdit()
        self.message_edit.setFont(QFont("Courier New", self.font_size))
        self.message_edit.setPlainText(revert_message)
        layout.addWidget(self.message_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.revert_btn = QPushButton("Revert")
        self.cancel_btn = QPushButton("Cancel")

        for btn in [self.revert_btn, self.cancel_btn]:
            btn.setMinimumWidth(120)
            btn.setMinimumHeight(40)
            btn.setProperty("class", "dialog-btn")

        self.revert_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self.message_edit.textChanged.connect(self._on_text_changed)
        self._on_text_changed()

        btn_layout.addWidget(self.revert_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def get_message(self):
        return self.message_edit.toPlainText().strip()

    def _on_text_changed(self):
        self.revert_btn.setEnabled(bool(self.message_edit.toPlainText().strip()))


class SquashDialog(QDialog):
    """Dialog for choosing and editing commit message during squash."""
    def __init__(self, sha1, msg1, sha2, msg2, font_size=10, parent=None, default_radio=1):
        super().__init__(parent)
        self.setWindowTitle("Interactive Squash")
        self.setMinimumSize(600, 400)
        self.font_size = font_size
        
        self.msg1 = msg1
        self.msg2 = msg2
        
        layout = QVBoxLayout(self)
        
        # Label
        layout.addWidget(QLabel("Select or edit the final commit message:"))
        
        # Radio Buttons
        self.radio1 = QRadioButton(f"Use commit msg of {sha1}: {msg1.splitlines()[0][:50]}...")
        self.radio2 = QRadioButton(f"Use commit msg of {sha2}: {msg2.splitlines()[0][:50]}...")
        
        layout.addWidget(self.radio1)
        layout.addWidget(self.radio2)
        
        # Text Editor
        self.editor = QTextEdit()
        self.editor.setFont(QFont("Courier New", self.font_size))
        layout.addWidget(self.editor)
        
        # Connections
        self.radio1.toggled.connect(self.on_radio_toggled)
        self.radio2.toggled.connect(self.on_radio_toggled)
        
        # Default selection
        if default_radio == 2:
            self.radio2.setChecked(True)
            self.editor.setPlainText(self.msg2)
        else:
            self.radio1.setChecked(True)
            self.editor.setPlainText(self.msg1)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.proceed_btn = QPushButton("Proceed")
        self.cancel_btn = QPushButton("Cancel")
        
        self.proceed_btn.setProperty("class", "dialog-btn")
        self.cancel_btn.setProperty("class", "dialog-btn")
        
        self.proceed_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        
        self.editor.textChanged.connect(self.on_text_changed)
        self.on_text_changed()
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.proceed_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def on_radio_toggled(self):
        if self.radio1.isChecked():
            self.editor.setPlainText(self.msg1)
        elif self.radio2.isChecked():
            self.editor.setPlainText(self.msg2)

    def get_message(self):
        return self.editor.toPlainText().strip()
        
    def on_text_changed(self):
        self.proceed_btn.setEnabled(bool(self.editor.toPlainText().strip()))


class MultiSquashDialog(QDialog):
    """Dialog for squashing N commits — shows one radio per commit for message selection."""
    def __init__(self, sha_msg_pairs, font_size=10, parent=None):
        """
        sha_msg_pairs: list of (sha, full_commit_message) in newest→oldest order
        """
        super().__init__(parent)
        self.setWindowTitle("Squash Commits — Choose Final Commit Message")
        self.setMinimumSize(680, 480)
        self.sha_msg_pairs = sha_msg_pairs

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"<b>Squashing {len(sha_msg_pairs)} commits.</b>  "
            "Select which commit message to use as the base, then edit:"
        ))

        # Main splitter to allow resizing between the list and the editor
        self.splitter = QSplitter(Qt.Vertical)
        
        # Scroll area for the radio buttons
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.scroll_area.setMinimumHeight(100)
        
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(5, 5, 5, 5)

        # Dynamic radio buttons — one per commit
        self.radios = []
        for sha, msg in sha_msg_pairs:
            first_line = msg.splitlines()[0][:60] if msg else "(empty)"
            radio = QRadioButton(f"{sha}: {first_line}...")
            self.scroll_layout.addWidget(radio)
            self.radios.append(radio)
        
        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        
        # Text editor
        self.editor = QTextEdit()
        self.editor.setFont(QFont("Courier New", font_size))
        self.editor.setMinimumHeight(100)

        # Add to splitter
        self.splitter.addWidget(self.scroll_area)
        self.splitter.addWidget(self.editor)
        
        # Disable collapsing for both panes to ensure minimum heights are respected
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        
        # Set stretch factors: list area gets some, editor gets more
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        
        layout.addWidget(self.splitter)

        # Wire radio toggling to update editor
        for i, radio in enumerate(self.radios):
            radio.toggled.connect(lambda checked, idx=i: self._on_radio(checked, idx))

        # Default: first commit selected
        self.radios[0].setChecked(True)
        self.editor.setPlainText(sha_msg_pairs[0][1])

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.proceed_btn = QPushButton("Proceed")
        self.cancel_btn = QPushButton("Cancel")
        self.proceed_btn.setProperty("class", "dialog-btn")
        self.cancel_btn.setProperty("class", "dialog-btn")
        self.proceed_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        
        self.editor.textChanged.connect(self.on_text_changed)
        self.on_text_changed()
        btn_layout.addWidget(self.proceed_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def _on_radio(self, checked, idx):
        if checked:
            self.editor.setPlainText(self.sha_msg_pairs[idx][1])

    def get_message(self):
        return self.editor.toPlainText().strip()
        
    def on_text_changed(self):
        self.proceed_btn.setEnabled(bool(self.editor.toPlainText().strip()))


class ProgressDialog(QDialog):
    """Indeterminate progress dialog for background operations."""
    def __init__(self, title, message, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(450, 150)
        self.setModal(True)
        
        # Disable close button and other hints to make it more "locked"
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint & ~Qt.WindowCloseButtonHint)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(10)
        
        self.label = QLabel(message)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setMinimumHeight(20)
        layout.addWidget(self.progress_bar)
        
        # Add some spacing at the bottom
        layout.addSpacing(10)


class UnstagedChangesDialog(QDialog):
    """Warning dialog for unstaged changes on startup."""
    CommitEachResult = 2
    BulkCommitResult = 3
    AmendResult = 4
    ViewerModeResult = 5
    DiscardResult = 6
    MergeResult = 7
    SelectiveCommitResult = 8

    def __init__(self, num_files, parent=None, from_rescan=False, repo_path=None, unstaged_files=None, font_size=None, managed_stash_exists=False, managed_stash_sha=None, viewer_mode=False):
        super().__init__(parent)
        self.repo_path = repo_path
        self.unstaged_files = unstaged_files or []
        self.managed_stash_sha = managed_stash_sha
        self.managed_stash_exists = managed_stash_exists or bool(managed_stash_sha)
        self.viewer_mode = viewer_mode
        if font_size is None:
            font_size = int(QSettings("shyjun", "GitInteractiveRebase").value("font_size", 10))
        self.font_size = font_size
        self.setWindowTitle("Unstaged Changes Warning")
        self.setMinimumWidth(600)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        message = (
            "<b>You have unstaged changes in the repo.</b><br><br>"
            "If needed, we can stash the changes and go ahead with the app. "
            "But be very careful with what you are doing.<br><br>"
            "Alternatively, we can <b>commit the changes</b> in various ways before we proceed.<br><br>"
            "<b>Note:</b> Untracked files are <b>not considered</b> and will be left untouched.<br><br>"
            "Otherwise, please exit, commit/discard manually, and start the app again."
        )
        
        self.label = QLabel(message)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("font-size: 13px; font-weight: normal;")
        layout.addWidget(self.label)
        
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(10)
        
        self.view_changes_btn = QPushButton("Show unstaged changes")
        self.view_changes_btn.setToolTip("Open a read-only viewer with only the unstaged changes. No edits allowed.")
        
        self.stash_btn = QPushButton("Stash and proceed to app")
        self.stash_btn.setToolTip("Stash all uncommitted changes and proceed to the app.")

        self.commit_selectively_btn = QPushButton("Commit Selectively")
        self.commit_selectively_btn.setToolTip("Choose which files (or diff hunks) to commit before starting the app.")

        commit_each_text = f"Commit each file changes separately and start app ({num_files} files modified, {num_files} commits)"
        self.commit_each_btn = QPushButton(commit_each_text)
        self.commit_each_btn.setToolTip("Commit each file's changes as its own commit, then start the app.")
        
        bulk_commit_text = f"Commit all unsaved changes to a single 'bulk' commit (Number of modified files: {num_files})"
        self.bulk_commit_btn = QPushButton(bulk_commit_text)
        self.bulk_commit_btn.setToolTip("Commit all changes into a single 'bulk' commit, then start the app.")
        
        amend_text = "Amend all changes into the HEAD commit (--amend --no-edit)"
        self.amend_btn = QPushButton(amend_text)
        self.amend_btn.setToolTip("Amend all changes into the HEAD commit (--amend --no-edit).")
        
        self.discard_btn = QPushButton("Discard unstaged changes (git checkout .), staged changes if any is untouched")
        self.discard_btn.setToolTip("Discard only unstaged (worktree) changes in tracked files. Staged changes are left untouched. This cannot be undone.")
        
        viewer_label = "Switch to" if from_rescan else "Start in"
        self.viewer_mode_btn = QPushButton(f"{viewer_label} Viewer Mode (No history-modifying operations will be allowed)")
        self.viewer_mode_btn.setToolTip(f"{viewer_label} Viewer Mode. Warning: no history-modifying operations are allowed.")

        self.exit_btn = QPushButton("Exit")
        self.exit_btn.setToolTip("Exit the application.")
        
        # Style buttons a bit
        for btn in [self.view_changes_btn, self.stash_btn, self.commit_selectively_btn, self.commit_each_btn, self.bulk_commit_btn, self.amend_btn, self.discard_btn, self.viewer_mode_btn, self.exit_btn]:
            btn.setMinimumHeight(35)
        
        self.view_changes_btn.clicked.connect(self.show_unstaged_changes)
        self.stash_btn.clicked.connect(self._on_stash)
        self.commit_selectively_btn.clicked.connect(lambda: self.done(self.SelectiveCommitResult))
        self.commit_each_btn.clicked.connect(lambda: self.done(self.CommitEachResult))
        self.bulk_commit_btn.clicked.connect(lambda: self.done(self.BulkCommitResult))
        self.amend_btn.clicked.connect(lambda: self.done(self.AmendResult))
        self.discard_btn.clicked.connect(self._on_discard)
        self.viewer_mode_btn.clicked.connect(lambda: self.done(self.ViewerModeResult))
        self.exit_btn.clicked.connect(self.reject)

        if self.viewer_mode:
            # In Viewer Mode no history-modifying / committing actions are allowed.
            # Discarding unstaged changes is still permitted.
            not_allowed = "Not allowed in Viewer Mode."
            for btn in [self.stash_btn, self.commit_selectively_btn, self.commit_each_btn, self.bulk_commit_btn, self.amend_btn]:
                btn.setEnabled(False)
                btn.setToolTip(not_allowed)
            self.viewer_mode_btn.setVisible(False)
        
        btn_layout.addWidget(self.view_changes_btn)
        btn_layout.addWidget(self.stash_btn)
        btn_layout.addWidget(self.commit_selectively_btn)
        btn_layout.addWidget(self.commit_each_btn)
        btn_layout.addWidget(self.bulk_commit_btn)
        btn_layout.addWidget(self.amend_btn)
        btn_layout.addWidget(self.discard_btn)
        btn_layout.addWidget(self.viewer_mode_btn)
        btn_layout.addWidget(self.exit_btn)
        
        layout.addLayout(btn_layout)

    def show_unstaged_changes(self):
        """Open a read-only viewer (same layout as View PR Diff) with only the unstaged changes."""
        if not self.repo_path:
            return
        try:
            diff_text = get_unstaged_diff(self.repo_path, ignore_submodules=True)
            file_stats = get_unstaged_file_stats(self.repo_path, ignore_submodules=True)
            branch = get_current_branch(self.repo_path) or "HEAD"
            head_sha = get_full_head_sha(self.repo_path)
            dlg = UnstagedDiffDialog(
                self.repo_path, self.unstaged_files, diff_text, file_stats,
                branch, head_sha, self.font_size, self
            )
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Unstaged Changes", f"Could not load unstaged changes: {e}")

    def _on_stash(self):
        """Handle 'Stash and proceed'. Only one managed stash is allowed per session."""
        if self.managed_stash_exists:
            # Offer to merge the current unstaged changes into the existing app-created stash
            box = QMessageBox(self)
            box.setWindowTitle("App-created stash already exists")
            box.setIcon(QMessageBox.Question)
            box.setTextFormat(Qt.RichText)
            box.setText(
                "An app-created stash already exists.<br><br>"
                f"Existing app-created stash:<br><b>{self.managed_stash_sha}</b><br><br>"
                "Would you like the application to attempt to merge the current unstaged "
                "changes with the existing app-created stash?<br><br>"
                "If the merge cannot be completed, the original app-created stash and your "
                "current unstaged changes will both be preserved."
            )
            merge_btn = box.addButton("Merge", QMessageBox.AcceptRole)
            cancel_btn = box.addButton("Cancel", QMessageBox.RejectRole)
            box.setDefaultButton(cancel_btn)
            box.exec()
            if box.clickedButton() != merge_btn:
                return  # do nothing, keep dialog open so the user can choose another option
            self.done(self.MergeResult)
            return
        self.accept()

    def _on_discard(self):
        """Handle 'Discard unstaged changes (git checkout .)'. Destructive, so confirm first."""
        if not self.repo_path:
            return
        has_staged, has_unstaged = classify_tracked_changes(self.repo_path)

        # Only staged changes: nothing to discard — tell the user to commit instead.
        if has_staged and not has_unstaged:
            QMessageBox.information(
                self,
                "Staged Changes",
                "All tracked changes are in the staged state.\n\n"
                "Discarding won't remove staged changes. Please commit them."
            )
            return

        if has_staged and has_unstaged:
            # Both staged and unstaged: warn that only unstaged will be lost.
            answer = QMessageBox.warning(
                self,
                "Discard Changes",
                "There are changes in the staged and unstaged areas.\n"
                "If you continue, the unstaged changes will be lost, "
                "and staged changes will not be touched. Are you sure?\n\n"
                "This can't be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer == QMessageBox.Yes:
                self.done(self.DiscardResult)
            return

        # Only unstaged changes: keep the existing flow.
        answer = QMessageBox.warning(
            self,
            "Discard Changes",
            "Are you sure you want to discard all unstaged changes in tracked files?\n\n"
            "This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.done(self.DiscardResult)


class CommitSelectivelyDialog(QDialog):
    """Dialog to pick which files (with stats) to commit from the unstaged worktree
    changes. The bottom pane shows the combined (consolidated) diff of all CHECKED
    files, with a separator line before each file's diff, like the main diff pane.
    The commit buttons are greyed out while no file is checked."""
    CommitSelectedResult = 1
    GitAddPResult = 2
    AmendSelectedResult = 3

    def __init__(self, repo_path, files, file_stats, font_size=10, parent=None, colors=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.files = list(files)
        self.file_stats = file_stats or {}
        self.font_size = font_size

        if colors is None:
            main_win = parent if isinstance(parent, QMainWindow) else None
            if main_win and hasattr(main_win, 'current_theme_colors'):
                colors = main_win.current_theme_colors
            else:
                colors = {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef", "separator": "#444444"}
        self.colors = colors

        self.setWindowTitle("Commit Selectively")
        self.setMinimumSize(860, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        branch = get_current_branch(repo_path) or "HEAD"
        header = QLabel(
            f"Unstaged Changes: <b>{branch}</b> - {len(self.files)} file{'s' if len(self.files) != 1 else ''}<br>"
            "Select the files to commit. The bottom pane shows the combined diff "
            "of the selected (checked) files."
        )
        header.setTextFormat(Qt.RichText)
        header.setWordWrap(True)
        layout.addWidget(header)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        select_all_btn = QPushButton("Select All")
        deselect_all_btn = QPushButton("Deselect All")
        select_all_btn.setFixedWidth(110)
        deselect_all_btn.setFixedWidth(110)
        select_all_btn.setToolTip("Check all files.")
        deselect_all_btn.setToolTip("Uncheck all files.")
        select_all_btn.clicked.connect(lambda: self._set_all(True))
        deselect_all_btn.clicked.connect(lambda: self._set_all(False))
        top_row.addWidget(select_all_btn)
        top_row.addWidget(deselect_all_btn)
        top_row.addStretch()
        self.counter_label = QLabel()
        top_row.addWidget(self.counter_label)
        layout.addLayout(top_row)

        # File list with per-file stats; highlight/selection is independent of checkboxes
        self.file_list = QListWidget()
        self.file_list.setFont(QFont("Courier New", font_size))
        for f in self.files:
            item = QListWidgetItem(f)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, self.file_stats.get(f))
            self.file_list.addItem(item)
        self.stats_delegate = StatsItemDelegate(
            added_color=colors.get("added", "#22863a"),
            removed_color=colors.get("removed", "#cb2431"),
            parent=self.file_list
        )
        self.file_list.setItemDelegate(self.stats_delegate)
        self.file_list.itemChanged.connect(self._update_counter)
        self.file_list.itemChanged.connect(self._refresh_diff)

        # Diff preview with the shared search bar
        self.diff_view = DiffView()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(QFont("Courier New", font_size))
        self.diff_view.setPlaceholderText("No files selected. Check files to preview their combined diff...")
        self.highlighter = DiffHighlighter(
            self.diff_view.document(),
            added_color=colors["added"],
            removed_color=colors["removed"],
            header_color=colors["header"]
        )
        self.search_bar = DiffSearchBar(target_view=self.diff_view, parent=self)
        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self.search_bar.show_and_focus)

        # Splitter so the file list pane and the diff preview pane are resizable
        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self.file_list)
        diff_pane = QWidget()
        diff_pane_layout = QVBoxLayout(diff_pane)
        diff_pane_layout.setContentsMargins(0, 0, 0, 0)
        diff_pane_layout.setSpacing(4)
        diff_pane_layout.addWidget(self.search_bar)
        diff_pane_layout.addWidget(self.diff_view)
        self.main_splitter.addWidget(diff_pane)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 2)
        self.main_splitter.setSizes([260, 400])
        layout.addWidget(self.main_splitter)

        # Bottom actions
        bot_row = QHBoxLayout()
        bot_row.setSpacing(10)

        self.amend_btn = QPushButton("commit --amend selected files")
        self.amend_btn.setToolTip("Stage only the checked files and amend them into the HEAD commit (message is editable).")
        self.amend_btn.setStyleSheet(
            "QPushButton { color: #8e44ad; border: 2px solid #8e44ad; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #f6eefb; }"
        )

        self.commit_btn = QPushButton("Commit Selected Files")
        self.commit_btn.setDefault(True)
        self.commit_btn.setToolTip("Stage only the checked files and commit them in a single commit.")
        self.commit_btn.setStyleSheet(
            "QPushButton { color: #0055cc; border: 2px solid #0055cc; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #eef4ff; }"
        )

        self.add_p_btn = QPushButton("git add -p")
        self.add_p_btn.setToolTip("Pick individual diff hunks to stage, then commit/amend.")
        self.add_p_btn.setStyleSheet(
            "QPushButton { color: #e67e22; border: 2px solid #e67e22; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #fff9f0; }"
        )

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Close without committing anything.")
        cancel_btn.setStyleSheet(
            "QPushButton { color: #555; border: 2px solid #555; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #f5f5f5; }"
        )

        self.amend_btn.clicked.connect(lambda: self.done(self.AmendSelectedResult))
        self.commit_btn.clicked.connect(lambda: self.done(self.CommitSelectedResult))
        self.add_p_btn.clicked.connect(lambda: self.done(self.GitAddPResult))
        cancel_btn.clicked.connect(self.reject)

        amend_col = QVBoxLayout()
        amend_col.setSpacing(2)
        amend_col.addWidget(self.amend_btn)
        amend_note = QLabel("(amend HEAD message)")
        amend_note.setStyleSheet("color: #8e44ad; font-size: 11px;")
        amend_note.setAlignment(Qt.AlignCenter)
        amend_col.addWidget(amend_note)

        commit_col = QVBoxLayout()
        commit_col.setSpacing(2)
        commit_col.addWidget(self.commit_btn)
        commit_note = QLabel("(unchecked files stay unstaged)")
        commit_note.setStyleSheet("color: #0055cc; font-size: 11px;")
        commit_note.setAlignment(Qt.AlignCenter)
        commit_col.addWidget(commit_note)

        addp_col = QVBoxLayout()
        addp_col.setSpacing(2)
        addp_col.addWidget(self.add_p_btn)
        addp_note = QLabel("(stage hunk by hunk)")
        addp_note.setStyleSheet("color: #e67e22; font-size: 11px;")
        addp_note.setAlignment(Qt.AlignCenter)
        addp_col.addWidget(addp_note)

        cancel_col = QVBoxLayout()
        cancel_col.setSpacing(2)
        cancel_col.addWidget(cancel_btn)
        cancel_note = QLabel("Cancel")
        cancel_note.setStyleSheet("color: #555; font-size: 11px;")
        cancel_note.setAlignment(Qt.AlignCenter)
        cancel_col.addWidget(cancel_note)

        bot_row.addStretch()
        bot_row.addLayout(amend_col)
        bot_row.addLayout(commit_col)
        bot_row.addLayout(addp_col)
        bot_row.addLayout(cancel_col)
        layout.addLayout(bot_row)

        self._update_counter()
        self._refresh_diff()

    def _refresh_diff(self, _=None):
        """Show the combined diff of the currently checked files (separator line
        before each file, like the main window diff pane). With no files checked,
        the pane is cleared and the commit actions are greyed out."""
        checked = self.checked_files()
        self.amend_btn.setEnabled(bool(checked))
        self.commit_btn.setEnabled(bool(checked))
        self.add_p_btn.setEnabled(bool(checked))
        if not checked:
            self.diff_view.clear()
            return
        try:
            parts = []
            for f in checked:
                d = get_unstaged_file_diff(self.repo_path, f).rstrip("\n")
                if d:
                    parts.append(d)
            text = "\n\n".join(parts) + ("\n" if parts else "")
            self.diff_view.setPlainText(text)
            self.diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.search_bar._perform_search()
        except Exception as e:
            self.diff_view.setPlainText(f"Error loading diff: {e}")

    def _set_all(self, state):
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(Qt.Checked if state else Qt.Unchecked)

    def _update_counter(self, _=None):
        total = self.file_list.count()
        sel = len(self.checked_files())
        self.counter_label.setText(f"<b>Selected:</b> {sel}&nbsp;&nbsp;<b>Total:</b> {total}")
        self.counter_label.setTextFormat(Qt.RichText)

    def checked_files(self):
        return [self.file_list.item(i).text()
                for i in range(self.file_list.count())
                if self.file_list.item(i).checkState() == Qt.Checked]


class SelectiveHunkDialog(QDialog):
    """Hunk-level selection for 'git add -p'. Lists every hunk of all chosen files
    grouped under a per-file header. Only the checked hunks are staged (and then
    committed or amended); unchecked hunks are left untouched in the working tree."""
    CommitResult = 1
    AmendResult = 2

    def __init__(self, repo_path, files, diff_by_file, hunks_by_file, font_size=10, parent=None, colors=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.files = list(files)
        self.diff_by_file = diff_by_file
        self.hunks_by_file = hunks_by_file
        self.font_size = font_size
        self.result_action = None

        if colors is None:
            main_win = parent if isinstance(parent, QMainWindow) else None
            if main_win and hasattr(main_win, 'current_theme_colors'):
                colors = main_win.current_theme_colors
            else:
                colors = {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef", "separator": "#444444"}
        self.colors = colors

        self.setWindowTitle("Commit Selectively - git add -p")
        self.setMinimumSize(920, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QLabel(
            "<b>git add -p</b> - pick individual hunks to stage.<br>"
            "Only the checked hunks will be staged and committed. "
            "Unchecked hunks stay in the working tree untouched."
        )
        header.setTextFormat(Qt.RichText)
        header.setWordWrap(True)
        layout.addWidget(header)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        select_all_btn = QPushButton("Select All")
        deselect_all_btn = QPushButton("Deselect All")
        select_all_btn.setFixedWidth(110)
        deselect_all_btn.setFixedWidth(110)
        select_all_btn.clicked.connect(lambda: self._set_all(True))
        deselect_all_btn.clicked.connect(lambda: self._set_all(False))
        top_row.addWidget(select_all_btn)
        top_row.addWidget(deselect_all_btn)
        top_row.addStretch()
        self.counter_label = QLabel()
        top_row.addWidget(self.counter_label)
        layout.addLayout(top_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        hunks_layout = QVBoxLayout(container)
        hunks_layout.setSpacing(8)

        self.hunk_widgets = []   # list of (filepath, HunkWidget) in display order
        for f in self.files:
            hunks = self.hunks_by_file.get(f, [])
            if not hunks:
                continue
            file_label = QLabel(f"<b>File:</b> {f}")
            file_label.setTextFormat(Qt.RichText)
            file_label.setWordWrap(True)
            hunks_layout.addWidget(file_label)
            for i, (hdr, body) in enumerate(hunks):
                hw = HunkWidget(i + 1, hdr, body, self.colors, font_size,
                                sha=None, filepath=f, allow_edit=False)
                hw.checkbox.stateChanged.connect(self._update_counter)
                self.hunk_widgets.append((f, hw))
                hunks_layout.addWidget(hw)

        hunks_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Bottom: exactly git commit / git commit --amend / Cancel
        bot_row = QHBoxLayout()
        bot_row.setSpacing(10)

        self.commit_btn = QPushButton("git commit")
        self.commit_btn.setDefault(True)
        self.commit_btn.setToolTip("Stage the checked hunks and commit them with a new message.")
        self.commit_btn.setStyleSheet(
            "QPushButton { color: #0055cc; border: 2px solid #0055cc; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #eef4ff; }"
        )

        self.amend_btn = QPushButton("git commit --amend")
        self.amend_btn.setToolTip("Stage the checked hunks and amend them into the HEAD commit (message is editable).")
        self.amend_btn.setStyleSheet(
            "QPushButton { color: #e67e22; border: 2px solid #e67e22; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #fff9f0; }"
        )

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Close without staging anything.")
        cancel_btn.setStyleSheet(
            "QPushButton { color: #555; border: 2px solid #555; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #f5f5f5; }"
        )

        self.commit_btn.clicked.connect(lambda: self._finish("commit"))
        self.amend_btn.clicked.connect(lambda: self._finish("amend"))
        cancel_btn.clicked.connect(self.reject)

        commit_col = QVBoxLayout()
        commit_col.setSpacing(2)
        commit_col.addWidget(self.commit_btn)
        commit_note = QLabel("(new message)")
        commit_note.setStyleSheet("color: #0055cc; font-size: 11px;")
        commit_note.setAlignment(Qt.AlignCenter)
        commit_col.addWidget(commit_note)

        amend_col = QVBoxLayout()
        amend_col.setSpacing(2)
        amend_col.addWidget(self.amend_btn)
        amend_note = QLabel("(edit HEAD message)")
        amend_note.setStyleSheet("color: #e67e22; font-size: 11px;")
        amend_note.setAlignment(Qt.AlignCenter)
        amend_col.addWidget(amend_note)

        cancel_col = QVBoxLayout()
        cancel_col.setSpacing(2)
        cancel_col.addWidget(cancel_btn)
        cancel_note = QLabel("Cancel")
        cancel_note.setStyleSheet("color: #555; font-size: 11px;")
        cancel_note.setAlignment(Qt.AlignCenter)
        cancel_col.addWidget(cancel_note)

        bot_row.addStretch()
        bot_row.addLayout(commit_col)
        bot_row.addLayout(amend_col)
        bot_row.addLayout(cancel_col)
        layout.addLayout(bot_row)

        self._update_counter()

    def _set_all(self, state):
        for _, hw in self.hunk_widgets:
            hw.set_selected(state)

    def _update_counter(self, _=None):
        total = len(self.hunk_widgets)
        sel = sum(1 for _, hw in self.hunk_widgets if hw.is_selected())
        self.counter_label.setText(f"<b>Selected hunks:</b> {sel}&nbsp;&nbsp;<b>Total:</b> {total}")
        self.counter_label.setTextFormat(Qt.RichText)

    def _finish(self, action):
        self.result_action = action
        self.done(self.CommitResult if action == "commit" else self.AmendResult)

    def selected_indices_by_file(self):
        """Returns {filepath: [kept hunk indices]} from the current checkbox states."""
        idx = 0
        kept = {}
        for f in self.files:
            n = len(self.hunks_by_file.get(f, []))
            kept[f] = [j for j in range(n)
                       if self.hunk_widgets[idx + j][1].is_selected()]
            idx += n
        return kept


class RefineFileSelectDialog(SplitCommitDialog):
    """File-selection dialog for Refine Changes. Reuses SplitCommitDialog layout."""
    def __init__(self, repo_path, sha, files, font_size=10, parent=None):
        super().__init__(repo_path, sha, files, font_size, parent)
        self.setWindowTitle(f"Refine Changes: {sha}")
        self.move_btn.setText("Refine changes in selected file")
        # Update the instruction label
        label = self.main_splitter.widget(1).layout().itemAt(0).widget()
        label.setText("<b>Select a file</b> to refine changes in this commit:")

    def show_file_context_menu(self, pos):
        item = self.file_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=item.text(): self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)

        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=item.text(): open_blame_window(self, text))
        menu.addAction(blame_action)

        refine_action = QAction("Refine changes in selected file", self)
        refine_action.triggered.connect(lambda checked=False, text=item.text(): self.move_file_out(text))
        menu.addAction(refine_action)
        menu.exec(self.file_list.mapToGlobal(pos))


class EditHunkDialog(QDialog):
    """A small lightweight dialog to edit a single diff hunk."""
    def __init__(self, sha, filepath, hunk_index, hunk_text, font_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Hunk")
        self.setMinimumSize(800, 500)
        self.original_hunk = hunk_text
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # Header info
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        
        commit_label = QLabel(f"<b>Commit:</b> <span style='color:{self.parent().colors['header'] if self.parent() and hasattr(self.parent(), 'colors') else '#66d9ef'};'>{sha}</span>&nbsp;&nbsp;changes in {filepath}")
        commit_label.setTextFormat(Qt.RichText)
        header_layout.addWidget(commit_label)
        
        file_label = QLabel(f"<b>File:</b> {filepath}")
        file_label.setTextFormat(Qt.RichText)
        header_layout.addWidget(file_label)
        
        hunk_label = QLabel("Edit the selected hunk below. Only valid patch format should be kept.")
        hunk_label.setStyleSheet("color: #666;")
        header_layout.addWidget(hunk_label)
        
        layout.addLayout(header_layout)
        
        # Editor
        editor_label = QLabel("Hunk (editable)")
        editor_label.setContentsMargins(2, 0, 0, 0)
        layout.addWidget(editor_label)
        
        self.editor = QTextEdit()
        self.editor.setFont(QFont("Courier New", font_size))
        self.editor.setPlainText(hunk_text)
        self.editor.setAcceptRichText(False)
        self.editor.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self.editor)
        
        # Tip/Warning row
        tip_row = QHBoxLayout()
        tip_row.setSpacing(8)
        warning_icon = QLabel("ⓘ")
        warning_icon.setStyleSheet("font-size: 16px; color: #e67e22;")
        warning_text = QLabel("Invalid patch edits may fail to apply.")
        warning_text.setStyleSheet("color: #666; font-size: 11px;")
        tip_row.addStretch()
        tip_row.addWidget(warning_icon)
        tip_row.addWidget(warning_text)
        layout.addLayout(tip_row)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        
        reset_btn = QPushButton("Reset to Original Hunk")
        reset_btn.setMinimumHeight(32)
        reset_btn.clicked.connect(self._reset)
        
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setMinimumHeight(32)
        self.apply_btn.setMinimumWidth(100)
        self.apply_btn.clicked.connect(self.accept)
        self.apply_btn.setStyleSheet("font-weight: bold;")
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(32)
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.apply_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

    def _reset(self):
        self.editor.setPlainText(self.original_hunk)

    def get_hunk_text(self):
        return self.editor.toPlainText()


class DropHunkDialog(QDialog):
    """A small lightweight dialog to confirm dropping a single diff hunk."""
    def __init__(self, sha, filepath, hunk_index, hunk_text, font_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Drop Hunk")
        self.setMinimumSize(800, 500)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # Header info
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        
        main_win = self.parent().parent() if self.parent() else None
        header_color = main_win.colors['header'] if main_win and hasattr(main_win, 'colors') else '#66d9ef'
        
        commit_label = QLabel(f"<b>Commit:</b> <span style='color:{header_color};'>{sha}</span>&nbsp;&nbsp;changes in {filepath}")
        commit_label.setTextFormat(Qt.RichText)
        header_layout.addWidget(commit_label)
        
        file_label = QLabel(f"<b>File:</b> {filepath}")
        file_label.setTextFormat(Qt.RichText)
        header_layout.addWidget(file_label)
        
        msg_label = QLabel("<b>Are you sure you want to drop this hunk from the commit?</b><br><br>This hunk will be removed from the current commit. This action can be undone using app undo/reset mechanisms if needed.")
        msg_label.setStyleSheet("color: #cc2200; font-size: 13px;")
        msg_label.setWordWrap(True)
        msg_label.setTextFormat(Qt.RichText)
        header_layout.addWidget(msg_label)
        
        layout.addLayout(header_layout)
        
        # Viewer
        viewer_label = QLabel("Hunk (read-only)")
        viewer_label.setContentsMargins(2, 0, 0, 0)
        layout.addWidget(viewer_label)
        
        self.viewer = QTextEdit()
        self.viewer.setFont(QFont("Courier New", font_size))
        self.viewer.setPlainText(hunk_text)
        self.viewer.setReadOnly(True)
        self.viewer.setAcceptRichText(False)
        self.viewer.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self.viewer)
        
        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        
        self.drop_btn = QPushButton("Drop Hunk")
        self.drop_btn.setMinimumHeight(32)
        self.drop_btn.setMinimumWidth(100)
        self.drop_btn.clicked.connect(self.accept)
        self.drop_btn.setStyleSheet("color: #cc2200; font-weight: bold; border: 2px solid #cc2200; border-radius: 4px; padding: 5px;")
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(32)
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_row.addStretch()
        btn_row.addWidget(self.drop_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)


class ElidedLabel(QLabel):
    """A QLabel that strictly stays on one line and elides text with '...' when space is constrained."""
    def __init__(self, text, checkbox_to_toggle=None, parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self.checkbox = checkbox_to_toggle
        self.setMinimumWidth(10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMaximumHeight(35) # Ensure it never pushes layout row height
        self._elided_text = text
        
    def setText(self, text):
        if self._full_text != text:
            self._full_text = text
            self._update_elided()
            self.update()
            
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided()

    def _update_elided(self):
        fm = self.fontMetrics()
        self._elided_text = fm.elidedText(self._full_text, Qt.ElideRight, self.width())
        
    def mouseReleaseEvent(self, event):
        if self.checkbox and event.button() == Qt.LeftButton:
            self.checkbox.toggle()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, self._elided_text)


class HunkWidget(QFrame):
    """A framed widget displaying a single diff hunk with a checkbox."""
    apply_hunk_modification = Signal(int)
    drop_hunk = Signal(int)

    def __init__(self, hunk_index, hunk_header, hunk_text, colors, font_size, sha=None, filepath=None, is_only_hunk=False, is_only_file=False, allow_edit=True):
        super().__init__()
        self.hunk_index = hunk_index
        self.hunk_header = hunk_header
        self.original_hunk_header = hunk_header
        self.original_hunk_text = hunk_text
        self.current_hunk_text = hunk_text
        self.colors = colors
        self.font_size = font_size
        self.sha = sha
        self.filepath = filepath
        self.is_only_hunk = is_only_hunk
        self.is_only_file = is_only_file
        self.allow_edit = allow_edit

        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Header row wrapped in a fixed-height widget to prevent expansion from long hunk headers
        self.header_widget = QWidget()
        self.header_widget.setFixedHeight(34)
        header_row = QHBoxLayout(self.header_widget)
        header_widget = self.header_widget  # alias for addWidget below
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        self.checkbox = QCheckBox("")  # Empty text so it takes minimum space and doesn't wrap natively
        self.checkbox.setChecked(True)
        # Prevent it from sizing dynamically
        self.checkbox.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        bold_font = self.checkbox.font()
        bold_font.setBold(True)
        
        # We manually render the text in an ElidedLabel which forwards clicks
        self.hunk_header_label = ElidedLabel(f"Change {hunk_index}   {hunk_header}", self.checkbox)
        self.hunk_header_label.setFont(bold_font)
        
        header_row.addWidget(self.checkbox)
        header_row.addWidget(self.hunk_header_label, stretch=1)
        
        # spacer to push right content

        header_row.addStretch()

        changed = sum(1 for l in hunk_text.splitlines() if l.startswith(('+', '-')) and not l.startswith(('+++', '---')))
        self.line_count_label = QLabel(f"{changed} line{'s' if changed != 1 else ''}")
        self.line_count_label.setStyleSheet("color: gray;")
        header_row.addWidget(self.line_count_label)
        
        if self.allow_edit:
            self.edit_btn = QPushButton("Edit")
            self.edit_btn.setFixedWidth(70)
            self.edit_btn.setFixedHeight(26)
            self.edit_btn.setCursor(Qt.PointingHandCursor)
            self.edit_btn.clicked.connect(self.show_hunk_menu)
            header_row.addWidget(self.edit_btn)
        
        layout.addWidget(header_widget)

        self.diff_view = QTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(QFont("Courier New", font_size))
        self.diff_view.setPlainText(hunk_text)
        self.diff_view.setLineWrapMode(QTextEdit.NoWrap)

        _fm = QFontMetrics(self.diff_view.font())
        _stripped = hunk_text.rstrip('\n')
        _lines = _stripped.count('\n') + 1 if _stripped else 1
        _doc_margin = int(self.diff_view.document().documentMargin())
        _h = (_lines * _fm.lineSpacing()
              + _doc_margin * 2
              + self.diff_view.frameWidth() * 2
              + self.diff_view.contentsMargins().top()
              + self.diff_view.contentsMargins().bottom()
              + 4)
        _final_h = min(max(_h, 50), 320)
        #print(f"[HunkWidget] hunk_index={hunk_index} lines={_lines} lineSpacing={_fm.lineSpacing()} docMargin={_doc_margin} frameW={self.diff_view.frameWidth()} computed_h={_h} final_h={_final_h}")
        self.diff_view.setMinimumHeight(_final_h)
        self.diff_view.setMaximumHeight(_final_h)

        self.highlighter = DiffHighlighter(
            self.diff_view.document(),
            added_color=colors["added"],
            removed_color=colors["removed"],
            header_color=colors["header"]
        )
        layout.addWidget(self.diff_view)

        # Deferred height adjustment: re-measure after the widget is shown and laid out
        QTimer.singleShot(0, self._adjust_diff_view_height)

    def _adjust_diff_view_height(self):
        """Re-measure and fix the diff_view height after the first event loop cycle."""
        doc_h = self.diff_view.document().size().height()
        m = self.diff_view.contentsMargins()
        h = int(doc_h) + self.diff_view.frameWidth() * 2 + m.top() + m.bottom() + 2
        h = min(max(h, 50), 320)

        self.diff_view.setMinimumHeight(h)
        self.diff_view.setMaximumHeight(h)

        # Compute and fix the total HunkWidget height explicitly — updateGeometry() alone
        # is not enough because the scroll area won't shrink already-allocated space.
        lm = self.layout().contentsMargins()
        total_h = (lm.top() + self.header_widget.height() +
                   self.layout().spacing() + h + lm.bottom())
        #print(f"[HunkWidget._adjust] doc_h={doc_h:.1f} diff_h={h} header_h={self.header_widget.height()} → total_hw={total_h} (was {self.height()})")
        self.setFixedHeight(total_h)

        parent = self.parent()
        while parent:
            parent.updateGeometry()
            parent.adjustSize() if hasattr(parent, 'adjustSize') else None
            parent = parent.parent() if not isinstance(parent, QScrollArea) else None

    def show_hunk_menu(self):
        menu = QMenu(self)
        edit_action = menu.addAction("Edit Hunk")
        copy_action = menu.addAction("Copy Hunk")
        menu.addSeparator()
        drop_action = menu.addAction("Drop Hunk")

        # Position menu below the edit button
        action = menu.exec(self.edit_btn.mapToGlobal(self.edit_btn.rect().bottomLeft()))

        if action == edit_action:
            self.open_edit_dialog()
        elif action == copy_action:
            QApplication.clipboard().setText(self.current_hunk_text)
        elif action == drop_action:
            self.open_drop_dialog()

    def open_drop_dialog(self):
        if self.is_only_hunk and self.is_only_file:
            QMessageBox.information(
                self,
                "Cannot Drop Hunk",
                "This is the only hunk in the entire commit.\n\n"
                "Dropping this hunk would effectively remove the whole commit. Please use the regular \"Drop Commit\" feature instead."
            )
            return

        full_text = f"{self.hunk_header}\n{self.current_hunk_text}"
        dlg = DropHunkDialog(self.sha, self.filepath, self.hunk_index, full_text, self.font_size, self)
        if dlg.exec() == QDialog.Accepted:
            self.set_selected(False)
            self.drop_hunk.emit(self.hunk_index)

    def open_edit_dialog(self):
        full_text = f"{self.hunk_header}\n{self.current_hunk_text}"
        dlg = EditHunkDialog(self.sha, self.filepath, self.hunk_index, full_text, self.font_size, self)
        if dlg.exec() == QDialog.Accepted:
            new_full_text = dlg.get_hunk_text()
            if '\n' in new_full_text:
                self.hunk_header, self.current_hunk_text = new_full_text.split('\n', 1)
            else:
                self.hunk_header = new_full_text
                self.current_hunk_text = ""

            # Update the label text to show potentially new header
            self.hunk_header_label.setText(f"Change {self.hunk_index}   {self.hunk_header}")
            self.diff_view.setPlainText(self.current_hunk_text)
            self._update_line_count()

            # Immediately apply the edited hunk — no intermediate MODIFIED state
            self.apply_hunk_modification.emit(self.hunk_index)

    def _update_line_count(self):
        changed = sum(1 for l in self.current_hunk_text.splitlines() if l.startswith(('+', '-')) and not l.startswith(('+++', '---')))
        self.line_count_label.setText(f"{changed} line{'s' if changed != 1 else ''}")

    def get_current_text(self):
        return self.current_hunk_text

    def is_selected(self):
        return self.checkbox.isChecked()

    def set_selected(self, state):
        self.checkbox.setChecked(state)


class RefineChangesDialog(QDialog):
    """Hunk selection dialog for Refine Changes in File feature."""
    apply_hunk_modification = Signal(int)
    drop_hunk = Signal(int)

    def __init__(self, sha, filepath, commit_msg, hunks, font_size=10, parent=None, is_only_file=False):
        """
        hunks: list of (hunk_header_str, hunk_body_str)
        """
        super().__init__(parent)
        self.setWindowTitle(f"Refine/Edit Changes in File: {filepath}")
        self.setMinimumSize(920, 720)
        self.hunk_widgets = []
        self.result_action = None   # 'keep' or 'drop'
        self.kept_indices = []

        main_win = parent if isinstance(parent, QMainWindow) else None
        if main_win and hasattr(main_win, 'current_theme_colors'):
            colors = main_win.current_theme_colors
        else:
            colors = {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef", "separator": "#444444"}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # --- Header ---
        short_msg = commit_msg.split('\n')[0] if commit_msg else ""
        header_html = (
            f"<b>Commit:</b> <span style='color:{colors['header']};'>{sha}</span>"
            f"&nbsp;&nbsp;{short_msg}<br>"
            "<br>"
            f"File: {filepath}<br>"
        )
        header_label = QLabel(header_html)
        header_label.setTextFormat(Qt.RichText)
        header_label.setWordWrap(True)
        layout.addWidget(header_label)

        # --- Select All / Deselect All + counter ---
        top_row = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        deselect_all_btn = QPushButton("Deselect All")
        select_all_btn.setFixedWidth(110)
        deselect_all_btn.setFixedWidth(110)
        select_all_btn.clicked.connect(lambda: self._set_all(True))
        deselect_all_btn.clicked.connect(lambda: self._set_all(False))
        top_row.addWidget(select_all_btn)
        top_row.addWidget(deselect_all_btn)
        top_row.addStretch()
        self.counter_label = QLabel()
        top_row.addWidget(self.counter_label)
        layout.addLayout(top_row)

        # --- Scrollable hunk list ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        hunks_layout = QVBoxLayout(container)
        hunks_layout.setSpacing(8)

        for i, (hdr, body) in enumerate(hunks):
            hw = HunkWidget(i + 1, hdr, body, colors, font_size, sha=sha, filepath=filepath, 
                            is_only_hunk=(len(hunks) == 1), is_only_file=is_only_file)
            hw.apply_hunk_modification.connect(self.apply_hunk_modification.emit)
            hw.drop_hunk.connect(self.drop_hunk.emit)
            hw.checkbox.stateChanged.connect(self._update_counter)
            self.hunk_widgets.append(hw)
            hunks_layout.addWidget(hw)

        hunks_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        self._update_counter()

        # --- Bottom buttons ---
        bot_row = QHBoxLayout()
        bot_row.setSpacing(10)

        self.drop_btn = QPushButton()
        self.drop_btn.setText("Drop Selected Hunks")
        self.drop_btn.setToolTip("Checked hunks will be removed from the commit; unchecked will be kept.")
        self.drop_btn.setStyleSheet(
            "QPushButton { color: #cc2200; border: 2px solid #cc2200; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #fff0ee; }"
        )

        self.keep_btn = QPushButton()
        self.keep_btn.setText("Apply Only Selected Hunks")
        self.keep_btn.setDefault(True)
        self.keep_btn.setToolTip("Checked hunks (including your edits) will remain in the commit; unchecked will be dropped.")
        self.keep_btn.setStyleSheet(
            "QPushButton { color: #0055cc; border: 2px solid #0055cc; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #eef4ff; }"
        )

        self.move_btn = QPushButton()
        self.move_btn.setText("Move Selected Changes to New Commit")
        self.move_btn.setToolTip("Checked hunks will be moved out to a new commit; unchecked will remain.")
        self.move_btn.setStyleSheet(
            "QPushButton { color: #e67e22; border: 2px solid #e67e22; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #fff9f0; }"
        )

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(80)
        cancel_btn.setToolTip("Close the refine window and return to history.")
        cancel_btn.setStyleSheet(
            "QPushButton { color: #555; border: 2px solid #555; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #f5f5f5; }"
        )

        self.drop_btn.clicked.connect(self._on_drop)
        self.keep_btn.clicked.connect(self._on_keep)
        self.move_btn.clicked.connect(self._on_move)
        cancel_btn.clicked.connect(self.reject)

        # Sub-labels
        drop_col = QVBoxLayout()
        drop_col.setSpacing(2)
        drop_col.addWidget(self.drop_btn)
        drop_note = QLabel("(Unchecked will be kept)")
        drop_note.setStyleSheet("color: #cc2200; font-size: 11px;")
        drop_note.setAlignment(Qt.AlignCenter)
        drop_col.addWidget(drop_note)

        keep_col = QVBoxLayout()
        keep_col.setSpacing(2)
        keep_col.addWidget(self.keep_btn)
        keep_note = QLabel("(Unchecked will be dropped)")
        keep_note.setStyleSheet("color: #0055cc; font-size: 11px;")
        keep_note.setAlignment(Qt.AlignCenter)
        keep_col.addWidget(keep_note)

        cancel_col = QVBoxLayout()
        cancel_col.setSpacing(2)
        cancel_col.addWidget(cancel_btn)
        cancel_note = QLabel("Cancel/Done")
        cancel_note.setStyleSheet("color: #555; font-size: 11px;")
        cancel_note.setAlignment(Qt.AlignCenter)
        cancel_col.addWidget(cancel_note)

        move_col = QVBoxLayout()
        move_col.setSpacing(2)
        move_col.addWidget(self.move_btn)
        move_note = QLabel("(Unchecked will remain in current commit)")
        move_note.setStyleSheet("color: #e67e22; font-size: 11px;")
        move_note.setAlignment(Qt.AlignCenter)
        move_col.addWidget(move_note)

        bot_row.addLayout(drop_col)
        bot_row.addLayout(keep_col)
        bot_row.addLayout(move_col)
        bot_row.addLayout(cancel_col)
        
        layout.addLayout(bot_row)
        
        # --- Tip label removed as requested ---

    def _update_counter(self, _=None):
        total = len(self.hunk_widgets)
        sel = sum(1 for hw in self.hunk_widgets if hw.is_selected())
        drop = total - sel
        self.counter_label.setText(
            f"<b>Selected:</b> {sel}&nbsp;&nbsp;<b>Un-Selected:</b> {drop}&nbsp;&nbsp;<b>Total:</b> {total}"
        )
        self.counter_label.setTextFormat(Qt.RichText)

    def _set_all(self, state):
        for hw in self.hunk_widgets:
            hw.set_selected(state)

    def _warn_single_hunk(self, action_label):
        """Show a warning when the file has only one hunk. Returns True to proceed."""
        if len(self.hunk_widgets) == 1:
            reply = QMessageBox.warning(
                self,
                "Single Change Warning",
                f"This file has only <b>one change (hunk)</b>.<br><br>"
                f"<b>{action_label}</b> on a single hunk will affect the <b>entire file change</b>.<br>"
                "Are you sure you want to continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            return reply == QMessageBox.Yes
        return True

    def _on_drop(self):
        if not self._warn_single_hunk("Drop Selected"):
            return
        # Kept = unchecked
        self.kept_indices = [i for i, hw in enumerate(self.hunk_widgets) if not hw.is_selected()]
        self.result_action = "keep"   # we reconstruct a patch with only the kept ones
        self.accept()

    def _on_keep(self):
        if not self._warn_single_hunk("Apply Selected Changes"):
            return
        # Kept = checked
        self.kept_indices = [i for i, hw in enumerate(self.hunk_widgets) if hw.is_selected()]
        self.result_action = "keep"
        self.accept()

    def _on_move(self):
        if not self._warn_single_hunk("Move Selected Changes to New Commit"):
            return
        # Moved = checked, Kept = unchecked
        self.moved_indices = [i for i, hw in enumerate(self.hunk_widgets) if hw.is_selected()]
        self.kept_indices = [i for i, hw in enumerate(self.hunk_widgets) if not hw.is_selected()]
        self.result_action = "move"
        self.accept()

    def get_hunk_data(self):
        """Returns a list of (hunk_header, hunk_text) for all hunks."""
        return [(hw.hunk_header, hw.get_current_text()) for hw in self.hunk_widgets]

    def reject(self):
        super().reject()

class StashNoticeDialog(QDialog):
    """Warning dialog for a missing/not-at-head managed stash. Offers a 'Copy SHA to
    clipboard' button that does NOT close the dialog, and an OK button to dismiss."""
    ManualPopResult = 2

    def __init__(self, text, sha, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Managed Stash")
        self.setMinimumWidth(480)
        self.setModal(True)

        short_sha = sha[:8]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)

        copy_btn = QPushButton("Copy SHA to clipboard")
        copy_btn.setToolTip("Copy the stash SHA to the clipboard.")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(short_sha))

        manual_btn = QPushButton("Its OK, I stash pop-ed it myself manually")
        manual_btn.setToolTip("Mark this stash as manually handled and stop tracking it.")
        manual_btn.clicked.connect(lambda: self.done(self.ManualPopResult))

        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(manual_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)


class BrowseBranchDialog(QDialog):
    """Dialog to pick a branch name and how many recent commits to show in the
    read-only branch browser. Returns branch name and an integer commit count."""

    def __init__(self, repo_path, parent=None, default_limit=50):
        super().__init__(parent)
        self.repo_path = repo_path
        self.setWindowTitle("Browse Branch")
        self.setMinimumWidth(380)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        branch_label = QLabel("Branch name:")
        layout.addWidget(branch_label)

        self.branch_combo = QComboBox()
        self.branch_combo.setEditable(True)
        self.branch_combo.addItem("")
        self.branch_combo.addItems(get_branch_names(self.repo_path))
        if self.branch_combo.lineEdit():
            self.branch_combo.lineEdit().setPlaceholderText("e.g. feature/login, dev, release/1.0")
        self.branch_combo.setToolTip("Existing branches are listed; you can also type a branch that hasn't been fetched yet.")
        layout.addWidget(self.branch_combo)

        limit_label = QLabel("Number of commits to show:")
        layout.addWidget(limit_label)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 1000000)
        self.limit_spin.setValue(default_limit)
        self.limit_spin.setToolTip("How many most-recent commits to load into the browse window.")
        layout.addWidget(self.limit_spin)

        open_btn = QPushButton("Open Browser")
        open_btn.setDefault(True)
        open_btn.setToolTip("Open a read-only viewer of this branch's history.")
        open_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(open_btn)
        layout.addLayout(btn_layout)

        self.branch_combo.setFocus()

    @property
    def branch_name(self):
        return self.branch_combo.currentText().strip()

    @property
    def commit_limit(self):
        return self.limit_spin.value()


class BrowseCommitLogDialog(QDialog):
    """Dialog to pick a commit and how many recent commits to show in the
    read-only commit-log browser. Returns a commit SHA and an integer commit count."""

    def __init__(self, repo_path, parent=None, default_limit=50):
        super().__init__(parent)
        self.repo_path = repo_path
        self.setWindowTitle("Browse Log of a Commit")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        commit_label = QLabel("Commit SHA or ref:")
        layout.addWidget(commit_label)

        self.commit_edit = QLineEdit()
        self.commit_edit.setPlaceholderText("e.g. c9bbbc4, HEAD, master")
        self.commit_edit.setToolTip("A commit SHA, short SHA, or a ref that resolves to a commit.")
        layout.addWidget(self.commit_edit)

        limit_label = QLabel("Number of commits to show:")
        layout.addWidget(limit_label)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 1000000)
        self.limit_spin.setValue(default_limit)
        self.limit_spin.setToolTip("How many most-recent commits to load into the browse window.")
        layout.addWidget(self.limit_spin)

        open_btn = QPushButton("Open Browser")
        open_btn.setDefault(True)
        open_btn.setToolTip("Open a read-only viewer of this commit's history.")
        open_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(open_btn)
        layout.addLayout(btn_layout)

        self.commit_edit.setFocus()

    @property
    def commit_id(self):
        return self.commit_edit.text().strip()

    @property
    def commit_limit(self):
        return self.limit_spin.value()


class BrowseFileLogDialog(QDialog):
    """Dialog to pick a file and how many recent commits to show in the
    read-only file-log browser. Returns a repo-relative file path and an
    integer commit count."""

    def __init__(self, repo_path, parent=None, default_limit=50):
        super().__init__(parent)
        self.repo_path = repo_path
        self.setWindowTitle("Browse File Log")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        file_label = QLabel("File path (repo-relative):")
        layout.addWidget(file_label)

        file_row = QHBoxLayout()
        file_row.setSpacing(6)
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("e.g. lib/app_window.py, README.md")
        self.file_edit.setToolTip("A path relative to the repository root; use Browse... to pick a file.")
        file_row.addWidget(self.file_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Pick a file in the repository.")
        browse_btn.clicked.connect(self._pick_file)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        limit_label = QLabel("Number of commits to show:")
        layout.addWidget(limit_label)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 1000000)
        self.limit_spin.setValue(default_limit)
        self.limit_spin.setToolTip("How many most-recent commits touching the file to load.")
        layout.addWidget(self.limit_spin)

        open_btn = QPushButton("Open Browser")
        open_btn.setDefault(True)
        open_btn.setToolTip("Open a read-only viewer of this file's history.")
        open_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(open_btn)
        layout.addLayout(btn_layout)

        self.file_edit.setFocus()

    def _pick_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select file to browse", self.repo_path)
        if file_path:
            rel = os.path.relpath(file_path, self.repo_path)
            if rel.startswith(".."):
                QMessageBox.warning(self, "Outside repository",
                                    "Please select a file inside the repository.")
                return
            self.file_edit.setText(rel.replace(os.sep, "/"))

    @property
    def file_path(self):
        return self.file_edit.text().strip()

    @property
    def commit_limit(self):
        return self.limit_spin.value()


class ApplyPatchDialog(QDialog):
    """Dialog to pick a patch file and choose whether to commit the changes or
    leave them unstaged in the working tree."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Apply Patch")
        self.setMinimumWidth(440)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        patch_label = QLabel("Patch file:")
        layout.addWidget(patch_label)

        patch_row = QHBoxLayout()
        patch_row.setSpacing(6)
        self.patch_edit = QLineEdit()
        self.patch_edit.setPlaceholderText("e.g. /path/to/change.patch")
        self.patch_edit.setToolTip("A unified-diff or format-patch file to apply.")
        patch_row.addWidget(self.patch_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Pick a patch file.")
        browse_btn.clicked.connect(self._pick_patch_file)
        patch_row.addWidget(browse_btn)
        layout.addLayout(patch_row)

        self.commit_cb = QCheckBox("Create a commit from the patch")
        self.commit_cb.setChecked(False)
        self.commit_cb.setToolTip("If checked, the changes are staged and committed using the patch's own message. "
                                  "If unchecked, the changes are left unstaged in the working tree.")
        layout.addWidget(self.commit_cb)

        apply_btn = QPushButton("Apply Patch")
        apply_btn.setDefault(True)
        apply_btn.setToolTip("Apply the selected patch to the repository.")
        apply_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(apply_btn)
        layout.addLayout(btn_layout)

        self.patch_edit.setFocus()

    def _pick_patch_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select patch file",
                                                   filter="Patch files (*.patch *.diff);;All files (*)")
        if file_path:
            self.patch_edit.setText(file_path)

    @property
    def patch_path(self):
        return self.patch_edit.text().strip()

    @property
    def commit_wanted(self):
        return self.commit_cb.isChecked()


class TagCommitDialog(QDialog):
    """Dialog to create a git tag (lightweight or annotated) on a commit."""

    def __init__(self, sha, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tag Commit")
        self.setMinimumWidth(440)
        self.setMinimumHeight(260)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        sha_label = QLabel(f"Tagging commit: {sha[:12]}")
        sha_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(sha_label)

        tag_label = QLabel("Tag name:")
        layout.addWidget(tag_label)

        self.tag_edit = QLineEdit()
        self.tag_edit.setPlaceholderText("e.g. v1.2.3")
        self.tag_edit.setToolTip("Name for the git tag (e.g. v1.0.0, release-20240101).")
        layout.addWidget(self.tag_edit)

        self.annotate_cb = QCheckBox("Annotate")
        self.annotate_cb.setChecked(False)
        self.annotate_cb.setToolTip("If checked, creates an annotated tag with a message.")
        self.annotate_cb.toggled.connect(self._on_annotate_toggled)
        layout.addWidget(self.annotate_cb)

        self.msg_edit = QTextEdit()
        self.msg_edit.setPlaceholderText("Annotation message (optional)")
        self.msg_edit.setToolTip("Message for an annotated tag. Ignored if 'Annotate' is unchecked.")
        self.msg_edit.setEnabled(False)
        self.msg_edit.setMinimumHeight(80)
        layout.addWidget(self.msg_edit)

        tag_btn = QPushButton("Create Tag")
        tag_btn.setDefault(True)
        tag_btn.setToolTip("Create the git tag.")
        tag_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(tag_btn)
        layout.addLayout(btn_layout)

        self.tag_edit.setFocus()

    def _on_annotate_toggled(self, checked):
        self.msg_edit.setEnabled(checked)
        if checked:
            self.msg_edit.setFocus()

    @property
    def tag_name(self):
        return self.tag_edit.text().strip()

    @property
    def annotated(self):
        return self.annotate_cb.isChecked()

    @property
    def message(self):
        return self.msg_edit.toPlainText().strip()


class MergeBaseDialog(QDialog):
    """Dialog to pick the branch to compare against the current branch's merge-base.
    Shows the current branch first, then a "VS" label, then a branch pulldown."""

    def __init__(self, repo_path, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.setWindowTitle("Find Merge-base")
        self.setMinimumWidth(380)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        cur_label = QLabel("Current branch:")
        layout.addWidget(cur_label)

        current = get_current_branch(repo_path) or "HEAD (detached)"
        self.current_branch_label = QLabel(current)
        cur_font = self.current_branch_label.font()
        cur_font.setBold(True)
        self.current_branch_label.setFont(cur_font)
        layout.addWidget(self.current_branch_label)

        vs_label = QLabel("VS")
        vs_label.setStyleSheet("font-size: 13px; color: gray;")
        layout.addWidget(vs_label)

        other_label = QLabel("Compare with branch:")
        layout.addWidget(other_label)

        self.branch_combo = QComboBox()
        self.branch_combo.setEditable(True)
        self.branch_combo.addItem("")
        self.branch_combo.addItems(get_branch_names(repo_path))
        if self.branch_combo.lineEdit():
            self.branch_combo.lineEdit().setPlaceholderText("e.g. origin/main, master")
        self.branch_combo.setToolTip("Pick the branch to find the merge-base against.")
        layout.addWidget(self.branch_combo)

        find_btn = QPushButton("Find")
        find_btn.setDefault(True)
        find_btn.setToolTip("Find the merge-base of the current branch and the selected branch.")
        find_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(find_btn)
        layout.addLayout(btn_layout)

        self.branch_combo.setFocus()

    @property
    def branch_name(self):
        return self.branch_combo.currentText().strip()


class MergeBaseResultDialog(QDialog):
    """Shows the computed merge-base SHA with a copy-to-clipboard button and an
    OK button (styled like StashNoticeDialog)."""

    def __init__(self, text, sha, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Merge-base Found")
        self.setMinimumWidth(480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(label)

        copy_btn = QPushButton("Copy SHA to clipboard")
        copy_btn.setToolTip("Copy the full merge-base SHA to the clipboard.")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(sha))

        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

