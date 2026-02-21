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
    QTextEdit, QPushButton, QHBoxLayout, QLabel
)
from PySide6.QtCore import Qt, QSize, QSettings
from PySide6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QAction

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
    def __init__(self, sha, diff_text, font_size=10, parent=None):
        super().__init__(f"View Commit: {sha}", sha, diff_text, font_size, parent)

    def setup_header(self, sha):
        label = QLabel(f"Showing changes for commit: <b>{sha}</b>")
        self.layout.addWidget(label)

    def setup_buttons(self):
        ok_btn = QPushButton("Ok")
        ok_btn.setMinimumWidth(100)
        ok_btn.clicked.connect(self.accept)
        self.btn_layout.addWidget(ok_btn)

class DropDialog(DiffViewerDialog):
    def __init__(self, sha, diff_text, font_size=10, parent=None):
        super().__init__("Confirm Drop Commit", sha, diff_text, font_size, parent)

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
        self.message_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #dcdcdc;
                border: 1px solid #3c3f41;
            }
        """)
        layout.addWidget(self.message_edit)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.apply_btn = QPushButton("Apply")
        self.discard_btn = QPushButton("Discard")
        
        for btn in [self.apply_btn, self.discard_btn]:
            btn.setMinimumWidth(120)
            btn.setMinimumHeight(40)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3c3f41;
                    color: #dcdcdc;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #4b6eaf; }
            """)
            
        self.apply_btn.clicked.connect(self.accept)
        self.discard_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.apply_btn)
        btn_layout.addWidget(self.discard_btn)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)

    def get_message(self):
        return self.message_edit.toPlainText().strip()

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
        self.load_history()

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
        self.list_widget.itemDoubleClicked.connect(self.view_commit)

        # Bottom Control Bar
        controls_layout = QHBoxLayout()
        
        self.zoom_in_btn = QPushButton("Zoom In (+)")
        self.zoom_out_btn = QPushButton("Zoom Out (-)")
        self.refresh_btn = QPushButton("Refresh")
        self.exit_btn = QPushButton("Exit")
        
        for btn in [self.zoom_in_btn, self.zoom_out_btn, self.refresh_btn, self.exit_btn]:
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(120)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3c3f41;
                    color: #dcdcdc;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #4b6eaf;
                }
                QPushButton:pressed {
                    background-color: #2d4470;
                }
            """)

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

    def handle_zoom_in(self):
        self.current_font_size += 1
        self.update_font()

    def handle_zoom_out(self):
        if self.current_font_size > 6:
            self.current_font_size -= 1
            self.update_font()

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
        
        view_action.triggered.connect(lambda: self.view_commit(item))
        # Move action is primarily via drag and drop, but we can make it focus the item
        move_action.triggered.connect(lambda: self.list_widget.setCurrentItem(item))
        reset_action.triggered.connect(lambda: self.handle_reset(item))
        drop_action.triggered.connect(lambda: self.handle_drop(item))
        rephrase_action.triggered.connect(lambda: self.handle_rephrase(item))
        
        menu.addAction(view_action)
        menu.addAction(move_action)
        menu.addSeparator()
        menu.addAction(reset_action)
        menu.addSeparator()
        menu.addAction(drop_action)
        menu.addAction(rephrase_action)
        menu.exec(self.list_widget.mapToGlobal(position))

    def handle_rephrase(self, item):
        """Handles the rephrase action."""
        sha = item.text().split()[0]
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
                QMessageBox.information(self, "Success", f"Commit {sha} rephrased successfully.")
            
            self.load_history()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while rephrasing: {str(e)}")
            self.load_history()

    def view_commit(self, item):
        """Helper to open the diff viewer for a commit item."""
        if not item:
            return
        sha = item.text().split()[0]
        dialog = DiffViewerDialog(
            repo_path=self.repo_path,
            commit_sha=sha,
            font_size=self.current_font_size,
            parent=self
        )
        dialog.exec()

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
                QMessageBox.information(self, "Success", f"Commit {sha} dropped successfully.")
            
            self.load_history()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while dropping: {str(e)}")
            self.load_history()

    def perform_move(self, new_shas):
        """Performs commit reordering using our unified rebase logic."""
        if self.run_interactive_rebase(new_shas):
            QMessageBox.information(self, "Success", "Commits reordered successfully!")
        self.load_history()

    def run_interactive_rebase(self, new_shas, rephrase_map=None):
        """
        Unified handler for history rewriting using git rebase -i.
        new_shas: SHAs in the desired final order (latest to oldest as seen in UI).
        rephrase_map: Optional dict mapping SHA -> new commit message string.
        Returns True if successful, False otherwise.
        """
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
                f.write("todo_path = sys.argv[1]\n")
                f.write("with open(todo_path, 'w') as f:\n")
                f.write("    for sha in new_order:\n")
                f.write("        f.write(f'pick {sha}\\n')\n")
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
