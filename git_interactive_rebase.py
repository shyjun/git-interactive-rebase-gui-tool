#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QListWidget, QVBoxLayout, 
    QWidget, QMessageBox, QListWidgetItem, QMenu, QDialog,
    QTextEdit, QPushButton, QHBoxLayout, QLabel
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QAction

def get_git_history(repo_path, commit_sha):
    """Fetches git history from HEAD to commit_sha."""
    try:
        cmd = ["git", "log", f"{commit_sha}..HEAD", "--oneline"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        history = result.stdout.strip().split('\n')
        
        cmd_sha = ["git", "log", "-1", commit_sha, "--oneline"]
        result_sha = subprocess.run(cmd_sha, cwd=repo_path, capture_output=True, text=True, check=True)
        history.append(result_sha.stdout.strip())
        
        return [line for line in history if line.strip()]
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch git history: {e.stderr}")

def get_commit_diff(repo_path, commit_sha):
    """Fetches the diff for a specific commit."""
    try:
        cmd = ["git", "show", commit_sha, "--format="]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch diff: {e.stderr}")

class DiffHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.added_format = QTextCharFormat()
        self.added_format.setForeground(QColor("#a6e22e"))  # Greenish
        
        self.removed_format = QTextCharFormat()
        self.removed_format.setForeground(QColor("#f92672"))  # Reddish
        
        self.header_format = QTextCharFormat()
        self.header_format.setForeground(QColor("#66d9ef"))  # Bluish

    def highlightBlock(self, text):
        if text.startswith('+') and not text.startswith('+++'):
            self.setFormat(0, len(text), self.added_format)
        elif text.startswith('-') and not text.startswith('---'):
            self.setFormat(0, len(text), self.removed_format)
        elif text.startswith('commit') or text.startswith('diff') or text.startswith('index'):
            self.setFormat(0, len(text), self.header_format)

class DiffViewerDialog(QDialog):
    """Base dialog for viewing diffs with centered buttons."""
    def __init__(self, title, sha, diff_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(800, 600)
        
        self.layout = QVBoxLayout(self)
        
        # Header info
        self.setup_header(sha)
        
        # Diff View
        self.diff_view = QTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(QFont("Courier New", 10))
        self.diff_view.setPlainText(diff_text)
        self.highlighter = DiffHighlighter(self.diff_view.document())
        
        self.diff_view.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #dcdcdc;
                border: 1px solid #3c3f41;
            }
        """)
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
    def __init__(self, sha, diff_text, parent=None):
        super().__init__(f"View Commit: {sha}", sha, diff_text, parent)

    def setup_header(self, sha):
        label = QLabel(f"Showing changes for commit: <b>{sha}</b>")
        self.layout.addWidget(label)

    def setup_buttons(self):
        ok_btn = QPushButton("Ok")
        ok_btn.setMinimumWidth(100)
        ok_btn.clicked.connect(self.accept)
        self.btn_layout.addWidget(ok_btn)

class DropDialog(DiffViewerDialog):
    def __init__(self, sha, diff_text, parent=None):
        super().__init__("Confirm Drop Commit", sha, diff_text, parent)

    def setup_header(self, sha):
        label = QLabel(f"Are you sure you want to drop the commit: <b>{sha}</b>?")
        label.setStyleSheet("color: #f92672;") # Reddish warning
        self.layout.addWidget(label)

    def setup_buttons(self):
        self.yes_btn = QPushButton("Yes, Drop it")
        self.no_btn = QPushButton("No, Cancel")
        
        self.yes_btn.setMinimumWidth(120)
        self.no_btn.setMinimumWidth(120)
        
        self.yes_btn.clicked.connect(self.accept)
        self.no_btn.clicked.connect(self.reject)
        
        self.btn_layout.addWidget(self.yes_btn)
        self.btn_layout.addWidget(self.no_btn)

class CommitListWidget(QListWidget):
    """Subclassed QListWidget to handle Drag & Drop move confirmation."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.InternalMove)
        
        self.dragging_item = None

    def dropEvent(self, event):
        # Determine the old and new positions
        old_row = self.currentRow()
        
        # Execute the default drop behavior first to update the list
        super().dropEvent(event)
        
        new_row = self.currentRow()
        
        if old_row != new_row:
            item = self.item(new_row)
            sha = item.text().split()[0]
            
            # Ask for confirmation
            reply = QMessageBox.question(
                self, 
                "Confirm Move",
                f"Do you want to move commit <b>{sha}</b> to a new position?",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                print(f"MOVE PROTOTYPE: User said YES to moving {sha} from index {old_row} to {new_row}")
                QMessageBox.information(self, "Move", f"Moving {sha}... (Functionality not implemented yet)")
            else:
                print(f"MOVE PROTOTYPE: User said NO to moving {sha}")
                # Revert move visually (optional, for prototype we might just refresh history later)
                # For now, let's keep it in the new position as it's a visual prototype

class GitHistoryApp(QMainWindow):
    def __init__(self, repo_path, commit_sha):
        super().__init__()
        self.repo_path = repo_path
        self.commit_sha = commit_sha
        
        self.setWindowTitle(f"Git History Explorer - {os.path.basename(repo_path)}")
        self.resize(1000, 800)

        self.setup_ui()
        self.load_history()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Use our custom list widget
        self.list_widget = CommitListWidget()
        self.list_widget.setFont(QFont("Monospace", 10))
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: #2b2b2b;
                color: #dcdcdc;
                border: 1px solid #3c3f41;
                border-radius: 4px;
                padding: 2px;
            }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #3c3f41; }
            QListWidget::item:selected { background-color: #4b6eaf; }
        """)
        
        layout.addWidget(self.list_widget)

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
        rephrase_action = QAction("Rephrase (Not implemented)", self)
        rephrase_action.setEnabled(False)
        
        view_action.triggered.connect(lambda: self.handle_view(item))
        # Move action is primarily via drag and drop, but we can make it focus the item
        move_action.triggered.connect(lambda: self.list_widget.setCurrentItem(item))
        reset_action.triggered.connect(lambda: self.handle_reset(item))
        drop_action.triggered.connect(lambda: self.handle_drop(item))
        
        menu.addAction(view_action)
        menu.addAction(move_action)
        menu.addSeparator()
        menu.addAction(reset_action)
        menu.addSeparator()
        menu.addAction(drop_action)
        menu.addAction(rephrase_action)
        menu.exec(self.list_widget.mapToGlobal(position))

    def handle_view(self, item):
        sha = item.text().split()[0]
        try:
            diff_text = get_commit_diff(self.repo_path, sha)
            dialog = ViewCommitDialog(sha, diff_text, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

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
        try:
            cmd = ["git", "reset", "--hard", sha]
            subprocess.run(cmd, cwd=self.repo_path, check=True, capture_output=True, text=True)
            QMessageBox.information(self, "Success", f"Successfully reset --hard to {sha}.")
            self.load_history()
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "Reset Failed", f"Could not perform reset.\n\nError: {e.stderr}")

    def handle_drop(self, item):
        sha = item.text().split()[0]
        try:
            diff_text = get_commit_diff(self.repo_path, sha)
            dialog = DropDialog(sha, diff_text, self)
            if dialog.exec() == QDialog.Accepted:
                self.perform_drop(sha)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def perform_drop(self, sha):
        try:
            cmd = ["git", "rebase", "--onto", f"{sha}^", sha, "HEAD"]
            subprocess.run(cmd, cwd=self.repo_path, check=True, capture_output=True, text=True)
            QMessageBox.information(self, "Success", f"Commit {sha} dropped successfully.")
            self.load_history()
        except subprocess.CalledProcessError as e:
            subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_path)
            QMessageBox.critical(self, "Rebase Failed", f"Could not drop commit.\n\nError: {e.stderr}")

    def load_history(self):
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
