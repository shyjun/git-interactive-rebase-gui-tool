import pathlib
import os
import platform
import shlex
import subprocess
import sys
import tempfile
import re
import time
from PySide6.QtCore import (
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontDatabase,
)
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
)
from PySide6.QtGui import QAction

import atexit
import shutil

PR_DIFF_SIZE_WARN_THRESHOLD = 200_000

PLAIN_DIFF_LINE_CAP = 10_000

MATCH_ROLE = Qt.UserRole + 7

_VERBOSE = False
_VERBOSE_TAGS = {'perf', 'ctx', 'diff', 'stats', 'thread', 'rescan'}


def set_verbose(enabled=True):
    global _VERBOSE
    _VERBOSE = enabled


def _log(msg, **_kw):
    """Log a message with a millisecond-precision timestamp.
    In non-verbose mode, only errors and essential startup messages are shown."""
    if not _VERBOSE:
        tag = msg.split(']')[0].lstrip('[') if ']' in msg else ''
        is_error = any(k in msg for k in ('FAILED', 'Error', 'error', 'Exception', 'Traceback'))
        if tag not in _VERBOSE_TAGS and not is_error:
            return
    print(f"[{time.strftime('%H:%M:%S')}.{time.time_ns() % 1000:03d}] {msg}")


_MONOSPACE_CANDIDATES = {
    "Windows": ["Cascadia Code", "Consolas", "Courier New", "Lucida Console"],
    "Darwin": ["Menlo", "Monaco", "Courier New"],
    "Linux": ["Monospace"],
}

def default_mono_family():
    """Return the first available monospace font on this platform."""
    system = platform.system()
    candidates = _MONOSPACE_CANDIDATES.get(system, ["Monospace"])
    available = QFontDatabase.families()
    for name in candidates:
        if name in available:
            return name
    return "Monospace"

def mono_font(size, family=None):
    """Return a QFont guaranteed to be monospace on all platforms."""
    if family is None:
        family = default_mono_family()
    f = QFont(family, size)
    f.setStyleHint(QFont.StyleHint.Monospace)
    return f


def _relaunch():
    """Relaunch the application. Handles both source and pip-installed modes."""
    import sys
    import os
    import platform
    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QApplication

    script = os.path.abspath(sys.argv[0])

    if platform.system() == "Windows" and not os.path.isfile(script):
        # Pip install on Windows: sys.argv[0] may be a generated wrapper.
        # Try running the .exe entry point directly.
        exe_path = script + ".exe"
        if os.path.isfile(exe_path):
            QProcess.startDetached(exe_path, sys.argv[1:])
            QApplication.quit()
            return
        # Fallback: re-run via python -m
        module = os.path.splitext(os.path.basename(script))[0]
        QProcess.startDetached(sys.executable, ["-m", module] + sys.argv[1:])
        QApplication.quit()
        return

    QProcess.startDetached(sys.executable, [script] + sys.argv[1:])
    QApplication.quit()


def clean_binary_diff_lines(diff_text):
    """Replace verbose 'Binary files ... differ' lines with compact markers."""
    lines = diff_text.split('\n')
    cleaned = []
    for line in lines:
        if line.startswith('Binary files ') and line.endswith(' differ'):
            cleaned.append('[binary file]')
        else:
            cleaned.append(line)
    return '\n'.join(cleaned)

_CREATED_TEMP_DIRS = set()


def _cleanup_temp_dirs():
    for d in list(_CREATED_TEMP_DIRS):
        try:
            if os.path.exists(d):
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


atexit.register(_cleanup_temp_dirs)


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

    # Use saved original if available (handles re-entrant calls without corrupting)
    original_stylesheet = getattr(button, '_original_stylesheet', button.styleSheet())
    if not hasattr(button, '_original_stylesheet'):
        button._original_stylesheet = original_stylesheet

    highlight = (
        f"border: 3px solid {color.name()}; "
        f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, 90); "
        f"font-weight: bold; {original_stylesheet}"
    )

    # Cancel any pending highlight timer from a previous call
    old_timer = getattr(button, '_highlight_timer', None)
    if old_timer is not None:
        old_timer.stop()

    def set_stylesheet(sheet):
        try:
            button.setStyleSheet(sheet)
        except RuntimeError:
            pass

    if blinks <= 0:
        set_stylesheet(highlight)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: (
            set_stylesheet(original_stylesheet),
            setattr(button, '_highlight_timer', None),
        ))
        timer.start(duration_ms)
        button._highlight_timer = timer
        return

    total_ticks = blinks * 2
    state = {"tick": 0}

    def toggle():
        state["tick"] += 1
        if state["tick"] >= total_ticks:
            set_stylesheet(original_stylesheet)
            button._highlight_timer = None
            return
        set_stylesheet(original_stylesheet if state["tick"] % 2 == 1 else highlight)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(toggle)
        timer.start(400)
        button._highlight_timer = timer

    set_stylesheet(highlight)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(toggle)
    timer.start(400)
    button._highlight_timer = timer


def add_open_with_system_default_action(menu, target_path, parent, sha=None, repo_path=None, is_head=False):
    """Add 'Open > With System Default App' submenu before Blame in a context menu.
    If sha is provided and the file was modified in newer commits, extracts the file
    content from that commit to /tmp. Otherwise opens from the working tree."""
    open_menu = menu.addMenu("Open")
    open_default_action = QAction("With System Default App", parent)
    if sha:
        rp = repo_path or parent.repo_path
        open_default_action.triggered.connect(
            lambda checked=False, filepath=target_path, s=sha, r=rp, p=parent:
                _open_file_smart(r, s, filepath, p)
        )
    else:
        open_default_action.triggered.connect(
            lambda checked=False, filepath=target_path: QDesktopServices.openUrl(
                QUrl.fromLocalFile(os.path.join(parent.repo_path, filepath))
            )
        )
    open_menu.addAction(open_default_action)


def _open_file_smart(repo_path, sha, filepath, parent):
    """Open file: from working tree if unchanged since sha, else extract from commit."""
    try:
        head_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_path
        ).decode().strip()
        if sha == head_sha or head_sha.startswith(sha):
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(os.path.join(repo_path, filepath)))
            return
        diff_result = subprocess.run(
            ["git", "diff", "--name-only", sha, "HEAD", "--", filepath],
            cwd=repo_path, capture_output=True, text=True
        )
        if not diff_result.stdout.strip():
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(os.path.join(repo_path, filepath)))
        else:
            _open_file_from_commit(repo_path, sha, filepath, parent)
    except Exception:
        _open_file_from_commit(repo_path, sha, filepath, parent)


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
        _CREATED_TEMP_DIRS.add(tmp_dir)
        tmp_path = os.path.join(tmp_dir, basename)
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(result.stdout)
        QDesktopServices.openUrl(QUrl.fromLocalFile(tmp_path))
    except Exception as e:
        QMessageBox.warning(parent, "Open Failed", f"Could not open file: {e}")


def _get_head_sha(repo_path):
    """Get the current HEAD SHA for a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path, capture_output=True, text=True,
            encoding='utf-8', errors='replace'
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


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
