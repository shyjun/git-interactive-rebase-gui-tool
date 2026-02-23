#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
import tempfile
import stat
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QListWidget, QVBoxLayout, 
    QWidget, QMessageBox, QListWidgetItem, QMenu, QDialog,
    QTextEdit, QPushButton, QHBoxLayout, QLabel, QRadioButton,
    QLineEdit
)
from PySide6.QtCore import Qt, QSize, QSettings
from PySide6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QAction, QShortcut, QKeySequence

def get_git_history(repo_path, commit_sha):
    """Fetches git history from HEAD down to commit_sha inclusive."""
    try:
        # Check if commit_sha has a parent
        has_parent = False
        try:
            subprocess.run(["git", "rev-parse", f"{commit_sha}^"], 
                           cwd=repo_path, check=True, capture_output=True)
            has_parent = True
        except:
            has_parent = False

        if has_parent:
            # Inclusive range: parent..HEAD shows commit_sha and its descendants
            cmd = ["git", "log", f"{commit_sha}^..HEAD", "--oneline"]
        else:
            # Root commit case: show everything reachable from HEAD
            cmd = ["git", "log", "HEAD", "--oneline"]
        
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return [line for line in result.stdout.strip().split('\n') if line.strip()]
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch git history: {e.stderr}")

def get_current_branch(repo_path):
    """Fetches current branch name."""
    try:
        cmd = ["git", "branch", "--show-current"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return result.stdout.strip() or "DETACHED"
    except:
        return "Unknown"

def get_head_sha(repo_path):
    """Fetches current HEAD SHA (short)."""
    try:
        cmd = ["git", "rev-parse", "--short", "HEAD"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except:
        return "Unknown"

def get_commit_diff(repo_path, commit_sha):
    """Fetches the diff for a specific commit."""
    try:
        cmd = ["git", "show", commit_sha, "--format="]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch diff: {e.stderr}")

def get_full_commit_message(repo_path, commit_sha):
    """Fetches the full (multi-line) commit message."""
    try:
        cmd = ["git", "log", "-1", "--format=%B", commit_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch commit message: {e.stderr}")

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

class ViewCommitDialog(DiffViewerDialog):
    def __init__(self, sha, diff_text, font_size=10, parent=None):
        super().__init__(f"View Commit: {sha}", sha, diff_text, font_size, parent)

    def setup_header(self, sha):
        label = QLabel(f"Showing changes for commit: <b>{sha}</b>")
        self.layout.addWidget(label)

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

class CommitListWidget(QListWidget):
    """Subclassed QListWidget to handle Drag & Drop move confirmation."""
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.InternalMove)

    def dropEvent(self, event):
        old_row = self.currentRow()
        super().dropEvent(event)
        new_row = self.currentRow()
        
        if old_row != new_row:
            item = self.item(new_row)
            sha = item.text().split()[0]
            
            # Ask for confirmation
            reply = QMessageBox.question(
                self, 
                "Confirm Move",
                f"Do you want to move commit <b>{sha}</b> to this new position?",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                # Capture all SHAs in current list order
                shas = []
                for i in range(self.count()):
                    shas.append(self.item(i).text().split()[0])
                # Call real move functionality
                self.main_window.perform_move(shas)
            else:
                # If No, reload the original history to undo the visual move
                self.main_window.load_history()

class GitHistoryApp(QMainWindow):
    def __init__(self, repo_path, commit_sha):
        super().__init__()
        self.repo_path = repo_path
        self.commit_sha = commit_sha
        
        # Persistence
        self.settings = QSettings("shyjun", "GitInteractiveRebase")
        self.current_font_size = int(self.settings.value("font_size", 10))
        
        self.setWindowTitle(f"git_interactive_rebase.py : branch=..., HEAD=..., path={self.repo_path}") # Temporary name until load_history updates it
        self.resize(1000, 800)

        self.setup_ui()
        self.load_settings()
        self.load_history()

    def load_settings(self):
        """Loads persistent user settings like font size and theme."""
        # Font Size
        size = self.settings.value("font_size", 10, type=int)
        self.current_font_size = size
        self.update_font()
        
        # Theme
        theme = self.settings.value("theme", "light", type=str)
        if theme == "dark":
            self.dark_radio.setChecked(True)
        else:
            self.light_radio.setChecked(True)
        self.apply_theme(theme)

    def update_window_title(self):
        """Updates window title with branch, HEAD, and path."""
        branch = get_current_branch(self.repo_path)
        head_sha = get_head_sha(self.repo_path)
        title = f"git_interactive_rebase.py : branch={branch}, HEAD={head_sha}, path={self.repo_path}"
        self.setWindowTitle(title)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Use our custom list widget
        self.list_widget = CommitListWidget(self)
        self.update_font()
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        
        # Search / Filter Bar
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search commits (SHA or Message)...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumHeight(35)
        self.search_edit.textChanged.connect(self.filter_commits)
        layout.addWidget(self.search_edit)

        layout.addWidget(self.list_widget)
        self.list_widget.itemDoubleClicked.connect(self.view_commit)
        self.update_window_title()

        # Bottom Control Bar
        controls_layout = QHBoxLayout()
        
        self.zoom_in_btn = QPushButton("Zoom In (+)")
        self.zoom_out_btn = QPushButton("Zoom Out (-)")
        self.refresh_btn = QPushButton("Refresh")
        # Theme controls
        self.dark_radio = QRadioButton("Dark Theme")
        self.light_radio = QRadioButton("Light Theme")
        self.dark_radio.toggled.connect(lambda: self.on_theme_toggled())
        self.light_radio.toggled.connect(lambda: self.on_theme_toggled())
        
        controls_layout.addWidget(QLabel("Theme:"))
        controls_layout.addWidget(self.dark_radio)
        controls_layout.addWidget(self.light_radio)
        controls_layout.addSpacing(20)

        self.exit_btn = QPushButton("Exit")
        
        for btn in [self.zoom_in_btn, self.zoom_out_btn, self.refresh_btn, self.exit_btn]:
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(120)

        self.zoom_in_btn.clicked.connect(self.handle_zoom_in)
        self.zoom_out_btn.clicked.connect(self.handle_zoom_out)
        self.refresh_btn.clicked.connect(self.load_history)
        self.exit_btn.clicked.connect(self.close)

        controls_layout.addWidget(self.zoom_in_btn)
        controls_layout.addWidget(self.zoom_out_btn)
        controls_layout.addStretch() # Space between zoom and refresh
        controls_layout.addWidget(self.refresh_btn)
        controls_layout.addWidget(self.exit_btn)
        
        layout.addLayout(controls_layout)

        # Keyboard Shortcuts
        self.slash_shortcut = QShortcut(QKeySequence("/"), self)
        self.slash_shortcut.activated.connect(self.handle_slash_shortcut)
        
        self.esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.esc_shortcut.activated.connect(self.handle_esc_shortcut)

    def handle_slash_shortcut(self):
        """Focus search bar when / is pressed."""
        if not self.search_edit.hasFocus():
            self.search_edit.setFocus()
            self.search_edit.selectAll()

    def handle_esc_shortcut(self):
        """Clear filter and focus when Esc is pressed."""
        if self.search_edit.text() or self.search_edit.hasFocus():
            self.search_edit.clear()
            self.search_edit.clearFocus()
            self.list_widget.setFocus()


    def filter_commits(self, text):
        """Live-filters the commits in the list based on search text."""
        search_term = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            # Match against SHA or Message
            item_text = item.text().lower()
            if search_term in item_text:
                item.setHidden(False)
            else:
                item.setHidden(True)

    def handle_zoom_in(self):
        self.current_font_size += 1
        self.update_font()

    def handle_zoom_out(self):
        if self.current_font_size > 6:
            self.current_font_size -= 1
            self.update_font()

    def on_theme_toggled(self):
        theme = "dark" if self.dark_radio.isChecked() else "light"
        self.apply_theme(theme)
        self.settings.setValue("theme", theme)

    def apply_theme(self, theme_name):
        """Applies a theme to the entire application globally."""
        if theme_name == "dark":
            # VS Code Dark+ inspired palette
            self.current_theme_colors = {
                "added": "#4ec9b0",   # Soft teal/green
                "removed": "#f48771", # Soft coral/red
                "header": "#569cd6",  # VS Code blue
                "bg": "#1e1e1e",      # Main background
                "fg": "#cccccc",      # Standard text
                "accent": "#007acc"   # VS Code accent blue
            }
            qss = """
                QMainWindow, QWidget {
                    background-color: #1e1e1e;
                    color: #cccccc;
                }
                QListWidget {
                    background-color: #252526;
                    border: 1px solid #3c3c3c;
                    border-radius: 8px;
                    padding: 5px;
                    color: #cccccc;
                }
                QListWidget::item { 
                    padding: 8px; 
                    border-bottom: 1px solid #333333; 
                }
                QListWidget::item:selected {
                    background-color: #37373d;
                    color: #ffffff;
                }
                QPushButton {
                    background-color: #333333;
                    color: #cccccc;
                    border: 1px solid #3c3c3c;
                    padding: 8px 15px;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #444444;
                }
                QPushButton:pressed {
                    background-color: #007acc;
                    color: white;
                }
                QPushButton.dialog-btn {
                    background-color: #333333;
                    border: 1px solid #444444;
                }
                QPushButton.dialog-btn:hover {
                    background-color: #007acc;
                    color: white;
                }
                QLabel {
                    font-weight: bold;
                }
                QDialog {
                    background-color: #1e1e1e;
                }
                QTextEdit {
                    background-color: #1e1e1e;
                    color: #d4d4d4;
                    border: 1px solid #3c3c3c;
                    border-radius: 4px;
                }
                QScrollBar:vertical {
                    background: #1e1e1e;
                    width: 12px;
                    margin: 0px;
                }
                QScrollBar::handle:vertical {
                    background: #37373d;
                    min-height: 20px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #4f4f4f;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """
        else:
            self.current_theme_colors = {
                "added": "#228b22",  # Darker green for light bg
                "removed": "#b22222", # Darker red for light bg
                "header": "#00008b", # Darker blue for light bg
                "bg": "#f5f5f7",
                "fg": "#333333",
                "accent": "#007aff"
            }
            qss = """
                QMainWindow, QWidget {
                    background-color: #f5f5f7;
                    color: #333;
                }
                QListWidget {
                    background-color: #ffffff;
                    border: 1px solid #ddd;
                    border-radius: 8px;
                    padding: 5px;
                    color: #333;
                }
                QListWidget::item { 
                    padding: 8px; 
                    border-bottom: 1px solid #eee; 
                }
                QListWidget::item:selected {
                    background-color: #007aff;
                    color: white;
                }
                QPushButton {
                    background-color: #ffffff;
                    color: #333;
                    border: 1px solid #ccc;
                    padding: 8px 15px;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #f0f0f0;
                }
                QPushButton:pressed {
                    background-color: #d0d0d0;
                }
                QPushButton.dialog-btn {
                    background-color: #e1e1e1;
                    border: 1px solid #bbb;
                }
                QPushButton.dialog-btn:hover {
                    background-color: #007aff;
                    color: white;
                }
                QLabel {
                    font-weight: bold;
                    color: #333;
                }
                QDialog {
                    background-color: #f5f5f7;
                }
                QTextEdit {
                    background-color: #ffffff;
                    color: #333;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                }
                QScrollBar:vertical {
                    background: #f5f5f7;
                    width: 12px;
                    margin: 0px;
                }
                QScrollBar::handle:vertical {
                    background: #ccc;
                    min-height: 20px;
                    border-radius: 6px;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """
        
        QApplication.instance().setStyleSheet(qss)
        
    def update_font(self):
        font = QFont("Monospace", self.current_font_size)
        self.list_widget.setFont(font)
        # Save persistence
        self.settings.setValue("font_size", self.current_font_size)

    def show_context_menu(self, position):
        item = self.list_widget.itemAt(position)
        if not item:
            return
            
        sha = item.text().split()[0]
        menu = QMenu()
        
        view_action = QAction(f"Show / View commit {sha}", self)
        move_action = QAction("Move (Drag item to reorder)", self)
        reset_action = QAction(f"Reset Hard to {sha}", self)
        drop_action = QAction("Drop", self)
        rephrase_action = QAction("Rephrase", self)
        
        # Clipboard items
        copy_sha_action = QAction("Copy SHA to clipboard", self)
        copy_msg_action = QAction("Copy commit msg to clipboard", self)
        copy_sha_msg_action = QAction("Copy SHA and commit msg to clipboard", self)
        
        # Squash items
        index = self.list_widget.row(item)
        count = self.list_widget.count()
        
        def format_squash_label(neighbor_item):
            parts = neighbor_item.text().split(maxsplit=1)
            n_sha = parts[0]
            n_msg = parts[1] if len(parts) > 1 else ""
            n_short_msg = " ".join(n_msg.split()[:10])
            return f"{n_sha} ({n_short_msg}...)"

        squash_above_action = None
        if index > 0:
            above_item = self.list_widget.item(index - 1)
            label = f"squash/merge with above commit ({format_squash_label(above_item)})"
            squash_above_action = QAction(label, self)
            squash_above_action.triggered.connect(lambda: self.handle_squash_above(item))
        else:
            squash_above_action = QAction("squash/merge with above commit (N/A)", self)
            squash_above_action.setEnabled(False)

        squash_below_action = None
        if index < count - 1:
            below_item = self.list_widget.item(index + 1)
            label = f"squash/merge with below commit ({format_squash_label(below_item)})"
            squash_below_action = QAction(label, self)
            squash_below_action.triggered.connect(lambda: self.handle_squash_below(item))
        else:
            squash_below_action = QAction("squash/merge with below commit (N/A)", self)
            squash_below_action.setEnabled(False)

        view_action.triggered.connect(lambda: self.view_commit(item))
        # Move action is primarily via drag and drop, but we can make it focus the item
        move_action.triggered.connect(lambda: self.list_widget.setCurrentItem(item))
        reset_action.triggered.connect(lambda: self.handle_reset(item))
        drop_action.triggered.connect(lambda: self.handle_drop(item))
        rephrase_action.triggered.connect(lambda: self.handle_rephrase(item))
        copy_sha_action.triggered.connect(lambda: self.handle_copy_sha(item))
        copy_msg_action.triggered.connect(lambda: self.handle_copy_message(item))
        copy_sha_msg_action.triggered.connect(lambda: self.handle_copy_sha_and_message(item))
        
        menu.addAction(view_action)
        menu.addAction(move_action)
        menu.addSeparator()
        menu.addAction(reset_action)
        menu.addSeparator()
        menu.addAction(drop_action)
        menu.addAction(rephrase_action)
        menu.addSeparator()
        menu.addAction(copy_sha_action)
        menu.addAction(copy_msg_action)
        menu.addAction(copy_sha_msg_action)
        menu.addSeparator()
        menu.addAction(squash_above_action)
        menu.addAction(squash_below_action)
        menu.exec(self.list_widget.mapToGlobal(position))

    def handle_rephrase(self, item):
        """Handles the rephrase action."""
        sha = item.text().split()[0]
        print(f"Preparing to rephrase {sha}...")
        try:
            current_message = get_full_commit_message(self.repo_path, sha)
            dialog = RephraseDialog(sha, current_message, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                new_message = dialog.get_message()
                if new_message != current_message:
                    self.perform_rephrase(sha, new_message)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch commit message: {str(e)}")

    def perform_rephrase(self, sha, new_message):
        """Executes the rephrase using unified rebase logic."""
        try:
            # Current list of SHAs in UI
            current_shas = []
            for i in range(self.list_widget.count()):
                current_shas.append(self.list_widget.item(i).text().split()[0])
            
            if self.run_interactive_rebase(current_shas, rephrase_map={sha: new_message}):
                print(f"Rephrased {sha}.")
                QMessageBox.information(self, "Success", f"Commit {sha} rephrased successfully.")
            
            self.load_history()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while rephrasing: {str(e)}")
            self.load_history()

    def handle_copy_sha(self, item):
        sha = item.text().split()[0]
        print(f"Copying SHA {sha} to clipboard...")
        QApplication.clipboard().setText(sha)
        QMessageBox.information(self, "Copied", f"Copied {sha} to clipboard.")

    def handle_copy_message(self, item):
        sha = item.text().split()[0]
        print(f"Copying message of {sha} to clipboard...")
        try:
            msg = get_full_commit_message(self.repo_path, sha)
            QApplication.clipboard().setText(msg)
            QMessageBox.information(self, "Copied", f"Copied commit message of {sha} to clipboard.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch message: {str(e)}")

    def handle_copy_sha_and_message(self, item):
        sha = item.text().split()[0]
        print(f"Copying SHA and message of {sha} to clipboard...")
        try:
            msg = get_full_commit_message(self.repo_path, sha)
            combined = f"{sha} {msg}"
            QApplication.clipboard().setText(combined)
            QMessageBox.information(self, "Copied", f"Copied SHA and commit message of {sha} to clipboard.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch message: {str(e)}")

    def view_commit(self, item):
        """Helper to open the diff viewer for a commit item."""
        if not item:
            return
        sha = item.text().split()[0]
        print(f"Viewing {sha}...")
        try:
            diff_text = get_commit_diff(self.repo_path, sha)
            dialog = ViewCommitDialog(sha, diff_text, self.current_font_size, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch commit diff: {str(e)}")

    def handle_reset(self, item):
        sha = item.text().split()[0]
        reply = QMessageBox.question(
            self, 
            "Confirm Reset Hard",
            f"Are you sure you want to <b>reset --hard</b> to commit <b>{sha}</b>?<br><br>"
            "This will discard all uncommitted changes and move your branch to this state.",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.perform_reset(sha)

    def perform_reset(self, sha):
        print(f"Resetting hard to {sha}...")
        try:
            cmd = ["git", "reset", "--hard", sha]
            subprocess.run(cmd, cwd=self.repo_path, check=True, capture_output=True, text=True)
            QMessageBox.information(self, "Success", f"Successfully reset --hard to {sha}.")
            self.load_history()
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "Reset Failed", f"Could not perform reset.\n\nError: {e.stderr}")

    def handle_squash_above(self, item):
        """Squashes the current commit with the one above it (newer)."""
        index = self.list_widget.row(item)
        if index <= 0: return
        
        above_item = self.list_widget.item(index - 1)
        sha_above = above_item.text().split()[0]
        sha_current = item.text().split()[0]
        
        try:
            msg_above = get_full_commit_message(self.repo_path, sha_above)
            msg_current = get_full_commit_message(self.repo_path, sha_current)
            
            dialog = SquashDialog(sha_above, msg_above, sha_current, msg_current, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                final_msg = dialog.get_message()
                print(f"Preparing to squash {sha_above} into {sha_current}...")
                self.perform_squash(sha_above, final_msg)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not prepare squash: {str(e)}")

    def handle_squash_below(self, item):
        """Squashes the current commit with the one below it (older)."""
        index = self.list_widget.row(item)
        if index >= self.list_widget.count() - 1: return
        
        sha_current = item.text().split()[0]
        below_item = self.list_widget.item(index + 1)
        sha_below = below_item.text().split()[0]
        
        try:
            msg_current = get_full_commit_message(self.repo_path, sha_current)
            msg_below = get_full_commit_message(self.repo_path, sha_below)
            
            dialog = SquashDialog(sha_current, msg_current, sha_below, msg_below, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                final_msg = dialog.get_message()
                print(f"Preparing to squash {sha_current} into {sha_below}...")
                self.perform_squash(sha_current, final_msg)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not prepare squash: {str(e)}")

    def perform_squash(self, sha_to_squash, final_msg):
        """Executes the squash using unified rebase logic."""
        try:
            # Current list of SHAs in UI
            current_shas = []
            for i in range(self.list_widget.count()):
                current_shas.append(self.list_widget.item(i).text().split()[0])
            
            # Use final_msg for the rebase - we associate it with the SHA being squashed
            # so the amend happens right after the squash command in the todo list.
            if self.run_interactive_rebase(current_shas, squash_shas=[sha_to_squash], 
                                          rephrase_map={sha_to_squash: final_msg}):
                print(f"Squashed {sha_to_squash}.")
                QMessageBox.information(self, "Success", "Commits squashed successfully.")
            
            self.load_history()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while squashing: {str(e)}")
            self.load_history()

    def handle_drop(self, item):
        sha = item.text().split()[0]
        print(f"Preparing to drop {sha}...")
        try:
            diff_text = get_commit_diff(self.repo_path, sha)
            dialog = DropDialog(sha, diff_text, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                self.perform_drop(sha)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def perform_drop(self, sha):
        """Drops a commit using our unified rebase logic."""
        try:
            # Current list of SHAs in UI
            current_shas = []
            for i in range(self.list_widget.count()):
                current_shas.append(self.list_widget.item(i).text().split()[0])
            
            # New list without the dropped SHA
            new_shas = [s for s in current_shas if s != sha]
            
            if self.run_interactive_rebase(new_shas):
                print(f"Dropped {sha}.")
                QMessageBox.information(self, "Success", f"Commit {sha} dropped successfully.")
            
            self.load_history()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while dropping: {str(e)}")
            self.load_history()

    def perform_move(self, new_shas):
        """Performs commit reordering using our unified rebase logic."""
        print("Performing commit reorder...")
        if self.run_interactive_rebase(new_shas):
            QMessageBox.information(self, "Success", "Commits reordered successfully!")
        self.load_history()

    def run_interactive_rebase(self, new_shas, rephrase_map=None, squash_shas=None):
        """
        Unified handler for history rewriting using git rebase -i.
        new_shas: SHAs in the desired final order (latest to oldest as seen in UI).
        rephrase_map: Optional dict mapping SHA -> new commit message string.
        squash_shas: Optional list of SHAs to mark as 'squash' in the todo.
        Returns True if successful, False otherwise.
        """
        print("Executing rebase...")
        try:
            # For rebase todo, we need oldest-first
            rebase_shas = list(reversed(new_shas))
            
            # Check if self.commit_sha has a parent
            has_parent = False
            try:
                subprocess.run(["git", "rev-parse", f"{self.commit_sha}^"], 
                               cwd=self.repo_path, check=True, capture_output=True)
                has_parent = True
            except subprocess.CalledProcessError:
                has_parent = False

            # Create a temporary sequence editor script
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
                f.write(f"#!/usr/bin/env python3\n")
                f.write("import sys, shlex\n")
                f.write(f"new_order = {rebase_shas}\n")
                f.write(f"rephrase_map = {rephrase_map or {}}\n")
                f.write(f"squash_shas = {squash_shas or []}\n")
                f.write("todo_path = sys.argv[1]\n")
                f.write("with open(todo_path, 'w') as f:\n")
                f.write("    for sha in new_order:\n")
                f.write("        op = 'squash' if sha in squash_shas else 'pick'\n")
                f.write("        f.write(f'{op} {sha}\\n')\n")
                f.write("        if sha in rephrase_map:\n")
                # Using --amend -m avoids spawning another editor
                f.write("            msg = shlex.quote(rephrase_map[sha])\n")
                f.write("            f.write(f'exec git commit --amend -m {msg}\\n')\n")
                editor_script = f.name
            
            # Make the script executable
            os.chmod(editor_script, os.stat(editor_script).st_mode | stat.S_IEXEC)
            
            # Run rebase
            env = os.environ.copy()
            env["GIT_SEQUENCE_EDITOR"] = editor_script
            # Use a headless editor for commit messages during squash to avoid hanging
            env["GIT_EDITOR"] = "true"
            
            if has_parent:
                cmd = ["git", "rebase", "-i", "--autosquash", f"{self.commit_sha}^"]
            else:
                cmd = ["git", "rebase", "-i", "--autosquash", "--root"]
            
            result = subprocess.run(cmd, cwd=self.repo_path, env=env, capture_output=True, text=True)
            
            # Clean up
            os.unlink(editor_script)
            
            if result.returncode == 0:
                # IMPORTANT: Update self.commit_sha to the NEW SHA of the bottom-most commit.
                # Interactive rebase of a range of length N results in N new SHAs at the top of history.
                # The oldest one in our range is now at HEAD~{N-1}.
                num_commits = len(new_shas)
                if num_commits > 0:
                    cmd_new_bottom = ["git", "rev-parse", f"HEAD~{num_commits - 1}"]
                    res = subprocess.run(cmd_new_bottom, cwd=self.repo_path, capture_output=True, text=True)
                    if res.returncode == 0:
                        self.commit_sha = res.stdout.strip()
                return True
            else:
                # Rebase failed (likely conflicts)
                # Only abort if there's actually a rebase in progress
                subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_path, capture_output=True)
                QMessageBox.critical(self, "Rebase Failed", 
                    f"Action failed (likely due to merge conflicts).\n"
                    f"The rebase has been aborted.\n\nError: {result.stderr}")
                return False
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred during rebase: {str(e)}")
            return False


    def load_history(self):
        """Fetches git history and populates the list widget."""
        # Clear search when reloading history
        if hasattr(self, 'search_edit'):
            self.search_edit.blockSignals(True)
            self.search_edit.clear()
            self.search_edit.blockSignals(False)

        print("Refreshing...")
        self.update_window_title()
        self.list_widget.clear()
        try:
            history = get_git_history(self.repo_path, self.commit_sha)
            for line in history:
                self.list_widget.addItem(line)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

def main():
    parser = argparse.ArgumentParser(description="Git History Explorer.")
    parser.add_argument("-C", "--location", type=str, default=os.getcwd())
    parser.add_argument("commit_sha", type=str)
    args = parser.parse_args()

    repo_path = os.path.abspath(os.path.expanduser(args.location))
    
    app = QApplication(sys.argv)
    window = GitHistoryApp(repo_path, args.commit_sha)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
