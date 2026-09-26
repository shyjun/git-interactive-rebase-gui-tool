"""Cross-platform detection of a previous run that did not exit normally.

Each instance writes a marker file (``git-interactive-rebase-gui-<PID>.json``
in the temp directory) at startup and removes it on normal exit. On the next
startup, a marker whose process is no longer running — or whose PID now belongs
to a different process — means the previous instance may have been killed or
crashed (SIGSEGV, kill -9, power loss, system shutdown, ...). One notification
is shown and the stale markers are then removed.

The mechanism never claims that a run definitely crashed; it only knows that
an instance left a marker behind without cleaning it up.

Everything is controlled by ``ENABLE_UNCLEAN_EXIT_DETECTION`` — set it to
False to disable scanning, marker creation, cleanup, and notifications
entirely.

Marker files can be redirected for tests via the ``GIT_REBASE_GUI_MARKER_DIR``
environment variable.
"""
import atexit
import datetime
import glob
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import webbrowser

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from lib.crash_report import (
    GITHUB_NEW_ISSUE_URL,
    _main_window_font,
    _tool_version,
)
from lib.logger import _log

# Set to False to disable the whole feature: no scan, no marker creation,
# no cleanup, no log messages, no notification.
ENABLE_UNCLEAN_EXIT_DETECTION = True

_MARKER_PREFIX = "git-interactive-rebase-gui-"
_MARKER_SUFFIX = ".json"

# A live process whose start time differs from the recorded start time by
# more than this many seconds is a different process that reused the PID.
_START_TOLERANCE_SECONDS = 120

NOTIFICATION_MESSAGE = (
    "A previous run of Git Interactive Rebase GUI did not exit normally.\n\n"
    "The application may have crashed or been terminated before it could "
    "shut down cleanly. The stale run(s) listed below have been cleaned up "
    "and will not be reported again."
)

_current_marker_path = None


def _marker_dir():
    """Directory holding marker files (env seam for tests, else tempdir)."""
    custom = os.environ.get("GIT_REBASE_GUI_MARKER_DIR")
    if custom:
        return custom
    return tempfile.gettempdir()


def _marker_path(pid):
    return os.path.join(_marker_dir(), f"{_MARKER_PREFIX}{pid}{_MARKER_SUFFIX}")


def _is_pid_alive(pid):
    """True / False / None (unknown). Never calls os.kill on Windows."""
    if pid <= 0:
        return False
    try:
        if platform.system() == "Windows":
            return _windows_pid_alive(pid)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    except Exception:
        return None


def _windows_pid_alive(pid):
    # os.kill(pid, 0) on Windows TERMINATES the target process — never use it.
    import ctypes

    process_query_limited_information = 0x1000
    still_active = 259
    error_invalid_parameter = 87
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if not handle:
        if kernel32.GetLastError() == error_invalid_parameter:
            return False
        return None
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return None
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _process_start_time(pid):
    """Best-effort start time (epoch seconds) of a running process."""
    try:
        if platform.system() == "Windows":
            return _windows_process_start_time(pid)
        return _unix_process_start_time(pid)
    except Exception:
        return None


