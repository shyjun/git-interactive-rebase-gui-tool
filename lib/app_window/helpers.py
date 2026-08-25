import pathlib
import os
import shlex
import subprocess
import sys
import tempfile
import re
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox, QMenu
from PySide6.QtGui import QAction

PR_DIFF_SIZE_WARN_THRESHOLD = 200_000

MATCH_ROLE = Qt.UserRole + 7


def _posix_path(p: str) -> str:
    return pathlib.Path(p).as_posix()


def _safe_unlink(*paths):
    for p in paths:
        if p:
            try:
                os.unlink(p)
            except OSError:
                pass


def _script_command(script_path: str) -> str:
    interp = shlex.quote(_posix_path(sys.executable))
    script = shlex.quote(_posix_path(script_path))
    return f"{interp} {script}"


def _diff_search_matches(haystack, term, match_case, whole_word):
    if not term:
        return False
    flags = 0 if match_case else re.IGNORECASE
    if whole_word:
        pattern = rf"\b{re.escape(term)}\b"
    else:
        pattern = re.escape(term)
    return re.search(pattern, haystack, flags) is not None


def highlight_button_temporarily(button, duration_ms=3000, blinks=0, color=None):
    if color is None:
        color = QColor(255, 140, 0)
    original_stylesheet = button.styleSheet()
    highlight = (
        f"border: 3px solid {color.name()}; "
        f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, 90); "
        f"font-weight: bold; {original_stylesheet}"
    )

    def set_stylesheet(sheet):
        try:
            button.setStyleSheet(sheet)
        except RuntimeError:
            pass

    if blinks <= 0:
        set_stylesheet(highlight)
        QTimer.singleShot(duration_ms, lambda: set_stylesheet(original_stylesheet))
        return

    total_ticks = blinks * 2
    state = {"tick": 0}

    def toggle():
        state["tick"] += 1
        if state["tick"] >= total_ticks:
            set_stylesheet(original_stylesheet)
            return
        set_stylesheet(original_stylesheet if state["tick"] % 2 == 1 else highlight)
        QTimer.singleShot(400, toggle)

    set_stylesheet(highlight)
    QTimer.singleShot(400, toggle)


def add_open_with_system_default_action(menu, target_path, parent, sha=None, repo_path=None):
    """Add 'Open > With System Default App' submenu before Blame in a context menu.
    If sha is provided, extracts the file content from that commit (for browsing
    a different branch). Otherwise opens the file from the working tree."""
    open_menu = menu.addMenu("Open")
    open_default_action = QAction("With System Default App", parent)
    if sha:
        rp = repo_path or parent.repo_path
        open_default_action.triggered.connect(
            lambda checked=False, filepath=target_path, s=sha, r=rp: _open_file_from_commit(r, s, filepath, parent)
        )
    else:
        open_default_action.triggered.connect(
            lambda checked=False, filepath=target_path: QDesktopServices.openUrl(
                QUrl.fromLocalFile(os.path.join(parent.repo_path, filepath))
            )
        )
    open_menu.addAction(open_default_action)


def _open_file_from_commit(repo_path, sha, filepath, parent):
    """Extract a file from a specific commit to /tmp and open it."""
    try:
        result = subprocess.run(
            ["git", "show", f"{sha}:{filepath}"],
            cwd=repo_path, capture_output=True, text=True,
            encoding='utf-8', errors='replace'
        )
        if result.returncode != 0:
            QMessageBox.warning(
                parent, "Open Failed",
                f"Could not extract '{filepath}' from commit {sha[:8]}.\n\n{result.stderr}"
            )
            return
        basename = os.path.basename(filepath)
        tmp_dir = tempfile.mkdtemp(prefix="git-browse-")
        tmp_path = os.path.join(tmp_dir, basename)
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(result.stdout)
        QDesktopServices.openUrl(QUrl.fromLocalFile(tmp_path))
    except Exception as e:
        QMessageBox.warning(parent, "Open Failed", f"Could not open file: {e}")


def is_editable_branch(parent):
    """Return True if the parent dialog's main window is on the checked-out branch.
    Walks the widget tree to find the root main window and checks viewer_mode."""
    widget = parent
    while widget is not None:
        if hasattr(widget, 'viewer_mode') and hasattr(widget, 'browse_mode'):
            return not widget.viewer_mode
        widget = widget.parent() if hasattr(widget, 'parent') else None
    return True


def get_theme_stylesheet(theme_name):
    if theme_name == "dark":
        return """
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
            QGroupBox {
                border: 1px solid #3c3c3c;
                border-radius: 5px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
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
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666666;
                border: 1px solid #444444;
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
                color: #cccccc;
            }
            QDialog, QMenu {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
            }
            QStatusBar {
                background-color: #1e1e1e;
                border-top: 1px solid #3c3c3c;
            }
            QStatusBar::item {
                border: none;
            }
            QMenu::item:selected {
                background-color: #007acc;
                color: white;
            }
            QMenu::item:disabled {
                color: #666666;
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
        return """
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
            QGroupBox {
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
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
            QPushButton:disabled {
                background-color: #f0f0f0;
                color: #aaaaaa;
                border: 1px solid #e0e0e0;
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
            QDialog, QMenu {
                background-color: #f5f5f7;
                color: #333;
                border: 1px solid #ccc;
            }
            QStatusBar {
                background-color: #f5f5f7;
                border-top: 1px solid #ccc;
            }
            QStatusBar::item {
                border: none;
            }
            QMenu::item:selected {
                background-color: #007aff;
                color: white;
            }
            QMenu::item:disabled {
                color: #aaaaaa;
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
