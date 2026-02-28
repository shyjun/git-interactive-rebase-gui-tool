
if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py")
    sys.exit(1)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QListWidget, QVBoxLayout, 
    QWidget, QMessageBox, QListWidgetItem, QMenu, QDialog,
    QTextEdit, QPushButton, QHBoxLayout, QLabel, QRadioButton,
    QLineEdit, QSplitter, QInputDialog
)
from PySide6.QtCore import Qt, QSize, QSettings
from PySide6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QAction, QShortcut, QKeySequence

from lib.git_helpers import get_file_diff_in_commit

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
        
        # Diff View
        self.diff_view = QTextEdit()
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
            colors = {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef"}
        self.colors = colors

        layout = QVBoxLayout(self)

        # Header
        header = QLabel(f"<b>Select a file</b> to preview its changes in commit <b>{sha}</b>")
        header.setTextFormat(Qt.RichText)
        layout.addWidget(header)

        # Splitter: file list (top) + diff view (bottom)
        splitter = QSplitter(Qt.Vertical)

        # File list
        self.file_list = QListWidget()
        self.file_list.setFont(QFont("Courier New", font_size))
        for f in files:
            self.file_list.addItem(f)
        self.file_list.currentTextChanged.connect(self.on_file_selected)
        splitter.addWidget(self.file_list)

        # Diff view
        self.diff_view = QTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(QFont("Courier New", font_size))
        self.diff_view.setPlaceholderText("Select a file above to view its diff...")
        self.highlighter = DiffHighlighter(
            self.diff_view.document(),
            added_color=colors["added"],
            removed_color=colors["removed"],
            header_color=colors["header"]
        )
        splitter.addWidget(self.diff_view)
        splitter.setSizes([150, 400])
        layout.addWidget(splitter)

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

    def on_file_selected(self, filepath):
        if not filepath:
            return
        self.selected_file = filepath
        self.move_btn.setEnabled(True)
        try:
            diff = get_file_diff_in_commit(self.repo_path, self.sha, filepath)
            self.diff_view.setPlainText(diff)
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
        
        btn_layout.addWidget(self.apply_btn)
        btn_layout.addWidget(self.discard_btn)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)

    def get_message(self):
        return self.message_edit.toPlainText().strip()

class SquashDialog(QDialog):
    """Dialog for choosing and editing commit message during squash."""
    def __init__(self, sha1, msg1, sha2, msg2, font_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Interactive Squash / Merge")
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



