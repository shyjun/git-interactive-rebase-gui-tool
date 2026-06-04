
if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py (git-interactive-rebase-gui-tool)")
    sys.exit(1)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QListWidget, QVBoxLayout,
    QWidget, QMessageBox, QListWidgetItem, QMenu, QDialog,
    QTextEdit, QPlainTextEdit, QPushButton, QHBoxLayout, QLabel, QRadioButton,
    QLineEdit, QSplitter, QInputDialog, QProgressBar, QScrollArea,
    QFrame, QCheckBox, QSizePolicy
)
# pyrefly: ignore [missing-import]
from PySide6.QtCore import Qt, QSize, QSettings, QTimer, Signal
# pyrefly: ignore [missing-import]
from PySide6.QtGui import QFont, QFontMetrics, QSyntaxHighlighter, QTextCharFormat, QColor, QAction, QShortcut, QKeySequence, QPainter, QTextFormat, QTextBlockFormat, QTextCursor

from lib.git_helpers import (
    get_file_diff_in_commit, get_file_diff_only_in_commit,
    get_full_commit_message, get_commit_metadata, get_revert_commit_message
)

class DiffHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None, added_color="#a6e22e", removed_color="#f92672", header_color="#66d9ef"):
        super().__init__(parent)
        self.added_format = QTextCharFormat()
        self.added_format.setForeground(QColor(added_color))
        
        self.removed_format = QTextCharFormat()
        self.removed_format.setForeground(QColor(removed_color))
        
        self.header_format = QTextCharFormat()
        self.header_format.setForeground(QColor(header_color))

    def highlightBlock(self, text):
        if text.startswith('+') and not text.startswith('+++'):
            self.setFormat(0, len(text), self.added_format)
        elif text.startswith('-') and not text.startswith('---'):
            self.setFormat(0, len(text), self.removed_format)
        elif text.startswith('commit') or text.startswith('diff') or text.startswith('index'):
            self.setFormat(0, len(text), self.header_format)

class DiffView(QPlainTextEdit):
    """A QPlainTextEdit that draws subtle 1px separators before file diffs."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.separator_color = QColor("#CCCCCC")
        self.draw_separators = True
        
    def set_separator_color(self, color):
        self.separator_color = QColor(color)
        self.viewport().update()
        
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.draw_separators:
            return
            
        painter = QPainter(self.viewport())
        # Disable antialiasing for sharp 1px lines
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.Antialiasing, False)
        
        block = self.firstVisibleBlock()
        # Find the top of the first visible block in viewport coordinates
        offset = self.contentOffset()
        top = int(offset.y())
        
        while block.isValid():
            # If the block is below the visible area, we're done
            if top > self.viewport().rect().bottom():
                break
            
            block_height = int(self.blockBoundingRect(block).height())
            bottom = top + block_height
            
            # If the block is at least partially visible
            if bottom >= 0:
                text = block.text().strip()
                # Detection: An empty block followed by a 'diff --git' block
                # was injected by git_helpers.py specifically for our separator.
                if text == "" and block.next().isValid():
                    next_text = block.next().text().strip()
                    if next_text.startswith('diff --git '):
                        # Center the line in this empty block height
                        # Use 2px thickness for better visibility
                        y = int(top + (block_height - 2) / 2)
                        painter.fillRect(0, y, self.viewport().width(), 2, self.separator_color)
            
            # Move to the top of the next block
            top = bottom
            block = block.next()

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
        
        self.layout.addWidget(self.diff_view)
        
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

        # Fetch commit details
        try:
            meta = get_commit_metadata(repo_path, sha)
            msg = get_full_commit_message(repo_path, sha)
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
            self.file_list.addItem(f)
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
        diff_layout.addWidget(self.diff_view)
        
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

        # Fetch commit details
        try:
            meta = get_commit_metadata(repo_path, sha)
            msg = get_full_commit_message(repo_path, sha)
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
            self.file_list.addItem(f)
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
        diff_layout.addWidget(self.diff_view)
        
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

        drop_action = QAction("Drop file changes from this commit", self)
        drop_action.triggered.connect(lambda checked=False, text=item.text(): self.drop_file(text))
        menu.addAction(drop_action)

        menu.exec(self.file_list.mapToGlobal(pos))

    def drop_file(self, filepath):
        self.selected_file = filepath
        self.accept()

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

        # Fetch commit details
        try:
            meta = get_commit_metadata(repo_path, sha)
            msg = get_full_commit_message(repo_path, sha)
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
        for f in files:
            self.file_list.addItem(f)
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
        diff_layout.addWidget(self.diff_view)
        
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
        menu = QMenu(self)
        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=item.text(): self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)
        
        is_only_file = self.file_list.count() <= 1

        move_action = QAction("Move file changes out of this commit", self)
        move_action.triggered.connect(lambda checked=False, text=item.text(): self.move_file_out(text))
        move_action.setEnabled(not is_only_file)
        menu.addAction(move_action)

        drop_action = QAction("Drop file changes from this commit", self)
        drop_action.triggered.connect(lambda checked=False, text=item.text(): self.drop_file(text))
        drop_action.setEnabled(not is_only_file)
        menu.addAction(drop_action)

        menu.addSeparator()
        refine_action = QAction("Refine/Edit changes in selected file", self)
        refine_action.triggered.connect(lambda checked=False, text=item.text(): self.refine_file(text))
        menu.addAction(refine_action)

        menu.exec(self.file_list.mapToGlobal(pos))

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
            diff = get_file_diff_only_in_commit(self.repo_path, self.sha, filepath)
            self.diff_view.setPlainText(diff)
            self.diff_view.set_separator_color(self.colors.get("separator", "#444444"))
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
    def __init__(self, sha1, msg1, sha2, msg2, font_size=10, parent=None):
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

    def __init__(self, num_files, parent=None):
        super().__init__(parent)
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
        self.label.setStyleSheet("font-size: 13px;")
        layout.addWidget(self.label)
        
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(10)
        
        self.stash_btn = QPushButton("Stash and proceed to app")
        
        commit_each_text = f"Commit each file changes separately and start app ({num_files} files modified, {num_files} commits)"
        self.commit_each_btn = QPushButton(commit_each_text)
        
        bulk_commit_text = f"Commit all unsaved changes to a single 'bulk' commit (Number of modified files: {num_files})"
        self.bulk_commit_btn = QPushButton(bulk_commit_text)
        
        self.exit_btn = QPushButton("Exit")
        
        # Style buttons a bit
        for btn in [self.stash_btn, self.commit_each_btn, self.bulk_commit_btn, self.exit_btn]:
            btn.setMinimumHeight(35)
        
        self.stash_btn.clicked.connect(self.accept)
        self.commit_each_btn.clicked.connect(lambda: self.done(self.CommitEachResult))
        self.bulk_commit_btn.clicked.connect(lambda: self.done(self.BulkCommitResult))
        self.exit_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.stash_btn)
        btn_layout.addWidget(self.commit_each_btn)
        btn_layout.addWidget(self.bulk_commit_btn)
        btn_layout.addWidget(self.exit_btn)
        
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
        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=item.text(): self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)
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

    def __init__(self, hunk_index, hunk_header, hunk_text, colors, font_size, sha=None, filepath=None, is_only_hunk=False, is_only_file=False):
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

