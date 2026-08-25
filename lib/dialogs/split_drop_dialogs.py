
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
    QPushButton,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QCheckBox,
)
# pyrefly: ignore [missing-import]
from PySide6.QtCore import (
    Qt,
    QTimer,
)
# pyrefly: ignore [missing-import]
from PySide6.QtGui import (
    QFont,
    QAction,
    QShortcut,
    QKeySequence,
)

from lib.git_helpers import (
    get_file_diff_only_in_commit,
    get_commit_metadata_and_message,
    get_commit_file_stats,
)
from lib.widgets import (
    DiffHighlighter,
    DiffSearchBar,
    DiffView,
    StatsItemDelegate,
)
from .hunk_file_dialogs import open_blame_window
from .diff_viewer_dialog import DiffViewerDialog
from lib.app_window.helpers import add_open_with_system_default_action


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
        add_open_with_system_default_action(menu, item.text(), self)
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=item.text(): open_blame_window(self, text))
        menu.addAction(blame_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=item.text(): self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)

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
        add_open_with_system_default_action(menu, item.text(), self)
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=item.text(): open_blame_window(self, text))
        menu.addAction(blame_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=item.text(): self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)

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
        add_open_with_system_default_action(menu, item.text(), self)
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=item.text(): open_blame_window(self, text))
        menu.addAction(blame_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=item.text(): self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)

        refine_action = QAction("Refine changes in selected file", self)
        refine_action.triggered.connect(lambda checked=False, text=item.text(): self.move_file_out(text))
        menu.addAction(refine_action)
        menu.exec(self.file_list.mapToGlobal(pos))