def _unix_process_start_time(pid):
    out = subprocess.run(
        ["ps", "-o", "etimes=", "-p", str(pid)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    text = out.stdout.strip()
    if out.returncode == 0 and text.isdigit():
        return time.time() - int(text)
    out = subprocess.run(
        ["ps", "-o", "lstart=", "-p", str(pid)],
        capture_output=True,
        text=True,
        timeout=5,
        env=dict(os.environ, LC_ALL="C"),
    )
    text = out.stdout.strip()
    if out.returncode == 0 and text:
        return time.mktime(time.strptime(text, "%a %b %d %H:%M:%S %Y"))
    return None


def _windows_process_start_time(pid):
    import ctypes.wintypes

    process_query_limited_information = 0x1000
    filetime_to_unix_epoch = 11644473600
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if not handle:
        return None
    try:
        creation = ctypes.wintypes.FILETIME()
        exit_time = ctypes.wintypes.FILETIME()
        kernel = ctypes.wintypes.FILETIME()
        user = ctypes.wintypes.FILETIME()
        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        if not ok:
            return None
        ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return ticks / 10_000_000 - filetime_to_unix_epoch
    finally:
        kernel32.CloseHandle(handle)


def _process_exec_name(pid):
    """Basename of the executable of a running process, or None."""
    try:
        if platform.system() == "Windows":
            return None
        out = subprocess.run(
            ["ps", "-o", "comm=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return os.path.basename(out.stdout.strip().splitlines()[0])
    except Exception:
        pass
    return None


def _marker_started_epoch(marker):
    try:
        text = marker.get("started_at")
        if not text:
            return None
        return datetime.datetime.fromisoformat(str(text)).timestamp()
    except Exception:
        return None


def _classify_marker(marker, pid):
    """Return "active" or "stale" for a marker file named with ``pid``."""
    if pid == os.getpid():
        return "active"
    alive = _is_pid_alive(pid)
    if alive is False:
        return "stale"
    if alive is None:
        # Cannot verify — never risk removing a running instance's marker.
        return "active"
    marker_start = _marker_started_epoch(marker)
    live_start = _process_start_time(pid)
    if marker_start is not None and live_start is not None:
        if abs(live_start - marker_start) <= _START_TOLERANCE_SECONDS:
            return "active"
        return "stale"
    marker_exe = os.path.basename(str(marker.get("executable") or "")).lower() or None
    live_exe = _process_exec_name(pid)
    if marker_exe and live_exe:
        return "active" if marker_exe == live_exe.lower() else "stale"
    return "active"


def _read_marker(path):
    """Return the marker dict, or None for invalid/corrupt files (kept, not deleted)."""
    try:
        with open(path, encoding="utf-8") as handle:
            marker = json.load(handle)
        if not isinstance(marker, dict):
            raise ValueError("marker is not a JSON object")
        return marker
    except Exception as exc:
        _log(f"[startup_check] ignoring invalid marker {os.path.basename(path)}: {exc}")
        return None


def _scan_markers():
    """Return stale markers: instances that left a marker but are not running."""
    directory = _marker_dir()
    _log("[startup_check] scanning marker files")
    stale = []
    try:
        pattern = os.path.join(directory, _MARKER_PREFIX + "*" + _MARKER_SUFFIX)
        paths = sorted(glob.glob(pattern))
    except Exception as exc:
        _log(f"[startup_check] could not scan marker files: {exc}")
        return stale
    for path in paths:
        name = os.path.basename(path)
        try:
            pid = int(name[len(_MARKER_PREFIX):-len(_MARKER_SUFFIX)])
        except ValueError:
            _log(f"[startup_check] skipping marker with unexpected name: {name}")
            continue
        marker = _read_marker(path)
        if marker is None:
            continue
        if _classify_marker(marker, pid) == "active":
            _log(f"[startup_check] found active instance pid={pid}")
            continue
        _log(f"[startup_check] found stale instance pid={pid}")
        stale.append({"path": path, "pid": pid, "marker": marker})
    return stale


def _create_marker(pid):
    """Atomically write this instance's marker file; return its path."""
    try:
        working_directory = os.getcwd()
    except Exception:
        working_directory = ""
    marker = {
        "pid": int(pid),
        "tool_version": _tool_version(),
        "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "executable": sys.executable,
        "working_directory": working_directory,
        "command_line": [str(part) for part in sys.argv],
    }
    path = _marker_path(pid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(marker, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    return path


def _format_notification_details(stale_instances):
    blocks = []
    total = len(stale_instances)
    for index, entry in enumerate(stale_instances, start=1):
        marker = entry.get("marker") or {}
        pid = entry.get("pid")
        header = "Previous instance" if total == 1 else f"Previous instance #{index}"
        started = str(marker.get("started_at") or "Unknown")
        command = " ".join(str(part) for part in (marker.get("command_line") or []))
        blocks.append("\n".join([
            header,
            "",
            f"Tool version: {marker.get('tool_version') or 'Unknown'}",
            f"Location: {marker.get('working_directory') or 'Unknown'}",
            f"Command: {command or 'Unknown'}",
            f"Started: {started}",
            f"PID: {pid}",
        ]))
    separator = "\n\n" + "-" * 48 + "\n\n"
    return separator.join(blocks)


def _open_github_issues():
    try:
        webbrowser.open(GITHUB_NEW_ISSUE_URL)
    except Exception:
        pass


def _apply_tool_theme():
    """Apply the tool's theme stylesheet so the dialog matches the tool look.

    main() applies this later for its own dialogs; the previous-run
    notification shows before that point and must not look foreign.
    """
    try:
        app = QApplication.instance()
        if app is None:
            return
        theme_name = QSettings(
            "git-interactive-rebase-gui-tool", "settings"
        ).value("theme", "light", type=str)
        from lib.app_window.helpers import get_theme_stylesheet
        app.setStyleSheet(get_theme_stylesheet(theme_name))
    except Exception:
        pass


def _build_notification_dialog(details):
    dialog = QDialog()
    dialog.setWindowTitle("Previous Run")
    dialog.setModal(True)
    dialog.resize(700, 460)

    layout = QVBoxLayout(dialog)
    message_label = QLabel(NOTIFICATION_MESSAGE)
    message_label.setWordWrap(True)
    layout.addWidget(message_label)

    details_area = QPlainTextEdit()
    details_area.setReadOnly(True)
    details_area.setPlainText(details)
    details_area.setFont(_main_window_font())
    layout.addWidget(details_area, 1)

    open_button = QPushButton("Open GitHub Issues")
    open_button.setMinimumWidth(120)
    open_button.setProperty("class", "dialog-btn")
    open_button.clicked.connect(_open_github_issues)
    noted_button = QPushButton("Noted. Continue")
    noted_button.setMinimumWidth(120)
    noted_button.setProperty("class", "dialog-btn")
    noted_button.clicked.connect(dialog.accept)

    buttons = QHBoxLayout()
    buttons.addStretch(1)
    buttons.addWidget(open_button)
    buttons.addWidget(noted_button)
    layout.addLayout(buttons)

    dialog.open_button = open_button
    dialog.noted_button = noted_button
    dialog.details_area = details_area
    return dialog


def show_previous_run_notification(stale_instances):
    """Show the previous-run notification. Never raises."""
    try:
        details = _format_notification_details(stale_instances)
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        _apply_tool_theme()
        dialog = _build_notification_dialog(details)
        dialog.exec()
    except Exception as exc:
        try:
            _log(f"[startup_check] could not show previous-run notification: {exc}")
        except Exception:
            pass


def cleanup_current_marker():
    """Remove this instance's marker on normal exit. Idempotent."""
    global _current_marker_path
    path = _current_marker_path
    _current_marker_path = None
    if not path:
        return
    try:
        os.remove(path)
        _log(f"[startup_check] removed marker {os.path.basename(path)}")
    except FileNotFoundError:
        pass
    except Exception as exc:
        _log(f"[startup_check] could not remove marker: {exc}")


def _install():
    global _current_marker_path
    try:
        stale = _scan_markers()
    except Exception as exc:
        _log(f"[startup_check] scan failed: {exc}")
        stale = []

    # Remove stale markers first, then report only the ones we cleared — a
    # marker we cannot delete (e.g. another user's) must not re-notify on
    # every startup, and concurrent instances racing on the same markers
    # produce at most one notification.
    reportable = []
    for entry in stale:
        name = os.path.basename(entry["path"])
        try:
            os.remove(entry["path"])
        except FileNotFoundError:
            continue
        except Exception as exc:
            _log(f"[startup_check] could not remove stale marker {name}: {exc}")
            continue
        _log(f"[startup_check] removed stale marker {name}")
        reportable.append(entry)

    if reportable:
        _log(f"[startup_check] showing previous-run notification ({len(reportable)} stale)")
        show_previous_run_notification(reportable)

    try:
        path = _create_marker(os.getpid())
    except Exception as exc:
        _log(f"[startup_check] could not create marker: {exc}")
        return
    _current_marker_path = path
    atexit.register(cleanup_current_marker)
    _log(f"[startup_check] created marker {os.path.basename(path)}")


def install_unclean_exit_detection():
    """Check for a previous abnormal exit, then mark this instance as running."""
    if not ENABLE_UNCLEAN_EXIT_DETECTION:
        return
    try:
        _install()
    except Exception as exc:
        try:
            _log(f"[startup_check] installation failed: {exc}")
        except Exception:
            pass
