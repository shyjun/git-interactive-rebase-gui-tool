"""Last-resort safety net for unexpected (unhandled) Python exceptions.

``install_excepthook`` (called at the start of ``main()``) registers
``sys.excepthook`` and ``threading.excepthook`` so any exception that escapes
all existing try/except handling shows a crash dialog with the full traceback
and a one-click way to file a GitHub issue.

Expected/recoverable errors that the application already handles are
unaffected — these hooks only run for exceptions that reach the top level.
OS-level faults (SIGSEGV etc.) are the job of ``faulthandler``, not here.
"""
import json
import os
import platform
import sys
import threading
import traceback
import webbrowser
from urllib.parse import urlencode

from PySide6.QtCore import (
    QObject,
    QSettings,
    Signal,
    Slot,
)
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

GITHUB_NEW_ISSUE_URL = (
    "https://github.com/shyjun/git-interactive-rebase-gui-tool/issues/new"
)

CRASH_MESSAGE = (
    "Git Interactive Rebase GUI crashed unexpectedly.\n\n"
    "Please report this as a bug on GitHub. The traceback below can help "
    "identify the problem."
)


def _main_window_font():
    """The same monospace font (family + size) the main window uses."""
    try:
        settings = QSettings("shyjun", "GitInteractiveRebase")
        size = int(settings.value("font_size", 10))
        family = settings.value("font_family", None)
        from lib.app_window.helpers import mono_font
        return mono_font(size, family=family)
    except Exception:
        return QFontDatabase.systemFont(QFontDatabase.FixedFont)


def _tool_version():
    """Best-effort tool version (short commit sha) for the crash report."""
    try:
        import lib
        from lib.git_helpers import get_head_sha
        tool_dir = os.path.abspath(
            os.path.join(os.path.dirname(lib.__file__), ".."))
        sha = get_head_sha(tool_dir)
        if sha == "Unknown":
            from lib.utils import get_assets_path
            vpath = os.path.join(get_assets_path(), "app_version.json")
            if os.path.exists(vpath):
                with open(vpath, encoding="utf-8") as f:
                    sha = json.load(f).get("sha", "Unknown")
        if sha and sha.lower() != "unknown":
            return sha[:8]
        return "Unknown"
    except Exception:
        return "Unknown"


def format_crash_report(exc_type, exc_value, tb, source=None):
    """Build the full crash report text (environment info + traceback)."""
    exc_name = getattr(exc_type, "__name__", str(exc_type))
    header = [
        "Git Interactive Rebase GUI — crash report",
        "=" * 44,
        f"Tool version: {_tool_version()}",
        f"Python: {sys.version.splitlines()[0]}",
        f"Platform: {platform.platform()}",
        f"Exception: {exc_name}: {exc_value}",
    ]
    if source:
        header.append(f"Source: {source}")
    try:
        if tb is not None:
            body = "".join(traceback.format_exception(exc_type, exc_value, tb))
        else:
            body = f"{exc_name}: {exc_value}\n"
    except Exception:
        body = f"{exc_name}: {exc_value}\n"
    return "\n".join(header) + "\n\n" + body


class CrashDialog(QDialog):
    """Read-only crash report with Copy / Issue / Continue / Exit buttons."""

    def __init__(self, report, parent=None):
        super().__init__(parent)
        self._report = report
        self.setWindowTitle("Unexpected Error")
        self.setModal(True)
        self.resize(760, 540)

        layout = QVBoxLayout(self)

        self.message_label = QLabel(CRASH_MESSAGE)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        self.text_area = QPlainTextEdit()
        self.text_area.setPlainText(report)
        self.text_area.setReadOnly(True)
        self.text_area.setFont(_main_window_font())
        layout.addWidget(self.text_area, 1)

        self.copy_button = QPushButton("Copy to Clipboard")
        self.copy_button.clicked.connect(self.copy_to_clipboard)
        self.issue_button = QPushButton("Open GitHub Issue")
        self.issue_button.clicked.connect(self.open_github_issue)
        self.continue_button = QPushButton("Noted. Continue")
        self.continue_button.clicked.connect(self.accept)
        self.exit_button = QPushButton("Exit App")
        self.exit_button.clicked.connect(self.exit_app)

        buttons = QHBoxLayout()
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.issue_button)
        buttons.addStretch(1)
        buttons.addWidget(self.continue_button)
        buttons.addWidget(self.exit_button)
        layout.addLayout(buttons)

    def copy_to_clipboard(self):
        # The crash dialog must never raise a secondary exception.
        try:
            QApplication.clipboard().setText(self._report)
        except Exception:
            pass

    def exit_app(self):
        try:
            QApplication.quit()
        except Exception:
            pass

    def _exception_summary(self):
        for line in self._report.splitlines():
            if line.startswith("Exception: "):
                return line[len("Exception: "):]
        return "unexpected error"

    def open_github_issue(self):
        try:
            title = "Crash: " + self._exception_summary()
            query = urlencode({"title": title[:120], "body": self._report})
            webbrowser.open(f"{GITHUB_NEW_ISSUE_URL}?{query}")
        except Exception:
            pass


def show_crash_dialog(report):
    """Show the crash dialog; creates a QApplication only if none exists yet."""
    try:
        if QApplication.instance() is None:
            QApplication(sys.argv[:1])
        CrashDialog(report).exec()
    except Exception:
        try:
            print(f"[crash] could not show the crash dialog:\n{report}",
                  file=sys.stderr)
        except Exception:
            pass


class _CrashNotifier(QObject):
    """Marshals crash dialogs from worker threads onto the main thread."""
    show_requested = Signal(str)

    @Slot(str)
    def _show(self, report):
        show_crash_dialog(report)


_notifier = _CrashNotifier()
_installed = False
_handling = False


def install_excepthook():
    """Install the global crash handlers; returns the previous hooks."""
    global _installed
    prev_sys_hook = sys.excepthook
    prev_thread_hook = threading.excepthook
    sys.excepthook = _unhandled_excepthook
    threading.excepthook = _unhandled_thread_excepthook
    if not _installed:
        _notifier.show_requested.connect(_notifier._show)
        _installed = True
    return prev_sys_hook, prev_thread_hook


def _unhandled_excepthook(exc_type, exc_value, tb):
    handle_unhandled_exception(exc_type, exc_value, tb)


def _unhandled_thread_excepthook(args):
    handle_unhandled_exception(
        args.exc_type, args.exc_value, args.exc_traceback,
        source=f"background thread '{getattr(args.thread, 'name', '?')}'")


def handle_unhandled_exception(exc_type, exc_value, tb, source=None):
    """Format the crash report, print it to stderr, and show the dialog."""
    global _handling
    try:
        report = format_crash_report(exc_type, exc_value, tb, source)
    except Exception:
        try:
            traceback.print_exception(exc_type, exc_value, tb)
        except Exception:
            pass
        return
    # Never suppress: keep the plain traceback visible on stderr as well.
    try:
        print(report, file=sys.stderr, end="")
    except Exception:
        pass
    if _handling:
        return
    _handling = True
    try:
        if threading.current_thread() is threading.main_thread():
            show_crash_dialog(report)
        else:
            # Qt widgets must be created on the main thread; queue the dialog.
            _notifier.show_requested.emit(report)
    except Exception:
        try:
            print("[crash] failed while showing the crash dialog\n",
                  file=sys.stderr)
        except Exception:
            pass
    finally:
        _handling = False
